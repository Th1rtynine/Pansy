"""The bodies the JSON API speaks, and how one is built from database rows.
Pydantic models, so each body's shape is stated once, checked on the way in, and shown in `/docs`. **Shape is checked here and refused with 422**;
**meaning** -- a real media type, a real date, a non-blank title -- goes through `app/fields.py` and `app/rules.py`, the same functions the forms use,
and is refused with 400 and the sentence the page would have shown. Response models carry the labels (`media_label`, `fields`) as well as the values, because that wording table lives only in `app/fields.py`.
"""

from pydantic import BaseModel

from app.covers import url_of
from app.fields import media_fields, media_label, parse_aliases
from app.models import Edition, Volume, Work


# ---- what a client sends ---------------------------------------------------


class WorkIn(BaseModel):
    """作品总标题: the three shared fields, and nothing else. 这里没有日期 —— 日期属于 作品,
    这一部的日期是它所有 作品 日期里最早的那个(算出来的,不是写下来的)。
    """

    title: str = ""
    original_title: str = ""
    aliases: list[str] = []


class CreatorLinkIn(BaseModel):
    """One line of the 作者与角色 box: a name and what they did here."""

    name: str
    role: str


class EditionIn(BaseModel):
    """一份作品: its own fields, plus its creators and tags in one body.
    作者与标签一次给全,与表单一致 —— 逐条增删是同一件事的第二套规则,会漂(页面上删掉的名字还能从 API 挂上)。
    """

    media_type: str
    title: str = ""
    published_on: str = ""
    summary: str = ""
    org: str = ""
    release_status: str = ""
    volume_count: int | None = None
    creators: list[CreatorLinkIn] = []
    tags: list[str] = []


class VolumeIn(BaseModel):
    volume_number: float | None = None
    title: str = ""
    summary: str = ""
    # 发售日:与作品那一层同一个形状,可空,写多少算多少。
    published_on: str = ""


class CreatorIn(BaseModel):
    name: str = ""
    aliases: list[str] = []


class TagIn(BaseModel):
    name: str = ""


class RelationIn(BaseModel):
    other_id: int


# ---- what a client gets ----------------------------------------------------


# 封面在响应里报的是地址(`cover_url`)而不是文件路径,浏览器直接取得到;一起报的还有 **原图像素尺寸**
# (`cover_width`/`cover_height`),让页面在图到之前按真实比例占住位置,读不出尺寸时是 None(前端退回 3:4)。
# 作品与卷两种封面同形,区别只在 `cover_url` 指着哪个文件;文件路径那一列(`volume.path`)不报出去。


class EditionRef(BaseModel):
    """一份作品的摘要。列表行、关联行、作者页与标签页上的一行都用它。"""

    id: int
    work_id: int
    work_title: str
    media_type: str
    media_label: str
    title: str | None
    published_on: str | None
    cover_url: str | None
    cover_width: int | None
    cover_height: int | None


class EditionRowOut(EditionRef):
    """A row of a list of 作品: a summary plus what the keyword hit on it."""

    matched_by: list[str] = []


class VolumeOut(BaseModel):
    id: int
    edition_id: int
    volume_number: float | None
    title: str | None
    summary: str | None
    published_on: str | None
    cover_url: str | None
    cover_width: int | None
    cover_height: int | None


class CreatorLinkOut(BaseModel):
    id: int
    name: str
    role: str


class TagRef(BaseModel):
    id: int
    name: str
    media_type: str
    media_label: str


class EditionOut(BaseModel):
    """一份作品的全部内容:字段、作者、标签、卷、关联。`fields` 是逐类型的措辞表(哪几项记、每项叫什么),客户端拿它画表单与展示页,不必自带一份。"""

    id: int
    work_id: int
    work_title: str
    media_type: str
    media_label: str
    fields: dict[str, str]
    title: str | None
    published_on: str | None
    cover_url: str | None
    cover_width: int | None
    cover_height: int | None
    summary: str | None
    org: str | None
    release_status: str | None
    volume_count: int | None
    creators: list[CreatorLinkOut] = []
    tags: list[TagRef] = []
    volumes: list[VolumeOut] = []
    relations: list[EditionRef] = []


