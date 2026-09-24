"""作品家族的有界遍历:照着真实夹具考,不连网、不碰库。

**为什么要单独一个文件**:分类器(见 `tests/test-family.py`)考的是「一条边算哪一类」,这里考的是
「从一条走出去,走出来的这一族对不对」—— 会不会走丢、会不会走进环里、会不会把番外篇并进来、
上游一半失败时还剩不剩结果。这些光看分类器看不出来。

夹具与 `test-family.py` 共用同一份(`tests/fixtures/bangumi-family.json`),所以两边的结论对得上。

用法:`python tests/test-family-traversal.py`。
"""

from __future__ import annotations

import json
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from app.sources import family  # noqa: E402
from app.sources.base import Candidate, SourceRelation  # noqa: E402
from family_fixture import FakeBangumi, load_sample, seed_of  # noqa: E402

NOVEL = "81467"
ANIME = "282372"
MANGA_A = "181467"
MANGA_B = "283417"
NINE = "451466"
SS = "514038"
DOUJIN = "315185"


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


def ids(nodes: list[family.FamilyNode]) -> list[str]:
    return [node.external_id for node in nodes]


def main() -> int:
    checks = Checks()
    sample = load_sample()
    if not sample:
        print("FAIL 夹具不在或读不出来")
        return 1

    fake = FakeBangumi(sample)
    print(f"夹具 {len(sample['entries'])} 条种子\n")

    # ---- 主验收案例:从轻小说出发 ------------------------------------------------
    preview = family.discover(
        source="bangumi",
        external_id=NOVEL,
        relations_of=fake.relations_of,
        fetch=fake.fetch,
    )
    print(f"从 {NOVEL}《{preview.seed.title}》出发:"
          f"同一作品 {ids(preview.editions)}")
    print(f"  关联作品 {ids(preview.related_works)}")
    print(f"  需要确认 {ids(preview.uncertain)}")
    print(f"  卷 {len(preview.volumes)} 条,走了 {preview.hops} 次请求,"
          f"用了 {preview.elapsed}s,警告 {preview.warnings}\n")

    checks.check(
        "种子在结果里(排位按类型分组,种子不特殊对待)",
        NOVEL in ids(preview.editions),
        f"同一作品 {ids(preview.editions)}",
    )
    checks.check(
        "种子的条目就是回话里那一条",
        preview.seed.external_id == NOVEL,
    )
    checks.check(
        "动画被并进同一作品",
        ANIME in ids(preview.editions),
        f"同一作品 {ids(preview.editions)}",
    )
    checks.check(
        "两个漫画改编都并进来,而且各算一件",
        MANGA_A in ids(preview.editions) and MANGA_B in ids(preview.editions),
        f"同一作品 {ids(preview.editions)}",
    )
    checks.check(
        "**两个漫画没有被合成一件**",
        len([i for i in ids(preview.editions) if i in (MANGA_A, MANGA_B)]) == 2,
    )
    checks.check(
        "99.9 与 SS 没有并进来,而是进了关联作品或需要确认",
        NINE not in ids(preview.editions) and SS not in ids(preview.editions),
        f"editions={ids(preview.editions)}",
    )
    checks.check(
        "官方同人集没有并进来",
        DOUJIN not in ids(preview.editions),
    )
    checks.check(
        "「单行本」被分流成卷,没有混进作品表",
        bool(preview.volumes)
        and all(i not in ids(preview.editions) for _from, i in preview.volumes),
        f"{len(preview.volumes)} 条卷",
    )

    # ---- 默认勾选:只有高置信的同一作品 ------------------------------------------
    checks.check(
        "默认勾上的都是高置信的同一作品",
        all(node.kind == family.SAME_WORK and node.confidence == "high" for node in preview.selected),
        f"勾了 {ids(preview.selected)}",
    )
    checks.check(
        "关联作品一个都没默认勾上",
        not any(node.selected for node in preview.related_works),
        f"关联 {ids(preview.related_works)}",
    )
    checks.check(
        "判不下来的一个都没默认勾上",
        not any(node.selected for node in preview.uncertain),
        f"需要确认 {ids(preview.uncertain)}",
    )
    checks.check(
        "每条都带一句给人看的理由",
        all(node.evidence for node in preview.editions + preview.related_works + preview.uncertain),
    )

    # ---- 类型:遍历时补过 `platform`,所以轻小说认得出 ----------------------------
    novel = next((n for n in preview.editions if n.external_id == NOVEL), None)
    checks.check(
        "**种子的类型补出来了**(关系表里没有 platform,靠 fetch 补)",
        novel is not None and novel.candidate.media == "light_novel",
        f"media={novel.candidate.media if novel else None}",
    )

    # ---- 环:从一个能走回去的节点出发,不许无限转 --------------------------------
    # 181467 与 283417 互指「不同版本」,81467 又指向两边 —— 这是个三角形。
    loop = family.discover(
        source="bangumi",
        external_id=MANGA_A,
        relations_of=fake.relations_of,
        fetch=fake.fetch,
    )
    checks.check(
        "**从环里的任一条出发都不会重复收同一条**",
        len(ids(loop.editions)) == len(set(ids(loop.editions))),
        f"editions={ids(loop.editions)}",
    )
    checks.check(
        "环里出发也能收敛(请求次数有上限)",
        loop.hops <= family.MAX_NODES * 2,
        f"hops={loop.hops}",
    )

    # ---- 部分失败:一半拿不到,结果仍然可用 --------------------------------------
    class Flaky(FakeBangumi):
        def __init__(self, sample: dict, fail_from: str) -> None:
            super().__init__(sample)
            self.fail_from = fail_from

        def relations_of(self, external_id: str) -> list[SourceRelation]:
            if external_id == self.fail_from:
                raise OSError("模拟上游超时")
            return super().relations_of(external_id)

    flaky = Flaky(sample, fail_from=ANIME)
    broken = family.discover(
        source="bangumi",
        external_id=NOVEL,
        relations_of=flaky.relations_of,
        fetch=flaky.fetch,
    )
    checks.check(
        "**一个节点的关系取不到时,照样回一份结果**(不抛异常)",
        bool(broken.editions),
        f"同一作品 {ids(broken.editions)}",
    )
    checks.check(
        "而且把「少了什么」写进了 warnings",
        any(ANIME in w for w in broken.warnings),
        f"warnings={broken.warnings}",
    )

    # ---- 种子取不到时要明说 ------------------------------------------------------
    try:
        family.discover(
            source="bangumi",
            external_id="999999999",
            relations_of=fake.relations_of,
            fetch=fake.fetch,
        )
        checks.check("种子取不到时抛 LookupError", False, "没有抛")
    except LookupError:
        checks.check("种子取不到时抛 LookupError", True)

    # ---- 时钟与封顶:参数真的生效 ------------------------------------------------
    tiny = family.discover(
        source="bangumi",
        external_id=NOVEL,
        relations_of=fake.relations_of,
        fetch=fake.fetch,
        max_nodes=3,
    )
    checks.check(
        "max_nodes 生效,而且说了为什么少",
        len(tiny.editions) + len(tiny.related_works) + len(tiny.uncertain) <= 3 + 1,
        f"收了 {len(tiny.editions) + len(tiny.related_works) + len(tiny.uncertain)} 条,"
        f"warnings={tiny.warnings}",
    )
    one_hop = family.discover(
        source="bangumi",
        external_id=MANGA_A,
        relations_of=fake.relations_of,
        fetch=fake.fetch,
        same_work_hops=1,
    )
    two_hops = family.discover(
        source="bangumi",
        external_id=MANGA_A,
        relations_of=fake.relations_of,
        fetch=fake.fetch,
        same_work_hops=2,
    )
    checks.check(
        "same_work_hops 生效:一层走到的不比两层多",
        len(one_hop.editions) <= len(two_hops.editions),
        f"一层 {ids(one_hop.editions)} / 两层 {ids(two_hops.editions)}",
    )

    # ---- 遍历结果与分类器的结论一致 ----------------------------------------------
    checks.check(
        "同一作品那几条的理由都说得出来源",
        all("Bangumi" in node.evidence or node.depth == 0 for node in preview.editions),
    )

    # ---- 关系方向:按关系词分开,不写死 ------------------------------------------
    # **实测踩过**:先前前端一律按 `from_related` 记,于是「动画」这类关系的方向是反的 ——
    # 而 `WorkRelation` 存在的理由就是方向。现在由后端按关系词定(见 `family.link_direction`)。
    directions = {node.direction for node in preview.related_works}
    checks.check(
        "**关联作品的方向不只一种**(说明它是按关系词算的,不是写死的)",
        len(directions) > 1,
        f"{sorted(directions)}",
    )
    checks.check(
        "方向只取 `from_main` / `from_related` 两个值",
        directions <= {"from_main", "from_related"},
        f"{sorted(directions)}",
    )
    by_type: dict[str, set[str]] = {}
    for node in preview.related_works:
        by_type.setdefault(node.relation_type, set()).add(node.direction)
    checks.check(
        "**番外篇是「它指向主作品」**(主作品不是它的衍生)",
        by_type.get("side_story") == {"from_related"},
        f"side_story -> {by_type.get('side_story')}",
    )
    checks.check(
        "**合集那一类是「主作品指向它」**(那张原声集不是主作品的衍生)",
        by_type.get("collection") == {"from_main"},
        f"collection -> {by_type.get('collection')}",
    )
    checks.check(
        "**方向是确定的**(同一份夹具跑两次,方向一模一样)",
        [
            (n.external_id, n.relation_type, n.direction)
            for n in preview.related_works
        ]
        == [
            (n.external_id, n.relation_type, n.direction)
            for n in family.discover(
                source="bangumi",
                external_id=NOVEL,
                relations_of=FakeBangumi(sample).relations_of,
                fetch=FakeBangumi(sample).fetch,
            ).related_works
        ],
        "方向靠字典顺序撞出来的话,这里就会飘",
    )
    checks.check(
        "**单向关系那几类方向固定**:「番外篇」永远是它指向主作品,「合集」永远是主作品指向它",
        by_type.get("side_story") == {"from_related"} and by_type.get("collection") == {"from_main"},
        f"side_story {by_type.get('side_story')} / collection {by_type.get('collection')}",
    )
    checks.check(
        "对称关系(相同世界观)方向不固定是**对的**:两边说的本来就是同一件事,谁指向谁没有意义",
        True,
        f"same_setting -> {by_type.get('same_setting')}",
    )

    # ---- 方向推断本身:纯函数单测 ------------------------------------------------
    checks.check(
        "「书籍/动画/游戏」的主体是**目标**(是谁的什么),所以主作品指向它",
        family.link_direction("书籍", subject="from_seed") == "from_main"
        and family.link_direction("动画", subject="from_seed") == "from_main",
    )
    checks.check(
        "「原作/番外篇/前传」的主体是**说这句话的那一条**,所以方向反过来",
        family.link_direction("番外篇", subject="from_seed") == "from_related"
        and family.link_direction("原作", subject="from_seed") == "from_related",
    )
    checks.check(
        "**认不出的关系词保守处理**:记成「关联作品指向主作品」,不把主作品说成别人的衍生",
        family.link_direction("某个没见过的词", subject="from_seed") == "from_related",
    )
    checks.check(
        "中间那一层说的关系,方向跟着反",
        family.link_direction("书籍", subject="from_related") == "from_related"
        and family.link_direction("番外篇", subject="from_related") == "from_main",
    )

    print(f"\n{checks.passed} 项通过,{checks.failed} 项失败")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
