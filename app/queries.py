"""Every read and write that goes through a database session.

Routes call these instead of writing queries of their own: routes -> queries -> models.
"""

import json

from fastapi import HTTPException
from sqlalchemy import delete, distinct, func, or_, select
from sqlalchemy.orm import Session

from app.fields import media_fields, parse_aliases
from app.models import (
    Creator,
    Edition,
    EditionCreator,
    EditionRelation,
    EditionTag,
    Tag,
    Volume,
    Work,
)


def get_work_or_404(session: Session, work_id: int) -> Work:
    work = session.get(Work, work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="作品总标题不存在")
    return work


def get_edition_or_404(session: Session, edition_id: int) -> Edition:
    edition = session.get(Edition, edition_id)
    if edition is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    return edition


def get_volume_or_404(session: Session, volume_id: int) -> Volume:
    volume = session.get(Volume, volume_id)
    if volume is None:
        raise HTTPException(status_code=404, detail="卷不存在")
    return volume


def get_creator_or_404(session: Session, creator_id: int) -> Creator:
    creator = session.get(Creator, creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="作者不存在")
    return creator


def find_creator_by_name(session: Session, name: str, *, exclude_id: int | None = None) -> Creator | None:
    """Look up a creator by name, aliases included: one person is one row. The name goes to
    the indexed column first; aliases are a JSON list inside a text column, so they are
    compared in Python -- a pen name already recorded must not start a second row.
    """
    statement = select(Creator).where(Creator.name == name)
    if exclude_id is not None:
        statement = statement.where(Creator.id != exclude_id)
    found = session.execute(statement).scalars().first()
    if found is not None:
        return found

    for creator in session.execute(select(Creator).order_by(Creator.id)).scalars():
        if creator.id == exclude_id:
            continue
        if name in parse_aliases(creator.aliases):
            return creator
    return None


def merge_creator(session: Session, keep: Creator, drop: Creator) -> None:
    """Fold one creator into another and remove the spare row. Two rows reached by the same
    name are the same person, so links move instead of the rename being refused; a link the
    kept row already holds on the (edition, role) key is dropped, not written twice.
    """
    taken = {
        (link.edition_id, link.role)
        for link in session.execute(
            select(EditionCreator).where(EditionCreator.creator_id == keep.id)
        ).scalars()
    }
    for link in session.execute(
        select(EditionCreator).where(EditionCreator.creator_id == drop.id)
    ).scalars():
        if (link.edition_id, link.role) in taken:
            session.delete(link)
            continue
        link.creator_id = keep.id
        taken.add((link.edition_id, link.role))

    merged = parse_aliases(keep.aliases) + parse_aliases(drop.aliases) + [drop.name]
    keep.aliases = json.dumps(list(dict.fromkeys(merged)), ensure_ascii=False)
    session.delete(drop)


def merge_tag(session: Session, keep: Tag, drop: Tag) -> None:
    """Fold one tag into another inside the same media type and remove the spare. A carrier with both
    spellings is carrying one tag, so that link is dropped, not written twice."""
    taken = {
        link.edition_id
        for link in session.execute(
            select(EditionTag).where(EditionTag.tag_id == keep.id)
        ).scalars()
    }
    for link in session.execute(
        select(EditionTag).where(EditionTag.tag_id == drop.id)
    ).scalars():
        if link.edition_id in taken:
            session.delete(link)
            continue
        link.tag_id = keep.id
        taken.add(link.edition_id)

    session.delete(drop)


def get_tag_or_404(session: Session, tag_id: int) -> Tag:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    return tag


def find_tag_by_name(
    session: Session,
    name: str,
    media_type: str,
    *,
    exclude_id: int | None = None,
) -> Tag | None:
    """Look up a tag by name inside one media type, ignoring one row when renaming. The media
    type is part of the unique key: 战斗 on a manga and 战斗 on an anime are two tags, and a
    carrier must find the tag belonging to its own type.
    """
    statement = select(Tag).where(Tag.name == name, Tag.media_type == media_type)
    if exclude_id is not None:
        statement = statement.where(Tag.id != exclude_id)
    return session.execute(statement).scalars().first()


