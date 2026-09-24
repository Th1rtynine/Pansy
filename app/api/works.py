"""The JSON side of 作品总标题: list, read, create, change, remove.

Same rows and same rules as `app/routes/works.py`, only data instead of a rendered page, with
`app/listing.py` deciding which rows a list holds and in what order. `POST /works/with-editions`
(加入作品)在一个事务里建出「作品总标题 + 若干件作品」,规矩引 `app/api/editions.py` 与 `sources.py`.
"""

import json
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from sqlalchemy import select

from app import covers
from app.api.editions import _archive_values, _creator_pairs, _published_on
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
from app.models import Edition, ExternalRef, Work, WorkExternalRef
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
    remember_work_relation,
    replace_creators,
    replace_tags,
)
from app.rules import blank
from app.sources import SOURCES
from app.sources.http import fetch_bytes

router = APIRouter(prefix="/api", tags=["作品总标题"])

SOURCE_NAMES = set(SOURCES)


def _fetch_pictures(urls: list[str]) -> list[bytes | None]:
    """并行取一批封面，同时给并发设上限。

    加入同一作品的多个版本时，封面数量很容易从一张变成几十张（特别是还带分卷）。逐张等待会把
    每张图的网络延迟全部相加；这里最多同时取 8 张，顺序仍与输入一致，后面的写库逻辑不用变化。
    """
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(urls))) as pool:
        return list(pool.map(fetch_bytes, urls))


