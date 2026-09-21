"""Tags."""

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tag(Base):
    """One tag, belonging to one media type: 同一个词可以是两个标签(漫画的 战斗 与动画的 战斗 是两行,
    互不相干,改一个的名字不动另一个)—— 杂志名在动画上没有意义,视觉小说在漫画上也没有。
    `name` 在类型内唯一:同类型重复录入被拒,另一个类型下的同一个词照收。
    """

    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_type: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (UniqueConstraint("media_type", "name", name="uq_tag_media_name"),)
