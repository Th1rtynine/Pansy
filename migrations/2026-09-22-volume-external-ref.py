r"""一卷在外部站点上是哪一条:新表 `volume_external_ref`。

跑一次,在项目根目录:`.\.venv\Scripts\python migrations\2026-09-22-volume-external-ref.py`

**为什么要这张表**:同一卷常常在两个站上各有一条(轻小说在 Bangumi 与 Hikarinagi 都有)。合并之后必须
记得「这一行是哪几条合出来的」,否则下一次导入认不出它,又会建出第二行。

**为什么不泛化 `external_ref`**:那一张的 `edition_id` 是 NOT NULL 的外键,泛化意味着把它变可空、再加一个
「指向哪张表」的判别列,于是每一处读它的地方都要先判一次,而其中绝大多数只想问作品级的对应。

**已有的库**:启动时 `create_all()` 会只建缺的表,所以不跑这个脚本它也会出现。这个脚本是给那些**已经
在跑、还没重启**的库用的:显式建一遍,动手前留副本。两边都幂等。

撤销:删掉 `volume_external_ref`(没有任何别的表引用它)。
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "pansy.db"
BACKUP_DIR = ROOT / "backups"

TABLE = "volume_external_ref"

#: 与 `app/models/volume_external_ref.py` 逐字对应。**`server_default` 那几处要跟着模型走** ——
#: 只在一侧写默认值,同一张表在两条建表路径上就会有两种行为(上一张表就是这么踩到的)。
CREATE = """
CREATE TABLE IF NOT EXISTS volume_external_ref (
    id          INTEGER PRIMARY KEY,
    volume_id   INTEGER NOT NULL REFERENCES volume(id) ON DELETE CASCADE,
    source      VARCHAR NOT NULL,
    external_id VARCHAR NOT NULL,
    url         VARCHAR,
    title       VARCHAR,
    fetched_at  VARCHAR,
    CONSTRAINT uq_volume_external_ref_source_entry UNIQUE (source, external_id)
)
"""

EXPECTED_FOREIGN_KEYS = {"volume_id"}


def shown(path: Path) -> str:
    """打出来给人看的路径。能相对就相对,不能就照原样(见 work-relation 那个迁移里的同一个函数)。"""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def backup() -> Path:
    """动手前留一份副本,用 SQLite 自己的备份接口。"""
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
    volumes = connection.execute("SELECT COUNT(*) FROM volume").fetchone()[0]
    print("  一共 %d 卷,它们现在都没记住自己在别的站上是哪一条" % volumes)

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
    keys = {row[3] for row in connection.execute("PRAGMA foreign_key_list(%s)" % TABLE)}
    print("  外键:%s" % "、".join(sorted(keys)))
    if keys != EXPECTED_FOREIGN_KEYS:
        print("  **外键与预期不符**:期望 %s" % "、".join(sorted(EXPECTED_FOREIGN_KEYS)))
    print("  行数 %d(新表,应当是 0)" % connection.execute(
        "SELECT COUNT(*) FROM %s" % TABLE
    ).fetchone()[0])
    print("  外键检查: %s" % (connection.execute("PRAGMA foreign_key_check").fetchall() or "无错误"))
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
