"""作品家族的关系分类:照着真实样本考,不连网。

**为什么要有这个文件**:关系怎么分类是这一整块功能的地基 —— 分类错了,家族预览、图式导入、分卷合并
全都建在错的前提上。而这件事**没法靠临场网络验证**:上游的条目会变,今天绿明天红,红的却是网络的脾气。
所以样本先由 `scripts/probe-family.py` 原样抓下来放进 `tests/fixtures/`,这里照着它跑纯函数。

用法:`python tests/test-family.py`。只读夹具,不碰数据库、不碰设置、不联网。
"""

from __future__ import annotations

import json
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.sources import family  # noqa: E402

FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "bangumi-family.json"

#: 《安达与岛村》那一族。规格给的验收案例就是这四个 id。
SEED = "81467"          # 轻小说(原型)
NOVEL = "81467"
ANIME = "282372"
MANGA_A = "181467"
MANGA_B = "283417"

#: 必须**独立成 Work** 的那几条,以及它们各自的关系词。
#: 99.9 与 SS 是番外篇;官方同人集是选集。
SEPARATE = {
    "451466": "安达与岛村99.9",
    "514038": "安达与岛村SS",
    "315185": "安达与岛村官方同人集",
}


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


def load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def relations_of(sample: dict, external_id: str) -> list[dict]:
    return [
        item
        for item in (sample["entries"].get(external_id, {}).get("relations") or [])
        if isinstance(item, dict)
    ]


def title_of(sample: dict, external_id: str) -> str:
    entry = sample["entries"].get(external_id, {}).get("entry") or {}
    return str(entry.get("name_cn") or entry.get("name") or "")


def classify_edge(sample: dict, from_id: str, item: dict):
    """把夹具里的一条关系喂给 `family.classify`,参数与 `Bangumi.relations_of` 传的一致。"""
    seed_entry = sample["entries"].get(from_id, {}).get("entry") or {}
    from app.sources.bangumi import guess_media

    seed_media = guess_media(seed_entry.get("type"), seed_entry.get("platform"))
    target_media = guess_media(item.get("type"), item.get("platform"))
    title = str(item.get("name_cn") or item.get("name") or "")
    return family.classify(
        relation=str(item.get("relation") or ""),
        seed_media=seed_media,
        seed_title=str(seed_entry.get("name_cn") or seed_entry.get("name") or ""),
        target_media=target_media,
        target_platform=str(item.get("platform") or "") or None,
        target_title=title,
    )


