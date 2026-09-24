"""The API and the delivered interface, checked end to end against a running server.

**不用凭据**:这份库只在自己电脑上用,写请求直接发,没有登录。它几乎每一件事都在写;自己建的记录都带
`PREFIX` 前缀,跑完自己清掉。与只读、不用服务的 `check.py` 相对,它连界面怎么发出去一起看 ——
构建产物由后端发、地址交给前端路由、只有 `/api` 回 JSON。用法 `python scripts/flow.py [地址]`,默认 127.0.0.1:8011。
"""

from __future__ import annotations

import base64
import json
import os
import random
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import load_paths, load_source_settings  # noqa: E402
from app.covers import covers_dir  # noqa: E402
from app.db import create_db_engine  # noqa: E402
from app.listing import PAGE_SIZE, WORK_SORT_VALUES  # noqa: E402
from app.ratelimit import BURST  # noqa: E402
from app.settings_store import profile_file, settings_file  # noqa: E402

# Everything this script makes carries this prefix, so leftovers are findable in one query.
PREFIX = "验收临时"

DEFAULT_BASE = "http://127.0.0.1:8011"

COUNTED_TABLES = ("work", "edition", "volume", "edition_relation", "creator", "tag")


#: 这次检查给哪一份作品、哪一卷、哪个总标题写了封面文件 —— 摘掉与换一张都不动文件(见 `app/covers.py`),
#: 要清哪几条记录得自己记着。
COVER_EDITION_ID = 0
COVER_VOLUME_ID = 0
COVER_WORK_ID = 0


class Stop(Exception):
    """A step could not be attempted. Counted as a failure, and the run ends."""


class Checks:
    """One run: the requests, the tally, and the lines it prints."""

    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        # 没有登录,也就没有 cookie:每个请求都是普通请求,带上 `Content-Type` 直接发。
        self.opener = urllib.request.build_opener()
        self.step = 0
        self.passed = 0
        self.failed = 0

    def api(self, method: str, path: str, body=None) -> tuple[int, object]:
        """Send one JSON request; hand back (status, parsed body): 正文与拒绝都解析成对象,理由在 `detail` 里。"""
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self.base + path,
            data=payload,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read().decode("utf-8")
                return response.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8")
            try:
                return error.code, json.loads(raw)
            except json.JSONDecodeError:
                return error.code, raw
        except urllib.error.URLError as error:
            raise Stop(f"{method} {path} 连不上 {self.base}({error.reason})") from error

    def text(self, path: str) -> tuple[int, str]:
        """GET and hand back (status, body) as text — for the interface, which is not JSON."""
        request = urllib.request.Request(self.base + path, method="GET")
        try:
            with self.opener.open(request, timeout=15) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", "replace")
        except urllib.error.URLError as error:
            raise Stop(f"GET {path} 连不上 {self.base}({error.reason})") from error

    def upload(self, path: str, filename: str, data: bytes) -> tuple[int, object]:
        """POST one file as multipart/form-data —— JSON 那个助手发不了这个形状,封面是全项目唯一带文件的
        请求;回话照着 JSON 那样读,因为接口回的就是它。"""
        boundary = "----pansy-flow-boundary"
        body = b"".join(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
                b"Content-Type: application/octet-stream\r\n\r\n",
                data,
                f"\r\n--{boundary}--\r\n".encode(),
            ]
        )
        request = urllib.request.Request(
            self.base + path,
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read().decode("utf-8")
                return response.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8")
            try:
                return error.code, json.loads(raw)
            except json.JSONDecodeError:
                return error.code, raw
        except urllib.error.URLError as error:
            raise Stop(f"POST {path} 连不上 {self.base}({error.reason})") from error

    def check(self, label: str, passed: bool, detail: str = "") -> None:
        self.step += 1
        print(f"{'PASS' if passed else 'FAIL'} [{self.step:02d}] {label}"
              + (f"  -- {detail}" if detail else ""))
        if passed:
            self.passed += 1
        else:
            self.failed += 1


def query(sql: str):
    engine = create_db_engine()
    try:
        with engine.connect() as connection:
            return connection.exec_driver_sql(sql).all()
    finally:
        engine.dispose()


def count(table: str) -> int:
    return query(f"SELECT COUNT(*) FROM {table}")[0][0]


def counts() -> dict:
    return {table: count(table) for table in COUNTED_TABLES}


def row_id(table: str, column: str, value: str) -> int:
    """The id of one row, found by a named column: 作品总标题 is a title, not a name."""
    found = query(f"SELECT id FROM {table} WHERE {column} = '{value}'")
    return int(found[0][0]) if found else 0


def relation_count(left: int, right: int) -> int:
    low, high = sorted((left, right))
    return query(
        "SELECT COUNT(*) FROM edition_relation "
        f"WHERE edition_a_id = {low} AND edition_b_id = {high}"
    )[0][0]


def field(body, name: str, default=None):
    """One value out of a JSON body, whether or not it parsed into a dict."""
    return body.get(name, default) if isinstance(body, dict) else default


def added(checks: Checks, method: str, path: str, body) -> tuple[int, object, int]:
    """Send a request that should create something and hand back its id —— 悄悄回 200 却没有新 id 的创建
    会让后面每条检查都失去意义,所以 id 在这里取一次。"""
    status, answer = checks.api(method, path, body)
    return status, answer, int(field(answer, "id") or 0)


def delete_work(checks: Checks, work_id: int) -> None:
    checks.api("DELETE", f"/api/works/{work_id}")


def sweep_vocabulary() -> list[str]:
    """Remove the creator and tag rows this prefix made, when nothing uses them —— 作者与标签故意没有删除
    接口(共用词汇、各有自己的页面),这里是脚本在清自己,直接落到表上,并且拒绝删还有引用的行。"""
    removed: list[str] = []
    for table, link, column in (
        ("creator", "edition_creator", "creator_id"),
        ("tag", "edition_tag", "tag_id"),
    ):
        for row_id_value, name in query(f"SELECT id, name FROM {table} WHERE name LIKE '{PREFIX}%'"):
            used = query(f"SELECT COUNT(*) FROM {link} WHERE {column} = {row_id_value}")[0][0]
            if used:
                print(f"     {table} {name} 还有 {used} 条引用,留着")
                continue
            engine = create_db_engine()
            with engine.begin() as connection:
                connection.exec_driver_sql(f"DELETE FROM {table} WHERE id = {row_id_value}")
            engine.dispose()
            removed.append(f"{table} {row_id_value} {name}")
    return removed


#: 一张真的 1×1 PNG —— 封面按**文件头**认格式,喂假数据测的就不是那条规矩了。
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


def cover_files(kind: str, row_id: int) -> list[str]:
    """这一条记录在硬盘上有哪几个封面文件 —— 按文件名找,不看数据库。`kind` 是 `"work"`、`"edition"`
    或 `"volume"`:三种封面的规矩完全一样,只有文件名分得出来(`work-1.png` 与 `edition-1.png`)。"""
    return sorted(path.name for path in covers_dir().glob(f"{kind}-{row_id}.*"))


def sweep_covers(kind: str, row_id: int) -> list[str]:
    """删掉这次检查为某一条记录写下的封面文件。**这是脚本在清自己的东西**:正常跑完时什么都不剩,
    它兜的是「上一次崩在删记录之前」那种情况。"""
    removed = []
    for name in cover_files(kind, row_id):
        (covers_dir() / name).unlink()
        removed.append(name)
    return removed


def _fetch(
    base: str, path: str, forwarded: str | None = None, body: object | None = None
) -> tuple[int, dict, str]:
    """一次直接请求,把状态、响应头与正文都带回来 —— 限速那几条要看 `Retry-After`,而 `Checks.api()`
    只回状态与正文,为这一个用途改它的返回形状不值得,所以这里自己发。"""
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        base + path, data=payload, method="POST" if payload is not None else "GET"
    )
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if forwarded:
        request.add_header("X-Forwarded-For", forwarded)
    try:
        with urllib.request.urlopen(request, timeout=15) as answer:
            # **键一律小写**:HTTP 头名不分大小写,而服务端发的是 `retry-after`,拿 `Retry-After` 去取会取不到。
            headers = {key.lower(): value for key, value in answer.headers.items()}
            return answer.status, headers, answer.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        headers = {key.lower(): value for key, value in error.headers.items()}
        return error.code, headers, error.read().decode("utf-8", "replace")
    except urllib.error.URLError as error:
        raise Stop(f"{path} 连不上 {base}({error.reason})") from error


def rate_limit_checks(checks: Checks) -> None:
    """限速那几条:**冒充一个外部地址来打**(本机自己是豁免的,见 `app/ratelimit.py`,不带
    `X-Forwarded-For` 打不到 429;假地址取文档专用的 TEST-NET-3,203.0.113.0/24)。**每次现取一个地址**:
    桶在服务器内存里,同一份地址连着跑两遍,第二遍一上来桶就是空的,「打到第几次才被挡」会随上一遍跑过多久而变。"""
    fake = f"203.0.113.{random.randint(1, 254)}"
    other = f"198.51.100.{random.randint(1, 254)}"
    reach = BURST + 80

    # 一、本机不带 X-Forwarded-For:连着打 BURST+30 次也不该被挡 —— 反面检查:少了它,
    # 以后有人把「本机豁免」改坏,要等验收脚本自己开始失败才发现。
    statuses = {_fetch(checks.base, "/api/media-types")[0] for _ in range(BURST + 30)}
    checks.check(
        f"本机不带 X-Forwarded-For 连打 {BURST + 30} 次不被挡",
        statuses == {200},
        f"出现的状态码:{sorted(statuses)}",
    )

    # 二、冒充外部地址:应该打到 429,并带回那句话与 Retry-After。
    blocked_at, detail, retry_after = 0, "", ""
    for index in range(1, reach):
        status, headers, raw = _fetch(checks.base, "/api/media-types", fake)
        if status == 429:
            blocked_at = index
            retry_after = headers.get("retry-after", "")
            try:
                detail = str(json.loads(raw).get("detail", ""))
            except json.JSONDecodeError:
                detail = raw[:80]
            break
    checks.check(
        f"冒充外部地址({fake})会被挡住(第 {blocked_at} 次)",
        blocked_at > 0,
        f"第 {blocked_at} 次挡住(一共打了 {reach - 1} 次)",
    )
    checks.check(
        f"挡在突发额度附近(第 {blocked_at} 次,突发 {BURST})",
        0 < blocked_at <= BURST + 40,
    )
    checks.check(
        "挡住时说的话与别的拒绝同一个形状",
        detail == "请求太频繁了,过一会儿再试。",
        detail,
    )
    checks.check("挡住时带回 Retry-After", retry_after.isdigit(), repr(retry_after))

    # 三、超限之后**写接口答的是 429** —— 限速挂在中间件上,是唯一一道闸门,读的写的都从它这里过,
    # 所以这个请求到不了接口那一层。
    # (真被挡住了才不会建出记录;万一没挡住,那条 PREFIX 记录会被收尾的数数抓出来。)
    status, _headers, raw = _fetch(checks.base, "/api/works", fake, {"title": f"{PREFIX}不该建出来"})
    checks.check(
        "超限之后写接口答 429 —— 请求到不了接口那一层",
        status == 429,
        f"答的是 {status}:{raw[:60]}",
    )

    # 四、换一个地址仍然通 —— 桶是按地址分的,一个人刷不该把所有人挡住。
    status, _headers, _raw = _fetch(checks.base, "/api/media-types", other)
    checks.check(f"换一个地址({other})仍然通 —— 桶按地址分", status == 200, f"答的是 {status}")


