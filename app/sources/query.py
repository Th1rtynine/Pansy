"""认「人敲进那一个框里的东西」:一个名字,或某站的一条(bgm:294993 / 294993 /
https://bgm.tv/subject/294993 / vndb:v4)。

一到三位纯数字当名字(「86」是作品),四位以上才算 Bangumi id,前缀不认识的整串也当名字。
别名不当搜索的词;一个源吃哪种名字写在它自己身上(`Source.prefers_cjk`),由 `pick_name()` 挑。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 站名的几种写法:前缀不在表里的整串当名字。
PREFIXES = {
    "bgm": "bangumi",
    "bangumi": "bangumi",
    "chii": "bangumi",
    "vndb": "vndb",
}

# id 的写法:`站名:编号`,编号前面可以带一两个字母(VNDB 的是 v4)。
_ASK = re.compile(r"^(?P<prefix>[A-Za-z]+)\s*[:：]\s*(?P<body>[A-Za-z]{0,3}\d{1,10})$")
_BANGUMI_URL = re.compile(
    r"^https?://(?:www\.)?(?:bgm\.tv|bangumi\.tv|chii\.in)/subject/(?P<id>\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)
_BARE_BANGUMI_ID = re.compile(r"^\d{4,10}$")

# 波浪线与各种长短横混着用(Bangumi `〜AFTER STORY〜`、VNDB `-AFTER STORY-`),比对时当作同一种。
_DASHES = re.compile(r"[〜～~\-–—―]")
# 结尾被横线隔开、又全是假名的那一段是读音(`CLANNAD-クラナド-`):比对时丢掉,两种写法才算一组。
_TRAILING_READING = re.compile(r"[-–—―]\s*[\u3040-\u30ff]+\s*[-–—―]?\s*$")
# 空白与标点不参与比对(「CLANNAD (1)」与「CLANNAD(1)」是同一条),但括号里的编号要留着:那是两条不同的卷。
_NOISE = re.compile(r"[\s\-–—―_・:：;；/／!！?？.,、'\"“”()（）\[\]【】]+")
_CJK = re.compile(r"[\u3400-\u9fff]")


@dataclass(frozen=True)
class Ask:
    """那个框里认出来的东西:要么是一个词,要么是某站的一条。"""

    keyword: str = ""
    source: str = ""
    external_id: str = ""

    @property
    def by_id(self) -> bool:
        return bool(self.external_id)


def parse(text: str) -> Ask:
    """认一个框里的东西。认不出来就是名字,不报错。"""
    raw = (text or "").strip()
    linked = _BANGUMI_URL.match(raw)
    if linked:
        return Ask(source="bangumi", external_id=linked.group("id"))
    found = _ASK.match(raw)
    if found:
        source = PREFIXES.get(found.group("prefix").lower())
        if source:
            body = found.group("body").lower()
            # VNDB 的条目一律写作 v4;人写「4」也认,补上那个 v 再去问。
            if source == "vndb" and not body.startswith("v"):
                body = f"v{body}"
            return Ask(source=source, external_id=body)
    if _BARE_BANGUMI_ID.match(raw):
        return Ask(source="bangumi", external_id=raw)
    return Ask(keyword=raw)


def flat(text: str | None) -> str:
    """把一个名字化到能比对的形状:去空白标点、统一横线、丢掉结尾的读音。页面上的「同一条」也按它分
    (后端把结果放进 `CandidateOut.group`)。"""
    value = _DASHES.sub("-", (text or "").strip().lower())
    value = _TRAILING_READING.sub("", value)
    return _NOISE.sub("", value)


def has_cjk(text: str | None) -> bool:
    """这个名字里有没有汉字。用来决定它该给谁搜。"""
    return bool(_CJK.search(text or ""))


def pick_name(names: list[str], prefer_cjk: bool) -> str:
    """从一串写法里挑一个,给某个源去搜。挑不出来(VNDB 只有拉丁字标题、目标是吃中文名的 Bangumi)
    就用第一个 —— 搜不到顶多少几条候选,不会搜错。"""
    for name in names:
        if has_cjk(name) == prefer_cjk:
            return name
    return names[0] if names else ""

