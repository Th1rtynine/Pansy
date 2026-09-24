# Pansy 依赖说明

[返回项目首页](../README.md) · [开发指南](development.md)

Pansy 把“应用运行需要什么”和“开发者打包需要什么”分开管理。普通开发不必安装整套桌面发布工具，最终用户则不需要手动安装这里的任何依赖。

## 依赖分层

| 层级 | 清单 | 谁需要 |
| --- | --- | --- |
| Python 应用 | [`requirements.txt`](../requirements.txt) | 后端开发、测试、桌面运行封装 |
| Python 打包 | [`requirements-build.txt`](../requirements-build.txt) | 生成桌面安装包的人 |
| Vue 前端 | [`frontend/package.json`](../frontend/package.json) | 前端开发与构建 |
| Tauri 外壳 | [`frontend/src-tauri/Cargo.toml`](../frontend/src-tauri/Cargo.toml) | 桌面开发与打包 |

## Python 应用依赖

| 包 | 职责 |
| --- | --- |
| FastAPI | 本地 API 与页面入口 |
| Uvicorn | 启动只监听本机的服务 |
| SQLAlchemy | SQLite 数据模型与查询 |
| python-multipart | 接收封面等表单文件 |
| pypinyin | 中文标题的拼音检索 |

这些依赖属于程序本身，统一放在 `requirements.txt`。版本使用兼容范围，避免无意跨入下一代破坏性版本。

## 桌面打包依赖

`requirements-build.txt` 目前只包含 PyInstaller。它把 Python、本地 API、后端依赖和编译后的 Vue 界面封装为 `pansy-server.exe`，再由 Tauri 随主程序一起安装。

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
```

不要把 PyInstaller 放回运行依赖：普通后端开发和自动测试不需要它。

## 前端依赖

### 随界面使用

- Vue 3
- Vue Router
- `@tauri-apps/plugin-opener`，只在桌面环境调用系统默认浏览器

### 只在开发与构建时使用

- Vite
- Tailwind CSS
- Vue 与 Tailwind 的 Vite 插件
- Tauri CLI

`package-lock.json` 必须提交。新增或更新前端依赖后使用 `npm install` 更新清单；其他开发者和自动构建使用 `npm ci` 复现同一版本。

## Rust 与 Tauri

| 依赖 | 职责 |
| --- | --- |
| Tauri | Windows 窗口、资源封装与安装包 |
| `tauri-plugin-shell` | 启动并管理 Python sidecar |
| `tauri-plugin-opener` | 使用系统应用打开外部链接 |
| `tauri-plugin-log` | 开发构建的桌面日志 |
| Serde / serde_json | 读取本地服务的启动握手信息 |

`Cargo.lock` 对应用项目同样必须提交，它保证桌面构建不会在另一台电脑上悄悄换用不同的 Rust 依赖版本。

## 系统工具

| 工具 | 什么时候需要 |
| --- | --- |
| Python 3.11+ | 后端开发、测试、打包 |
| Node.js 20.19+ 或 22.12+ | 前端构建 |
| Rust 1.77.2+ | Tauri 编译 |
| WebView2 Runtime | Windows 上运行桌面界面 |
| NSIS | 生成安装程序；Tauri 首次打包时自动下载 |

## 更新原则

1. 只为明确的功能或安全修复增加依赖。
2. 运行依赖与构建依赖保持分离。
3. 一次只更新一个技术层，并在更新后完成相应构建或测试。
4. 不因为普通代码提交发布新安装包；依赖更新随下一次稳定版本一起发布。
5. 安装包、依赖缓存与编译目录永远不进入 Git。
