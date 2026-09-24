"""网页上改得动的设置,以及「这个令牌到底对不对」。

设置本身存在数据目录下的 `settings.json`(见 `app/settings_store.py`),这里只管收、发、验。
**发出去的一律是掩码**:完整令牌与 client_secret 从不回显 —— 它们是要拿去授权的东西,而人只需要
认出「是不是我填的那个」。

两类设置:单值(Bangumi 的令牌)与有具名几格的源凭据(Hikarinagi 的 client_id + client_secret、VNDB 的
token)。后者按 `app/settings_store.py` 的 `CREDENTIALS` 通用地收发,所以再加一个源时,这个文件不用改。
"""

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    AccountOut,
    CredentialOut,
    HikarinagiAccountOut,
    SettingsIn,
    SettingsOut,
    TokenCheckOut,
)
from app.config import PROJECT_ROOT, load_source_settings
from app.sources import SOURCES, configured as source_configured
from app.sources import get
from app.settings_store import (
    CREDENTIALS,
    MAX_CREDENTIAL_LENGTH,
    MAX_TOKEN_LENGTH,
    TOKEN_KEY,
    SOURCE_PRIORITY_KEY,
    forget_settings,
    forget_profile,
    mask,
    save_credentials,
    save_profile,
    save_settings,
    saved_fields,
    saved_profile_of,
    saved_token,
    source_priority,
    settings_file,
)

router = APIRouter(prefix="/api", tags=["设置"])


def _credentials() -> list[CredentialOut]:
    """有凭据可填的源,现在各是什么状态。

    **`configured` 问的是「这个源现在能不能用」,不是「填了几格」。** 这一点不能偷懒:VNDB 读公开条目
    根本不要凭据,它的 token 只是给将来的同步功能留的 —— 要是照「填了才算配好」去报,页面就会对着一个
    明明能用的源说「没有凭据时这个源取不到任何数据」,那是假话。
    """
    found = []
    for source, spec in CREDENTIALS.items():
        names = spec.names()
        identifier = names[0] if names else ""
        stored = saved_fields(source)
        found.append(
            CredentialOut(
                source=source,
                # 名字问源自己,不在这里另抄一份表 —— 抄一份就是留一份会过期的副本
                # (与 `GET /api/sources` 用的是同一个 `label`)。
                label=getattr(get(source), "label", source),
                hint=spec.hint,
                fields={name: label for name, (label, _key) in spec.fields.items()},
                configured=source_configured(source),
                optional=spec.optional,
                noop=spec.noop,
                masked=mask(stored.get(identifier, "")),
                from_="settings" if any(stored.values()) else "",
            )
        )
    return found


def hikarinagi_account_status() -> HikarinagiAccountOut:
    """Hikarinagi 那边登录着谁,以及**该往控制台填什么**。

    账号那半边**只从存下来的会话里读,不联网**:打开设置页就问一次服务端"我是谁"是没必要的往返,
    资料在登录那一刻取过一次就够。会话里没有就说明没登录。**没登录时账号那几格一律是空的** ——
    退出登录会把资料一起忘掉(`logout()` 里的 `forget_profile()`),所以这里不必再挑一次。

    「该填什么」那半边每次都现算 —— 端口是配置项,人改了 `config.toml` 就该立刻看到新地址,
    而不是等重启。

    **这个函数是给别处也用的**(登录与登出那两条路由回的也是同一份状态),所以它不叫 `_current`
    那一套私有名字 —— 那两个路由改完之后,页面拿到的形状必须一致。
    """
    from app.sources.hikarinagi import Hikarinagi, login_scope, logout_url, redirect_uri

    target = {
        "redirect_uri": redirect_uri(),
        "login_scope": login_scope(),
        # 登出地址**每次都给**:页面在退出登录之后要用它把浏览器也带去服务端登出。
        "logout_url": logout_url(),
    }

    if not Hikarinagi().logged_in():
        return HikarinagiAccountOut(**target)
    return HikarinagiAccountOut(logged_in=True, **_account_from("hikarinagi").model_dump(), **target)


