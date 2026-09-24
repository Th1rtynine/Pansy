r"""给每个具体版本增加本机资源入口 `edition.local_path`。

运行:`.\.venv\Scripts\python migrations\2026-09-23-edition-local-path.py`
SQLite 的 `create_all()` 不会给旧表补列，所以已有数据库必须显式迁移；修改前会先做完整备份。
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "pansy.db"
BACKUP_DIR = ROOT / "backups"
COLUMN = "local_path"


def main() -> int:
    if not DATABASE.exists():
        print(f"找不到 {DATABASE}")
        return 1
    connection = sqlite3.connect(DATABASE)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(edition)")}
    if COLUMN in columns:
        print(f"edition.{COLUMN} 已经有了,这次迁移不做改动。")
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
        connection.execute("ALTER TABLE edition ADD COLUMN local_path VARCHAR")
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
    print(f"已建立 edition.{COLUMN};备份在 {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
