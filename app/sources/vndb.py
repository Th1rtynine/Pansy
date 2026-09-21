"""VNDB: 视觉小说的标题、开发商、制作人员、标签、封面。公开数据不需要凭据,令牌只管个人收藏。
与 Bangumi 不同:id 是带前缀的字符串(`v4`)不是整数;中文名多半只在 `aliases` 里;`staff.role`
是枚举;`tags` 带 `rating`/`spoiler`/`category`;`/vn` 没有「卷」这一层,只取 `/vn`。
"""

from __future__ import annotations

import re

from app.sources.base import Candidate, Suggestion, WorkIdentity, snippet
from app.sources.http import post_json

API = "https://api.vndb.org/kana/vn"
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
