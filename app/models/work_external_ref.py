"""A stable outside identity for a unified Work, separate from any concrete edition."""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WorkExternalRef(Base):
    """同一原作在来源站上的锚点。

    Edition 的来源编号回答“这是哪个具体版本”；这里回答“这些版本共同属于哪一部作品”。
    两层不能混用，否则把原作编号挂到漫画版本上后，真正导入小说时会被误判成重复版本。
    """

    __tablename__ = "work_external_ref"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("work.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_work_external_ref_source_entry"),
    )
