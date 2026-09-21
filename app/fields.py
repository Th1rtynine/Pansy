"""Reading and formatting the plain values the forms and pages exchange.

Pure functions only: no session, no request, no template, so a route module can call them without setup.
"""

import json
import re
from datetime import date


# The media types in the order they are shown in: original work outwards, not alphabetical, and one tuple for both the order and the values a form is checked against.
MEDIA_TYPE_LABELS = {
    "manga": "漫画",
    "light_novel": "轻小说",
    # 内容以 galgame 为主,叫 Gal 比「游戏」精确、比「Galgame」短。
    "game": "Gal",
    "anime": "动画",
}
MEDIA_TYPE_VALUES = tuple(MEDIA_TYPE_LABELS)


# 每种类型实际记的东西。列是共用的(published_on / org / release_status / volume_count 与卷表
# 装各自的对等物),但东西本身不同:游戏没有卷、动画的行是季、漫画的出版社不是 发行商。
MEDIA_TYPE_FIELDS = {
    "manga": {
        "time": "连载开始",
        "org": "出版社",
        "status": "连载状态",
        "status_hint": "连载中 / 已完结 / 休载",
        "count": "应有卷数",
        "unit": "卷",
        "unit_hint": "一行一卷,可留空。支持「1-30」「3 卷名」",
        "number": "卷号",
        "name": "卷名",
    },
    "light_novel": {
        "time": "刊行开始",
        "org": "出版社",
        "status": "连载状态",
        "status_hint": "连载中 / 已完结 / 休载",
        "count": "应有卷数",
        "unit": "卷",
        "unit_hint": "一行一卷,可留空。支持「1-30」「3 卷名」",
        "number": "卷号",
        "name": "卷名",
    },
    "game": {
        "time": "发售时间",
        "org": "发行商",
        "status": "发售状态",
        "status_hint": "已发售 / 未发售",
        "count": "",
        "unit": "",
        "unit_hint": "",
        "number": "",
        "name": "",
    },
    "anime": {
        "time": "放送开始",
        "org": "制作公司",
        "status": "放送状态",
        "status_hint": "放送中 / 已完结 / 未放送",
        "count": "应有季数",
        "unit": "季度",
        "unit_hint": "一行一季,可留空。例如「1 第1期」「2」",
        "number": "期号",
        "name": "标题",
    },
}

EMPTY_MEDIA_FIELDS = {
    "time": "",
    "org": "",
    "status": "",
    "status_hint": "",
    "count": "",
    "unit": "",
    "unit_hint": "",
    "number": "",
    "name": "",
}


def media_fields(media_type: str) -> dict[str, str]:
    """What one media type records; an unknown one records none of it.
    Templates ask this directly, which keeps the display page and the edit form saying the same words.
    """
    return MEDIA_TYPE_FIELDS.get(media_type, EMPTY_MEDIA_FIELDS)


def media_unit(media_type: str) -> str:
    """What one row of a carrier's internal list is called; empty when it has none.
    An empty answer means the list does not belong to that carrier at all: a game has no volumes.
    """
    return media_fields(media_type)["unit"]


def parse_aliases(raw: str) -> list[str]:
    """Read the alias list kept in a text column; anything unparsable is empty."""
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def aliases_to_text(raw: str) -> str:
    """Turn the stored list back into the one-per-line form the textarea wants."""
    return "\n".join(parse_aliases(raw))


def split_lines(raw: str) -> list[str]:
    """One value per line; blank lines are dropped. Used for aliases and tags."""
    return [line.strip() for line in raw.splitlines() if line.strip()]


def format_volume_number(number: float | None) -> str:
    """A whole number shows without a decimal point; an empty number shows a dash."""
    if number is None:
        return "—"
    if number == int(number):
        return str(int(number))
    return str(number)


def media_label(media_type: str) -> str:
    return MEDIA_TYPE_LABELS.get(media_type, media_type)


def media_group_label(media_type: str | None) -> str:
    """The heading over a group of rows. Rows with no carrier get their own."""
    return MEDIA_TYPE_LABELS.get(media_type, "尚未建立作品")


def volume_words(media_type: str) -> dict[str, str]:
    """What this type calls its internal unit and the columns of one row of it.

    For refusals, which name the column the reader was looking at instead of calling a season a volume; a game records none of it, so the words fall back.
    """
    fields = media_fields(media_type)
    return {
        "unit": fields["unit"] or "条",
        "count": fields["count"] or "数量",
        "number": fields["number"] or "序号",
        "name": fields["name"] or "名字",
    }


DATE_PATTERN = re.compile(r"^(\d{4})(?:[-/.年](\d{1,2})(?:[-/.月](\d{1,2})日?)?)?$")