def _account_from(source: str) -> AccountOut:
    """把某个源缓存下来的账号资料,挑成接口那一份形状。

    **显式挑字段,不用 `**那一份`**:缓存文件里可能留着旧版本写下的键,而 Pydantic 默认会因为
    多出来的键直接报错 —— 那会让"打开设置页"整个坏掉。三个源共用这一段,所以加源时只改一处。

    `verified` 问的是**缓存里到底有没有过一份资料**:有就是"验证通过了、账号也认下来了",
    页面据此把那一格输入框收起来。所以清掉账号资料(`forget_profile`)与「重新展开输入框」
    在页面上是同一个动作,不需要另立一格状态。
    """
    stored = saved_profile_of(source)
    return AccountOut(
        verified=bool(stored),
        id=stored.get("id"),
        name=str(stored.get("name") or ""),
        nickname=str(stored.get("nickname") or ""),
        avatar_url=str(stored.get("avatar_url") or ""),
        bio=str(stored.get("bio") or ""),
        signature=str(stored.get("signature") or ""),
        registered_at=str(stored.get("registered_at") or ""),
    )


def _bangumi_account() -> AccountOut:
    """Bangumi 那边这个令牌对应谁。**只读缓存,不联网。**

    这一份是「验证」那一枚按钮换来的:`/v0/me` 通了就顺手把资料记下来。
    没验证过(或者验证失败)时是空的一份,页面据此显示「未验证」。
    """
    return _account_from("bangumi")


def _vndb_account() -> AccountOut:
    """VNDB 那边这个令牌对应谁。同样**只读缓存,不联网**。

    走的与 Bangumi 是同一条路:按「验证」时拿令牌去问一句 `/authinfo`。
    **注意它跟另两个源不一样**:VNDB 读公开条目根本不需要令牌,这一格只管"读你自己账号的收藏",
    所以没填、没验证都不影响 VNDB 能不能用。
    """
    return _account_from("vndb")


def _current() -> SettingsOut:
    """现在这些设置合起来是什么样。优先级见 `app/config.py` 的 `load_source_settings`。"""
    settings = load_source_settings()
    try:
        where = str(settings_file().relative_to(PROJECT_ROOT))
    except ValueError:
        where = str(settings_file())

    return SettingsOut(
        bangumi_token_set=settings.bangumi_token != "",
        bangumi_token_masked=mask(settings.bangumi_token),
        bangumi_token_from=settings.token_from,
        credentials=_credentials(),
        hikarinagi_account=hikarinagi_account_status(),
        bangumi_account=_bangumi_account(),
        vndb_account=_vndb_account(),
        user_agent=settings.user_agent,
        timeout=settings.timeout,
        settings_file=where,
        source_priority=source_priority(set(SOURCES)),
    )


def _clean(value: str, label: str) -> str:
    """一格凭据值:去两头空白,挡住过长与夹了空白的(从网页上复制常把换行带进来)。"""
    text = value.strip()
    if len(text) > MAX_CREDENTIAL_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"{label} 太长了(超过 {MAX_CREDENTIAL_LENGTH} 个字符),看着不像是一个值。",
        )
    if any(character.isspace() for character in text):
        raise HTTPException(status_code=400, detail=f"{label} 里不该有空格或换行,检查是不是多贴了一段。")
    return text


@router.get("/settings", response_model=SettingsOut)
def show_settings() -> SettingsOut:
    """现在填的是什么(令牌与 secret 只回掩码)。"""
    return _current()


@router.put("/settings", response_model=SettingsOut)
def write_settings(body: SettingsIn) -> SettingsOut:
    """把令牌或某一对凭据写进 `settings.json`。

    **这里不验证。**「存下来」与「这个值能不能用」是两件事:没网的时候也该让人先把东西填进去。
    Bangumi 的令牌有单独的验证动作(见 `POST /api/settings/bangumi-token/check`)。

    传空串就是清掉 —— 清掉之后如果 `config.toml` 里还写着一个令牌,那个会接着起作用
    (`_current` 会如实报出 `from` 是 `config`),这样「我清干净了怎么还在用」不至于变成一个谜。

    **换了一枚令牌就忘掉上次那份账号资料**(与 `_write_credentials` 同一个理由):那份"你是谁"是
    配着旧令牌问出来的,留着会让页面把上一个账号的卡挂在现在这枚令牌名下 —— 页面上「已连接」
    收起来的输入框也就再也展不开了。
    """
    if body.source is not None:
        return _write_credentials(body)

    if body.source_priority is not None:
        priority = [str(name).strip() for name in body.source_priority]
        if len(priority) != len(set(priority)) or set(priority) != set(SOURCES):
            raise HTTPException(status_code=400, detail="来源顺序必须恰好包含当前全部来源。")
        save_settings({SOURCE_PRIORITY_KEY: priority})
        return _current()

    if body.bangumi_token is None:
        return _current()

    token = body.bangumi_token.strip()
    if len(token) > MAX_TOKEN_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"令牌太长了(超过 {MAX_TOKEN_LENGTH} 个字符),看着不像是一个访问令牌。",
        )
    if any(character.isspace() for character in token):
        # 从网页上复制令牌常会把换行一起带进来;这里已经 strip 过两头,中间再有空白就是贴错了东西。
        raise HTTPException(status_code=400, detail="令牌里不该有空格或换行,检查是不是多贴了一段。")

    if token != saved_token():
        # 只有**真的换了**才忘。清一次空、或者把同一个令牌再存一遍,都不该让人重验一遍。
        forget_profile("bangumi")
    save_settings({TOKEN_KEY: token})
    return _current()


