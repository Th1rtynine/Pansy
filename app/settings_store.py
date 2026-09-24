"""网页上改得动的那些设置:存在数据目录下的 `settings.json`。

**为什么另起一个文件,而不是写回 `config.toml`:** 那个文件是人手写的,里头有成段的注释与说明;从程序里
覆盖它会把注释冲掉。而 `data/` 本来就是「这一份库的全部」——README 说搬机器就是把它整个复制过去——所以
网页上填的东西放这里,**跟着库走**,备份也带得上。

**优先级:这个文件 > `config.toml`。** 两边都写了同一个键时以这里为准(网页上填的就是最后的意思);
这里没写的键仍由 `config.toml` 决定。文件不存在、读不动、或里头不是个对象,一律当作「网页上什么都没填」,
不是错误 —— 刚克隆下来的库本来就没有这个文件。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import load_paths

#: 认得的键。写文件时只写这里列出来的,别的东西(例如将来手改加的)原样留着不丢。
TOKEN_KEY = "bangumi_token"
SOURCE_PRIORITY_KEY = "source_priority"
DEFAULT_SOURCE_PRIORITY = ("hikarinagi", "bangumi", "vndb")


@dataclass(frozen=True)
class CredentialSpec:
    """一个源要填哪些格。

    **不是每个源都需要凭据,而需要的那些格数也不一样** —— 所以这里按「一堆具名的格」描述,而不是写死
    「id + secret 两格」:

    - Hikarinagi 走 OIDC 的 `client_credentials`,**两格都得有**才换得到令牌。
    - VNDB 读公开条目**根本不要凭据**;它那一格 token 是留给「同步我自己账号的收藏」的,所以标
      `optional`(不填也能用)并标 `noop`(当前版本还不会读它)。

    `fields` 是 `(键名, 给人看的名字, 存进 `settings.json` 的键)`。**存储键写死在这里**,不按源名拼 ——
    `bangumi_token` 这个先例说明键名是给人看的,该显式写出来而不是推导出来。
    """

    fields: dict[str, tuple[str, str]]
    #: 怎么拿到,一句话(页面照着做就行)。
    hint: str = ""
    #: 不填也不影响这个源能不能用(填了只是给将来的功能留着)。
    optional: bool = False
    #: **当前版本不会用到它** —— 存下来只是先把位置留好。页面上要如实说,免得人以为填了就生效。
    noop: bool = False

    def stored_keys(self) -> tuple[str, ...]:
        return tuple(key for _label, key in self.fields.values())

    def names(self) -> list[str]:
        return list(self.fields)


#: 哪些源有凭据可填。源名 -> 它的那几格。
CREDENTIALS: dict[str, CredentialSpec] = {
    "hikarinagi": CredentialSpec(
        fields={
            "client_id": ("Client ID", "hikarinagi_client_id"),
            "client_secret": ("Client Secret", "hikarinagi_client_secret"),
        },
        hint="在 Hikarinagi 开发者控制台建一个应用,勾选 catalog:read(想读 NSFW 就勾 catalog:full),"
        "客户端类型选服务端应用(机密客户端),把它的 Client ID 与 Client Secret 填在这里。",
    ),
    "vndb": CredentialSpec(
        fields={"token": ("API 令牌", "vndb_token")},
        hint="在 VNDB 的 My Profile → Applications 里生成一个令牌(也可以用 vndb.org/u/tokens 这个地址)。"
        "读公开条目不需要它 —— 这一格是留给「同步你自己 VNDB 账号的收藏与评分」的;"
        "填了之后按「验证」能确认它是谁的。",
        optional=True,
    ),
}

#: 下面两张表是上面那张的**只读视图**,给「按源遍历」的地方用(接口层与验收脚本)。加源只改 `CREDENTIALS`。
CREDENTIAL_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    source: tuple((name, label) for name, (label, _key) in spec.fields.items())
    for source, spec in CREDENTIALS.items()
}
CREDENTIAL_KEYS: dict[str, tuple[str, ...]] = {
    source: spec.stored_keys() for source, spec in CREDENTIALS.items()
}
CREDENTIAL_HINTS: dict[str, str] = {source: spec.hint for source, spec in CREDENTIALS.items()}

#: 令牌长度上限。Bangumi 的访问令牌是几十个字符;给足余量,同时挡住把整篇文章贴进来。
MAX_TOKEN_LENGTH = 512

#: 凭据每一项的长度上限。client_secret 比令牌长一些,同样给足余量。
MAX_CREDENTIAL_LENGTH = 512


def settings_file() -> Path:
    """网页设置存哪。**不建目录** —— 调用方多半只是想读,写的时候才建(见 `save_settings`)。"""
    return load_paths().data_dir / "settings.json"


def load_saved_settings() -> dict:
    """网页上存过的那一份设置。读不出来就是空的那一份。"""
    try:
        raw = settings_file().read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except (OSError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def save_settings(changes: dict) -> dict:
    """把这几项写进去,其余的键原样保留,回写完之后的那一整份。"""
    return _write({**load_saved_settings(), **changes})


def drop_settings(keys: list[str]) -> dict:
    """把这几项从文件里**拿掉**(不是写成空串),其余的键原样保留,回写完之后的那一整份。

    清掉一项必须走这里,不能靠 `save_settings({key: ""})`:`save_settings` 是 update 语义,
    把整份读出来、改掉一格再传回去,那一格又会被写回来(实测踩过)。
    """
    current = load_saved_settings()
    for key in keys:
        current.pop(key, None)
    return _write(current)


def _write(current: dict) -> dict:
    """整份写下去。调用方负责先合好。"""
    path = settings_file()
    _write_json(path, current)
    return current


def _write_json(path: Path, current: dict) -> None:
    """把一份 JSON 写下去:**先写同目录下的临时文件再替换**,中途崩了也不会留下半截文件,旧的那一份还在。

    这份库要写好几个这样的文件(`settings.json`、登录会话、账号资料缓存),所以这一段只写一次。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_json(path: Path) -> dict:
    """读一份 JSON。读不出来(还没有、坏了、不是对象)一律当空的那一份 —— 不是错误状态。"""
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def saved_token() -> str:
    """网页上存过的令牌,没有就是空串。"""
    value = load_saved_settings().get(TOKEN_KEY)
    return value.strip() if isinstance(value, str) else ""


