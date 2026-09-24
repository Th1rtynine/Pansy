"""外部数据源那一侧的 JSON 接口:问它有什么、记住这条对应它哪一条。
按页面使用顺序:`GET /api/sources`、`POST /api/sources/collect`(**那一个框**:名字或 id 都收,先补全、
再每个源搜一遍)、`POST /api/sources/search` / `resolve` / `identity` / `suggest`、
`GET/PUT/DELETE /api/editions/{id}/source-refs`。这里不写任何源的名字(谁在 `app/sources/__init__.py`
注册过就认谁);外部内容一个字段都不写进正式表,只回建议;一个源答不上来不影响别的(超时就丢掉)。
"""

from __future__ import annotations

import html
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, delete, or_, select

from app.api.schemas import (
    CandidateOut,
    ClaimOut,
    CollectIn,
    CollectOut,
    CollectStepOut,
    FamilyMemberOut,
    FamilyPreviewIn,
    FamilyPreviewOut,
    HikarinagiAccountOut,
    HikarinagiLoginOut,
    SourceOut,
    SourceIdentityOut,
    SourcePickIn,
    SourceRefIn,
    SourceRefOut,
    SourceCounterpartsOut,
    WorkClaimOut,
    SourceResolveIn,
    SourceSearchIn,
    SourceSuggestIn,
    SuggestionOut,
    VolumeDraftOut,
)
from app.config import load_source_settings
from app.db import session_scope
from app.models import Edition, ExternalRef, Work, WorkExternalRef
from app.search import SearchHit, build_entry, rank_match, rank_near_match, retry_keywords
from app.sources import HINTS, SOURCES, configure_hint, configured as source_configured, get
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
    pool = ThreadPoolExecutor(max_workers=len(keys))
    futures = [pool.submit(work, key) for key in keys]
    # `future.result(timeout=within)` 逐个调用会把“总时限”变成 N × within；而 `with` 离开时还会
    # 等所有超时线程结束。一次 wait 才是真正从同一个起点算的总时钟。
    done, pending = wait(futures, timeout=max(0.0, within))
    answers = []
    for future in futures:  # 仍按请求顺序合并，排序不因网络先后而飘。
        if future not in done:
            continue
        try:
            answers.extend(future.result())
        except Exception:
            continue
    for future in pending:
        future.cancel()
    pool.shutdown(wait=False, cancel_futures=True)
    return answers


def _candidate_out(
    item: Candidate, *, match_score: int = 0, match_approximate: bool = False
) -> CandidateOut:
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
        match_score=match_score,
        match_approximate=match_approximate,
    )


def _rank_candidates(
    items: list[Candidate], terms: list[str], resolved: Candidate | None = None
) -> tuple[list[CandidateOut], bool]:
    """用站内搜索同一套规则给外部候选排队,但不丢掉上游结果。

    有标准命中时不混入错字命中;标准命中全空才启用容错。0 分项排在最后,页面默认折叠、仍可展开，
    这样跨语言标题不会被不可逆地删掉。精确编号点名的那一条永远置顶。
    """
    unique: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item.source, item.external_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    entries = [
        build_entry(
            index,
            [
                ("标题", item.title),
                ("原名", item.original_title or ""),
                *(("别名", alias) for alias in item.aliases),
            ],
        )
        for index, item in enumerate(unique)
    ]

    def merged(ranker) -> dict[int, SearchHit]:
        found: dict[int, SearchHit] = {}
        for term in dict.fromkeys(term.strip() for term in terms if term.strip()):
            for hit in ranker(entries, term):
                previous = found.get(hit.row_id)
                if previous is None or hit.score > previous.score:
                    found[hit.row_id] = hit
        return found

    ranked = merged(rank_match)
    exact_count = len(ranked)
    # 精确与容错候选可以共存:「无限的」确实会命中《无限的未知》,但也不能因此藏掉只差一字的
    # 《无限斯特拉托斯》。标准命中的分数天然更高,所以近似项只补进来、不抢走前排。
    for index, hit in merged(rank_near_match).items():
        ranked.setdefault(index, hit)
    approximate = exact_count == 0 and bool(ranked)

    if resolved is not None:
        resolved_key = (resolved.source, resolved.external_id)
        for index, item in enumerate(unique):
            if (item.source, item.external_id) == resolved_key:
                ranked[index] = SearchHit(index, ("精确编号",), 2000, False)
                break

    order = sorted(
        range(len(unique)),
        key=lambda index: (
            0 if index in ranked else 1,
            -ranked[index].score if index in ranked else 0,
            index,
        ),
    )
    return (
        [
            _candidate_out(
                unique[index],
                match_score=ranked[index].score if index in ranked else 0,
                match_approximate=ranked[index].approximate if index in ranked else False,
            )
            for index in order
        ],
        approximate,
    )


