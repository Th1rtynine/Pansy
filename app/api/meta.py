"""The JSON side of what is not a record: the media types themselves.

**「哪个类型记哪几项、每项叫什么」只有 `app/fields.py` 一份**,抄过去就是留一份会过期的副本;它不
属于任何一张表,所以不挂在某个实体下 —— 这个文件就是「不属于谁的那些接口」。
"""

from fastapi import APIRouter

from app.api.schemas import MediaTypeListOut, MediaTypeOut
from app.fields import MEDIA_TYPE_FIELDS, MEDIA_TYPE_LABELS

router = APIRouter(prefix="/api", tags=["类型"])


@router.get("/media-types", response_model=MediaTypeListOut)
def list_media_types() -> MediaTypeListOut:
    """每一种媒体类型:取值、名字、以及它记哪几项。顺序即 MEDIA_TYPE_LABELS 的顺序,从原作往外排。"""
    return MediaTypeListOut(
        items=[
            MediaTypeOut(
                value=value,
                label=label,
                fields=dict(MEDIA_TYPE_FIELDS[value]),
            )
            for value, label in MEDIA_TYPE_LABELS.items()
        ]
    )
