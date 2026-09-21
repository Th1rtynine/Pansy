"""Bangumi: 条目、简介、制作人员、标签、封面。

读公开条目不需要令牌(带令牌才读得到收藏与 NSFW 条目;不带令牌那类返回 404 而不是 403)。搜索用
`POST /v0/search/subjects`,body 里可按类型过滤并翻页,响应带 `platform` 与 `date`。制作人员读
`infobox`,不读 `/v0/subjects/{id}/persons`(一部动画五百多条);infobox 键名由编辑手写,按同义词组匹配。
"""

from __future__ import annotations

import re
from dataclasses import replace

from app.sources.base import Candidate, Suggestion, VolumeDraft, WorkIdentity, snippet
from app.sources.http import get_json, post_json
from app.config import load_source_settings
from app.sources.query import flat

BASE = "https://api.bgm.tv"
SEARCH_URL = f"{BASE}/v0/search/subjects"
SUBJECT_URL = f"{BASE}/v0/subjects/{{id}}"
RELATIONS_URL = f"{SUBJECT_URL}/subjects"

# 关系标签不总是 ``原作``:动画指向原作常写 ``书籍``,视觉小说改编写 ``游戏``;单行本、画集、番外篇、前传是相关条目,不收。
ORIGIN_RELATIONS = {"原作", "书籍", "游戏"}
IDENTITY_HOPS = 3

# 职位与发行方:infobox 键名由编辑手写,一组一组地认。
ROLE_KEYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("导演", ("导演", "监督", "総監督")),
    ("剧本", ("剧本", "脚本", "系列构成", "シナリオ")),
    ("原画", ("原画", "人物设定", "角色设计", "キャラクターデザイン")),
    ("音乐", ("音乐", "音楽", "主题歌")),
    ("原作", ("原作", "原作イラスト")),
)

ORG_KEYS = ("开发", "开发商", "開発", "出版社", "发行", "动画制作", "制作")

TAG_STOP_WORDS = {
    "tv", "ova", "oad", "web", "剧场版", "动画", "漫画", "小说", "轻小说", "游戏", "galgame",
    "书籍", "画集", "连载", "完结", "已完结", "连载中", "单行本", "文库", "原作", "日本",
    "bgm", "bangumi", "三次元", "音乐", "同人", "汉化", "中文", "简体中文",
}

TAG_LIMIT = 20