def load_creator_pairs(session: Session, edition_id: int) -> list[tuple[str, str]]:
    """Read one carrier's creators as (name, role), in a stable order."""
    rows = session.execute(
        select(Creator.name, EditionCreator.role)
        .join(EditionCreator, EditionCreator.creator_id == Creator.id)
        .where(EditionCreator.edition_id == edition_id)
        .order_by(Creator.name, EditionCreator.role)
    ).all()
    return [(name, role) for name, role in rows]


def load_tag_names(session: Session, edition_id: int) -> list[str]:
    """Read one carrier's tags by name, in a stable order."""
    rows = session.execute(
        select(Tag.name)
        .join(EditionTag, EditionTag.tag_id == Tag.id)
        .where(EditionTag.edition_id == edition_id)
        .order_by(Tag.name)
    ).all()
    return [row[0] for row in rows]


def load_work_search_values(session: Session) -> list[tuple[int, list[tuple[str, str]]]]:
    """One pair per work: its id, and the names belonging to the work itself, not its
    carriers' content -- a keyword on a work's own name brings out all of its carriers, while
    one only a single carrier has brings out that carrier alone. Each name carries the field
    it is, so the page says 「命中 原名」 or 「命中 别名」; aliases go over as stored text."""
    values: dict[int, list[tuple[str, str]]] = {}
    for work_id, title, original_title, aliases in session.execute(
        select(Work.id, Work.title, Work.original_title, Work.aliases)
    ):
        row = values.setdefault(work_id, [])
        for kind, text in (
            ("作品总标题", title),
            ("原名", original_title),
            ("别名", aliases),
        ):
            if text:
                row.append((kind, text))

    return sorted(values.items())


def load_edition_search_values(session: Session) -> list[tuple[int, list[tuple[str, str]]]]:
    """One pair per carrier: its id, and the text belonging to it alone -- title, org (in the
    word its media type uses), creators' names and aliases, tags, volume names, each labelled
    with the field's own word. A volume matches by name only, never by number, or a bare 「4」
    brings out every carrier with a fourth volume. Aliases are searched too, not just resolved."""
    values: dict[int, list[tuple[str, str]]] = {}

    def add(edition_id: int, kind: str, text: str | None) -> None:
        if text:
            values.setdefault(edition_id, []).append((kind, text))

    for edition_id, media_type, title, org in session.execute(
        select(Edition.id, Edition.media_type, Edition.title, Edition.org)
    ):
        add(edition_id, "作品标题", title)
        add(edition_id, media_fields(media_type)["org"], org)

    for edition_id, name, aliases in session.execute(
        select(EditionCreator.edition_id, Creator.name, Creator.aliases).join(
            Creator, Creator.id == EditionCreator.creator_id
        )
    ):
        add(edition_id, "作者", name)
        add(edition_id, "作者", aliases)

    for edition_id, name in session.execute(
        select(EditionTag.edition_id, Tag.name).join(Tag, Tag.id == EditionTag.tag_id)
    ):
        add(edition_id, "标签", name)

    for edition_id, title in session.execute(select(Volume.edition_id, Volume.title)):
        add(edition_id, "卷名", title)

    return sorted(values.items())


def load_edition_rows(
    session: Session,
    edition_ids: list[int] | None,
    work_ids: list[int] | None = None,
) -> list[tuple[Work, Edition | None]]:
    """The carriers to show, each paired with its work. edition_ids are carriers whose own
    content matched, and only those come back; work_ids are works whose own name matched, and
    every carrier of those comes back; both None means no narrowing. A work with no carrier
    comes back once with an empty one; pinyin and typos are the caller's (app/search.py)."""
    statement = (
        select(Work, Edition)
        .outerjoin(Edition, Edition.work_id == Work.id)
        .order_by(Work.id, Edition.id)
    )

    if edition_ids is not None or work_ids is not None:
        wanted = [Edition.id.in_(edition_ids or [])]
        if work_ids:
            wanted.append(Work.id.in_(work_ids))
        statement = statement.where(or_(*wanted))

    return session.execute(statement).all()


