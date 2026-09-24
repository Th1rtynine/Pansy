"""Record what the sources actually say about one work family, before any mapping is written.

**Why this exists**: 关系怎么分类不能靠中文名字猜。分类规则一旦写错,后面每一层(家族预览、图式导入、
分卷合并)都建在错的前提上。所以先把真实响应原样抓下来,存成夹具,再照着它写映射;测试也照着夹具跑,
不再依赖当时的网络。

只读:**只发 GET、只打印、只写 `--out` 那个文件**,不碰数据库、不碰设置。

用法:
    python scripts/probe-family.py                     # 读内置那四个 Bangumi id
    python scripts/probe-family.py --ids 81467,282372
    python scripts/probe-family.py --out .tmp/family.json

凭据是可选的:没有也照样问公开条目(Bangumi 的 relations 与 volumes 都不要令牌)。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.sources import SOURCES  # noqa: E402

#: 《安达与岛村》那一族。用户给的验收案例就是这四个 id:轻小说、动画、两部漫画改编。
DEFAULT_IDS = ("81467", "282372", "181467", "283417")

#: 跑一次就够、再跑也不会变的那些:关系与卷。**不含搜索** —— 搜索随对方索引变,记下来会变成假夹具。
BANGUMI_URLS = {
    "entry": "https://api.bgm.tv/v0/subjects/{id}",
    "relations": "https://api.bgm.tv/v0/subjects/{id}/subjects",
}

#: 单个条目:`type`(1 书籍 / 2 动画 / 4 游戏)与 `platform`(漫画 / 画集……)都在这儿,
#: 而关系表里没有 `platform` —— 判断目标是不是故事类时要用它。
SUBJECT_ONE = "https://api.bgm.tv/v0/subjects/{id}"


def _json(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def probe_bangumi(ids: tuple[str, ...]) -> dict[str, Any]:
    """把 Bangumi 那几个 id 的条目、关系、卷原样抓一份。

    **走 `app` 里那个源自己的方法**,不另写一份请求:夹具要反映的是「Pansy 会看到什么」,
    另写一份就成了另一套抓法的产物,照着它写的映射可能跟程序实际拿到的对不上。
    """
    import urllib.error
    import urllib.request

    from app.sources.bangumi import Bangumi

    source = Bangumi()
    recorded: dict[str, Any] = {"source": "bangumi", "entries": {}, "errors": {}, "origin_titles": {}}

    for external_id in ids:
        entry: dict[str, Any] = {}
        for label, url in BANGUMI_URLS.items():
            request = urllib.request.Request(
                url.format(id=external_id),
                headers={"User-Agent": "Th1rtynine/Pansy (https://github.com/Th1rtynine/Pansy)"},
            )
            try:
                with urllib.request.urlopen(request, timeout=20) as answer:
                    entry[label] = json.load(answer)
            except urllib.error.HTTPError as error:
                recorded["errors"][f"{external_id}/{label}"] = f"HTTP {error.code}"
            except OSError as error:
                recorded["errors"][f"{external_id}/{label}"] = f"{type(error).__name__}: {error}"

        # **「原作」那两个字的标题要单独取一次**:关系表里**只有 id、名字、类型,没有 `platform`**,
        # 而「原作」这条判据恰恰要靠标题 —— 一部漫画的「原作」会同时指向同名的轻小说和一部无关动画
        # (实测:181467 的「原作」里有 7931《返乡战士》)。不把它们取回来,夹具就考不了这条规则,
        # 测试只能去连网 —— 那正是这一整套要避免的。
        if isinstance(entry.get("relations"), list):
            recorded["origin_titles"][external_id] = _origin_targets(
                entry["relations"], recorded["errors"], external_id
            )

        # 这两条走源自己的方法:它们的形状就是程序真正吃进去的形状。
        try:
            entry["volumes"] = [
                {
                    "external_id": draft.external_id,
                    "number": draft.number,
                    "title": draft.title,
                    "published_on": draft.published_on,
                }
                for draft in source.volumes_of(external_id)
            ]
        except Exception as error:  # noqa: BLE001 — 抓样本时哪一种失败都要记下来,不能中断整轮
            recorded["errors"][f"{external_id}/volumes_of"] = f"{type(error).__name__}: {error}"

        try:
            identity = source.identity(external_id)
            entry["identity"] = (
                {
                    "external_id": identity.candidate.external_id,
                    "title": identity.candidate.title,
                    "relations": list(identity.relations),
                }
                if identity
                else None
            )
        except Exception as error:  # noqa: BLE001
            recorded["errors"][f"{external_id}/identity"] = f"{type(error).__name__}: {error}"

        recorded["entries"][external_id] = entry

    return recorded


def _origin_targets(relations: list, errors: dict[str, str], external_id: str) -> list[dict]:
    """把这一条的「原作」目标各自取一份条目,只要判断用得上的那几格。

    取回来的是 `type` 与 `platform`:判断「原作」可不可信要看目标是不是故事类(画集、设定集的 `platform`
    会写出来),而关系表里没有这两格。
    """
    import urllib.error
    import urllib.request

    found: list[dict] = []
    for item in relations:
        if not isinstance(item, dict) or str(item.get("relation") or "") != "原作":
            continue
        target = str(item.get("id"))
        record = {
            "id": item.get("id"),
            "name": item.get("name"),
            "name_cn": item.get("name_cn"),
            "type": item.get("type"),
        }
        request = urllib.request.Request(
            SUBJECT_ONE.format(id=target),
            headers={"User-Agent": "Th1rtynine/Pansy (https://github.com/Th1rtynine/Pansy)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as answer:
                detail = json.load(answer)
            record["platform"] = detail.get("platform")
            record["type"] = detail.get("type")
            record["name_cn"] = detail.get("name_cn") or record["name_cn"]
        except urllib.error.HTTPError as error:
            errors[f"{external_id}/origin/{target}"] = f"HTTP {error.code}"
        except OSError as error:
            errors[f"{external_id}/origin/{target}"] = f"{type(error).__name__}: {error}"
        found.append(record)
    return found


def brief(recorded: dict[str, Any]) -> list[str]:
    """把抓到的关系缩成几行给人看:哪个 id、什么关系词、指向谁。分类规则照这个写。"""
    lines = []
    for external_id, entry in recorded.get("entries", {}).items():
        title = (entry.get("entry") or {}).get("name_cn") or (entry.get("entry") or {}).get("name") or "?"
        relations = entry.get("relations") or []
        volumes = entry.get("volumes") or []
        lines.append(f"{external_id}  {title}")
        for item in relations if isinstance(relations, list) else []:
            if isinstance(item, dict):
                lines.append(
                    f"    关系 {str(item.get('relation') or '?'):<8} -> "
                    f"{item.get('id')}  {item.get('name_cn') or item.get('name')}"
                )
        lines.append(f"    volumes_of 回 {len(volumes)} 卷")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="抓一份来源关系的真实样本")
    parser.add_argument("--ids", default=",".join(DEFAULT_IDS), help="逗号分隔的 Bangumi id")
    parser.add_argument("--out", default=".tmp/family-sample.json", help="写到哪儿")
    arguments = parser.parse_args()

    ids = tuple(part.strip() for part in arguments.ids.split(",") if part.strip())
    print(f"源:{', '.join(sorted(SOURCES))}")
    print(f"要抓的 Bangumi id:{'、'.join(ids)}\n")

    recorded = probe_bangumi(ids)

    for line in brief(recorded):
        print(line)

    if recorded["errors"]:
        print("\n没抓到的:")
        for where, reason in recorded["errors"].items():
            print(f"  {where}: {reason}")

    destination = PROJECT_ROOT / arguments.out
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(recorded, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\n原样样本写到 {destination}")
    print(f"抓到的关系词:{sorted({str(i.get('relation')) for e in recorded['entries'].values() for i in (e.get('relations') or []) if isinstance(i, dict)})}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
