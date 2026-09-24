"""一卷在外部站点上是哪一条。

**为什么另起一张表,而不是把 `external_ref` 泛化成「能指向不同实体」**:那一张的 `edition_id` 是
`NOT NULL` 的外键,泛化意味着把那一列变成可空、再加一个「指向哪张表」的判别列 —— 于是每一处读
`external_ref` 的地方都要先看判别列,而其中绝大多数只是想要「这一件作品在哪个站上是哪一条」。
一张小表比一个到处要判别的列便宜。

**它要解决的是一件具体的事**:同一卷常常在两个站上各有一条(轻小说在 Bangumi 与 Hikarinagi 都有),
合并之后必须记得「这一行是哪几条合出来的」—— 否则下一次导入认不出它,又会建出第二行。
"""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VolumeExternalRef(Base):
    """「这一卷在某个站上是哪一条」。与 `external_ref` 同一条规矩:同一站上的同一条只许记一次。

    行随它的卷一起消失(`CASCADE`):它不是共用词表,是关于那一卷的备注。
    `title` 留着,因为一个光秃秃的编号半年后什么也说明不了。
    """

    __tablename__ = "volume_external_ref"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    volume_id: Mapped[int] = mapped_column(
        ForeignKey("volume.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    #: 文本而不是整数:VNDB 说 `v4`,Hikarinagi 说 `ln:81467:volume:9`。
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    fetched_at: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        # 与 `external_ref` 那条完全对称:同一个站上的同一条,库里只许记一次。
        UniqueConstraint("source", "external_id", name="uq_volume_external_ref_source_entry"),
    )
