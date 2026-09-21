"""The JSON side of 作品总标题: list, read, create, change, remove.

Same rows and same rules as `app/routes/works.py`, only data instead of a rendered page, with
`app/listing.py` deciding which rows a list holds and in what order. `POST /works/with-editions`
(加入作品)在一个事务里建出「作品总标题 + 若干件作品」,规矩引 `app/api/editions.py` 与 `sources.py`.
"""

import json

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from app import covers
from app.api.editions import _creator_pairs, _published_on
from app.api.schemas import (
    ImportIn,
    LinkedWorkOut,
    WorkDetailOut,
    WorkIn,
    WorkListOut,
    WorkOut,
    clean_names,
    edition_out,
    url_of,
    work_out,
)
from app.api.sources import remember_ref
from app.db import session_scope
from app.fields import MEDIA_TYPE_VALUES, parse_aliases
from app.listing import PAGE_SIZE, select_works
from app.models import Edition, Work
from app.queries import (
    add_volumes,
    get_work_or_404,
    load_carrier_creators,
    load_carrier_tags,
    load_editions,
    load_linked_editions,
    load_linked_works,
    load_volumes,
    load_work_start_dates,
    replace_creators,
    replace_tags,
)
from app.rules import blank
from app.sources import SOURCES
from app.sources.http import fetch_bytes

router = APIRouter(prefix="/api", tags=["作品总标题"])

SOURCE_NAMES = set(SOURCES)


@router.get("/works", response_model=WorkListOut)
def list_works(q: str = "", sort: str = "", page: int = 1) -> WorkListOut:
    """The library, one row per work, with the same search and order as the page. No `media_type`
    here: this endpoint is always 作品总标题 -- a list of 作品 is `/api/editions`.
    """
    keyword = q.strip()
    with session_scope() as session:
        found = select_works(session, keyword, sort, page)

    return WorkListOut(
        total=found.total,
        page=found.page,
        pages=found.pages,
        page_size=PAGE_SIZE,
        sort=found.sort,
        keyword=keyword,
        approximate=found.approximate,
        items=[
            work_out(row.work, row.editions, row.published_on, row.matched_by)
            for row in found.rows
        ],
    )


@router.post("/works", response_model=WorkOut, status_code=201)
def create_work(body: WorkIn) -> WorkOut:
    """Make a 作品总标题. Its 作品 are added one at a time, under it: the page makes the first one
    in the same submission (its type dropdown is part of the form), while a client can make the
    work and then post its 作品.
    """
    refusal = blank(body.title, "作品总标题")
    if refusal:
        raise HTTPException(status_code=400, detail=refusal)

    with session_scope() as session:
        work = Work(
            title=body.title.strip(),
            original_title=body.original_title.strip() or None,
            aliases=json.dumps(clean_names(body.aliases), ensure_ascii=False),
        )
        session.add(work)
        session.flush()
        answer = work_out(work, [], None)

    return answer