def source_priority(known: set[str] | None = None) -> list[str]:
    """导入时采用来源的顺序。旧设置没有这一项时给出稳定默认值；新增来源自动补在末尾。"""
    allowed = known or set(DEFAULT_SOURCE_PRIORITY)
    raw = load_saved_settings().get(SOURCE_PRIORITY_KEY)
    requested = raw if isinstance(raw, list) else list(DEFAULT_SOURCE_PRIORITY)
    ordered: list[str] = []
    for value in requested:
        name = str(value).strip()
        if name in allowed and name not in ordered:
            ordered.append(name)
    ordered.extend(name for name in DEFAULT_SOURCE_PRIORITY if name in allowed and name not in ordered)
    ordered.extend(sorted(allowed - set(ordered)))
    return ordered


def saved_fields(source: str) -> dict[str, str]:
    """这个源那几格**存着什么就回什么**(空串就是没填)。

    与 `saved_credentials` 的区别:那个是「这个值现在能不能用」(半对当没填),这个是「文件里到底有什么」。
    页面报「有没有填」用后者 —— 人填了一格就该看见那一格有了,而不是被另一格的状态盖住。
    """
    spec = CREDENTIALS.get(source)
    if spec is None:
        return {}
    stored = load_saved_settings()
    return {
        name: value.strip() if isinstance(value := stored.get(key), str) else ""
        for name, (_label, key) in spec.fields.items()
    }


