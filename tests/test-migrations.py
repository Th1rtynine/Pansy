"""迁移脚本建出来的表,与模型 `create_all` 建出来的表是不是同一张。

**为什么值得单独考**:同一个仓库里有两条建表的路 —— 启动时 `db.init_db()` 的 `create_all()`,以及
`migrations/` 下那些脚本。它们必须得出**同一张表**:拿到新库的人走第一条,拿着旧库的人走第二条,
两条要是岔开,同一个版本在不同机器上就是两个形状,而这种事只会在很久以后以别的样子冒出来。

比的是**行为**不是 SQL 文本:列名与类型比一比,然后真写几条进去,看唯一约束与删除行为是不是一样。
(不比 `sqlite_master` 里的原文:列级 `REFERENCES` 与表级 `FOREIGN KEY(...)` 写法不同但意思一样,
而把「写法」当成「意思」去比,报出来的都是假问题。)

用法:`python tests/test-migrations.py`。用一次性临时库,不碰 `data/`。
"""

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import sqlite3
import sys
import tempfile

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, inspect  # noqa: E402

from app.models import Base  # noqa: E402

REAL_DATABASE = PROJECT_ROOT / "data" / "pansy.db"
MIGRATIONS = PROJECT_ROOT / "migrations"

#: 这个仓库里每一张新建的表都要有一条对应的迁移脚本。少一条就说明「拿着旧库的人升不上来」。
EXPECTED = {
    "work_relation": "2026-09-22-work-relation.py",
    "volume_external_ref": "2026-09-22-volume-external-ref.py",
    "work_external_ref": "2026-09-23-work-external-ref.py",
}

EDITION_COLUMN_MIGRATION = "2026-09-23-edition-local-path.py"


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


def load_migration(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), MIGRATIONS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def columns_of(path: pathlib.Path, table: str) -> dict[str, str]:
    """列名 → 类型。**不比可空**:SQLite 把 `INTEGER PRIMARY KEY` 报成可空,而那与模型写法无关。"""
    found = inspect(create_engine(f"sqlite:///{path.as_posix()}")).get_columns(table)
    return {column["name"]: str(column["type"]) for column in found}


def fingerprint(path: pathlib.Path) -> str:
    """一份文件的指纹:没有就是 `不存在`,有就是「字节数 + 内容哈希」。拿它证明「没被碰过」。"""
    if not path.is_file():
        return "不存在"
    import hashlib

    raw = path.read_bytes()
    return f"{len(raw)}:{hashlib.sha256(raw).hexdigest()[:16]}"


