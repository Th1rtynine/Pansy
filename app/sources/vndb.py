"""VNDB: 视觉小说的标题、开发商、制作人员、标签、封面。公开数据不需要凭据,令牌只管个人收藏。
与 Bangumi 不同:id 是带前缀的字符串(`v4`)不是整数;中文名多半只在 `aliases` 里;`staff.role`
是枚举;`tags` 带 `rating`/`spoiler`/`category`;`/vn` 没有「卷」这一层,只取 `/vn`。
"""

from __future__ import annotations

import re
from urllib.parse import quote

from app.sources.base import Candidate, SourceRelation, Suggestion, WorkIdentity, snippet
from app.sources.http import get_json_with_status, post_json

API = "https://api.vndb.org/kana/vn"
#: 令牌校验用。`API` 那一行是具体端点,这个只到 `/kana`,好让下面拼出 `/kana/authinfo`。
KANA = "https://api.vndb.org/kana"
SITE = "https://vndb.org/{id}"

# 整个站只有视觉小说一类,所以类型推测在这里是个常数。
MEDIA = "game"

SEARCH_FIELDS = "id,title,alttitle,released,image.url"
# 比搜索多一个 `aliases`:中文名常常只出现在别名里,所以「补全」要它。
FETCH_FIELDS = "id,title,alttitle,aliases,released,image.url"
DETAIL_FIELDS = ",".join(
    (
        "id",
        "title",
        "alttitle",
        "titles{lang,title,latin,main}",
        "aliases",
        "released",
        "description",
        "image.url",
        "developers{name,original}",
        "tags{name,rating,spoiler,category}",
        "staff{id,name,original,role}",
    )
)

# 职位:VNDB 的 `staff_role` 枚举 → 库里的词。翻译、编辑、QA、staff 不收:库里记的是「谁做了
# 这一部」,收进来作者表会被淹掉(CLANNAD 一条就带九十多个翻译者)。
STAFF_ROLES = {
    "scenario": "剧本",
    "director": "导演",
    "chardesign": "原画",
    "art": "原画",
    "music": "音乐",
    "songs": "音乐",
}

# 一次最多给几条标签。VNDB 的条目动辄上百个标签,而这是给人过目的一张表。
TAG_LIMIT = 20

# 年代、年份、季节不是题材,一律不收。
_NOISE_TAG = re.compile(
    r"^(\d{4}s?|\d{4}\s*[-–]\s*\d{4}|heisei era|showa era|taisho era|meiji era"
    r"|spring|summer|autumn|fall|winter)$",
    re.IGNORECASE,
)