def _write_credentials(body: SettingsIn) -> SettingsOut:
    """写某个源的凭据。

    **每一格都要给**(传空串也算给)。为什么:API 是整体覆写的语义,「没传」与「清掉」分不清 ——
    只传 client_id 而不传 client_secret,到底是「没打算改 secret」还是「想把 secret 清了」?两种都说得通,
    所以要求调用方把意图写全。

    唯一的例外是 `optional` 的源(VNDB):它不填也能用,所以允许只存一格。
    """
    source = str(body.source)
    spec = CREDENTIALS.get(source)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"不认识这个源:{source}")

    fields = body.fields or {}
    names = spec.names()
    if not spec.optional:
        missing = [name for name in names if name not in fields]
        if missing:
            label = "这两格" if len(names) == 2 else "这一格"
            raise HTTPException(
                status_code=400,
                detail=f"{label}要一起填:" + "、".join(names) + "。",
            )

    cleaned = {name: _clean(str(fields.get(name, "")), name) for name in names}
    # **换了一格的源,上次那份账号资料就不作数了** —— 它是配着旧凭据验出来的"你是谁"。
    # 留着会有两个后果:页面上「已连接」的那张卡显示的其实是上一个账号(甚至上一个令牌的主人),
    # 而且按你说的,输入框会一直收着、没法换一个账号。所以只要有一格真的变了就一起忘掉,
    # 让页面退回到「填凭据」那一步,等重新验证。
    before = saved_fields(source)
    if any(before.get(name, "") != value for name, value in cleaned.items()):
        forget_profile(source)
    save_credentials(source, cleaned)
    return _current()


@router.post("/settings/bangumi-token/check", response_model=TokenCheckOut)
def check_bangumi_token() -> TokenCheckOut:
    """拿现在这个令牌去问 Bangumi 一句。**不通不是错误,是一个结果** —— 所以永远回 200。

    通了就顺手把「这个令牌对应谁」记下来(昵称、头像、签名),设置页那块账号区域读的就是它。
    **失败时不清旧的**:一次网络抖动不该把上次看到的账号信息抹掉。
    """
    from app.sources.bangumi import Bangumi

    token = load_source_settings().bangumi_token
    ok, detail, profile = Bangumi.verify_token(token)
    if ok and profile:
        save_profile("bangumi", profile)
    return TokenCheckOut(ok=ok, detail=detail)


@router.post("/settings/vndb-token/check", response_model=TokenCheckOut)
def check_vndb_token() -> TokenCheckOut:
    """拿 VNDB 那枚令牌去问一句「这是谁」。**不通不是错误,是一个结果** —— 永远回 200。

    这一格**可选**:VNDB 读公开条目根本不要令牌,填它只是为了以后读你自己账号的收藏。
    所以这里跟 Bangumi 那条一样只做一件事:通了就把账号资料记下来给设置页显示。
    """
    from app.sources.vndb import Vndb

    token = saved_fields("vndb").get("token", "")
    ok, detail, profile = Vndb.verify_token(token)
    if ok and profile:
        save_profile("vndb", profile)
    return TokenCheckOut(ok=ok, detail=detail)


@router.delete("/settings", response_model=SettingsOut)
def clear_settings() -> SettingsOut:
    """把网页上那一份整个抹掉,回到只认 `config.toml` 的状态。"""
    forget_settings()
    return _current()