class WorkOut(BaseModel):
    """A work as a row: its own three fields, its date, its 作品, and its cover.
    `cover_url` 是**这一部想用的那张图**:总标题自己传过就用它,没传过就沿用**第一件的封面**(与件、卷各自那张并存)。
    """

    id: int
    title: str
    original_title: str | None
    aliases: list[str]
    published_on: str | None
    cover_url: str | None = None
    cover_width: int | None = None
    cover_height: int | None = None
    editions: list[EditionRef] = []
    matched_by: list[str] = []


class LinkedWorkOut(BaseModel):
    """一个被关联的作品总标题,连同它有几份作品连着。"""

    id: int
    title: str
    published_on: str | None
    edition_count: int


class WorkDetailOut(WorkOut):
    editions: list[EditionOut] = []
    linked_works: list[LinkedWorkOut] = []


class WorkListOut(BaseModel):
    total: int
    page: int
    pages: int
    page_size: int
    sort: str
    keyword: str
    approximate: bool
    items: list[WorkOut]


class EditionListOut(BaseModel):
    total: int
    page: int
    pages: int
    page_size: int
    sort: str
    keyword: str
    media_type: str
    approximate: bool
    items: list[EditionRowOut]


class CreatorOut(BaseModel):
    id: int
    name: str
    aliases: list[str]
    edition_count: int = 0
    work_count: int = 0


class CreatorCreditOut(BaseModel):
    """一行「这个人参与过的一份作品」,连带他在这里的角色。"""

    edition: EditionRef
    role: str


class CreatorDetailOut(CreatorOut):
    credits: list[CreatorCreditOut] = []


class TagOut(TagRef):
    edition_count: int = 0


class TagDetailOut(TagOut):
    editions: list[EditionRef] = []


class VolumesAddedOut(BaseModel):
    """批量加卷的结果。加进去几条、跳过几条,以及这个作品现在的全部卷。"""

    added: int
    skipped: int
    volumes: list[VolumeOut]


class MediaTypeOut(BaseModel):
    """一个媒体类型:它的取值、给人看的名字、以及它记哪几项。
    `fields` 就是 `MEDIA_TYPE_FIELDS` 那一行(哪几项记、每项叫什么、空着的是不记);客户端拿它画表单与展示页,于是那一张表只有一份。
    """

    value: str
    label: str
    fields: dict[str, str]


class MediaTypeListOut(BaseModel):
    items: list[MediaTypeOut]


class RelationOut(BaseModel):
    """一条关联。两头以小 id 在前,与库里那一行一致。"""

    edition_a_id: int
    edition_b_id: int


# ---- building a body out of rows -------------------------------------------


def clean_names(values: list[str]) -> list[str]:
    """别名、标签这类一行一个的清单:去掉两端空白,丢掉空行(表单对 textarea 用 fields.split_lines 做同一件事)。"""
    return [value.strip() for value in values if value.strip()]


def edition_ref(edition: Edition, work: Work) -> EditionRef:
    return EditionRef(
        id=edition.id,
        work_id=work.id,
        work_title=work.title,
        media_type=edition.media_type,
        media_label=media_label(edition.media_type),
        title=edition.title,
        published_on=edition.published_on,
        cover_url=url_of(edition.cover_path),
        cover_width=edition.cover_width,
        cover_height=edition.cover_height,
    )


def volume_out(volume: Volume) -> VolumeOut:
    return VolumeOut(
        id=volume.id,
        edition_id=volume.edition_id,
        volume_number=volume.volume_number,
        title=volume.title,
        summary=volume.summary,
        published_on=volume.published_on,
        cover_url=url_of(volume.cover_path),
        cover_width=volume.cover_width,
        cover_height=volume.cover_height,
    )


