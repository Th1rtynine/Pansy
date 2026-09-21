"""The outside sources, gathered so callers ask for one by name.

Adding a source is one module plus one line in `SOURCES` below. Nothing else in
the app knows the names of individual sources.
"""

from app.sources.base import Candidate, Source, Suggestion
from app.sources.bangumi import Bangumi
from app.sources.vndb import Vndb

SOURCES: dict[str, Source] = {source.name: source for source in (Bangumi(), Vndb())}

# 页面上那一句话:这个源能给什么。只说明它是什么,不说我们怎么用它。
HINTS = {
    "bangumi": "动画、漫画、轻小说的条目、简介与制作人员",
    "vndb": "视觉小说的原名、开发商、制作人员与标签",
}


def get(name: str) -> Source | None:
    return SOURCES.get(name)


__all__ = ["Candidate", "HINTS", "SOURCES", "Source", "Suggestion", "get"]
