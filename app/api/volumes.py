"""The JSON side of 卷: list a 作品's volumes, add several, change one, remove one.
One volume = one row of a 作品's internal list, named by media type; refusals ask `fields.media_unit`.
"""

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from app import covers
from app.api.schemas import VolumeIn, VolumeOut, VolumesAddedOut, volume_out
from app.db import session_scope
from app.queries import (
    add_volumes,
    get_edition_or_404,
    get_volume_or_404,
    load_volumes,
)
from app.rules import volume_number_taken

router = APIRouter(prefix="/api", tags=["卷"])


@router.get("/editions/{edition_id}/volumes", response_model=list[VolumeOut])
def list_volumes(edition_id: int) -> list[VolumeOut]:
    """This 作品's volumes, in number order, unnumbered ones last."""
    with session_scope() as session:
        get_edition_or_404(session, edition_id)
        volumes = load_volumes(session, [edition_id])
        answer = [volume_out(volume) for volume in volumes]

    return answer


@router.post("/editions/{edition_id}/volumes", response_model=VolumesAddedOut)
def create_volumes(edition_id: int, body: list[VolumeIn]) -> VolumesAddedOut:
    """Add several volumes at once, skipping the numbers this 作品 already has -- 粘贴三十行的人要
    的是新的那几条;手写一条会被拒,见 update_volume。"""
    with session_scope() as session:
        edition = get_edition_or_404(session, edition_id)
        added, skipped = add_volumes(
            session,
            edition.id,
            [
                (
                    item.volume_number, item.title.strip() or None, item.published_on.strip() or None,
                    item.summary.strip() or None, item.catalog_code.strip() or None, item.page_count,
                    item.volume_type.strip() or None, item.local_path.strip() or None,
                )
                for item in body
            ],
        )
        volumes = load_volumes(session, [edition.id])
        answer = VolumesAddedOut(
            added=added, skipped=skipped, volumes=[volume_out(volume) for volume in volumes]
        )

    return answer


@router.get("/volumes/{volume_id}", response_model=VolumeOut)
def show_volume(volume_id: int) -> VolumeOut:
    with session_scope() as session:
        volume = get_volume_or_404(session, volume_id)
        answer = volume_out(volume)

    return answer


@router.put("/volumes/{volume_id}", response_model=VolumeOut)
def update_volume(volume_id: int, body: VolumeIn) -> VolumeOut:
    """Write one volume back, refusing a number its 作品 already uses."""
    with session_scope() as session:
        volume = get_volume_or_404(session, volume_id)
        edition = get_edition_or_404(session, volume.edition_id)

        taken = volume_number_taken(
            session, edition, body.volume_number, exclude_id=volume.id
        )
        if taken:
            raise HTTPException(status_code=400, detail=taken)

        volume.volume_number = body.volume_number
        volume.title = body.title.strip() or None
        volume.summary = body.summary.strip() or None
        volume.published_on = body.published_on.strip() or None
        volume.catalog_code = body.catalog_code.strip() or None
        volume.page_count = body.page_count
        volume.volume_type = body.volume_type.strip() or None
        volume.path = body.local_path.strip() or None
        answer = volume_out(volume)

    return answer


@router.delete("/volumes/{volume_id}", status_code=204)
def delete_volume(volume_id: int) -> Response:
    """Remove one volume. Its 作品 and its work stay.
    封面文件跟着删,认的是文件名,换封面留下的旧版本与摘掉封面后没人指着的那张也算(见
    `app/covers.py`);摘掉封面本身不动文件 —— 记录还在,换错了还指得回去。
    """
    with session_scope() as session:
        volume = get_volume_or_404(session, volume_id)
        session.delete(volume)

    covers.remove_row_covers(covers.KIND_VOLUME, volume_id)

    return Response(status_code=204)


# ---- 封面 -------------------------------------------------------------------
# 与作品的封面同一套规矩、同一个模块(`app/covers.py`),只靠文件名区分;一卷的封面是那一卷的样子,作品那一张是整套的样子。


@router.post("/volumes/{volume_id}/cover", response_model=VolumeOut, tags=["卷"])
def upload_cover(volume_id: int, file: UploadFile = File(...)) -> VolumeOut:
    """收一张卷的封面。**先落盘,再改数据库里的路径** —— 见 `app/covers.py`。"""
    data = file.file.read(covers.MAX_BYTES + 1)
    with session_scope() as session:
        volume = get_volume_or_404(session, volume_id)
        try:
            saved = covers.save_cover(covers.KIND_VOLUME, volume.id, data)
        except covers.CoverRefused as refusal:
            raise HTTPException(status_code=400, detail=str(refusal)) from refusal
        volume.cover_path = saved.path
        volume.cover_width = saved.width
        volume.cover_height = saved.height
        session.flush()
        return volume_out(volume)


@router.delete("/volumes/{volume_id}/cover", response_model=VolumeOut, tags=["卷"])
def drop_cover(volume_id: int) -> VolumeOut:
    """摘掉这一卷的封面:硬盘上那个文件留着(换错了一张还指得回去),尺寸跟着路径一起清空 ——
    它们说的是这一个文件多大,留着就成了上一张封面的话。"""
    with session_scope() as session:
        volume = get_volume_or_404(session, volume_id)
        volume.cover_path = None
        volume.cover_width = None
        volume.cover_height = None
        session.flush()
        return volume_out(volume)
