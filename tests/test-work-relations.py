"""作品关系的读写:幂等、方向、以及两头都查得到。

**为什么单独一个文件**:这一层的三件事都容易写错,而且错了不会当场报错 —— 重复导入会悄悄多出一行、
方向被排序之后「谁是番外篇」就再也说不清、只查一侧则「这一部有哪些衍生作」少一半。三条都得真跑一遍。

用一次性临时库,不碰 `data/`。用法:`python tests/test-work-relations.py`。
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.models import Base, Work  # noqa: E402
from app.queries import (  # noqa: E402
    delete_work_relation,
    load_work_relations,
    remember_work_relation,
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


def main() -> int:
    checks = Checks()
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="pansy-relations-"))
    engine = create_engine(f"sqlite:///{(scratch / 'iso.db').as_posix()}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        main_work = Work(title="安达与岛村")
        extra = Work(title="安达与岛村99.9")
        same_setting = Work(title="我的初恋对象与人接吻了")
        session.add_all([main_work, extra, same_setting])
        session.flush()
        main_id, extra_id, setting_id = main_work.id, extra.id, same_setting.id

        # ---- 幂等:同一个来源、同一对、同一种关系,写两遍只有一行 --------------------
        remember_work_relation(
            session,
            from_work_id=extra_id,
            to_work_id=main_id,
            relation_type="side_story",
            source="bangumi",
            raw_relation="番外篇",
            confidence="high",
        )
        remember_work_relation(
            session,
            from_work_id=extra_id,
            to_work_id=main_id,
            relation_type="side_story",
            source="bangumi",
            raw_relation="番外篇",
            confidence="high",
        )
        session.flush()
        rows = load_work_relations(session, main_id)
        checks.check(
            "**重复导入只留一行**(幂等)",
            len(rows) == 1,
            f"{len(rows)} 行",
        )

        # ---- 方向不被归一:反过来是另一条 ------------------------------------------
        remember_work_relation(
            session,
            from_work_id=main_id,
            to_work_id=extra_id,
            relation_type="side_story",
            source="bangumi",
            raw_relation="番外篇",
            confidence="high",
        )
        session.flush()
        checks.check(
            "**反方向是另一条**(谁是谁的番外篇分得清)",
            len(load_work_relations(session, main_id)) == 2,
            f"{len(load_work_relations(session, main_id))} 行",
        )
        directed = [
            (relation.from_work_id, relation.to_work_id)
            for relation, _f, _t in load_work_relations(session, main_id)
        ]
        checks.check(
            "两个方向都在,而且没有哪条被排序过",
            (extra_id, main_id) in directed and (main_id, extra_id) in directed,
            f"{directed}",
        )

        # ---- 两头都查得到 -----------------------------------------------------------
        # 问「衍生作」那一部:它自己那一侧也应当看得到这条关系。
        from_extra = load_work_relations(session, extra_id)
        checks.check(
            "从任一头查都能看到同一条关系",
            len(from_extra) == 2,
            f"{len(from_extra)} 行",
        )

        # ---- 不同来源 / 不同关系各算一条 --------------------------------------------
        remember_work_relation(
            session,
            from_work_id=main_id,
            to_work_id=setting_id,
            relation_type="same_setting",
            source="bangumi",
            raw_relation="相同世界观",
            confidence="high",
        )
        remember_work_relation(
            session,
            from_work_id=main_id,
            to_work_id=setting_id,
            relation_type="same_setting",
            source="manual",
            raw_relation=None,
            confidence="high",
        )
        session.flush()
        setting_rows = load_work_relations(session, setting_id)
        checks.check(
            "同一种关系不同来源各算一条(`manual` 不该被自动同步顶掉)",
            len(setting_rows) == 2,
            f"{len(setting_rows)} 行",
        )

        # ---- 补写时更新原话,但不多建行 ----------------------------------------------
        remember_work_relation(
            session,
            from_work_id=main_id,
            to_work_id=setting_id,
            relation_type="same_setting",
            source="bangumi",
            raw_relation="同世界观(改过)",
            confidence="high",
        )
        session.flush()
        checks.check(
            "再记一次同一个来源:更新原话,不新增行",
            len(load_work_relations(session, setting_id)) == 2,
            f"{len(load_work_relations(session, setting_id))} 行",
        )

        # ---- 删一条只删那一条 --------------------------------------------------------
        first = load_work_relations(session, main_id)[0][0]
        checks.check("删一条关系返回真", delete_work_relation(session, first.id) is True)
        session.flush()
        checks.check(
            "**只删掉那一条**,别的都还在",
            len(load_work_relations(session, main_id)) == 3,
            f"{len(load_work_relations(session, main_id))} 行",
        )
        checks.check(
            "两部作品都还在(删关系不是删作品)",
            session.get(Work, extra_id) is not None and session.get(Work, main_id) is not None,
        )

        # ---- 删作品时关系跟着走 ------------------------------------------------------
        session.delete(extra)
        session.flush()
        remaining = {
            (relation.from_work_id, relation.to_work_id)
            for relation, _f, _t in load_work_relations(session, main_id)
        }
        checks.check(
            "删掉一部作品,牵到它的关系跟着删",
            (extra_id, main_id) not in remaining and (main_id, extra_id) not in remaining,
            f"{sorted(remaining)}",
        )

    print(f"\n{checks.passed} 项通过,{checks.failed} 项失败")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
