"""One carrier of a work: a manga, a light novel, a game or an anime."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Edition(Base):
    """One carrier. title 空时显示作品的标题;org / release_status / volume_count 是刻意中性的名字,装漫画的出版社、动画的制作公司或游戏的发行商,所以不必按类型扩展表。
    published_on 是文本,只写到知道的那一位(2015 / 2015-04 / 2015-04-01):没记到的月份留空而不是填 01,三种形状按文本排序就是时间序。
    原作时间不落库 —— 它是这一部各载体里最早的那个日期,画列表时算出来,所以两者不会互相矛盾;cover_width/height 是上传时从图片头读到的原图像素,让页面在图到之前占住形状(读不出则按 3:4)。
    """

    __tablename__ = "edition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("work.id", ondelete="CASCADE"), nullable=False)
    media_type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    summary: Mapped[str | None] = mapped_column(Text)
    cover_path: Mapped[str | None] = mapped_column(String)
    cover_width: Mapped[int | None] = mapped_column(Integer)
    cover_height: Mapped[int | None] = mapped_column(Integer)
    org: Mapped[str | None] = mapped_column(String)
    release_status: Mapped[str | None] = mapped_column(String)
    volume_count: Mapped[int | None] = mapped_column(Integer)
    published_on: Mapped[str | None] = mapped_column(String)
