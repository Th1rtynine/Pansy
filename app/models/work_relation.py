"""A directed link between two works: 前传 / 后传 / 番外篇, and which one is which.

**为什么另起一张表,而不是给 `EditionRelation` 加两列**:那一张存的是**无向对子**(`edition_a_id` 永远
是小的那个,所以同一条关联从哪头进都写同一行),它自己就说了「小 id 在前的对子放不下方向」。而这里
要记的恰恰是方向 —— 「当前作品是目标作品的番外篇」与「目标作品是当前作品的番外篇」是两件事,合成
一行就再也分不出来。

两张表并存而不是替换:**载体级的关系仍然有用**(两部作品的某两个版本之间确实可能单独相关),
而作品级是说「这一部与那一部」的关系 —— 层级不同,不是同一件事的两种说法。
"""

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WorkRelation(Base):
    """一条**有方向**的作品关系:`from_work_id` 与 `to_work_id` 之间是什么关系。

    `relation_type` 用我们自己的词(related / prequel / sequel / side_story / spin_off / same_setting /
    collection / adaptation / unknown),**不是来源站的原话** —— 源各说各的,Bangumi 写「番外篇」、
    Hikarinagi 写 `SIDE_STORY`;翻译在 `app/sources/family.py` 那一层做,这里只存归一化之后的。

    `raw_relation` 保留对方的原话,`source` 记是谁说的。**留着是为了以后能改规则** —— 分类规则
    迟早要调,而调规则时手上没有原话就只能重新去抓一遍上游。

    `confidence` 是 high / low / unknown 三档,与家族预览里那一格同义。

    **旧的无向关系不猜**:`EditionRelation` 那一张原样留着,谁也没往这里搬 —— 「这两个版本相连」
    推不出「谁是前传」,凭空填一个方向比留空更糟。要搬由人一条条来。
    """

    __tablename__ = "work_relation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: 从哪一部(当前这一部)。
    from_work_id: Mapped[int] = mapped_column(
        ForeignKey("work.id", ondelete="CASCADE"), nullable=False
    )
    #: 到哪一部。**与 `from_work_id` 是两回事**,顺序本身带意思。
    to_work_id: Mapped[int] = mapped_column(
        ForeignKey("work.id", ondelete="CASCADE"), nullable=False
    )
    #: 归一化之后的关系词(见类文档)。认不出来时写 `unknown`,不写空串 —— 空串分不出「没写」与「认不出」。
    #: **`server_default` 不能省**:只写 `default` 时模型建出来的表没有 SQL 层默认值,而迁移脚本
    #: 建出来的有 —— 同一张表在两条路上行为不同(直接用 SQL 插一行,一个报 NOT NULL、一个不报)。
    #: 实测就是这么发现的:`Work.aliases` 两样都写,正是这个理由。
    relation_type: Mapped[str] = mapped_column(
        String, nullable=False, default="unknown", server_default="unknown"
    )
    #: 谁说的(bangumi / hikarinagi / manual)。`manual` 是人自己建的,那种关系不该被自动同步覆盖掉。
    source: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
    #: 对方的原话,原样留着。
    raw_relation: Mapped[str | None] = mapped_column(String)
    #: high / low / unknown。**只有 high 才默认显示成已确认的**,低置信的仍要人过目。
    confidence: Mapped[str] = mapped_column(
        String, nullable=False, default="unknown", server_default="unknown"
    )
    #: 建这一行的时刻,与 `external_ref.fetched_at` 同一个形状(字符串,人看得懂)。
    created_at: Mapped[str | None] = mapped_column(String)
    #: 关系强度(0–1),给排序用;没有就是空。**`confidence` 才是「可不可信」,这一列只是排序**。
    weight: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        # 同一对、同一种关系只记一次 —— 与 `external_ref` 那条唯一索引同一个用处:重复提交要幂等。
        # **方向算在里面**:`a -> b` 与 `b -> a` 是两条,所以约束是四列的,不是三列。
        UniqueConstraint(
            "from_work_id",
            "to_work_id",
            "relation_type",
            "source",
            name="uq_work_relation_pair",
        ),
    )