def saved_credentials(source: str) -> tuple[str, str]:
    """网页上存过的这一对凭证(id, secret)。任何一半没填就整对当没填 —— 只有半个没法换令牌,
    当成「配好了」会让页面以为能用,而真正调用时才失败。

    **只对「正好两格」的源有意义**(眼下只有 Hikarinagi)。别的源用 `saved_fields`。
    """
    spec = CREDENTIALS.get(source)
    if spec is None or len(spec.fields) != 2:
        return "", ""
    values = saved_fields(source)
    pair = tuple(values.get(name, "") for name in spec.fields)
    return pair if all(pair) else ("", "")  # type: ignore[return-value]


def save_credentials(source: str, values: dict[str, str]) -> None:
    """把这几格写进去。**全部传空串就是清掉**(真的从文件里拿掉,不是写空串)。

    「必须全填」那一类(有 `optional` 的除外)由接口层拦 —— 这里只管写文件。这一层认得的是「格名」,
    存储键由 `CREDENTIALS` 决定,所以调用方不用知道键叫什么。

    **清掉凭据是页面上的「清除」,不是「退出登录」** —— 后者走 `app/sources/hikarinagi.py` 的
    `logout()`,只撤销会话、不碰这两格。两件事分开是有意的:凭据是建应用时抄一次、长期不动的
    那一层,退出登录不该把它一起带走。
    """
    spec = CREDENTIALS.get(source)
    if spec is None:
        raise ValueError(f"不认识的源 {source!r},只认 {sorted(CREDENTIALS)}")
    cleaned = {name: str(values.get(name, "")).strip() for name in spec.fields}
    if not any(cleaned.values()):
        # 凭据清掉了,登录会话与账号资料也就没用了 —— 会话里那枚 refresh token 是**配着某个
        # client_id** 发的,留着只会在下一次请求时报一些难懂的错;而"上次看到你是谁"也不该
        # 在一个已经清空的源上继续显示。一起清掉,状态才干净。
        forget_session()
        forget_profile(source)
        return drop_settings(list(spec.stored_keys()))
    save_settings(
        {key: cleaned[name] for name, (_label, key) in spec.fields.items() if cleaned[name]}
    )


def has_credentials(source: str) -> bool:
    """这个源在网页上配齐了没有。

    **「配齐」不等于「能用」**:VNDB 的 token 是可选的,没填它照样是个完整可用的源。所以调用方若要问
    「这个源现在能不能用」,该问源自己的 `configured()`(见 `app/api/sources.py`),而不是这里。
    """
    spec = CREDENTIALS.get(source)
    if spec is None:
        return False
    values = saved_fields(source)
    if spec.optional:
        return any(values.values())
    return all(values.values())


def forget_settings() -> None:
    """把网页上那一份整个抹掉,回到「只认 `config.toml`」的状态。

    **是删文件,不是往里写一个空对象** —— 留着个 `{}` 也读得出来是「什么都没填」,但那会让人以为
    「我明明清掉了,怎么还有这个文件」。删不掉不算错(本来就不在)。
    """
    try:
        settings_file().unlink()
    except OSError:
        pass


def mask(token: str) -> str:
    """给页面看的那个样子:**只留头尾各四个字符**,中间一律省略号。

    页面上永远不出现完整令牌 —— 它是要拿去授权的东西,回显一次就多一个泄漏面(截图、别人瞟一眼、
    浏览器把响应存进缓存),而人只需要认出「是不是我填的那一个」。
    """
    if not token:
        return ""
    if len(token) <= 12:
        return "…" + token[-2:]
    return f"{token[:4]}…{token[-4:]}"


# ---- 登录会话(用户级令牌)---------------------------------------------------
#
# **另起一个文件**,而不是塞进 `settings.json`。理由是这两样东西的性质不同:
#
# - `settings.json` 是**人填的**设置,搬机器、备份、给别人看都无所谓(凭据除外)。
# - 这个文件是**程序换回来的会话**,里面的 refresh token 是"能长期代表你去读账号数据"的东西。
#
# 分开之后,「清掉登录」与「清掉设置」是两件事:退出登录不会把你的 Client ID/Secret 一起删掉,
# 反过来也一样。文件权限也照 0600 收着(见 `_write_session`)。

