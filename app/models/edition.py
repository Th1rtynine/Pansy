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
    ended_on: Mapped[str | None] = mapped_column(String)
    subtype: Mapped[str | None] = mapped_column(String)
    region: Mapped[str | None] = mapped_column(String)
    language: Mapped[str | None] = mapped_column(String)
    catalog_code: Mapped[str | None] = mapped_column(String)
    homepage: Mapped[str | None] = mapped_column(String)
    engine: Mapped[str | None] = mapped_column(String)
    audience: Mapped[str | None] = mapped_column(String)
    reading_mode: Mapped[str | None] = mapped_column(String)
    content_notice: Mapped[str | None] = mapped_column(String)
    # 多值档案用 JSON 文本保存；仍属于这一具体版本，不会上提到 Work。
    # 可空是为了让旧的手写 SQL/迁移探针仍能插入版本；读出时统一把空值当成 []。
    platforms: Mapped[str | None] = mapped_column(Text, default="[]")
    organizations: Mapped[str | None] = mapped_column(Text, default="[]")
    official_links: Mapped[str | None] = mapped_column(Text, default="[]")
    # 本机资源入口(可执行文件、目录、电子书或视频)。当前只记录，不由服务器直接执行。
    local_path: Mapped[str | None] = mapped_column(String)
