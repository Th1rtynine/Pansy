# Pansy

![version](https://img.shields.io/badge/version-0.1-informational.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab.svg)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/Node.js-20.19%2B%20%7C%2022.12%2B-5fa04e.svg)](https://nodejs.org/)

## 项目介绍

Pansy 是一个自用的 ACG 信息收集库,用于记录个人收藏的作品,以及这部作品下面的各个版本。

写它的出发点很直接:记录自己关心的那部分信息,而不是参与一个公共条目库 —— 分类与标签由自己决定,不必迁就别人维护的那一套。同时,一部作品往往以多种形式存在:原作可能是 Gal,之后另有漫画版、动画版与轻小说版,每一种形式又各自有卷,它们常常散落在若干条目与本地目录中,而在这里可以放在一起看。

Pansy 把一部作品记成三层:作品总标题、件(各个版本)与卷,每一层各配一张封面;条目资料与封面可以从 Bangumi 与 VNDB 取回,取回之后由自己修改与整理。它同时是一份可以直接改写的基础模板:媒体类型、字段、标签与外部数据源都可以按照自己的习惯增删。

## 界面

![作品列表](docs/screenshot-list.jpg)

![作品详情](docs/screenshot-detail.jpg)

## 设计

### 三层结构

一部作品记成两级包含关系,加上最上面一层的共用信息:

- **作品总标题**(`work`):共用的名称、原名与别名,以及这个作品自己的一张封面。
- **件**(`edition`):作品的一种版本,例如漫画版、动画版、小说版、Gal。每一件各有类型、标题、日期、简介、出版社、状态、应有卷数、作者、标签与封面。
- **卷**(`volume`):件下面的一卷,带卷号、名称、发售日、简介与封面。

以 CLANNAD 为例:库里只记一条总标题,它下面挂三件 —— Gal、动画与漫画;漫画那一件下面再挂八卷。于是「有哪几版」与「收到第几卷」这两件事在同一个页面里就能看完。

封面每一层各有一张,互不顶替 —— 漫画版与动画版本来就不是同一张图,共用一张必然互相顶掉。总标题那张是「系列原作使用的图」,件那张是这一件的样子,卷那张是这一卷的样子;总标题尚未设置封面时,沿用第一件的封面。支持 png、jpg、gif 与 webp,单个文件上限 8MB。封面文件存放在 `data/covers/`,数据库中只记录路径与尺寸。

![件与它下面的卷](docs/screenshot-volume.jpg)

### 外部数据源

加入作品时可按名称或编号检索 Bangumi 与 VNDB,一次创建「总标题 + 若干件」,并带回原名、简介、日期、作者、标签与封面;每一件上会记录它在外部站点的条目编号,之后可按编号重新获取。取回的内容先进入草稿,点击保存时才写入数据库 —— 外部的资料只作参考,库里留下的始终是自己确认过的那一份。外部数据源在代码中按源分模块,新增一个源只需一个模块加一行注册。

### 作者与标签

作者与标签各有独立页面。作者可以设置多个别名,搜索与导入识别都以「名称 + 别名」为准:同一个人在不同站点的写法常常不同(Bangumi 写「折戸伸治」,库里记的是「折户伸治」),只认名字会把一个人记成两条。改名时若与库中已有记录重名,两条记录直接合并 —— 引用转移到保留的那一条,被合并掉的名称保留为别名,因此两种写法此后都能搜到。标签在同一媒体类型内同名时合并。

### 检索与浏览

搜索忽略大小写、标点与全角差异,按子串匹配,并支持拼音输入(不必先切输入法);精确匹配一无所获时,才按编辑距离容错一至两个字符 —— 两个字符以内的关键词不容错,免得凭空造出结果。件与卷以封面卡片墙排列,列表可按标题或按时间排序,每页 10 条;件与件之间还可以建立关联。

## 环境与运行

### 环境要求与安装

| 项目 | 要求 |
| --- | --- |
| Python | 3.11 或更高(程序中使用了标准库 `tomllib`) |
| Node.js | 20.19+ 或 22.12+(仅构建前端时需要,由 Vite 8 决定) |
| 系统 | Windows / macOS / Linux,依赖为现成 wheel 或纯 Python,无需编译 |

- 后端依赖见 `requirements.txt`:SQLAlchemy、FastAPI、Uvicorn、python-multipart、pypinyin
- 前端依赖见 `frontend/package.json`:Vue 3、Vue Router、Vite、Tailwind CSS

```bash
# 后端
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt     # Windows
.venv/bin/pip install -r requirements.txt         # macOS / Linux

# 前端:后端直接托管 frontend/dist,该目录不入库,必须构建一次
cd frontend && npm ci && npm run build && cd ..
```

`package-lock.json` 中的下载地址指向国内镜像,在国外安装会较慢,可先切回官方 registry。

### 配置

```bash
copy config.example.toml config.toml     # Windows
cp config.example.toml config.toml       # macOS / Linux
```

`config.toml` 描述的是本机设置,不入库。四个键都可以不改。

| 配置项 | 说明 |
| --- | --- |
| `[paths] data_dir` | 数据目录。相对路径以该 `config.toml` 所在目录为基准,也可填绝对路径;默认 `data`。 |
| `[sources] bangumi_token` | Bangumi 访问令牌,可留空。留空时公开条目仍可读取,NSFW 条目返回 404 而非 403。令牌在 bgm.tv 的设置页生成,无需把 Bangumi 账号交给本程序。 |
| `[sources] timeout` | 请求外部数据源的超时时间,默认 10 秒。 |
| `[sources] user_agent` | 请求外部数据源时对外声明的名称。Bangumi 要求提供可识别的 User-Agent,自行部署时修改此行即可。 |

整个 `[sources]` 段落可以省略,省略即「无令牌、默认超时、默认 User-Agent」。

### 运行

```bash
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000     # Windows
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000         # macOS / Linux
```

界面在 `http://127.0.0.1:8000/`,接口文档在 `/docs`。首次启动会自动建表,空库即可使用,不需要执行迁移脚本。

默认只监听 `127.0.0.1`。如需局域网内其他机器访问,把 `--host` 改为 `0.0.0.0`;此时任何访问者都可以修改数据。部署到公网前请自行加一层认证(例如反向代理的 Basic Auth),本项目未内置认证。

启动后库是空的,初次使用按以下顺序:点右上角的 `+`,在「从 Bangumi 查找」中填作品名、Bangumi 编号或条目链接,选择需要的件,一次建立「总标题 + 若干件」;随后逐件补全资料;最后在件下面添加卷。

### 数据与备份

程序在本机运行,数据全部保存在 `config.toml` 指定的数据目录里,可以整体复制与迁移。

```
<config.toml 所在目录>/data/pansy.db     所有条目
<config.toml 所在目录>/data/covers/      封面文件,每行一个文件
```

备份即复制整个 `data/` 目录;更换机器时把 `data/` 与 `config.toml` 一并复制过去。`data/`、`config.toml`、`backups/` 都不进仓库。

## 架构

后端为 FastAPI + SQLAlchemy 2 + SQLite,前端为 Vue 3 + Vite + Tailwind,构建产物由后端直接托管,因此整套程序只有一个进程、一个数据目录,不需要额外服务。

```
app/               后端
  main.py          应用装配与静态文件托管
  api/             一扇门一个模块(作品总标题、件、卷、作者、标签、外部数据源)
  sources/         外部数据源:一个源一个模块(bangumi.py、vndb.py)
  models/          表定义
  queries.py       读写(不查库的组装在 api/schemas.py)
  rules.py         跨字段的规矩(改名合并、卷号冲突等)
frontend/          前端:自有组件在 frontend/src/ui/,页面在 frontend/src/pages/
scripts/           验收脚本
migrations/        改表脚本(保留一个作为模板)
docs/              README 使用的图片
config.example.toml  配置模板(config.toml 不入库)
data/ backups/     数据与备份 —— 都不进仓库
```

### 验收脚本

`scripts/` 下有两个自用的验收脚本:`check.py` 只读检查(表结构、数据是否自洽、接口形状、外部源的解析规则),`flow.py` 走真实接口把整个流程跑一遍并清理自己的记录;空库上 `check.py` 会报两条与数据有关的失败,属正常。

## 鸣谢

数据来源与设计参考:

- [Bangumi](https://bgm.tv) - 番组计划,动画、漫画与轻小说的条目资料
- [VNDB](https://vndb.org) - The Visual Novel Database,视觉小说的条目资料
- [Hikarinagi](https://www.hikarinagi.org) - ACGN 社区,界面设计参考

## 许可证

[MIT](LICENSE):可自由使用、修改与商用,保留版权声明即可。
