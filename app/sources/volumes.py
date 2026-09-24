"""把几个来源上的卷合成一份:同一卷只留一行,冲突如实报出来。

**为什么是纯函数**:这里全是判断 —— 哪个算同一条、哪一条该覆盖哪一条、哪些说不清。夹着库和网络写,
就只能靠端到端试,而端到端试不出「两个来源卷号一样但名字不同」这种角落。所以这一段不碰库、不连网,
只吃 `VolumeDraft` 列表(见 `app/sources/base.py`),出去还是列表。

**规矩(照规格)**:

1. 先看**明确的外部 id**:同一个来源的同一条,天生就是一行。
2. 再看**卷号**:来源各说各的,但「第 3 卷」在两处通常是同一卷。
3. 再看**规范化卷名**:没有号、或者号对不上时,名字一样多半是同一卷。
4. 再看**出版日期**:名字都没有(番外那种只有番号文本)时,同一天出的算同一卷。
5. 最后才是 ISBN 一类稳定字段 —— **眼下没有任何一个源给 ISBN**,所以这一档留着位置、
   不假装在比:少一档比多一档假的好。真拿到了再加,加的时候这一段有测试兜着。

**没有一条对得上就不合并**,也不猜:两卷说不清是不是同一卷,就各留一行、把疑问写进 `conflicts`。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.sources.base import VolumeDraft

#: 名字里那些与「第几卷」无关的装饰。归一化时一律去掉,只留下用来比的名字。
_DECORATION = re.compile(r"[\s　\-–—_·、,，.。:：;；/()()\[\]【】《》〈〉「」『』!！?？'\"“”‘’]+")

#: 「上 / 下 / 前 / 后 / 中」这种没有数字的卷序 —— 它们是有序的,只是没有号。
_ORDINALS = {
    "上": 1,
    "中": 2,
    "下": 3,
    "前": 1,
    "后": 2,
    "前篇": 1,
    "后篇": 2,
    "上卷": 1,
    "中卷": 2,
    "下卷": 3,
}

#: 卷名里去掉「第 N 卷」之后剩下的部分,用来判两卷是不是同一卷。
_VOLUME_MARK = re.compile(
    r"^(?:"
    r"第?\s*\d{1,3}(?:\.\d)?\s*(?:巻|卷|册|冊|集|話|话|期)?"
    r"|vol\.?\s*\d{1,3}(?:\.\d)?"
    r"|(?:上|中|下|前|后)(?:巻|卷)?"
    r")$",
    re.IGNORECASE,
)


@dataclass
class VolumeMerge:
    """合并的结果:**合出来的卷**,以及两种「要人看一眼」的东西。

    **冲突与提示分开是有意的**:两个来源用不同语言写同一个卷名(「安達としまむら (1)」与
    「安达与岛村 第1卷」)是**正常的**,把它们当冲突报出来,真正的矛盾(日期对不上)就会被淹掉 ——
    实测第一版就是这么报的,满屏都是语言差异。所以:
    `conflicts` 只放**对不上的事实**(日期 / 封面这类),`notes` 放**说明性的差异**(名字写法不同)。
    """

    volumes: list["MergedVolume"] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class MergedVolume:
    """合并之后的一卷。**带着它从哪几个来源来**,所以「这一行是怎么来的」查得回去。"""

    number: float | None
    title: str | None = None
    published_on: str | None = None
    summary: str | None = None
    cover_url: str | None = None
    catalog_code: str | None = None
    page_count: int | None = None
    volume_type: str | None = None
    local_path: str | None = None
    #: 这一卷在哪些来源上是哪一条:`(来源, 外部 id)`,按来源名排序,出结果稳定。
    refs: list[tuple[str, str]] = field(default_factory=list)
    #: 哪几个来源给了它 —— 只有一个来源时说明还没有别的来源印证过。
    sources: list[str] = field(default_factory=list)

    def key(self) -> tuple:
        """判重用的键:`(来源, 外部 id)` 排好序 —— 同一组来源不管以什么顺序合过来都是同一个键。"""
        return (self.number, tuple(sorted(self.refs)))


def normalize_title(title: str | None) -> str:
    """卷名的归一化形式:去装饰、去大小写、全角折半角。**只用来比,不用来显示。**"""
    if not title:
        return ""
    text = title.strip().casefold()
    text = "".join(
        chr(ord(character) - 0xFEE0) if 0xFF01 <= ord(character) <= 0xFF5E else character
        for character in text
    )
    return _DECORATION.sub("", text)


def ordinal_of(title: str | None) -> float | None:
    """「上 / 中 / 下」这种没有数字的卷序。**认不出就 None**,不猜。

    「上巻」「上卷」「下巻」都算 —— 先把结尾那个量词去掉再查表。实测:第一版只查「上」「下」,
    于是「上巻」与「上」被判成两卷(同一卷在日文站与中文站各写一遍)。
    """
    if not title:
        return None
    text = normalize_title(title)
    for suffix in ("巻", "卷", "册", "冊"):
        if len(text) > 1 and text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return _ORDINALS.get(text)


def same_volume(left: VolumeDraft, right: VolumeDraft) -> tuple[bool, str]:
    """这两卷算不算同一卷。回 `(算不算, 凭哪一条认出来的)`。

    **判定顺序就是规格那一条**:外部 id → 卷号 → 规范化卷名 → 出版日期。先认出来的先用。
    """
    if left.source and right.source and left.source == right.source:
        # 同一个来源:它自己给的外部 id 是权威的,不必再看号码。
        return (left.external_id == right.external_id, "外部 id")

    left_name = normalize_title(left.title)
    right_name = normalize_title(right.title)

    # 两边都有号:号一样就是同一卷;号不一样**不合并** —— 不同来源对同一卷的编号常有出入,
    # 但那也可能是两条不同的东西,替人合并比留两行危险得多。
    if left.number is not None and right.number is not None:
        if left.number == right.number:
            return True, "卷号"
        if left_name and left_name == right_name:
            return False, "卷号不一致(名字却一样)"
        return False, "卷号不同"

    # 两边都没号:番外、上下卷这一类。先看卷序,再看名字,最后看日期。
    if left.number is None and right.number is None:
        left_ordinal = ordinal_of(left.title)
        right_ordinal = ordinal_of(right.title)
        if left_ordinal is not None and left_ordinal == right_ordinal:
            return True, "卷序(上下)"
        if left_name and left_name == right_name:
            return True, "卷名"
        if left.published_on and left.published_on == right.published_on:
            return True, "出版日期"
        return False, "对不上"

    # 一个有号一个没号:只有名字或日期完全一致才认为同一卷。
    if left_name and left_name == right_name:
        return True, "卷名"
    if left.published_on and left.published_on == right.published_on:
        return True, "出版日期"
    return False, "对不上"


def merge_volumes(drafts: list[VolumeDraft]) -> VolumeMerge:
    """把几个来源的卷合成一份。回一个 `VolumeMerge`(卷 + 冲突 + 提示)。

    **合并规则**:先到的定下这一行的底子;后来的**只补它没有的格子**(封面、日期、简介),
    **不覆盖已有的** —— 覆盖等于悄悄丢掉一个来源的说法。两边对同一件事说得不一样时写进 `conflicts`
    (事实对不上)或 `notes`(只是写法不同),让人自己看(规格:有冲突时保留预览并让用户确认,
    不要静默覆盖)。

    排序:有号的按号;没号的排最后(与库里 `load_volumes` 同一个规矩)。
    """
    result = VolumeMerge()

    for draft in drafts:
        found: MergedVolume | None = None
        why = ""
        for row in result.volumes:
            # 与这一行里任意一个来源比:认出来就算同一卷。
            for ref_source, ref_id in row.refs:
                if ref_source != draft.source:
                    continue
                # 同一个来源:先看外部 id,再看号码。
                if ref_id == draft.external_id:
                    found = row
                    why = "外部 id"
                    break
            if found is not None:
                break
            representative = _representative(row, draft)
            if representative is None:
                continue
            same, why = same_volume(representative, draft)
            if same:
                found = row
                break

        if found is None:
            result.volumes.append(_fresh(draft))
            continue

        _absorb(found, draft, why, result)

    result.volumes.sort(
        key=lambda row: (row.number is None, row.number if row.number is not None else 0.0, row.title or "")
    )
    return result


def _representative(row: MergedVolume, draft: VolumeDraft) -> VolumeDraft | None:
    """拿这一行现有的样子,变回一个 `VolumeDraft` 好与新的那条比。"""
    return VolumeDraft(
        source="",
        external_id="",
        number=row.number,
        title=row.title,
        published_on=row.published_on,
        summary=row.summary,
        cover_url=row.cover_url,
    )


def _fresh(draft: VolumeDraft) -> MergedVolume:
    return MergedVolume(
        number=draft.number,
        title=draft.title or None,
        published_on=draft.published_on or None,
        summary=draft.summary or None,
        cover_url=draft.cover_url or None,
        catalog_code=draft.catalog_code or None,
        page_count=draft.page_count,
        volume_type=draft.volume_type or None,
        local_path=draft.local_path or None,
        refs=[(draft.source, draft.external_id)],
        sources=[draft.source],
    )


def _absorb(row: MergedVolume, draft: VolumeDraft, why: str, result: VolumeMerge) -> None:
    """把后来那条并进这一行:**只补空格子,不覆盖**;说法不同时按性质记进冲突或提示。"""
    if (draft.source, draft.external_id) not in row.refs:
        row.refs.append((draft.source, draft.external_id))
        row.refs.sort()
    if draft.source not in row.sources:
        row.sources.append(draft.source)
        row.sources.sort()

    label = row.title or (f"第 {row.number} 卷" if row.number is not None else "无号卷")

    if not row.title and draft.title:
        row.title = draft.title
    elif row.title and draft.title and normalize_title(row.title) != normalize_title(draft.title):
        # **只是写法不同**(多语种卷名、全角半角):记成提示,不当冲突 —— 把它当冲突报,
        # 真正对不上的那几条就淹了。
        result.notes.append(f"{label}:另一个来源写作「{draft.title}」")

    if not row.published_on and draft.published_on:
        row.published_on = draft.published_on
    elif row.published_on and draft.published_on and row.published_on != draft.published_on:
        # **日期对不上是事实矛盾**,要人确认。
        result.conflicts.append(
            f"{label}:日期对不上(留了 {row.published_on},另一个来源写 {draft.published_on})"
        )

    # 封面只补空:**不覆盖已有的** —— 换一张图是人的决定,不该由合并替人做。
    if not row.cover_url and draft.cover_url:
        row.cover_url = draft.cover_url
    if not row.summary and draft.summary:
        row.summary = draft.summary
    if not row.catalog_code and draft.catalog_code:
        row.catalog_code = draft.catalog_code
    elif row.catalog_code and draft.catalog_code and row.catalog_code != draft.catalog_code:
        result.conflicts.append(f"{label}:ISBN/编号对不上")
    if row.page_count is None and draft.page_count is not None:
        row.page_count = draft.page_count
    elif row.page_count is not None and draft.page_count is not None and row.page_count != draft.page_count:
        result.conflicts.append(f"{label}:页数对不上")
    if not row.volume_type and draft.volume_type:
        row.volume_type = draft.volume_type
    if not row.local_path and draft.local_path:
        row.local_path = draft.local_path
