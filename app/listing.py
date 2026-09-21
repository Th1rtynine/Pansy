"""Which rows a list shows, in what order, and on which page.

Two shapes (works, 作品) with two callers each (the HTML page, the JSON API), so *which
rows* is decided here once. No requests, templates or JSON; reads through `queries.py`,
matches through `search.py`.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.fields import MEDIA_TYPE_VALUES, split_by_media_type
from app.models import Edition, Work
from app.queries import (
    load_edition_rows,
    load_edition_search_values,
    load_work_search_values,
    load_work_start_dates,
)
from app.search import build_entry, match, near_match


# 列表能按什么排,以及界面上叫什么;第一档是默认。
# 时间不是作品上的一列:全部那一行按它下面最早的作品,选类型的一行按它自己。
WORK_SORTS = (
    ("title", "按标题"),
    ("date", "按时间"),
)

WORK_SORT_VALUES = tuple(value for value, _label in WORK_SORTS)


# 列表一页放多少行,同时决定什么时候出现翻页链接。
PAGE_SIZE = 10


@dataclass
class WorkRow:
    """One row of the 全部 list: a work, its 作品, and what the keyword hit."""

    work: Work
    published_on: str | None
    editions: list[Edition]
    matched_by: list[str] = field(default_factory=list)


@dataclass
class EditionRow:
    """One row of a list of 作品: a carrier, its work, and what the keyword hit."""

    work: Work
    edition: Edition
    matched_by: list[str] = field(default_factory=list)


@dataclass
class Page:
    """One page of a list: the rows, and where they sit in the whole.
    matched **不是「rows 非空」**,而是搜索有没有结果(先于类型过滤):据此区分「没有这个
    关键词」与「这个类型下没有」。approximate 只找到拼写相近的;sort 是实际用的顺序。
    """

    rows: list
    total: int
    page: int
    pages: int
    matched: bool
    approximate: bool
    sort: str


def select_works(session: Session, keyword: str, sort: str, page: int) -> Page:
    """One row per work, for 全部 (and the API's /works): a work with no 作品 still
    arrives as one row, so nothing drops out."""
    sorting = sort if sort in WORK_SORT_VALUES else WORK_SORT_VALUES[0]
    rows, work_hits, edition_hits, approximate = _narrow(session, keyword)

    # 时间每一档都要读:行里要打印它,而且默认就按它显示。
    start_dates = load_work_start_dates(session)

    by_work: dict[int, tuple[Work, list[Edition]]] = {}
    for work, edition in rows:
        entry = by_work.setdefault(work.id, (work, []))
        if edition is not None:
            entry[1].append(edition)

    ordered: list[WorkRow] = []
    for work, editions in sorted(
        by_work.values(),
        key=lambda item: sort_key(sorting, item[0], None, start_dates.get(item[0].id)),
    ):
        # 作品名命中时全部作品都回来了,名字是作品的;只有部分作品命中时,名字是那些
        # 作品自己的。
        kinds = work_hits.get(work.id) or [
            kind for edition in editions for kind in edition_hits.get(edition.id, [])
        ]
        ordered.append(
            WorkRow(
                work=work,
                published_on=start_dates.get(work.id),
                editions=editions,
                matched_by=list(dict.fromkeys(kinds)),
            )
        )

    window, current, pages = _cut(len(ordered), page)
    return Page(
        rows=ordered[window],
        total=len(ordered),
        page=current,
        pages=pages,
        matched=bool(rows),
        approximate=approximate,
        sort=sorting,
    )


def select_editions(
    session: Session, keyword: str, media_type: str, sort: str, page: int
) -> Page:
    """One row per 作品, for a list narrowed to a type (or unfiltered, for /editions).

    空的 media_type 不限类型;返回一条扁平列表:页面只要一个标题,API 自己分组。
    """
    sorting = sort if sort in WORK_SORT_VALUES else WORK_SORT_VALUES[0]
    chosen = media_type if media_type in MEDIA_TYPE_VALUES else ""
    rows, work_hits, edition_hits, approximate = _narrow(session, keyword)

    members: list[tuple[Work, Edition, list[str]]] = []
    for kind, group in split_by_media_type(
        rows, lambda row: {row[1].media_type} if row[1] is not None else set()
    ):
        if chosen and kind != chosen:
            continue
        for work, edition in group:
            kinds = work_hits.get(work.id) or edition_hits.get(edition.id, [])
            members.append((work, edition, list(dict.fromkeys(kinds))))

    # 这一行是一份作品,按它自己的时间排:2015 年的漫画,它的动画不是 2015 年的。
    members.sort(key=lambda row: sort_key(sorting, row[0], row[1], row[1].published_on))

    window, current, pages = _cut(len(members), page)
    return Page(
        rows=[
            EditionRow(work=work, edition=edition, matched_by=kinds)
            for work, edition, kinds in members[window]
        ],
        total=len(members),
        page=current,
        pages=pages,
        matched=bool(rows),
        approximate=approximate,
        sort=sorting,
    )


def sort_key(
    sorting: str,
    work: Work,
    edition: Edition | None,
    published_on: str | None,
) -> tuple:
    """How one row is ordered, with the title as the tie-breaker throughout.
    日期由调用方传进来,因为两级按的不是同一个:全部那一行按作品下最早的一份,选了类型
    的一行按它自己。没有日期的排在最后,不是最前 ——「不知道」不是「最早」。
    """
    if sorting == "date":
        if published_on:
            return (0, published_on, work.title, edition.id if edition is not None else 0)
        return (1, "", work.title, edition.id if edition is not None else 0)
    return (work.title, edition.id if edition is not None else 0)


def _narrow(session: Session, keyword: str):
    """The rows a keyword leaves, and what it hit on each of the two levels.
    命中作品名带出它的全部作品;只命中某一份作品(作者、标签)就只带出那一份。拼写兜底只
    在两级都没有精确命中时问一次 —— 分级去问会让作品名上的近似命中盖掉作者上的精确命中。
    """
    if not keyword:
        # None, not []: no narrowing at all. [] would mean 「narrow to nothing」.
        return load_edition_rows(session, None, None), {}, {}, False

    work_entries = [
        build_entry(row_id, values) for row_id, values in load_work_search_values(session)
    ]
    edition_entries = [
        build_entry(row_id, values) for row_id, values in load_edition_search_values(session)
    ]
    work_hits = match(work_entries, keyword)
    edition_hits = match(edition_entries, keyword)
    approximate = False
    if not work_hits and not edition_hits:
        work_hits = near_match(work_entries, keyword)
        edition_hits = near_match(edition_entries, keyword)
        approximate = bool(work_hits or edition_hits)

    # [] 是「缩到空」,None 是「不缩」:没找到东西必须传 [],否则整个库都会回来,
    # 而页面写着 未找到。
    rows = load_edition_rows(session, list(edition_hits), list(work_hits))
    return rows, work_hits, edition_hits, approximate


def _cut(total: int, page: int) -> tuple[slice, int, int]:
    """Where one page starts and ends, pulled back when the number is past the end.
    页码超过末尾就落到最后一页,不回空页:旧书签不该因为库变小就读到 暂无作品。不是
    正数的都算第一页。
    """
    pages = max(1, -(-total // PAGE_SIZE))
    current = min(max(page, 1), pages)
    return slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE), current, pages