def _candidate_entries(items: list[Candidate]):
    return [
        build_entry(
            index,
            [
                ("标题", item.title),
                ("原名", item.original_title or ""),
                *(("别名", alias) for alias in item.aliases),
            ],
        )
        for index, item in enumerate(items)
    ]


def _has_full_candidate_match(items: list[Candidate], terms: list[str]) -> bool:
    """是否已经拿到与输入整字段相同的标题/原名/别名(也认完整拼音)。"""
    entries = _candidate_entries(items)
    for term in dict.fromkeys(term.strip() for term in terms if term.strip()):
        text = build_entry(-1, [("输入", term)])
        folded = {value for _kind, value in text.fields}
        folded.update(value for _kind, value in text.spellings)
        if any(
            value in folded
            for entry in entries
            for _kind, value in (*entry.fields, *entry.spellings)
        ):
            return True
    return False


def _has_approximate_only_candidate(items: list[Candidate], terms: list[str]) -> bool:
    """这一轮是否带回了只能靠容错解释的候选;有就说明放宽查询已经完成任务。"""
    entries = _candidate_entries(items)
    for term in dict.fromkeys(term.strip() for term in terms if term.strip()):
        normal = {hit.row_id for hit in rank_match(entries, term)}
        nearby = {hit.row_id for hit in rank_near_match(entries, term)}
        if nearby - normal:
            return True
    return False


@router.get("/sources", response_model=list[SourceOut])
def list_sources() -> list[SourceOut]:
    """有哪些源、它们各自有没有凭据,以及没凭据时去哪儿配。**没有凭据不是错误状态。**"""
    return [
        SourceOut(
            name=source.name,
            label=source.label,
            hint=HINTS.get(source.name, ""),
            configured=source_configured(source.name),
            # 没凭据时页面要显示「去哪儿配」;有凭据时这一栏空着(页面不显示那一句)。
            configure_hint="" if source_configured(source.name) else configure_hint(source.name),
        )
        for source in SOURCES.values()
    ]


