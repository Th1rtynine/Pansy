"""The FastAPI application: serve the JSON API, and hand out the built interface.

**每个请求都先过一道闸门**:**限速**(`app/ratelimit.py`),它是全站唯一一道;这份库只在自己电脑上用,
谁打开都能直接改,没有登录。API 在 `app/api/`,界面是 `frontend/dist` 的构建产物,地址交给前端路由
(`frontend/src/router.ts`)。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import ratelimit
from app.api import API_ROUTERS
from app.config import load_paths
from app.db import init_db

DIST = Path(
    os.environ.get("PANSY_STATIC_DIR", Path(__file__).resolve().parent.parent / "frontend" / "dist")
).resolve()
INDEX = DIST / "index.html"

#: 没有构建产物时说的话 —— 不报一个空白的 404,免得让人以为后端坏了。
MISSING_BUILD = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>还没有构建前端</title></head>
<body style="font-family:system-ui,'Microsoft YaHei';max-width:38rem;margin:12vh auto;line-height:1.8">
<h1 style="font-size:1.2rem">还没有构建前端</h1>
<p>后端起来了,但 <code>frontend/dist</code> 里没有东西,所以没有界面可发。
接口本身是好的 —— <a href="/docs">/docs</a> 能打开。</p>
<p>在项目根目录跑一次:</p>
<pre style="background:#f4f2ee;padding:.75rem 1rem;border-radius:6px">cd frontend
npm install
npm run build</pre>
<p>开发界面时不必构建:另开一个窗口 <code>npm run dev</code>,用 5173 那个地址。</p>
</body></html>
"""


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Create missing tables on startup, then release that connection."""
    init_db().dispose()
    yield


def create_app() -> FastAPI:
    """Build the application, register the API, and put the built interface behind it."""
    application = FastAPI(title="Pansy", lifespan=lifespan)

    # 一道闸门:限速。`middleware("http")` 挂上去,所有请求都算进同一个桶,不只 `/api`。
    application.middleware("http")(ratelimit.guard)

    for router in API_ROUTERS:
        application.include_router(router)

    def wants_json(path: str) -> bool:
        """/api/ 下是程序要的数据,其余是浏览器打开的界面 —— 按路径分,不问客户端。"""
        return path.startswith("/api/")

    @application.exception_handler(StarletteHTTPException)
    async def answer_error(request: Request, error: StarletteHTTPException):
        """A missing record is data under /api and the interface everywhere else: `/api/` 下与别的拒绝
        一样是 `{"detail": "…"}`,其余按路径**带不带扩展名**分 —— 带的是在要文件(缺了照实 404,免得浏览器
        把一段 HTML 当脚本解析),不带的是一个地址,交给前端路由,给它外壳与 200。
        """
        if wants_json(request.url.path):
            return JSONResponse({"detail": error.detail}, status_code=error.status_code)
        if not INDEX.is_file():
            return HTMLResponse(MISSING_BUILD, status_code=503)
        if Path(request.url.path).suffix:
            return PlainTextResponse(f"找不到这个文件:{request.url.path}", status_code=404)
        return HTMLResponse(INDEX.read_text(encoding="utf-8"))

    @application.exception_handler(RequestValidationError)
    async def answer_bad_body(request: Request, error: RequestValidationError):
        """A body of the wrong shape, answered in the one-string form every refusal uses:
        FastAPI 自己的 422 带的是一串错误对象,这里变成 `{"detail": "请求内容的格式不对:字段。"}`。
        """
        names = list(
            dict.fromkeys(
                str(part)
                for item in error.errors()
                for part in item.get("loc", ())
                if part != "body"
            )
        )
        detail = "请求内容的格式不对" + (f":{'、'.join(names)}。" if names else "。")
        return JSONResponse({"detail": detail}, status_code=422)

    # 封面文件:前缀 `/covers` 与 app/covers.py 的 url_of() 是一对,且要排在界面那个挂载前面。
    covers = load_paths().covers_dir
    covers.mkdir(parents=True, exist_ok=True)
    application.mount("/covers", StaticFiles(directory=covers), name="covers")

    if INDEX.is_file():
        # 界面:构建产物由后端一起发。挂载放在最后,所以 /api 与 /docs 先被匹配到。
        application.mount("/", StaticFiles(directory=DIST, html=True), name="ui")
    else:
        @application.get("/", include_in_schema=False)
        async def missing_build() -> HTMLResponse:
            """Say how to build the interface instead of showing a blank 404."""
            return HTMLResponse(MISSING_BUILD, status_code=503)

    return application


app = create_app()
