"""One volume inside a carrier, and the file that holds it."""

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Volume(Base):
    """One volume, season or episode of a carrier. `volume_number` 是实数(4.5 这种夹在中间的卷才排得对),
    也可空 —— SS、上、下 就是没有号的卷,它们排最后。`path` 是文件在磁盘上的路径,还没拿到的卷留着行、path 空;
    整部打包这种载体级文件记成「空卷号 + 手写卷名」的一行。cover_width/height 与载体上那两列同义。
    """

    __tablename__ = "volume"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    edition_id: Mapped[int] = mapped_column(
        ForeignKey("edition.id", ondelete="CASCADE"), nullable=False
    )
    volume_number: Mapped[float | None] = mapped_column(Float)
    title: Mapped[str | None] = mapped_column(String)
    summary: Mapped[str | None] = mapped_column(Text)
    # 发售日:与 `edition.published_on` 同一个形状(可空,写多少算多少 —— 「2006」、
    # 「2006-05」、「2006-05-24」都合法)。从源里读一个系列底下的卷时,每一条单行本
    # 自己就带着它(例如 `Fate/stay night (01)` = 2006-05-24)。
    published_on: Mapped[str | None] = mapped_column(String)
    cover_path: Mapped[str | None] = mapped_column(String)
    cover_width: Mapped[int | None] = mapped_column(Integer)
    cover_height: Mapped[int | None] = mapped_column(Integer)
    path: Mapped[str | None] = mapped_column(String)

    # Rows with an empty volume_number are excluded from the uniqueness rule,
    # so several unnumbered volumes may coexist in one carrier.
    __table_args__ = (
        Index(
            "uq_volume_number",
            "edition_id",
            "volume_number",
            unique=True,
            sqlite_where=text("volume_number IS NOT NULL"),
        ),
    )