def load_work_start_dates(session: Session, work_ids: list[int] | None = None) -> dict[int, str]:
    """Each work's 原作时间: the earliest date among its carriers, MIN over the text as
    published_on is written. A work whose carriers all have no date is absent, and the caller
    reads a missing key as 「不知道」, so those rows sort last by date. Read library-wide,
    since the date belongs to the work, not to the carrier a search brought out."""
    statement = select(Edition.work_id, func.min(Edition.published_on)).where(
        Edition.published_on.is_not(None)
    )
    if work_ids is not None:
        statement = statement.where(Edition.work_id.in_(work_ids))
    return {
        work_id: earliest
        for work_id, earliest in session.execute(statement.group_by(Edition.work_id))
    }


def load_editions(session: Session, work_id: int) -> list[Edition]:
    """Every carrier of one work, oldest first."""
    return list(
        session.execute(
            select(Edition).where(Edition.work_id == work_id).order_by(Edition.id)
        ).scalars().all()
    )


def load_volumes(session: Session, edition_ids: list[int]) -> list[Volume]:
    """The volumes of several carriers at once, unnumbered ones last."""
    if not edition_ids:
        return []
    return list(
        session.execute(
            select(Volume)
            .where(Volume.edition_id.in_(edition_ids))
            .order_by(Volume.edition_id, Volume.volume_number.is_(None), Volume.volume_number)
        ).scalars().all()
    )


def load_carrier_creators(session: Session, edition_ids: list[int]) -> list[tuple[int, str, int, str]]:
    """Creators of several carriers at once: (edition_id, role, creator_id, name).

    Batched, so the page's query count does not grow with the number of carriers.
    """
    if not edition_ids:
        return []
    return session.execute(
        select(EditionCreator.edition_id, EditionCreator.role, Creator.id, Creator.name)
        .join(Creator, Creator.id == EditionCreator.creator_id)
        .where(EditionCreator.edition_id.in_(edition_ids))
        .order_by(EditionCreator.edition_id, EditionCreator.role, Creator.name)
    ).all()


def load_carrier_tags(session: Session, edition_ids: list[int]) -> list[tuple[int, int, str]]:
    """Tags of several carriers at once: (edition_id, tag_id, name)."""
    if not edition_ids:
        return []
    return session.execute(
        select(EditionTag.edition_id, Tag.id, Tag.name)
        .join(Tag, Tag.id == EditionTag.tag_id)
        .where(EditionTag.edition_id.in_(edition_ids))
        .order_by(EditionTag.edition_id, Tag.name)
    ).all()


def load_creators_with_usage(session: Session) -> list[tuple[Creator, int]]:
    """Every creator with the number of 作品 it appears on, by name. Counted over distinct
    carriers, not link rows: several roles on one carrier are still one 作品. The number of
    作品总标题 a person reaches is a different, larger count, printed on the person's own page.
    """
    return session.execute(
        select(Creator, func.count(distinct(Edition.id)))
        .outerjoin(EditionCreator, EditionCreator.creator_id == Creator.id)
        .outerjoin(Edition, Edition.id == EditionCreator.edition_id)
        .group_by(Creator.id)
        .order_by(Creator.name)
    ).all()


def load_creator_work_counts(session: Session) -> dict[int, int]:
    """How many 作品总标题 each creator reaches, over distinct works. One person credited on
    two forms of the same work is one 作品总标题 and two 作品, which is why the person's page
    prints both numbers.
    """
    return dict(
        session.execute(
            select(EditionCreator.creator_id, func.count(distinct(Edition.work_id)))
            .join(Edition, Edition.id == EditionCreator.edition_id)
            .group_by(EditionCreator.creator_id)
        ).all()
    )


