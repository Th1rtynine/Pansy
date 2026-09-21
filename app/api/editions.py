"""The JSON side of 作品: list, read, add, change, remove, and link. The write path is the one the page walks,
rule for rule: the same date reader, creators and tags handed over whole, the same refusal sentence for a volume
number already in use, and the four link refusals from `app/rules.py`; only the travel differs (a 400 body instead
of a paragraph). The type is not editable (see update_edition); 作品总标题's three fields go through `/api/works/{id}`.
"""

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app import covers
from app.api.schemas import (
    EditionIn,
    EditionListOut,
    EditionOut,
    EditionRef,
    EditionRowOut,
    RelationIn,
    RelationOut,
    clean_names,
    edition_out,
    edition_ref,
)
from app.db import session_scope
from app.fields import (
    MEDIA_TYPE_VALUES,
    media_fields,
    read_published_on,
)
from app.listing import PAGE_SIZE, select_editions
from app.models import Edition, Work
from app.queries import (
    add_edition_relation,
    delete_edition_relation,
    get_edition_or_404,
    get_work_or_404,
    load_carrier_creators,
    load_carrier_tags,
    load_linked_editions,
    load_relation_candidates,
    load_volumes,
    replace_creators,
    replace_tags,
)
from app.rules import blank, link_editions

router = APIRouter(prefix="/api", tags=["作品"])


@router.get("/editions", response_model=EditionListOut)
def list_editions(
    q: str = "", media_type: str = "", sort: str = "", page: int = 1
) -> EditionListOut:
    """The library, one row per 作品, optionally narrowed to one media type. This is the other half of
    `/api/works` (there a row is a work; here a row is one 作品); the page picks by whether a type is
    chosen, and two addresses that each mean one thing are easier to call.
    """
    keyword = q.strip()
    with session_scope() as session:
        found = select_editions(session, keyword, media_type, sort, page)

    return EditionListOut(
        total=found.total,
        page=found.page,
        pages=found.pages,
        page_size=PAGE_SIZE,
        sort=found.sort,
        keyword=keyword,
        media_type=media_type,
        approximate=found.approximate,
        items=[
            EditionRowOut(
                **edition_ref(row.edition, row.work).model_dump(),
                matched_by=row.matched_by,
            )
            for row in found.rows
        ],
    )


@router.post("/works/{work_id}/editions", response_model=EditionOut, status_code=201)
def create_edition(work_id: int, body: EditionIn) -> EditionOut:
    """Add one 作品 to a work, with its creators and tags named in the body."""
    with session_scope() as session:
        work = get_work_or_404(session, work_id)

        if body.media_type not in MEDIA_TYPE_VALUES:
            raise HTTPException(status_code=400, detail="类型不在可选范围内。")
        published_on = _published_on(body, body.media_type)

        edition = Edition(
            work_id=work_id,
            media_type=body.media_type,
            title=body.title.strip() or None,
            summary=body.summary.strip() or None,
            org=body.org.strip() or None,
            release_status=body.release_status.strip() or None,
            volume_count=body.volume_count,
            published_on=published_on,
        )
        session.add(edition)
        session.flush()

        replace_creators(session, edition, _creator_pairs(body))
        replace_tags(session, edition, clean_names(body.tags))
        answer = _full(session, edition, work)

    return answer


@router.get("/editions/{edition_id}", response_model=EditionOut)
def show_edition(edition_id: int) -> EditionOut:
    """One 作品: its fields, its creators, its tags, its volumes and its links."""
    with session_scope() as session:
        edition = get_edition_or_404(session, edition_id)
        work = get_work_or_404(session, edition.work_id)
        answer = _full(session, edition, work)

    return answer


@router.put("/editions/{edition_id}", response_model=EditionOut)
def update_edition(edition_id: int, body: EditionIn) -> EditionOut:
    """Write this 作品's fields, creators and tags back. **The media type in the body is ignored; the one on
    the row is used** -- it is fixed when the 作品 is made and the page prints it rather than offering it.
    """
    with session_scope() as session:
        edition = get_edition_or_404(session, edition_id)
        work = get_work_or_404(session, edition.work_id)

        edition.title = body.title.strip() or None
        edition.summary = body.summary.strip() or None
        edition.org = body.org.strip() or None
        edition.release_status = body.release_status.strip() or None
        edition.volume_count = body.volume_count
        edition.published_on = _published_on(body, edition.media_type)

        replace_creators(session, edition, _creator_pairs(body))
        replace_tags(session, edition, clean_names(body.tags))
        answer = _full(session, edition, work)

    return answer


@router.delete("/editions/{edition_id}", status_code=204)
def delete_edition(edition_id: int) -> Response:
    """Remove one 作品, its volumes and its links (the work and the vocabulary stay). The covers those rows owned go too, 认文件名而不是数据库那一列。"""
    with session_scope() as session:
        edition = get_edition_or_404(session, edition_id)
        volumes = [volume.id for volume in load_volumes(session, [edition_id])]
        session.delete(edition)

    covers.remove_row_covers(covers.KIND_EDITION, edition_id)
    for volume_id in volumes:
        covers.remove_row_covers(covers.KIND_VOLUME, volume_id)

    return Response(status_code=204)