class Bangumi:
    name = "bangumi"
    label = "Bangumi"
    prefers_cjk = True
    # Bangumi 类型编号:1 书籍、2 动画、3 音乐、4 游戏、6 三次元;漫画与轻小说都是「书籍」。
    BUCKETS = {"books": 1, "anime": 2, "game": 4}
    media_buckets = {
        "manga": "books",
        "light_novel": "books",
        "anime": "anime",
        "game": "game",
    }

    def __init__(self) -> None:
        self.token = load_source_settings().bangumi_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def search(self, keyword: str, limit: int = 8, bucket: str = "") -> list[Candidate]:
        body: dict = {"keyword": keyword}
        # 不带类过滤时音乐专辑会把漫画、小说挤出前 20 条;limit 再大也没用,一次最多回 20 条。
        kind = self.BUCKETS.get(bucket)
        if kind is not None:
            body["filter"] = {"type": [kind]}
        answer = post_json(f"{SEARCH_URL}?limit={limit}", body, self._headers())
        found = []
        # 搜索响应里带着 `series`:系列条目是 True,单行本与画集是 False。
        standing: dict[str, bool] = {}
        for item in (answer or {}).get("data") or []:
            entry_id = item.get("id")
            if entry_id is None:
                continue
            standing[str(entry_id)] = bool(item.get("series"))            # name_cn 经常是空串,这里不能直接解引用。
            found.append(
                Candidate(
                    source=self.name,
                    external_id=str(entry_id),
                    title=item.get("name_cn") or item.get("name") or "",
                    original_title=item.get("name"),
                    year=(item.get("date") or "")[:4] or None,
                    kind=item.get("platform") or None,
                    cover_url=_image(item),
                    media=guess_media(item.get("type"), item.get("platform")),
                    series=bool(item.get("series")),
                )
            )
        return _fold_volumes(found, standing, self._series_of)

    def _series_of(self, item: Candidate) -> Candidate | None:
        """一条单行本的上一层:关系里那一条「系列」。关系是双向的(系列条目指向各卷时写「单行本」),
        这里只认「系列」;系列条目通常自己就在前 20 条里。
        """
        answer = get_json(RELATIONS_URL.format(id=item.external_id), self._headers())
        for related in answer if isinstance(answer, list) else []:
            if isinstance(related, dict) and str(related.get("relation") or "") == "系列":
                chosen = self.fetch(str(related.get("id")))
                if chosen is not None:
                    return chosen
        return None

    def volumes_of(self, external_id: str) -> list[VolumeDraft]:
        """一个系列底下的卷:关系里那些「单行本」,再各取一次补日期与简介。上限 `VOLUME_LIMIT` 卷,
        前 `VOLUME_FETCHES` 卷才各取一次(关系接口不给日期与简介);封面只带地址回去,取不到的卷不丢。
        """
        answer = get_json(RELATIONS_URL.format(id=external_id), self._headers())
        drafts = _volumes_from(answer)
        enriched: list[VolumeDraft] = []
        for index, draft in enumerate(drafts[:VOLUME_LIMIT]):
            if index >= VOLUME_FETCHES:
                # 超出的那些只留关系里给的名字与卷号,不再各问一次上游。
                enriched.append(draft)
                continue
            entry = get_json(SUBJECT_URL.format(id=draft.external_id), self._headers())
            if not isinstance(entry, dict):
                enriched.append(draft)
                continue
            enriched.append(
                replace(
                    draft,
                    title=draft.title or entry.get("name") or None,
                    published_on=(entry.get("date") or "")[:10] or None,
                    summary=entry.get("summary") or None,
                    cover_url=_image(entry),
                )
            )
        return enriched

    def fetch(self, external_id: str) -> Candidate | None:
        """按 id 取回这一条:名字、别名、类型推测。搜索接口不回别名,而「补全」要的正是别名。"""
        entry = get_json(SUBJECT_URL.format(id=external_id), self._headers())
        if not isinstance(entry, dict) or entry.get("id") is None:
            return None
        return Candidate(
            source=self.name,
            external_id=str(entry["id"]),
            title=entry.get("name_cn") or entry.get("name") or "",
            original_title=entry.get("name"),
            year=(entry.get("date") or "")[:4] or None,
            kind=entry.get("platform") or None,
            cover_url=_image(entry),
            media=guess_media(entry.get("type"), entry.get("platform")),
            aliases=tuple(_infobox_values(entry.get("infobox"), "别名")),
        )

    def identity(self, external_id: str) -> WorkIdentity | None:
        """Walk conservative adaptation relations to a shared work title. Only the source-like labels
        above participate and title similarity picks among the many neighbours (soundtracks, guide
        books, sequels...); three hops cover anime -> manga -> novel.
        """

        current = self.fetch(external_id)
        if current is None:
            return None

        visited = {current.external_id}
        relations: list[str] = []
        for _ in range(IDENTITY_HOPS):
            answer = get_json(RELATIONS_URL.format(id=current.external_id), self._headers())
            related = answer if isinstance(answer, list) else []
            chosen = _pick_identity_relation(current, related, visited)
            if chosen is None:
                break
            found = self.fetch(str(chosen["id"]))
            if found is None or found.external_id in visited:
                break
            visited.add(found.external_id)
            relations.append(str(chosen.get("relation") or "关联"))
            current = found

        return WorkIdentity(candidate=current, relations=tuple(relations))

    def suggest(self, external_id: str) -> list[Suggestion]:
        entry = get_json(SUBJECT_URL.format(id=external_id), self._headers())
        if not isinstance(entry, dict):
            return []

        url = f"https://bgm.tv/subject/{external_id}"
        names = [entry.get("name") or "", entry.get("name_cn") or ""]
        found: list[Suggestion] = []

        def add(field: str, value: str | None, excerpt: str | None = None, role: str | None = None) -> None:
            if not value:
                return
            found.append(
                Suggestion(
                    field=field,
                    value=value.strip(),
                    source=self.name,
                    external_id=external_id,
                    url=url,
                    role=role,
                    excerpt=excerpt,
                )
            )

        add("title", entry.get("name_cn"))
        add("original_title", entry.get("name"))
        # The subject is a carrier too, so its own display name also belongs on Edition.title.
        add("edition_title", entry.get("name_cn") or entry.get("name"))
        add("summary", entry.get("summary"), snippet(entry.get("summary")))

        date = (entry.get("date") or "").strip()
        if date and date != "0000-00-00":
            add("published_on", date, f"Bangumi 记的日期:{date}")

        for key in ORG_KEYS:
            value = _infobox_text(entry.get("infobox"), key)
            if value:
                add("org", value, f"infobox「{key}」")
                break

        for role, keys in ROLE_KEYS:
            for key in keys:
                value = _infobox_text(entry.get("infobox"), key)
                if value:
                    # 一条 infobox 值可能挤着好几个人(「音乐」那格是 `麻枝准、折戸伸治…`),而库里一条
                    # 记录一个人,所以拆开;括号里逐集的分工没地方放,丢掉。
                    for name in _split_names(value):
                        add("creator", name, f"infobox「{key}」", role=role)
                    break

        for alias in _infobox_values(entry.get("infobox"), "别名"):
            add("alias", alias, "infobox「别名」")

        for tag in entry.get("tags") or []:
            name = (tag or {}).get("name") or ""
            if name and not _is_noise_tag(name, names):
                add("tag", name, f"Bangumi 标签,{tag.get('count', 0)} 人标过")
                if len([item for item in found if item.field == "tag"]) >= TAG_LIMIT:
                    break

        add("cover_url", _image(entry))

        return found


