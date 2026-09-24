r"""Add objective, edition-owned archive fields and volume bibliographic fields."""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "pansy.db"
BACKUP_DIR = ROOT / "backups"

EDITION_COLUMNS = {
    "ended_on": "VARCHAR", "subtype": "VARCHAR", "region": "VARCHAR", "language": "VARCHAR",
    "catalog_code": "VARCHAR", "homepage": "VARCHAR", "engine": "VARCHAR", "audience": "VARCHAR",
    "reading_mode": "VARCHAR", "content_notice": "VARCHAR",
    "platforms": "TEXT NOT NULL DEFAULT '[]'", "organizations": "TEXT NOT NULL DEFAULT '[]'",
    "official_links": "TEXT NOT NULL DEFAULT '[]'",
}
VOLUME_COLUMNS = {
    "catalog_code": "VARCHAR", "page_count": "INTEGER", "volume_type": "VARCHAR",
}


def main() -> int:
    if not DATABASE.exists():
        print(f"找不到 {DATABASE}")
        return 1
    connection = sqlite3.connect(DATABASE)
    pending = []
    for table, wanted in (("edition", EDITION_COLUMNS), ("volume", VOLUME_COLUMNS)):
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        pending.extend((table, name, sql_type) for name, sql_type in wanted.items() if name not in existing)
    if not pending:
        print("版本与分卷档案字段已经齐全,这次迁移不做改动。")
        connection.close()
        return 0

    target = BACKUP_DIR / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target.mkdir(parents=True, exist_ok=True)
    written = target / "pansy.db"
    copy = sqlite3.connect(written)
    with copy:
        connection.backup(copy)
    copy.close()

    connection.execute("BEGIN")
    try:
        for table, name, sql_type in pending:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
        broken = connection.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise RuntimeError(f"外键检查失败:{broken}")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        connection.close()
        raise
    connection.close()
    print(f"已补齐 {len(pending)} 个档案字段;备份在 {written.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
