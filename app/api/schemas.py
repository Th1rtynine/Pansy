"""The bodies the JSON API speaks, and how one is built from database rows.
Pydantic models, so each body's shape is stated once, checked on the way in, and shown in `/docs`. **Shape is checked here and refused with 422**;
**meaning** -- a real media type, a real date, a non-blank title -- goes through `app/fields.py` and `app/rules.py`, the same functions the forms use,
and is refused with 400 and the sentence the page would have shown. Response models carry the labels (`media_label`, `fields`) as well as the values, because that wording table lives only in `app/fields.py`.
"""

import json

from pydantic import BaseModel, ConfigDict, Field

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


class OrganizationIn(BaseModel):
    name: str = ""
    role: str = ""


class OfficialLinkIn(BaseModel):
    label: str = ""
    url: str = ""


class EditionIn(BaseModel):
    """一份作品: its own fields, plus its creators and tags in one body.
    作者与标签一次给全,与表单一致 —— 逐条增删是同一件事的第二套规则,会漂(页面上删掉的名字还能从 API 挂上)。
    """

    media_type: str
    title: str = ""
    published_on: str = ""
    ended_on: str = ""
    summary: str = ""
    org: str = ""
    release_status: str = ""
    volume_count: int | None = None
    subtype: str = ""
    region: str = ""
    language: str = ""
    catalog_code: str = ""
    homepage: str = ""
    engine: str = ""
    audience: str = ""
    reading_mode: str = ""
    content_notice: str = ""
    platforms: list[str] = []
    organizations: list[OrganizationIn] = []
    official_links: list[OfficialLinkIn] = []
    #: 本机资源入口。只保存路径文本；当前版本不从网页执行它。
    local_path: str = ""
    creators: list[CreatorLinkIn] = []
    tags: list[str] = []


class VolumeIn(BaseModel):
    volume_number: float | None = None
    title: str = ""
    summary: str = ""
    # 发售日:与作品那一层同一个形状,可空,写多少算多少。
    published_on: str = ""
    catalog_code: str = ""
    page_count: int | None = None
    volume_type: str = ""
    local_path: str = ""


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
    catalog_code: str | None = None
    page_count: int | None = None
    volume_type: str | None = None
    local_path: str | None = None
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
    ended_on: str | None = None
    cover_url: str | None
    cover_width: int | None
    cover_height: int | None
    summary: str | None
    org: str | None
    release_status: str | None
    volume_count: int | None
    local_path: str | None = None
    subtype: str | None = None
    region: str | None = None
    language: str | None = None
    catalog_code: str | None = None
    homepage: str | None = None
    engine: str | None = None
    audience: str | None = None
    reading_mode: str | None = None
    content_notice: str | None = None
    platforms: list[str] = []
    organizations: list[OrganizationIn] = []
    official_links: list[OfficialLinkIn] = []
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


def _json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(item) for item in value if str(item).strip()] if isinstance(value, list) else []


