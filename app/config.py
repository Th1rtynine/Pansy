"""Read local configuration and resolve paths shared by the app and scripts."""

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Paths:
    config_file: Path
    data_dir: Path
    database: Path
    covers_dir: Path


#: 问外部源时对外报的名字。对方靠它认人(Bangumi 明确要求带上),fork 出去自己改
#: `config.toml` 的 `[sources].user_agent`,不必改代码。
DEFAULT_USER_AGENT = "Th1rtynine/Pansy (https://github.com/Th1rtynine/Pansy)"

#: Hikarinagi 登录时默认申请的 scope。见 `SourceSettings.hikarinagi_login_scope`。
DEFAULT_LOGIN_SCOPE = "openid profile offline_access"

#: Hikarinagi 登录回调默认用的本机端口。见 `SourceSettings.hikarinagi_callback_port`。
DEFAULT_CALLBACK_PORT = 8000


@dataclass(frozen=True)
class SourceSettings:
    """外部数据源的凭据与超时。**凭据只从这里读,`config.toml` 不进仓库**(和 data_dir 一个待遇):
    文件里没有 `[sources]` 段时全取默认值 —— 没有令牌不是错误状态,只是 Bangumi 看不到 NSFW 条目。
    超时短是有意的:等不到就当这个源没答上来(见 `app/sources/http.py`)。

    令牌有**两个来源**:网页上填的(`<data_dir>/settings.json`)优先,其次才是 `config.toml` 里那一行。
    `token_from` 说的就是现在这个值是哪来的,页面上要如实写出来 —— 否则同一个人在两个地方填了不一样的值,
    会看着库「不听话」。
    """

    bangumi_token: str = ""
    timeout: float = 10.0
    user_agent: str = DEFAULT_USER_AGENT
    #: "settings" = 网页上填的,"config" = `config.toml` 里写的,空串 = 两处都没有。
    token_from: str = ""
    #: Hikarinagi 登录回调用的本机端口。**这一项必须与你在控制台登记的那条回调地址一致**,
    #: 所以它可配 —— 把 Pansy 跑在别的端口上,登录才不会莫名其妙地失败。
    hikarinagi_callback_port: int = 8000
    #: 登录时申请的 scope(空格分隔)。做成可配的理由:控制台勾了什么就得申请什么,
    #: 而「申请了但没勾」会静默地拿不到那一项(实测:offline_access 就是这么被裁掉的)。
    hikarinagi_login_scope: str = "openid profile offline_access"


def _read_settings(config_file: str | Path | None) -> tuple[Path, dict]:
    # 桌面安装版把配置与资料放在用户目录，源码运行仍旧读取项目根目录。
    # 只留这一个入口，避免桌面路径判断散落到数据库、封面与来源模块里。
    selected = config_file if config_file is not None else os.environ.get("PANSY_CONFIG_FILE")
    config = Path(selected).resolve() if selected is not None else PROJECT_ROOT / "config.toml"
    with config.open("rb") as source:
        return config, tomllib.load(source)


def load_paths(config_file: str | Path | None = None) -> Paths:
    """Resolve data paths relative to the configuration file's directory."""
    config, settings = _read_settings(config_file)

    raw_data_dir = settings.get("paths", {}).get("data_dir")
    if not isinstance(raw_data_dir, str) or not raw_data_dir.strip():
        raise ValueError(f"{config}: [paths].data_dir must be a nonempty string")

    data_dir = Path(raw_data_dir).expanduser()
    if not data_dir.is_absolute():
        data_dir = config.parent / data_dir
    data_dir = data_dir.resolve()

    return Paths(
        config_file=config,
        data_dir=data_dir,
        database=data_dir / "pansy.db",
        covers_dir=data_dir / "covers",
    )


def load_source_settings(config_file: str | Path | None = None) -> SourceSettings:
    """The outside sources' credentials; a missing or unreadable file means defaults.
    没写过 `[sources]` 段的库也要能跑:令牌缺失读作「这个源少一类内容」,而不是错误。

    令牌的优先级是**网页填的 > `config.toml` 里写的**。这里不 import `app.settings_store`(它会回过头
    来 import 本模块),而是在调用时才取 —— 循环导入会在这里断掉。
    """
    try:
        _config, settings = _read_settings(config_file)
    except (OSError, tomllib.TOMLDecodeError):
        # 文件不在或读不动:超时与 User-Agent 取默认值,**但网页上填的令牌仍然要认** ——
        # 那是另一份文件,不该被这一份读不出来连累。
        settings = {}

    section = settings.get("sources") or {}
    if not isinstance(section, dict):
        section = {}

    token = section.get("bangumi_token")
    timeout = section.get("timeout")
    agent = section.get("user_agent")
    raw_port = section.get("hikarinagi_callback_port")
    raw_scope = section.get("hikarinagi_login_scope")

    from app.settings_store import saved_token

    from_web = saved_token()
    from_config = token.strip() if isinstance(token, str) else ""
    if from_web:
        chosen, origin = from_web, "settings"
    elif from_config:
        chosen, origin = from_config, "config"
    else:
        chosen, origin = "", ""

    return SourceSettings(
        bangumi_token=chosen,
        timeout=float(timeout) if isinstance(timeout, (int, float)) and timeout > 0 else 10.0,
        user_agent=agent.strip() if isinstance(agent, str) and agent.strip() else DEFAULT_USER_AGENT,
        token_from=origin,
        # 端口超范围就当没写:那种值只会让登录拼出一个连不上的地址,退回默认更不容易误事。
        hikarinagi_callback_port=(
            int(raw_port) if isinstance(raw_port, int) and 1 <= raw_port <= 65535 else 8000
        ),
        hikarinagi_login_scope=(
            raw_scope.strip() if isinstance(raw_scope, str) and raw_scope.strip() else DEFAULT_LOGIN_SCOPE
        ),
    )
