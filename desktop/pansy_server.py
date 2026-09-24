"""Pansy 桌面版的 Python sidecar 入口。

网页开发仍使用项目根目录的 ``config.toml``；只有这个入口会把运行数据放进
``%LOCALAPPDATA%\\Pansy``。它必须在导入 ``app.main`` 以前写好环境变量，因为
数据库、封面目录与静态页面都会在应用初始化时读取它们。
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import traceback


def _app_data_dir() -> Path:
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / "Pansy"
    return Path.home() / ".local" / "share" / "Pansy"


def _bundle_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    return Path(frozen_root) if frozen_root else Path(__file__).resolve().parent.parent


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    if sys.platform == "win32":
        synchronize = 0x00100000
        wait_timeout = 0x00000102
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _stop_with_parent(server, parent_pid: int) -> None:
    """桌面外壳消失后结束真正运行 API 的 PyInstaller 子进程。"""
    while not server.should_exit:
        if not _process_alive(parent_pid):
            server.should_exit = True
            return
        time.sleep(0.8)


def _ensure_config(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    config = root / "config.toml"
    if not config.exists():
        config.write_text(
            "[paths]\n"
            'data_dir = "data"\n\n'
            "[sources]\n"
            # 登录回调是预先登记在 Hikarinagi 控制台里的固定地址；它与桌面界面本轮
            # 使用哪个空闲业务端口是两件事，不能被动态端口改写。
            "hikarinagi_callback_port = 8000\n",
            encoding="utf-8",
        )
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Pansy desktop local service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--fallback-port",
        action="store_true",
        help="首选端口不可用时，让系统分配一个空闲端口",
    )
    parser.add_argument("--app-data", type=Path, default=None)
    parser.add_argument("--ready-file", type=Path, default=None)
    parser.add_argument("--parent-pid", type=int, default=0)
    args = parser.parse_args()

    app_data = (args.app_data or _app_data_dir()).resolve()
    bundle_root = _bundle_root()
    if str(bundle_root) not in sys.path:
        sys.path.insert(0, str(bundle_root))

    # 正常安装仍优先用 8000，以保持已经登记的 Hikarinagi 回调可用；开发网站占着
    # 8000 时自动退到系统分配的端口，至少桌面应用本身可以正常启动。
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind((args.host, args.port))
    except OSError:
        if not args.fallback_port or args.port == 0:
            listener.close()
            raise
        listener.bind((args.host, 0))
    listener.listen(2048)
    actual_port = int(listener.getsockname()[1])

    config_file = _ensure_config(app_data)
    os.environ["PANSY_CONFIG_FILE"] = str(config_file)
    os.environ["PANSY_STATIC_DIR"] = str(bundle_root / "frontend" / "dist")
    os.environ["PANSY_RUNTIME_PORT"] = str(actual_port)
    (app_data / "desktop-error.log").unlink(missing_ok=True)

    import uvicorn
    from app.main import app

    ready_file = args.ready_file.resolve() if args.ready_file else None
    if ready_file:
        ready_file.parent.mkdir(parents=True, exist_ok=True)
        ready_file.write_text(
            json.dumps({"pid": os.getpid(), "port": actual_port}), encoding="utf-8"
        )

    # 安装版是 windowed 进程，没有 stdout/stderr。禁用 Uvicorn 默认日志配置，否则某些
    # Python/打包器组合会在尝试访问控制台时直接退出。
    config = uvicorn.Config(app, log_config=None, access_log=False)
    server = uvicorn.Server(config)
    if args.parent_pid:
        threading.Thread(
            target=_stop_with_parent,
            args=(server, args.parent_pid),
            name="pansy-parent-watch",
            daemon=True,
        ).start()
    try:
        server.run(sockets=[listener])
    finally:
        listener.close()
        if ready_file:
            ready_file.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        configured = os.environ.get("PANSY_CONFIG_FILE")
        log_dir = Path(configured).parent if configured else Path(tempfile.gettempdir())
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "desktop-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
