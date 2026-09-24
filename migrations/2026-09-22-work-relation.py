r"""作品与作品之间**有方向**的关系:新表 `work_relation`。

跑一次,在项目根目录:`.\.venv\Scripts\python migrations\2026-09-22-work-relation.py`

**为什么另起一张表**:`edition_relation` 存的是无向对子(`edition_a_id` 永远是小的那个),它自己就说了
「小 id 在前的对子放不下方向」。而「当前作品是目标作品的番外篇」与反过来是两件事,必须分开记。

**旧数据一条都不动,也不猜方向**:`edition_relation` 原样留着。它记的是「这两个载体相连」,从中推不出
谁是前传 —— 凭空填一个方向比留空更糟。要搬由人一条条来「关联作品」那一页做。

**已有的库怎么建出这张表**:启动时 `db.init_db()` 的 `create_all()` 会**只建缺的表**,所以这张表
其实不跑这个脚本也会出现。这个脚本存在的理由是 `data/pansy.db` 里那些**已经在跑、还没重启**的库:它
把建表语句显式跑一遍,并在动手前留一份副本。两边都幂等,先跑谁都不出错。

撤销:删掉 `work_relation` 这张表(没有任何别的表引用它)。
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "pansy.db"
BACKUP_DIR = ROOT / "backups"

TABLE = "work_relation"

#: 建表语句。与 `app/models/work_relation.py` **逐字对应** —— 两边不一致时,`create_all` 建出来的与
#: 这里建出来的就是两张不同的表,而这种偏差只会在很久以后以别的样子冒出来。`scripts/check.py` 会核对外键。
CREATE = """
CREATE TABLE IF NOT EXISTS work_relation (
    id            INTEGER PRIMARY KEY,
    from_work_id  INTEGER NOT NULL REFERENCES work(id) ON DELETE CASCADE,
    to_work_id    INTEGER NOT NULL REFERENCES work(id) ON DELETE CASCADE,
    relation_type VARCHAR NOT NULL DEFAULT 'unknown',
    source        VARCHAR NOT NULL DEFAULT '',
    raw_relation  VARCHAR,
    confidence    VARCHAR NOT NULL DEFAULT 'unknown',
    created_at    VARCHAR,
    weight        FLOAT,
    CONSTRAINT uq_work_relation_pair UNIQUE (from_work_id, to_work_id, relation_type, source)
)
"""

#: 查外键时报出来的那几条,应当一条不少。
EXPECTED_FOREIGN_KEYS = {"from_work_id", "to_work_id"}


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


def shown(path: Path) -> str:
    """打出来给人看的路径。**能相对就相对,不能就照原样** —— 备份目录不在仓库里时(测试会把整个迁移
    指到临时目录去跑),`relative_to` 会抛 `ValueError`,而一个只在「路径恰好落在仓库里」时才不炸的
    打印语句,是那种平时看不出、换台机器就冒出来的毛病。
    """
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    if not DATABASE.exists():
        print("找不到 %s" % DATABASE)
        return 1

    connection = sqlite3.connect(DATABASE)
    tables = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )]

    if TABLE in tables:
        print("%s 已经有了,这次迁移跑过了(什么都不做,也不留备份)。" % TABLE)
        connection.close()
        return 0

    print("=" * 72)
    print("做之前")
    print("=" * 72)
    print("  现有 %d 张表" % len(tables))
    works = connection.execute("SELECT COUNT(*) FROM work").fetchone()[0]
    print("  一共 %d 部作品,它们之间的关系现在一条都没记" % works)
    old = connection.execute("SELECT COUNT(*) FROM edition_relation").fetchone()[0]
    print("  edition_relation 里那 %d 条无向关系**原样留着**,不搬也不猜方向。" % old)

    written = backup()
    print("  备份写到 %s" % shown(written))

    connection.execute("BEGIN")
    try:
        connection.execute(CREATE)

        broken = connection.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise RuntimeError("外键检查失败: %s" % broken)

        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        connection.close()
        print("回滚了,数据库没变。备份在 %s" % shown(written))
        raise

    print("=" * 72)
    print("做完之后")
    print("=" * 72)
    after = [row[1] for row in connection.execute("PRAGMA table_info(%s)" % TABLE)]
    print("  %s 现在是 %d 列:%s" % (TABLE, len(after), ", ".join(after)))
    keys = [row[3] for row in connection.execute("PRAGMA foreign_key_list(%s)" % TABLE)]
    print("  外键:%s" % "、".join(keys))
    if set(keys) != EXPECTED_FOREIGN_KEYS:
        print("  **外键与预期不符**:期望 %s" % "、".join(sorted(EXPECTED_FOREIGN_KEYS)))
    print("  行数 %d(新表,应当是 0)" % connection.execute(
        "SELECT COUNT(*) FROM %s" % TABLE
    ).fetchone()[0])
    print("  外键检查: %s" % (connection.execute("PRAGMA foreign_key_check").fetchall() or "无错误"))
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
