"""Read-only checks for the current database and for the wording on the pages.
Run with: python scripts/check.py. Nothing here writes; safe to run at any time. Most checks
read the database, the rest scan the strings a reader can see and refuse development wording;
`scripts/flow.py` drives the real HTTP interface -- run both before calling a change done.
"""

import ast
from pathlib import Path
import re
import sys

from sqlalchemy import inspect


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.api.schemas import CollectIn  # noqa: E402
from app.api.sources import collect_from_sources  # noqa: E402
from app.config import load_paths  # noqa: E402
from app.db import create_db_engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.sources import SOURCES  # noqa: E402
from app.sources.base import Candidate  # noqa: E402
from app.sources.bangumi import (  # noqa: E402
    _fold_volumes,
    _pick_identity_relation,
    _volume_base,
    guess_media,
)
from app.sources.query import flat, parse, pick_name  # noqa: E402

# 页面上不许出现的说法:这些词说明的是项目怎么做,不是库里有什么。
BANNED_WORDING = (
    "阶段",
    "载体",
    "形态",
    "容器",
    "暂不建立",
    "当前不限类型",
    "不区分方向",
    "以后再",
)


def source_texts() -> list[tuple[str, str]]:
    """(where it came from, the words a reader could end up seeing).

    Templates lose their Jinja comments, Python modules their docstrings.
    """
    found: list[tuple[str, str]] = []

    python_paths = sorted((PROJECT_ROOT / "app" / "api").glob("*.py"))
    python_paths += [PROJECT_ROOT / "app" / name for name in ("fields.py", "listing.py", "rules.py")]

    for path in python_paths:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        docstrings = {
            ast.get_docstring(node, clean=False)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        pieces = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value not in docstrings
        ]
        found.append((str(path.relative_to(PROJECT_ROOT)), "\n".join(pieces)))

    # 界面那一侧。`<script>` 那一段与 HTML 注释读者看不到,整段去掉,留下的就是会画到屏幕上的字。
    for path in sorted((PROJECT_ROOT / "frontend" / "src").rglob("*.vue")):
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.S)
        text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
        found.append((str(path.relative_to(PROJECT_ROOT)), text))

    # TypeScript 里的字是标签(浅色 / 深色 / 跟随系统 这类),注释去掉再交上来。
    for path in sorted((PROJECT_ROOT / "frontend" / "src").rglob("*.ts")):
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
        text = re.sub(r"//[^\n]*", " ", text)
        found.append((str(path.relative_to(PROJECT_ROOT)), text))

    return found


EXPECTED_TABLES = {
    "work",
    "edition_relation",
    "edition",
    "volume",
    "creator",
    "edition_creator",
    "tag",
    "edition_tag",
    # 一条作品在外部站点上是哪一条。新建的表,已有的库启动时由 create_all 自动建出(只建缺的)。
    "external_ref",
}

# (子表, 外键列, 父表, 删掉父记录时该做什么)
# 前五条 CASCADE:子记录不能比父记录活得久;后两条不 CASCADE 是有意的 —— 作者与标签是共用词汇,还在被用时删掉必须失败。关系跟着任一边的载体走。
REFERENCE_RULES = (
    ("edition", "work_id", "work", "CASCADE"),
    ("volume", "edition_id", "edition", "CASCADE"),
    ("edition_creator", "edition_id", "edition", "CASCADE"),
    ("edition_tag", "edition_id", "edition", "CASCADE"),
    ("edition_relation", "edition_a_id", "edition", "CASCADE"),
    ("edition_relation", "edition_b_id", "edition", "CASCADE"),
    ("edition_creator", "creator_id", "creator", "NO ACTION"),
    ("edition_tag", "tag_id", "tag", "NO ACTION"),
    # 外部条目是「这一条作品的注记」,不是共用词汇,跟着作品一起删。
    ("external_ref", "edition_id", "edition", "CASCADE"),
)