@router.post("/works/with-editions", response_model=WorkDetailOut, status_code=201)
def create_with_editions(body: ImportIn) -> WorkDetailOut:
    """加入作品:一个事务里建出「作品总标题 + 它的若干件作品」,每一件各记下自己的外部条目 ——
    分两次请求的话,中途一步失败就会留下一条没人要的空总标题。件数不设上限、类型可以重复
    (同一原作的两种版本靠标题、作者与外部条目区分),但「至少一件」仍然拦。规矩一条都不新写:
    标题用 `blank`、类型对 `MEDIA_TYPE_VALUES`、日期走 `_published_on`、作者与标签交给那两扇门。"""
    refusal = blank(body.work.title, "作品总标题")
    if refusal:
        raise HTTPException(status_code=400, detail=refusal)
    if not body.editions:
        raise HTTPException(status_code=400, detail="至少要有这一件作品。")
    for item in body.editions:
        if item.media_type not in MEDIA_TYPE_VALUES:
            raise HTTPException(status_code=400, detail="类型不在可选范围内。")

    # 封面是外链:**先取回来、再落盘、最后写库**。取图放在事务**外面** —— 一张图最大 8MB,攥着库锁等下载会让别人排队。
    pictures = [
        fetch_bytes(item.cover_url) if item.cover_url else None for item in body.editions
    ]
    # 卷的封面也是外链,同样**先取回来**(一部常常几十条),全部取完再写库,写事务里只落盘;取不到的跳过。
    volume_pictures = [
        [fetch_bytes(volume.cover_url) if volume.cover_url else None for volume in item.volumes]
        for item in body.editions
    ]
    # 总标题自己的封面也是外链(原作那一条的图),同样在写库之前取回来。
    work_picture = fetch_bytes(body.work_cover_url) if body.work_cover_url else None

    with session_scope() as session:
        work = Work(
            title=body.work.title.strip(),
            original_title=body.work.original_title.strip() or None,
            aliases=json.dumps(clean_names(body.work.aliases), ensure_ascii=False),
        )
        session.add(work)
        session.flush()

        # 总标题自己的封面:原作那一条的图。取不到或格式不认就跳过 —— 读取那一侧会沿用第一件的封面。
        if work_picture:
            try:
                saved = covers.save_cover(covers.KIND_WORK, work.id, work_picture)
            except covers.CoverRefused:
                saved = None
            if saved is not None:
                work.cover_path = saved.path
                work.cover_width = saved.width
                work.cover_height = saved.height
                session.flush()

        for item, picture, volume_picture in zip(body.editions, pictures, volume_pictures):
            # 载体的那半边与 POST /works/{id}/editions 一字不差:同一个 _published_on、同一个 _creator_pairs。
            published_on = _published_on(item, item.media_type)

            edition = Edition(
                work_id=work.id,
                media_type=item.media_type,
                title=item.title.strip() or None,
                summary=item.summary.strip() or None,
                org=item.org.strip() or None,
                release_status=item.release_status.strip() or None,
                volume_count=item.volume_count,
                published_on=published_on,
            )
            session.add(edition)
            session.flush()

            replace_creators(session, edition, _creator_pairs(item))
            replace_tags(session, edition, clean_names(item.tags))

            for ref in item.refs:
                if ref.source in SOURCE_NAMES:
                    remember_ref(session, edition.id, ref)

            # 取不到或格式不认就跳过:作品已经建好了,封面可以在它自己的页面上再传。
            if picture:
                try:
                    saved = covers.save_cover(covers.KIND_EDITION, edition.id, picture)
                except covers.CoverRefused:
                    saved = None
                if saved is not None:
                    edition.cover_path = saved.path
                    edition.cover_width = saved.width
                    edition.cover_height = saved.height
                    session.flush()

            # 卷:从源读回来、人改过的那一份,跟着这一件在同一事务里写进去,用 `add_volumes`(自带卷号跳过);卷的封面按**卷号 + 名字**认回刚建好的行。
            if item.volumes:
                add_volumes(
                    session,
                    edition.id,
                    [
                        (
                            volume.volume_number,
                            volume.title.strip() or None,
                            volume.published_on.strip() or None,
                        )
                        for volume in item.volumes
                    ],
                )
                rows = {
                    (row.volume_number, row.title): row
                    for row in load_volumes(session, [edition.id])
                }
                for volume, volume_picture in zip(item.volumes, volume_picture):
                    if not volume_picture:
                        continue
                    row = rows.get((volume.volume_number, volume.title.strip() or None))
                    if row is None:
                        continue
                    try:
                        saved = covers.save_cover(covers.KIND_VOLUME, row.id, volume_picture)
                    except covers.CoverRefused:
                        continue
                    row.cover_path = saved.path
                    row.cover_width = saved.width
                    row.cover_height = saved.height
                    session.flush()

        work_id = work.id

    return show_work(work_id)


@router.get("/works/{work_id}", response_model=WorkDetailOut)
def show_work(work_id: int) -> WorkDetailOut:
    """One work: its own fields, its 原作时间, every 作品 of it, and its links."""
    with session_scope() as session:
        work = get_work_or_404(session, work_id)
        editions = load_editions(session, work_id)
        edition_ids = [edition.id for edition in editions]

        # Every work's date read once, not once per linked work; the links are read the same way.
        start_dates = load_work_start_dates(session)
        published_on = start_dates.get(work_id)
        linked = load_linked_works(session, edition_ids)
        volumes = load_volumes(session, edition_ids)
        creators = load_carrier_creators(session, edition_ids)
        tags = load_carrier_tags(session, edition_ids)

        # 每件作品自己的关联一件一件读:load_linked_editions 丢掉两端都在视野里的行,单个 id 时那只可能是连到自身。
        contents = [
            edition_out(
                edition,
                work,
                creators=[
                    (creator_id, name, role)
                    for row_edition_id, role, creator_id, name in creators
                    if row_edition_id == edition.id
                ],
                tags=[
                    (tag_id, name)
                    for row_edition_id, tag_id, name in tags
                    if row_edition_id == edition.id
                ],
                volumes=[volume for volume in volumes if volume.edition_id == edition.id],
                relations=load_linked_editions(session, [edition.id]),
            )
            for edition in editions
        ]

        # 这一部想用的图与 `work_out` 同一条规矩:自己传过用它,没传过沿用第一件的封面;没有复用它是因为详情自己拼 `WorkDetailOut`。
        fallback = next((edition for edition in editions if edition.cover_path), None)
        chosen = work if work.cover_path else fallback
        answer = WorkDetailOut(
            id=work.id,
            title=work.title,
            original_title=work.original_title,
            aliases=parse_aliases(work.aliases),
            published_on=published_on,
            cover_url=url_of(chosen.cover_path) if chosen is not None else None,
            cover_width=chosen.cover_width if chosen is not None else None,
            cover_height=chosen.cover_height if chosen is not None else None,
            editions=contents,
            linked_works=[
                LinkedWorkOut(
                    id=other.id,
                    title=other.title,
                    published_on=start_dates.get(other.id),
                    edition_count=count,
                )
                for other, count in linked
            ],
        )

    return answer


