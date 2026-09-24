"""What one outside source provides, and how it answers.
A source implements the `Source` protocol: search by keyword, turn one external id into field
suggestions, say what an external id is called; no merge logic, no storage, no page. It answers with
`Suggestion`s (source, raw value, link) so every row stays checkable; 外部数据只进草稿,人工过目后才写正式表.
`field` 用这里自己的词:title / original_title / alias、edition_title / summary / org、published_on / release_status、creator(带 role)/ tag / cover_url;列表字段一项一条建议,没有对应列的字段不提。
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Candidate:
    """One hit from a search: enough for a person to recognise the entry. No summary, no staff --
    fetching each candidate's full entry would be several requests per keystroke, and the reader only
    needs to answer 「是这一条吗」.
    """

    source: str
    external_id: str
    title: str
    original_title: str | None = None
    year: str | None = None
    kind: str | None = None  # 那边自己的类型字样:TV、漫画、游戏……
    cover_url: str | None = None
    # 我们这边的类型推测(manga / light_novel / game / anime),翻不出来是 None;只用来分组、给表单初值。
    media: str | None = None
    # 这一条在源上是不是「系列」(一部作品的上一层,卷挂在它底下),只有分得出这一层的源才给真值:
    # Bangumi 的搜索响应带 `series`,系列条目 True、单行本与画集 False;读不出来就当普通条目。
    series: bool = False
    # 别名。只有「按 id 取回一条」时才有(搜索不给)。不当搜索词(拿别名会搜到同名的别部作品),只用于人工确认。
    aliases: tuple[str, ...] = ()
    # 这个具体版本在别的来源上的明确编号。只有来源自己给出映射时才有；绝不由标题猜。
    external_refs: tuple[tuple[str, str], ...] = ()

    def titles(self) -> list[str]:
        """这一条的主要写法:标题与原名,不含别名。拿它去别的源搜。"""
        found = [self.title, self.original_title or ""]
        return [name.strip() for name in found if name and name.strip()]


@dataclass(frozen=True)
class WorkIdentity:
    """A source entry chosen as the shared work identity for one carrier. ``candidate`` holds the
    title/original title/aliases for the Work row; ``relations`` records how the source led there (empty
    = the carrier itself). Keeping this source-side hides what Bangumi calls a book relation.
    """

    candidate: Candidate
    relations: tuple[str, ...] = ()


@dataclass(frozen=True)
class VolumeDraft:
    """源上的一条卷,够我们写一行 `volume`。卷不是「一件作品」,所以没有类型、没有别名、也不进候选
    列表;`external_id` 留着按 id 回头补齐(封面、简介)。只有分得出「系列 / 卷」这一层的源才给得出。
    """

    source: str
    external_id: str
    number: float | None = None
    title: str | None = None
    published_on: str | None = None
    summary: str | None = None
    cover_url: str | None = None
    catalog_code: str | None = None
    page_count: int | None = None
    volume_type: str | None = None
    local_path: str | None = None


@dataclass(frozen=True)
class SourceRelation:
    """这一条在来源站上跟哪一条有关系,以及**那是一条什么关系**。

    **来源各说各的,所以这里只收原话,不给它下结论**:`raw_relation` 是对方写的词(「原作」「不同版本」
    「SEQUEL」),`canonical` 是照着 `app/sources/family.py` 那张表翻出来的三类之一。分类要拿**两边的
    类型**一起判断(同一句「书籍」既可以是轻小说改编、也可以是画集),所以 `candidate.media` 与
    `candidate.kind` 都得带着。

    `evidence` 是给人看的一句话(「Bangumi 标记为动画改编」),`confidence` 分 high / low / unknown ——
    **只有 high 才默认勾选**,其余进「需要确认」。
    """

    source: str
    from_external_id: str
    to_external_id: str
    candidate: Candidate
    raw_relation: str
    #: SAME_WORK / VOLUME_OF / RELATED_WORK / UNKNOWN;由 `family.classify` 给。
    canonical: str = "UNKNOWN"
    #: 关系的方向 —— `out` = 从这一条指向对方,`in` = 对方指向这一条。
    #: **番外篇、前传这些必须分得清方向**,合成一个无向对子就再也说不清谁是谁的衍生。
    direction: str = "out"
    confidence: str = "unknown"
    evidence: str = ""


@dataclass(frozen=True)
class Suggestion:
    """One field, as one source would fill it. `excerpt` is the source's own words, shortened -- a
    summary's opening, a date's raw string -- and it is what makes the suggestion checkable without
    opening the link.
    """

    field: str
    value: str
    source: str
    external_id: str
    url: str
    role: str | None = None  # 只给 creator 用:在那一部作品里的职位
    excerpt: str | None = None


class Source(Protocol):
    """一个数据源要会做的三件事:搜索、按 id 取回字段建议、按 id 取回这一条本身。
    `name` 是机器读的短名(bangumi / vndb),`label` 画在页面上。
    """

    name: str
    label: str
    # 这个源吃哪种名字:True = 优先拿带汉字的那个(中文名),False = 优先拿拉丁字/假名的(原名)。
    prefers_cjk: bool
    # 这个源自己分得清的几类,以及我们这边的四个类型各自落在它哪一类里(值是它自己的叫法,不透明,
    # `search(..., bucket=...)` 认这个值)。按类分开搜是因为条数有上限:CLANNAD 在 Bangumi 前 20 条里
    # 12 条是音乐专辑,按书籍搜第 3 条就是漫画版;同一类里的两个类型只问一次(`set(media_buckets.values())`)。
    media_buckets: dict[str, str]

    def search(self, keyword: str, limit: int = 8, bucket: str = "") -> list[Candidate]:
        """按关键词找候选。取不到就回空表、不抛异常;`bucket` 是 `media_buckets` 里的一个值,空 = 不分那一类。
        """
        ...

    def suggest(self, external_id: str) -> list[Suggestion]:
        """按外部 id 取回逐字段的建议。同样:失败回空表。"""
        ...

    def fetch(self, external_id: str) -> Candidate | None:
        """按外部 id 取回这一条本身:名字、别名、类型推测。与 `suggest` 分开(`suggest` 问「这条有什么内容」);失败回 None。
        """
        ...

    def volumes_of(self, external_id: str) -> list[VolumeDraft]:
        """这一条底下的卷(只读);分不出「系列 / 卷」这一层的源回空表。卷不是候选,由我们自己的 `volume` 记,回先给人过目、可以改的草稿。
        """
        return []

    def relations_of(self, external_id: str) -> list[SourceRelation]:
        """这一条在来源站上连到哪几条,各是什么关系(只读)。

        **跟 `volumes_of` 分开,不是同一条路的两种问法**:卷要的是「这一部底下的第几册」,关系要的是
        「这一部跟别的那几部是什么关系」—— 前者进 `volume`,后者决定谁是同一个统一作品。

        **默认回空表,和 `volumes_of` 一个待遇**:VNDB 只有「关联作品」没有跨媒体关系图,Hikarinagi 的
        `/relations` 只挂在 galgame 下面 —— 它们没有这种关系不算缺陷,所以不给它们逼出一个假答案,
        家族归组到时候少一个来源即可(见 `app/sources/family.py` 的开头)。
        """
        return []

    def identity(self, external_id: str) -> WorkIdentity | None:
        """Find the source entry that should name the shared Work. A source without relation data returns its fetched entry; one that knows adaptation relations may walk to the original work. Still a draft.
        """

        ...


def snippet(text: str | None, limit: int = 80) -> str | None:
    """The opening of a long text, as an excerpt for the review page."""
    if not text:
        return None
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "…"