def load_tags_with_usage(session: Session) -> list[tuple[Tag, int]]:
    """Every tag with the number of 作品 it is used on, grouped by media type. Ordered by media
    type, so the tag library page can lay the four sets out itself. Counted over distinct
    carriers, like the creator library: a tag belongs to one media type, so its 作品 are too.
    """
    return session.execute(
        select(Tag, func.count(distinct(Edition.id)))
        .outerjoin(EditionTag, EditionTag.tag_id == Tag.id)
        .outerjoin(Edition, Edition.id == EditionTag.edition_id)
        .group_by(Tag.id)
        .order_by(Tag.media_type, Tag.name)
    ).all()


def load_creator_carriers(session: Session, creator_id: int) -> list[tuple[Work, Edition, str]]:
    """Every carrier this creator worked on, with its work and the role held."""
    return session.execute(
        select(Work, Edition, EditionCreator.role)
        .join(Edition, Edition.work_id == Work.id)
        .join(EditionCreator, EditionCreator.edition_id == Edition.id)
        .where(EditionCreator.creator_id == creator_id)
        .order_by(Work.id, Edition.id, EditionCreator.role)
    ).all()


def load_tag_carriers(session: Session, tag_id: int) -> list[tuple[Work, Edition]]:
    """Every carrier carrying this tag, with the work it belongs to."""
    return session.execute(
        select(Work, Edition)
        .join(Edition, Edition.work_id == Work.id)
        .join(EditionTag, EditionTag.edition_id == Edition.id)
        .where(EditionTag.tag_id == tag_id)
        .order_by(Work.id, Edition.id)
    ).all()


def find_volume_by_number(
    session: Session, edition_id: int, number: float, *, exclude_id: int
) -> Volume | None:
    """Look for a carrier's volume with this number, ignoring one row."""
    return session.execute(
        select(Volume).where(
            Volume.edition_id == edition_id,
            Volume.volume_number == number,
            Volume.id != exclude_id,
        )
    ).scalars().first()


def replace_creators(session: Session, edition: Edition, pairs: list[tuple[str, str]]) -> None:
    """Make a carrier's creators match the given (name, role) pairs exactly: the existing links
    are dropped and written again, and a name not yet in the library is created here -- which
    is what lets the field be typed straight in.
    """
    session.execute(delete(EditionCreator).where(EditionCreator.edition_id == edition.id))

    # 判重按**认出来的那一行**算,不按打进来的字:同一个人的两种写法(别名)是同一行,
    # 同一 (件, 人, 职位) 写两次会撞唯一键,整次保存变成 500。
    written: set[tuple[int, str]] = set()
    for name, role in pairs:
        creator = find_creator_by_name(session, name)
        if creator is None:
            creator = Creator(name=name, aliases="[]")
            session.add(creator)
            session.flush()

        if (creator.id, role) in written:
            continue
        written.add((creator.id, role))

        session.add(EditionCreator(edition_id=edition.id, creator_id=creator.id, role=role))


def replace_tags(session: Session, edition: Edition, names: list[str]) -> None:
    """Make a carrier's tags match the given names exactly. A name not yet in the library is
    created under this carrier's media type -- typing 视觉小说 on an anime makes an anime tag --
    and looked up inside that type, so the same word on another type is a separate row.
    """
    session.execute(delete(EditionTag).where(EditionTag.edition_id == edition.id))

    written: set[int] = set()
    for name in dict.fromkeys(names):
        tag = find_tag_by_name(session, name, edition.media_type)
        if tag is None:
            tag = Tag(name=name, media_type=edition.media_type)
            session.add(tag)
            session.flush()

        if tag.id in written:
            continue
        written.add(tag.id)

        session.add(EditionTag(edition_id=edition.id, tag_id=tag.id))


def add_volumes(
    session: Session, edition_id: int, entries: list[tuple[float | None, str | None, str | None]]
) -> tuple[int, int]:
    """Add volumes to one carrier, skipping numbers it already has; returns (added, skipped).
    An unnumbered volume is never a duplicate -- that is how SS or 上/下 is recorded, and several
    coexist. Each entry is (number, title, published_on), the date coming from the source.
    """
    taken = set(
        session.execute(select(Volume.volume_number).where(Volume.edition_id == edition_id)).scalars()
    )
    added = skipped = 0
    for number, title, published_on in entries:
        if number is not None and number in taken:
            skipped += 1
            continue
        session.add(
            Volume(
                edition_id=edition_id,
                volume_number=number,
                title=title,
                published_on=published_on,
            )
        )
        if number is not None:
            taken.add(number)
        added += 1
    return added, skipped


