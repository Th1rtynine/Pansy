"""Which tags a carrier carries."""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EditionTag(Base):
    """Many-to-many link between a carrier and its tags. 标签挂在载体而不是作品上:台版、BDRip、作画崩坏
    这类只属于载体的标签没有别处可放,而作品级的标签可以逐个载体挂。
    """

    __tablename__ = "edition_tag"

    edition_id: Mapped[int] = mapped_column(
        ForeignKey("edition.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("tag.id"), primary_key=True)