#: 一次最多读多少卷:一部漫画几十卷是常事,上百卷就不像「一部作品」了,而且每卷各取一次就是几百次请求。
VOLUME_LIMIT = 100

#: 其中最多为几卷再各取一次详情(日期、简介、封面):一卷一次,不该一口气打上百次上游。
VOLUME_FETCHES = 40

# 卷号:名字结尾带括号的一到三位数字(「(01)」「(3.5)」)或不带宽括号的「第 3 巻」;四位数字是年份,不算。
_VOLUME_NUMBER = re.compile(
    r"[（(\[【]\s*(?:第\s*)?(?P<number>\d{1,3}(?:\.\d)?)\s*(?:巻|卷|册|冊|集|話|话)?\s*[)）\]】]\s*$"
)
_VOLUME_CN = re.compile(r"第\s*(?P<number>\d{1,3}(?:\.\d)?)\s*[巻卷册冊集話话]")


def _volume_number(title: str | None) -> float | None:
    """这条名字里的卷号;认不出就是 None。"""
    text = (title or "").strip()
    found = _VOLUME_NUMBER.search(text) or _VOLUME_CN.search(text)
    return float(found.group("number")) if found else None


def _volumes_from(related: object) -> list[VolumeDraft]:
    """关系表 → 卷(纯函数,不连网)。只认 `relation == "单行本"`(系列条目指向各卷时写的就是这两个字);
    按卷号排,认不出卷号的排最后。
    """
    drafts: list[VolumeDraft] = []
    for item in related if isinstance(related, list) else []:
        if not isinstance(item, dict) or str(item.get("relation") or "") != "单行本":
            continue
        entry_id = item.get("id")
        if entry_id is None:
            continue
        title = str(item.get("name_cn") or item.get("name") or "") or None
        drafts.append(
            VolumeDraft(
                source=Bangumi.name,
                external_id=str(entry_id),
                number=_volume_number(title),
                title=title,
            )
        )
    drafts.sort(key=lambda draft: (draft.number is None, draft.number or 0.0))
    return drafts