class Vndb:
    name = "vndb"
    label = "VNDB"
    # 条目名就是原文标题,中文名多半只在别名里,所以这个源吃原名/拉丁字。
    prefers_cjk = False
    # `bucket` 传什么都不改变请求,只是让调用方按同一套写法问它。
    media_buckets = {"game": "vn"}

    def configured(self) -> bool:
        """**永远 True:这个源就没有「缺凭据」这种状态。**

        读公开条目不需要令牌(见 `verify_token`),那一格是留给「同步你自己账号的收藏」的。
        所以这里不能照「凭据填了没有」去答 —— 那会让页面把一个明明能用的源报成没配好。
        """
        return True

    def relations_of(self, external_id: str) -> list[SourceRelation]:
        """**空表:VNDB 没有跨媒体关系图。**

        `/vn` 只回「关联作品」那一栏(续作、外传),没有 Bangumi 那种「这一部是那一部的动画改编」的
        关系表;而且整个站只有视觉小说一类,本来就没有跨媒体可言。所以家族归组在 VNDB 上拿不到东西 ——
        **回空表是对的,不是缺陷**(与 `volumes_of` 同一种待遇)。
        """
        return []

    @staticmethod
    def verify_token(token: str) -> tuple[bool, str, dict]:
        """拿这个令牌去问一句 VNDB「这是谁」。回 `(能不能用, 一句话, 账号资料)`。

        **读公开条目根本不需要令牌**,所以这一格就算不填,VNDB 照样是个完整可用的源。
        它有的用途只有一个:读**你自己账号里的收藏**。而 `GET /authinfo` 正好能回答
        「这枚令牌是谁的、带着哪些权限」—— 顺带就把设置页那块账号区域填上了。

        VNDB 的令牌在 `Authorization` 头里用的是 **`Token`** 这个类型,不是 `Bearer`;
        而且令牌本身形如 `xxxx-xxxxx-...`,中间那些短横线可以省。
        """
        token = token.strip()
        if not token:
            return False, "还没有填 VNDB 的 API 令牌。", ""

        answer, status = get_json_with_status(
            f"{KANA}/authinfo", {"Authorization": f"Token {token}"}
        )
        if status == 200 and isinstance(answer, dict):
            who = str(answer.get("username") or "").strip()
            permissions = [str(item) for item in (answer.get("permissions") or [])]
            detail = f"令牌有效,对应 VNDB 账号「{who}」。" if who else "令牌有效。"
            if permissions:
                detail += "权限:" + "、".join(permissions) + "。"
            return True, detail, _account_shape(answer)
        if status in (401, 403):
            return (
                False,
                "VNDB 说这个令牌不对(401)。检查有没有复制完整、或者它是不是已经被撤销了。",
                "",
            )
        if status is None:
            return False, "连不上 VNDB,没法验证。网络通了再试,令牌已经填进去了。", ""
        return False, f"VNDB 回了 {status},没法确认这个令牌。", ""

    def search(self, keyword: str, limit: int = 8, bucket: str = "") -> list[Candidate]:
        answer = post_json(
            API,
            {
                "filters": ["search", "=", keyword],
                "fields": SEARCH_FIELDS,
                "sort": "searchrank",
                "results": limit,
            },
        )
        found = []
        for item in (answer or {}).get("results") or []:
            entry_id = item.get("id")
            if not entry_id:
                continue
            found.append(
                Candidate(
                    source=self.name,
                    external_id=str(entry_id),
                    title=item.get("title") or "",
                    original_title=item.get("alttitle"),
                    year=(item.get("released") or "")[:4] or None,
                    kind="视觉小说",
                    cover_url=_image(item),
                    media=MEDIA,
                )
            )
        return found

    def fetch(self, external_id: str) -> Candidate | None:
        """按 id 取回这一条:名字与别名。"""
        answer = post_json(API, {"filters": ["id", "=", external_id], "fields": FETCH_FIELDS})
        results = (answer or {}).get("results") or []
        if not results:
            return None
        item = results[0]
        return Candidate(
            source=self.name,
            external_id=str(item.get("id") or external_id),
            title=item.get("title") or "",
            original_title=item.get("alttitle"),
            year=(item.get("released") or "")[:4] or None,
            kind="视觉小说",
            cover_url=_image(item),
            media=MEDIA,
            aliases=tuple(str(alias) for alias in item.get("aliases") or []),
        )

    def identity(self, external_id: str) -> WorkIdentity | None:
        """VNDB currently has no relation rule used by Pansy; use the entry itself."""

        found = self.fetch(external_id)
        return WorkIdentity(candidate=found) if found is not None else None

    def suggest(self, external_id: str) -> list[Suggestion]:
        answer = post_json(API, {"filters": ["id", "=", external_id], "fields": DETAIL_FIELDS})
        results = (answer or {}).get("results") or []
        if not results:
            return []
        entry = results[0]

        url = SITE.format(id=external_id)
        found: list[Suggestion] = []

        def add(field: str, value: str | None, excerpt: str | None = None, role: str | None = None) -> None:
            if not value:
                return
            found.append(
                Suggestion(
                    field=field,
                    value=str(value).strip(),
                    source=self.name,
                    external_id=external_id,
                    url=url,
                    role=role,
                    excerpt=excerpt,
                )
            )

        display_title = _title(entry, ("zh-Hans", "zh-Hant")) or entry.get("title")
        add("title", _title(entry, ("zh-Hans", "zh-Hant")), "VNDB 上的中文标题")
        add("original_title", _title(entry, ("ja",)) or entry.get("alttitle") or entry.get("title"))
        add("edition_title", display_title)
        add("summary", entry.get("description"), snippet(entry.get("description")))

        released = (entry.get("released") or "").strip()
        # 「TBA」不是日期,是「还没定」,当没有处理。
        if released and released != "TBA":
            add("published_on", released, f"VNDB 记的发售日:{released}")

        for developer in entry.get("developers") or []:
            add("org", developer.get("name") or developer.get("original"), "VNDB developers")

        for member in entry.get("staff") or []:
            role = STAFF_ROLES.get(str(member.get("role") or ""))
            name = member.get("name") or member.get("original")
            if role and name:
                add("creator", name, f"VNDB staff.role={member.get('role')}", role=role)

        for tag in _content_tags(entry.get("tags")):
            add("tag", tag.get("name"), f"VNDB 标签,评分 {tag.get('rating')}")

        add("cover_url", _image(entry))

        return found


def _account_shape(answer: dict) -> dict:
    """`/authinfo` 的响应 → 我们那一份缓存的形状。

    VNDB 那边给的东西很少:`id`(`u3`)、`username`、`permissions`。它**没有头像**,所以
    `avatar_url` 留空 —— 设置页那块账号卡会自动退化成"名字首字"的占位,版式不变。

    `id` 在这里是**字符串**(`u3` 那种格式),而库里那几处都按可空整数走,所以顺手拆掉前缀、
    不认识就留空。`bio` 与 `signature` 它压根不给,一并留空。
    """
    raw_id = str(answer.get("id") or "")
    digits = raw_id.lstrip("uU") if raw_id[:1] in ("u", "U") else raw_id
    return {
        "id": int(digits) if digits.isdigit() else None,
        "name": str(answer.get("username") or ""),
        "nickname": str(answer.get("username") or ""),
        "avatar_url": "",
        "bio": "",
        "signature": "",
        # VNDB 不给注册时间。
        "registered_at": "",
    }


def _image(entry: dict) -> str | None:
    image = entry.get("image") or {}
    return image.get("url") or image.get("thumbnail") or None


def _title(entry: dict, languages: tuple[str, ...]) -> str | None:
    """`titles` 里某个语言的标题;没有就 None(不拿罗马字标题冒充中文)。"""
    for wanted in languages:
        for title in entry.get("titles") or []:
            if title.get("lang") == wanted and title.get("title"):
                return str(title["title"])
    return None


def _content_tags(tags: object) -> list[dict]:
    """只收内容类标签,按评分从高到低取前若干条:剧透级别 2 与年代季节一概不收。"""
    kept = []
    for tag in tags or []:
        if not isinstance(tag, dict) or not tag.get("name"):
            continue
        if tag.get("category") != "cont":
            continue
        if tag.get("spoiler") == 2 or _NOISE_TAG.match(str(tag["name"]).strip()):
            continue
        kept.append(tag)
    kept.sort(key=lambda item: item.get("rating") or 0, reverse=True)
    return kept[:TAG_LIMIT]
