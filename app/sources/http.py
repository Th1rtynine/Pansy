"""One place where an outside request is made, so the rules are written once.

三条规矩:User-Agent 带开发者与项目名(Bangumi 明确要求,封 UA 有先例);失败一律回 None 不往外抛 ——
数据源取不到时草稿仍要用别的东西生成;超时短,不拖住整页。走 `urllib`:`curl` 拿不到 schannel 凭据、
浏览器抓取工具会被 Cloudflare 挡,而 urllib 两家都通。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.config import load_source_settings


def _user_agent() -> str:
    """对外报的名字,`config.toml` 的 `[sources].user_agent` 可以换掉(默认见 `app/config.py`)。"""
    return load_source_settings().user_agent


def _request(url: str, data: bytes | None, headers: dict[str, str]) -> Any | None:
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    request.add_header("User-Agent", _user_agent())
    request.add_header("Accept", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)

    try:
        with urllib.request.urlopen(request, timeout=load_source_settings().timeout) as answer:
            return json.loads(answer.read())
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        # 网络不通、超时、对方回了不是 JSON 的东西 —— 三种都当作「这个源没答上来」。
        # 不记日志、不抛:页面上会显示这一栏是空的。
        return None


def get_json(url: str, headers: dict[str, str] | None = None) -> Any | None:
    return _request(url, None, headers or {})


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> Any | None:
    body = json.dumps(payload).encode("utf-8")
    sent = {"Content-Type": "application/json", **(headers or {})}
    return _request(url, body, sent)


def fetch_bytes(url: str, limit: int = 8 * 1024 * 1024) -> bytes | None:
    """取一份文件的字节(外部源给的封面)。失败回 None,不往外抛 —— 取不到封面不该让「加入作品」失败;
    上限是为了别把几十兆的图整个读进内存,超过就当没取到;格式认不认由 `app/covers.py` 决定。
    """
    request = urllib.request.Request(url)
    request.add_header("User-Agent", _user_agent())
    try:
        with urllib.request.urlopen(request, timeout=load_source_settings().timeout) as answer:
            data = answer.read(limit + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    return data if 0 < len(data) <= limit else None