# 复合主键就是防重复的那道墙
PRIMARY_KEYS = (
    ("edition_relation", ["edition_a_id", "edition_b_id"]),
    ("edition_creator", ["edition_id", "creator_id", "role"]),
    ("edition_tag", ["edition_id", "tag_id"]),
)

# (表, 列) —— 这一列上要有一个单列唯一索引
UNIQUE_COLUMNS = (("creator", "name"),)

# (表, 列) —— 这几列合起来要有一个唯一索引;tag 按媒体类型分,所以同名标签在不同类型下各有一条。
UNIQUE_COLUMN_GROUPS = (
    ("tag", ("media_type", "name")),
    # 同一个站上的同一条只许记一次 —— 判重就靠这个索引。
    ("external_ref", ("source", "external_id")),
)

# /api 这一层的接口清单。读的是 app.openapi(),不需要服务也不碰库 —— /docs 画的就是这份描述,
# 描述里没有的路径页面上点不到。**两个方向都要对**:少一条说明有东西没挂上,多一条说明露了出去。
EXPECTED_API_ROUTES = {
    ("get", "/api/media-types"),
    ("get", "/api/works"),
    ("post", "/api/works"),
    # 加入作品:一个事务里建出「作品总标题 + 它的若干件作品」。
    ("post", "/api/works/with-editions"),
    ("get", "/api/works/{work_id}"),
    ("put", "/api/works/{work_id}"),
    ("post", "/api/works/{work_id}/cover"),
    ("delete", "/api/works/{work_id}/cover"),
    ("delete", "/api/works/{work_id}"),
    ("post", "/api/works/{work_id}/editions"),
    ("get", "/api/editions"),
    ("get", "/api/editions/{edition_id}"),
    ("put", "/api/editions/{edition_id}"),
    ("delete", "/api/editions/{edition_id}"),
    ("post", "/api/editions/{edition_id}/cover"),
    ("delete", "/api/editions/{edition_id}/cover"),
    ("get", "/api/editions/{edition_id}/volumes"),
    ("post", "/api/editions/{edition_id}/volumes"),
    ("get", "/api/volumes/{volume_id}"),
    ("put", "/api/volumes/{volume_id}"),
    ("delete", "/api/volumes/{volume_id}"),
    ("post", "/api/volumes/{volume_id}/cover"),
    ("delete", "/api/volumes/{volume_id}/cover"),
    ("post", "/api/editions/{edition_id}/relations"),
    ("delete", "/api/editions/{edition_id}/relations/{other_id}"),
    ("get", "/api/editions/{edition_id}/relation-candidates"),
    ("get", "/api/creators"),
    ("get", "/api/creators/{creator_id}"),
    ("put", "/api/creators/{creator_id}"),
    ("get", "/api/tags"),
    ("get", "/api/tags/{tag_id}"),
    ("put", "/api/tags/{tag_id}"),
    # 外部数据源:问它有什么、要候选、要逐字段建议,以及记住对应关系。
    ("get", "/api/sources"),
    ("get", "/api/sources/claims"),
    # 一条系列条目底下的卷:只读,选中后先给人过目,再随作品一起提交。
    ("get", "/api/sources/volumes"),
    ("post", "/api/sources/search"),
    # 一个框收名字或条目 ID:先补全,再拿补全后的名字把每个源搜一遍。
    ("post", "/api/sources/collect"),
    ("post", "/api/sources/resolve"),
    ("post", "/api/sources/identity"),
    ("post", "/api/sources/suggest"),
    ("get", "/api/editions/{edition_id}/source-refs"),
    ("put", "/api/editions/{edition_id}/source-refs"),
    ("delete", "/api/editions/{edition_id}/source-refs/{source}"),
}


# (表, 列) —— 这些列必须存在。自动建表不补列,给老库加过的列要在这里点名:少了它就是一次 500。
EXPECTED_COLUMNS = (("edition", "published_on"),)

# 载体时间的合法写法:2015、2015-04、2015-04-01;缺的那一段不许拿 0 顶上,否则「不知道几月」会变成具体月份。
DATE_SHAPES = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")

