"""The JSON side of 标签: the list, one tag, and renaming.

和 作者 一样,没有接口新建标签也没有接口删标签:标签是在 作品 上写名字时产生的,类型也只能来自那一部作品;
而删除会带走它的引用(标签是共用词表)。同一类型内改成该类型已有的名字是合并,规则在 `app/rules.py`。
"""

from fastapi import APIRouter, HTTPException

from app.api.schemas import TagDetailOut, TagIn, TagOut, edition_ref
from app.db import session_scope
from app.fields import media_label
from app.queries import (
    get_tag_or_404,
    load_tag_carriers,
    load_tags_with_usage,
)
from app.rules import rename_tag

router = APIRouter(prefix="/api", tags=["标签"])


@router.get("/tags", response_model=list[TagOut])
def list_tags(media_type: str = "") -> list[TagOut]:
    """Every tag with how many 作品 carry it, optionally only one media type."""
    with session_scope() as session:
        rows = load_tags_with_usage(session)
        answer = [
            TagOut(
                id=tag.id,
                name=tag.name,
                media_type=tag.media_type,
                media_label=media_label(tag.media_type),
                edition_count=edition_count,
            )
            for tag, edition_count in rows
            if not media_type or tag.media_type == media_type
        ]

    return answer


@router.get("/tags/{tag_id}", response_model=TagDetailOut)
def show_tag(tag_id: int) -> TagDetailOut:
    """One tag and every 作品 carrying it."""
    with session_scope() as session:
        tag = get_tag_or_404(session, tag_id)
        rows = load_tag_carriers(session, tag_id)

        answer = TagDetailOut(
            id=tag.id,
            name=tag.name,
            media_type=tag.media_type,
            media_label=media_label(tag.media_type),
            edition_count=len(rows),
            editions=[edition_ref(edition, work) for work, edition in rows],
        )

    return answer


@router.put("/tags/{tag_id}", response_model=TagOut)
def update_tag(tag_id: int, body: TagIn) -> TagOut:
    """Rename one tag. The media type is not in the body and cannot be changed:
    它不是标签上的一个字样,而是决定哪些 作品 能挂它 —— 改了就会留下挂在错类型 作品 上的标签。
    """
    with session_scope() as session:
        tag = get_tag_or_404(session, tag_id)
        refusal = rename_tag(session, tag, body.name)
        if refusal:
            raise HTTPException(status_code=400, detail=refusal)

        answer = TagOut(
            id=tag.id,
            name=tag.name,
            media_type=tag.media_type,
            media_label=media_label(tag.media_type),
            edition_count=len(load_tag_carriers(session, tag_id)),
        )

    return answer