def _download_import_pictures(body: ImportIn):
    """一次下载本次导入用到的全部封面，再还原成 `_write_import` 需要的嵌套形状。"""
    urls: list[str] = []

    def remember(url: str) -> int | None:
        if not url:
            return None
        urls.append(url)
        return len(urls) - 1

    edition_slots = [remember(item.cover_url) for item in body.editions]
    volume_slots = [
        [remember(volume.cover_url) for volume in item.volumes]
        for item in body.editions
    ]
    work_slot = remember(body.work_cover_url)
    related_slots = [
        [remember(item.cover_url) for item in related.editions]
        for related in body.related
    ]
    related_volume_slots = [
        [
            [remember(volume.cover_url) for volume in item.volumes]
            for item in related.editions
        ]
        for related in body.related
    ]
    related_work_slots = [remember(related.work_cover_url) for related in body.related]

    downloaded = _fetch_pictures(urls)

    def picture(slot: int | None) -> bytes | None:
        return downloaded[slot] if slot is not None else None

    return (
        [picture(slot) for slot in edition_slots],
        [[picture(slot) for slot in slots] for slots in volume_slots],
        picture(work_slot),
        [[picture(slot) for slot in slots] for slots in related_slots],
        [
            [[picture(slot) for slot in slots] for slots in editions]
            for editions in related_volume_slots
        ],
        [picture(slot) for slot in related_work_slots],
    )


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
    标题用 `blank`、类型对 `MEDIA_TYPE_VALUES`、日期走 `_published_on`、作者与标签交给那两扇门。

    `body.related` 给了就**在同一事务里**再建那几部关联作品,并记下它们与主作品之间的有向关系 ——
    分开两次请求的话,第一次成功而第二次失败,库里就留下「主作品建好了、它该有的关联一部没有」那种
    半截状态。**每一部关联作品可以一件都没有**(人只要那条关系),但那样它就只是一条总标题。
    """
    refusal = blank(body.work.title, "作品总标题")
    if refusal:
        raise HTTPException(status_code=400, detail=refusal)
    if not body.editions:
        raise HTTPException(status_code=400, detail="至少要有这一件作品。")
    _reject_mixed_identities(body)
    for item in body.editions:
        if item.media_type not in MEDIA_TYPE_VALUES:
            raise HTTPException(status_code=400, detail="类型不在可选范围内。")
    for related in body.related:
        # 关联作品那一侧与主作品同一个规矩:名字不能空、类型要认得。**在这里先全查一遍**,
        # 而不是建到一半才发现第三部不合法 —— 那时前两部已经写进去了(虽然会被回滚,但错得晚不如错得早)。
        related_refusal = blank(related.work.title, "关联作品的总标题")
        if related_refusal:
            raise HTTPException(status_code=400, detail=related_refusal)
        for item in related.editions:
            if item.media_type not in MEDIA_TYPE_VALUES:
                raise HTTPException(status_code=400, detail="类型不在可选范围内。")

    # 封面是外链:**先取回来、再落盘、最后写库**。取图放在事务**外面** —— 一张图最大 8MB,攥着库锁等下载会让别人排队。
    # 关联作品的图也一样,在同一个事务外全取完。
    (
        pictures,
        volume_pictures,
        work_picture,
        related_pictures,
        related_volume_pictures,
        related_work_pictures,
    ) = _download_import_pictures(body)

    with session_scope() as session:
        work_id = _write_import(session, body, pictures, volume_pictures, work_picture,
                                related_pictures, related_volume_pictures, related_work_pictures)

    return show_work(work_id)


def _write_import(
    session,
    body: ImportIn,
    pictures: list,
    volume_pictures: list,
    work_picture,
    related_pictures: list,
    related_volume_pictures: list,
    related_work_pictures: list,
) -> int:
    """这一趟要写的全部东西,都在调用方给的那个 session 里做完,回主作品的 id。

    **事务边界留给调用方**:这样测试可以把它放进一个一次性临时库的 session 里跑,与线上走的是
    **同一段代码** —— 而不是另写一份「差不多的」导入逻辑去测。`_build_work` 抽出来是同一个理由。
    """
    _reject_mixed_identities(body)
    target_work_id = body.existing_work_id
    if body.work_ref is not None and body.work_ref.source in SOURCE_NAMES:
        anchored = session.execute(
            select(WorkExternalRef).where(
                WorkExternalRef.source == body.work_ref.source,
                WorkExternalRef.external_id == body.work_ref.external_id,
            )
        ).scalar_one_or_none()
        if anchored is None:
            # 兼容升级前已经录入的库：那时没有 Work 级锚点，但原作本身若已作为一个具体版本
            # 收录，它的 external_ref 仍是同一份精确证据。只按来源+编号，不按标题猜。
            legacy_work_id = session.execute(
                select(Edition.work_id)
                .join(ExternalRef, ExternalRef.edition_id == Edition.id)
                .where(
                    ExternalRef.source == body.work_ref.source,
                    ExternalRef.external_id == body.work_ref.external_id,
                )
            ).scalar_one_or_none()
            if legacy_work_id is not None:
                anchored = WorkExternalRef(
                    work_id=legacy_work_id,
                    source=body.work_ref.source,
                    external_id=body.work_ref.external_id,
                    title=body.work_ref.title,
                )
                session.add(anchored)
                session.flush()
        if anchored is not None:
            if target_work_id is not None and target_work_id != anchored.work_id:
                raise HTTPException(status_code=400, detail="这个原作已经归入另一部作品。")
            # 页面会先查一次，让人保存前就看见“将归入已有作品”；这里再判一次才是最终约束。
            # 即使查找响应晚到或两个窗口同时操作，也不能因此新建一部重复的 Work。
            target_work_id = anchored.work_id

    if target_work_id is not None:
        row = get_work_or_404(session, target_work_id)
        work_id = row.id
        _build_editions(session, row, body.editions, pictures, volume_pictures)
        # 已有总作品的名称与别名属于用户资料，不用一次自动导入覆盖。封面也只在原来没有时补上。
        if work_picture and not row.cover_path:
            _save_work_picture(session, row, work_picture)
    else:
        work_id = _build_work(
            session,
            body.work,
            body.editions,
            pictures,
            volume_pictures,
            work_picture,
        )

    if body.work_ref is not None and body.work_ref.source in SOURCE_NAMES:
        _remember_work_ref(session, work_id, body.work_ref)

    # 关联作品:一部一行,连带它与主作品的关系。**方向照 `link.direction` 来** ——
    # 「谁是番外篇」由它决定,不在这里替人排序。
    for related, related_pictures_one, related_volume_pictures_one, related_work_picture in zip(
        body.related, related_pictures, related_volume_pictures, related_work_pictures
    ):
        related_id = _build_work(
            session,
            related.work,
            related.editions,
            related_pictures_one,
            related_volume_pictures_one,
            related_work_picture,
        )
        link = related.link
        if link.direction == "from_main":
            source_id, target_id = work_id, related_id
        else:
            source_id, target_id = related_id, work_id
        remember_work_relation(
            session,
            from_work_id=source_id,
            to_work_id=target_id,
            relation_type=link.relation_type or "related",
            source=link.source,
            raw_relation=link.raw_relation,
            confidence=link.confidence,
        )

    return work_id


def _reject_mixed_identities(body: ImportIn) -> None:
    """The UI warns early; this is the transaction-side wall that cannot be bypassed."""
    identities = {
        (item.identity_ref.source, item.identity_ref.external_id)
        for item in body.editions
        if item.identity_ref is not None
    }
    if len(identities) > 1:
        raise HTTPException(status_code=400, detail="这些版本指向不同的作品，不能放进同一个条目。")
    if body.work_ref is not None and identities and (
        body.work_ref.source, body.work_ref.external_id
    ) not in identities:
        raise HTTPException(status_code=400, detail="版本的作品依据与总标题不一致。")


def _remember_work_ref(session, work_id: int, ref) -> None:
    """记住统一作品的原作锚点；同一锚点不允许落到两部作品。"""
    taken = session.execute(
        select(WorkExternalRef).where(
            WorkExternalRef.source == ref.source,
            WorkExternalRef.external_id == ref.external_id,
        )
    ).scalar_one_or_none()
    if taken is not None and taken.work_id != work_id:
        raise HTTPException(status_code=400, detail="这个原作已经归入另一部作品。")
    row = taken or WorkExternalRef(
        work_id=work_id,
        source=ref.source,
        external_id=ref.external_id,
    )
    if taken is None:
        session.add(row)
    row.title = ref.title or row.title
    session.flush()


def _build_work(
    session,
    work: WorkIn,
    editions: list,
    pictures: list,
    volume_pictures: list,
    work_picture,
) -> int:
    """把「一部总标题 + 它的件」写进这一趟事务,回它的 id。

    **抽出来是因为主作品与关联作品是同一件事**:一处写两遍的话,关联作品那一侧迟早会少做一步
    (少记 refs、少一个封面、少一次 flush),而那种偏差平时看不出来。规矩仍然只有这一份。
    """
    row = Work(
        title=work.title.strip(),
        original_title=work.original_title.strip() or None,
        aliases=json.dumps(clean_names(work.aliases), ensure_ascii=False),
    )
    session.add(row)
    session.flush()

    if work_picture:
        _save_work_picture(session, row, work_picture)

    _build_editions(session, row, editions, pictures, volume_pictures)
    return row.id


def _save_work_picture(session, row: Work, picture) -> None:
    """给总作品补一张封面；图片不合法不影响条目导入。"""
    try:
        saved = covers.save_cover(covers.KIND_WORK, row.id, picture)
    except covers.CoverRefused:
        saved = None
    if saved is not None:
        row.cover_path = saved.path
        row.cover_width = saved.width
        row.cover_height = saved.height
        session.flush()


def _build_editions(session, row: Work, editions: list, pictures: list, volume_pictures: list) -> None:
    """把若干具体版本写进一个已确定的总作品；新建与追加共用同一套规则。"""

    for item, picture, volume_picture in zip(editions, pictures, volume_pictures):
        # 载体的那半边与 POST /works/{id}/editions 一字不差:同一个 _published_on、同一个 _creator_pairs。
        published_on = _published_on(item, item.media_type)

        edition = Edition(
            work_id=row.id,
            media_type=item.media_type,
            title=item.title.strip() or None,
            summary=item.summary.strip() or None,
            org=item.org.strip() or None,
            release_status=item.release_status.strip() or None,
            volume_count=item.volume_count,
            published_on=published_on,
            **_archive_values(item),
            local_path=item.local_path.strip() or None,
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

        # 卷:从源读回来、人改过的那一份,跟着这一件在同一事务里写进去。
        # **走 `merge_volumes` 再 `add_merged_volumes`**:前一步把「同一卷被几个来源各说了一遍」合成一份,
        # 后一步按外部 id 认回已有的行 —— 于是从第二个来源再导一次不会多出一卷,而是给原来那一卷补上来源。
        if item.volumes:
            from app.queries import add_merged_volumes
            from app.sources.base import VolumeDraft
            from app.sources.volumes import merge_volumes

            # 每一卷按它自己的 refs 展开成若干草稿;**没有任何 refs 的(手工加的那一卷)也得能写进去** ——
            # 给它造一个只在本件内唯一的 `manual` 标识,`merge_volumes` 才不会把它与别人合掉。
            drafts: list[VolumeDraft] = []
            for index, volume in enumerate(item.volumes):
                known = [ref for ref in volume.refs if ref.source in SOURCE_NAMES]
                if not known:
                    drafts.append(
                        VolumeDraft(
                            source="manual",
                            external_id=f"{edition.id}:{index}",
                            number=volume.volume_number,
                            title=volume.title.strip() or None,
                            published_on=volume.published_on.strip() or None,
                            summary=volume.summary.strip() or None,
                            catalog_code=volume.catalog_code.strip() or None,
                            page_count=volume.page_count,
                            volume_type=volume.volume_type.strip() or None,
                            local_path=volume.local_path.strip() or None,
                        )
                    )
                    continue
                for ref in known:
                    drafts.append(
                        VolumeDraft(
                            source=ref.source,
                            external_id=ref.external_id,
                            number=volume.volume_number,
                            title=volume.title.strip() or None,
                            published_on=volume.published_on.strip() or None,
                            summary=volume.summary.strip() or None,
                            catalog_code=volume.catalog_code.strip() or None,
                            page_count=volume.page_count,
                            volume_type=volume.volume_type.strip() or None,
                            local_path=volume.local_path.strip() or None,
                        )
                    )
            add_merged_volumes(session, edition.id, merge_volumes(drafts).volumes)

            rows = {
                (volume_row.volume_number, volume_row.title): volume_row
                for volume_row in load_volumes(session, [edition.id])
            }
            for volume, volume_picture_one in zip(item.volumes, volume_picture):
                if not volume_picture_one:
                    continue
                found = rows.get((volume.volume_number, volume.title.strip() or None))
                if found is None:
                    continue
                try:
                    saved = covers.save_cover(covers.KIND_VOLUME, found.id, volume_picture_one)
                except covers.CoverRefused:
                    continue
                found.cover_path = saved.path
                found.cover_width = saved.width
                found.cover_height = saved.height
                session.flush()



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
