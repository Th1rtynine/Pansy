"""A link between two carriers. Not between two works: see the note below."""

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EditionRelation(Base):
    """Two carriers that are connected, stored once as an unordered pair: `edition_a_id` 永远是小的那个,所以
    同一条关联从哪头进都写同一行(镜像的重复表达不出来,那条检查顺带排除了自己连自己);挂在载体而不是作品上 ——
    同一作品的载体已经靠作品连在一起,只有载体这一级说得清指的是哪两个。不存种类与方向:前传 / 续集 是方向,而小 id 在前的对子放不下方向。
    """

    __tablename__ = "edition_relation"

    edition_a_id: Mapped[int] = mapped_column(
        ForeignKey("edition.id", ondelete="CASCADE"), primary_key=True
    )
    edition_b_id: Mapped[int] = mapped_column(
        ForeignKey("edition.id", ondelete="CASCADE"), primary_key=True
    )

    # A foreign key cannot express this, so the database is told directly.
    __table_args__ = (
        CheckConstraint("edition_a_id < edition_b_id", name="ck_edition_relation_order"),
    )

