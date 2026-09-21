"""Authors and the studios or circles behind a work."""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Creator(Base):
    """One creator. 同一个人在不同载体上可以是不同职位(职位由 edition_creator 记),所以这里只有一行;
    `name` 唯一,重复录入同一个人会在源头被拒。笔名与异体写法进 `aliases`,不新开一行。
    """

    __tablename__ = "creator"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    aliases: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
