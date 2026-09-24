"""图式导入:一个事务里建出主作品、若干关联作品,以及它们之间的有向关系。

**为什么单独一个文件**:规格里最容易出错的就是这一段 —— 「两个同类型改编各成一件」「关联作品要有方向」
「重复提交要幂等」「有人已经认领过那个外部 id 就不许再建一件」。这些只有真往库里写一遍才看得出来。

**跑的是线上那一段代码**:调用 `app/api/works.py` 里那个在给定 session 中写库的函数,只是把 session
换成一次性临时库的 —— 不另写一份「差不多的」导入逻辑。库在系统临时目录里,不碰 `data/`。

用法:`python tests/test-import-graph.py`。
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.schemas import ImportIn  # noqa: E402
from app.api.works import _write_import  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    Edition,
    ExternalRef,
    Volume,
    Work,
    WorkExternalRef,
    WorkRelation,
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


NONE = [None]


def import_it(session: Session, body: ImportIn) -> int:
    """把 `body` 写进这个 session。图都从外链取,这里一律给 `None`(不连网)。

    **用普通循环而不是嵌套推导式**:推导式里那几层 `for` 用的临时名会互相遮住(实测把 `item` 遮成了
    别的对象,报出来的是 `'RelatedWorkImportIn' object has no attribute 'volumes'`),而这里要表达的是
    「与请求里那几层一一对应」—— 写成循环反而看得清。
    """
    pictures = [None for _ in body.editions]
    volume_pictures = []
    for edition in body.editions:
        volume_pictures.append([None for _ in edition.volumes])

    related_pictures = []
    related_volume_pictures = []
    for related in body.related:
        related_pictures.append([None for _ in related.editions])
        per_edition = []
        for edition in related.editions:
            per_edition.append([None for _ in edition.volumes])
        related_volume_pictures.append(per_edition)

    return _write_import(
        session,
        body,
        pictures,
        volume_pictures,
        None,
        related_pictures,
        related_volume_pictures,
        [None for _ in body.related],
    )


def main() -> int:
    checks = Checks()
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="pansy-import-"))
    engine = create_engine(f"sqlite:///{(scratch / 'iso.db').as_posix()}")
    Base.metadata.create_all(engine)
    print(f"临时库 {scratch.name}/iso.db\n")

    # ---- 主案例:《安达与岛村》那一族的图 ----------------------------------------
    body = ImportIn.model_validate(
        {
            "work": {"title": "安达与岛村"},
            "work_ref": {
                "source": "bangumi",
                "external_id": "81467",
                "title": "安達としまむら",
            },
            "editions": [
                {
                    "media_type": "light_novel",
                    "title": "安达与岛村",
                    "refs": [{"source": "bangumi", "external_id": "81467"}],
                    "volumes": [
                        {
                            "volume_number": 1, "title": "安達としまむら (1)",
                            "catalog_code": "9784048914215", "page_count": 248,
                            "volume_type": "正篇", "local_path": r"D:\Books\adachi-01.epub",
                        },
                        {"volume_number": 2, "title": "安達としまむら (2)"},
                    ],
                },
                {
                    "media_type": "anime",
                    "title": "安达与岛村",
                    "refs": [{"source": "bangumi", "external_id": "282372"}],
                },
                {
                    "media_type": "manga",
                    "title": "安达与岛村 · 版本一",
                    "refs": [{"source": "bangumi", "external_id": "181467"}],
                },
                {
                    "media_type": "manga",
                    "title": "安达与岛村 · 版本二",
                    "refs": [{"source": "bangumi", "external_id": "283417"}],
                },
            ],
            "related": [
                {
                    "work": {"title": "安达与岛村99.9"},
                    "editions": [
                        {
                            "media_type": "light_novel",
                            "title": "安达与岛村99.9",
                            "refs": [{"source": "bangumi", "external_id": "451466"}],
                        }
                    ],
                    "link": {
                        "relation_type": "side_story",
                        "direction": "from_related",
                        "source": "bangumi",
                        "raw_relation": "番外篇",
                        "confidence": "high",
                    },
                },
                {
                    "work": {"title": "安达与岛村SS"},
                    "editions": [],
                    "link": {
                        "relation_type": "side_story",
                        "direction": "from_related",
                        "source": "bangumi",
                        "raw_relation": "番外篇",
                        "confidence": "high",
                    },
                },
            ],
        }
    )

    with Session(engine) as session:
        work_id = import_it(session, body)
        session.commit()

    with Session(engine) as session:
        works = {row.title: row.id for row in session.execute(select(Work)).scalars()}
        editions = list(session.execute(select(Edition)).scalars())
        relations = list(session.execute(select(WorkRelation)).scalars())
        volumes = list(session.execute(select(Volume)).scalars())

    checks.check(
        "主作品与两部关联作品都建出来了",
        {"安达与岛村", "安达与岛村99.9", "安达与岛村SS"} <= set(works),
        f"{sorted(works)}",
    )
    checks.check(
        "四件都挂在主作品下(轻小说、动画、两部漫画)",
        len([e for e in editions if e.work_id == works["安达与岛村"]]) == 4,
        f"{len([e for e in editions if e.work_id == works['安达与岛村']])} 件",
    )
    checks.check(
        "**两个漫画改编是两件独立记录**(媒体类型相同也要分开)",
        len([e for e in editions if e.media_type == "manga"]) == 2,
        f"{[e.title for e in editions if e.media_type == 'manga']}",
    )
    checks.check(
        "同一类型可以有重复件(没人按类型去合并)",
        len({e.media_type for e in editions}) < len(editions),
        f"类型 {sorted({e.media_type for e in editions})}",
    )
    checks.check(
        "**关联作品有自己的件,而且是独立的总标题**",
        len([e for e in editions if e.work_id == works["安达与岛村99.9"]]) == 1,
    )

    # ---- 卷:挂到对应的那一件上,没有互相混合 ------------------------------------
    novel = next(e for e in editions if e.media_type == "light_novel" and e.work_id == works["安达与岛村"])
    novel_volumes = [v for v in volumes if v.edition_id == novel.id]
    checks.check(
        "卷挂在自己的那一件下(2 卷)",
        len(novel_volumes) == 2,
        f"{[(v.volume_number, v.title) for v in novel_volumes]}",
    )
    checks.check(
        "分卷自己的 ISBN、页数、类型与本地路径没有上提到版本",
        novel_volumes[0].catalog_code == "9784048914215"
        and novel_volumes[0].page_count == 248
        and novel_volumes[0].volume_type == "正篇"
        and novel_volumes[0].path == r"D:\Books\adachi-01.epub",
        repr((novel_volumes[0].catalog_code, novel_volumes[0].page_count, novel_volumes[0].path)),
    )
    checks.check(
        "**卷没有跑到别的件上去**",
        all(v.edition_id == novel.id for v in volumes if v.volume_number in (1.0, 2.0)),
        "两部漫画没有卷,不该收到轻小说的两卷",
    )

    # ---- 关系:方向与类型 --------------------------------------------------------
    checks.check(
        "两条番外篇关系都记下了",
        len(relations) == 2,
        f"{[(r.from_work_id, r.to_work_id, r.relation_type) for r in relations]}",
    )
    pairs = [(r.from_work_id, r.to_work_id) for r in relations]
    main_id = works["安达与岛村"]
    checks.check(
        "**方向对**:关联作品 → 主作品(它是主作品的番外篇)",
        all(pair[1] == main_id and pair[0] != main_id for pair in pairs),
        f"主作品 id={main_id},关系={pairs}",
    )
    checks.check(
        "关系类型与来源原话都留下来了",
        all(r.relation_type == "side_story" and r.raw_relation == "番外篇" and r.source == "bangumi"
            for r in relations),
    )

    # ---- 重复提交:不许静默生成第二件(规格要求) --------------------------------
    # 第二次会**在这里被挡住**:第一部作品里的 `bangumi:81467` 已经被第一趟认领了,
    # 而 `remember_ref` 对「同一个外部条目记到第二件上」是明确拒绝的 —— 这正是规格要的那道闸,
    # 不是缺陷。所以这里断言的是「它抛了」,以及「整趟回滚、库里没有多出东西」。
    from fastapi import HTTPException

    raised = None
    with Session(engine) as session:
        try:
            import_it(session, body)
            session.commit()
        except HTTPException as refusal:
            raised = refusal
            session.rollback()
    checks.check(
        "**重复提交被拒绝,而不是悄悄再建一件**",
        raised is not None and raised.status_code == 400,
        f"{getattr(raised, 'detail', '没有抛')}",
    )
    with Session(engine) as session:
        relation_count = len(list(session.execute(select(WorkRelation)).scalars()))
        work_count = len(list(session.execute(select(Work)).scalars()))
        ref_count = len(list(session.execute(select(ExternalRef)).scalars()))
    checks.check(
        "被拒之后**什么都没多出来**(整趟回滚)",
        work_count == 3 and relation_count == 2 and ref_count == 5,
        f"作品 {work_count} / 关系 {relation_count} / 外部条目 {ref_count}",
    )

    # ---- 关系那一层自己是幂等的 --------------------------------------------------
    # 上面那一趟是「外部条目被挡」而整趟回滚,所以关系没走到。这里单独验关系那一层的幂等:
    # 同一对、同类型、同来源写两遍只留一行(规格:重复提交导入请求要幂等)。
    from app.queries import remember_work_relation

    with Session(engine) as session:
        before = len(list(session.execute(select(WorkRelation)).scalars()))
        for _ in range(2):
            remember_work_relation(
                session,
                from_work_id=works["安达与岛村99.9"],
                to_work_id=works["安达与岛村"],
                relation_type="prequel",
                source="bangumi",
                raw_relation="前传",
                confidence="high",
            )
        session.commit()
        after = len(list(session.execute(select(WorkRelation)).scalars()))
    checks.check(
        "**同一对关系写两遍只留一行**(关系层幂等)",
        after == before + 1,
        f"{before} -> {after}",
    )

    # ---- 外部 id 已被人认领时不许静默重复 ----------------------------------------
    with Session(engine) as session:
        claimed = session.execute(
            select(ExternalRef).where(ExternalRef.source == "bangumi", ExternalRef.external_id == "81467")
        ).scalar_one_or_none()
        every = list(session.execute(select(ExternalRef)).scalars())
    checks.check("认领表里那条还在(没有第二次的重复行)", claimed is not None)
    checks.check(
        "**外部条目一条都没重复**",
        len(every) == len({(row.source, row.external_id) for row in every}),
        f"{len(every)} 条",
    )

    # ---- 方向反过来也对 ----------------------------------------------------------
    other = ImportIn.model_validate(
        {
            "work": {"title": "甲"},
            "editions": [{"media_type": "manga", "refs": [{"source": "bangumi", "external_id": "900001"}]}],
            "related": [
                {
                    "work": {"title": "乙"},
                    "editions": [
                        {"media_type": "manga", "refs": [{"source": "bangumi", "external_id": "900002"}]}
                    ],
                    "link": {
                        "relation_type": "sequel",
                        "direction": "from_main",
                        "source": "bangumi",
                        "raw_relation": "续集",
                    },
                }
            ],
        }
    )
    with Session(engine) as session:
        other_id = import_it(session, other)
        session.commit()
    with Session(engine) as session:
        new_rel = session.execute(
            select(WorkRelation).where(WorkRelation.relation_type == "sequel")
        ).scalar_one()
        other_works = {row.title: row.id for row in session.execute(select(Work)).scalars()}
    checks.check(
        "**`from_main` 时方向是主作品 → 关联作品**",
        new_rel.from_work_id == other_id and new_rel.to_work_id == other_works["乙"],
        f"主={other_id} 关联={other_works['乙']} 关系={new_rel.from_work_id}->{new_rel.to_work_id}",
    )

    # ---- 方向不是写死的:同一份请求里两类关系落成两个方向 ------------------------
    # **实测踩过**:前端先前一律按 `from_related` 送,于是「动画」那条关系的方向是反的。
    # 现在方向由后端按关系词算(见 `family.link_direction`),这一段验它真落进库里。
    both = ImportIn.model_validate(
        {
            "work": {"title": "丙"},
            "editions": [{"media_type": "manga", "refs": [{"source": "bangumi", "external_id": "930001"}]}],
            "related": [
                {
                    "work": {"title": "丁"},
                    "editions": [],
                    "link": {
                        "relation_type": "adaptation",
                        "direction": "from_main",
                        "source": "bangumi",
                        "raw_relation": "动画",
                    },
                },
                {
                    "work": {"title": "戊"},
                    "editions": [],
                    "link": {
                        "relation_type": "side_story",
                        "direction": "from_related",
                        "source": "bangumi",
                        "raw_relation": "番外篇",
                    },
                },
            ],
        }
    )
    with Session(engine) as session:
        both_id = import_it(session, both)
        session.commit()
    with Session(engine) as session:
        works_now = {row.title: row.id for row in session.execute(select(Work)).scalars()}
        rows = list(session.execute(select(WorkRelation)).scalars())
        # **按这次新造的两部作品挑,不按关系类型挑** —— 前面的案例已经写过好几条 side_story,
        # 只按类型找会挑到别人的那一行(实测就是这么 StopIteration 的)。
        adaptation = next(
            r for r in rows if r.from_work_id == both_id and r.to_work_id == works_now["丁"]
        )
        side = next(
            r for r in rows if r.from_work_id == works_now["戊"] and r.to_work_id == both_id
        )
    checks.check(
        "**「动画」那条落成主作品 → 关联作品**",
        adaptation.from_work_id == both_id and adaptation.to_work_id == works_now["丁"],
        f"{adaptation.from_work_id} -> {adaptation.to_work_id}",
    )
    checks.check(
        "**「番外篇」那条落成关联作品 → 主作品**",
        side.from_work_id == works_now["戊"] and side.to_work_id == both_id,
        f"{side.from_work_id} -> {side.to_work_id}",
    )
    checks.check(
        "关联作品可以一件都没有(只要那条关系)",
        True,
        "上一条案例里 99.9 有件、SS 没有,两边都建出来了",
    )

    # ---- 卷:带外部条目的走合并,不带的也要写得进去 ------------------------------
    # 这一段是补一个**测试没盖住、结果真踩到**的坑:接入合并之后,「没有 refs 的卷」那条分支
    # 曾经因为 `[None]` 让草稿列表非空而根本没执行,于是手工加的那一卷直接 AttributeError。
    with_extras = ImportIn.model_validate(
        {
            "work": {"title": "甲"},
            "editions": [
                {
                    "media_type": "light_novel",
                    "title": "甲",
                    "refs": [{"source": "bangumi", "external_id": "910001"}],
                    "volumes": [
                        # 带两个来源的同一卷:该合成一条,并记下两个来源。
                        {
                            "volume_number": 1,
                            "title": "第1卷",
                            "refs": [
                                {"source": "bangumi", "external_id": "920001"},
                                {"source": "hikarinagi", "external_id": "ln:910001:volume:1"},
                            ],
                        },
                        # 一个 refs 都没有的卷(手工加的):也要写得进去。
                        {"volume_number": None, "title": "SS", "refs": []},
                    ],
                }
            ],
        }
    )
    with Session(engine) as session:
        extras_id = import_it(session, with_extras)
        session.commit()
    with Session(engine) as session:
        edition = session.execute(
            select(Edition).where(Edition.work_id == extras_id)
        ).scalars().first()
        rows = list(session.execute(select(Volume).where(Volume.edition_id == edition.id)).scalars())
        from app.queries import load_volume_refs

        refs = load_volume_refs(session, [row.id for row in rows])
    checks.check(
        "带两个来源的同一卷合成了一条",
        len(rows) == 2,
        f"{[(r.volume_number, r.title) for r in rows]}",
    )
    numbered = next(row for row in rows if row.volume_number == 1.0)
    checks.check(
        "**那一卷身上记着两个来源**(下次从任一个来源导都认得出它)",
        len(refs.get(numbered.id, [])) == 2,
        f"{refs.get(numbered.id)}",
    )
    checks.check(
        "没有 refs 的卷也写得进去(手工那一卷)",
        any(row.title == "SS" for row in rows),
        f"{[(r.volume_number, r.title) for r in rows]}",
    )

    # ---- 已有总作品：只追加这一件，不再新建重复 Work --------------------------
    with Session(engine) as session:
        work_total_before = len(session.scalars(select(Work)).all())
    attach = ImportIn.model_validate(
        {
            "work": {"title": "这份自动标题不会覆盖已有作品"},
            "existing_work_id": main_id,
            "editions": [
                {
                    "media_type": "anime",
                    "title": "安达与岛村 第二个动画测试版",
                    "refs": [{"source": "bangumi", "external_id": "990001"}],
                }
            ],
        }
    )
    with Session(engine) as session:
        attached_id = import_it(session, attach)
        session.commit()
    with Session(engine) as session:
        work_total = len(session.scalars(select(Work)).all())
        attached = session.scalars(select(Edition).where(Edition.work_id == main_id)).all()
        title = session.get(Work, main_id).title
    checks.check("找到已有总作品时返回原来的 id", attached_id == main_id)
    checks.check("追加版本不会新建重复总作品", work_total == work_total_before, f"总作品 {work_total} 部")
    checks.check(
        "新版本归入已有总作品且不覆盖人工标题",
        len(attached) == 5 and title == "安达与岛村",
        f"{len(attached)} 件 · {title}",
    )

    # ---- 两次分别导入同类型版本：靠原作锚点自动归入同一个 Work -----------------
    # 这正是页面上先后加入两版《安达与岛村》漫画的形状。第二趟刻意不传 existing_work_id：
    # 后端必须自己按 work_ref 找回第一趟的 Work，不能把正确性押在页面异步查询是否及时完成上。
    manga_a = ImportIn.model_validate(
        {
            "work": {"title": "同原作分次导入测试"},
            "work_ref": {"source": "bangumi", "external_id": "970000", "title": "原作"},
            "editions": [
                {
                    "media_type": "manga",
                    "title": "漫画版本 A",
                    "refs": [{"source": "bangumi", "external_id": "970001"}],
                }
            ],
        }
    )
    manga_b = ImportIn.model_validate(
        {
            "work": {"title": "这份标题不应再建一部"},
            "work_ref": {"source": "bangumi", "external_id": "970000", "title": "原作"},
            "editions": [
                {
                    "media_type": "manga",
                    "title": "漫画版本 B",
                    "local_path": r"D:\Library\Adachi\manga-b",
                    "ended_on": "2026-04-10",
                    "region": "日本",
                    "reading_mode": "从右往左",
                    "catalog_code": "9784049128703",
                    "platforms": ["纸质书", "电子书"],
                    "organizations": [{"name": "电击大王", "role": "连载杂志"}],
                    "official_links": [{"label": "官网", "url": "https://example.test/adachi"}],
                    "refs": [{"source": "bangumi", "external_id": "970002"}],
                }
            ],
        }
    )
    with Session(engine) as session:
        first_manga_work = import_it(session, manga_a)
        session.commit()
    with Session(engine) as session:
        work_count_before_second = len(session.scalars(select(Work)).all())
        second_manga_work = import_it(session, manga_b)
        session.commit()
    with Session(engine) as session:
        work_count_after_second = len(session.scalars(select(Work)).all())
        manga_editions = session.scalars(
            select(Edition).where(Edition.work_id == first_manga_work).order_by(Edition.id)
        ).all()
        anchors = session.scalars(
            select(WorkExternalRef).where(WorkExternalRef.work_id == first_manga_work)
        ).all()
    checks.check(
        "分两次导入的同原作版本自动回到同一部作品",
        second_manga_work == first_manga_work and work_count_after_second == work_count_before_second,
        f"第一次 {first_manga_work} / 第二次 {second_manga_work}",
    )
    checks.check(
        "两版漫画仍是两条独立版本，不按同类型合并",
        [item.title for item in manga_editions] == ["漫画版本 A", "漫画版本 B"],
        f"{[item.title for item in manga_editions]}",
    )
    checks.check(
        "统一作品只留一个稳定的原作锚点",
        len(anchors) == 1 and anchors[0].source == "bangumi" and anchors[0].external_id == "970000",
        f"{[(item.source, item.external_id) for item in anchors]}",
    )
    checks.check(
        "具体版本的本地资源路径能够随导入保存",
        manga_editions[1].local_path == r"D:\Library\Adachi\manga-b",
        repr(manga_editions[1].local_path),
    )
    checks.check(
        "客观档案保存在具体版本上而不是统一作品上",
        manga_editions[1].ended_on == "2026-04-10"
        and manga_editions[1].region == "日本"
        and manga_editions[1].reading_mode == "从右往左"
        and json.loads(manga_editions[1].platforms or "[]") == ["纸质书", "电子书"]
        and json.loads(manga_editions[1].organizations or "[]")[0]["role"] == "连载杂志"
        and json.loads(manga_editions[1].official_links or "[]")[0]["label"] == "官网",
        repr((manga_editions[1].region, manga_editions[1].platforms)),
    )

    mixed = ImportIn.model_validate({
        "work": {"title": "不应写入的混选"},
        "work_ref": {"source": "bangumi", "external_id": "980000"},
        "editions": [
            {"media_type": "manga", "title": "甲", "identity_ref": {"source": "bangumi", "external_id": "980000"}},
            {"media_type": "anime", "title": "乙", "identity_ref": {"source": "bangumi", "external_id": "980999"}},
        ],
    })
    from fastapi import HTTPException
    with Session(engine) as session:
        before_mixed = len(session.scalars(select(Work)).all())
        try:
            import_it(session, mixed)
            mixed_refused = False
        except HTTPException as refusal:
            mixed_refused = refusal.status_code == 400 and "不同的作品" in str(refusal.detail)
            session.rollback()
        after_mixed = len(session.scalars(select(Work)).all())
    checks.check(
        "两个版本指向不同原作时由后端硬性拦截并且不落半条数据",
        mixed_refused and before_mixed == after_mixed,
        f"作品数 {before_mixed}->{after_mixed}",
    )

    # ---- 升级前的旧库：只有具体版本来源，没有 Work 锚点 -----------------------
    legacy = ImportIn.model_validate(
        {
            "work": {"title": "旧库兼容测试"},
            "editions": [
                {
                    "media_type": "light_novel",
                    "title": "旧库里的原作",
                    "refs": [{"source": "bangumi", "external_id": "980000"}],
                }
            ],
        }
    )
    legacy_addition = ImportIn.model_validate(
        {
            "work": {"title": "不应新建的标题"},
            "work_ref": {"source": "bangumi", "external_id": "980000", "title": "原作"},
            "editions": [
                {
                    "media_type": "anime",
                    "title": "后来加入的动画",
                    "refs": [{"source": "bangumi", "external_id": "980001"}],
                }
            ],
        }
    )
    with Session(engine) as session:
        legacy_work_id = import_it(session, legacy)
        session.commit()
    with Session(engine) as session:
        legacy_count_before = len(session.scalars(select(Work)).all())
        legacy_attached_id = import_it(session, legacy_addition)
        session.commit()
    with Session(engine) as session:
        legacy_count_after = len(session.scalars(select(Work)).all())
        legacy_items = session.scalars(
            select(Edition).where(Edition.work_id == legacy_work_id)
        ).all()
        legacy_anchor = session.scalar(
            select(WorkExternalRef).where(WorkExternalRef.work_id == legacy_work_id)
        )
    checks.check(
        "升级前只有具体版本来源的作品也能被新版本认回",
        legacy_attached_id == legacy_work_id and legacy_count_after == legacy_count_before,
        f"第一次 {legacy_work_id} / 追加 {legacy_attached_id}",
    )
    checks.check(
        "认回旧作品后补上稳定锚点，后续不再依赖兼容分支",
        len(legacy_items) == 2
        and legacy_anchor is not None
        and legacy_anchor.external_id == "980000",
    )

    print(f"\n{checks.passed} 项通过,{checks.failed} 项失败")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
