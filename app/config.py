"""Read local configuration and resolve paths shared by the app and scripts."""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class SourceSettings:
    """外部数据源的凭据与超时。**凭据只从这里读,`config.toml` 不进仓库**(和 data_dir 一个待遇):
    文件里没有 `[sources]` 段时全取默认值 —— 没有令牌不是错误状态,只是 Bangumi 看不到 NSFW 条目。
    超时短是有意的:等不到就当这个源没答上来(见 `app/sources/http.py`)。
    """

    bangumi_token: str = ""
    timeout: float = 10.0
    user_agent: str = DEFAULT_USER_AGENT


def _read_settings(config_file: str | Path | None) -> tuple[Path, dict]:
    config = Path(config_file).resolve() if config_file is not None else PROJECT_ROOT / "config.toml"
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
    """
    try:
        _config, settings = _read_settings(config_file)
    except (OSError, tomllib.TOMLDecodeError):
        return SourceSettings()

    section = settings.get("sources") or {}
    if not isinstance(section, dict):
        return SourceSettings()

    token = section.get("bangumi_token")
    timeout = section.get("timeout")
    agent = section.get("user_agent")
    return SourceSettings(
        bangumi_token=token.strip() if isinstance(token, str) else "",
        timeout=float(timeout) if isinstance(timeout, (int, float)) and timeout > 0 else 10.0,
        user_agent=agent.strip() if isinstance(agent, str) and agent.strip() else DEFAULT_USER_AGENT,
    )