def _safe_hikarinagi_callback(value: str) -> str:
    """只接受当前 Pansy 回调那一种地址。"""
    try:
        parsed = urlsplit(value)
    except ValueError:
        parsed = None
    loopback = parsed and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if (
        parsed is None
        or parsed.scheme not in {"http", "https"}
        or (parsed.scheme == "http" and not loopback)
        or parsed.path != "/api/sources/hikarinagi/callback"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(status_code=400, detail="Hikarinagi 回调地址无效。")
    return value


@router.get("/sources/hikarinagi/login", response_model=HikarinagiLoginOut)
def hikarinagi_login(redirect_uri: str = "", choose_account: bool = False) -> HikarinagiLoginOut:
    """要跳去 Hikarinagi 登录的地址。

    **地址由后端拼好,人不填任何东西** —— `redirect_uri` 是代码里写死的常量,与控制台登记的那一串
    必须一致;不一致时服务端会回 `redirect_uri mismatch`,页面照实把那句话显示出来就行。
    """
    from app.sources.hikarinagi import Hikarinagi

    callback = _safe_hikarinagi_callback(redirect_uri) if redirect_uri else ""
    url, reason = Hikarinagi().login_url(callback, choose_account=choose_account)
    return HikarinagiLoginOut(url=url, detail=reason)


def _callback_page(ok: bool, heading: str, detail: str) -> HTMLResponse:
    """回调结束时给人看的那一页。

    **这个路由不能用 `/api` 那套 JSON 回话** —— 打开它的是浏览器跳转,人正看着这一页。
    所以它自己回一段 HTML:说清成没成,然后自己关掉(它是弹出来的窗口),没关掉就留一个回设置页的链接。
    """
    escape = html.escape
    tone = "#2f7d4f" if ok else "#b4453c"
    return HTMLResponse(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{escape(heading)} · Pansy</title>
<style>
  body {{ font-family: system-ui, "Microsoft YaHei", sans-serif; max-width: 34rem;
         margin: 14vh auto; padding: 0 1.25rem; line-height: 1.8; color: #2b2733; }}
  h1 {{ font-size: 1.15rem; color: {tone}; margin: 0 0 .5rem; }}
  p {{ margin: 0 0 .75rem; }}
  a {{ color: {tone}; }}
  .dim {{ color: #7b7488; font-size: .9rem; }}
</style></head>
<body>
  <h1>{escape(heading)}</h1>
  <p>{escape(detail)}</p>
  <p class="dim" id="hint">这一页马上会自己关上。</p>
  <p><a href="/settings">回设置页</a></p>
  <script>
    // 是弹出来的就自己关掉;不是(比如人直接点链接打开的)就留着,让人自己回去。
    setTimeout(function () {{
      if (window.opener) {{ window.close(); return; }}
      document.getElementById("hint").textContent = "可以关掉这一页了,回 Pansy 的设置页看看。";
    }}, 900);
  </script>
</body></html>"""
    )


@router.get("/sources/hikarinagi/callback", response_class=HTMLResponse)
def hikarinagi_callback(
    code: str = "", state: str = "", error: str = "", error_description: str = ""
) -> HTMLResponse:
    """Hikarinagi 把浏览器跳回来的地方。

    三个必须先看的东西:

    - **`state` 对不上就直接拒绝** —— 这是防 CSRF 的那一道,不验等于白带。
    - **`code` 是一次性的**,而且几分钟就过期。重复回调、或者人在登录页上停留太久,都会失败。
    - 失败时**照样回 HTML 并让人看见原因**:这里是浏览器,不能像 `/api` 那样回一句 JSON。
    """
    from app.sources.hikarinagi import Hikarinagi

    if error:
        detail = error_description.strip() or "你取消了授权。"
        return _callback_page(False, "登录未完成", detail)
    if not code or not state:
        return _callback_page(False, "登录没成", "服务端没把授权码带回来。回设置页重新点一次登录。")
    profile, reason = Hikarinagi().complete_login(code, state)
    if not profile:
        return _callback_page(False, "登录没成", reason)
    who = str(profile.get("nickname") or profile.get("name") or "").strip() or "这个账号"
    return _callback_page(True, "登录成功", f"已登录为「{who}」。回 Pansy 就能看到你的账号了。")


@router.delete("/sources/hikarinagi/login", response_model=HikarinagiAccountOut)
def hikarinagi_logout() -> HikarinagiAccountOut:
    """退出登录:先让服务端把那枚长期凭证作废,再清掉本地那一份。

    回话与设置页那一栏**是同一份形状**(包括"该往控制台填什么"那两格)—— 两条路各拼一遍的话,
    它们迟早会漂开,而页面两边都读。
    """
    from app.api.settings import hikarinagi_account_status
    from app.sources.hikarinagi import Hikarinagi

    Hikarinagi().logout()
    return hikarinagi_account_status()


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
            catalog_code=draft.catalog_code,
            page_count=draft.page_count,
            volume_type=draft.volume_type,
        )
        for draft in found.volumes_of(external_id)
    ]


@router.post("/sources/family-preview", response_model=FamilyPreviewOut)
def family_preview(body: FamilyPreviewIn) -> FamilyPreviewOut:
    """这一条所在的「一族」现在长什么样。**只读,不写库** —— 用户确认之前一条都不落。

    为什么单独一趟而不是塞进 `collect`:`collect` 是「敲一下要快」的那条路,而这里要顺着关系图走几步,
    慢得多、也可能只走完一部分。分开之后,慢的这一段不影响搜索的手感,而它的失败也不会把搜索一起拖垮。

    **拿不到一部分就带着一部分回去**:某一个节点的关系取不到时,结果照给,原因写在 `warnings` 里 ——
    整份预览因为一次超时而失败,比少给两条更糟(见 `app/sources/family.py` 的 `discover`)。

    **顺手把「这一条本地是不是已经有了」一起标出来**:规格要求导入前先查外部 id,不许静默生成重复的
    Edition。这一趟本来就要把候选全列出来,所以正好用**一条**查询把该问的都问掉 —— 让人为每一条各发
    一次 `GET /api/sources/claims` 是把一个本来一次的查询拆成几十次。
    """
    from app.sources.family import discover

    found = _source_or_404(body.source)
    try:
        preview = discover(
            source=found.name,
            external_id=body.external_id,
            relations_of=found.relations_of,
            fetch=found.fetch,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    every = preview.editions + preview.related_works + preview.uncertain
    claimed = _claims_for([(node.source, node.external_id) for node in every])

    def member(node) -> FamilyMemberOut:
        owner = claimed.get((node.source, node.external_id))
        return FamilyMemberOut(
            candidate=_candidate_out(node.candidate),
            kind=node.kind,
            confidence=node.confidence,
            evidence=node.evidence,
            relation_type=node.relation_type,
            direction=node.direction,
            via=node.via,
            depth=node.depth,
            selected=node.selected,
            already_in_library=owner is not None,
            claimed_by=owner,
        )

    return FamilyPreviewOut(
        seed=_candidate_out(preview.seed),
        editions=[member(node) for node in preview.editions],
        related_works=[member(node) for node in preview.related_works],
        uncertain=[member(node) for node in preview.uncertain],
        volumes=list(preview.volumes),
        warnings=list(preview.warnings),
        hops=preview.hops,
        elapsed=preview.elapsed,
    )


def _claims_for(keys: list[tuple[str, str]]) -> dict[tuple[str, str], ClaimOut]:
    """这一批外部条目里,哪几条本地已经有了。**一条查询问完,不按条数发请求。**

    「已经有了」与「没有」都要如实报:页面靠它把「已经在库里的」与「要新建的」分开放 ——
    那条唯一索引最后当然也会拦,但那时人已经填完一整屏了。
    """
    if not keys:
        return {}
    wanted = {(source, external_id) for source, external_id in keys}
    by_source: dict[str, set[str]] = {}
    for source, external_id in wanted:
        by_source.setdefault(source, set()).add(external_id)

    found: dict[tuple[str, str], ClaimOut] = {}
    with session_scope() as session:
        rows = session.execute(
            select(ExternalRef).where(
                or_(
                    *(
                        and_(ExternalRef.source == source, ExternalRef.external_id.in_(ids))
                        for source, ids in by_source.items()
                    )
                )
            )
        ).scalars()
        for row in rows:
            key = (row.source, row.external_id)
            if key not in wanted:
                continue
            edition = session.get(Edition, row.edition_id)
            if edition is None:
                continue
            work = session.get(Work, edition.work_id)
            found[key] = ClaimOut(
                edition_id=edition.id,
                work_id=edition.work_id,
                work_title=work.title if work else "",
                edition_title=edition.title,
            )
    return found


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

    hits = _gather(wanted, ask_one, within=max(0.0, DEADLINE - (time.monotonic() - started)))

    # 来源站自己的网页通常有纠错/分词,公开 API 却可能拿「无限的」直接回空。首轮没有一个候选能
    # 被原词解释时,才逐个用保守短词补召回;一旦找回近似标题立即停止。最终排序始终看原词,
    # 重试词只负责把候选带回来,不会因为查询放宽就把无关条目当成命中。
    if resolved is None and not _has_full_candidate_match(hits, [text]):
        for retry in retry_keywords(text):
            remaining = DEADLINE - (time.monotonic() - started)
            if remaining <= 0:
                break
            retry_wanted = [(name, retry, bucket) for name, _keyword, bucket in wanted]
            recovered = _gather(retry_wanted, ask_one, within=remaining)
            hits.extend(recovered)
            if _has_full_candidate_match(recovered, [text]) or _has_approximate_only_candidate(
                recovered, [text]
            ):
                break

    # 人点名的那一条一定在候选里:搜索未必把它带回来(名字对不上、或者排在很多条之后),页面默认勾着它。
    if resolved is not None:
        hits = [resolved, *hits]

    terms = [text] if resolved is None else [*resolved.titles(), *resolved.aliases]
    candidates, approximate = _rank_candidates(hits, terms, resolved)

    return CollectOut(
        resolved=_candidate_out(resolved, match_score=2000) if resolved is not None else None,
        steps=steps,
        candidates=candidates,
        approximate=approximate,
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

    started = time.monotonic()

    def ask(pair: tuple[str, str, int]):
        source = get(pair[0])
        return [] if source is None else source.search(pair[1], pair[2])

    hits = _gather([(name, keyword, 8) for name in names], ask)
    if not _has_full_candidate_match(hits, [keyword]):
        for retry in retry_keywords(keyword):
            remaining = DEADLINE - (time.monotonic() - started)
            if remaining <= 0:
                break
            # 补搜词更短、同名项更多;仍只取 8 条会把真正的近似标题挤出候选池。
            recovered = _gather(
                [(name, retry, COLLECT_LIMIT) for name in names], ask, within=remaining
            )
            hits.extend(recovered)
            if _has_full_candidate_match(recovered, [keyword]) or _has_approximate_only_candidate(
                recovered, [keyword]
            ):
                break

    candidates, _approximate = _rank_candidates(hits, [keyword])
    return candidates


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


@router.post("/sources/counterparts", response_model=SourceCounterpartsOut)
def source_counterparts(body: SourcePickIn) -> SourceCounterpartsOut:
    """找同一具体版本的跨站记录。标题相同不算证据，必须由来源条目明确给出对方编号。"""
    source = _source_or_404(body.source)
    seed = source.fetch(body.external_id.strip())
    if seed is None:
        return SourceCounterpartsOut()
    found: list[CandidateOut] = []
    for source_name, external_id in seed.external_refs:
        peer_source = get(source_name)
        if peer_source is None:
            continue
        peer = peer_source.fetch(external_id)
        if peer is None or peer.media != seed.media:
            continue
        found.append(_candidate_out(peer))
    return SourceCounterpartsOut(items=found)


@router.get("/sources/work-claims", response_model=WorkClaimOut | None)
def work_claim(source: str, external_id: str) -> WorkClaimOut | None:
    """这个原作锚点是否已经对应某个统一作品。只按来源与编号，不按标题猜。"""
    _source_or_404(source)
    with session_scope() as session:
        row = session.execute(
            select(WorkExternalRef, Work)
            .join(Work, Work.id == WorkExternalRef.work_id)
            .where(
                WorkExternalRef.source == source,
                WorkExternalRef.external_id == external_id,
            )
        ).one_or_none()
        if row is not None:
            ref, work = row
            return WorkClaimOut(work_id=ref.work_id, work_title=work.title)

        # 升级前没有 Work 级锚点；如果这个原作条目本身已经作为具体版本收录，仍能用旧的
        # external_ref 精确认回那一部。这里是只读查询，真正保存新版本时会顺手补上稳定锚点。
        legacy = session.execute(
            select(Edition, Work)
            .join(ExternalRef, ExternalRef.edition_id == Edition.id)
            .join(Work, Work.id == Edition.work_id)
            .where(
                ExternalRef.source == source,
                ExternalRef.external_id == external_id,
            )
        ).one_or_none()
        if legacy is None:
            return None
        edition, work = legacy
        return WorkClaimOut(work_id=edition.work_id, work_title=work.title)


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