#: 登录会话存哪些键。**认得的只有这四个**,别的一律不写。
#: 账号资料**不在这里** —— 它归下面那块通用缓存(`{源}_profile.json`),这样"退出登录"与
#: "上次看到你是谁"是两件可以分开处置的事。
SESSION_KEYS = ("refresh_token", "access_token", "expires_at", "at")

#: 会话文件叫什么(在数据目录下)。
SESSION_FILE = "hikarinagi_session.json"


def session_file() -> Path:
    return load_paths().data_dir / SESSION_FILE


def load_session() -> dict:
    """登录会话。读不出来(还没登录、文件坏了)就是空的那一份。"""
    try:
        parsed = json.loads(session_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def saved_refresh_token() -> str:
    """那枚长期凭证。没有就是空串 —— 空串意味着「没登录」。"""
    value = load_session().get("refresh_token")
    return value.strip() if isinstance(value, str) else ""


def save_session(changes: dict) -> dict:
    """把这几项并进登录会话里。

    **并进去而不是整份覆盖**:换令牌那一步只会拿到 `access_token` 与 `refresh_token`,
    整份覆盖会把另一枚冲掉。
    """
    current = load_session()
    known = {key: value for key, value in current.items() if key in SESSION_KEYS}
    return _write_session({**known, **changes})


def save_access_token(token: str, expires_at: float) -> None:
    """记下刚换到的那枚访问令牌与它的到期时刻。"""
    save_session({"access_token": token, "expires_at": float(expires_at)})


def _write_session(current: dict) -> dict:
    """整份写下去。全部为空就是**删文件** —— 留一个 `{}` 会让人以为「我明明退出了,怎么还有这个文件」。"""
    path = session_file()
    kept = {key: value for key, value in current.items() if key in SESSION_KEYS and value not in ("", None, {})}
    if not kept:
        try:
            path.unlink()
        except OSError:
            pass
        return {}
    kept["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write_json(path, kept)
    # refresh token 与 `settings.json` 里的 client_secret 是一个量级的东西,权限照收:
    # 本机别的用户不该读得到。做不到(比如 Windows 上的某些文件系统)不算错。
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return kept


def forget_session() -> None:
    """退出登录:把这一份整个删掉。"""
    try:
        session_file().unlink()
    except OSError:
        pass


# ---- 账号资料缓存 -----------------------------------------------------------
#
# 一块给**所有**源用的地方:登录(或验证令牌)时顺手取到的那份"我是谁"。
#
# 为什么要缓存:问一次服务端"我是谁"是一次网络往返,而昵称头像不会天天变。页面每次打开都去问,
# 既慢又没必要 —— 所以取到一次就记下来,之后从本地读。
#
# 与日志/会话分开放:**退出登录只该删会话,不该把"上次看到你是谁"也一起抹掉** —— 那个是给人看的
# 一点残留信息,不含任何能拿去授权的东西。

#: 每一份最多留这些键。写文件时只写这里列出来的。
PROFILE_KEYS = (
    "id",
    "name",
    "nickname",
    "avatar_url",
    "bio",
    "signature",
    "registered_at",
)


def profile_file(source: str) -> Path:
    return load_paths().data_dir / f"{source}_profile.json"


def saved_profile_of(source: str) -> dict:
    """这个源上次看到的账号资料。没有、或者读不出来,都是空的那一份。"""
    stored = _read_json(profile_file(source))
    return {key: value for key, value in stored.items() if key in PROFILE_KEYS and value not in ("", None)}


def save_profile(source: str, profile: dict) -> dict:
    """记下这个源的账号资料。全是空值就是**删文件** —— 没登录时不该在硬盘上留一份空壳。"""
    path = profile_file(source)
    kept = {key: value for key, value in profile.items() if key in PROFILE_KEYS and value not in ("", None)}
    if not kept:
        try:
            path.unlink()
        except OSError:
            pass
        return {}
    kept["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write_json(path, kept)
    return kept


def forget_profile(source: str) -> None:
    """忘掉这个源的账号资料。退出登录、或者凭据被清掉时用。"""
    try:
        profile_file(source).unlink()
    except OSError:
        pass
