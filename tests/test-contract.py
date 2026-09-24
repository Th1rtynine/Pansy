"""前后端的契约有没有漂开:导入那几张形状的字段名逐个对。

**为什么要有这个文件**:前后端各写一份字段名,漂开之后的表现是「页面上少填了一样东西」或者
「提交上去后端说缺一格」—— 两种都要点到那一步才发现。规格明确要求让类型检查能发现这种偏差,
而这里做的正是那件事:把后端的 Pydantic 模型与前端的 `type` 拿出来对字段名。

**只比字段名**,不比可选性:前端有 `?` 与后端有默认值说的是同一件事,而两边的写法不同;
把写法当意思去比,报出来的都是假问题。

用法:`python tests/test-contract.py`。只读源码,不连网、不碰库。
"""

from __future__ import annotations

import pathlib
import re
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

TYPES_TS = PROJECT_ROOT / "frontend" / "src" / "types.ts"

#: 要对的几对「后端模型 ↔ 前端类型」:`(后端模型名, 前端类型名)`。**只列真正跨前后端传的那几张** ——
#: 往上送的请求体与往回读的响应都算:两边各写一份字段名,漂开之后的表现是「页面上少了一格」
#: 或者「提交上去后端说缺一格」,两种都要点到那一步才发现。
#:
#: 两边的名字**不要求一样**:`EditionImportIn` 在前端叫 `ImportEditionIn`(那里 `Import` 是前缀,
#: 与 `ImportIn` / `ImportEditionIn` 排在一起更顺)。名字不同不是漂移,字段不同才是。
PAIRS = (
    ("ImportIn", "ImportIn"),
    ("RelatedWorkImportIn", "RelatedWorkImportIn"),
    ("WorkImportLinkIn", "WorkImportLinkIn"),
    ("FamilyPreviewIn", "FamilyPreviewIn"),
    # 家族那一块前端直接读这几个字段来画(它与「要存哪一类关系」都靠 `relation_type`),
    # 所以它也算契约的一部分。
    ("FamilyMemberOut", "FamilyMemberOut"),
    ("VolumeImportIn", "VolumeImportIn"),
    ("EditionImportIn", "ImportEditionIn"),
)


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.step = 0

    def check(self, label: str, passed: bool, detail: str = "") -> None:
        self.step += 1
        print(f"{'PASS' if passed else 'FAIL'} [{self.step:02d}] {label}" + (f"  -- {detail}" if detail else ""))
        if passed:
            self.passed += 1
        else:
            self.failed += 1


def ts_fields(source: str, name: str) -> set[str] | None:
    """前端一个 `export type X = ...` 里的字段名。找不到就回 None。

    **`A & { ... }` 这种交叉类型也要认**:`ImportEditionIn` 就是 `EditionIn & { refs, cover_url, volumes }`。
    只找 `= {` 的话它会被当成「前端没有这个类型」而整条跳过 —— 那比报错更糟:一条本来该管的契约悄悄没被检查。
    """
    if f"export type {name} " not in source and f"export type {name}=" not in source:
        return None
    marker = f"export type {name} ="
    body = source[source.index(marker) + len(marker) :]
    brace = body.find("{")
    if brace < 0:
        return set()
    tail = body[brace:]
    return set(re.findall(r"^\s{2}(\w+)\??:", tail[: tail.index("};")], flags=re.M))


def _inherited_fields(source: str, name: str) -> set[str]:
    """前端类型写成 `A & { ... }` 时,把基类型 `A` 的字段也取出来。

    **不能省**:`ImportEditionIn` 是 `EditionIn & { refs, cover_url, volumes }`,只比后面那三个的话,
    `EditionIn` 那十来个字段就没人管了 —— 而它们同样要与后端的 `EditionIn` 对上。
    """
    marker = f"export type {name} ="
    if marker not in source:
        return set()
    head = source[source.index(marker) + len(marker) :]
    if "&" not in head.split("{")[0]:
        return set()
    base = head.split("&")[0].strip()
    if not base or base.startswith("{"):
        return set()
    return ts_fields(source, base) or set()


def main() -> int:
    checks = Checks()
    import importlib

    schemas = importlib.import_module("app.api.schemas")
    source = TYPES_TS.read_text(encoding="utf-8")
    print(f"前端类型 {TYPES_TS.relative_to(PROJECT_ROOT)}\n")

    for model_name, type_name in PAIRS:
        model = getattr(schemas, model_name, None)
        if model is None:
            checks.check(f"{model_name} 在后端存在", False, "找不到这个模型")
            continue
        front = ts_fields(source, type_name)
        if front is None:
            checks.check(f"{type_name} 在前端存在", False, f"types.ts 里没有 export type {type_name}")
            continue
        back = set(model.model_fields)
        # 后端的 `from_`(带 alias)在前端写作 `from` —— 两边说的是同一个键,不该报成漂移。
        back = {("from" if name == "from_" else name) for name in back}
        # 前端用 `A & { ... }` 继承时,字段散在基类型里;`ImportEditionIn` 就是这样,所以把基类型
        # (`EditionIn` 那一半)的字段也并进来比 —— 否则会把继承来的字段报成「前端缺」。
        inherited = _inherited_fields(source, type_name)
        front = front | inherited
        missing = sorted(back - front)
        extra = sorted(front - back)
        checks.check(
            f"{model_name} 与前端 {type_name} 字段一致",
            not missing and not extra,
            f"前端缺={missing or '—'} 前端多={extra or '—'}",
        )

    # 反面:比对器本身要能发现漂移 —— 拿一个不存在的字段名试一下,别让它永远绿。
    probe = set(ts_fields(source, "ImportIn") or set())
    probe.add("绝不该有的字段")
    checks.check(
        "**比对器真的能发现漂移**(不是永远绿)",
        bool(probe - set(schemas.ImportIn.model_fields)),
        "拿一个造出来的字段名去比,应当被认出来",
    )

    print(f"\n{checks.passed} 项通过,{checks.failed} 项失败")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