@router.get("/editions/{edition_id}/relation-candidates", response_model=list[EditionRef])
def list_relation_candidates(edition_id: int) -> list[EditionRef]:
    """The 作品 this one could still be linked to: not itself, not the 作品 of its own work, not the ones already
    linked -- that rule lives on the server (`queries.load_relation_candidates`), not in whoever draws the picker.
    """
    with session_scope() as session:
        edition = get_edition_or_404(session, edition_id)
        candidates = load_relation_candidates(session, edition)
        answer = [edition_ref(other, work) for other, work in candidates]

    return answer


@router.post("/editions/{edition_id}/relations", response_model=RelationOut, status_code=201)
def create_relation(edition_id: int, body: RelationIn) -> RelationOut:
    """Link this 作品 to another one. No kind and no direction, as on the page."""
    with session_scope() as session:
        edition = get_edition_or_404(session, edition_id)
        refusal = link_editions(session, edition, body.other_id)
        if refusal:
            raise HTTPException(status_code=400, detail=refusal)

        relation = add_edition_relation(session, edition.id, body.other_id)
        answer = RelationOut(
            edition_a_id=relation.edition_a_id, edition_b_id=relation.edition_b_id
        )

    return answer


@router.delete("/editions/{edition_id}/relations/{other_id}", status_code=204)
def remove_relation(edition_id: int, other_id: int) -> Response:
    """Drop one link, from whichever end it is asked for. Neither 作品 is touched."""
    with session_scope() as session:
        get_edition_or_404(session, edition_id)
        if not delete_edition_relation(session, edition_id, other_id):
            raise HTTPException(status_code=404, detail="这两个作品之间没有关联。")

    return Response(status_code=204)


def _full(session: Session, edition: Edition, work: Work) -> EditionOut:
    """Everything one 作品 body holds, read back after a write or for a read: reading back (not echoing the request) keeps a create and a later read saying the same thing."""
    return edition_out(
        edition,
        work,
        creators=[
            (creator_id, name, role)
            for _edition_id, role, creator_id, name in load_carrier_creators(
                session, [edition.id]
            )
        ],
        tags=[
            (tag_id, name)
            for _edition_id, tag_id, name in load_carrier_tags(session, [edition.id])
        ],
        volumes=load_volumes(session, [edition.id]),
        relations=load_linked_editions(session, [edition.id]),
    )


def _creator_pairs(body: EditionIn) -> list[tuple[str, str]]:
    """The body's creator list as the (name, role) pairs the writers expect; a name or role of only spaces is refused in the page's 「名字 角色」 words."""
    for link in body.creators:
        refusal = blank(link.name, "作者名") or blank(link.role, "角色")
        if refusal:
            raise HTTPException(status_code=400, detail=refusal)
    return [(link.name.strip(), link.role.strip()) for link in body.creators]


def _published_on(body: EditionIn, media_type: str) -> str | None:
    """Read the date the way the form does; None means 「不知道」."""
    published_on, date_error = read_published_on(
        body.published_on, media_fields(media_type)["time"]
    )
    if date_error:
        raise HTTPException(status_code=400, detail=date_error)
    return published_on


# ---- 封面 -------------------------------------------------------------------
# 规矩(先写文件再改库、不覆盖旧文件、不删硬盘上的文件、格式按内容认)在 app/covers.py,这里只收上传、交出拒绝的话。


@router.post("/editions/{edition_id}/cover", response_model=EditionOut, tags=["作品"])
def upload_cover(edition_id: int, file: UploadFile = File(...)) -> EditionOut:
    """收一张封面。**先落盘,再改数据库里的路径**。**同步函数,不是 async**:同步接口由 FastAPI 放进线程池,
    写成 async 会把读库写库压在事件循环上(上传内容从 `file.file` 直接读,所以不必 await)。
    """
    data = file.file.read(covers.MAX_BYTES + 1)
    with session_scope() as session:
        edition = get_edition_or_404(session, edition_id)
        work = get_work_or_404(session, edition.work_id)
        try:
            saved = covers.save_cover(covers.KIND_EDITION, edition.id, data)
        except covers.CoverRefused as refusal:
            raise HTTPException(status_code=400, detail=str(refusal)) from refusal
        edition.cover_path = saved.path
        edition.cover_width = saved.width
        edition.cover_height = saved.height
        session.flush()
        return _full(session, edition, work)


@router.delete("/editions/{edition_id}/cover", response_model=EditionOut, tags=["作品"])
def drop_cover(edition_id: int) -> EditionOut:
    """摘掉封面。**硬盘上那个文件留着** —— 换错了一张,想指回去还有救;尺寸跟着路径一起清空,
    它们说的是**这一个文件**多大,留着就成了上一张封面的话。
    """
    with session_scope() as session:
        edition = get_edition_or_404(session, edition_id)
        work = get_work_or_404(session, edition.work_id)
        edition.cover_path = None
        edition.cover_width = None
        edition.cover_height = None
        session.flush()
        return _full(session, edition, work)