def work_out(
    work: Work,
    editions: list[Edition],
    published_on: str | None,
    matched_by: list[str] | None = None,
) -> WorkOut:
    # 这一部想用的那张图:**自己传过就用它**,没传过就沿用第一件(按 id 排,与列表次序一致)的封面;两个都空就是 None。
    fallback = next((edition for edition in editions if edition.cover_path), None)
    chosen = work if work.cover_path else fallback
    return WorkOut(
        id=work.id,
        title=work.title,
        original_title=work.original_title,
        aliases=parse_aliases(work.aliases),
        published_on=published_on,
        cover_url=url_of(chosen.cover_path) if chosen is not None else None,
        cover_width=chosen.cover_width if chosen is not None else None,
        cover_height=chosen.cover_height if chosen is not None else None,
        editions=[edition_ref(edition, work) for edition in editions],
        matched_by=matched_by or [],
    )


def edition_out(
    edition: Edition,
    work: Work,
    *,
    creators: list[tuple[int, str, str]] = (),
    tags: list[tuple[int, str]] = (),
    volumes: list[Volume] = (),
    relations: list[tuple[Edition, Work]] = (),
) -> EditionOut:
    """Assemble one 作品 body from the rows the caller already read: this module must not query,
    and every caller has already read what it needs (see the `load_*` functions in `app/queries.py`).
    """
    return EditionOut(
        id=edition.id,
        work_id=work.id,
        work_title=work.title,
        media_type=edition.media_type,
        media_label=media_label(edition.media_type),
        fields=dict(media_fields(edition.media_type)),
        title=edition.title,
        published_on=edition.published_on,
        summary=edition.summary,
        cover_url=url_of(edition.cover_path),
        cover_width=edition.cover_width,
        cover_height=edition.cover_height,
        org=edition.org,
        release_status=edition.release_status,
        volume_count=edition.volume_count,
        creators=[
            CreatorLinkOut(id=creator_id, name=name, role=role)
            for creator_id, name, role in creators
        ],
        tags=[
            TagRef(id=tag_id, name=name, media_type=edition.media_type,
                   media_label=media_label(edition.media_type))
            for tag_id, name in tags
        ],
        volumes=[volume_out(volume) for volume in volumes],
        relations=[edition_ref(other, other_work) for other, other_work in relations],
    )


# ---- 外部数据源 -------------------------------------------------------------


class SourceOut(BaseModel):
    """一个数据源,以及它现在能不能用。`configured` 是「有没有凭据」而不是「能不能用」:两个源读公开内容都不要凭据,false 只说明少给你一类内容(Bangumi 的 NSFW 条目)。"""

    name: str
    label: str
    hint: str
    configured: bool


class VolumeDraftOut(BaseModel):
    """源上一个系列的**一卷**:够我们写一行 `volume`,也够页面在保存前列出来给人改。
    卷不是候选(不进 `CandidateOut`):它没有类型、没有别名;`number` 从名字里认(`(01)`→1),认不出就是空 —— SS、上、下本来就是这一类。
    """

    source: str
    external_id: str
    number: float | None = None
    title: str | None = None
    published_on: str | None = None
    summary: str | None = None
    cover_url: str | None = None


class CandidateOut(BaseModel):
    """搜索结果里的一条。够人认出「是不是它」,不取详情。

    `media` 是**我们这边的类型推测**(manga / light_novel / game / anime),`kind` 是那边自己的类型字样(TV、视觉小说):后者让人认出这一条是什么,前者只用来分组 —— **推测不等于定了类型**。
    `group` 是同一条作品的归一化名字(见 `app/sources/query.py` 的 `flat`),跨源同一部归一组,**分组只是建议**:页面上照它列,但不替人勾。"""

    source: str
    external_id: str
    # 这一条在源上是不是「系列」(一部作品的上一层,卷挂在它底下);页面靠它决定选中之后要不要去问它的卷。
    # **少了这一行不会报错**:pydantic 会把多余的键默默丢掉,于是页面上一直是 undefined、读卷那一段永远不触发。
    series: bool = False
    title: str
    original_title: str | None = None
    year: str | None = None
    kind: str | None = None
    cover_url: str | None = None
    media: str | None = None
    group: str = ""
    # 别名**只有「按 id 取回一条」时才有**(搜索结果里没有)。它够再搜一轮。
    aliases: list[str] = []


class CollectStepOut(BaseModel):
    """这一轮用了哪个词去搜哪个源、**为什么用这个词**:「补全」是两步(先把 id 补成名字、再拿名字去搜),人看得见这两步才能判断「怎么少了一个源」。"""

    source: str
    keyword: str
    why: str