def _json_objects(raw: str | None) -> list[dict[str, str]]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def volume_out(volume: Volume) -> VolumeOut:
    return VolumeOut(
        id=volume.id,
        edition_id=volume.edition_id,
        volume_number=volume.volume_number,
        title=volume.title,
        summary=volume.summary,
        published_on=volume.published_on,
        catalog_code=volume.catalog_code,
        page_count=volume.page_count,
        volume_type=volume.volume_type,
        local_path=volume.path,
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
        ended_on=edition.ended_on,
        summary=edition.summary,
        cover_url=url_of(edition.cover_path),
        cover_width=edition.cover_width,
        cover_height=edition.cover_height,
        org=edition.org,
        release_status=edition.release_status,
        volume_count=edition.volume_count,
        local_path=edition.local_path,
        subtype=edition.subtype,
        region=edition.region,
        language=edition.language,
        catalog_code=edition.catalog_code,
        homepage=edition.homepage,
        engine=edition.engine,
        audience=edition.audience,
        reading_mode=edition.reading_mode,
        content_notice=edition.content_notice,
        platforms=_json_list(edition.platforms),
        organizations=[OrganizationIn(**item) for item in _json_objects(edition.organizations)],
        official_links=[OfficialLinkIn(**item) for item in _json_objects(edition.official_links)],
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
    #: 没有凭据时去哪儿配,一句话(**由源自己或后端那张表给,页面不自己编**);有凭据时是空串。
    configure_hint: str = ""


class CredentialOut(BaseModel):
    """一个有凭据可填的源,现在配成什么样。**secret 只回掩码,永不回完整值。**

    `from` 与 `masked` 分开是有意的:`from` 说这个值是哪来的(网页设置还是 `config.toml`),`masked`
    让人认出「是不是我填的那一个」。两样都不泄漏完整凭据。

    **`configured` 说的是「这个源现在能不能用」,不是「填了几格」。** VNDB 读公开条目根本不要凭据,
    所以它 `configured=True` 而 `masked` 可能是空的 —— 页面据此不说「没有凭据就用不了」那种话。
    """

    source: str
    label: str
    #: 怎么拿到凭据,一句话(页面上照着做就行)。
    hint: str = ""
    #: 可以填哪几格:键名 → 给人的名字。前端据此画输入框,加一个源不用改前端。
    fields: dict[str, str] = {}
    #: 这个源现在能用吗(**不等于「填了凭据」**)。
    configured: bool = False
    #: 还没填完时,这几格是不是**必须**填。false 且没填 = 页面不该报警。
    optional: bool = False
    #: 存下来了但**当前版本不会读它** —— 页面上要如实说,免得人以为填了就生效。
    noop: bool = False
    masked: str = ""
    #: "settings" = 网页上填的,"config" = `config.toml` 里写的,空串 = 都没有。
    from_: str = Field(default="", alias="from")

    model_config = ConfigDict(populate_by_name=True)


class AccountOut(BaseModel):
    """某个源上「这个凭据对应谁」—— 一块给所有源用的展示形状。

    **不带任何令牌**,连掩码都不带:这里要的是「认不认得这个人」,而头像与昵称已经足够认人。
    全是空值就说明还没拿到过资料(没登录、或者还没验证过令牌)。

    `verified` 与「有没有资料」是同一件事的两种说法(前者给人看,后者是原始数据):页面拿它决定
    **收起还是展开那一格输入框** —— 验证过了就没有再让人看一遍输入框的道理。
    """

    #: 这个源的身份**确认过了**(登录成功、或者令牌验证通过)。凭据一改就又变回 false。
    verified: bool = False
    id: int | None = None
    #: 用户名(`name` / Bangumi 的 `username`)。
    name: str = ""
    #: 昵称 —— 显示时优先用它。
    nickname: str = ""
    avatar_url: str = ""
    bio: str = ""
    signature: str = ""
    #: 注册时间。只有 Bangumi 给得出,没有就是空串。
    registered_at: str = ""


class HikarinagiAccountOut(AccountOut):
    """Hikarinagi 那边「现在登录着谁」。

    比通用形状多两样:一个 `logged_in`(决定页面画「登录」还是「退出登录」),以及**该往控制台填什么**
    (回调地址与 scope)。后两样是给人照抄用的 —— 手抄一串带端口和路径的地址太容易错,
    而错了只会在跳转时报一个不容易看懂的 `redirect_uri mismatch`。
    """

    #: 登录着谁。**与 `verified` 是同一件事**:登录成功就两个都为真,退出登录就都为假。
    #: 留着两个名字是因为它们的读者不同 —— `logged_in` 是 Hikarinagi 自己的说法(页面画「登录」还是
    #: 「退出登录」),`verified` 是三个源共用的说法(页面据此决定收不收起输入框)。
    logged_in: bool = False
    #: 本机登录回调地址。**要原样填进 Hikarinagi 控制台**;它由 `config.toml` 的端口决定。
    redirect_uri: str = ""
    #: 这次登录会申请的 scope。控制台里得把对应的格子勾上,否则拿不到。
    login_scope: str = ""
    #: 单点登出地址。退出登录之后页面要把浏览器送过去 —— **只清本地不够**:
    #: Hikarinagi 那边的登录会话还在,下次授权时服务端会跳过同意页、复用旧的那份同意记录。
    logout_url: str = ""


class HikarinagiLoginOut(BaseModel):
    """要跳去登录的地址。`url` 为空就说明现在跳不了,`detail` 里写着为什么。"""

    url: str = ""
    detail: str = ""


class SettingsOut(BaseModel):
    """网页上那些设置现在的样子。**永远不回完整令牌** —— 回的只是「有没有填」加上一个掩码。
    `bangumi_token_masked` 是空串就说明两处都没有填。
    """

    bangumi_token_set: bool
    bangumi_token_masked: str
    #: "settings" = 网页上填的(优先),"config" = `config.toml` 里写的,空串 = 两处都没有。
    bangumi_token_from: str = ""
    #: 有凭据可填的那些源(眼下是 Hikarinagi 与 VNDB)。
    credentials: list[CredentialOut] = []
    #: Hikarinagi 那边登录着谁(用户级令牌换来的)。**没登录时是空的一份**,不是错误状态。
    hikarinagi_account: HikarinagiAccountOut = Field(default_factory=HikarinagiAccountOut)
    #: Bangumi 那个令牌对应谁。**验证过一次之后才有** —— 它不登录,只是拿令牌去问了一句「我是谁」。
    bangumi_account: AccountOut = Field(default_factory=AccountOut)
    #: VNDB 那个令牌对应谁。同样验证过一次才有。
    #: **它跟另两个不一样:VNDB 读公开条目根本不需要令牌**,这一格只管"读你自己账号的收藏"。
    vndb_account: AccountOut = Field(default_factory=AccountOut)
    #: 请求外部源时对外声明的名字,只读 —— 它来自 `config.toml`,页面上改不了。
    user_agent: str = ""
    timeout: float = 10.0
    #: 网页设置存在哪(相对数据目录),给人一个「东西写到哪去了」的交代。
    settings_file: str = ""
    #: 自动预填字段时的来源顺序；排在前面的先填，空缺再向后找。
    source_priority: list[str] = []


class SettingsIn(BaseModel):
    """要写进网页设置里的东西。`bangumi_token` 传空串就是清掉;不传(None)就是不动它。"""

    bangumi_token: str | None = None
    #: 成对凭据:给 `source` 就按它要的那两格写。两个都传空串 = 清掉。
    source: str | None = None
    fields: dict[str, str] | None = None
    source_priority: list[str] | None = None


class TokenCheckOut(BaseModel):
    """拿现在这个令牌去问了一句「我是谁」之后的结果。

    **不通不是错误,是一个结果** —— 所以接口永远回 200,结论在 `ok` 里。
    `detail` 是给人看的一句话:为真时说「对应哪个账号」,为假时说清是令牌不对还是连不上。
    """

    ok: bool
    detail: str


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
    catalog_code: str | None = None
    page_count: int | None = None
    volume_type: str | None = None


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
    # 只在搜索响应里有意义:越高越相关,0 表示上游回了、但本地标题/拼音/容错没有认出来。
    match_score: int = 0
    # 这条是靠错字容许才认出来的;精确编号不走这一层。
    match_approximate: bool = False


class ClaimOut(BaseModel):
    """某个外部条目已经被库里的哪一条认领了(认领本身在 `external_ref` 那张表上,这里只是读出来给人看);给「加进来之前先说一声」用,免得保存时才被 400 挡回来。"""

    edition_id: int
    work_id: int
    work_title: str
    edition_title: str | None = None


class FamilyMemberOut(BaseModel):
    """作品家族里的一条:**它是哪一条、凭什么进来的、要不要默认勾上**。

    `evidence` 是给人看的一句话(「Bangumi 标记为动画改编」)—— 页面上就是那一行小字。**不要把
    `confidence` 画成数字或百分比**:它只是 high / low / unknown 三档,画成数字就是在假装精确。
    """

    candidate: CandidateOut
    #: SAME_WORK / RELATED_WORK / UNKNOWN。
    kind: str
    confidence: str
    evidence: str
    #: 要存进 `work_relation.relation_type` 的那一类(related / side_story / adaptation / …)。
    #: **前端直接用它,不要去解析 `evidence`** —— 那句话是给人看的,随时可能改写。
    relation_type: str = "related"
    #: 要存进 `work_relation` 的方向:`from_main` = 主作品指向它,`from_related` = 它指向主作品。
    #: **由后端按关系词定好**(「动画」与「番外篇」的方向是相反的),前端照抄就行,不要自己写死。
    direction: str = "from_related"
    #: 由哪一条走过来的(种子是空串)。
    via: str = ""
    depth: int = 0
    selected: bool = False
    #: 这一条本地已经有了(靠 `external_ref` 判,不看标题)。**有了就不该再建一件** ——
    #: 规格要求导入前先查外部 id,不许静默生成重复的 Edition。
    already_in_library: bool = False
    #: 已经有的话,它现在是哪一件(没有就是 null)。页面据此把「已在库里」那一组单独画出来。
    claimed_by: ClaimOut | None = None


class FamilyPreviewIn(BaseModel):
    """要看哪一条的家族。**只读**,不会写任何东西。"""

    source: str
    external_id: str


class FamilyPreviewOut(BaseModel):
    """一族现在的样子 —— 一份**草稿**,用户确认之前一条都不落库。

    `volumes` 是扫到但**没有**进来当作品的卷(它们属于某个 edition,由分卷那一步处理):
    `(属于哪一条, 卷的外部 id)`,要详细内容再按 id 单独问。
    """

    seed: CandidateOut
    editions: list[FamilyMemberOut] = []
    related_works: list[FamilyMemberOut] = []
    uncertain: list[FamilyMemberOut] = []
    volumes: list[tuple[str, str]] = []
    #: 少了什么、为什么少。**有它说明结果不完整,但结果仍然可用。**
    warnings: list[str] = []
    hops: int = 0
    elapsed: float = 0.0


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
    approximate: bool = False


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


class SourcePickIn(BaseModel):
    source: str
    external_id: str


class SourceCounterpartsOut(BaseModel):
    """同一个具体版本在其他来源上的明确对应；只接受来源自身提供的外部编号。"""

    items: list[CandidateOut] = []


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


class WorkClaimOut(BaseModel):
    """一个原作锚点已经属于库里的哪部统一作品。"""

    work_id: int
    work_title: str


class EditionImportIn(EditionIn):
    """加入作品时的一件作品:作品自己的字段之外,再带上这一件的外部条目与封面。**继承 `EditionIn`**,
    不另写一遍那十个字段 —— 格子、库里的规矩、报错的那句话因此还是同一份;`refs` 同一个源最多一条,挑不挑都不影响建记录。
    """

    refs: list[SourceRefIn] = []
    # 这一具体版本沿来源关系找到的统一作品。后端用它拦截把两部不同作品塞进同一 Work。
    identity_ref: SourceRefIn | None = None
    # 采用的那张外链封面:后端先落盘再写库,存不下不影响记录本身;**每一件各有一张**(漫画与动画的封面不是一张图)。
    cover_url: str = ""
    # 这一件底下的卷:页面上从源里读回来、人过目改过之后再提交,所以这里就是**最终要写进去的那一份**(每卷可带自己的封面外链)。
    volumes: list[VolumeImportIn] = []


class VolumeImportIn(VolumeIn):
    """加入作品时的一卷:卷自己的字段,再带上它的外部条目与封面外链。**继承 `VolumeIn`**,理由同
    `EditionImportIn`:封面由后端在写库之前取回来,取不到就跳过 —— 一卷的图不该让「加入作品」失败。

    `refs` 是这一卷在来源站上是哪几条(同一卷在两个站上各有一条)。**留着它才能跨来源合并**:
    下次从另一个来源导同一卷时,靠它认回原来那一行,而不是又建一卷。
    """

    cover_url: str = ""
    refs: list[SourceRefIn] = []


class WorkImportLinkIn(BaseModel):
    """一个关联作品与主作品之间的**有方向**关系。

    **方向不能省**:「主作品是它的番外篇」与「它是主作品的番外篇」是两件事。`direction` 说这一条从哪边
    出发 —— `from_related` 表示「关联作品 → 主作品」(例如 99.9 是主作品的番外篇),`from_main` 反过来。
    """

    #: related / prequel / sequel / side_story / spin_off / same_setting / collection / adaptation / unknown。
    relation_type: str = "related"
    #: `from_main` = 主作品指向它;`from_related` = 它指向主作品。默认按「它是主作品的衍生」记。
    direction: str = "from_related"
    source: str = ""
    #: 来源站的原话,原样留着(以后改分类规则时要用)。
    raw_relation: str | None = None
    confidence: str = "unknown"


class RelatedWorkImportIn(BaseModel):
    """一个**要真正建出来**的关联作品(例如《安达与岛村99.9》):它自己那一部,加上它的件。

    **只有「人要导入的」才放这里。** 扫到但这次不导入的关联作品不该在这里 —— 那会建出一堆空的总标题,
    而规格明确不要那个。**件可以为空**:人可能只想要那条关系,不想要它的任何一件。
    """

    work: WorkIn
    editions: list[EditionImportIn] = []
    #: 它与主作品是什么关系。
    link: WorkImportLinkIn = WorkImportLinkIn()
    #: 这一部自己那张封面外链。
    work_cover_url: str = ""


class ImportIn(BaseModel):
    """加入作品:一次建出「作品总标题 + 它的若干件作品」,一个事务里做完,失败就什么都没有
    (见 `app/api/works.py` 的 `create_with_editions`)。**「只加一件」就是这里只有一项**,不另开一扇门。

    `related` 是可选的**图**:同一事务里再建若干部关联作品,并记下它们与主作品之间的有向关系。
    不传就是原来的行为(一条总标题加它的件),所以老的调用方一个字都不用改。
    """

    work: WorkIn
    editions: list[EditionImportIn]
    #: 找到同一原作且它已经在库里时，直接把本次版本加到那一部下面；空值才新建总作品。
    existing_work_id: int | None = None
    #: 本次识别出的原作锚点；新建或归入已有作品后都要记住，供下一种版本认回同一部作品。
    work_ref: SourceRefIn | None = None
    #: **总标题自己的封面:原作那一条的图**(身份那一步 `/api/sources/identity` 认出来的原作条目,也是填总标题那三个字段用的那一条)。
    #: 按发行时间判原作是不对的(改编常比原作先出、再版又比初版晚),所以这里用关系走出来的那一条;这一次请求里顺手取回落盘,留空则不动。
    work_cover_url: str = ""
    #: 这次一并建出来的关联作品,以及它们与主作品的关系。**默认空 = 只建主作品那一部。**
    related: list[RelatedWorkImportIn] = []
