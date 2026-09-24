"""The JSON routers, gathered so app/main.py only includes them once.

一个实体一个模块,和 `app/models/` 一样。每个 router 都带 `/api` 前缀,所以 JSON 路径不会撞页面路径,
FastAPI 的 `/docs` 显示的正是这一组。
"""

from app.api.creators import router as creators
from app.api.editions import router as editions
from app.api.meta import router as meta
from app.api.settings import router as settings
from app.api.sources import router as sources
from app.api.tags import router as tags
from app.api.volumes import router as volumes
from app.api.works import router as works

API_ROUTERS = (works, editions, volumes, creators, tags, sources, settings, meta)
