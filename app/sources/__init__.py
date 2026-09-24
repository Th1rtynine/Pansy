"""The outside sources, gathered so callers ask for one by name.

Adding a source is one module plus one line in `SOURCES` below. Nothing else in
the app knows the names of individual sources.
"""

from app.sources.base import Candidate, Source, Suggestion
from app.sources.bangumi import Bangumi
from app.sources.hikarinagi import Hikarinagi
from app.sources.vndb import Vndb

SOURCES: dict[str, Source] = {
    source.name: source for source in (Bangumi(), Vndb(), Hikarinagi())
}

# 页面上那一句话:这个源能给什么。只说明它是什么,不说我们怎么用它。
HINTS = {
    "bangumi": "动画、漫画、轻小说的条目、简介与制作人员",
    "vndb": "视觉小说的原名、开发商、制作人员与标签",
    "hikarinagi": "Galgame、轻小说与漫画的条目、分卷、制作人员与标签",
}

# 没有凭据时,让人去哪儿把它配上。**键少一个也能跑**:源没写就退回那句通用的。
CONFIGURE_HINTS = {
    "bangumi": "去设置页填一个 Bangumi 访问令牌",
    "hikarinagi": "去设置页填 Hikarinagi 的 client_id 与 client_secret",
}

#: 源没写 `configure_hint` 时用这一句。
DEFAULT_CONFIGURE_HINT = "去设置页把它的凭据填上"


def configure_hint(name: str) -> str:
    """这个源现在没法用,该去哪儿配。**由源自己或这张表说了算,页面不自己编。**"""
    source = get(name)
    written = getattr(source, "configure_hint", "")
    if written:
        return str(written)
    return CONFIGURE_HINTS.get(name, DEFAULT_CONFIGURE_HINT)


def configured(name: str) -> bool:
    """这个源现在能不能用 —— **页面与接口问的是这一件事,不是「填了几格凭据」**。

    两种,不能一律回 True:不需要凭据的源(VNDB 读公开内容)永远算能用,它没有「缺凭据」这种
    状态;需要凭据的源问它自己 `configured()`,答 True 就是撒谎。

    **这个函数放在这里,是为了只有一份。** 先前 `app/api/settings.py` 与 `app/api/sources.py`
    各写了一个私有的,同名的两个私有函数给出的答案还不一样(源认不出来时一个退回看凭据、一个回
    True)—— 同一个问题两个答案,迟早会漂开。
    """
    source = get(name)
    ask = getattr(source, "configured", None)
    if callable(ask):
        return bool(ask())
    # **源答不出来时按「凭据填齐了没有」算,不回 True**:把不知道说成"能用",页面上就会对着一个
    # 真需要凭据的源不提示去哪儿配。
    from app.settings_store import has_credentials

    return has_credentials(name)


def get(name: str) -> Source | None:
    return SOURCES.get(name)


__all__ = [
    "Candidate",
    "CONFIGURE_HINTS",
    "HINTS",
    "SOURCES",
    "Source",
    "Suggestion",
    "configure_hint",
    "configured",
    "get",
]