def con(path: pathlib.Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def seed(connection: sqlite3.Connection) -> tuple[int, int]:
    connection.execute("INSERT INTO work (title) VALUES ('甲')")
    connection.execute("INSERT INTO work (title) VALUES ('乙')")
    first = connection.execute("SELECT id FROM work WHERE title='甲'").fetchone()[0]
    second = connection.execute("SELECT id FROM work WHERE title='乙'").fetchone()[0]
    return first, second


def behaviour(path: pathlib.Path, table: str) -> dict:
    """真写几条进去,看四件事:能写、重复被拒、反方向算另一条、删父记录时跟着删。

    **每张表各写各的**:`work_relation` 的父是两部作品、`volume_external_ref` 的父是一卷 ——
    用同一段 SQL 套两张表只会两边都错。
    """
    connection = con(path)
    result: dict = {}
    try:
        if table == "work_relation":
            first, second = seed(connection)
            connection.execute(
                "INSERT INTO work_relation (from_work_id, to_work_id, relation_type, source)"
                " VALUES (?, ?, 'side_story', 'bangumi')",
                (first, second),
            )
            connection.commit()
            result["wrote"] = connection.execute("SELECT COUNT(*) FROM work_relation").fetchone()[0]

            # 同一条再写一遍:唯一约束该拦下来。
            try:
                connection.execute(
                    "INSERT INTO work_relation (from_work_id, to_work_id, relation_type, source)"
                    " VALUES (?, ?, 'side_story', 'bangumi')",
                    (first, second),
                )
                connection.commit()
                result["duplicate_rejected"] = False
            except sqlite3.IntegrityError:
                result["duplicate_rejected"] = True

            # **反方向是另一条**:这正是这张表存在的理由(无向对子放不下方向)。
            connection.execute(
                "INSERT INTO work_relation (from_work_id, to_work_id, relation_type, source)"
                " VALUES (?, ?, 'side_story', 'bangumi')",
                (second, first),
            )
            connection.commit()
            result["reverse_allowed"] = (
                connection.execute("SELECT COUNT(*) FROM work_relation").fetchone()[0] == 2
            )

            # 删掉一部作品,指向它的关系该跟着走。
            connection.execute("DELETE FROM work WHERE id=?", (second,))
            connection.commit()
            result["cascaded"] = connection.execute("SELECT COUNT(*) FROM work_relation").fetchone()[0]
        elif table == "volume_external_ref":
            # volume_external_ref:同一站上的同一条只许记一次,而且**不做方向那一套**
            # (它没有方向的余地),所以这里只验「能写 / 重复被拒 / 父没了跟着走」。
            volume_id = seed_volume(connection)
            external_id = f"migration-probe-volume-{volume_id}"
            before = connection.execute("SELECT COUNT(*) FROM volume_external_ref").fetchone()[0]
            connection.execute(
                "INSERT INTO volume_external_ref (volume_id, source, external_id, title)"
                " VALUES (?, 'bangumi', ?, '迁移测试卷')",
                (volume_id, external_id),
            )
            connection.commit()
            result["wrote"] = connection.execute(
                "SELECT COUNT(*) FROM volume_external_ref"
            ).fetchone()[0] - before

            try:
                # 换一卷、但同一个 (来源, 外部 id):也该被拦 —— 判重精确到「哪个站上的哪一条」。
                other = seed_volume(connection, number=2.0)
                connection.execute(
                    "INSERT INTO volume_external_ref (volume_id, source, external_id, title)"
                    " VALUES (?, 'bangumi', ?, '重复')",
                    (other, external_id),
                )
                connection.commit()
                result["duplicate_rejected"] = False
            except sqlite3.IntegrityError:
                result["duplicate_rejected"] = True

            # 不同来源的同一个 id 不算重复。
            connection.execute(
                "INSERT INTO volume_external_ref (volume_id, source, external_id, title)"
                " VALUES (?, 'hikarinagi', ?, '同号不同站')",
                (volume_id, external_id),
            )
            connection.commit()
            result["reverse_allowed"] = (
                connection.execute("SELECT COUNT(*) FROM volume_external_ref").fetchone()[0] - before == 2
            )

            connection.execute("DELETE FROM volume WHERE id=?", (volume_id,))
            connection.commit()
            result["cascaded"] = connection.execute(
                "SELECT COUNT(*) FROM volume_external_ref"
            ).fetchone()[0] - before
        else:
            # work_external_ref:同一来源原作只能归到一部 Work；不同来源的同号各自成立。
            first, second = seed(connection)
            connection.execute(
                "INSERT INTO work_external_ref (work_id, source, external_id, title)"
                " VALUES (?, 'bangumi', '81467', '安達としまむら')",
                (first,),
            )
            connection.commit()
            result["wrote"] = connection.execute(
                "SELECT COUNT(*) FROM work_external_ref"
            ).fetchone()[0]

            try:
                connection.execute(
                    "INSERT INTO work_external_ref (work_id, source, external_id, title)"
                    " VALUES (?, 'bangumi', '81467', '重复归属')",
                    (second,),
                )
                connection.commit()
                result["duplicate_rejected"] = False
            except sqlite3.IntegrityError:
                result["duplicate_rejected"] = True

            connection.execute(
                "INSERT INTO work_external_ref (work_id, source, external_id, title)"
                " VALUES (?, 'hikarinagi', '81467', '同号不同站')",
                (first,),
            )
            connection.commit()
            result["reverse_allowed"] = (
                connection.execute("SELECT COUNT(*) FROM work_external_ref").fetchone()[0] == 2
            )

            connection.execute("DELETE FROM work WHERE id=?", (first,))
            connection.commit()
            result["cascaded"] = connection.execute(
                "SELECT COUNT(*) FROM work_external_ref"
            ).fetchone()[0]
    finally:
        connection.close()
    return result


def seed_volume(connection: sqlite3.Connection, number: float | None = 1.0) -> int:
    """造一卷出来给它挂外部对应(连带它需要的作品与件)。"""
    first, _second = seed(connection)
    connection.execute(
        "INSERT INTO edition (work_id, media_type, title) VALUES (?, 'light_novel', '安达与岛村')",
        (first,),
    )
    edition_id = connection.execute("SELECT MAX(id) FROM edition").fetchone()[0]
    connection.execute(
        "INSERT INTO volume (edition_id, volume_number, title) VALUES (?, ?, '某卷')",
        (edition_id, number),
    )
    return connection.execute("SELECT MAX(id) FROM volume").fetchone()[0]


def main() -> int:
    checks = Checks()
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="pansy-migrations-"))
    # **先记下真实库的指纹**:整段跑完再比一次 —— 这一套的特权就是「不碰真实库」,那就得真验,
    # 而不是嘴上说一句。先前那一版写的是 `... or True`,那种断言永远绿,等于没写。
    before = fingerprint(REAL_DATABASE)

    # A:迁移脚本建出来的(跑在**真实库的副本**上 —— 真实库一个字节都不动)
    by_migration = scratch / "by-migration.db"
    if REAL_DATABASE.is_file():
        shutil.copy2(REAL_DATABASE, by_migration)
    else:
        # 还没有库(刚克隆下来):先按模型建一份,再当成「旧库」交给迁移 —— 迁移只建缺的表。
        Base.metadata.create_all(create_engine(f"sqlite:///{by_migration.as_posix()}"))
        connection = con(by_migration)
        connection.execute("DROP TABLE IF EXISTS work_relation")
        connection.commit()
        connection.close()

    for table, script in EXPECTED.items():
        path = MIGRATIONS / script
        checks.check(f"{table} 有对应的迁移脚本", path.is_file(), f"{script}")
        if not path.is_file():
            continue
        migration = load_migration(script)
        migration.DATABASE = by_migration
        migration.BACKUP_DIR = scratch / "backups"
        checks.check(
            f"{script} 跑得通",
            migration.main() == 0,
        )
        # 幂等:再跑一次不该出错、也不该再留一份备份。
        checks.check(f"{script} 再跑一次是幂等的", migration.main() == 0)

    # 加列迁移单独从一张旧形状的 edition 表起步，证明它不依赖真实库恰好已经升级。
    legacy_column = scratch / "legacy-edition.db"
    legacy = con(legacy_column)
    legacy.execute("CREATE TABLE work (id INTEGER PRIMARY KEY, title VARCHAR NOT NULL)")
    legacy.execute(
        "CREATE TABLE edition (id INTEGER PRIMARY KEY, work_id INTEGER NOT NULL,"
        " media_type VARCHAR NOT NULL, title VARCHAR)"
    )
    legacy.execute("INSERT INTO work (title) VALUES ('旧作品')")
    legacy.execute("INSERT INTO edition (work_id, media_type, title) VALUES (1, 'manga', '旧版本')")
    legacy.commit()
    legacy.close()
    column_migration = load_migration(EDITION_COLUMN_MIGRATION)
    column_migration.DATABASE = legacy_column
    column_migration.BACKUP_DIR = scratch / "column-backups"
    checks.check(f"{EDITION_COLUMN_MIGRATION} 跑得通", column_migration.main() == 0)
    checks.check(f"{EDITION_COLUMN_MIGRATION} 再跑一次是幂等的", column_migration.main() == 0)
    legacy = con(legacy_column)
    checks.check(
        "旧 edition 表补上 local_path 且原数据保留",
        "local_path" in {row[1] for row in legacy.execute("PRAGMA table_info(edition)")}
        and legacy.execute("SELECT title FROM edition WHERE id=1").fetchone()[0] == "旧版本",
    )
    legacy.close()

    # B:模型 create_all 建出来的
    by_model = scratch / "by-model.db"
    Base.metadata.create_all(create_engine(f"sqlite:///{by_model.as_posix()}"))

    for table in EXPECTED:
        checks.check(
            f"{table}:两条路建出来的列与类型一致",
            columns_of(by_migration, table) == columns_of(by_model, table),
            f"迁移={columns_of(by_migration, table)} 模型={columns_of(by_model, table)}",
        )
        left = behaviour(by_migration, table)
        right = behaviour(by_model, table)
        checks.check(
            f"{table}:两条路的行为一致(唯一约束、方向、级联删除)",
            left == right,
            f"迁移={left} 模型={right}",
        )

    # 行为本身也要对,不能只是「两边一样地错」。
    seen = behaviour(by_model, "work_relation")
    checks.check("能写进去", seen.get("wrote") == 1, f"{seen}")
    checks.check("同一条重复写被唯一约束拦下", seen.get("duplicate_rejected") is True)
    checks.check("**反方向算另一条**(方向是真的)", seen.get("reverse_allowed") is True)
    checks.check("删作品时关系跟着删(级联)", seen.get("cascaded") == 0, f"剩 {seen.get('cascaded')} 条")

    seen_volume = behaviour(by_model, "volume_external_ref")
    checks.check("卷的外部对应能写进去", seen_volume.get("wrote") == 1, f"{seen_volume}")
    checks.check(
        "同一个站上的同一条卷只许记一次",
        seen_volume.get("duplicate_rejected") is True,
    )
    checks.check(
        "**不同来源的同号卷各算一条**",
        seen_volume.get("reverse_allowed") is True,
    )
    checks.check("删卷时它的外部对应跟着删", seen_volume.get("cascaded") == 0)

    seen_work_ref = behaviour(by_model, "work_external_ref")
    checks.check("统一作品的原作锚点能写进去", seen_work_ref.get("wrote") == 1, f"{seen_work_ref}")
    checks.check(
        "同一个来源原作只许归到一部作品",
        seen_work_ref.get("duplicate_rejected") is True,
    )
    checks.check(
        "不同来源的同号原作各算一条",
        seen_work_ref.get("reverse_allowed") is True,
    )
    checks.check("删作品时原作锚点跟着删", seen_work_ref.get("cascaded") == 0)

    # 旧表一个字都没动。
    old = con(by_migration)
    checks.check(
        "旧的 edition_relation 原样留着,没被搬也没被删",
        old.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='edition_relation'"
        ).fetchone()[0]
        == 1,
    )
    old.close()

    checks.check(
        "**真实库一个字节都没动**",
        fingerprint(REAL_DATABASE) == before,
        f"跑之前 {before} / 跑之后 {fingerprint(REAL_DATABASE)}",
    )

    print(f"\n{checks.passed} 项通过,{checks.failed} 项失败")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
