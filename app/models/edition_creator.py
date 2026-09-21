"""Who worked on which carrier, in what role."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EditionCreator(Base):
    """Many-to-many link between a carrier and its creators, with a role. 联合主键让同一个人在同一载体上
    可以有几个职位(例如 原作 与 作画 是同一人);`edition_id` 随载体 CASCADE,`creator_id` 不 CASCADE ——
    还在用的作者删不掉,只能先解除这条关联。
    """

    __tablename__ = "edition_creator"

    edition_id: Mapped[int] = mapped_column(
        ForeignKey("edition.id", ondelete="CASCADE"), primary_key=True
    )
    creator_id: Mapped[int] = mapped_column(ForeignKey("creator.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String, primary_key=True)
