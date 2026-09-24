"""The tables, one class per module.

Importing this package registers every table on Base.metadata, which is what db.init_db() 的 create_all() 靠的;
这里没导入的模型不会被建表,`scripts/check.py` 靠列出期望的表来发现。
"""

from app.models.base import Base
from app.models.creator import Creator
from app.models.edition import Edition
from app.models.edition_creator import EditionCreator
from app.models.edition_relation import EditionRelation
from app.models.edition_tag import EditionTag
from app.models.external_ref import ExternalRef
from app.models.tag import Tag
from app.models.volume import Volume
from app.models.volume_external_ref import VolumeExternalRef
from app.models.work import Work
from app.models.work_external_ref import WorkExternalRef
from app.models.work_relation import WorkRelation

__all__ = [
    "Base",
    "Creator",
    "Edition",
    "EditionCreator",
    "EditionRelation",
    "EditionTag",
    "ExternalRef",
    "Tag",
    "Volume",
    "VolumeExternalRef",
    "Work",
    "WorkExternalRef",
    "WorkRelation",
]
