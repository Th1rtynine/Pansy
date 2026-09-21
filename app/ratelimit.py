"""限速:一个来源每分钟最多能从这台机器上取走多少东西。
四条规矩:本机的程序不设限;客户端地址只在 `client_key` 一处算,对端不是回环时不信
X-Forwarded-For;所有请求都算进同一个桶,不只 `/api`;它是全站唯一一道闸门。
代价:多进程不共享(`--workers 4` 就是四倍),表随地址数增长靠 `_forget_stale()` 清,
重启就清空。
"""

from dataclasses import dataclass
from math import ceil
import time

from fastapi import Request
from fastapi.responses import JSONResponse, Response

#: 一分钟允许多少次。这个数是量出来的:一次冷访问 25 个请求、站内翻页 4 个、一页十张封面 ——
#: 240 够一个人连着翻六十页,而一个脚本最多被压在 4 次/秒,约占家宽上行的百分之十几。
PER_MINUTE = 240

#: 一次能连着用掉多少。一次冷访问就是二十几个请求,额度再高也得分批给。
BURST = 120

#: 上面那两个数的单位换算用。
WINDOW = 60.0
RATE = PER_MINUTE / WINDOW

#: 多久没用到的桶就丢掉,不然内存里那张表会随地址数一直涨。
KEEP_SECONDS = 600
#: 清理最多多久跑一次 —— 每个请求都扫一遍是 O(地址数)。
SWEEP_EVERY = 60.0

#: 认作「本机」的对端地址;对端是这几个之一、又没带 X-Forwarded-For,就是本机的程序。
LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})

#: 超了说的话。与别的拒绝同一个形状,只说一件事:等一会儿。
TOO_MANY = "请求太频繁了,过一会儿再试。"


@dataclass
class Bucket:
    """一个来源的水位:令牌桶。"""

    tokens: float
    filled_at: float


def client_key(peer: str | None, forwarded: str | None) -> str | None:
    """这个请求算谁的。**None 表示不设限**(本机的程序)。
    对端不是回环就是它自己;回环带 X-Forwarded-For 按第一段算,回环没带就是本机 ——
    挂隧道之后所有请求的对端都是回环,所以只有「回环且没带 XFF」才当本机。
    """
    if peer is None:
        return None
    if peer not in LOOPBACK:
        return peer
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return None


def refill(bucket: Bucket, now: float) -> None:
    """按过了多久把令牌加回来,不超过上限。"""
    elapsed = max(0.0, now - bucket.filled_at)
    bucket.tokens = min(float(BURST), bucket.tokens + elapsed * RATE)
    bucket.filled_at = now


def take(bucket: Bucket, now: float) -> float:
    """要用一个令牌:**0 表示可以走**,大于 0 表示还要等几秒。纯计算,不碰网络也不碰时钟。"""
    refill(bucket, now)
    if bucket.tokens >= 1.0:
        bucket.tokens -= 1.0
        return 0.0
    return (1.0 - bucket.tokens) / RATE


_buckets: dict[str, Bucket] = {}
_swept_at = 0.0


def _forget_stale(now: float) -> None:
    """把久没用到的桶丢掉。**最多每 `SWEEP_EVERY` 秒跑一次。**"""
    global _swept_at
    if now - _swept_at < SWEEP_EVERY:
        return
    _swept_at = now
    for key in [key for key, bucket in _buckets.items() if now - bucket.filled_at > KEEP_SECONDS]:
        del _buckets[key]


def reset() -> None:
    """把水位清空。给验收脚本用,也给「想立刻解开」的时候用。"""
    global _swept_at
    _buckets.clear()
    _swept_at = 0.0


async def guard(request: Request, call_next) -> Response:
    """那道限速闸门。`app/main.py` 把它挂成中间件 —— 全站的请求都从这里过。"""
    key = client_key(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
    )
    if key is None:
        return await call_next(request)

    now = time.monotonic()
    _forget_stale(now)
    bucket = _buckets.setdefault(key, Bucket(tokens=float(BURST), filled_at=now))
    wait = take(bucket, now)
    if wait > 0:
        return JSONResponse(
            {"detail": TOO_MANY},
            status_code=429,
            # 几秒后再来。**取整到秒**,四舍五入会让「等 0.4 秒」写成 0。
            headers={"Retry-After": str(ceil(wait))},
        )
    return await call_next(request)
