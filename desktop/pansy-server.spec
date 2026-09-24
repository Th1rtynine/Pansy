# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 配置：生成供 Tauri 启动的 Python sidecar。"""

from pathlib import Path


project = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(project / "desktop" / "pansy_server.py")],
    pathex=[str(project)],
    binaries=[],
    datas=[(str(project / "frontend" / "dist"), "frontend/dist")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="pansy-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
