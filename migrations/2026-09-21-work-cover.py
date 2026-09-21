r"""作品总标题也有自己的封面:三列 `work.cover_path / cover_width / cover_height`,都可空。
跑一次,在项目根目录:`.\.venv\Scripts\python migrations\2026-09-21-work-cover.py`
宽高存的是原图尺寸,由 `app/covers.py` 传图时从文件头读出来(与件、卷同一个理由:页面在图片到达之前就能把形状占住)。
没有历史数据要回填:总标题本来没有图,加完每条都是空;空的时候照旧沿用它第一件的封面
(`app/api/schemas.py` 的 `work_out`),所以今天看到的样子一张都不会变。撤销:删掉三列。备份写到 `backups/<时间戳>/`,不进 `data/`。
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "pansy.db"
BACKUP_DIR = ROOT / "backups"

#: 加哪三列。顺序有意义:打印与说明都按这个顺序说。
COLUMNS = (
    ("cover_path", "TEXT"),
    ("cover_width", "INTEGER"),
    ("cover_height", "INTEGER"),
)


def backup() -> Path:
    """动手前留一份副本,用 SQLite 自己的备份接口(直接拷文件可能拷到写了一半的状态)。"""
    target = BACKUP_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    target.mkdir(parents=True, exist_ok=True)
    written = target / "pansy.db"

    source = sqlite3.connect(DATABASE)
    copy = sqlite3.connect(written)
    with copy:
        source.backup(copy)
    copy.close()
    source.close()
    return written


def main() -> int:
    if not DATABASE.exists():
        print("找不到 %s" % DATABASE)
        return 1

    connection = sqlite3.connect(DATABASE)
    columns = [row[1] for row in connection.execute("PRAGMA table_info(work)")]

    if all(name in columns for name, _kind in COLUMNS):
        print("work 已经有 %s,这次迁移应该已经跑过。" % "、".join(n for n, _ in COLUMNS))
        connection.close()
        return 1

    print("=" * 72)
    print("做之前")
    print("=" * 72)
    works = connection.execute("SELECT COUNT(*) FROM work").fetchone()[0]
    print("  work %d 列,一共 %d 部作品" % (len(columns), works))
    print("      %s" % "、".join("%s %s" % (name, kind) for name, kind in COLUMNS))
    print("  没有历史数据要回填:总标题本来没有图,读取那一侧仍沿用第一件的封面。")

    written = backup()
    print("  备份写到 %s" % written.relative_to(ROOT))

    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute("BEGIN")
    try:
        for name, kind in COLUMNS:
            connection.execute("ALTER TABLE work ADD COLUMN %s %s" % (name, kind))

        broken = connection.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise RuntimeError("外键检查失败: %s" % broken)

        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.close()
        print("回滚了,数据库没变。备份在 %s" % written.relative_to(ROOT))
        raise

    connection.execute("PRAGMA foreign_keys=ON")

    print("=" * 72)
    print("做完之后")
    print("=" * 72)
    after = [row[1] for row in connection.execute("PRAGMA table_info(work)")]
    print("  work 现在是 %d 列:%s" % (len(after), ", ".join(after)))
    filled = connection.execute(
        "SELECT COUNT(*) FROM work WHERE cover_path IS NOT NULL"
    ).fetchone()[0]
    print("  新加的那三列现在 %d 条有值(应当是 0,等页面上传一张)" % filled)
    print("  外键检查: %s" % (connection.execute("PRAGMA foreign_key_check").fetchall() or "无错误"))
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