def read_published_on(raw: str, label: str) -> tuple[str | None, str | None]:
    """Read a date written as far as it is known; return (value, error).

    Shapes 2015 / 2015-04 / 2015-04-01, separator -, / or .; a month nobody recorded stays missing rather than becoming 01, so the values still sort as text. The label is the medium's own word, so a refusal names the box the reader was looking at.
    """
    text = raw.strip()
    if not text:
        return None, None

    shape = f"{label}须写作 2015、2015-04 或 2015-04-01;留空表示未知。"
    found = DATE_PATTERN.fullmatch(text)
    if found is None:
        return None, shape

    year, month, day = found.group(1), found.group(2), found.group(3)
    if month is None:
        return year, None
    if day is None:
        if not 1 <= int(month) <= 12:
            return None, shape
        return f"{year}-{int(month):02d}", None

    try:
        date(int(year), int(month), int(day))
    except ValueError:
        # The regex lets 2015-02-30 through; a day that does not exist is a typo.
        return None, shape
    return f"{year}-{int(month):02d}-{int(day):02d}", None


def read_volume_count(raw: str, media_type: str) -> tuple[int | None, str | None]:
    """Return (value, error); an empty field means no value and no error."""
    text = raw.strip()
    if not text:
        return None, None
    if not text.isdigit():
        return None, f"{volume_words(media_type)['count']}须为整数,或留空。"
    return int(text), None


def read_volume_number(raw: str, media_type: str) -> tuple[float | None, str | None]:
    """Return (value, error); an empty field means an unnumbered volume."""
    text = raw.strip()
    if not text:
        return None, None
    words = volume_words(media_type)
    try:
        return float(text), None
    except ValueError:
        return (
            None,
            f"{words['number']}须为数字,例如 3 或 4.5;留空表示该{words['unit']}无序号。",
        )


MAX_BATCH_VOLUMES = 200


RANGE_PATTERN = re.compile(r"(\d+)\s*-\s*(\d+)")


def parse_volume_lines(
    raw: str, media_type: str
) -> tuple[list[tuple[float | None, str | None]], list[str]]:
    """Read one volume per line; return (entries, errors).

    A line may be "1-30", "3 卷名", "3", or "- 卷名". The type is taken so refusals name the column this type actually has: a season's number is 期号, not 卷号.
    """
    words = volume_words(media_type)
    entries: list[tuple[float | None, str | None]] = []
    errors: list[str] = []

    for position, line in enumerate(raw.splitlines(), start=1):
        text = line.strip()
        if not text:
            continue

        unnumbered = re.fullmatch(r"-\s*(.*)", text)
        if unnumbered:
            entries.append((None, unnumbered.group(1).strip() or None))
            continue

        span = RANGE_PATTERN.fullmatch(text)
        if span:
            start, end = int(span.group(1)), int(span.group(2))
            if end < start:
                errors.append(f"第 {position} 行:{start}-{end} 的终点小于起点。")
            elif end - start + 1 > MAX_BATCH_VOLUMES:
                errors.append(
                    f"第 {position} 行:单次最多 {MAX_BATCH_VOLUMES} {words['unit']}。"
                )
            else:
                entries.extend((float(number), None) for number in range(start, end + 1))
            continue

        head, _, tail = text.partition(" ")
        try:
            number = float(head)
        except ValueError:
            errors.append(
                f"第 {position} 行:行首须为{words['number']},或写作 1-30 形式的范围。"
            )
            continue
        entries.append((number, tail.strip() or None))

    return entries, errors


def parse_creator_lines(raw: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Read one creator per line as "名字 角色"; return (pairs, errors).

    The last run of spaces separates the two, so "Gege Akutami 作画" keeps the name.
    """
    pairs: list[tuple[str, str]] = []
    errors: list[str] = []

    for position, line in enumerate(raw.splitlines(), start=1):
        text = line.strip()
        if not text:
            continue

        name, separator, role = text.rpartition(" ")
        if not separator or not name.strip() or not role.strip():
            errors.append(f"第 {position} 行:格式须为「名字 角色」。")
            continue

        pairs.append((name.strip(), role.strip()))

    return pairs, errors


def creators_to_text(pairs: list[tuple[str, str]]) -> str:
    """Turn stored pairs back into the one-per-line form the textarea wants."""
    return "\n".join(f"{name} {role}" for name, role in pairs)


def split_by_media_type(rows: list, types_of) -> list[tuple[str | None, list]]:
    """Group rows by media type, in MEDIA_TYPE_VALUES order, untyped ones last.

    types_of returns the media types one row belongs to; the untyped case collects under the None key, which the templates draw as 「尚未建立作品」.
    """
    buckets: dict[str | None, list] = {}
    for row in rows:
        kinds = [kind for kind in MEDIA_TYPE_VALUES if kind in types_of(row)] or [None]
        for kind in kinds:
            buckets.setdefault(kind, []).append(row)

    order: list[str | None] = [kind for kind in MEDIA_TYPE_VALUES if kind in buckets]
    if None in buckets:
        order.append(None)
    return [(kind, buckets[kind]) for kind in order]