#: 一次搜索里最多走几步去问「单行本的上一层」(兜底:系列条目通常自己就在前 20 条里)。
VOLUME_WALKS = 3

# 结尾带卷号的书名:「(01)」「第 3 巻」「Vol.2」。数字只认一到三位 —— 四位是年份。
_VOLUME = re.compile(
    r"^(?P<base>.+?)\s*(?:"
    r"[（(\[【]\s*(?:第\s*)?\d{1,3}\s*(?:巻|卷|册|冊|集|話|话)?\s*[)）\]】]"
    r"|第\s*\d{1,3}\s*(?:巻|卷|册|冊|集|話|话)"
    r"|[Vv]ol\.?\s*\d{1,3}"
    r")\s*$"
)


def _volume_base(title: str | None) -> str | None:
    """这条书名是不是「某部的第几卷」;是就回它上一层那个名字,不是就回 None。"""
    found = _VOLUME.match((title or "").strip())
    return found.group("base").strip() if found else None


def _fold_volumes(
    found: list[Candidate],
    standing: dict[str, bool],
    series_of,
) -> list[Candidate]:
    """把同一系列的单行本折成一条:候选里只留上一层(Bangumi 那边每卷是各自独立的书籍条目,卷由我们的
    `volume` 记)。折法按顺序:同名且不带卷号的那一条 → 顺「系列」关系问一步(`series_of`) → 都不成则留
    最早那一卷、改用上一层的名字(外部 id 不变),替换在第一卷原来的位置上。
    """
    groups: dict[str, list[Candidate]] = {}
    for item in found:
        base = _volume_base(item.title or item.original_title)
        if base is not None:
            groups.setdefault(flat(base), []).append(item)

    # 系列条目自己不带卷号,所以按名字认它(`name` 与 `name_cn` 两个都算)。
    by_name: dict[str, list[Candidate]] = {}
    for item in found:
        if _volume_base(item.title or item.original_title) is not None:
            continue
        for name in item.titles():
            by_name.setdefault(flat(name), []).append(item)

    folded: dict[str, Candidate] = {}
    echoed: set[str] = set()
    walked = 0
    for key, group in groups.items():
        named = by_name.get(key) or []
        # 同名的那几条里,`series` 为真的优先(同一个名字也可能有一本同名画集)。
        chosen = next((item for item in named if standing.get(item.external_id)), None)
        if chosen is None and named:
            chosen = named[0]
        if chosen is not None:
            echoed.add(group[0].external_id)
        if chosen is None and walked < VOLUME_WALKS:
            walked += 1
            chosen = series_of(group[0])
        if chosen is None:
            first = group[0]
            chosen = replace(
                first,
                title=_volume_base(first.title or first.original_title) or first.title,
            )
        folded[group[0].external_id] = chosen

    out: list[Candidate] = []
    for item in found:
        if _volume_base(item.title or item.original_title) is None:
            out.append(item)
            continue
        chosen = folded.get(item.external_id)
        if chosen is not None and item.external_id not in echoed:
            out.append(chosen)
    return out


