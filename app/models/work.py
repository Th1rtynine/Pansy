"""The identity of one work, shared by every carrier of it."""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Work(Base):
    """One work. 载体在 edition,卷再低一层;这里的 `title` 是共用的那个,自己没有标题的载体显示它。
    这张表上面没有别的东西:成系列、同世界观的作品不另立一行 —— 关联作品 说两条相连,标签说哪些归在一起,
    而「上面那层」装的就是一个集合,集合已经是标签了。
    """

    __tablename__ = "work"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    original_title: Mapped[str | None] = mapped_column(String)
    aliases: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")

    # 总标题自己的封面。与 edition、volume 的封面列一字不差:路径 + 原图的像素宽高。
    # **空的时候读取那一侧沿用第一件作品的封面** —— 所以每一部作品在页面上永远有一张图
    # 可看,而这一列是「这一部想用哪张」的那个选择。
    cover_path: Mapped[str | None] = mapped_column(String)
    cover_width: Mapped[int | None] = mapped_column(Integer)
    cover_height: Mapped[int | None] = mapped_column(Integer)
