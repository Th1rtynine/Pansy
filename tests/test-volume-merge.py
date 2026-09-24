"""分卷合并:同一卷认得出、该合的合、不该合的不合、冲突如实报。

**为什么单独一个文件**:规格把这一块列得很细 —— 正篇与 EXTRA、第 0 卷、7.5 卷、上下卷、短篇集、
别册,以及「两个来源卷名与日期冲突」。这些外面看不出来,只有拿具体的卷摆进去跑一遍才知道合没合对。
纯函数,不连网、不碰库。

**一条容易被忽略的边界**:《安达与岛村99.9》看着像 7.5 卷那种编号,但它**是一部独立作品**(番外篇),
不是卷 —— 所以它该由关系图排除,不该出现在分卷这一步里。这里也考了「像卷号的东西不等于卷」。

用法:`python tests/test-volume-merge.py`。
"""

from __future__ import annotations

import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.sources.base import VolumeDraft  # noqa: E402
from app.sources.volumes import (  # noqa: E402
    merge_volumes,
    normalize_title,
    ordinal_of,
    same_volume,
)


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.step = 0

    def check(self, label: str, passed: bool, detail: str = "") -> None:
        self.step += 1
        print(f"{'PASS' if passed else 'FAIL'} [{self.step:02d}] {label}" + (f"  -- {detail}" if detail else ""))
        if passed:
            self.passed += 1
        else:
            self.failed += 1


def draft(source: str, external_id: str, **kwargs) -> VolumeDraft:
    return VolumeDraft(source=source, external_id=external_id, **kwargs)


BGM = "bangumi"
HKN = "hikarinagi"


