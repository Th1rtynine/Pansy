"""One carrier's counterpart on an outside site: which entry it is there.

One row per (source, entry) -- a column per source would mean a migration every time a source is added. It is
also the dedup key: the same outside entry must not become a second record here, and that check compares ids,
not titles. `edition_id`, not `work_id`: an outside entry is carrier-level in every source looked at, not our 作品总标题.
"""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExternalRef(Base):
    """「这一条作品在某个站上是哪一条」,以及取回它时那边的样子。
    `external_id` 是文本:VNDB 说 `v4` 而不是 `4`,两边的编号不能撞。`title` 与 `url` 留着,因为一个光秃秃的数字
    半年后什么也说明不了;行随它的作品一起消失(`CASCADE`)—— 它不是共用词表,是关于那一条记录的备注。
    """

    __tablename__ = "external_ref"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    edition_id: Mapped[int] = mapped_column(
        ForeignKey("edition.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    fetched_at: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        # 同一个站上的同一条,库里只许记一次 —— 判重就靠它。
        UniqueConstraint("source", "external_id", name="uq_external_ref_source_entry"),
    )