@router.put("/works/{work_id}", response_model=WorkOut)
def update_work(work_id: int, body: WorkIn) -> WorkOut:
    """Write the three shared fields back."""
    refusal = blank(body.title, "作品总标题")
    if refusal:
        raise HTTPException(status_code=400, detail=refusal)

    with session_scope() as session:
        work = get_work_or_404(session, work_id)
        work.title = body.title.strip()
        work.original_title = body.original_title.strip() or None
        work.aliases = json.dumps(clean_names(body.aliases), ensure_ascii=False)

        editions = load_editions(session, work_id)
        published_on = load_work_start_dates(session, [work_id]).get(work_id)
        answer = work_out(work, editions, published_on)

    return answer


@router.post("/works/{work_id}/cover", response_model=WorkOut, tags=["作品总标题"])
def upload_work_cover(work_id: int, file: UploadFile = File(...)) -> WorkOut:
    """收一张总标题的封面。**先落盘,再改数据库里的路径** —— 见 `app/covers.py`。与件、卷的封面同一套
    规矩、同一个模块,只有文件名分得出来(`work-3.jpg`)。没传过时读取那一侧沿用第一件的封面。
    """
    data = file.file.read(covers.MAX_BYTES + 1)
    with session_scope() as session:
        work = get_work_or_404(session, work_id)
        try:
            saved = covers.save_cover(covers.KIND_WORK, work.id, data)
        except covers.CoverRefused as refusal:
            raise HTTPException(status_code=400, detail=str(refusal)) from refusal
        work.cover_path = saved.path
        work.cover_width = saved.width
        work.cover_height = saved.height
        session.flush()
        editions = load_editions(session, work_id)
        answer = work_out(work, editions, load_work_start_dates(session).get(work_id))

    return answer


@router.delete("/works/{work_id}/cover", response_model=WorkOut, tags=["作品总标题"])
def drop_work_cover(work_id: int) -> WorkOut:
    """摘掉总标题自己的封面。**硬盘上那个文件留着** —— 换错了一张,想指回去还有救。摘掉之后页面
    上看到的是它第一件的封面,不是空白。
    """
    with session_scope() as session:
        work = get_work_or_404(session, work_id)
        work.cover_path = None
        work.cover_width = None
        work.cover_height = None
        session.flush()
        editions = load_editions(session, work_id)
        answer = work_out(work, editions, load_work_start_dates(session).get(work_id))

    return answer


@router.delete("/works/{work_id}", status_code=204)
def delete_work(work_id: int) -> Response:
    """Remove a work. Its 作品 and their volumes go with it, via the schema; the cover files those rows
    owned go too, including the ones 换封面 and 摘掉封面 left behind. Creators and tags stay.
    """
    with session_scope() as session:
        work = get_work_or_404(session, work_id)
        carriers = [edition.id for edition in load_editions(session, work_id)]
        volumes = [volume.id for volume in load_volumes(session, carriers)]
        session.delete(work)

    # 库先落地,再动硬盘。反过来的话,事务要是没提交成,图就白删了。
    covers.remove_row_covers(covers.KIND_WORK, work_id)
    for edition_id in carriers:
        covers.remove_row_covers(covers.KIND_EDITION, edition_id)
    for volume_id in volumes:
        covers.remove_row_covers(covers.KIND_VOLUME, volume_id)

    return Response(status_code=204)
