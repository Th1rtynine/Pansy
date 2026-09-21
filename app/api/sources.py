"""外部数据源那一侧的 JSON 接口:问它有什么、记住这条对应它哪一条。
按页面使用顺序:`GET /api/sources`、`POST /api/sources/collect`(**那一个框**:名字或 id 都收,先补全、
再每个源搜一遍)、`POST /api/sources/search` / `resolve` / `identity` / `suggest`、
`GET/PUT/DELETE /api/editions/{id}/source-refs`。这里不写任何源的名字(谁在 `app/sources/__init__.py`
注册过就认谁);外部内容一个字段都不写进正式表,只回建议;一个源答不上来不影响别的(超时就丢掉)。
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import delete, select

from app.api.schemas import (
    CandidateOut,
    ClaimOut,
    CollectIn,
    CollectOut,
    CollectStepOut,
    SourceOut,
    SourceIdentityOut,
    SourcePickIn,
    SourceRefIn,
    SourceRefOut,
    SourceResolveIn,
    SourceSearchIn,
    SourceSuggestIn,
    SuggestionOut,
    VolumeDraftOut,
)
from app.config import load_source_settings
from app.db import session_scope
from app.models import Edition, ExternalRef, Work
from app.sources import HINTS, SOURCES, get
from app.sources.base import Candidate
from app.sources.query import flat, parse, pick_name

router = APIRouter(prefix="/api", tags=["外部数据源"])

# 一次动作最多等多久。**总时限,不是每个源一份** —— 三个源各等十秒就是三十秒,而人只等一次;「补全」那两步共用它。
DEADLINE = 12.0

# 「一个框」那条路上每个源取回多少条候选。**比单独搜一个词宽**:那边的 8 条够人认出是哪一条,这边的目标
# 是一部作品的全部版本都摆出来 —— 漫画、轻小说、动画在那边是好几条,常常排在前面几条之后。
COLLECT_LIMIT = 20


def _source_or_404(name: str):
    """认名字,认不出来直接拒绝,不悄悄跳过。"""
    source = get(name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"没有这个数据源:{name}")
    return source


def _sources_or_404(names: list[str]) -> list[str]:
    """要问哪几个源;没点名就问全部。认不出的名字直接拒绝,不悄悄跳过。"""
    if not names:
        return list(SOURCES)
    unknown = [name for name in names if name not in SOURCES]
    if unknown:
        raise HTTPException(status_code=404, detail=f"没有这个数据源:{'、'.join(unknown)}")
    return names


def _gather(keys: list, work, within: float = DEADLINE) -> list:
    """几个源同时问,过了时限就只收已经答上来的。每个源自己的失败在适配器里已经变成空表(见
    app/sources/http.py),所以这里只处理「还没答完」;`within` 是这次动作还剩多少时间,两步合起来也不许超过 `DEADLINE`。
    """
    if not keys:
        return []
    with ThreadPoolExecutor(max_workers=len(keys)) as pool:
        futures = [pool.submit(work, key) for key in keys]
        answers = []
        for future in futures:
            try:
                answers.extend(future.result(timeout=max(0.0, within)))
            except Exception:
                # 超时、线程里炸了 —— 两种情况都是「这个源这次没答上来」。
                continue
    return answers


def _candidate_out(item: Candidate) -> CandidateOut:
    """候选 → 接口上的形状。`group` 就是归一化后的名字(`app/sources/query.py` 的 `flat`),页面拿它把两个
    源上的同一条归到一起;归一化只有一份,所以页面上分的组与后端认的「同一条」永远是同一个判断。
    """
    return CandidateOut(
        source=item.source,
        external_id=item.external_id,
        title=item.title,
        original_title=item.original_title,
        year=item.year,
        kind=item.kind,
        cover_url=item.cover_url,
        media=item.media,
        series=item.series,
        group=flat(item.title or item.original_title or ""),
        aliases=list(item.aliases),
    )


def _configured(name: str) -> bool:
    """这个源现在有没有凭据。**只有需要凭据的源才可能是 False** —— 读公开内容都不用。"""
    if name == "bangumi":
        return load_source_settings().bangumi_token != ""
    return True


@router.get("/sources", response_model=list[SourceOut])
def list_sources() -> list[SourceOut]:
    """有哪些源,以及它们各自有没有凭据。**没有凭据不是错误状态。**"""
    return [
        SourceOut(
            name=source.name,
            label=source.label,
            hint=HINTS.get(source.name, ""),
            configured=_configured(source.name),
        )
        for source in SOURCES.values()
    ]


@router.get("/sources/claims", response_model=ClaimOut | None)
def who_claimed(source: str, external_id: str) -> ClaimOut | None:
    """这个外部条目已经被哪一条作品认领了;没人认领就回 null。加进来是先问一句:不加也能跑(保存时
    `external_ref` 那条唯一索引会拒绝),但那时人已经填完一整屏。
    """
    with session_scope() as session:
        row = session.execute(
            select(ExternalRef).where(
                ExternalRef.source == source, ExternalRef.external_id == external_id
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        edition = session.get(Edition, row.edition_id)
        if edition is None:
            return None
        work = session.get(Work, edition.work_id)
        return ClaimOut(
            edition_id=edition.id,
            work_id=edition.work_id,
            work_title=work.title if work else "",
            edition_title=edition.title,
        )


@router.get("/sources/volumes", response_model=list[VolumeDraftOut])
def series_volumes(source: str, external_id: str) -> list[VolumeDraftOut]:
    """这一条底下的卷(**只读**,不写库):页面选到一条系列条目时问它。卷不该跟候选一起搜出来,但人选中
    「这一部」之后,底下有几卷、每卷叫什么、什么时候出的,都是他要过目修改的东西,所以单独问、只回一份草稿;
    分不出「系列 / 卷」的源回空表(基类默认行为),卷仍可手工加。
    """
    found = _source_or_404(source)
    return [
        VolumeDraftOut(
            source=draft.source,
            external_id=draft.external_id,
            number=draft.number,
            title=draft.title,
            published_on=draft.published_on,
            summary=draft.summary,
            cover_url=draft.cover_url,
        )
        for draft in found.volumes_of(external_id)
    ]


@router.post("/sources/collect", response_model=CollectOut)
def collect_from_sources(body: CollectIn) -> CollectOut:
    """**那一个框**:名字或条目 ID 都收,把这部作品的每一种版本都找出来。先补全(敲的是 id 就把它取回来、
    拿到名字与别名,敲的是名字就用它搜,之后每个源用哪个词由源自己定),再按每个源**自己分得清的类别**
    (`Source.media_buckets`,这里不认站名)各搜一遍 —— 不是拿别名再搜一次(那样搜回来的是同名的别部作品)。
    """
    text = body.query.strip()
    if not text:
        raise HTTPException(status_code=400, detail="先写一个名字或者条目 ID。")

    started = time.monotonic()
    ask = parse(text)
    resolved: Candidate | None = None

    if ask.by_id:
        source = _source_or_404(ask.source)
        resolved = source.fetch(ask.external_id)
        if resolved is None:
            raise HTTPException(
                status_code=404, detail=f"{source.label} 上取不到这一条:{ask.external_id}"
            )

    # 每个源用哪个词、分几类搜在这里定下来;`steps` 报给页面的是**词**,分几类搜是源自己的事。
    wanted: list[tuple[str, str, str]] = []
    steps: list[CollectStepOut] = []
    for name, item in SOURCES.items():
        if resolved is None:
            keyword = text
            why = "你给的名字"
        elif item.name == resolved.source:
            # 它自己那个站:用它自己的名字(标题),不绕别名。
            keyword = resolved.title or resolved.original_title or ""
            why = "按 ID 取回的名字"
        else:
            # 别的源:按它吃哪种名字挑一个写法。
            keyword = pick_name(resolved.titles(), item.prefers_cjk)
            why = "按 ID 取回的名字"
        if not keyword:
            continue
        steps.append(CollectStepOut(source=name, keyword=keyword, why=why))
        for bucket in sorted(set(item.media_buckets.values())):
            wanted.append((name, keyword, bucket))

    def ask_one(pair: tuple[str, str, str]):
        source = get(pair[0])
        return [] if source is None else source.search(pair[1], COLLECT_LIMIT, pair[2])

    hits = _gather(wanted, ask_one)

    # 人点名的那一条一定在候选里:搜索未必把它带回来(名字对不上、或者排在很多条之后),页面默认勾着它。
    if resolved is not None:
        hits = [resolved, *hits]

    seen: set[tuple[str, str]] = set()
    candidates: list[CandidateOut] = []
    for item in hits:
        key = (item.source, item.external_id)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(_candidate_out(item))

    return CollectOut(
        resolved=_candidate_out(resolved) if resolved is not None else None,
        steps=steps,
        candidates=candidates,
    )


@router.post("/sources/resolve", response_model=CandidateOut)
def resolve_entry(body: SourceResolveIn) -> CandidateOut:
    """按 id 取回这一条:名字、别名、类型推测 —— **「补全」的第一步单独摆出来**。形状与候选一样,页面
    拿它当候选用;取不到就是 404:这里与人打的字直接相关,不能悄悄回一条空的。
    """
    source = _source_or_404(body.source)
    found = source.fetch(body.external_id.strip())
    if found is None:
        raise HTTPException(
            status_code=404, detail=f"{source.label} 上取不到这一条:{body.external_id}"
        )
    return _candidate_out(found)


@router.post("/sources/search", response_model=list[CandidateOut])
def search_sources(body: SourceSearchIn) -> list[CandidateOut]:
    """一个词,几个源同时问。回的是**候选**,不是建议 —— 人先选定是哪一条。"""
    keyword = body.keyword.strip()
    if not keyword:
        return []
    names = _sources_or_404(body.sources)

    def ask(name: str):
        source = get(name)
        return [] if source is None else source.search(keyword)

    return [_candidate_out(item) for item in _gather(names, ask)]


@router.post("/sources/identity", response_model=SourceIdentityOut)
def identify_work(body: SourcePickIn) -> SourceIdentityOut:
    """Find the source entry that should name the shared Work.
    The adapter owns relation semantics: Bangumi may walk from an adaptation to a book/game source;
    a source without trustworthy relations returns the selected entry itself. Draft only, not saved.
    """

    source = _source_or_404(body.source)
    found = source.identity(body.external_id.strip())
    if found is None:
        raise HTTPException(
            status_code=404, detail=f"{source.label} 上取不到这一条:{body.external_id}"
        )
    return SourceIdentityOut(
        work=_candidate_out(found.candidate), relations=list(found.relations)
    )


@router.post("/sources/suggest", response_model=list[SuggestionOut])
def suggest_from_sources(body: SourceSuggestIn) -> list[SuggestionOut]:
    """选中的那几条(可以一个源一条),各回一串逐字段建议。"""
    if not body.picks:
        return []
    unknown = [pick.source for pick in body.picks if pick.source not in SOURCES]
    if unknown:
        raise HTTPException(status_code=404, detail=f"没有这个数据源:{'、'.join(sorted(set(unknown)))}")

    def ask(index: int):
        pick = body.picks[index]
        source = get(pick.source)
        return [] if source is None else source.suggest(pick.external_id)

    # 两个源可能给出同一条(一个人在两处都写着「原画」),同一个源也可能给两遍 —— 按「谁说的 + 哪个字段 + 什么值 + 什么职位」去重,顺序照旧。
    seen: set[tuple] = set()
    out: list[SuggestionOut] = []
    for item in _gather(list(range(len(body.picks))), ask):
        key = (item.source, item.field, item.value, item.role)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            SuggestionOut(
                field=item.field,
                value=item.value,
                source=item.source,
                external_id=item.external_id,
                url=item.url,
                role=item.role,
                excerpt=item.excerpt,
            )
        )
    return out


@router.get("/editions/{edition_id}/source-refs", response_model=list[SourceRefOut])
def list_source_refs(edition_id: int) -> list[SourceRefOut]:
    """这条作品记住的外部条目。"""
    with session_scope() as session:
        _edition_or_404(session, edition_id)
        rows = session.execute(
            select(ExternalRef).where(ExternalRef.edition_id == edition_id).order_by(ExternalRef.source)
        ).scalars()
        return [_ref_out(row) for row in rows]


@router.put("/editions/{edition_id}/source-refs", response_model=SourceRefOut)
def remember_source_ref(edition_id: int, body: SourceRefIn) -> SourceRefOut:
    """记住「这条作品在那个站上是哪一条」。"""
    _source_or_404(body.source)

    with session_scope() as session:
        _edition_or_404(session, edition_id)
        row = remember_ref(session, edition_id, body)
        return _ref_out(row)


def remember_ref(session, edition_id: int, body: SourceRefIn) -> ExternalRef:
    """把一条外部条目记在这件作品上。**同一个站上的同一条只许记一次。** 抽出来给两处用:上面那个 PUT,
    以及「加入作品」一次建两层时顺带记下来。别人已经认领了就拒绝(判重精确到 id,不靠标题相似去猜);
    换一条(同一个站换另一个 id)等于改主意,允许。
    """
    taken = session.execute(
        select(ExternalRef).where(
            ExternalRef.source == body.source, ExternalRef.external_id == body.external_id
        )
    ).scalar_one_or_none()
    if taken is not None and taken.edition_id != edition_id:
        raise HTTPException(
            status_code=400,
            detail=f"{body.source} 的 {body.external_id} 已经记在另一件作品上了。",
        )

    row = session.execute(
        select(ExternalRef).where(
            ExternalRef.edition_id == edition_id, ExternalRef.source == body.source
        )
    ).scalar_one_or_none()
    if row is None:
        row = ExternalRef(edition_id=edition_id, source=body.source, external_id=body.external_id)
        session.add(row)
    row.external_id = body.external_id
    row.title = body.title or row.title
    row.url = body.url or row.url
    row.fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    session.flush()
    return row


@router.delete("/editions/{edition_id}/source-refs/{source}", status_code=204)
def forget_source_ref(edition_id: int, source: str) -> Response:
    """忘掉那个站上的对应关系(不会动作品本身)。"""
    with session_scope() as session:
        _edition_or_404(session, edition_id)
        session.execute(
            delete(ExternalRef).where(
                ExternalRef.edition_id == edition_id, ExternalRef.source == source
            )
        )
    return Response(status_code=204)


def _edition_or_404(session, edition_id: int) -> Edition:
    edition = session.get(Edition, edition_id)
    if edition is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    return edition


def _ref_out(row: ExternalRef) -> SourceRefOut:
    return SourceRefOut(
        source=row.source,
        external_id=row.external_id,
        title=row.title,
        url=row.url,
        fetched_at=row.fetched_at,
    )
