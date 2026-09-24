r"""给统一作品增加稳定的外部原作锚点 `work_external_ref`。

运行:`.\.venv\Scripts\python migrations\2026-09-23-work-external-ref.py`
启动时 `create_all()` 也会建立缺失的新表；此脚本用于显式迁移并在变更前备份现有数据库。
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "pansy.db"
BACKUP_DIR = ROOT / "backups"
TABLE = "work_external_ref"

CREATE = """
CREATE TABLE IF NOT EXISTS work_external_ref (
    id          INTEGER PRIMARY KEY,
    work_id     INTEGER NOT NULL REFERENCES work(id) ON DELETE CASCADE,
    source      VARCHAR NOT NULL,
    external_id VARCHAR NOT NULL,
    title       VARCHAR,
    CONSTRAINT uq_work_external_ref_source_entry UNIQUE (source, external_id)
)
"""


def main() -> int:
    if not DATABASE.exists():
        print(f"找不到 {DATABASE}")
        return 1
    connection = sqlite3.connect(DATABASE)
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
    ).fetchone()
    if exists:
        print(f"{TABLE} 已经有了,这次迁移不做改动。")
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
        connection.execute(CREATE)
        broken = connection.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise RuntimeError(f"外键检查失败:{broken}")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        connection.close()
        raise
    connection.close()
    try:
        shown = written.relative_to(ROOT)
    except ValueError:
        shown = written
    print(f"已建立 {TABLE};备份在 {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