TRIMMED_COLUMNS = (("creator", "name"), ("tag", "name"), ("edition_creator", "role"))

# SQLite's one-argument TRIM strips only spaces, so tab/LF/CR/space are spelled out.
BLANKS = " || ".join(("CHAR(9)", "CHAR(10)", "CHAR(13)", "CHAR(32)"))


def foreign_key_rows(connection, table: str) -> list:
    return connection.exec_driver_sql(f"PRAGMA foreign_key_list({table})").fetchall()


def primary_key_columns(connection, table: str) -> list[str]:
    """The primary key columns in key order (PRAGMA table_info's pk field)."""
    rows = connection.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    keyed = sorted((row for row in rows if row[5]), key=lambda row: row[5])
    return [row[1] for row in keyed]


def column_names(connection, table: str) -> list[str]:
    return [row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()]


def has_single_column_unique_index(connection, table: str, column: str) -> bool:
    """True when a unique index covers exactly this one column, matched by column: SQLite names them itself."""
    return has_unique_index_over(connection, table, [column])


def has_unique_index_over(connection, table: str, columns: list[str]) -> bool:
    """True when a unique index covers exactly these columns, in this order."""
    for index in connection.exec_driver_sql(f"PRAGMA index_list({table})").fetchall():
        if not index[2]:
            continue
        covered = [
            row[2]
            for row in connection.exec_driver_sql(f"PRAGMA index_info({index[1]})").fetchall()
        ]
        if covered == columns:
            return True
    return False


def count_untrimmed(connection, table: str, column: str) -> int:
    return connection.exec_driver_sql(
        f"SELECT COUNT(*) FROM {table} WHERE {column} <> TRIM({column}, {BLANKS})"
    ).scalar_one()


def count_blank(connection, table: str, column: str) -> int:
    return connection.exec_driver_sql(
        f"SELECT COUNT(*) FROM {table} WHERE TRIM({column}, {BLANKS}) = ''"
    ).scalar_one()


