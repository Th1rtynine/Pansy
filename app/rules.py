"""The rules a write has to pass, whichever door it came in through.

Two doors: the HTML forms and the JSON API under /api; a rule both doors need lives here, so it
cannot exist in one door only. **The sentences are part of the rule**: each returns a refusal
sentence or None (「this may be written」) instead of raising, and both doors use the same words.
"""

import json

from sqlalchemy.orm import Session

from app.fields import format_volume_number, media_unit, parse_aliases
from app.models import Creator, Edition, Tag
from app.queries import (
    find_creator_by_name,
    find_edition_relation,
    find_tag_by_name,
    find_volume_by_number,
    merge_creator,
    merge_tag,
)


def blank(value: str | None, label: str) -> str | None:
    """Refuse a required name that is empty; None when there is something there. The label is the
    form's own wording for the field (作品总标题 / 作者名 / 标签名), so the refusal names the box the
    reader was looking at.
    """
    if not (value or "").strip():
        return f"{label}不能为空。"
    return None


def link_editions(session: Session, edition: Edition, other_id: int) -> str | None:
    """Whether this 作品 may be linked to that one; None when it may. Four refusals, the first
    three of which would otherwise be a certain error: a row that is gone, a link to itself, two
    作品 of the same work (already connected by belonging to it), and a pair that already has a
    row. The same-work case is the one the table cannot express: it only sees two ids."""
    other = session.get(Edition, other_id)
    if other is None:
        return "所选作品已不存在。"
    if other.id == edition.id:
        return "作品不能与自身建立关联。"
    if other.work_id == edition.work_id:
        return "同一个作品总标题下的作品不需要关联,它们本来就属于同一部作品。"
    if find_edition_relation(session, edition.id, other.id) is not None:
        return "这两个作品已建立关联。"
    return None


def volume_number_taken(
    session: Session, edition: Edition, number: float | None, *, exclude_id: int = 0
) -> str | None:
    """Whether this 作品 already has that number; None when it is free. A volume with no number can
    never clash: that is how SS or 上/下 is recorded, and several coexist. The batch form does not
    use this -- it skips what is there and says how many, which is what a reader pasting thirty
    lines wants; writing one volume by hand is where being told beats being quietly skipped."""
    if number is None:
        return None
    if find_volume_by_number(session, edition.id, number, exclude_id=exclude_id) is None:
        return None
    unit = media_unit(edition.media_type)
    return f"这个作品下已经有第 {format_volume_number(number)} {unit}了。"


def rename_creator(session: Session, creator: Creator, name: str, aliases: list[str]) -> str | None:
    """Write a creator's new name and alias list; None when it was written. **Renaming onto a name
    the library already answers to is a merge, not a clash**: the two rows are one person, so the
    references move and the dropped name becomes an alias of the kept one. The clash is looked up
    and the merge flushed *before* the new name is written, or the UPDATE beats the DELETE (a 500)."""
    refusal = blank(name, "作者名")
    if refusal:
        return refusal
    cleaned = name.strip()

    clash = find_creator_by_name(session, cleaned, exclude_id=creator.id)
    creator.aliases = json.dumps(aliases, ensure_ascii=False)
    if clash is not None:
        merge_creator(session, creator, clash)
        session.flush()

    creator.name = cleaned
    # A name is not its own alias: the merge appends the dropped row's name, which is often the
    # name just taken, so it is dropped again rather than listed as a second spelling of itself.
    creator.aliases = json.dumps(
        [alias for alias in parse_aliases(creator.aliases) if alias != cleaned],
        ensure_ascii=False,
    )
    return None


def rename_tag(session: Session, tag: Tag, name: str) -> str | None:
    """Write a tag's new name; None when it was written. Same merge-on-rename as a creator, inside
    one media type: a name already taken *in that type* is the same word and the two rows fold into
    one, while the same word in another type stays separate. The type itself is never editable --
    it decides which 作品 may carry the tag. The ordering is the creator's -- see rename_creator."""
    refusal = blank(name, "标签名")
    if refusal:
        return refusal
    cleaned = name.strip()

    clash = find_tag_by_name(session, cleaned, tag.media_type, exclude_id=tag.id)
    if clash is not None:
        merge_tag(session, tag, clash)
        session.flush()

    tag.name = cleaned
    return None
