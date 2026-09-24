"""家族预览接上本地库之后的两件事:谁已经在库里、以及批量查询不按条数发请求。

**为什么要单独一个文件**:这两件事都需要一个**真的库** —— 而真实的那个库是用户的,不能拿它试。
所以这里建一个一次性临时库(在系统临时目录下),自己建表、自己写几条,跑完就完了。

**它不碰 `data/`**:引擎是照临时路径直接建的(不用 `app.db.create_db_engine`,那个读的是真配置)。
顺手也就没有网络:数据全来自夹具(`tests/fixtures/bangumi-family.json`)。

用法:`python tests/test-family-claims.py`。
"""

from __future__ import annotations

import importlib
import pathlib
import sys
import tempfile
from contextlib import contextmanager
from unittest import mock

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.models import Base, Edition, ExternalRef, Work  # noqa: E402


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
    sources = importlib.import_module("app.api.sources")

    scratch = pathlib.Path(tempfile.mkdtemp(prefix="pansy-claims-"))
    engine = create_engine(f"sqlite:///{(scratch / 'iso.db').as_posix()}")
    Base.metadata.create_all(engine)

    # 库里先放两条:**一条是这一族里的动画**(282372),一条是同名的另一部作品(不能张冠李戴)。
    with Session(engine) as session:
        work = Work(title="已经存在的总标题")
        session.add(work)
        session.flush()
        edition = Edition(work_id=work.id, media_type="anime", title="已经存在的动画版")
        session.add(edition)
        session.flush()
        edition_id = edition.id
        session.add(
            ExternalRef(edition_id=edition_id, source="bangumi", external_id="282372", title="安达与岛村")
        )
        # 同一个 id 换一个来源:不该被当成「同一条」—— 判重看的是 (来源, 外部 id)。
        other_work = Work(title="另一部")
        session.add(other_work)
        session.flush()
        other = Edition(work_id=other_work.id, media_type="manga", title="另一件")
        session.add(other)
        session.flush()
        session.add(ExternalRef(edition_id=other.id, source="vndb", external_id="282372", title="同号不同站"))
        session.commit()

    @contextmanager
    def isolated():
        with Session(engine) as session:
            yield session

    from app.api.schemas import FamilyPreviewIn

    with mock.patch.object(sources, "session_scope", isolated):
        preview = sources.family_preview(
            FamilyPreviewIn(source="bangumi", external_id="81467")
        ).model_dump()

    by_id = {member["candidate"]["external_id"]: member for member in preview["editions"]}
    checks.check(
        "本地已有的那一条被标成「已在库里」",
        by_id.get("282372", {}).get("already_in_library") is True,
        f"282372 -> {by_id.get('282372', {}).get('already_in_library')}",
    )
    checks.check(
        "而且说得出它现在是哪一件",
        (by_id.get("282372", {}).get("claimed_by") or {}).get("edition_title") == "已经存在的动画版",
        f"{by_id.get('282372', {}).get('claimed_by')}",
    )
    checks.check(
        "**不是同一来源的同号条目不算「已有」**(判重看 (来源, 外部 id),不看 id 本身)",
        by_id.get("282372", {}).get("claimed_by", {}).get("edition_id") == edition_id,
        "vndb:282372 那条不该认到它头上",
    )
    checks.check(
        "本地没有的那几条照实报「要新建」",
        all(
            by_id[i]["already_in_library"] is False
            for i in ("81467", "283417", "181467")
            if i in by_id
        ),
        f"{[(i, by_id[i]['already_in_library']) for i in by_id]}",
    )

    # ---- 批量查询:一条语句,不按条数发请求 --------------------------------------
    # 这一条是拿真的 SQL 记的:先前写成 `or_(*(and_(...)))`,条数一多就该是几十条 OR,
    # 而这里要的不是「能跑」,是**一次查询**。
    statements: list[str] = []
    from sqlalchemy import event

    @event.listens_for(engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    with mock.patch.object(sources, "session_scope", isolated):
        sources.family_preview(FamilyPreviewIn(source="bangumi", external_id="81467"))

    selects = [s for s in statements if "external_ref" in s and s.strip().lower().startswith("select")]
    event.remove(engine, "before_cursor_execute", record)
    checks.check(
        "**整族的外部 id 只查一次**(不是每条一个请求)",
        len(selects) == 1,
        f"查了 {len(selects)} 次 external_ref",
    )

    # ---- 空表也要能跑 -----------------------------------------------------------
    empty_engine = create_engine(f"sqlite:///{(scratch / 'empty.db').as_posix()}")
    Base.metadata.create_all(empty_engine)

    @contextmanager
    def empty_scope():
        with Session(empty_engine) as session:
            yield session

    with mock.patch.object(sources, "session_scope", empty_scope):
        blank = sources.family_preview(
            FamilyPreviewIn(source="bangumi", external_id="81467")
        ).model_dump()
    checks.check(
        "空库时一个都不标「已有」,而且不报错",
        bool(blank["editions"]) and not any(m["already_in_library"] for m in blank["editions"]),
    )

    # ---- 没人认领的条目直接问 claims 也是 null -----------------------------------
    checks.check(
        "没写进库的外部条目,批量查询回空",
        sources._claims_for([("bangumi", "999999999")]) == {},
    )

    print(f"\n{checks.passed} 项通过,{checks.failed} 项失败")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