def _pick_identity_relation(
    current: Candidate, related: list[object], visited: set[str]
) -> dict | None:
    """Pick the most plausible original-work neighbour, or decline to guess: 标题相同或互相包含是强证据,单个像原作的选择直接认,几个互不相关的都留作载体。"""

    # Relation labels name the *target* kind, not a direction: an anime points to its source as 书籍/游戏,
    # while a source manga also points to later game adaptations as 游戏. 按当前载体类型限步,免得走过原作走进改编。
    allowed = {"原作"}
    if current.media == "anime":
        allowed.update({"书籍", "游戏"})
    elif current.media == "manga":
        allowed.add("书籍")
    elif current.media is None:
        allowed.update(ORIGIN_RELATIONS)

    eligible = [
        item
        for item in related
        if isinstance(item, dict)
        and str(item.get("relation") or "") in allowed
        and str(item.get("id") or "") not in visited
    ]
    if not eligible:
        return None

    current_names = [flat(name) for name in current.titles() if flat(name)]

    def score(item: dict) -> int:
        relation = str(item.get("relation") or "")
        points = 100 if relation == "原作" else 20
        names = [flat(item.get("name_cn")), flat(item.get("name"))]
        names = [name for name in names if name]
        for left in current_names:
            for right in names:
                if left == right:
                    points = max(points, 90)
                elif left in right or right in left:
                    # Prefer the closer contained title, so a plain series entry beats a guidebook.
                    points = max(points, 65 - min(20, abs(len(left) - len(right))))
        return points

    ranked = sorted(eligible, key=score, reverse=True)
    best = ranked[0]
    # One explicit relation is useful even for a renamed adaptation; several weak ones stay carriers.
    if len(ranked) > 1 and score(best) <= 20:
        return None
    return best


def _image(entry: dict) -> str | None:
    images = entry.get("images") or {}
    return images.get("large") or images.get("common") or images.get("medium") or None


def guess_media(entry_type: object, platform: object) -> str | None:
    """把 Bangumi 的 `type`(+ `platform`)翻成我们这边的类型,翻不出来就是 None。`2` 动画、`4` 游戏,
    `1`(书籍)再看 `platform` 分漫画与小说;`3` 音乐、`6` 三次元与画集、写真集一律 None。翻错只是候选
    被分到隔壁那一组,类型始终要人点了才算。
    """
    text = str(platform or "").strip()
    if entry_type == 2:
        return "anime"
    if entry_type == 4:
        return "game"
    if entry_type == 1:
        if "漫画" in text:
            return "manga"
        # Bangumi 的「小说」不分轻小说与一般小说,这里一律按轻小说起草,人可在表单上改。
        if "小说" in text or "輕小說" in text or "轻小说" in text:
            return "light_novel"
    return None


def _is_noise_tag(name: str, names: list[str]) -> bool:
    """类型、平台、状态那一类,以及条目自己的名字,都不当标签收。"""
    flat = name.strip().lower().replace(" ", "")
    if flat in TAG_STOP_WORDS:
        return True
    return any(flat == (other or "").strip().lower().replace(" ", "") for other in names if other)


def _infobox_values(infobox: object, key: str) -> list[str]:
    """infobox 里某个键的值,拉平成字符串表。值的形态有字符串、`[{"v": …}]` 和数组里带 `{k, v}` 的嵌套,
    「别名」那一项两种混着出现,都收。
    """
    for item in infobox or []:
        if not isinstance(item, dict) or key not in str(item.get("key", "")):
            continue
        value = item.get("value")
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            out = []
            for element in value:
                if isinstance(element, dict) and element.get("v"):
                    out.append(str(element["v"]).strip())
                elif isinstance(element, str) and element.strip():
                    out.append(element.strip())
            return [item for item in out if item]
    return []


def _infobox_text(infobox: object, key: str) -> str | None:
    values = _infobox_values(infobox, key)
    return "、".join(values) if values else None


def _split_names(value: str) -> list[str]:
    """把一个挤了好几个人的 infobox 值拆成一个个名字。括号里是逐条线的分工,按分隔符一把切会切出
    「AFTER STORY 担当)」这种碎片,所以先按深度扫一遍、只在括号外拆;括号连同里面的分工一起去掉。
    """
    pieces: list[str] = []
    current: list[str] = []
    depth = 0
    for char in value:
        if char in "(（":
            depth += 1
        elif char in ")）":
            depth = max(0, depth - 1)
        if char in "、,，;；" and depth == 0:
            pieces.append("".join(current))
            current = []
            continue
        current.append(char)
    pieces.append("".join(current))

    names = []
    for piece in pieces:
        name = re.sub(r"[（(].*?[)）]", "", piece).strip()
        if name:
            names.append(name)
    return names