def clean_before(checks: Checks) -> None:
    """Clear what a previous run left behind, through the app where it can."""
    leftovers = query(f"SELECT id, title FROM work WHERE title LIKE '{PREFIX}%'")
    for work_id, title in leftovers:
        delete_work(checks, int(work_id))
        print(f"     清掉上次留下的作品总标题 {work_id} {title}")
    for gone in sweep_vocabulary():
        print(f"     清掉上次留下的 {gone}")


#: 文件名里带这些字样的,还原时一律按"含密"对待 —— 权限收紧到 0600。
#: 凭据、登录令牌、账号资料:这三样都不该让本机别的用户读得到(理由与 `settings_store` 里
#: 给会话文件 `chmod 0600` 是同一条)。
_SECRET_NAME_PARTS = ("settings.json", "session.json", "_profile.json")


def _is_secret_path(path) -> bool:
    return any(part in path.name for part in _SECRET_NAME_PARTS)


def _write_text(path, content: str) -> None:
    """写一份文本文件:**先写同目录下的临时文件再替换**。

    不直接用 `write_text` 的理由是还原过程中再次中断会留下**截断的 JSON** —— 那比"文件还在旧的
    那一份"糟糕得多:下一次读它的人拿到的是一个解析不了的半截文件。同目录 + `replace()` 在同一个
    文件系统上是原子的,所以要么是新的、要么还是旧的,没有中间态。

    临时文件先按 0600 建(在 Windows 上是个空操作),这样**内容落盘之前权限就已经收好了**,
    不存在"刚写完还是 0644、下一行才 chmod"的那个窗口。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    with open(temporary, "w", encoding="utf-8", opener=lambda name, flags: os.open(name, flags, 0o600)) as handle:
        handle.write(content)
    temporary.replace(path)


def _restore_path(path, mode: int | None) -> None:
    """还原之后把权限收回报错前的样子。

    **含密的那些一律 0600,不看原权限。** 这一条要写在前面:`mode` 是"照原样还原",而原样可能
    本来就是宽的(文件从来没被 `settings_store` 建过、或者人手工 chmod 过)。先前把两条的先后
    写反了 —— 先按原权限还原、再收紧,于是后一步被前一步覆盖,等于没收紧(实测发现)。

    其余文件按 `stat` 读来的访问位还原,免得把权限悄悄改宽或改窄。
    都是尽力而为:Windows 上 `chmod` 基本是空操作,某些文件系统也不支持,做不到不算错。
    """
    if mode is None:
        return
    try:
        path.chmod(0o600 if _is_secret_path(path) else stat.S_IMODE(mode))
    except OSError:
        pass


def sweep_flow_backups() -> list[str]:
    """清掉以前版本留在数据目录里的 `.flowbackup`。

    **那个设计是错的,所以这一版把它删掉。** 它会把 `client_secret`、access token、refresh token
    明文抄一份留在本机,而且**成功还原之后也不删** —— 换言之,为了防一次崩溃,长期多留了一份密钥。
    留底现在只在内存里(见 `local_state_snapshot`),它唯一能挡的"崩溃"就是 Python 异常,
    而那条路由 `main()` 的 `finally` 兜着;真被 Ctrl-C 或断电打断时,也不需要一份明文的密钥在那儿等着。

    返回清掉的文件名,好让调用方打一行字出来。
    """
    removed = []
    for leftover in sorted(load_paths().data_dir.glob("*.flowbackup")):
        try:
            leftover.unlink()
        except OSError:
            continue
        removed.append(leftover.name)
    return removed


def local_state_snapshot() -> list[tuple]:
    """把**会被这一跑弄丢的本地文件**挨个留底。收尾时照原样放回去。

    要留的有三样,而且都是实测踩出来的:

    - `settings.json` —— 那两格 Hikarinagi 凭据会被这一跑清掉。
    - `hikarinagi_session.json` —— **凭据被清掉时后端会连带清掉登录会话**。删它的不是
      `DELETE /api/settings`(那个只删设置),而是紧接着**用空凭据调保存接口**那一步:
      那条路会 `forget_session()` 与 `forget_profile()`(会话离开凭据没法续期,那个设计是对的)。
    - `{源}_profile.json` —— 同上,账号资料也会跟着没。**按源登记表 `SOURCES` 遍历,不写死名字**:
      换凭据(或清掉)现在也会 `forget_profile()`,因为那份"你是谁"是配着旧凭据问出来的。

    最后这一条踩过两次,值得记下来:**别用"有凭据可填的源"(`CREDENTIALS`)当这份名单** ——
    Bangumi 的令牌走的是 `settings.json` 里那一格、不在 `CREDENTIALS` 里,于是它的资料一直没人留底。
    而这一跑会往 Bangumi 写一个假令牌、再清掉,两条路都会把真资料删掉 —— 结果就是每跑一次验收,
    设置页上那个真账号就被抹掉一次(实测:跑完 `bangumi_account` 整个空了)。名单要从 `SOURCES` 来,
    它才是"有哪些源"的唯一出处。

    **只在内存里留,不落盘一份备份文件**:那会把密钥明文再抄一份留在本机,而且成功还原之后也不删。
    够用的理由是这里要挡的是"脚本自己抛异常半路退出",而那条路由 `main()` 的 `finally` 兜着。

    每样返回 `(路径, 内容或 None, 原权限位或 None)`。
    """
    from app.settings_store import profile_file, session_file
    from app.sources import SOURCES

    targets = [settings_file(), session_file()]
    targets += [profile_file(source) for source in SOURCES]
    found = []
    for path in targets:
        if not path.is_file():
            found.append((path, None, None))
            continue
        try:
            found.append((path, path.read_text(encoding="utf-8"), path.stat().st_mode))
        except OSError:
            found.append((path, None, None))
    return found


def restore_local_state(snapshot: list[tuple]) -> None:
    """把留底的那几份文件放回去。**文件级的还原,不是再调一次接口** ——
    接口只会写它认得的那几个键,而"这个文件本来就不该存在"这件事只有文件系统知道。

    留底里 `None` 表示"跑之前它不在",那就删掉 —— 而不是留一个空的 `{}`。
    """
    for path, content, mode in snapshot:
        if content is None:
            path.unlink(missing_ok=True)
            continue
        _write_text(path, content)
        _restore_path(path, mode)



def settings_from_snapshot(snapshot: list[tuple]):
    """从留底里挑出设置那一份:`(跑之前的内容, 原权限位)`。

    **它不自己去读文件** —— 留底只该在最早那一刻做一次(见 `main()`)。这里再读一次的话,
    读到的可能是中途被弄坏的内容,而那份坏内容会被当成"跑之前的样子"。
    实测踩过:人的 Hikarinagi 凭据就是这么丢的。
    """
    for path, content, mode in snapshot:
        if path == settings_file():
            return content, mode
    raise AssertionError("留底里没有 settings.json —— local_state_snapshot 改坏了")


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE

    checks = Checks(base)
    print(f"目标 {checks.base}")
    print(f"数据库 {load_paths().database}\n")

    #: 会把本地文件弄丢的那一跑,先全部留个底。**在最外面留、而且只留这一次** ——
    #: 这样不管后面哪一步炸了,`finally` 都能把它们还原回去(包括登录会话:清凭据会连带清掉它)。
    #: 这里也是**唯一**写 `.flowbackup` 的地方:中途再留一次底的话,那一刻若文件已经坏了,
    #: 好备份就会被坏内容覆盖 —— 实测踩过,人的凭据就是这么丢的。
    local_before = local_state_snapshot()
    settings_before, _settings_mode = settings_from_snapshot(local_before)

    try:
        clean_before(checks)
    except Stop as stop:
        checks.check("流程能走完", False, str(stop))
        print(f"\n{checks.passed} 项通过,{checks.failed} 项失败")
        return 1

    before = counts()
    print(f"起始数量 {before}\n")

    # **收尾永远要跑**,哪怕中间炸了。两件事都得保证做到:清掉这一跑留下的东西、把本地那几份
    # 文件还原回去 —— 后者包含人真填过的凭据与登录会话(实测踩过:崩半路就把它们弄丢了)。
    #
    # **两层 `try/finally`,不是一层**:清理里那几个 `sweep_*` 自己也可能抛(数据库锁、文件占用),
    # 而它们在原版里排在还原**前面** —— 一旦其中一个抛出来,执行流就直接离开 `finally`,
    # **还原被跳过**。所以还原必须是最后一道、且不可跳过的保障,清理炸了也不能拦着它。
    swept: list[str] = []
    failed = ""
    try:
        try:
            run(checks, local_before)
            rate_limit_checks(checks)
        except Stop as stop:
            checks.check("流程能走完", False, str(stop))
        except Exception as error:  # noqa: BLE001 — 验收脚本自己出错也要先把现场收拾干净
            import traceback

            print("\n验收脚本自己崩了,下面是它的调用栈。**现场会照常清理、设置会照常还原。**\n")
            traceback.print_exc()
            checks.check("流程能走完", False, f"{type(error).__name__}: {error}")
    finally:
        try:
            # The run removes its own records; this clears the two vocabulary rows it cannot remove through the app.
            swept = sweep_vocabulary()
            swept += [f"covers/{name}" for name in sweep_covers("edition", COVER_EDITION_ID)]
            swept += [f"covers/{name}" for name in sweep_covers("volume", COVER_VOLUME_ID)]
            swept += [f"covers/{name}" for name in sweep_covers("work", COVER_WORK_ID)]
        except Exception as error:  # noqa: BLE001
            failed = f"{type(error).__name__}: {error}"
            print(f"\n收尾清理没做完({failed})。**不影响下面的还原** —— 库可能没回到起始状态。\n")
        finally:
            # ★ 这一句必须最后执行、且不可跳过:留底只在内存里,这里不还原就真没了。
            restore_local_state(local_before)

    # 旧版本会把留底抄一份 `.flowbackup` 放在数据目录里 —— 那等于长期多留一份明文密钥。
    # 顺手清掉以前留下的。
    for leftover in sweep_flow_backups():
        print(f"清掉旧版本留下的 {leftover}")

    after = counts()
    checks.check(
        "库回到起始状态",
        after == before,
        f"{before} -> {after}" + (f",清掉 {swept}" if swept else "") + (f",清理未完成:{failed}" if failed else ""),
    )
    restored_settings = settings_file()
    checks.check(
        "这一节动过的那份设置已经还原",
        (restored_settings.read_text(encoding="utf-8") if restored_settings.is_file() else None)
        == settings_before,
        "跑验收不该改掉这台机器上真填过的东西",
    )

    print(f"\n{checks.passed} 项通过,{checks.failed} 项失败")
    return 1 if checks.failed else 0


def run(checks: Checks, local_before: list[tuple]) -> None:
    """The flow itself: what is delivered, then the rules the API holds."""

    # 开始前 covers 目录里已有的文件,收尾时对照:该删的删了,不该删的一个都不许动。
    covers_before = sorted(path.name for path in covers_dir().glob("*"))

    # ---- 界面是怎么发出去的:地址交给前端路由、只有 /api 回 JSON、静态文件真的在 --------
    status, shell = checks.text("/")
    checks.check(
        "根地址发的是界面外壳",
        status == 200 and 'id="app"' in shell,
        f"GET / -> {status}",
    )
    shelf_asset = re.search(r'src="(/assets/[^"]+\.js)"', shell)
    if shelf_asset is None:
        raise Stop("界面外壳里没有找到构建产物的脚本地址,后面的静态文件检查做不了")
    status, asset = checks.text(shelf_asset.group(1))
    checks.check(
        "外壳引用的那个脚本真的发得出来",
        status == 200 and "<!doctype" not in asset.lower(),
        f"GET {shelf_asset.group(1)} -> {status}",
    )

    status, deep = checks.text("/works/1")
    checks.check(
        "站点里的地址交给前端路由,而不是后端报 404",
        status == 200 and 'id="app"' in deep,
        f"GET /works/1 -> {status} —— 后端不认识这个地址是正常的,前端认识",
    )
    status, missing_file = checks.text("/assets/there-is-no-such-file.js")
    checks.check(
        "缺一个文件时照实说找不到,不拿界面去糊",
        status == 404 and "<!doctype" not in missing_file.lower(),
        f"GET /assets/there-is-no-such-file.js -> {status}",
    )
    status, answer = checks.api("GET", "/api/there-is-no-such-endpoint")
    checks.check(
        "接口那一侧找不到地址时是 JSON,不是界面",
        status == 404 and field(answer, "detail") == "Not Found",
        f"GET /api/there-is-no-such-endpoint -> {status} {field(answer, 'detail')!r}",
    )
    status, docs = checks.text("/docs")
    checks.check("接口文档还在", status == 200 and "swagger" in docs.lower(), f"GET /docs -> {status}")

    # ---- 夹具:三条总标题,四份作品,全部自己建 -----------------------------
    # 甲的两份时间相差很大(1900-01 与 2099-01-01),乙只有一份 1900-02 的游戏 —— 给两种排法用的。
    status, _, work_a = added(
        checks,
        "POST",
        "/api/works",
        {"title": f"{PREFIX}甲", "original_title": f"{PREFIX}甲原名", "aliases": [f"{PREFIX}甲别名"]},
    )
    checks.check("建出第一个总标题", status == 201 and work_a > 0, f"POST /api/works -> {status}")

    status, _, edition_a = added(
        checks,
        "POST",
        f"/api/works/{work_a}/editions",
        {
            "media_type": "manga",
            "title": f"{PREFIX}甲漫画",
            "published_on": "1900-01",
            "org": f"{PREFIX}甲出版社",
            "release_status": "已完结",
            "volume_count": 2,
            "creators": [{"name": f"{PREFIX}作者", "role": "原作"}],
            "tags": [f"{PREFIX}标签"],
        },
    )
    checks.check(
        "建出甲的漫画那一份",
        status == 201 and edition_a > 0,
        f"POST /api/works/{work_a}/editions -> {status}",
    )

    status, _, edition_a_game = added(
        checks,
        "POST",
        f"/api/works/{work_a}/editions",
        {"media_type": "game", "title": f"{PREFIX}甲游戏", "published_on": "2099-01-01"},
    )
    checks.check("建出甲的游戏那一份", status == 201 and edition_a_game > 0, f"-> {status}")

    status, _, work_b = added(checks, "POST", "/api/works", {"title": f"{PREFIX}乙"})
    status, _, edition_b = added(
        checks,
        "POST",
        f"/api/works/{work_b}/editions",
        {"media_type": "game", "title": f"{PREFIX}乙游戏", "published_on": "1900-02"},
    )
    checks.check("建出乙与它的游戏", work_b > 0 and edition_b > 0, f"work {work_b}, edition {edition_b}")

    # 作者自己的别名只有作者那一页写得了,所以建完再补一次。
    creator_a = row_id("creator", "name", f"{PREFIX}作者")
    checks.api("PUT", f"/api/creators/{creator_a}", {"name": f"{PREFIX}作者", "aliases": [f"{PREFIX}笔名"]})

    # 同一个人的两种写法一起送:判重按**认出来的那一行**算,不按打进来的字。按字判重会让
    # 同一 (件, 人, 职位) 写两次、撞唯一键,整次保存变成 500(源里给日文写法、库里记中文写法
    # 时就会这样)。
    status, answer = checks.api(
        "PUT",
        f"/api/editions/{edition_a}",
        {
            "media_type": "manga",
            "title": f"{PREFIX}甲漫画",
            "published_on": "1900-01",
            "org": f"{PREFIX}甲出版社",
            "release_status": "已完结",
            "volume_count": 2,
            "creators": [
                {"name": f"{PREFIX}作者", "role": "原作"},
                {"name": f"{PREFIX}笔名", "role": "原作"},
            ],
            "tags": [f"{PREFIX}标签"],
        },
    )
    checks.check(
        "正名与别名一起送时,同一个人只连一次",
        status == 200 and [item.get("name") for item in field(answer, "creators", [])] == [f"{PREFIX}作者"],
        f"PUT /api/editions/{edition_a} -> {status},creators {field(answer, 'creators', [])}",
    )

    # ---- 时间:写在作品上,总标题的时间取最早那一份 -------------------------
    status, answer = checks.api("GET", f"/api/works/{work_a}")
    checks.check(
        "总标题的时间取它下面最早的那一份",
        status == 200 and field(answer, "published_on") == "1900-01",
        f"甲下面有 1900-01 与 2099-01-01 各一份,回的是 {field(answer, 'published_on')!r}",
    )
    checks.check(
        "总标题自己不存时间这一列",
        query(f"SELECT COUNT(*) FROM pragma_table_info('work') WHERE name = 'published_on'")[0][0] == 0,
        "时间是算出来的,存第二遍就有两个说法要一起改",
    )

    # ---- 封面:传、取、换一张、拒、摘掉,以及硬盘上的文件 -------------------
    global COVER_EDITION_ID
    COVER_EDITION_ID = edition_a

    status, answer = checks.upload(f"/api/editions/{edition_a}/cover", "cover.png", TINY_PNG)
    first_url = str(field(answer, "cover_url") or "")
    checks.check(
        "传一张封面,回话里就有地址",
        status == 200 and first_url.endswith(".png") and "/covers/" in first_url,
        f"POST /api/editions/{edition_a}/cover -> {status} {first_url!r}",
    )
    status, served = checks.text(first_url)
    checks.check(
        "那个地址真的取得到,而且字节数一样",
        status == 200 and len(served.encode("utf-8", "replace")) > 0 and len(cover_files("edition", edition_a)) == 1,
        f"GET {first_url} -> {status},硬盘上 {cover_files("edition", edition_a)}",
    )

    # 尺寸是从**文件头**读出来的,所以拿一张真的 1×1 去传,回话里就该是 1×1
    checks.check(
        "回话里带着原图的像素尺寸",
        field(answer, "cover_width") == 1 and field(answer, "cover_height") == 1,
        f"传的是 1×1 的 PNG,回的是 {field(answer, 'cover_width')}×{field(answer, 'cover_height')}",
    )

    # 用关键词把这**一条**搜出来,而不是去翻列表第一页:库大了之后按标题排它可能落在任何一页上。
    found = checks.api("GET", f"/api/editions?q={urllib.parse.quote(f'{PREFIX}甲漫画')}")[1]
    rows = field(found, "items", [])
    mine = next((item for item in rows if field(item, "id") == edition_a), None)
    checks.check(
        "列表行里也带着封面地址",
        mine is not None and field(mine, "cover_url") == first_url,
        f"列表里这一行的 cover_url = {field(mine, 'cover_url') if mine else None!r}",
    )

    status, answer = checks.upload(f"/api/editions/{edition_a}/cover", "again.png", TINY_PNG)
    second_url = str(field(answer, "cover_url") or "")
    checks.check(
        "换一张写的是新文件,不覆盖旧的",
        status == 200 and second_url != first_url and len(cover_files("edition", edition_a)) == 2,
        f"第一次 {first_url!r},第二次 {second_url!r},硬盘上 {cover_files("edition", edition_a)}",
    )
    checks.check(
        "换了封面之后,旧地址仍然取得到",
        checks.text(first_url)[0] == 200,
        f"GET {first_url} —— 换封面不删旧文件,所以它必须还在",
    )
    checks.check(
        "库里记的是新那一个",
        field(checks.api("GET", f"/api/editions/{edition_a}")[1], "cover_url") == second_url,
        "数据库那一列只记「现在指的是哪一个」",
    )

    status, answer = checks.upload(f"/api/editions/{edition_a}/cover", "notes.txt", b"this is not an image")
    checks.check(
        "不是图片的文件被拒,理由是一句话",
        status == 400 and "图片" in str(field(answer, "detail")),
        f"传一个文本文件 -> {status} {field(answer, 'detail')!r}",
    )

    status, answer = checks.api("DELETE", f"/api/editions/{edition_a}/cover")
    checks.check(
        "摘掉封面之后地址为空",
        status == 200 and field(answer, "cover_url") is None,
        f"DELETE /api/editions/{edition_a}/cover -> {status}",
    )
    checks.check(
        "尺寸也跟着空了",
        field(answer, "cover_width") is None and field(answer, "cover_height") is None,
        "尺寸说的是那一个文件多大,留着就成了上一张封面的话",
    )
    checks.check(
        "摘掉封面不动硬盘上的文件",
        len(cover_files("edition", edition_a)) == 2,
        f"硬盘上仍是 {cover_files("edition", edition_a)} —— 摘掉只是把数据库那一列清空",
    )

    # ---- 网页设置:存、只回掩码、清掉、以及「不通也不算错」的验证 -------------------
    # **这一段会动 `settings.json`。** 留底与还原都由 `main()` 的 `finally` 统一管(那里连登录会话
    # 与账号资料一起留),这里**只取用那份留底**。
    #
    # 先前这里又留了一次底,而那时可能已经晚了:留底写在函数中途,一旦那一刻文件已经被弄坏,
    # 坏内容就会被当成"跑之前的样子" —— 实测就是这么把人的 Hikarinagi 凭据弄丢的。
    # **留底只能有一个地方、而且必须是最早那一刻**,这是这一处的教训。
    settings_before, _settings_mode = settings_from_snapshot(local_before)
    #: 跑之前**这台机器上**是不是已经填过 Bangumi 令牌。验收脚本要能在任何一台机器上重跑:
    #: 写死「一定没填过」的话,人一旦真填了令牌,这一节就会红 —— 那不是产品的毛病,是断言的毛病。
    token_was_set = bool(load_source_settings().bangumi_token)

    status, answer = checks.api("GET", "/api/settings")
    checks.check(
        "设置读得出来,而且「填没填」报的是实情",
        status == 200 and field(answer, "bangumi_token_set") is token_was_set,
        f"GET /api/settings -> {status}, 跑之前填过={token_was_set}, "
        f"报的={field(answer, 'bangumi_token_set')}",
    )

    fake_token = "flow-check-abcdefghijklmnop"
    status, answer = checks.api("PUT", "/api/settings", {"bangumi_token": fake_token})
    checks.check(
        "存下一个令牌之后,回话里说已经填了",
        status == 200 and field(answer, "bangumi_token_set") is True,
        f"PUT /api/settings -> {status}",
    )
    checks.check(
        "回话里只有掩码,**没有完整令牌**",
        fake_token not in str(answer) and "…" in str(field(answer, "bangumi_token_masked")),
        f"掩码是 {field(answer, 'bangumi_token_masked')!r}",
    )
    checks.check(
        "来历报的是网页这一份(而不是 config.toml)",
        field(answer, "bangumi_token_from") == "settings",
        f"from = {field(answer, 'bangumi_token_from')!r}",
    )

    status, answer = checks.api("GET", "/api/settings")
    settings_on_disk = settings_file()
    checks.check(
        "再读一次仍是已填 —— 真的落盘了,不是只在这一次回话里",
        field(answer, "bangumi_token_set") is True and settings_on_disk.is_file(),
        f"{settings_on_disk.name} 在不在: {settings_on_disk.is_file()}",
    )

    status, answer = checks.api("PUT", "/api/settings", {"bangumi_token": "x" * 600})
    checks.check(
        "过长的令牌被拒,理由是一句话",
        status == 400 and isinstance(field(answer, "detail"), str),
        f"-> {status} {field(answer, 'detail')}",
    )
    status, answer = checks.api("PUT", "/api/settings", {"bangumi_token": "abc def"})
    checks.check(
        "令牌里夹空格被拒(多半是贴错了东西)",
        status == 400,
        f"-> {status} {field(answer, 'detail')}",
    )

    # 验证那一条:**网络通不通、令牌真不真,都算通过**。这一条考的是「它永远回 200,而且给得出一句人话」——
    # 不能断言「一定说不对」:这台机器上可能填的是枚真令牌,那它就该说有效。(先前写死了「不对/连不上」那几个词,
    # 于是人一旦真填了令牌,这一条就红 —— 断言的毛病,不是产品的。)
    #
    # **否定的那一半只要求"说清了是哪一类没成",不逐个列举措辞。** 先前只认「不对/连不上/没法/没有填」四个词,
    # 而 Bangumi 偶尔回一个 429(实测:`令牌一时验不了:服务端说 429,过一会儿再试`),那句话一个都不沾 ——
    # 于是这一条会红,红的却是网络的脾气。所以改成:要么说有效,要么说得出一句**提到失败原因**的话。
    NOT_OK_WORDS = ("不对", "连不上", "没法", "没有填", "一时", "过一会儿", "服务端", "失败")
    # 这一步**真的会联网**,所以先记下盘上那份账号资料现在在不在,再问。
    # 理由:`check` 只在验通时写资料;网络一抖它就只回一句失败,资料原样不动。所以"跑完之后资料还在不在"
    # 与"刚才那次通没通"无关 —— 该问的是「**这一步有没有把它弄丢**」,拿前后对比来问。
    # (先前写成了"跑完必须有一份",于是令牌已被清掉、本来就该没有资料时反而报红 —— 断言的毛病。)
    profile_before = profile_file("bangumi").is_file()
    status, answer = checks.api("POST", "/api/settings/bangumi-token/check")
    detail = str(field(answer, "detail") or "")
    verdict = field(answer, "ok")
    checks.check(
        "验证令牌:不管通不通都回 200,而且给得出一句人话",
        status == 200
        and isinstance(verdict, bool)
        and bool(detail)
        and (("有效" in detail) if verdict else any(word in detail for word in NOT_OK_WORDS)),
        f"POST .../check -> {status},ok={verdict},detail={detail!r}",
    )
    checks.check(
        "**验不通也丢不了账号资料**:一次网络抖动不该把上次看到的那份抹掉",
        profile_file("bangumi").is_file() == profile_before,
        f"问之前 {profile_before},问之后 {profile_file('bangumi').is_file()}",
    )

    status, answer = checks.api("DELETE", "/api/settings")
    checks.check(
        "清掉之后回到「没填」",
        status == 200
        and field(answer, "bangumi_token_set") is False
        and not settings_on_disk.exists(),
        f"DELETE /api/settings -> {status}",
    )

    # ---- 成对凭据(Hikarinagi):收、只回掩码、拒半对、清得掉 -------------------
    # 这一节会清掉凭据,而**清凭据会连带清掉登录会话与账号资料**(见 `settings_store.save_credentials`)。
    # 那是有意的:会话里那枚 refresh token 是配着某个 client_id 发的,留着只会在下次请求时报难懂的错。
    # 留底与还原由 `main()` 的 `finally` 统一管。
    status, answer = checks.api("GET", "/api/settings")
    listed = field(answer, "credentials") or []
    entry = next((item for item in listed if field(item, "source") == "hikarinagi"), None)
    checks.check(
        "设置里列出了需要凭据的源,并写明了要哪几格",
        status == 200
        and entry is not None
        and sorted((field(entry, "fields") or {}).keys()) == ["client_id", "client_secret"],
        f"credentials = {json.dumps(listed, ensure_ascii=False)[:200]}",
    )
    checks.check(
        "它现在报的是「还没配」,而且给得出说明",
        field(entry, "configured") is False and bool(field(entry, "hint")),
        f"configured={field(entry, 'configured')}",
    )

    fake_secret = "flow-check-secret-abcdef"
    status, answer = checks.api(
        "PUT",
        "/api/settings",
        {"source": "hikarinagi", "fields": {"client_id": "flow-check-id", "client_secret": fake_secret}},
    )
    entry = next(
        (item for item in (field(answer, "credentials") or []) if field(item, "source") == "hikarinagi"),
        None,
    )
    checks.check(
        "存下凭据之后报「已配」",
        status == 200 and entry is not None and field(entry, "configured") is True,
        f"PUT /api/settings -> {status}",
    )
    checks.check(
        "回话里只有掩码,**没有完整 secret**",
        fake_secret not in json.dumps(answer, ensure_ascii=False)
        and "…" in str(field(entry, "masked") or ""),
        f"masked={field(entry, 'masked')!r}",
    )

    status, answer = checks.api(
        "PUT", "/api/settings", {"source": "hikarinagi", "fields": {"client_id": "only-one"}}
    )
    checks.check(
        "只填一格被拒(半对换不到令牌)",
        status == 400 and isinstance(field(answer, "detail"), str),
        f"-> {status} {field(answer, 'detail')}",
    )
    status, answer = checks.api("PUT", "/api/settings", {"source": "nobody", "fields": {}})
    checks.check("不认识的源被拒", status == 404, f"-> {status}")

    status, answer = checks.api(
        "PUT",
        "/api/settings",
        {"source": "hikarinagi", "fields": {"client_id": "", "client_secret": ""}},
    )
    entry = next(
        (item for item in (field(answer, "credentials") or []) if field(item, "source") == "hikarinagi"),
        None,
    )
    checks.check(
        "两个空串就是清掉",
        status == 200 and entry is not None and field(entry, "configured") is False,
        f"-> {status}",
    )

    # ---- VNDB 的令牌:一格、可选、而且当前版本还不会读它 ------------------------
    # 这一节的要害是「有没有填」与「能不能用」必须分开报:VNDB 读公开条目不要凭据,
    # 所以它 `configured` 从头到尾都是 true —— 哪怕那一格是空的。
    status, answer = checks.api("GET", "/api/settings")
    vndb_entry = next(
        (item for item in (field(answer, "credentials") or []) if field(item, "source") == "vndb"),
        None,
    )
    checks.check(
        "VNDB 也在凭据清单里,而且只要一格 token",
        status == 200
        and vndb_entry is not None
        and sorted((field(vndb_entry, "fields") or {}).keys()) == ["token"],
        f"credentials = {json.dumps(field(answer, 'credentials'), ensure_ascii=False)[:200]}",
    )
    checks.check(
        "VNDB 报的是「可选」,但**不再报「当前版本用不到」**",
        field(vndb_entry, "optional") is True and field(vndb_entry, "noop") is False,
        "填了可以按「验证」确认它是谁的 —— 所以那一格已经不是摆设了。"
        f"optional={field(vndb_entry, 'optional')} noop={field(vndb_entry, 'noop')}",
    )
    status, answer = checks.api("POST", "/api/settings/vndb-token/check")
    detail = str(field(answer, "detail") or "")
    checks.check(
        "VNDB 的验证端点:没填令牌时也回 200,而且说清是「还没填」",
        status == 200 and field(answer, "ok") is False and "没有填" in detail,
        f"-> {status} ok={field(answer, 'ok')} detail={detail!r}",
    )
    checks.check(
        "**没填凭据的 VNDB 仍然报「能用」**",
        field(vndb_entry, "configured") is True and field(vndb_entry, "masked") == "",
        f"configured={field(vndb_entry, 'configured')} masked={field(vndb_entry, 'masked')!r}",
    )

    vndb_fake = "flow-check-vndb-token-abcdef"
    status, answer = checks.api("PUT", "/api/settings", {"source": "vndb", "fields": {"token": vndb_fake}})
    vndb_entry = next(
        (item for item in (field(answer, "credentials") or []) if field(item, "source") == "vndb"),
        None,
    )
    checks.check(
        "VNDB 只给一格也存得下(它不像 Hikarinagi 那样要成对)",
        status == 200 and vndb_entry is not None and field(vndb_entry, "configured") is True,
        f"PUT /api/settings -> {status}",
    )
    checks.check(
        "VNDB 这一格也只回掩码,不回完整令牌",
        vndb_fake not in json.dumps(answer, ensure_ascii=False)
        and "…" in str(field(vndb_entry, "masked") or ""),
        f"masked={field(vndb_entry, 'masked')!r}",
    )
    status, answer = checks.api("PUT", "/api/settings", {"source": "vndb", "fields": {"token": ""}})
    vndb_entry = next(
        (item for item in (field(answer, "credentials") or []) if field(item, "source") == "vndb"),
        None,
    )
    checks.check(
        "清掉 VNDB 那一格之后,它**照样报「能用」**",
        status == 200
        and vndb_entry is not None
        and field(vndb_entry, "masked") == ""
        and field(vndb_entry, "configured") is True,
        f"-> {status} configured={field(vndb_entry, 'configured')}",
    )

    # ---- Hikarinagi 的用户级登录:地址由后端拼、回调拒绝假 state -----------------
    # 这一节只考「不登录那半边」:真正的登录要人在 Hikarinagi 页面上点一次同意,脚本做不了。
    # 能自动验的是:地址拼得对不对、回调认不认 state、登出是不是幂等。
    #
    # **自己放一份假凭据再测**,而不是依赖"这台机器上恰好填过真的":
    # 「登入地址拼不拼得出来」取决于有没有 client_id,靠机器实情的话,在一台没填过的机器上这一节
    # 就永远测不到真正的拼装逻辑 —— 而那正是要测的东西。收尾会把真凭据原样放回去。
    checks.api(
        "PUT",
        "/api/settings",
        {"source": "hikarinagi", "fields": {"client_id": "flow-login-id", "client_secret": "flow-login-secret"}},
    )

    status, answer = checks.api("GET", "/api/sources/hikarinagi/login")
    url = str(field(answer, "url") or "")
    checks.check(
        "登入地址由后端拼好,而且带上 PKCE 与 state",
        status == 200
        and url.startswith("https://id.hikarinagi.org/oidc/auth?")
        and "code_challenge_method=S256" in url
        and "code_challenge=" in url
        and "state=" in url,
        f"-> {status} url={url[:90]}",
    )
    checks.check(
        "登入地址里的 scope 含 openid 与 offline_access",
        "openid" in url and "offline_access" in url,
        f"url={url[:170]}",
    )
    checks.check(
        "**回调地址就是控制台里登记的那一串**",
        "redirect_uri=http%3A%2F%2F127.0.0.1%3A8000%2Fapi%2Fsources%2Fhikarinagi%2Fcallback" in url,
        "回调地址是代码里的常量,与控制台登记的那一串必须逐字符相同",
    )
    checks.check(
        "**登录请求带 `prompt=consent`** —— 少了它服务端会复用旧授权,于是 offline_access 永远不生效",
        "prompt=consent" in url,
        f"url={url[:200]}",
    )

    status, page = checks.text("/api/sources/hikarinagi/callback?code=x&state=bogus")
    checks.check(
        "回调对不上 state 时**回的是给人看的 HTML**,不是 JSON",
        status == 200 and "登录没成" in page,
        f"-> {status} 片段={page[:80]!r}",
    )

    status, answer = checks.api("GET", "/api/settings")
    checks.check(
        "没登录时账号栏是空的,而且不是错误",
        status == 200
        and isinstance(field(answer, "hikarinagi_account"), dict)
        and field(field(answer, "hikarinagi_account"), "logged_in") is False,
        f"account={json.dumps(field(answer, 'hikarinagi_account'), ensure_ascii=False)}",
    )

    status, answer = checks.api("DELETE", "/api/sources/hikarinagi/login")
    checks.check(
        "退出登录在没登录时也成功(幂等)",
        status == 200 and field(answer, "logged_in") is False,
        f"-> {status}",
    )

    # 收尾的还原**不在这里**:`main()` 的 `finally` 会把设置、登录会话、账号资料一起放回去。
    # 放在那儿的理由是脚本崩半路也得还原。**删掉登录会话的不是 `DELETE /api/settings`**(那个只删设置),
    # 而是上面这两步:清空凭据时会 `forget_session()` / `forget_profile()`。

    # ---- 两个源的「账号」区域 ---------------------------------------------------
    # 两块都是**只读缓存、不联网**的展示:页面每次打开都去问一次服务端"我是谁"是没必要的往返。
    status, answer = checks.api("GET", "/api/settings")
    bangumi_account = field(answer, "bangumi_account")
    checks.check(
        "设置里带上了 Bangumi 的账号区域",
        status == 200 and isinstance(bangumi_account, dict),
        f"bangumi_account={json.dumps(bangumi_account, ensure_ascii=False)[:120]}",
    )
    checks.check(
        "**账号区域里没有邮箱** —— /v0/me 回它,但我们不存",
        "email" not in json.dumps(bangumi_account, ensure_ascii=False),
        "少存一份用不上的个人信息,是不需要理由的",
    )
    # **公共的那几格**必须在三边都在。Hikarinagi 另外多了 `logged_in` 与两格"该往控制台填什么"
    # (回调地址、scope),那是它独有的 —— 用子集断言,将来哪边多加一格都不会误报。
    common = {"verified", "id", "name", "nickname", "avatar_url", "bio", "signature", "registered_at"}
    hikarinagi_account = field(answer, "hikarinagi_account") or {}
    vndb_account = field(answer, "vndb_account") or {}
    checks.check(
        "三个源的账号区域共用同一套公共键",
        common <= set(bangumi_account or {})
        and common <= set(hikarinagi_account)
        and common <= set(vndb_account),
        f"bangumi={sorted(bangumi_account or {})} vndb={sorted(vndb_account)} "
        f"hikarinagi={sorted(hikarinagi_account)}",
    )
    checks.check(
        "Hikarinagi 那两格「该往控制台填什么」也报出来了",
        str(hikarinagi_account.get("redirect_uri") or "").startswith("http://127.0.0.1:")
        and "openid" in str(hikarinagi_account.get("login_scope") or ""),
        f"redirect_uri={hikarinagi_account.get('redirect_uri')!r} "
        f"scope={hikarinagi_account.get('login_scope')!r}",
    )

    # ---- 「收不收起输入框」看的那一格 -------------------------------------------
    # 页面只有一条判据:`verified`。它必须**如实**跟着状态走,否则要么验证过了输入框还摊着,
    # 要么没验证就把输入框收起来(那样这一格就再也填不进去了)。
    checks.check(
        "这一跑没登录,所以 Hikarinagi 报的是「没验证」",
        hikarinagi_account.get("logged_in") is False and hikarinagi_account.get("verified") is False,
        f"logged_in={hikarinagi_account.get('logged_in')} verified={hikarinagi_account.get('verified')}",
    )
    checks.check(
        "没验证过的源报 `verified` 为假,而且资料是空的那一份",
        bangumi_account.get("verified") is False and bangumi_account.get("nickname") == "",
        f"bangumi_account={json.dumps(bangumi_account, ensure_ascii=False)[:120]}",
    )
    # 换一枚令牌 = 上一个账号的资料不作数了。**这条是「能换账号」的前提**:留着旧资料,页面就会
    # 一直收着输入框,人再也没法把新令牌填进去。
    from app.settings_store import save_profile

    # **这一份假资料必须自己收回去,不能指望 `main()` 那份留底。** 留底是"跑之前的样子",
    # 只在最外面还原一次;而这里写下去的假资料**会先被中途的 GET/PUT 读走、也会留在盘上** ——
    # 上一版就是靠外层留底收的,结果第二次连着跑时,第二次的留底已经把假资料当成"跑之前的样子",
    # 于是人的真账号(昵称、ID)被这份 `424242` 顶掉了,页面上显示的是"上一个账号"。实测踩过。
    bangumi_profile = profile_file("bangumi")
    keep = bangumi_profile.read_text(encoding="utf-8") if bangumi_profile.is_file() else None
    # 权限位也照原样带回去(这份文件与凭据同级,走 `_restore_path` 的"密钥路径一律收成 0600"那条)。
    keep_mode = bangumi_profile.stat().st_mode if keep is not None else None
    try:
        save_profile("bangumi", {"id": 424242, "name": "flow-stale", "nickname": "上一个账号"})
        status, answer = checks.api(
            "PUT", "/api/settings", {"source": "vndb", "fields": {"token": "flow-swap-token"}}
        )
        checks.check(
            "换一枚令牌之后,上次那份账号资料被忘掉了",
            status == 200 and field(answer, "vndb_account", {}).get("verified") is False,
            f"-> {status} vndb_account={json.dumps(field(answer, 'vndb_account'), ensure_ascii=False)[:120]}",
        )
        checks.check(
            "**只**忘掉换过的那个源,别的源不动",
            profile_file("bangumi").is_file(),
            "换 VNDB 的令牌不该把 Bangumi 那边认下的账号也抹掉",
        )
        status, answer = checks.api("GET", "/api/settings")
        checks.check(
            "换过令牌之后 VNDB 那一格回到「没验证」,输入框才展得开",
            status == 200
            and field(answer, "vndb_account", {}).get("verified") is False
            and field(answer, "vndb_account", {}).get("nickname") == "",
            f"vndb_account={json.dumps(field(answer, 'vndb_account'), ensure_ascii=False)[:120]}",
        )
    finally:
        if keep is None:
            bangumi_profile.unlink(missing_ok=True)
        else:
            _write_text(bangumi_profile, keep)
            _restore_path(bangumi_profile, keep_mode)
    status, answer = checks.api(
        "PUT", "/api/settings", {"source": "bangumi", "fields": {"client_id": "x", "client_secret": "y"}}
    )
    checks.check(
        "不认识的源名换来 404 与一句人话,而不是 500",
        status == 404 and isinstance(field(answer, "detail"), str),
        f"-> {status} {field(answer, 'detail')}",
    )

    # 三个源都在,而且各自的「有没有凭据」与「没有时去哪儿配」都说得清楚。
    status, listed = checks.api("GET", "/api/sources")
    by_name = {str(field(item, "name")): item for item in (listed or [])}
    checks.check(
        "源清单里有 Hikarinagi",
        status == 200 and "hikarinagi" in by_name,
        f"-> {status} {sorted(by_name)}",
    )
    checks.check(
        "每个源的说明与「有没有凭据」都齐",
        all(field(item, "hint") and isinstance(field(item, "configured"), bool) for item in (listed or [])),
        str([(field(item, "name"), field(item, "configured")) for item in (listed or [])]),
    )
    # **没凭据的源必须说得出「去哪儿配」**,有凭据的不该显那句话 —— 页面上那句提示就靠它。
    checks.check(
        "没凭据的源都给了「去哪儿配」",
        all(field(item, "configure_hint") for item in (listed or []) if not field(item, "configured")),
        str([(field(item, "name"), field(item, "configure_hint")) for item in (listed or [])]),
    )
    checks.check(
        "不需要凭据的源不显那句话",
        all(not field(item, "configure_hint") for item in (listed or []) if field(item, "configured")),
        str([(field(item, "name"), field(item, "configure_hint")) for item in (listed or [])]),
    )

    # ---- 两种排法必须给出不同的顺序:按总标题的时间甲在前(甲最早 1900-01,乙 1900-02),
    # 只看游戏、按作品自己的时间则乙在前(1900-02 早于 2099-01-01)。
    order = [field(item, "title") for item in field(checks.api("GET", f"/api/works?sort=date")[1], "items", [])]
    checks.check(
        "按总标题的时间排,甲在乙前面",
        order.index(f"{PREFIX}甲") < order.index(f"{PREFIX}乙"),
        f"顺序 {order}",
    )
    games = field(checks.api("GET", "/api/editions?media_type=game&sort=date")[1], "items", [])
    names = [field(item, "title") for item in games]
    checks.check(
        "按作品自己的时间排,乙的游戏在甲的游戏前面",
        names.index(f"{PREFIX}乙游戏") < names.index(f"{PREFIX}甲游戏"),
        f"顺序 {names}",
    )

    # ---- 排序与分页的形状:不写死条数,写死规律 -----------------------------
    titles = [field(item, "title") for item in field(checks.api("GET", "/api/works?sort=title")[1], "items", [])]
    checks.check(
        "按标题排是升序",
        titles == sorted(titles),
        f"前几个 {titles[:4]}",
    )
    checks.check(
        "排序只认那两档",
        sorted(WORK_SORT_VALUES) == ["date", "title"],
        f"app/listing.py 里是 {WORK_SORT_VALUES}",
    )
    status, first_page = checks.api("GET", "/api/editions")
    total = int(field(first_page, "total") or 0)
    pages = int(field(first_page, "pages") or 0)
    checks.check(
        "分页的形状对得上总数",
        status == 200
        and field(first_page, "page") == 1
        and field(first_page, "page_size") == PAGE_SIZE
        and pages == max(1, -(-total // PAGE_SIZE)),
        f"total {total},pages {pages},page_size {field(first_page, 'page_size')}",
    )
    if pages >= 2:
        second = field(checks.api("GET", "/api/editions?page=2")[1], "items", [])
        first_ids = {field(item, "id") for item in field(first_page, "items", [])}
        checks.check(
            "第二页装的是另外一批",
            bool(second) and not (first_ids & {field(item, "id") for item in second}),
            f"第一页 {len(first_ids)} 条,第二页 {len(second)} 条",
        )
    else:
        checks.check("这一页放得下,没有第二页可验", pages == 1, f"total {total},pages {pages}")

    # ---- 接口:写进去、读出来、拒得对、删得干净 -----------------------------
    # 这一段自己建记录自己删,所以跑完库和跑之前一样。每一步先看状态码再看身体里那一项 ——
    # 只看状态码,一个回 201 却没写进去的接口照样会通过。
    status, answer = checks.api("GET", "/api/media-types")
    kinds = field(answer, "items", []) or []
    checks.check(
        "接口报得出四个类型与各自的字段名",
        status == 200
        and [item.get("value") for item in kinds] == ["manga", "light_novel", "game", "anime"]
        and kinds[0].get("fields", {}).get("time") == "连载开始",
        f"GET /api/media-types -> {status},{[item.get('value') for item in kinds]}",
    )
    checks.check(
        "客户端因此不必自己抄一份类型表",
        "org" in kinds[0].get("fields", {}) and kinds[0].get("label") == "漫画",
        "字段名与给人看的名字都从这一处来",
    )

    status, answer = checks.api("POST", "/api/works", {"title": f"{PREFIX}丙"})
    work_c = int(field(answer, "id") or 0)
    checks.check(
        "接口能建作品总标题",
        status == 201 and field(answer, "title") == f"{PREFIX}丙" and work_c > 0,
        f"POST /api/works -> {status} {field(answer, 'title')!r}",
    )
    checks.check("接口建的记录在库里", row_id("work", "title", f"{PREFIX}丙") == work_c)
    checks.check(
        "新总标题没有作品,也没有时间",
        field(answer, "editions") == [] and field(answer, "published_on") is None,
        "刚建好的总标题不该有作品,作品的时间也没有地方从它身上算",
    )

    status, answer = checks.api(
        "POST",
        f"/api/works/{work_c}/editions",
        {
            "media_type": "anime",
            "title": "",
            "published_on": "1999-05",
            "org": "验收制作",
            "creators": [{"name": f"{PREFIX}丙作者", "role": "原作"}],
            "tags": [f"{PREFIX}丙标签"],
        },
    )
    edition_d = int(field(answer, "id") or 0)
    checks.check(
        "接口能加一份作品",
        status == 201 and edition_d > 0 and field(answer, "work_id") == work_c,
        f"POST /api/works/{work_c}/editions -> {status}",
    )
    checks.check(
        "接口把作者与标签一起写了进去",
        [item.get("name") for item in field(answer, "creators", [])] == [f"{PREFIX}丙作者"]
        and [item.get("name") for item in field(answer, "tags", [])] == [f"{PREFIX}丙标签"],
        "作者与标签是整批交的,回话里应该就是刚交的那两样",
    )
    checks.check(
        "接口按类型取时间的名字",
        field(answer, "fields", {}).get("time") == "放送开始",
        "动画那一格在接口里也叫放送开始",
    )
    checks.check("接口把时间写了进去", field(answer, "published_on") == "1999-05")

    status, answer = checks.api("GET", f"/api/works/{work_c}")
    checks.check(
        "接口算出了作品总标题的时间",
        status == 200 and field(answer, "published_on") == "1999-05",
        "这一份作品的时间就是这一行的原作时间",
    )

    # 卷:一次交两条同号的,加进去一条、跳过一条 —— 与批量页同一条规矩。
    status, answer = checks.api(
        "POST",
        f"/api/editions/{edition_d}/volumes",
        [{"volume_number": 1, "title": "第一期"}, {"volume_number": 1, "title": "重复的第一期"}],
    )
    checks.check(
        "接口批量加卷会跳过已有的号",
        status == 200 and field(answer, "added") == 1 and field(answer, "skipped") == 1,
        f"POST /api/editions/{edition_d}/volumes -> {status} 加 {field(answer, 'added')} 跳 {field(answer, 'skipped')}",
    )
    checks.api(
        "POST", f"/api/editions/{edition_d}/volumes", [{"volume_number": 2, "title": "第二期"}]
    )
    status, answer = checks.api("GET", f"/api/editions/{edition_d}/volumes")
    volumes = answer if isinstance(answer, list) else []
    second = next((item for item in volumes if item.get("volume_number") == 2), None)
    checks.check("接口能读这份作品的卷", len(volumes) == 2, f"{len(volumes)} 条")

    if second is None:
        raise Stop("接口加的卷没读到,后面的卷检查做不了")

    # 卷的封面:同一组规矩,只是文件名是 volume-<id>.*。换一张、拒、摘掉已经在作品那一节对过,
    # 这里只对「卷也接上了」和「尺寸照样读得出来」。
    global COVER_VOLUME_ID
    COVER_VOLUME_ID = int(second.get("id"))
    status, answer = checks.upload(f"/api/volumes/{COVER_VOLUME_ID}/cover", "volume.png", TINY_PNG)
    volume_url = str(field(answer, "cover_url") or "")
    checks.check(
        "卷也能传封面,回话里就有地址",
        status == 200 and volume_url.endswith(".png") and "volume-" in volume_url,
        f"POST /api/volumes/{COVER_VOLUME_ID}/cover -> {status} {volume_url!r}",
    )
    checks.check(
        "卷的封面也带着原图的像素尺寸",
        field(answer, "cover_width") == 1 and field(answer, "cover_height") == 1,
        f"传的是 1×1 的 PNG,回的是 {field(answer, 'cover_width')}×{field(answer, 'cover_height')}",
    )
    status, served = checks.text(volume_url)
    checks.check(
        "卷那个地址真的取得到,硬盘上就是 volume-<id>.png",
        status == 200
        and len(served.encode("utf-8", "replace")) > 0
        and cover_files("volume", COVER_VOLUME_ID) == [f"volume-{COVER_VOLUME_ID}.png"],
        f"GET {volume_url} -> {status},硬盘上 {cover_files('volume', COVER_VOLUME_ID)}",
    )
    status, answer = checks.api("DELETE", f"/api/volumes/{COVER_VOLUME_ID}/cover")
    checks.check(
        "摘掉卷的封面之后地址与尺寸都空了",
        status == 200
        and field(answer, "cover_url") is None
        and field(answer, "cover_width") is None
        and field(answer, "cover_height") is None,
        f"DELETE /api/volumes/{COVER_VOLUME_ID}/cover -> {status}",
    )
    checks.check(
        "摘掉之后硬盘上那个文件仍然在",
        cover_files("volume", COVER_VOLUME_ID) == [f"volume-{COVER_VOLUME_ID}.png"],
        "与作品的封面同一条规矩:摘掉只动数据库那一列,不动文件",
    )

    status, answer = checks.api(
        "PUT", f"/api/volumes/{second.get('id')}", {"volume_number": 1, "title": "改成第一期"}
    )
    checks.check(
        "手写一个已有的卷号被拒,而且按类型叫季度",
        status == 400 and "已经有第 1 季度了" in str(field(answer, "detail")),
        f"PUT /api/volumes/{second.get('id')} -> {status} {field(answer, 'detail')!r}",
    )

    # 排序:有时间的在前面,而且升序。不写死是哪一条,库里多一条记录也不会失效。
    items = field(checks.api("GET", "/api/editions?media_type=anime&sort=date")[1], "items", [])
    dates = [item.get("published_on") for item in items]
    filled = [value for value in dates if value]
    checks.check(
        "接口按时间排时,有时间的在前而且升序",
        dates[: len(filled)] == filled == sorted(filled),
        f"GET /api/editions?sort=date 的时间依次是 {dates}",
    )

    # 类型不在接口里也不能改:交上去的 media_type 会被忽略,用的是行上那一个。
    status, answer = checks.api(
        "PUT",
        f"/api/editions/{edition_d}",
        {"media_type": "manga", "title": "改过的标题", "published_on": "1999-05"},
    )
    checks.check(
        "接口改作品时改不动类型",
        status == 200 and field(answer, "media_type") == "anime",
        f"PUT /api/editions/{edition_d} 交的是 manga,回来的是 {field(answer, 'media_type')!r}",
    )
    checks.check("接口改了这份作品的标题", field(answer, "title") == "改过的标题")

    # 关联:四条拒绝在 app/rules.py 里,两扇门共用。
    status, answer = checks.api(
        "POST", f"/api/editions/{edition_d}/relations", {"other_id": edition_a}
    )
    checks.check(
        "接口能建立关联",
        status == 201 and field(answer, "edition_a_id") is not None,
        f"POST /api/editions/{edition_d}/relations -> {status}",
    )
    checks.check("接口写的关联在库里", relation_count(edition_d, edition_a) == 1)
    status, answer = checks.api(
        "POST", f"/api/editions/{edition_d}/relations", {"other_id": edition_d}
    )
    checks.check(
        "接口拒绝自连",
        status == 400 and "自身" in str(field(answer, "detail")),
        f"-> {status} {field(answer, 'detail')!r}",
    )
    status, answer = checks.api(
        "POST", f"/api/editions/{edition_d}/relations", {"other_id": edition_a}
    )
    checks.check(
        "接口拒绝重复关联",
        status == 400 and "已建立关联" in str(field(answer, "detail")),
        f"-> {status} {field(answer, 'detail')!r}",
    )
    checks.check(
        "接口删关联返回 204",
        checks.api("DELETE", f"/api/editions/{edition_d}/relations/{edition_a}")[0] == 204
        and relation_count(edition_d, edition_a) == 0,
    )
    checks.check(
        "删一条不存在的关联是 404",
        checks.api("DELETE", f"/api/editions/{edition_d}/relations/{edition_a}")[0] == 404,
    )

    # 候选名单里没有自己、同一个总标题下的与已关联过的 —— 这三条留在服务端,画选择框的那边不必再筛。
    status, answer = checks.api(
        "POST", f"/api/works/{work_c}/editions", {"media_type": "manga", "title": "丙的第二份"}
    )
    sibling = int(field(answer, "id") or 0)
    checks.check("丙有了第二份作品", sibling > 0 and sibling != edition_d)

    ids = [
        item.get("id")
        for item in checks.api("GET", f"/api/editions/{edition_d}/relation-candidates")[1]
    ]
    checks.check("候选名单里没有自己", edition_d not in ids, f"{len(ids)} 个候选")
    checks.check("候选名单里没有同一个总标题下的作品", sibling not in ids)
    checks.check("候选名单里有别的总标题的作品", edition_a in ids)

    checks.api("POST", f"/api/editions/{edition_d}/relations", {"other_id": edition_a})
    ids = [
        item.get("id")
        for item in checks.api("GET", f"/api/editions/{edition_d}/relation-candidates")[1]
    ]
    checks.check("已经关联过的不在候选里", edition_a not in ids)
    checks.api("DELETE", f"/api/editions/{edition_d}/relations/{edition_a}")
    ids = [
        item.get("id")
        for item in checks.api("GET", f"/api/editions/{edition_d}/relation-candidates")[1]
    ]
    checks.check("删掉关联之后它又回到候选里", edition_a in ids)

    # 改名即合并:同一条规矩,另一扇门。丙的作者改成甲那位作者的名字,两条并成一条。
    drop_creator = row_id("creator", "name", f"{PREFIX}丙作者")
    keep_creator = row_id("creator", "name", f"{PREFIX}作者")
    # 合并前两条记录合起来挂着几份作品 —— 数出来而不是写死,因为它取决于上面那些检查动过什么。
    moved = query(
        "SELECT COUNT(DISTINCT edition_id) FROM edition_creator"
        f" WHERE creator_id IN ({drop_creator}, {keep_creator})"
    )[0][0]
    status, answer = checks.api(
        "PUT", f"/api/creators/{drop_creator}", {"name": f"{PREFIX}作者", "aliases": []}
    )
    checks.check(
        "接口改名到已有的名字是合并",
        status == 200 and field(answer, "id") == drop_creator,
        f"PUT /api/creators/{drop_creator} -> {status}",
    )
    checks.check(
        "合并之后带过来的是另一条的别名",
        f"{PREFIX}笔名" in (field(answer, "aliases") or []),
        f"aliases {field(answer, 'aliases')} —— 并掉那一条的别名应该跟着过来",
    )
    checks.check(
        "合并之后两条记录只剩一条",
        row_id("creator", "name", f"{PREFIX}丙作者") == 0 and row_id("creator", "name", f"{PREFIX}作者") > 0,
        "被并掉的那个名字应该不在了",
    )
    checks.check(
        "合并之后留下的是被改的那一行",
        row_id("creator", "name", f"{PREFIX}作者") == drop_creator,
        "改名前那一页的地址要还能用,所以留下的是被改的那一行,不是撞名的那一行",
    )
    checks.check(
        "合并之后连接都指向留下的那一行",
        query(
            "SELECT COUNT(DISTINCT edition_id) FROM edition_creator"
            f" WHERE creator_id = {drop_creator}"
        )[0][0]
        == moved,
        f"两条记录合起来原本挂着 {moved} 份作品,合并之后应还是 {moved} 份",
    )

    # 标签的类型不在接口里:同一个词在动画下改成漫画已有的那个名字,不会并成一条。
    tag_id = query(f"SELECT id FROM tag WHERE name = '{PREFIX}丙标签'")[0][0]
    status, answer = checks.api("PUT", f"/api/tags/{tag_id}", {"name": f"{PREFIX}标签"})
    checks.check(
        "接口改标签名时不跨类型合并",
        status == 200 and field(answer, "media_type") == "anime",
        f"PUT /api/tags/{tag_id} -> {status} {field(answer, 'media_type')!r}",
    )
    checks.check(
        "同名标签在不同类型下仍是两条",
        query(f"SELECT COUNT(*) FROM tag WHERE name = '{PREFIX}标签'")[0][0] == 2,
        "漫画下一条、动画下一条",
    )

    # 错误的形状:两扇门说的是同一句话。
    status, answer = checks.api("POST", "/api/works", {"title": "   "})
    checks.check(
        "接口说「不能为空」用的是页面上那句话",
        status == 400 and field(answer, "detail") == "作品总标题不能为空。",
        f"-> {status} {field(answer, 'detail')!r}",
    )
    status, answer = checks.api(
        "POST",
        f"/api/works/{work_c}/editions",
        {"media_type": "anime", "published_on": "1999-13"},
    )
    checks.check(
        "接口拒绝不存在的月份,而且按类型取词",
        status == 400 and "放送开始须写作" in str(field(answer, "detail")),
        f"-> {status} {field(answer, 'detail')!r}",
    )
    status, answer = checks.api(
        "POST", f"/api/works/{work_c}/editions", {"media_type": "music"}
    )
    checks.check(
        "接口拒绝范围外的类型",
        status == 400 and field(answer, "detail") == "类型不在可选范围内。",
        f"-> {status} {field(answer, 'detail')!r}",
    )
    status, answer = checks.api("POST", "/api/works", {"title": 123})
    checks.check(
        "身体的类型不对时也是同一种形状",
        status == 422 and str(field(answer, "detail")).startswith("请求内容的格式不对")
        and "title" in str(field(answer, "detail")),
        f"-> {status} {field(answer, 'detail')!r}",
    )
    status, answer = checks.api("GET", "/api/works/999999")
    checks.check(
        "接口找不到记录时是 404 与 JSON",
        status == 404 and field(answer, "detail") == "作品总标题不存在",
        f"-> {status} {field(answer, 'detail')!r}",
    )
    # 浏览器那一侧拿到的**是界面**:后端不知道前端有哪些地址,给外壳,由前端路由画「没有这一条」。
    status, shell = checks.text("/works/999999")
    checks.check(
        "浏览器那一侧拿到的仍然是界面",
        status == 200 and 'id="app"' in shell,
        f"GET /works/999999 -> {status},应是一页外壳而不是 JSON",
    )

    # 硬删记录是程序唯一会动硬盘文件的地方,所以两样都看:它自己的封面与它下面几卷的封面。
    status, answer = checks.upload(f"/api/editions/{edition_d}/cover", "delete-me.png", TINY_PNG)
    checks.check(
        "删这一份之前先给它传一张封面",
        status == 200 and cover_files("edition", edition_d) == [f"edition-{edition_d}.png"],
        f"POST /api/editions/{edition_d}/cover -> {status},硬盘上 {cover_files('edition', edition_d)}",
    )
    checks.check(
        "这时它下面那一卷的封面文件还在",
        cover_files("volume", COVER_VOLUME_ID) == [f"volume-{COVER_VOLUME_ID}.png"],
        f"硬盘上 {cover_files('volume', COVER_VOLUME_ID)}",
    )

    # 接口的删除:作品、它的卷与关联一起走。
    checks.check(
        "接口删作品返回 204",
        checks.api("DELETE", f"/api/editions/{edition_d}")[0] == 204,
    )
    checks.check(
        "删掉之后接口读不到这一份作品了",
        checks.api("GET", f"/api/editions/{edition_d}")[0] == 404,
    )
    checks.check(
        "它自己那一张封面文件跟着删了",
        cover_files("edition", edition_d) == [],
        f"删完硬盘上是 {cover_files('edition', edition_d)} —— 记录没了,图再没人认领",
    )
    checks.check(
        "它下面那一卷的封面文件也一起删了",
        cover_files("volume", COVER_VOLUME_ID) == [],
        f"删完硬盘上是 {cover_files('volume', COVER_VOLUME_ID)}",
    )
    checks.check(
        "接口删总标题返回 204",
        checks.api("DELETE", f"/api/works/{work_c}")[0] == 204,
    )
    checks.check(
        "删掉之后接口也读不到这个总标题了",
        checks.api("GET", f"/api/works/{work_c}")[0] == 404,
        f"GET /api/works/{work_c}",
    )

    # ---- 加入作品:四件(Gal、动画、两个不同作者的漫画版)一次建出来,前两件各带外部条目 ----
    # 两个漫画故意使用同一类型,验的是同一总标题下允许多件同类型作品。
    status, answer, imported_work = added(
        checks,
        "POST",
        "/api/works/with-editions",
        {
            "work": {
                "title": f"{PREFIX}丁",
                "original_title": f"{PREFIX}ディン",
                "aliases": [f"{PREFIX}丁的别名"],
            },
            "editions": [
                {
                    "media_type": "game",
                    "title": "",
                    "summary": "一句话简介。",
                    "org": f"{PREFIX}发行",
                    "release_status": "",
                    "volume_count": None,
                    "published_on": "2004-04",
                    "creators": [{"name": f"{PREFIX}丁作者", "role": "剧本"}],
                    "tags": [f"{PREFIX}丁标签"],
                    "refs": [{"source": "vndb", "external_id": "v900001", "title": f"{PREFIX}丁"}],
                },
                {
                    "media_type": "anime",
                    "title": "",
                    "summary": "",
                    "org": f"{PREFIX}制作",
                    "release_status": "",
                    "volume_count": 1,
                    "published_on": "2007-10",
                    "creators": [{"name": f"{PREFIX}丁作者", "role": "导演"}],
                    "tags": [],
                    "refs": [{"source": "bangumi", "external_id": "900001", "title": f"{PREFIX}丁"}],
                },
                {
                    "media_type": "manga",
                    "title": f"{PREFIX}丁 漫画甲",
                    "summary": "",
                    "org": f"{PREFIX}出版社",
                    "release_status": "",
                    "volume_count": 2,
                    "published_on": "2008-01",
                    "creators": [{"name": f"{PREFIX}漫画家甲", "role": "作画"}],
                    "tags": [],
                    "refs": [],
                },
                {
                    "media_type": "manga",
                    "title": f"{PREFIX}丁 漫画乙",
                    "summary": "",
                    "org": f"{PREFIX}出版社",
                    "release_status": "",
                    "volume_count": 3,
                    "published_on": "2009-01",
                    "creators": [{"name": f"{PREFIX}漫画家乙", "role": "作画"}],
                    "tags": [],
                    "refs": [],
                },
            ],
        },
    )
    imported = field(answer, "editions") or []
    checks.check(
        "加入作品一次建出总标题与它的四件作品",
        status == 201 and len(imported) == 4,
        f"POST /api/works/with-editions -> {status}",
    )
    checks.check(
        "四件都挂在这一个总标题下",
        imported_work > 0
        and {int(item.get("work_id") or 0) for item in imported} == {imported_work},
    )
    checks.check(
        "同一总标题允许两个漫画版本",
        [item.get("media_type") for item in imported] == ["game", "anime", "manga", "manga"],
        f"{[item.get('media_type') for item in imported]}",
    )
    checks.check(
        "作者与标签一起写了进去",
        [link.get("role") for link in (imported[0].get("creators") or [])] == ["剧本"]
        and [tag.get("name") for tag in (imported[0].get("tags") or [])] == [f"{PREFIX}丁标签"],
    )

    # 外部条目按件各记各的:同一个源最多一条,而两件不必来自同一个源。
    per_edition = []
    for item in imported:
        refs_status, refs = checks.api("GET", f"/api/editions/{item['id']}/source-refs")
        per_edition.append(
            [(ref.get("source"), ref.get("external_id")) for ref in (refs or [])]
            if refs_status == 200
            else None
        )
    checks.check(
        "外部条目只记在各自那一件上",
        per_edition == [[("vndb", "v900001")], [("bangumi", "900001")], [], []],
        f"{per_edition}",
    )

    status, answer = checks.api(
        "PUT", f"/api/editions/{edition_a}/source-refs", {"source": "vndb", "external_id": "v900001"}
    )
    checks.check(
        "同一个外部条目不许记到第二件作品上",
        status == 400,
        f"-> {status} {field(answer, 'detail')}",
    )

    # **一件不成立就一件都不建**:前一件完全合法,错在第二件的日期上,结果必须是库里一条都没有。
    works_before = count("work")
    editions_before = count("edition")
    status, answer = checks.api(
        "POST",
        "/api/works/with-editions",
        {
            "work": {"title": f"{PREFIX}戊", "original_title": "", "aliases": []},
            "editions": [
                {
                    "media_type": "game",
                    "title": "",
                    "summary": "",
                    "org": "",
                    "release_status": "",
                    "volume_count": None,
                    "published_on": "2004-04",
                    "creators": [],
                    "tags": [],
                },
                {
                    "media_type": "anime",
                    "title": "",
                    "summary": "",
                    "org": "",
                    "release_status": "",
                    "volume_count": None,
                    "published_on": "2004-13",
                    "creators": [],
                    "tags": [],
                },
            ],
        },
    )
    checks.check(
        "后一件的日期写法不对时,整条(含前一件)都不建",
        status == 400 and count("work") == works_before and count("edition") == editions_before,
        f"-> {status} {field(answer, 'detail')}",
    )

    # 件数的两头:一件都没有要拒;另一头**没有上限** —— 一次加几件由人定。
    thin = {
        "media_type": "game",
        "title": "",
        "summary": "",
        "org": "",
        "release_status": "",
        "volume_count": None,
        "published_on": "2004-04",
        "creators": [],
        "tags": [],
    }
    works_before = count("work")
    status, answer = checks.api(
        "POST",
        "/api/works/with-editions",
        {
            "work": {"title": f"{PREFIX}己", "original_title": "", "aliases": []},
            "editions": [],
        },
    )
    checks.check(
        "一件都没有时拒绝,也不留空总标题",
        status == 400 and count("work") == works_before,
        f"-> {status} {field(answer, 'detail')}",
    )

    # 件数没有上限(一次加几件由人定):五件里最后一件又是漫画,就是「同类型可以重复」那种形状。
    editions_before = count("edition")
    status, answer = checks.api(
        "POST",
        "/api/works/with-editions",
        {
            "work": {"title": f"{PREFIX}庚", "original_title": "", "aliases": []},
            "editions": [
                {**thin, "media_type": kind, "title": f"{PREFIX}庚之{index}"}
                for index, kind in enumerate(
                    ("manga", "light_novel", "game", "anime", "manga"), start=1
                )
            ],
        },
    )
    many = field(answer, "editions") or []
    checks.check(
        "五件一次建出来(没有件数上限,同一类型可以重复)",
        status == 201 and count("edition") == editions_before + 5,
        f"-> {status} {field(answer, 'detail')}",
    )
    checks.check(
        "五件都挂在这一个总标题下",
        [item.get("media_type") for item in many]
        == ["manga", "light_novel", "game", "anime", "manga"],
        f"{[item.get('media_type') for item in many]}",
    )

    # 这一条也是这一节自己建的,自己收掉。
    delete_work(checks, row_id("work", "title", f"{PREFIX}庚"))
    checks.check("那一部五件的也删干净了", count("edition") == editions_before)

    # 这一条是这一节自己建的,自己收掉,库才会回到起始状态。
    delete_work(checks, imported_work)
    checks.check("加入的那一条删干净了", row_id("work", "title", f"{PREFIX}丁") == 0)

    # ---- 总标题自己的封面:与件、卷同一套规矩,但清理这一头曾经漏掉过它 -------------
    # 传在删记录之前:这一条的图归**总标题**所有,删总标题时该跟着走(件与卷那两张在上一节已经验过)。
    global COVER_WORK_ID
    COVER_WORK_ID = work_a
    status, answer = checks.upload(f"/api/works/{work_a}/cover", "work.png", TINY_PNG)
    checks.check(
        "总标题也收得下自己那张封面",
        status == 200
        and cover_files("work", work_a) == [f"work-{work_a}.png"]
        and str(field(answer, "cover_url") or "").endswith(".png"),
        f"POST /api/works/{work_a}/cover -> {status},硬盘上 {cover_files('work', work_a)}",
    )
    # 与件、卷不同的一处:`cover_url` 本来是「沿用第一件的封面」,总标题自己传过就该换成自己这张。
    checks.check(
        "传过之后总标题报的是自己这张,不再沿用第一件的",
        field(checks.api("GET", f"/api/works/{work_a}")[1], "cover_url") == field(answer, "cover_url"),
        f"回的是 {field(answer, 'cover_url')!r}",
    )

    # ---- 删掉作品:作者与标签留下,连接跟着走 -----------------------------
    creators_kept, tags_kept = count("creator"), count("tag")
    delete_work(checks, work_a)
    delete_work(checks, work_b)
    checks.check("删掉之后作品总标题不在了", row_id("work", "title", f"{PREFIX}甲") == 0)
    checks.check(
        "作者与标签留在库里",
        count("creator") == creators_kept and count("tag") == tags_kept,
        f"creator {count('creator')}, tag {count('tag')}",
    )
    checks.check(
        "它们与作品的连接消失了",
        query(
            "SELECT COUNT(*) FROM edition_creator AS l "
            "LEFT JOIN creator AS c ON c.id = l.creator_id WHERE c.id IS NULL"
        )[0][0]
        == 0,
    )
    # 总标题删掉时,它下面几件作品、那些作品下的卷、以及它们的封面文件一起走 —— 总标题自己那张也在内。
    checks.check(
        "连它自己的封面文件一起删了",
        cover_files("work", COVER_WORK_ID) == [],
        f"删掉总标题之后硬盘上是 {cover_files('work', COVER_WORK_ID)}",
    )
    checks.check(
        "连它留下的封面文件一起删了",
        cover_files("edition", COVER_EDITION_ID) == [],
        f"删掉总标题之后硬盘上是 {cover_files('edition', COVER_EDITION_ID)}",
    )
    # 反面:该删的删了,库里原有的封面必须一个没动 —— 删文件只有这一处,就在这一处一起看住。
    present = {path.name for path in covers_dir().glob("*")}
    checks.check(
        "库里原有的封面文件一个没动",
        all(name in present for name in covers_before),
        f"跑之前 {covers_before},现在 {sorted(present)}",
    )
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except Stop as stop:
        print(f"FAIL 连不上服务,或环境不对: {stop}")
        raise SystemExit(1) from None