def load_linked_editions(session: Session, edition_ids: list[int]) -> list[tuple[Edition, Work]]:
    """The carriers linked to any of these, each with the work it belongs to. The link row is
    unordered, so both columns are read: a carrier sits on the left of some rows and the right
    of others. A row with both ends in view drops out, which also keeps a pair from printing twice.
    """
    if not edition_ids:
        return []

    wanted = set(edition_ids)
    rows = session.execute(
        select(EditionRelation).where(
            or_(
                EditionRelation.edition_a_id.in_(edition_ids),
                EditionRelation.edition_b_id.in_(edition_ids),
            )
        )
    ).scalars()

    other_ids = {
        other_id
        for relation in rows
        for other_id in (relation.edition_a_id, relation.edition_b_id)
        if other_id not in wanted
    }
    if not other_ids:
        return []

    return list(
        session.execute(
            select(Edition, Work)
            .join(Work, Work.id == Edition.work_id)
            .where(Edition.id.in_(other_ids))
            .order_by(Work.title, Edition.id)
        ).all()
    )


def load_linked_works(session: Session, edition_ids: list[int]) -> list[tuple[Work, int]]:
    """The works linked to any of these carriers, each with how many forms link. The same links
    read one level up, so several forms of one work point at one entry instead of repeating
    it; the count is kept so the page can say it was linked through two of them.
    """
    counted: dict[int, tuple[Work, int]] = {}
    for _edition, work in load_linked_editions(session, edition_ids):
        seen = counted.get(work.id)
        counted[work.id] = (work, seen[1] + 1) if seen else (work, 1)
    return sorted(counted.values(), key=lambda entry: entry[0].title)


def load_relation_candidates(session: Session, edition: Edition) -> list[tuple[Edition, Work]]:
    """The carriers this one could still be linked to, with their works. Three are left out,
    each of which would otherwise be a certain error: the carrier itself, which the table
    refuses; its own work's carriers, already connected by belonging to it; and the linked ones.
    """
    linked = {
        other_id
        for relation in session.execute(
            select(EditionRelation).where(
                or_(
                    EditionRelation.edition_a_id == edition.id,
                    EditionRelation.edition_b_id == edition.id,
                )
            )
        ).scalars()
        for other_id in (relation.edition_a_id, relation.edition_b_id)
        if other_id != edition.id
    }

    return session.execute(
        select(Edition, Work)
        .join(Work, Work.id == Edition.work_id)
        .where(
            Edition.id.not_in(linked),
            Edition.id != edition.id,
            Edition.work_id != edition.work_id,
        )
        .order_by(Work.title, Edition.id)
    ).all()


def find_edition_relation(session: Session, left: int, right: int) -> EditionRelation | None:
    """The row linking two carriers, whichever order they were given in."""
    low, high = sorted((left, right))
    return session.get(EditionRelation, {"edition_a_id": low, "edition_b_id": high})


def add_edition_relation(session: Session, left: int, right: int) -> EditionRelation:
    """Link two carriers. Sorted first: the table only accepts the smaller id first."""
    low, high = sorted((left, right))
    relation = EditionRelation(edition_a_id=low, edition_b_id=high)
    session.add(relation)
    return relation


def delete_edition_relation(session: Session, left: int, right: int) -> bool:
    """Drop one link, whichever order the two carriers were given in. Only the link goes: both carriers
    stay, with all of their volumes and their other links."""
    low, high = sorted((left, right))
    result = session.execute(
        delete(EditionRelation).where(
            EditionRelation.edition_a_id == low,
            EditionRelation.edition_b_id == high,
        )
    )
    return result.rowcount > 0