def main() -> int:
    checks = Checks()

    # ---- 1. 同一个来源的同一条:外部 id 说了算 ------------------------------------
    rows = merge_volumes(
        [
            draft(BGM, "66306", number=1, title="安達としまむら (1)"),
            draft(BGM, "66306", number=1, title="安達としまむら (1)", cover_url="http://x/1.jpg"),
        ]
    )
    checks.check("同一个来源的同一条只留一行", len(rows.volumes) == 1, f"{len(rows.volumes)} 行")
    checks.check("而且它的外部 id 记下来了", rows.volumes[0].refs == [(BGM, "66306")])

    # ---- 2. 跨来源同一卷:按卷号认出来 -------------------------------------------
    rows = merge_volumes(
        [
            draft(BGM, "66306", number=1, title="安達としまむら (1)", published_on="2016-01-01"),
            draft(HKN, "ln:1:volume:9", number=1, title="安达与岛村 第1卷", cover_url="http://x/1.jpg"),
        ]
    )
    volume = rows.volumes[0]
    checks.check("跨来源按卷号合成一行", len(rows.volumes) == 1, f"{len(rows.volumes)} 行")
    checks.check(
        "**两个来源都在它身上**(下次导入才认得出它)",
        sorted(volume.refs) == [(BGM, "66306"), (HKN, "ln:1:volume:9")],
        f"{volume.refs}",
    )
    checks.check(
        "封面只补空格子(第二个来源带了图,第一个没有)",
        volume.cover_url == "http://x/1.jpg",
        f"{volume.cover_url}",
    )
    checks.check(
        "**多语种卷名算提示,不算冲突**",
        not rows.conflicts and rows.notes,
        f"冲突={rows.conflicts} 提示={rows.notes}",
    )

    # ---- 3. 日期真的对不上,才算冲突 ---------------------------------------------
    rows = merge_volumes(
        [
            draft(BGM, "a", number=2, title="安達としまむら (2)", published_on="2017-09-09"),
            draft(HKN, "ln:1:volume:2", number=2, title="安达与岛村 第2卷", published_on="2017-05-01"),
        ]
    )
    checks.check(
        "日期对不上时报冲突,而且**保留先到的那个说法**(不静默覆盖)",
        bool(rows.conflicts) and rows.volumes[0].published_on == "2017-09-09",
        f"冲突={rows.conflicts} 留的是 {rows.volumes[0].published_on}",
    )

    # ---- 4. 非标准卷号:0、7.5、上下、EXTRA ---------------------------------------
    rows = merge_volumes(
        [
            draft(BGM, "z0", number=0.0, title="第0卷"),
            draft(BGM, "zh", number=7.5, title="7.5 短篇集"),
            draft(BGM, "up", number=None, title="上"),
            draft(BGM, "down", number=None, title="下"),
            draft(BGM, "ex", number=None, title="EXTRA"),
        ]
    )
    numbers = [(v.number, v.title) for v in rows.volumes]
    checks.check(
        "**第 0 卷与 7.5 卷都留得住**(实数卷号就是为这个)",
        (0.0, "第0卷") in numbers and (7.5, "7.5 短篇集") in numbers,
        f"{numbers}",
    )
    checks.check(
        "**上/下/EXTRA 都没有号,而且各占一行**(不因「都没号」互相吞掉)",
        len([v for v in rows.volumes if v.number is None]) == 3,
        f"{[v.title for v in rows.volumes if v.number is None]}",
    )
    checks.check(
        "没号的排在最后",
        all(v.number is not None for v in rows.volumes[:2]),
        f"{numbers}",
    )

    # ---- 5. 上下卷跨来源要认得出 ------------------------------------------------
    same, why = same_volume(draft(BGM, "u", title="上巻"), draft(HKN, "h:up", title="上"))
    checks.check("「上巻」与「上」算同一卷", same, f"凭 {why}")
    same, why = same_volume(draft(BGM, "u", title="上"), draft(HKN, "h:d", title="下"))
    checks.check("「上」与「下」不算同一卷", not same, f"凭 {why}")

    # ---- 6. 卷号不一致时不硬合 ---------------------------------------------------
    same, why = same_volume(
        draft(BGM, "a", number=8, title="安達としまむら (8)"),
        draft(HKN, "b", number=9, title="安达与岛村 第9卷"),
    )
    checks.check("**卷号不同就不合并**(宁可两行,不替人猜)", not same, f"凭 {why}")

    # ---- 7. 只有日期一致时才合 ---------------------------------------------------
    rows = merge_volumes(
        [
            draft(BGM, "a", number=None, title=None, published_on="2020-03-01"),
            draft(HKN, "b", number=None, title=None, published_on="2020-03-01"),
        ]
    )
    checks.check(
        "两条都没号没名字,但同一天出 —— 合成一行",
        len(rows.volumes) == 1,
        f"{len(rows.volumes)} 行",
    )
    rows = merge_volumes(
        [
            draft(BGM, "a", number=None, title=None, published_on="2020-03-01"),
            draft(HKN, "b", number=None, title=None, published_on="2021-03-01"),
        ]
    )
    checks.check("日期不同就各留一行", len(rows.volumes) == 2, f"{len(rows.volumes)} 行")

    # ---- 8. 两卷真的不同时不许被吞 -----------------------------------------------
    rows = merge_volumes(
        [
            draft(BGM, "v1", number=1, title="安達としまむら (1)"),
            draft(BGM, "v2", number=2, title="安達としまむら (2)"),
            draft(BGM, "v3", number=3, title="安達としまむら (3)"),
        ]
    )
    checks.check(
        "同一来源的三卷各占一行",
        len(rows.volumes) == 3 and [v.number for v in rows.volumes] == [1.0, 2.0, 3.0],
        f"{[v.number for v in rows.volumes]}",
    )

    # ---- 9. 归一化本身 -----------------------------------------------------------
    checks.check(
        "全角半角、空格、括号都不影响「是不是同一个名字」",
        normalize_title("安達としまむら (1)") == normalize_title("安達としまむら(1)")
        == normalize_title("安達としまむら　1"),
        f"{normalize_title('安達としまむら (1)')}",
    )
    checks.check("认不出卷序时回 None,不猜", ordinal_of("随便一个名字") is None)

    # ---- 10. 「像卷号」不等于卷 ---------------------------------------------------
    # 《安达与岛村99.9》那一条:它**是一部独立作品**,该由关系图排除,不该出现在分卷这一步。
    # 分卷这一步只处理「来源明确说是某一件底下的卷」的那些,所以这里考的是:它作为一个普通标题
    # 既不会被当成第 99.9 卷、也不会与 7.5 卷合并。
    rows = merge_volumes(
        [
            draft(BGM, "ninetynine", number=None, title="安达与岛村99.9"),
            draft(BGM, "sevenfive", number=7.5, title="7.5 短篇集"),
        ]
    )
    checks.check(
        "《安达与岛村99.9》**没有**被当成 99.9 卷、也没并进 7.5 卷",
        len(rows.volumes) == 2 and rows.volumes[0].number == 7.5,
        f"{[(v.number, v.title) for v in rows.volumes]}",
    )

    # ---- 11. 顺序稳定:同一批输入跑两次结果一样 -----------------------------------
    batch = [
        draft(BGM, "a", number=3, title="C"),
        draft(BGM, "b", number=1, title="A"),
        draft(BGM, "c", number=2, title="B"),
        draft(HKN, "d", number=1, title="A"),
    ]
    first = merge_volumes(list(batch))
    second = merge_volumes(list(batch))
    checks.check(
        "同样的输入给出同样的结果(不是靠字典顺序撞出来的)",
        [(v.number, v.title, v.refs) for v in first.volumes]
        == [(v.number, v.title, v.refs) for v in second.volumes],
    )
    checks.check(
        "跨来源那一卷被合掉之后剩 3 行",
        len(first.volumes) == 3,
        f"{[(v.number, v.sources) for v in first.volumes]}",
    )

    # ---- 12. 写库那一段 ----------------------------------------------------------
    persistence_checks(checks)

    print(f"\n{checks.passed} 项通过,{checks.failed} 项失败")
    return 1 if checks.failed else 0


