"""关系词 → 三类,以及「这一条凭什么是同一个作品」。

**为什么单独一个模块**:这一段是纯函数,不连网、不碰库 —— 关系怎么分类只能照着真实响应写,
而照着真实响应写的东西必须能单独考。样本见 `tests/fixtures/bangumi-family.json`
(由 `scripts/probe-family.py` 抓下来的原样响应)。

**为什么要两边类型一起判断**:Bangumi 的关系词**指的是目标那一类**,不是方向,而且粗到没法单独用 ——
「书籍」既可能是轻小说改编(同一作品),也可能是画集、官方同人集、选集(都是另一部作品)。
所以判定要看 (关系词, 种子是什么, 目标是什么) 三样。

**一条边不够,要合起来判**:实测 451466《安达与岛村99.9》被两条边指向 —— 81467 说「番外篇」、
282372 说「书籍」。单看一条会得出相反的结论,所以 `resolve` 拿同一个目标的全部边一起算。
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from app.sources.base import Candidate, SourceRelation
from app.sources.query import flat

#: 三类 + 认不出的那一类。写成常量是为了别的地方(预览、导入)不用再抄一遍字符串。
SAME_WORK = "SAME_WORK"
VOLUME_OF = "VOLUME_OF"
RELATED_WORK = "RELATED_WORK"
UNKNOWN = "UNKNOWN"

#: 我们这边的四个媒体类型(与 `app/fields.py` 的 `MEDIA_TYPE_VALUES` 同一套词)。
BOOK_LIKE = ("manga", "light_novel")

# high  = 关系词加两边类型就够确定,默认勾选。
# low   = 说得通但不够确定,进「需要确认」,默认不勾。
# none  = 明确是另一部作品(关联作品),默认不并入。
_HIGH, _LOW, _NONE = "high", "low", "none"

#: 关系词 → (关系性质, 可信度)。**只收实测见过的词**(`scripts/probe-family.py` 的样本里有 11 个)。
#: 前缀 `*` 表示不限媒体类型;带中括号的那几条另有条件,见 `classify`。
BANGUMI_RELATIONS: dict[str, tuple[str, str]] = {
    # ---- 同一作品:改编 ----
    "动画": (SAME_WORK, _HIGH),
    "书籍": (SAME_WORK, _LOW),          # 目标可能是画集 / 选集,可不可信要看类型与标题
    "游戏": (SAME_WORK, _LOW),
    "三次元": (SAME_WORK, _LOW),
    "音乐": (RELATED_WORK, _LOW),       # 音乐条目不是「同一部作品的另一版」,但同族
    # ---- 同一作品:同一部的两种版本 ----
    "不同版本": (SAME_WORK, _HIGH),
    # ---- 卷:单行本是某个系列底下的一册,不是另一件作品 ----
    "单行本": (VOLUME_OF, _HIGH),
    # ---- 另一部作品 ----
    "番外篇": (RELATED_WORK, _HIGH),    # 99.9 与 SS 就是这两个字,必须独立成 Work
    "相同世界观": (RELATED_WORK, _HIGH),
    "画集": (RELATED_WORK, _HIGH),
    "原声集": (RELATED_WORK, _HIGH),
    "片头曲": (RELATED_WORK, _HIGH),
    "片尾曲": (RELATED_WORK, _HIGH),
    "角色歌": (RELATED_WORK, _HIGH),
}

#: 「原作」单独一张表:它的可信度完全取决于**目标是不是种子自己那一部的原作**。
#: 同源(标题一致)才是同一作品;标题不一致时要往下判,不能直接并。见 `classify`。
ORIGINAL_RELATION = "原作"

#: 目标类型 —— 这些是「另一部作品」,即使关系词写着「书籍」。
#: 画集 / 设定集 / 选集这些在 Bangumi 都记成 `type=1`(书籍),`platform` 才分得出来。
NON_STORY_PLATFORMS = (
    "画集",
    "设定集",
    "原画集",
    "插画集",
    "同人集",
    "选集",
    "合集",
    "指南",
    "公式",
    "资料集",
    "音乐",
)

#: 书名里结尾的卷号:「(01)」「第 3 巻」「Vol.2」。判「同一个名字的另一版」时要先把它去掉。
_VOLUME_SUFFIX = re.compile(
    r"^(?P<base>.+?)\s*(?:"
    r"[（(\[【]\s*(?:第\s*)?\d{1,3}\s*(?:巻|卷|册|冊|集|話|话)?\s*[)）\]】]"
    r"|第\s*\d{1,3}\s*(?:巻|卷|册|冊|集|話|话)"
    r"|[Vv]ol\.?\s*\d{1,3}"
    r")\s*$"
)


def base_title(title: str | None) -> str:
    """去掉结尾的卷号,留下「这一部叫什么」。判两个条目是不是同一部的两种版本时用它。"""
    found = _VOLUME_SUFFIX.match((title or "").strip())
    return found.group("base").strip() if found else (title or "").strip()


def looks_like_non_story(platform: str | None, title: str | None) -> bool:
    """这一条是画集 / 设定集 / 选集那一类吗。

    **`platform` 先判,标题兜底** —— 实测画集那一栏的 `platform` 写的是「画集」,分得出来;
    但「官方同人集」那种在 `platform` 上只写「漫画」,只有名字里有「同人集」,所以两者都要看。
    """
    text = f"{platform or ''}"
    if any(word in text for word in NON_STORY_PLATFORMS):
        return True
    return any(word in (title or "") for word in ("画集", "设定集", "原画集", "同人集", "选集", "合集", "指南"))


#: 来源的关系词 → 要存进 `work_relation.relation_type` 的那一类。**只收实测见过的词**
#: (`scripts/probe-family.py` 的样本里那 11 个),加上几个含义无歧义的常见词。
#: 认不出的一律 `related` —— **不猜**:猜错方向比留一个笼统的「相关」糟得多。
RELATION_TYPES: dict[str, str] = {
    "原作": "adaptation",
    "动画": "adaptation",
    "书籍": "adaptation",
    "游戏": "adaptation",
    "三次元": "adaptation",
    "不同版本": "variant",
    "单行本": "volume",
    "番外篇": "side_story",
    "前传": "prequel",
    "后传": "sequel",
    "续集": "sequel",
    "外传": "spin_off",
    "相同世界观": "same_setting",
    "画集": "collection",
    "选集": "collection",
    "合集": "collection",
    "原声集": "collection",
    "片头曲": "collection",
    "片尾曲": "collection",
    "角色歌": "collection",
    "音乐": "collection",
}


def relation_type_of(raw_relation: str) -> str:
    """来源的原话 → 我们要存的那一类。**认不出就是 `related`**,并把这当成正常结果而不是缺陷。"""
    return RELATION_TYPES.get((raw_relation or "").strip(), "related")


#: 关系里**哪一头是主体**。`target` = 来源那句话是在说「对方是这一条的什么」
#: (轻小说指向漫画,写「书籍」);`source` = 反过来(漫画指向轻小说,写「原作」)。
SUBJECT_TARGET = frozenset({"书籍", "动画", "游戏", "三次元", "不同版本", "单行本", "画集", "选集", "合集"})
SUBJECT_SOURCE = frozenset({"原作", "番外篇", "前传", "后传", "续集", "外传", "相同世界观"})


def relation_subject(raw_relation: str) -> str:
    """这句话的主体在哪一头。**认不出时当 `source`** —— 于是一条拿不准的关系会被记成
    「关联作品 → 主作品」,而不是反过来把主作品说成别人的衍生。"""
    word = (raw_relation or "").strip()
    if word in SUBJECT_TARGET:
        return "target"
    if word in SUBJECT_SOURCE:
        return "source"
    return "source"


def link_direction(raw_relation: str, *, subject: str) -> str:
    """要存进 `work_relation` 的方向,取值与前端 `WorkImportLinkIn.direction` 同一套。

    `subject` 是**说那句话的那一条**是主作品(`from_seed`)还是这一条关联作品(`from_related`)。
    回 `from_main` 表示「主作品 → 它」,`from_related` 表示「它 → 主作品」。

    **不能一律写死**:「动画」那句是主作品(轻小说)指向动画,而「番外篇」那句是番外篇指向主作品。
    都记成同一个方向,「谁是番外篇」就再也分不出来了 —— 而 `WorkRelation` 存在的理由正是方向。
    """
    subject_is_target = relation_subject(raw_relation) == "target"
    # 主作品是主体:关系从主作品出发。
    if subject == "from_seed":
        return "from_main" if subject_is_target else "from_related"
    # 这一条关联作品是主体:方向反过来。
    return "from_related" if subject_is_target else "from_main"


def classify(
    *,
    relation: str,
    seed_media: str | None,
    seed_title: str | None,
    target_media: str | None,
    target_kind: str | None = None,
    target_platform: str | None = None,
    target_title: str | None = None,
) -> tuple[str, str, str]:
    """这一条关系该怎么算。回 `(三类之一或 UNKNOWN, 可信度 high/low/unknown, 给人看的一句话)`。

    **参数全是原样传进来的**:这个函数只看词与类型,不做任何请求 —— 所以夹具能完整地考它。

    判定顺序是有意的:先排除「另一部作品」的明确信号(番外篇、画集、选集),再认卷,最后才认同一作品。
    反过来的话,一部名字里带「选集」的正篇就会被当成改编并进来。
    """
    relation = (relation or "").strip()

    # 1. 关系词本身就说清了是另一部作品。
    known = BANGUMI_RELATIONS.get(relation)
    if known is not None:
        nature, confidence = known
        if nature == RELATED_WORK:
            return RELATED_WORK, confidence, f"Bangumi 标记为{relation}"
        if nature == VOLUME_OF:
            return VOLUME_OF, confidence, "Bangumi 标记为单行本(某一系列底下的一册)"
        # 同一作品那一半还要过下面两道。
    elif relation == ORIGINAL_RELATION:
        nature, confidence = SAME_WORK, _LOW
    else:
        return UNKNOWN, "unknown", f"认不出的关系词「{relation}」"

    # 2. 目标是画集 / 选集那一类 —— 不管关系词写的是什么,它都是另一部作品。
    #    实测:81467 的「书籍」里混着 625675(raemz 画集 Amour)与 315185(官方同人集)。
    if looks_like_non_story(target_platform, target_title):
        return RELATED_WORK, _HIGH, f"Bangumi 标记为{relation},但目标是画集/选集一类"

    # 3. 「不同版本」是来源明确给出的身份关系，不需要再靠标题猜。
    if relation == "不同版本":
        return SAME_WORK, _HIGH, _evidence(relation, target_media)

    # 4. 同一作品要两边说得通:漫画指向漫画、动画指向动画这类「同类型」不是改编,是同一条被重复记了;
    #    真正的改编一定跨类型(或同属书的两类之间:轻小说 ↔ 漫画)。
    if seed_media and target_media and seed_media == target_media and relation != "不同版本":
        # 同类型且不是「不同版本」:可能是同一条被重复列出,也可能只是同一类的另一部。
        # **不并**,交给「需要确认」让人看一眼。
        return SAME_WORK, _LOW, f"Bangumi 标记为{relation},但两边是同一个类型"

    # 5. 「原作」的标题判据:同源才收。
    #    实测:漫画的「原作」里同时有 81467(同名,同一部)与 7931《返乡战士》(无关动画)——
    #    只按关系词就会把后者并进来。
    if relation == ORIGINAL_RELATION and not titles_match_exactly(seed_title, target_title):
        return UNKNOWN, "unknown", "标记为原作,但名字对不上(可能是同一作者的另一部)"

    # 6. 「书籍 / 动画 / 游戏 / 三次元」只说明目标的载体类型，不说明它一定是同一部作品。
    #    Bangumi 的跨界联动也会这样连：从《咒术回战》沿游戏走一步，就能碰到《死神》《火影忍者》；
    #    如果把关系词本身当作 high，第二层遍历会把整张联动网自动勾进来。只有标题完全一致时才自动归入，
    #    标题带季名、篇章、舞台剧前缀等情况留在“需要确认”，让用户决定。
    if not titles_match_exactly(seed_title, target_title):
        return SAME_WORK, _LOW, f"Bangumi 标记为{relation},但标题不完全一致"

    return SAME_WORK, _HIGH, _evidence(relation, target_media)


def _evidence(relation: str, target_media: str | None) -> str:
    """一句话说清「为什么它可以并进来」——页面上那一行小字就是它。"""
    if relation == ORIGINAL_RELATION:
        return "Bangumi 标记为原作"
    if relation == "不同版本":
        return "与已选条目互为不同版本"
    if relation == "动画":
        return "Bangumi 标记为动画改编"
    if relation == "书籍":
        return "Bangumi 标记为书籍改编" if target_media in BOOK_LIKE else "Bangumi 标记为书籍"
    return f"Bangumi 标记为{relation}"


def titles_agree(left: str | None, right: str | None) -> bool:
    """两个名字算不算「同一部的名字」。

    **只用来否掉假阳性,不用来把两条并起来** —— 规格要求标题不能成为归组依据,所以这里只回答
    「明显不是同一条吗」。规则:去掉卷号后相等、或者一个是另一个的前缀 / 包含关系。
    """
    left = base_title(left)
    right = base_title(right)
    if not left or not right:
        return False
    if left == right:
        return True
    return left in right or right in left


def titles_match_exactly(left: str | None, right: str | None) -> bool:
    """自动勾选所需的严格标题证据。

    `titles_agree` 的包含关系适合“有没有可能相关”的宽松判断，却不能用于自动合并：作品名是另一部
    作品标题的前缀非常常见。这里仍忽略标点、空格和末尾卷号，但正文必须完整相同。
    """
    left_key = flat(base_title(left))
    right_key = flat(base_title(right))
    return bool(left_key and right_key and left_key == right_key)


#: 一条边只要用了这几个词,目标就**一定是另一部作品**,别的边说什么都不算数。
#: 实测:451466 与 514038 都被两条边指向 —— 一条「番外篇」、一条「书籍」。只看其中一条会得出相反的
#: 结论,而「番外篇」是编辑明确写下的,比粗粒度的「书籍」重。
VETO_RELATIONS = ("番外篇", "相同世界观", "画集", "原声集", "片头曲", "片尾曲", "角色歌", "选集", "合集")


def resolve(edges: list[tuple[str, str, str]]) -> tuple[str, str, str]:
    """同一个目标被好几条边指向时,合起来算一个结论。回 `(三类, 可信度, 一句话)`。

    **这是「同名不同说法」那件事的唯一出口**,所以它必须是纯函数、必须单独考:一个目标往往被多条边
    指向,而它们各说各的。实测:451466《安达与岛村99.9》被两条边指向 —— 81467 说「番外篇」,
    282372 说「书籍」,只看其中一条会得出相反的结论。

    取强不取弱:几条都说同一作品时,「不同版本」本来就是把「书籍」说细了。但只要有一条否决词,
    就一律按否决走 —— 名字像不像都不能推翻它。
    """
    if not edges:
        return UNKNOWN, "unknown", "没有任何一条关系指向它"

    vetoed = [edge for edge in edges if edge[1] in VETO_RELATIONS]
    if vetoed:
        raw = vetoed[0][1]
        return RELATED_WORK, _HIGH, f"Bangumi 标记为{raw}(明确写成另一部作品)"

    # 三类里优先同一作品,其次卷;同一类里取 high。
    order = {SAME_WORK: 0, VOLUME_OF: 1, RELATED_WORK: 2, UNKNOWN: 3}
    weight = {"high": 0, "low": 1, "unknown": 2}
    best = sorted(edges, key=lambda edge: (order.get(edge[0], 3), weight.get(edge[2], 2)))[0]
    if best[0] == UNKNOWN:
        return UNKNOWN, "unknown", "关系词认不出,也没别的边说得更清楚"
    return best[0], best[2], f"Bangumi 标记为{best[1]}"


# ---- 有界遍历:从一个种子走出一族 --------------------------------------------
#
# **为什么要有界**:关系图不是树,是网。实测这一族里 81467 有 22 条边、283417 与 181467 互指,
# 顺着走能一路走到整站;而每一次跳都是一次上游请求。所以:visited 去环、同一作品最多两层、
# 关联作品只展开一层、总量封顶、再给一个总时钟。**宁可少给几条,也不能把设置页卡住。**

#: 同一作品这一层最多再走几跳。两层够用:动画 → 原作轻小说 → 它的漫画版,实测就是两层。
SAME_WORK_HOPS = 2

#: 一次预览最多收多少条(不含卷)。到顶就停,并在 `warnings` 里说明。
MAX_NODES = 40

#: 一次预览的总时钟(秒)。到点就带着已经拿到的结果回去,不把请求拖下去。
#: **实测:真实网络下一次上游请求约一秒,这一族两层走完要十几秒** —— 所以给到 25 秒。
#: 注意它的作用只是兜底:封顶(`MAX_NODES`)才是主要的那道闸。
BUDGET_SECONDS = 25.0


@dataclass(frozen=True)
class FamilyNode:
    """族里的一条:它是谁、凭什么进来的、要不要默认勾上。"""

    candidate: Candidate
    #: SAME_WORK / RELATED_WORK / UNKNOWN —— 与 `classify` 同一套词。
    kind: str
    confidence: str
    #: 给人看的一句话,例如「Bangumi 标记为动画改编」。**页面上那一行小字就是它。**
    evidence: str
    #: **要存进 `work_relation` 的那一类**:related / prequel / sequel / side_story / spin_off /
    #: same_setting / collection / adaptation / unknown。**前端不该去解析 `evidence` 反推它** ——
    #: 那句话是给人看的,随时可能改写。
    relation_type: str = "related"
    #: 要存进 `work_relation` 的**方向**:`from_main` = 主作品指向它,`from_related` = 它指向主作品。
    #: 由关系词与「谁说的这句话」一起定(见 `link_direction`)—— **不能一律写死**。
    direction: str = "from_related"
    #: 由哪一条走过来的(种子为空串)。
    via: str = ""
    #: 从种子数起第几层。
    depth: int = 0
    #: 默认勾选:只有高置信的同一作品才勾。
    selected: bool = False

    @property
    def external_id(self) -> str:
        return self.candidate.external_id

    @property
    def source(self) -> str:
        return self.candidate.source

    @property
    def key(self) -> tuple[str, str]:
        return (self.candidate.source, self.candidate.external_id)


@dataclass
class FamilyPreview:
    """一族现在的样子。**只读的草稿,不落库** —— 用户确认之前一条都不写。"""

    seed: Candidate
    #: 归入同一个统一作品的:含种子自己,按 (类型, 标题) 排好给页面分组用。
    editions: list[FamilyNode] = field(default_factory=list)
    #: 独立成另一部作品的,带方向的关系词。
    related_works: list[FamilyNode] = field(default_factory=list)
    #: 判不下来的:让人自己选「归入 / 关联 / 忽略」。
    uncertain: list[FamilyNode] = field(default_factory=list)
    #: 扫到的卷。**卷不进来当作品** —— 它们属于某个 edition,由分卷那一步处理。
    volumes: list[tuple[str, str]] = field(default_factory=list)
    #: 少了什么、为什么少。**有它就说明结果不完整,但结果仍然可用。**
    warnings: list[str] = field(default_factory=list)
    #: 这一趟走了几步、花了多久,给排查用。
    hops: int = 0
    elapsed: float = 0.0

    @property
    def selected(self) -> list[FamilyNode]:
        return [node for node in self.editions if node.selected]


def _seed_candidate(source: str, external_id: str) -> Candidate | None:
    from app.sources import get

    entry = get(source)
    if entry is None:
        return None
    return entry.fetch(external_id)


def current_title(candidate: Candidate) -> str:
    """拿哪个名字去比。**中文名优先**(库里存的是中文),没有就退回原名。"""
    return candidate.title or candidate.original_title or ""


def discover(
    *,
    source: str,
    external_id: str,
    relations_of,
    fetch,
    same_work_hops: int = SAME_WORK_HOPS,
    max_nodes: int = MAX_NODES,
    budget_seconds: float = BUDGET_SECONDS,
) -> FamilyPreview:
    """从这一条走出一族。回一份**只读**的预览。

    `relations_of(external_id)` 与 `fetch(external_id)` 由调用方注入 —— 一个源的绑定方法直接传进来
    就行(`source.relations_of`),这样这一段能拿夹具考,不必连网(见 `tests/test-family-traversal.py`)。

    **为什么只走一个源**:跨源合并靠的是外部 id 映射(`bangumi_*_id`),不是走关系图 ——
    一个源的关系只在它自己站内有意义。所以这里不跨源跳。

    走法:先取种子的边,按 `resolve` 合成结论(同一作品 / 卷 / 另一部作品 / 判不下来),再**只为
    同一作品那一类**继续往外走,最多 `same_work_hops` 层;关联作品只收一层、不展开。任何一次
    上游抛异常都记进 `warnings` 并继续 —— **一部分拿不到不该让整份预览失败**。

    **为什么同一作品那一类要 `fetch` 一次**:关系表里没有 `platform`,所以「书籍」那一档分不出
    漫画还是轻小说(实测 81467 就是 `media=None`)。补这一下才能把类型填对,而它只落在少数几条上。
    """
    started = time.monotonic()
    seed = _seed_candidate(source, external_id)
    if seed is None:
        raise LookupError(f"取不到这一条:{source}:{external_id}")

    preview = FamilyPreview(seed=seed)
    seen: set[tuple[str, str]] = {(source, external_id)}
    #: 每条候选**收齐所有指向它的边**再下结论 —— 单看一条会得出相反的答案。
    incoming: dict[tuple[str, str], list[SourceRelation]] = {}

    def read_edges(key: tuple[str, str]):
        """只做上游请求，不改共享状态；同一层的几个节点因此可以并行读取。"""
        _from_source, from_id = key
        try:
            return relations_of(from_id), None
        except Exception as error:  # noqa: BLE001 — 一个来源拿不到不该让整份预览失败
            return [], error

    def remember_edges(key: tuple[str, str], edges, error) -> list[tuple[str, str]]:
        """把一份已经读回来的边按目标归拢。回**新出现的**目标。"""
        _from_source, from_id = key
        if error is not None:
            preview.warnings.append(f"{source}:{from_id} 的关系没取到({type(error).__name__})")
            return []
        preview.hops += 1
        fresh: list[tuple[str, str]] = []
        for edge in edges:
            target = (edge.candidate.source, edge.to_external_id)
            incoming.setdefault(target, []).append(edge)
            if target not in seen:
                seen.add(target)
                fresh.append(target)
        return fresh

    def note_edges(key: tuple[str, str]) -> list[tuple[str, str]]:
        edges, error = read_edges(key)
        return remember_edges(key, edges, error)

    def note_edges_many(keys: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """同一层并行读取，最后仍按原顺序归拢，结果稳定但不再逐条等待网络。"""
        if not keys:
            return []
        with ThreadPoolExecutor(max_workers=len(keys)) as pool:
            answers = list(pool.map(read_edges, keys))
        fresh: list[tuple[str, str]] = []
        for key, (edges, error) in zip(keys, answers):
            fresh.extend(remember_edges(key, edges, error))
        return fresh

    def verdict(key: tuple[str, str]) -> tuple[str, str, str]:
        edges = incoming.get(key) or []
        return resolve([(edge.canonical, edge.raw_relation, edge.confidence) for edge in edges])

    def enrich(candidate: Candidate) -> Candidate:
        """补一次 `fetch`,把关系表里没有的 `platform`(因此也就有类型与日期)填上。

        **只在缺类型时才补,而且只在第二趟补** —— 关系表已经给出类型的不再问一遍。
        """
        if candidate.media is not None:
            return candidate
        try:
            full = fetch(candidate.external_id)
        except Exception as error:  # noqa: BLE001
            preview.warnings.append(
                f"{source}:{candidate.external_id} 的详情没取到({type(error).__name__})"
            )
            return candidate
        preview.hops += 1
        return full or candidate

    seed_key = (source, external_id)
    front = note_edges(seed_key) if _within(started, budget_seconds) else []
    preview.editions.append(
        FamilyNode(
            candidate=seed,
            kind=SAME_WORK,
            confidence="high",
            evidence="你选的这一条",
            depth=0,
            selected=True,
        )
    )

    for depth in range(1, same_work_hops + 1):
        if not front:
            break
        following: list[tuple[str, str]] = []
        for key in front:
            if _over_budget(started, budget_seconds):
                preview.warnings.append("时间用完了,只走了一部分 —— 结果仍然可用,可以再来一次")
                following = []
                break
            if len(preview.editions) + len(preview.related_works) + len(preview.uncertain) >= max_nodes:
                preview.warnings.append(
                    f"来源站还列出了更多关系；这里只保留前 {max_nodes} 条供确认，未确认的内容不会加入"
                )
                following = []
                break

            kind, confidence, evidence = verdict(key)
            if kind == VOLUME_OF:
                # 卷在这儿就分流:它不进作品表,挂到它所属的那一件下面去。
                preview.volumes.append((incoming[key][0].from_external_id, key[1]))
                continue
            # **先按关系表里已有的信息收下来,不在这里补详情。** 补一次 `fetch` 就是一次上游请求,
            # 而同一个来源往往一次带回几十条关系(实测 81467 有 22 条)—— 边收边补会让「收」被
            # 「补」挤掉,结果是关系表里明明有的一大半条目根本没被读过(实测:12 秒的钟只读掉 3 条)。
            # 所以分两趟:先把这一层的边全部收完,再只为真正要用的那几条补类型。
            node = FamilyNode(
                candidate=incoming[key][0].candidate,
                kind=kind,
                confidence=confidence,
                evidence=evidence,
                # 要存进 `work_relation` 的那两类,都由**来源的原话**翻出来 —— 前端不解析 `evidence`。
                relation_type=relation_type_of(incoming[key][0].raw_relation),
                direction=link_direction(
                    incoming[key][0].raw_relation,
                    # 这句话是谁说的:第一层是种子自己说的,再往外是中间那一条说的。
                    subject="from_seed" if depth == 1 else "from_related",
                ),
                via=incoming[key][0].from_external_id,
                depth=depth,
                selected=(kind == SAME_WORK and confidence == "high"),
            )
            if kind == SAME_WORK and confidence == "high":
                preview.editions.append(node)
                following.append(key)
            elif kind == RELATED_WORK:
                preview.related_works.append(node)
            else:
                # 判不下来的:同一作品但低置信、或者关系词认不出 —— 都交给人工。
                preview.uncertain.append(node)
        if _over_budget(started, budget_seconds):
            preview.warnings.append("时间用完了,少看了一层 —— 已经拿到的结果仍然可用")
            front = []
        else:
            front = note_edges_many(following)

    # **第二趟:只为要用的那几条补类型。** 关系表里没有 `platform`,所以「书籍」那一档判不出漫画还是
    # 轻小说(实测 81467 就是 `media=None`)。只补同一作品那几条 —— 关联作品不归组,类型不准也不影响
    # 它显示;补它们只是白花请求。预算不够就留着 `None`,由页面显示成「未知类型」让人自己选。
    missing = [
        (index, node)
        for index, node in enumerate(preview.editions)
        if node.candidate.media is None
    ]
    if missing and not _over_budget(started, budget_seconds):
        with ThreadPoolExecutor(max_workers=len(missing)) as pool:
            enriched = list(pool.map(lambda pair: enrich(pair[1].candidate), missing))
        for (index, node), candidate in zip(missing, enriched):
            preview.editions[index] = replace_node(node, candidate)
    elif missing:
        preview.warnings.append("时间用完了,有几种类型没认出来")

    preview.editions.sort(key=lambda n: (n.candidate.media or "", current_title(n.candidate)))
    preview.related_works.sort(key=lambda n: current_title(n.candidate))
    preview.uncertain.sort(key=lambda n: current_title(n.candidate))
    preview.elapsed = round(time.monotonic() - started, 3)
    return preview


def replace_node(node: FamilyNode, candidate: Candidate) -> FamilyNode:
    """换掉一条的条目,其余原样。**只为补类型用**,所以它不改 kind / evidence / selected。"""
    return FamilyNode(
        candidate=candidate,
        kind=node.kind,
        confidence=node.confidence,
        evidence=node.evidence,
        relation_type=node.relation_type,
        direction=node.direction,
        via=node.via,
        depth=node.depth,
        selected=node.selected,
    )


def _over_budget(started: float, budget_seconds: float) -> bool:
    return (time.monotonic() - started) > budget_seconds


def _within(started: float, budget_seconds: float) -> bool:
    return not _over_budget(started, budget_seconds)