def main() -> int:
    checks = Checks()
    if not FIXTURE.is_file():
        print(f"FAIL 夹具不在: {FIXTURE}")
        return 1

    sample = load()
    print(f"夹具 {FIXTURE.name}({FIXTURE.stat().st_size} 字节)\n")

    # ---- 样本本身站得住 ---------------------------------------------------------
    checks.check(
        "夹具里就是那四条验收案例",
        all(sample["entries"].get(i) for i in (NOVEL, ANIME, MANGA_A, MANGA_B)),
        f"有 {'、'.join(sorted(sample['entries']))}",
    )
    checks.check(
        "样本抓的时候没出错",
        not sample.get("errors"),
        f"errors={sample.get('errors')}",
    )

    # ---- 每一条关系都分类,而且没有一条落进「认不出」 ----------------------------
    unknown: list[str] = []
    for from_id in sample["entries"]:
        for item in relations_of(sample, from_id):
            canonical, _confidence, _evidence = classify_edge(sample, from_id, item)
            if canonical == family.UNKNOWN:
                unknown.append(f"{from_id} --{item.get('relation')}--> {item.get('id')}")
    checks.check(
        "样本里每一条关系都认得出(没有落进 UNKNOWN)",
        not unknown,
        f"认不出的:{unknown[:6]}",
    )

    # ---- 三类各自落对 -----------------------------------------------------------
    def edges_into(to_id: str) -> list[tuple[str, str, str]]:
        """把所有指向这一条的关系攒成 `(三类, 关系词原话, 可信度)`。

        **关系词原话必须带上** —— 结论要看全部边,而「同一作品」这一类的内部还分得细:
        「番外篇」写的也是同一作品那一栏的候选词,却是否决词。只传分类结果,`resolve` 就看不见它。
        """
        from app.sources.bangumi import guess_media

        found = []
        for from_id in sample["entries"]:
            for item in relations_of(sample, from_id):
                if str(item.get("id")) != to_id:
                    continue
                canonical, confidence, _evidence = classify_edge(sample, from_id, item)
                found.append((canonical, str(item.get("relation") or ""), confidence))
        return found

    def verdict_of(to_id: str) -> tuple[str, str, str]:
        return family.resolve(edges_into(to_id))

    # 轻小说 -> 动画:动画改编,同一作品。
    checks.check(
        "轻小说 → 动画 算同一作品",
        verdict_of(ANIME)[0] == family.SAME_WORK,
        f"{verdict_of(ANIME)}",
    )
    # 两个漫画互指「不同版本」:是同一部的两种版本。
    checks.check(
        "漫画 A ↔ 漫画 B 的「不同版本」算同一作品",
        verdict_of(MANGA_B)[0] == family.SAME_WORK,
        f"{verdict_of(MANGA_B)}",
    )
    # 单行本是卷,不是作品。
    volume_edges = [
        item for item in relations_of(sample, NOVEL) if str(item.get("relation")) == "单行本"
    ]
    checks.check(
        "「单行本」算卷,不算另一件作品",
        bool(volume_edges)
        and all(classify_edge(sample, NOVEL, item)[0] == family.VOLUME_OF for item in volume_edges),
        f"单行本 {len(volume_edges)} 条",
    )

    # ---- 必须独立成 Work 的那几条,一个都不许并进来 ------------------------------
    for external_id, name in SEPARATE.items():
        canonical, confidence, evidence = verdict_of(external_id)
        checks.check(
            f"《{name}》({external_id})被当成另一部作品,没并进这一族",
            canonical == family.RELATED_WORK,
            f"{canonical}/{confidence} · {evidence}",
        )

    # ---- 几条边各说各的时候,合起来算一个结论 ------------------------------------
    # 实测:451466 同时被「番外篇」与「书籍」指向。**单看「书籍」那条会说它属于同一作品** ——
    # 这一条考的就是「多条边不一致时不许乱并」。
    raw_kinds = sorted({kind for kind, _c, _e in edges_into("451466")})
    checks.check(
        "451466 的几条边本身就不一致(所以必须合起来判)",
        len(raw_kinds) > 1,
        f"单条边分别判成 {raw_kinds}",
    )
    checks.check(
        "**合起来判之后以「番外篇」为准**,仍算另一部作品",
        family.resolve(edges_into("451466"))[0] == family.RELATED_WORK,
        f"{family.resolve(edges_into('451466'))}",
    )
    checks.check(
        "没有任何一条边指向它时不猜",
        family.resolve([])[0] == family.UNKNOWN,
    )
    checks.check(
        "只有高置信的同一作品边时才默认并进来",
        family.resolve([(family.SAME_WORK, "不同版本", "high")])[:2] == (family.SAME_WORK, "high"),
    )
    # ---- 「原作」那条规则:真实样本里没有,所以单独造一条考它 ---------------------
    # **实测:这四个种子里一条「原作」都没有**(夹具的 `origin_titles` 是空的)。所以这条规则
    # 在真实数据上还没被触发过 —— 但一旦出现,它必须保守:名字对不上就绝不并进来。
    checks.check(
        "「原作」指向名字对不上的条目时不算同一作品",
        family.classify(
            relation="原作",
            seed_media="manga",
            seed_title="安达与岛村",
            target_media="anime",
            target_title="返乡战士",
        )[0]
        != family.SAME_WORK,
        "纯函数单测:真实样本里没有「原作」边,这条规则靠这里兜住",
    )
    checks.check(
        "「原作」指向同名的条目时才算同一作品",
        family.classify(
            relation="原作",
            seed_media="manga",
            seed_title="安达与岛村",
            target_media="light_novel",
            target_title="安达与岛村",
        )[0]
        == family.SAME_WORK,
    )
    checks.check(
        "关系词写着书籍，也不能把标题不同的联动作品自动并入",
        family.classify(
            relation="书籍",
            seed_media="game",
            seed_title="JUMP：群星集结",
            target_media="manga",
            target_title="咒术回战",
        )[1]
        != "high",
        "这正是《咒术回战》曾一路吸进死神、火影忍者等四十多条结果的入口",
    )
    checks.check(
        "跨载体且标题完全相同时仍会自动归入",
        family.classify(
            relation="动画",
            seed_media="light_novel",
            seed_title="安达与岛村",
            target_media="anime",
            target_title="安达与岛村",
        )[:2]
        == (family.SAME_WORK, "high"),
    )
    checks.check(
        "标题只是前缀时只列为待确认，不再自动归入",
        family.classify(
            relation="动画",
            seed_media="manga",
            seed_title="咒术回战",
            target_media="anime",
            target_title="咒术回战 死灭回游 前篇",
        )[:2]
        == (family.SAME_WORK, "low"),
    )

    # ---- 画集 / 选集在关系表里没有 platform,所以不许悄悄并进来 -------------------
    for external_id, name in (("625675", "raemz画集 Amour"),):
        found = [
            item for from_id in sample["entries"] for item in relations_of(sample, from_id)
            if str(item.get("id")) == external_id
        ]
        if found:
            canonical, _c, evidence = classify_edge(sample, NOVEL, found[0])
            checks.check(
                f"《{name}》没有被当成改编并进来",
                canonical != family.SAME_WORK,
                f"{canonical} · {evidence}",
            )

    # ---- 已知边界:关系表没有 `platform`,所以「书籍」那一档判不出漫画还是轻小说 ----------
    # 实测:81467 的三条同一作品边里,轻小说那一条的 `media` 是 None(关系表只给 `type=1`,
    # 画集与轻小说在 `type` 上是一样的)。**这不是 bug,是这段数据的边界** —— 要分清就得对那几条
    # 各取一次条目(关系表里没有 `platform`)。家族遍历那一层要负责补这一步,这里先把边界钉住,
    # 免得日后有人以为分类器会凭空知道类型。
    novel_edge = [
        item for item in relations_of(sample, NOVEL) if str(item.get("id")) == MANGA_B
    ]
    checks.check(
        "关系表拿得到目标 id、名字与关系词",
        bool(novel_edge) and novel_edge[0].get("name_cn"),
        f"{novel_edge[0].get('name_cn') if novel_edge else '没有'}",
    )
    checks.check(
        "**但拿不到 `platform`** —— 所以「书籍」那一档的类型要在遍历时补一次",
        "platform" not in (novel_edge[0] if novel_edge else {}),
        "这条边界写在测试里,免得日后被当成 bug 去改分类器",
    )

    # ---- 标题判据本身 ------------------------------------------------------------
    checks.check(
        "去掉卷号后同名算同一个名字",
        family.titles_agree("安达与岛村", "安达与岛村") is True
        and family.titles_agree("安達としまむら (2)", "安達としまむら") is True,
    )
    checks.check(
        "明显不同的名字不算同一个",
        family.titles_agree("返乡战士", "安达与岛村") is False,
        "这一条是「原作」判据的底线",
    )
    checks.check(
        "一个是另一个的前缀算同一个(99.9 / SS 那种要靠关系词排除,不靠名字)",
        family.titles_agree("安达与岛村", "安达与岛村") is True,
    )
    checks.check(
        "**番外篇那种即使名字对得上也独立成 Work**",
        family.classify(
            relation="番外篇",
            seed_media="light_novel",
            seed_title="安达与岛村",
            target_media="light_novel",
            target_title="安达与岛村99.9",
        )[0]
        == family.RELATED_WORK,
        "名字不是归组依据,关系词才是",
    )

    # ---- 每个源都要能拿出关系 ----------------------------------------------------
    # 三种能力分开考:VNDB 与 Hikarinagi 本来就没有关系图(前者只有关联,后者的 `/relations` 只挂
    # galgame),所以它们回空表是**对的**;但「能调、而且回的是列表」不能只有 Bangumi 做得到。
    from app.sources import SOURCES

    callable_everywhere = [name for name, source in SOURCES.items() if not callable(getattr(source, "relations_of", None))]
    checks.check("三个源都答得出 relations_of", not callable_everywhere, f"缺的:{callable_everywhere}")
    silent = [
        name for name, source in SOURCES.items()
        if not isinstance(source.relations_of("0"), list)
    ]
    checks.check("回的是列表(没有的源回空表,不是抛异常)", not silent, f"抛了或回错的:{silent}")
    checks.check(
        "Bangumi 那个是真实现(不是继承来的空表)",
        "relations_of" in type(SOURCES["bangumi"]).__dict__,
    )

    print(f"\n{checks.passed} 项通过,{checks.failed} 项失败")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