class CollectOut(BaseModel):
    """一个框里敲一下之后拿到的全部东西。`resolved` 只有「敲的是 id」时才有(补全出来的那一条,页面上默认就勾着它)。"""

    resolved: CandidateOut | None = None
    steps: list[CollectStepOut] = []
    candidates: list[CandidateOut] = []


class SourceSearchIn(BaseModel):
    keyword: str
    sources: list[str] = []


class SourceResolveIn(BaseModel):
    """按 id 取回这一条:哪个源、哪个 id。"""

    source: str
    external_id: str


class CollectIn(BaseModel):
    """那一个框里的原文:名字,或者 `bgm:294993` / `vndb:v4`。**认它的是后端。**"""

    query: str


class SuggestionOut(BaseModel):
    """一条逐字段的建议:**字段 + 值 + 出处**,页面一行一行画、人一行一行采用。"""

    field: str
    value: str
    source: str
    external_id: str
    url: str
    role: str | None = None
    excerpt: str | None = None


class SourceRefOut(BaseModel):
    """「这条作品在那个站上是哪一条」。"""

    source: str
    external_id: str
    title: str | None = None
    url: str | None = None
    fetched_at: str | None = None


class ClaimOut(BaseModel):
    """某个外部条目已经被库里的哪一条认领了(认领本身在 `external_ref` 那张表上,这里只是读出来给人看);给「加进来之前先说一声」用,免得保存时才被 400 挡回来。"""

    edition_id: int
    work_id: int
    work_title: str
    edition_title: str | None = None


class SourcePickIn(BaseModel):
    source: str
    external_id: str


class SourceIdentityOut(BaseModel):
    """The external entry whose names should identify the shared Work. `relations` is empty when the
    selected carrier names itself, otherwise the conservative path the source adapter followed (e.g.
    `["书籍"]` from an anime to its manga/novel source) -- shown so an automatic choice stays reviewable.
    """

    work: CandidateOut
    relations: list[str] = []


class SourceSuggestIn(BaseModel):
    picks: list[SourcePickIn]


class SourceRefIn(BaseModel):
    source: str
    external_id: str
    title: str | None = None
    url: str | None = None


class EditionImportIn(EditionIn):
    """加入作品时的一件作品:作品自己的字段之外,再带上这一件的外部条目与封面。**继承 `EditionIn`**,
    不另写一遍那十个字段 —— 格子、库里的规矩、报错的那句话因此还是同一份;`refs` 同一个源最多一条,挑不挑都不影响建记录。
    """

    refs: list[SourceRefIn] = []
    # 采用的那张外链封面:后端先落盘再写库,存不下不影响记录本身;**每一件各有一张**(漫画与动画的封面不是一张图)。
    cover_url: str = ""
    # 这一件底下的卷:页面上从源里读回来、人过目改过之后再提交,所以这里就是**最终要写进去的那一份**(每卷可带自己的封面外链)。
    volumes: list[VolumeImportIn] = []


class VolumeImportIn(VolumeIn):
    """加入作品时的一卷:卷自己的字段,再带上它的封面外链。**继承 `VolumeIn`**,理由同 `EditionImportIn`:
    封面由后端在写库之前取回来,取不到就跳过 —— 一卷的图不该让「加入作品」失败。
    """

    cover_url: str = ""


class ImportIn(BaseModel):
    """加入作品:一次建出「作品总标题 + 它的若干件作品」,一个事务里做完,失败就什么都没有
    (见 `app/api/works.py` 的 `create_with_editions`)。**「只加一件」就是这里只有一项**,不另开一扇门。
    """

    work: WorkIn
    editions: list[EditionImportIn]
    #: **总标题自己的封面:原作那一条的图**(身份那一步 `/api/sources/identity` 认出来的原作条目,也是填总标题那三个字段用的那一条)。
    #: 按发行时间判原作是不对的(改编常比原作先出、再版又比初版晚),所以这里用关系走出来的那一条;这一次请求里顺手取回落盘,留空则不动。
    work_cover_url: str = ""