def persistence_checks(checks: "Checks") -> None:
    """写库那一段:合并出来的卷要能落下去,而且**再导一次要认回原来那一行**。

    这一段非用库不可,所以建一个一次性临时库(系统临时目录),不碰 `data/`。
    """
    import tempfile

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models import Base, Edition, Volume, VolumeExternalRef, Work
    from app.queries import add_merged_volumes, load_volume_refs

    scratch = pathlib.Path(tempfile.mkdtemp(prefix="pansy-volumes-"))
    engine = create_engine(f"sqlite:///{(scratch / 'iso.db').as_posix()}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        work = Work(title="安达与岛村")
        session.add(work)
        session.flush()
        edition = Edition(work_id=work.id, media_type="light_novel", title="安达与岛村")
        session.add(edition)
        session.flush()
        edition_id = edition.id

        # 第一次:从 Bangumi 来
        first = merge_volumes(
            [draft(BGM, "66306", number=1, title="安達としまむら (1)", published_on="2016-01-01")]
        )
        added, skipped, reused = add_merged_volumes(session, edition_id, first.volumes)
        session.commit()
        checks.check("第一次导入写了 1 卷", (added, skipped, reused) == (1, 0, 0), f"{(added, skipped, reused)}")

        # 第二次:从 Hikarinagi 来同一个第 1 卷 —— **必须认回那一行**
        second = merge_volumes(
            [draft(HKN, "ln:1:volume:9", number=1, title="安达与岛村 第1卷", cover_url=None)]
        )
        added2, skipped2, reused2 = add_merged_volumes(session, edition_id, second.volumes)
        session.commit()
        checks.check(
            "**从另一个来源再导同一卷:认回原来那一行,不新建**",
            (added2, skipped2, reused2) == (0, 0, 1),
            f"{(added2, skipped2, reused2)}",
        )
        rows = list(session.execute(select(Volume)).scalars())
        checks.check("库里仍然只有 1 卷(没被导成两卷)", len(rows) == 1, f"{len(rows)} 卷")
        refs = load_volume_refs(session, [rows[0].id])
        checks.check(
            "**两个来源都记在那一卷上**",
            sorted(refs[rows[0].id]) == [(BGM, "66306"), (HKN, "ln:1:volume:9")],
            f"{refs}",
        )
        checks.check(
            "先到的说法保留(日期没被后来的覆盖)",
            rows[0].published_on == "2016-01-01",
            f"{rows[0].published_on}",
        )

        # 第三次:同一个外部 id 再导一次 —— 幂等
        added3, _s3, reused3 = add_merged_volumes(session, edition_id, second.volumes)
        session.commit()
        checks.check(
            "同一个外部 id 再导一次是幂等的(不新增)",
            added3 == 0 and reused3 == 1,
            f"{(added3, _s3, reused3)}",
        )

        # 没有外部 id 的卷:按卷号跳过已有的
        third = merge_volumes([draft(BGM, "new-id", number=1, title="第1卷")])
        added4, skipped4, _r4 = add_merged_volumes(session, edition_id, third.volumes)
        session.commit()
        checks.check(
            "同一个卷号、新外部 id:不新建第二行",
            added4 == 0,
            f"新增 {added4} / 跳过 {skipped4}",
        )

        # 无号卷可以并存
        extra = merge_volumes(
            [
                draft(BGM, "up", number=None, title="上"),
                draft(BGM, "down", number=None, title="下"),
            ]
        )
        added5, _s5, _r5 = add_merged_volumes(session, edition_id, extra.volumes)
        session.commit()
        checks.check("**无号卷各占一行**(上/下并存是对的)", added5 == 2, f"新增 {added5}")

        total = len(list(session.execute(select(Volume)).scalars()))
        ref_count = len(list(session.execute(select(VolumeExternalRef)).scalars()))
        checks.check(
            "总数对得上:1 + 上 + 下 = 3 卷",
            total == 3,
            f"{total} 卷 / {ref_count} 条外部对应",
        )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
