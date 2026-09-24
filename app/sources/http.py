"""One place where an outside request is made, so the rules are written once.

三条规矩:User-Agent 带开发者与项目名(Bangumi 明确要求,封 UA 有先例);失败一律回 None 不往外抛 ——
数据源取不到时草稿仍要用别的东西生成;超时短,不拖住整页。**唯一的例外是 `get_json_with_status`**:
问「这个令牌对不对」时必须分得清 401 与对方没答,所以那一处把状态码一并交回来。走 `urllib`:`curl` 拿不到 schannel 凭据、
浏览器抓取工具会被 Cloudflare 挡,而 urllib 两家都通。
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.config import SourceSettings, load_source_settings


def _settings() -> SourceSettings:
    """这次请求用哪套设置。**读不出来就给全默认值** —— 这里的调用方是「问别的站要数据」,而
    `config.toml` 缺失或写坏了是本地的事,不该让每一次外部请求都抛出去(见 `app/config.py` 里
    `_read_settings` 是硬开的)。
    """
    try:
        return load_source_settings()
    except (OSError, ValueError):
        return SourceSettings()


def _user_agent() -> str:
    """对外报的名字,`config.toml` 的 `[sources].user_agent` 可以换掉(默认见 `app/config.py`)。"""
    return _settings().user_agent


def _request(url: str, data: bytes | None, headers: dict[str, str]) -> Any | None:
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    request.add_header("User-Agent", _user_agent())
    request.add_header("Accept", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)

    try:
        with urllib.request.urlopen(request, timeout=_settings().timeout) as answer:
            return json.loads(answer.read())
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        # 网络不通、超时、对方回了不是 JSON 的东西 —— 三种都当作「这个源没答上来」。
        # 不记日志、不抛:页面上会显示这一栏是空的。
        return None


def get_json(url: str, headers: dict[str, str] | None = None) -> Any | None:
    return _request(url, None, headers or {})


def get_json_with_status(url: str, headers: dict[str, str] | None = None) -> tuple[Any | None, int | None]:
    """和 `get_json` 同一条路,但**把状态码一起交回来**。

    给「这个令牌到底对不对」那一处用:那里必须分得清「对方答了 401(令牌不对)」与「对方没答上来
    (网不通 / 超时 / 回了不是 JSON)」—— 前者要人换令牌,后者要人查网络,而 `get_json` 把两者都变成了
    `None`。状态码是 `None` 就说明对方压根没答。
    """
    request = urllib.request.Request(url, method="GET")
    request.add_header("User-Agent", _user_agent())
    request.add_header("Accept", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)

    try:
        with urllib.request.urlopen(request, timeout=_settings().timeout) as answer:
            return json.loads(answer.read()), answer.status
    except urllib.error.HTTPError as error:
        # 对方答了,只是答的是个错误码 —— 这一条要留给调用方判(401 与 5xx 是两件事)。
        return None, error.code
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None, None


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> Any | None:
    body = json.dumps(payload).encode("utf-8")
    sent = {"Content-Type": "application/json", **(headers or {})}
    return _request(url, body, sent)


def post_form_with_status(
    url: str, fields: dict[str, str], basic: tuple[str, str] | None = None
) -> tuple[Any | None, int | None]:
    """发一个 `application/x-www-form-urlencoded` 的表单,**把状态码一起交回来**;`basic` 给了就带 Basic 认证。

    给 OIDC 换令牌那一处用(`app/sources/hikarinagi.py`):那个端点按 OAuth 规范吃表单而不是 JSON,
    而且失败时**必须分得清**「凭据不对(401)」与「对方没答上来(网不通)」—— 前者要人回去改设置,
    后者只要重试。所以这里不能像 `get_json` 那样把两者都吞成 `None`。
    """
    body = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", _user_agent())
    if basic is not None:
        # 凭据按 RFC 7617 用 base64 放进去;urllib 的 HTTPBasicAuthHandler 会先等一次 401,
        # 而这里想一次就把凭据带上(401 之后重发对某些端点并不等价)。
        token = base64.b64encode(f"{basic[0]}:{basic[1]}".encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")

    try:
        with urllib.request.urlopen(request, timeout=_settings().timeout) as answer:
            return json.loads(answer.read()), answer.status
    except urllib.error.HTTPError as error:
        return _error_body(error), error.code
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None, None


def _error_body(error: urllib.error.HTTPError) -> Any | None:
    """错误响应里常常带着一句能读的话(OAuth 的 `error_description` 就在这里)。"""
    try:
        return json.loads(error.read())
    except (ValueError, OSError):
        return None


def fetch_bytes(url: str, limit: int = 8 * 1024 * 1024) -> bytes | None:
    """取一份文件的字节(外部源给的封面)。失败回 None,不往外抛 —— 取不到封面不该让「加入作品」失败;
    上限是为了别把几十兆的图整个读进内存,超过就当没取到;格式认不认由 `app/covers.py` 决定。
    """
    request = urllib.request.Request(url)
    request.add_header("User-Agent", _user_agent())
    try:
        with urllib.request.urlopen(request, timeout=_settings().timeout) as answer:
            data = answer.read(limit + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    return data if 0 < len(data) <= limit else None