def main() -> int:
    paths = load_paths()
    if not paths.database.is_file():
        print(f"FAIL 数据库不存在: {paths.database}")
        return 1

    failures = 0

    def check(label: str, passed: bool) -> None:
        nonlocal failures
        print(f"{'PASS' if passed else 'FAIL'} {label}")
        if not passed:
            failures += 1

    engine = create_db_engine()
    try:
        tables = set(inspect(engine).get_table_names())
        check(f"{len(EXPECTED_TABLES)} 张表已建立", EXPECTED_TABLES <= tables)
        if not EXPECTED_TABLES <= tables:
            print(f"缺少的表: {', '.join(sorted(EXPECTED_TABLES - tables))}")
            return 1

        with engine.connect() as connection:
            for table, column in EXPECTED_COLUMNS:
                check(f"{table}.{column} 已建立", column in column_names(connection, table))

            # 写法在录入时已归一化,库里出现别的形状只有两种可能:绕过接口直接写,或归一化被改坏。
            written_dates = [
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT published_on FROM edition WHERE published_on IS NOT NULL"
                ).fetchall()
            ]
            odd_dates = [value for value in written_dates if not DATE_SHAPES.fullmatch(value)]
            check(
                f"载体时间的写法统一({len(written_dates)} 份作品写了时间)",
                not odd_dates,
            )
            if odd_dates:
                print(f"       写法不对的:{', '.join(repr(value) for value in odd_dates[:5])}")

            for table, column, parent, on_delete in REFERENCE_RULES:
                check(
                    f"{table}.{column} → {parent},删除行为 {on_delete}",
                    any(
                        key[2] == parent and key[3] == column and key[6] == on_delete
                        for key in foreign_key_rows(connection, table)
                    ),
                )

            for table, expected in PRIMARY_KEYS:
                check(
                    f"{table} 的主键是 ({', '.join(expected)})",
                    primary_key_columns(connection, table) == expected,
                )

            for table, column in UNIQUE_COLUMNS:
                check(
                    f"{table}.{column} 上有一个唯一索引",
                    has_single_column_unique_index(connection, table, column),
                )

            for table, columns in UNIQUE_COLUMN_GROUPS:
                check(
                    f"{table} 上 ({', '.join(columns)}) 有唯一索引",
                    has_unique_index_over(connection, table, list(columns)),
                )

            volume_indexes = connection.exec_driver_sql("PRAGMA index_list(volume)").fetchall()
            check("volume 卷号唯一索引已建立", any(row[1] == "uq_volume_number" for row in volume_indexes))

            check("当前连接启用 SQLite 外键", connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1)
            check("现有数据没有外键错误", not connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall())

            for table, column in TRIMMED_COLUMNS:
                check(f"{table}.{column} 没有前后空白", count_untrimmed(connection, table, column) == 0)

            check("没有空的作者名", count_blank(connection, "creator", "name") == 0)
            check("没有空的标签名", count_blank(connection, "tag", "name") == 0)

            check("至少有一条作品", connection.exec_driver_sql("SELECT COUNT(*) FROM work").scalar_one() >= 1)
            check("至少有一条载体", connection.exec_driver_sql("SELECT COUNT(*) FROM edition").scalar_one() >= 1)
            check(
                "载体有一条所属作品",
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM edition AS d "
                    "LEFT JOIN work AS w ON w.id = d.work_id WHERE w.id IS NULL"
                ).scalar_one()
                == 0,
            )
            check(
                "媒体类型属于当前收录范围",
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM edition "
                    "WHERE media_type NOT IN ('manga', 'light_novel', 'game', 'anime')"
                ).scalar_one()
                == 0,
            )
            check(
                "tag 的媒体类型属于当前收录范围",
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM tag "
                    "WHERE media_type NOT IN ('manga', 'light_novel', 'game', 'anime')"
                ).scalar_one()
                == 0,
            )
            # A tag is only ever attached to carriers of its own type; a row means the link was written without checking it.
            check(
                "标签只连到同类型的载体上",
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM edition_tag AS l "
                    "JOIN tag AS t ON t.id = l.tag_id "
                    "JOIN edition AS e ON e.id = l.edition_id "
                    "WHERE t.media_type <> e.media_type"
                ).scalar_one()
                == 0,
            )

            check(
                "载体关系存的是无序对",
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM edition_relation WHERE edition_a_id >= edition_b_id"
                ).scalar_one()
                == 0,
            )
            check(
                "载体关系连的是两部不同作品的载体",
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM edition_relation AS r"
                    " JOIN edition AS a ON a.id = r.edition_a_id"
                    " JOIN edition AS b ON b.id = r.edition_b_id"
                    " WHERE a.work_id = b.work_id"
                ).scalar_one()
                == 0,
            )
    finally:
        engine.dispose()

    # ---- JSON 接口这一层:不碰库也不需要服务,/docs 画的就是 FastAPI 手里那份描述,描述里没有的路径点不到。
    schema = fastapi_app.openapi()
    declared = {
        (method, path)
        for path, operations in schema["paths"].items()
        if path.startswith("/api")
        for method in operations
    }
    check(f"JSON 路径正好是约定的 {len(EXPECTED_API_ROUTES)} 条", declared == EXPECTED_API_ROUTES)
    if declared != EXPECTED_API_ROUTES:
        for method, path in sorted(EXPECTED_API_ROUTES - declared):
            print(f"       少了:{method.upper()} {path}")
        for method, path in sorted(declared - EXPECTED_API_ROUTES):
            print(f"       多了:{method.upper()} {path}")

    # 每条路都要写清回什么,否则 /docs 上点得开却看不到形状。**204 是例外**:删除回的就是「没有身体」。
    undocumented = [
        f"{method.upper()} {path}"
        for path, operations in schema["paths"].items()
        if path.startswith("/api")
        for method, operation in operations.items()
        if not any(
            str(code).startswith("2")
            and (str(code) == "204" or "application/json" in (answer.get("content") or {}))
            for code, answer in (operation.get("responses") or {}).items()
        )
    ]
    check("每条 JSON 路径都写明了回什么", not undocumented)
    if undocumented:
        for line in undocumented:
            print(f"       {line}")

    # 只有一扇门:接口在 /api,界面是前端构建出来的静态文件由后端一起发(见 app/main.py),所以要盯的是反过来的那件事 —— 网页路由不许出现在接口描述里,而界面那个挂载要在。
    mounted = {getattr(route, "path", "") for route in fastapi_app.routes}
    serves_ui = any(getattr(route, "name", "") == "ui" for route in fastapi_app.routes) or "/" in mounted
    check(
        "只剩 /api 是接口,界面由静态挂载发出去,/docs 还开着",
        "/api/works" in schema["paths"]
        and "/works" not in schema["paths"]
        and serves_ui
        and {"/docs", "/openapi.json"} <= mounted,
    )

    # ---- 「一个框」这件事本身 -----------------------------------------------
    # 不碰网络也不碰库,都是纯函数。它们错了不会报错,只会悄悄搜错:把「86」当条目 ID、把「AFTER STORY」并进「CLANNAD」,页面照样画得出来,只是画的是错的。
    asked = parse("bgm:294993")
    check(
        "站名加编号认得出是条目",
        asked.by_id and asked.source == "bangumi" and asked.external_id == "294993",
    )
    asked = parse("vndb:4")
    check(
        "VNDB 的编号少写一个 v 也认",
        asked.by_id and asked.source == "vndb" and asked.external_id == "v4",
    )
    check(
        "短数字仍当名字,四位以上数字可直接当 Bangumi 编号",
        not parse("86").by_id
        and parse("86").keyword == "86"
        and parse("294993").by_id
        and parse("294993").source == "bangumi"
        and parse("294993").external_id == "294993",
    )
    check(
        "Bangumi 条目链接可直接查",
        parse("https://bgm.tv/subject/294993").by_id
        and parse("https://bgm.tv/subject/294993").external_id == "294993",
    )
    check(
        "认不出的前缀整串当名字",
        not parse("CLANNAD: After Story").by_id
        and parse("CLANNAD: After Story").keyword == "CLANNAD: After Story",
    )
    check(
        "同一条的两种写法归一化后相等,另一部作品不等",
        flat("CLANNAD-クラナド-") == flat("CLANNAD") == flat(" clannad ")
        and flat("CLANNAD 〜AFTER STORY〜") != flat("CLANNAD"),
    )
    check(
        "类型推测按那张对照表翻,翻不出来就是 None",
        guess_media(2, "TV") == "anime"
        and guess_media(4, "游戏") == "game"
        and guess_media(1, "漫画") == "manga"
        and guess_media(1, "小说") == "light_novel"
        and guess_media(1, "画集") is None
        and guess_media(3, "") is None,
    )
    # 单行本折成**上一层**:候选里不该出现「(01)…(17)」,那是卷,由 volume 记。认法两条实测
    # 依据:系列条目 `series` 为真、单行本为假;单行本的关系里有一条「系列」指回上一层。
    check(
        "卷号认得出,四位数字(年份)与画集不误伤",
        _volume_base("Fate/stay night (01)") == "Fate/stay night"
        and _volume_base("よつばと! 第3巻") == "よつばと!"
        and _volume_base("Yotsuba Vol.2") == "Yotsuba"
        and _volume_base("86 (2016)") is None
        and _volume_base("Fate/stay night ビジュアルコレクション") is None,
    )
    series = Candidate(
        source="bangumi",
        external_id="34549",
        title="Fate/stay night 漫画版",
        original_title="Fate/stay night",
        media="manga",
    )
    volumes = [
        Candidate(
            source="bangumi",
            external_id=entry_id,
            title=f"Fate/stay night ({number})",
            original_title=f"Fate/stay night ({number})",
            media="manga",
        )
        for entry_id, number in (("12321", "01"), ("34528", "02"))
    ]
    folded = _fold_volumes(volumes, {"12321": False, "34528": False}, lambda item: None)
    check(
        "一层里只有单行本:折成最早的那一卷,名字按上一层写",
        [(item.external_id, item.title) for item in folded] == [("12321", "Fate/stay night")],
    )
    asked: list[str] = []
    folded = _fold_volumes(
        volumes,
        {"12321": False, "34528": False},
        lambda item: asked.append(item.external_id) or series,
    )
    check(
        "系列条目没被搜出来时,顺着「系列」关系问一步,只问一次",
        [item.external_id for item in folded] == ["34549"] and asked == ["12321"],
    )
    folded = _fold_volumes([series, *volumes], {"34549": True}, lambda item: None)
    check(
        "系列条目就在这次搜索里:只留它一条,不重复出现",
        [item.external_id for item in folded] == ["34549"],
    )

    anime = Candidate(
        source="bangumi",
        external_id="294993",
        title="咒术回战",
        original_title="呪術廻戦",
        media="anime",
    )
    related = [
        {"id": 319569, "relation": "单行本", "name": "公式ガイド", "name_cn": "官方指南"},
        {"id": 238887, "relation": "书籍", "name": "呪術廻戦", "name_cn": "咒术回战"},
        {"id": 373584, "relation": "游戏", "name": "呪術廻戦 幻影夜行", "name_cn": "咒术回战 幻影夜行"},
    ]
    chosen_identity = _pick_identity_relation(anime, related, {anime.external_id})
    check(
        "原作推断只在来源型关系里挑最接近的总标题",
        chosen_identity is not None and chosen_identity.get("id") == 238887,
    )
    check(
        "挑给谁搜的名字跟着源走:吃中文的拿中文,吃原名的拿原名",
        pick_name(["CLANNAD", "团子大家族"], True) == "团子大家族"
        and pick_name(["CLANNAD", "团子大家族"], False) == "CLANNAD",
    )

    # 每个源都得能答这几件事 —— 少一件页面上就是一个静默的空;加源时最常忘的就是新加的那件。
    thin = [
        f"{name}({'/'.join(missing)})"
        for name, source in SOURCES.items()
        for missing in [
            [
                thing
                for thing in ("search", "suggest", "fetch", "identity")
                if not callable(getattr(source, thing, None))
            ]
            + ([] if isinstance(getattr(source, "prefers_cjk", None), bool) else ["prefers_cjk"])
            + (
                []
                if isinstance(getattr(source, "media_buckets", None), dict)
                and getattr(source, "media_buckets")
                else ["media_buckets"]
            )
        ]
        if missing
    ]
    check(f"{len(SOURCES)} 个源各自都能搜、能取建议、能按 id 取回并判断作品身份", not thin)
    if thin:
        print("       " + "、".join(thin))

    # ---- 「一个框」那条路本身:把两个源换成假的,走一遍真的 collect ---------------
    # 不碰网络,走的却是真的那段编排:认字符串 → 挑名字 → 按类各搜一遍 → 去重 → 报「用了哪些词」。错了不容易看出来:少 import 一个名字就是 500,少搜一类就是少一批。
    class FakeBangumi:
        name, label, prefers_cjk = "bangumi", "Bangumi", True
        # 漫画与轻小说都是它的「书籍」:两个类型指同一类,**只该问它一次**。
        media_buckets = {
            "manga": "books",
            "light_novel": "books",
            "anime": "anime",
            "game": "game",
        }

        def __init__(self):
            self.asked: list[tuple[str, str]] = []

        def search(self, keyword, limit=8, bucket=""):
            self.asked.append((keyword, bucket))
            # 不分那一次:音乐专辑排在前面,漫画与小说被挤出去了(实测就是这样)。
            if bucket == "":
                return [
                    Candidate(
                        source="bangumi",
                        external_id="616",
                        title="CLANNAD Original SoundTrack",
                        kind="",
                        media=None,
                    )
                ]
            if keyword != "CLANNAD":
                return []
            if bucket == "books":
                # 漫画与轻小说都在书籍这一类里,靠 platform 再分。
                return [
                    Candidate(
                        source="bangumi",
                        external_id="48",
                        title="CLANNAD Official Another Story",
                        kind="小说",
                        media="light_novel",
                    ),
                    Candidate(
                        source="bangumi",
                        external_id="149014",
                        title="CLANNAD 漫画版",
                        kind="漫画",
                        media="manga",
                    ),
                ]
            if bucket == "anime":
                return [
                    Candidate(
                        source="bangumi",
                        external_id="51",
                        title="CLANNAD",
                        kind="TV",
                        year="2007",
                        media="anime",
                    )
                ]
            if bucket == "game":
                return [
                    Candidate(
                        source="bangumi",
                        external_id="13",
                        title="CLANNAD",
                        kind="游戏",
                        media="game",
                    )
                ]
            return []

        def suggest(self, external_id):
            return []

        def fetch(self, external_id):
            return Candidate(
                source="bangumi",
                external_id=external_id,
                title="CLANNAD",
                original_title="CLANNAD-クラナド-",
                aliases=("小镇家族",),
                media="game",
            )

    class FakeVndb:
        name, label, prefers_cjk = "vndb", "VNDB", False
        # 整个站只有一类。
        media_buckets = {"game": "vn"}

        def __init__(self):
            self.asked: list[tuple[str, str]] = []

        def search(self, keyword, limit=8, bucket=""):
            self.asked.append((keyword, bucket))
            return [Candidate(source="vndb", external_id="v4", title="CLANNAD", media="game")]

        def suggest(self, external_id):
            return []

        def fetch(self, external_id):
            return Candidate(
                source="vndb",
                external_id=external_id,
                title="CLANNAD",
                media="game",
            )

    real_sources = dict(SOURCES)
    try:
        fake_bangumi, fake_vndb = FakeBangumi(), FakeVndb()
        SOURCES.clear()
        SOURCES.update({"bangumi": fake_bangumi, "vndb": fake_vndb})

        by_name = collect_from_sources(CollectIn(query="CLANNAD"))
        check(
            "输名字:每个源按它自己分得清的类各搜一遍(漫画与轻小说合成一次)",
            sorted(fake_bangumi.asked) == [("CLANNAD", "anime"), ("CLANNAD", "books"), ("CLANNAD", "game")]
            and fake_vndb.asked == [("CLANNAD", "vn")],
        )
        check(
            "搜完的候选合成一张表,四种类型都在",
            [(item.external_id, item.media) for item in by_name.candidates]
            == [
                ("51", "anime"),
                ("48", "light_novel"),
                ("149014", "manga"),
                ("13", "game"),
                ("v4", "game"),
            ],
        )
        check(
            "同一条候选出现在两类里也只留一条",
            len({(item.source, item.external_id) for item in by_name.candidates})
            == len(by_name.candidates),
        )
        check(
            "用了哪些词如实报出来(每类各搜几次是源自己的事)",
            [(step.source, step.keyword) for step in by_name.steps]
            == [("bangumi", "CLANNAD"), ("vndb", "CLANNAD")],
        )
        check("输名字时没有「按 ID 取回的那一条」", by_name.resolved is None)

        fake_bangumi, fake_vndb = FakeBangumi(), FakeVndb()
        SOURCES.clear()
        SOURCES.update({"bangumi": fake_bangumi, "vndb": fake_vndb})

        by_id = collect_from_sources(CollectIn(query="bgm:13"))
        check(
            "输 ID:先补全出名字,再拿它把每个源都搜一遍",
            by_id.resolved is not None
            and by_id.resolved.external_id == "13"
            and by_id.resolved.aliases == ["小镇家族"]
            and sorted(fake_bangumi.asked)
            == [("CLANNAD", "anime"), ("CLANNAD", "books"), ("CLANNAD", "game")],
        )
        check(
            "人点名的那一条排在候选第一个 —— 页面上默认勾的就是它",
            by_id.candidates[0].external_id == "13",
        )

        # 别名不拿去当搜索的词:Bangumi 的搜索按词切分,拿别名「小镇家族」去搜回来的是一堆同名的别部作品(《小镇有你》之类),真正要找的漫画版一条都没进来。
        fake_bangumi, fake_vndb = FakeBangumi(), FakeVndb()
        SOURCES.clear()
        SOURCES.update({"bangumi": fake_bangumi, "vndb": fake_vndb})
        collect_from_sources(CollectIn(query="bgm:13"))
        check(
            "别名不拿去当搜索的词",
            {keyword for keyword, _ in fake_bangumi.asked} == {"CLANNAD"}
            and {keyword for keyword, _ in fake_vndb.asked} == {"CLANNAD"},
        )
    finally:
        SOURCES.clear()
        SOURCES.update(real_sources)

    # ---- 限速 --------------------------------------------------------------
    # 桶的算法与「这个请求算谁的」都是纯函数,直接考它们,不需要服务也不碰库;**真发请求打到 429 的那几条在 `scripts/flow.py` 里**。
    from app.ratelimit import BURST, PER_MINUTE, Bucket, client_key, refill, take

    check(
        "本机的程序不设限(对端是回环、又没有 X-Forwarded-For)",
        client_key("127.0.0.1", None) is None and client_key("::1", None) is None,
    )
    check(
        "挂隧道时按 X-Forwarded-For 的第一段算客户端",
        client_key("127.0.0.1", "203.0.113.7") == "203.0.113.7"
        and client_key("127.0.0.1", "203.0.113.7, 10.0.0.1") == "203.0.113.7",
    )
    check(
        "对端不是回环时**不信** X-Forwarded-For(那个头客户端自己能写)",
        client_key("198.51.100.9", "203.0.113.7") == "198.51.100.9",
    )
    check("认不出对端时不设限", client_key(None, "203.0.113.7") is None)

    # 一个全新的桶:前 BURST 次都能走,第 BURST+1 次起要等。
    bucket = Bucket(tokens=float(BURST), filled_at=0.0)
    allowed = 0
    for _ in range(BURST + 5):
        if take(bucket, 0.0) == 0.0:
            allowed += 1
    check(f"新桶正好放行 {BURST} 次(实际 {allowed} 次)", allowed == BURST)
    check("用光之后要等一会儿(给的是正数秒)", take(bucket, 0.0) > 0)
    # 等够一分钟,水位回到上限。
    refill(bucket, 60.0)
    check(f"过一分钟水位回到上限(实际 {bucket.tokens:.3f})", abs(bucket.tokens - BURST) < 0.001)
    # 按秒回填:每分钟 PER_MINUTE 次,一秒就是 PER_MINUTE/60 个。
    trickle = Bucket(tokens=0.0, filled_at=0.0)
    refill(trickle, 1.0)
    check(
        f"一秒回填 {PER_MINUTE / 60:.0f} 个令牌(实际 {trickle.tokens:.3f})",
        abs(trickle.tokens - PER_MINUTE / 60) < 0.001,
    )
    check(f"额度({PER_MINUTE})比突发({BURST})大 —— 长期速率才封得住", PER_MINUTE > BURST)
    check(f"突发({BURST})够一次冷访问(实测一次 25 个请求)", BURST >= 100)

    # ---- 页面上不许出现开发期的说法:扫的是会被人看到的那部分源码(前端模板正文与模块字符串、后端说到屏幕上的句子),写给开发者的注释不算。
    for where, text in source_texts():
        hit = [word for word in BANNED_WORDING if word in text]
        check(f"{where} 没有开发期的说法", not hit)
        if hit:
            for word in hit:
                for line in text.split("\n"):
                    if word in line:
                        print(f"       {word}: {line.strip()[:100]}")
                        break

    print(f"检查结束: {failures} 项失败")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
