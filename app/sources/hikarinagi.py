"""Hikarinagi: Galgame、轻小说、漫画的条目、简介、制作人员、标签、封面、分卷。

与别的源不同,这个源**必须有凭据**:它走 OIDC 的 `client_credentials`,先拿 client_id/client_secret
换一枚 1 小时有效的访问令牌,再带着它请求。令牌在 `app/settings_store.py` 里存着(网页设置页填),
这里只在内存里缓存换到的令牌与它的到期时间 —— 换令牌是一次额外的网络往返,不该每个请求都做一遍。

三类条目各一个端点,`external_id` 因此**带命名空间**:`galgame:1` / `light_novel:1` / `manga:1`。
不带的话「按 id 取回」就得先猜它是哪一类,猜错就是一次白跑的请求。

两个 scope:`catalog:read` 只读公开条目(不含 NSFW 与乙女向),`catalog:full` 含全部。这里**要最宽的
那个** —— 库里本来就可能有成人向作品,少读到比多读到更难发现。代价是控制台必须勾上 `catalog:full`,
否则换令牌会被 `invalid_scope` 顶回来;服务端说「请求的 scope 不得超出应用已获授权的范围」。

---- 字段命名:两套约定,别混 --------------------------------------------------

这是这个源最容易读错的地方。**条目**与**人 / 厂商 / 角色**用的不是同一套译名键:

==============  ====================  ==============================
              条目译名               跨站 id
==============  ====================  ==============================
galgame        `trans_title`        `bangumi_game_id` / `vndb_id`
light_novel    `name_cn`            `bangumi_book_id`
manga          `name_cn`            `bangumi_subject_id`
人/厂商/角色    `trans_name`         —
==============  ====================  ==============================

(上面这些是读 hikarinagi.org 现网条目的内嵌 JSON 实测出来的,不是照文档占位值猜的:
galgames/25288 的 `trans_title` 就是 `null`、`origin_title` 是 `"COCORO"`、`aliases` 是 `[]`。
只认一套键会把中文名整批丢掉——`trans_name` 那一处就这么错过一次。)

`bangumi_*_id` 与 `vndb_id` 说明**它自己就记着跨站编号**。`identity()` 目前不用它们(见该方法的
说明),但那是将来让跨站身份真正可用的线索。
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import threading
import time
from itertools import zip_longest
from urllib.parse import quote

from app.sources.base import Candidate, SourceRelation, Suggestion, VolumeDraft, WorkIdentity, snippet
from app.sources.http import get_json_with_status, post_form_with_status
from app.settings_store import (
    forget_profile,
    forget_session,
    load_session,
    save_profile,
    save_session,
    saved_credentials,
    saved_profile_of,
    saved_refresh_token,
)

API = "https://api.hikarinagi.org/v3"
TOKEN_URL = "https://id.hikarinagi.org/oidc/token"
AUTH_URL = "https://id.hikarinagi.org/oidc/auth"
REVOKE_URL = "https://id.hikarinagi.org/oidc/token/revocation"
USERINFO_URL = "https://id.hikarinagi.org/oidc/me"
#: 单点登出。**退出登录时必须把浏览器也送过去** —— 只清本地的话,人在 Hikarinagi 那边的
#: 登录会话还在,下次授权时服务端一看"已登录、已同意过",**就不重新问同意页了**:
#: 于是权限改了也不生效、也永远看不到那一页。实测踩过这个坑。
END_SESSION_URL = "https://id.hikarinagi.org/oidc/session/end"
SITE = "https://www.hikarinagi.org"
SCOPE = "catalog:full"

#: 登录时申请哪些 scope 的**默认值**;实际用的是 `config.toml` 里那一项(见 `login_scope()`)。
#: `openid` 不能少(否则不知道登录的是谁),`profile` 给昵称与头像(设置页那块区域就靠它),
#: `offline_access` 是**能否自动续期的分水岭**:不勾它服务端根本不发 refresh token。
DEFAULT_LOGIN_SCOPE = "openid profile offline_access"

#: 回调默认落在哪个本机端口,见 `redirect_uri()`。
DEFAULT_CALLBACK_PORT = 8000


def callback_port() -> int:
    """登录回调用哪个本机端口。`config.toml` 的 `[sources].hikarinagi_callback_port` 可以改。

    **改这里就必须回去改控制台里登记的那条回调地址** —— 两边不一致时服务端会回
    `redirect_uri mismatch`,而那是个不容易看懂的错。
    """
    from app.config import load_source_settings

    try:
        return load_source_settings().hikarinagi_callback_port
    except (OSError, ValueError):
        return DEFAULT_CALLBACK_PORT


def login_scope() -> str:
    """登录时申请哪些 scope。`config.toml` 的 `[sources].hikarinagi_login_scope` 可以改。

    **申请了不等于拿得到**:服务端按控制台勾选的集合裁一遍,裁掉哪个**不报错**。
    实测踩过这一处 —— 请求里带着 `offline_access`,回来的 `scope` 里却没有它。
    """
    from app.config import load_source_settings

    try:
        return load_source_settings().hikarinagi_login_scope
    except (OSError, ValueError):
        return DEFAULT_LOGIN_SCOPE


def logout_url() -> str:
    """退出登录之后要把浏览器送去哪 —— Hikarinagi 的单点登出地址。

    **为什么光清本地不够**:删掉 Pansy 这边的会话,只解决了"Pansy 不记得你";
    而 Hikarinagi **那边**的登录会话还在浏览器里。下次点登录时,服务端一看"这人还登录着、
    而且这个应用同意过了",就**跳过同意页**直接发令牌 —— 于是:

    - 在控制台新勾的 scope 不生效(它复用旧的那份同意)
    - 人也看不到同意页,没法确认到底授权了什么

    实测踩过:勾了 `offline_access` 却一直拿不到,就是因为同意记录停在更早的那一份上。

    **不加 `post_logout_redirect_uri`**:那个参数跟回调地址一样要预先登记,而这个应用的
    授权设置里没有它 —— 带上会被回一句 `post_logout_redirect_uri not registered`。
    人登出后自己回 Pansy 就行。
    """
    return END_SESSION_URL


def redirect_uri() -> str:
    """登录回调地址。**必须与开发者控制台里登记的那一串逐字符相同**,差一个斜杠就是 mismatch。

    选本机固定端口:后端本来就是个常驻的本地服务,端口不会随机变,所以能预先登记。
    端口从配置读,这样把它跑在别的端口上时,登录不会莫名其妙地失败。
    """
    return f"http://127.0.0.1:{callback_port()}/api/sources/hikarinagi/callback"


#: 服务发现文档。**实现选用的那两样在这里能对上**(实测取过):
#: `grant_types_supported` 含 `client_credentials`,`token_endpoint_auth_methods_supported` 含
#: `client_secret_basic`(就是下面用的 Basic 认证),`scopes_supported` 含 `catalog:read`/`catalog:full`。
#: 文档里**没有** `registration_endpoint`,所以建应用只能去控制台点,没法程序化拿凭据。
DISCOVERY_URL = "https://id.hikarinagi.org/oidc/.well-known/openid-configuration"

#: 它只放了 `OpenGalgameCoverDto` 里 `url` 的形状,没说是不是绝对地址;给相对地址时补上站点域名。
_ASSET_HOST = "https://www.hikarinagi.org"

#: 条目三类 —— 它自己的叫法(用于 `types=` 与 `/v3/{path}/{id}`)与库里的媒体类型一个对一个。
TYPE_MEDIA = {
    "galgame": "game",
    "light_novel": "light_novel",
    "manga": "manga",
}
#: 它的端点是复数的、连字符的,而 `types=` 里是单数的 —— 两套写法各自记着,别拼。
TYPE_PATH = {
    "galgame": "galgames",
    "light_novel": "light-novels",
    "manga": "mangas",
}
#: 库里这几种媒体类型各自去它哪一类里搜。同一类里的两个类型只问一次(调用方按 `set()` 去重)。
MEDIA_BUCKETS = {
    "game": "galgame",
    "light_novel": "light_novel",
    "manga": "manga",
}

#: 能分出「系列 / 卷」的两类:它们各有 `/{id}/volumes`。Galgame 没有这一层(它本身就是一部)。
VOLUME_TYPES = ("light_novel", "manga")

#: 职位:`GalgameStaffRole` 枚举 → 库里的词。翻译、编辑、质检、协力不收 —— 库里记的是「谁做了这一部」,
#: 收进来作者表会被淹掉(VNDB 那边同一个决定,见 `app/sources/vndb.py`)。
STAFF_ROLES = {
    "AUTHOR": "作者",
    "ILLUSTRATION": "插图",
    "ORIGINAL_CREATOR": "原作",
    "SCRIPT": "脚本",
    "DIRECTOR": "导演",
    "SCENARIO": "剧本",
    "SERIES_COMPOSITION": "剧本",
    "ANIMATION_SCRIPT": "剧本",
    "ART": "原画",
    "CHARACTER_DESIGN": "原画",
    "SD_ART": "原画",
    "ANIMATION_SUPERVISOR": "作画监督",
    "MUSIC": "音乐",
    "THEME_COMPOSITION": "音乐",
    "THEME_LYRICS": "作词",
    "THEME_PERFORMANCE": "演唱",
    "ORIGINAL_WORK": "原作",
    "PRODUCER": "制作人",
    "EXECUTIVE_PRODUCER": "制作总指挥",
    "ANIMATION_PRODUCTION": "动画制作",
    "SOUND_DIRECTOR": "音响监督",
    "GAME_DESIGNER": "游戏设计",
}

STATUS = {
    "SERIALIZING": "连载中", "FINISHED": "已完结", "PAUSED": "暂停连载",
    "ABANDONED": "中止", "RELEASED": "已发售", "IN_DEVELOPMENT": "开发中",
    "CANCELLED": "开发终止",
}
AUDIENCE = {"SHONEN": "少年", "SHOJO": "少女", "SEINEN": "青年", "JOSEI": "女性"}
READING_MODE = {"PAGED_LTR": "从左往右", "PAGED_RTL": "从右往左", "WEBTOON": "条漫"}
VOLUME_TYPE = {"MAIN": "正篇", "EXTRA": "番外"}
ORG_ROLES = {
    "DEVELOPER": "开发商", "LOCALIZER": "本地化", "PUBLISHER": "发行/出版",
    "LABEL": "书系", "MAGAZINE": "连载杂志", "bunko": "文库", "publisher": "出版社",
}

#: 一次最多给几条标签 —— 这是给人过目的一张表,不是全量导出。
TAG_LIMIT = 20

#: `search()` 每一类各要多少条。**不跟着 `limit` 走**:`limit` 是三类合起来的总预算,每一类都按它
#: 去要就变成了三倍量;这个数只要够三类混合后有得挑就行。
_SEARCH_PAGE_SIZE = 10

#: 换到的令牌还剩这么久就当作过期,提前换掉:留着最后几秒去请求,多半正好撞上它过期。
TOKEN_EARLY_SECONDS = 60.0

#: 换令牌的失败要能被页面读到,所以记下最近一次的原因(而不是只回一个空表)。
#: 键是 client_id,值是 (令牌, 到期时刻) 或 (None, 那句话)。
_token_cache: dict[str, tuple[str | None, float]] = {}
_token_lock = threading.Lock()

#: 用户级令牌的缓存。与上面那张表**分开**:两者换法不同(一个用 Secret,一个用 refresh token)、
#: 续期依据也不同,混在一起两套逻辑会打架。
_user_token: dict[str, tuple[str, float]] = {}

#: 登录中途的状态:`state` 随机串 → (code_verifier, 发起时刻, 回调地址)。
#:
#: 存在内存里,不落盘:它是**一次跳转之内**才有效的东西,进程重启了那一次跳转也就废了。
#: `state` 是防 CSRF 的,顺带当键用 —— 回调只能领走自己那一次发起的那一份。
_pending_logins: dict[str, tuple[str, float, str]] = {}

#: 一次登录发起最多留多久。过了就当作废(人可能把页面开着过夜)。
LOGIN_TTL_SECONDS = 600.0

class Hikarinagi:
    name = "hikarinagi"
    label = "Hikarinagi"
    # 它的三类条目都用中文名(`trans_title` / `name_cn`),所以优先给它带汉字的那个词。
    prefers_cjk = True
    media_buckets = MEDIA_BUCKETS

    # ---- 凭据与令牌 ---------------------------------------------------------

    @staticmethod
    def credentials() -> tuple[str, str]:
        """网页设置里填的那一对(client_id, client_secret)。没填就是两个空串。"""
        return saved_credentials("hikarinagi")

    # ---- 用户级登录(授权码 + PKCE)-----------------------------------------

    @staticmethod
    def _pkce_pair() -> tuple[str, str]:
        """`(verifier, challenge)`。

        **PKCE 在 OAuth 2.1 里对该流程是必填的**,我们这个机密客户端也一样要带 —— 它防的是
        「授权码在回来的路上被截走」:截到了也没用,因为换令牌时还要出示 `verifier` 原文,
        而那串东西从没离开过这台机器。

        challenge 是 verifier 的 SHA-256,base64url 且**去掉尾部 `=`**;服务端只认 `S256`,
        不接受 `plain`(文档:「Hikarinagi ID 仅接受 S256」)。
        """
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return verifier, challenge

    def login_url(self, callback: str = "", *, choose_account: bool = False) -> tuple[str, str]:
        """`(要跳去的地址, 失败原因)`。地址非空就说明可以跳了。

        **回调地址不用人填** —— 它是 `redirect_uri()` 按配置拼出来的,与开发者控制台里登记的那一串
        必须一致;不一致时服务端会回 `redirect_uri mismatch`,那才是要人去改的时候。
        """
        client_id, client_secret = self.credentials()
        if not client_id or not client_secret:
            return "", "还没有填 Hikarinagi 的 client_id 与 client_secret,去上面那两格填一下。"

        verifier, challenge = self._pkce_pair()
        state = secrets.token_urlsafe(24)
        callback = callback or redirect_uri()
        requested_scope = login_scope()

        now = time.time()
        with _token_lock:
            # 清掉过期的发起记录:人点了几次「登录」就攒几条,不清会一直涨。
            for stale in [
                key
                for key, (_v, born, _callback) in _pending_logins.items()
                if now - born > LOGIN_TTL_SECONDS
            ]:
                _pending_logins.pop(stale, None)
            # 回调地址必须与授权请求里的一模一样。把这一趟真正使用的地址跟 state 存在一起，
            # 才能同时支持构建版(通常是 :8000)与 Vite 开发版(通常是 :5173)。
            _pending_logins[state] = (verifier, now, callback)

        query = "&".join(
            f"{key}={quote(str(value), safe='')}"
            for key, value in (
                ("client_id", client_id),
                ("redirect_uri", callback),
                ("response_type", "code"),
                ("scope", requested_scope),
                # OIDC 对 offline_access 要求显式取得同意；切换账号时再要求服务端显示账号选择，
                # 不能只清 Pansy 的本地会话，否则浏览器仍会沿用 Hikarinagi 的登录账号。
                ("prompt", "consent select_account" if choose_account else "consent"),
                ("code_challenge", challenge),
                ("code_challenge_method", "S256"),
                ("state", state),
            )
        )
        return f"{AUTH_URL}?{query}", ""

    def complete_login(self, code: str, state: str) -> tuple[dict, str]:
        """回调用:拿 `code` 换令牌,再读一次账号资料。`(资料, 失败原因)`。

        三步顺序不能换:

        1. **先校验 `state`** —— 对不上就说明这不是我们发起的那一次跳转,直接拒绝。
        2. 拿 `code` + `code_verifier` 换令牌(这一次要带 client_secret,我们是机密客户端)。
        3. 用换到的**用户级**令牌请求 OIDC userinfo endpoint,把昵称与头像取回来。

        第 3 步不是多余的:`profile` 那些声明在 ID 令牌里,但读它要解开并信任一枚 JWT;
        而 `/oidc/me` 是**服务端拿这枚令牌现查的**,它认了才算数。
        """
        with _token_lock:
            pending = _pending_logins.pop(state, None)
        if pending is None:
            return {}, "这次登录的凭据已经失效(可能重复回调,或者放太久过了十分钟)。回设置页重新点一次登录。"
        verifier, born, callback = pending
        if time.time() - born > LOGIN_TTL_SECONDS:
            return {}, "这次登录放了太久,已经作废。回设置页重新点一次登录。"

        client_id, client_secret = self.credentials()
        if not client_id or not client_secret:
            return {}, "凭据不见了 —— 可能刚被清掉。回设置页重新填一次。"

        answer, status = post_form_with_status(
            TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": callback,
                "client_id": client_id,
                "code_verifier": verifier,
            },
            basic=(client_id, client_secret),
        )
        payload = answer if isinstance(answer, dict) else {}
        token = str(payload.get("access_token") or "")
        if not token:
            return {}, _login_failure(payload, status)

        refresh = str(payload.get("refresh_token") or "")
        save_session(_session_from(payload, refresh or saved_refresh_token()))
        with _token_lock:
            _user_token[client_id] = (token, _expiry(payload))

        profile, reason = self._fetch_profile(token)
        if profile:
            save_profile(self.name, _account_shape(profile))
            return profile, ""
        # 令牌已经拿到了，资料接口暂时不可用不应把一次成功授权判成失败。留一个最小资料，
        # 设置页仍会显示已连接；下次真正用到令牌时也能正常续期。
        fallback = {"name": "Hikarinagi 用户"}
        save_profile(self.name, _account_shape(fallback))
        return fallback, f"登录成功,但没读到账号资料:{reason}"

    def logout(self) -> None:
        """退出登录。

        **先撤销,再清本地**:撤销是"告诉服务端这枚 refresh token 从现在起作废",清本地是"我这边也不留"。
        撤销失败(没网、令牌已失效)不算错 —— 本地该清还是要清,不然人点了退出却还留着东西。
        """
        client_id, client_secret = self.credentials()
        session = load_session()
        revokable = str(session.get("refresh_token") or session.get("access_token") or "")
        if revokable and client_id and client_secret:
            post_form_with_status(
                REVOKE_URL,
                {"token": revokable},
                basic=(client_id, client_secret),
            )
        with _token_lock:
            _user_token.pop(client_id, None)
            # 登录中途那些发起记录也一起丢掉:刚点了退出,不该还能拿旧 state 完成一次登录。
            _pending_logins.clear()
        forget_profile(self.name)
        forget_session()

    def account(self) -> dict:
        """现在登录着谁。没登录就是空字典。

        优先用**存下来的资料**:它在登录那一刻取过一次,之后不必每次开设置页都去问服务端。
        """
        if not self.logged_in():
            return {}
        return saved_profile_of(self.name)

    def logged_in(self) -> bool:
        """现在还有没有可用的用户会话。refresh token 可续期；没有它时，一枚尚未过期的
        access token 也代表这次登录已经成功，不能因为不能长期续期就把它说成“没登录”。"""
        session = load_session()
        if str(session.get("refresh_token") or ""):
            return True
        access = str(session.get("access_token") or "")
        try:
            expires_at = float(session.get("expires_at") or 0)
        except (TypeError, ValueError):
            expires_at = 0
        # 兼容修复前留下的会话：旧流程可能在 userinfo 失败时只写入 access token，
        # 页面随后会误显示成“已登录”。新流程成功后一定会留下最小账号资料。
        return bool(access and time.time() < expires_at and saved_profile_of(self.name))

    def _fetch_profile(self, token: str) -> tuple[dict, str]:
        """从 OIDC discovery 声明的 userinfo endpoint 读取账号资料。

        这里不能用目录 API 的 `/v3/user/me`：`profile` scope 对应的是标准 OIDC userinfo，
        后者还会额外要求 `user:read`，会把一次本来成功的登录误报成 403。
        """
        answer, status = get_json_with_status(USERINFO_URL, {"Authorization": f"Bearer {token}"})
        if status == 200 and isinstance(answer, dict):
            return answer, ""
        if status in (401, 403):
            return {}, "服务端不认这枚令牌(可能已过期、已撤销或缺少 profile 权限)。"
        if status is None:
            return {}, "连不上 Hikarinagi。"
        return {}, f"服务端回了 {status}。"

    def _user_access_token(self) -> tuple[str, str]:
        """`(用户级令牌, 失败原因)`。过期就用 refresh token 换一枚。

        **refresh token 每次刷新都会轮换**(文档:「每次刷新均会轮换。请以响应中返回的新值覆盖原有
        refresh token」),所以换完必须把新的存回去;漏了这一步,下一次刷新就会失败,而且只能重新登录。
        """
        client_id, client_secret = self.credentials()
        if not client_id or not client_secret:
            return "", "凭据不见了,没法续期。"

        with _token_lock:
            cached = _user_token.get(client_id)
            if cached is not None:
                token, expires_at = cached
                if token and time.time() < expires_at:
                    return token, ""

        # 进程重启后内存缓存会空，但登录时落盘的 access token 仍可能有效。
        session = load_session()
        stored_token = str(session.get("access_token") or "")
        try:
            stored_expiry = float(session.get("expires_at") or 0)
        except (TypeError, ValueError):
            stored_expiry = 0
        if stored_token and time.time() < stored_expiry:
            with _token_lock:
                _user_token[client_id] = (stored_token, stored_expiry)
            return stored_token, ""

        refresh = str(session.get("refresh_token") or "")
        if not refresh:
            return "", "登录已过期,请重新登录 Hikarinagi。"

        answer, status = post_form_with_status(
            TOKEN_URL,
            {"grant_type": "refresh_token", "refresh_token": refresh},
            basic=(client_id, client_secret),
        )
        payload = answer if isinstance(answer, dict) else {}
        token = str(payload.get("access_token") or "")
        if not token:
            # 刷不动了。**把本地那份清掉并让调用方知道要重新登录** —— 死守着它只会每次都失败,
            # 而失败原因是「授权被撤销」还是「网不通」,在页面上是两件完全不同的事。
            with _token_lock:
                _user_token.pop(client_id, None)
            return "", _refresh_failure(payload, status)

        save_session(_session_from(payload, str(payload.get("refresh_token") or "") or refresh))
        with _token_lock:
            _user_token[client_id] = (token, _expiry(payload))
        return token, ""

    def _access_token(self) -> tuple[str, str]:
        """`(令牌, 一句说明)`。令牌是空串就说明这次没换成,说明里写着为什么。

        换到的令牌按 client_id 缓存在内存里,到期前 60 秒当作过期。凭据被改过时
        client_id 会变,缓存自然 miss —— 不需要额外去失效它。
        """
        client_id, client_secret = self.credentials()
        if not client_id or not client_secret:
            return "", "还没有填 Hikarinagi 的 client_id 与 client_secret,去设置页填一下。"

        with _token_lock:
            cached = _token_cache.get(client_id)
            if cached is not None:
                token, expires_at = cached
                if token and time.time() < expires_at:
                    return token, ""

        answer, status = post_form_with_status(
            TOKEN_URL,
            {"grant_type": "client_credentials", "scope": SCOPE},
            basic=(client_id, client_secret),
        )
        token = str((answer or {}).get("access_token") or "") if isinstance(answer, dict) else ""
        if token:
            with _token_lock:
                _token_cache[client_id] = (token, _expiry(answer))
            return token, ""

        reason = _token_failure(answer, status)
        self._forget_token()
        return "", reason

    def configured(self) -> bool:
        client_id, client_secret = self.credentials()
        return bool(client_id and client_secret)

    # ---- 取数据 -------------------------------------------------------------

    @staticmethod
    def _forget_token() -> None:
        """把当前凭据对应的那枚**应用级**缓存令牌丢掉,让下一次 `_access_token()` 重新去换。

        用在收到 401 的时候:应用级令牌**不签发 refresh token**(文档原话),过期了只能重新换,
        没有别的续期办法。
        """
        client_id, _secret = Hikarinagi.credentials()
        if client_id:
            with _token_lock:
                _token_cache.pop(client_id, None)

    @staticmethod
    def _forget_user_token() -> None:
        """把**用户级**令牌丢掉(缓存与会话里那两样)。

        用在收到 401 的时候。**不清 refresh token**:401 多半只是访问令牌过期或被撞上,
        而那枚长期凭证还能换新的 —— 真到了换不动的地步,`_user_access_token()` 自己会说清楚。
        """
        client_id, _secret = Hikarinagi.credentials()
        if client_id:
            with _token_lock:
                _user_token.pop(client_id, None)
        save_session({"access_token": "", "expires_at": 0.0})

    def _catalog_token(self) -> tuple[str, str, bool]:
        """读条目数据用哪一枚令牌。`(令牌, 失败原因, 是不是用户级)`。

        **登录了就优先用用户级,换不动就退回应用级。**

        为什么值得这样降级:用户级令牌代表的是某个人,比应用级"窄"—— 它可能因为那个人撤销授权而
        整个失效。而读公开目录**本来不需要代表任何人**,所以那一刻应用级是完全够用的。
        没有这一层的话,"登录失效"会连带把"读目录"一起弄坏,而那本来是两件不相干的事。
        """
        if self.logged_in():
            token, _reason = self._user_access_token()
            if token:
                return token, "", True
        token, reason = self._access_token()
        return token, reason, False

    def _get(self, path: str, params: dict[str, str] | None = None) -> object | None:
        """带令牌 GET 一个端点,回 `data` 那一层(统一信封的里层)。失败回 None。

        令牌**中途失效了会自己重来一次**:缓存说它还有效、服务端却说 401(时钟差、或者刚好卡在
        过期的边上),这时把缓存丢掉、换一枚新的、原样再请求一次。只重试一次 —— 第二次还是 401
        就说明不是过期问题(凭据被撤销、scope 不对),再试多少次都一样。

        `post_form_with_status` / `get_json_with_status` 是这里唯一能看见状态码的两个口子;别处
        一律用不带状态码的那两个(它们把「对方没答」与「对方答了错误码」都当成没答)。
        """
        query = ""
        if params:
            pairs = "&".join(f"{key}={_quote(value)}" for key, value in params.items() if value)
            query = f"?{pairs}" if pairs else ""
        url = f"{API}{path}{query}"

        for attempt in range(3):
            token, reason, using_user = self._catalog_token()
            if not token:
                return None
            answer, status = get_json_with_status(url, {"Authorization": f"Bearer {token}"})
            if status == 401 and attempt < 2:
                # 缓存那枚不算数了,丢掉重换一次。**两枚令牌各有一次机会**:用户级那枚可能是授权
                # 被撤销,应用级那枚可能是时钟差 —— 把用户级丢掉并退回应用级,是这里最合理的下一步。
                if using_user:
                    self._forget_user_token()
                else:
                    self._forget_token()
                continue
            if not isinstance(answer, dict) or not answer.get("success"):
                return None
            return answer.get("data")
        return None

    def _items(self, path: str, params: dict[str, str] | None = None) -> list[dict]:
        """子资源端点回的东西,**两种形状都得认**:

        - `/v3/search` 是分页端点,回 `{items, meta}`(`data` 那一层里)。
        - `/{id}/volumes`、`/{id}/staff`、`/{id}/people` 这些**回的是平铺的数组** —— 开发者文档里
          它们的小标题就写着「GET返回数组」,响应示例也是以 `[` 开头(实测把 14 个这类端点逐个查过)。
          它们的示例 URL 上虽然挂着 `?page=1&page_size=10`,但查询参数表里**没有** page/page_size,
          那是文档的样板,传了也不起作用。

        只认前者的话,卷与制作人员会**静默地永远回空** —— 这是实测文档形状时发现的一处真问题。
        """
        data = self._get(path, params)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            items = data.get("items")
            return [item for item in items or [] if isinstance(item, dict)]
        return []

    # ---- Source 协议 --------------------------------------------------------

    def search(self, keyword: str, limit: int = 8, bucket: str = "") -> list[Candidate]:
        """按关键词找三类条目。`bucket` 空 = 三类都找;给了就只找那几类。

        搜索响应只给标题、副标题、开发商与封面 —— 按 Pansy 的规矩(见 `app/sources/base.py`)候选本来
        就只要「够认出是不是它」,完整的资料等选中之后再 `suggest()` 取。

        **三类各搜一次,再三类轮流取,直到凑满 `limit`。** 这件事踩过一次坑:先前是边搜边攒、
        攒够 `limit` 就 `break`,而三类里 galgame 排第一 —— 于是「炎拳」「刀剑神域」这种在另两类里
        才有的关键词一条都搜不出来,页面看着像"这个源只收 galgame"。

        光去掉 `break` 还不够:三类**依次拼**起来再截,结果会全被第一类占满(搜「刀剑神域」八条
        全是轻小说,而它明明在 galgame 里也有)。所以是轮流取一条,让三类在结果里都有位置。
        `limit` 是**结果总数**的预算,不是每一类各自的上限。
        """
        wanted = [bucket] if bucket in TYPE_MEDIA else list(TYPE_MEDIA)
        per_kind: list[list[Candidate]] = []
        for kind in wanted:
            # `types=` 是**真的在筛**(实测:传 galgame 回 10 条全是 galgame)。`page_size` 用固定值而
            # 不是 `limit`:三类先各取这么些,合起来再按 `limit` 截,否则每一类都按总数要一遍。
            items = self._items(
                "/search",
                {"q": keyword, "types": kind, "page": "1", "page_size": str(_SEARCH_PAGE_SIZE)},
            )
            got: list[Candidate] = []
            for item in items:
                # 再筛一遍类型是**保险**:`types=` 只认三类里那几个值,写错了它不报错而是当没传
                # (不传就是三类混合返回)。这一道让「写错类型名」的后果是少几条,而不是混进别类。
                if str(item.get("type") or "").lower() not in (kind, ""):
                    continue
                candidate = _candidate(item, fallback_kind=kind)
                if candidate is not None:
                    got.append(candidate)
            per_kind.append(got)

        found: list[Candidate] = []
        for row in zip_longest(*per_kind):
            for candidate in row:
                if candidate is not None:
                    found.append(candidate)
                    if len(found) >= limit:
                        return found
        return found

    def fetch(self, external_id: str) -> Candidate | None:
        """按 `类型:编号` 取回这一条:名字、别名、类型推测。"""
        kind, number = _split_id(external_id)
        if kind is None:
            return None
        entry = self._get(f"/{TYPE_PATH[kind]}/{number}")
        if not isinstance(entry, dict):
            return None
        return _candidate(entry, fallback_kind=kind, external_id=f"{kind}:{number}")

    def identity(self, external_id: str) -> WorkIdentity | None:
        """身份就用这一条自己。

        **为什么不沿 `/relations` 走:** 那个端点的关系是 `SEQUEL` / `PREQUEL` / `SIDE_STORY` /
        `MAIN_VERSION` / `COLLECTION` 这一类,目标**也是这一站上的另一部 galgame**(响应里那个字段
        就叫 `galgame`)。它连不到 Bangumi 或 VNDB 上的条目,所以走它推不出「这几件共用一个总标题」。
        而 `/relations` 只挂在 galgame 下面,轻小说与漫画连这个端点都没有。

        要真按关系认身份,得先拿到该站的真实数据看那几种关系各自意味着什么 —— 没数据之前不猜。
        """
        found = self.fetch(external_id)
        return WorkIdentity(candidate=found) if found is not None else None

    def relations_of(self, external_id: str) -> list[SourceRelation]:
        """**空表,而且是有理由的空表。**

        这一站的 `/relations` 只挂在 **galgame** 下面(响应的目标字段名就叫 `galgame`),轻小说与漫画
        **根本没有这个端点**;就算有,它连的也是这一站上的另一部 galgame,推不出「这几件共用一个总标题」。
        所以跨媒体归组在这个源上做不了 —— 它能贡献的是 `bangumi_*_id` 那种映射(见 `identity`),
        由调用方按外部 id 合并,**而不是从这里拿关系边**。

        写一个真的请求再回空表更糟:那会为每一条候选多打一次必然没结果的请求。
        """
        return []

    def volumes_of(self, external_id: str) -> list[VolumeDraft]:
        """轻小说与漫画的分卷;Galgame 没有这一层,回空表。

        `/{id}/volumes` 回的是**平铺数组**(见 `_items`),所以这里不用翻页。
        """
        kind, number = _split_id(external_id)
        if kind is None or kind not in VOLUME_TYPES:
            return []
        drafts = []
        for item in self._items(f"/{TYPE_PATH[kind]}/{number}/volumes"):
            drafts.append(
                VolumeDraft(
                    source=self.name,
                    external_id=f"{kind}:{number}:volume:{item.get('id')}",
                    number=_as_float(item.get("volume_number")),
                    # 名字优先中文;都没有就看卷号文本(番外那种没有号的卷只有 `volume_label`)。
                    title=_first(item.get("name_cn"), item.get("name"), item.get("volume_label")),
                    published_on=_date(item.get("publication_date")),
                    cover_url=_cover_url(item),
                    catalog_code=_first(item.get("isbn")),
                    page_count=int(item["page_count"]) if isinstance(item.get("page_count"), int) else None,
                    volume_type=VOLUME_TYPE.get(str(item.get("volume_type") or "")),
                )
            )
        return drafts

    def suggest(self, external_id: str) -> list[Suggestion]:
        """按 `类型:编号` 取回逐字段建议。"""
        kind, number = _split_id(external_id)
        if kind is None:
            return []
        entry = self._get(f"/{TYPE_PATH[kind]}/{number}")
        if not isinstance(entry, dict):
            return []

        url = f"{API}/{TYPE_PATH[kind]}/{number}"
        found: list[Suggestion] = []

        def add(field: str, value: object, excerpt: str | None = None, role: str | None = None) -> None:
            if value is None or not str(value).strip():
                return
            found.append(
                Suggestion(
                    field=field,
                    value=str(value).strip(),
                    source=self.name,
                    external_id=external_id,
                    url=url,
                    role=role,
                    excerpt=excerpt,
                )
            )

        # 中文名与原名:三类条目的字段名不一样(galgame 是 trans_title/origin_title,另两类是
        # name_cn/name),所以两个都试一遍,谁有算谁。
        chinese = _first(entry.get("trans_title"), entry.get("name_cn"))
        original = _first(entry.get("origin_title"), entry.get("name"), entry.get("en_title"))
        add("title", chinese, "Hikarinagi 上的中文标题")
        add("original_title", original)
        add("edition_title", chinese or original)

        add("summary", _first(entry.get("trans_intro"), entry.get("summary_cn")), "Hikarinagi 上的简介译文")
        add("summary", _first(entry.get("origin_intro"), entry.get("summary")), "Hikarinagi 上的原文简介")

        add("published_on", _date(entry.get("release_date") or entry.get("publication_date")))

        # 开发商:galgame 给的是一个名字,另两类要去 producers 里取,这里只收现成的那一个。
        add("org", entry.get("developer"))

        status = STATUS.get(str(entry.get("novel_status") or entry.get("serial_status") or entry.get("dev_status") or ""))
        add("release_status", status)

        add("ended_on", _date(entry.get("publication_end_date")))
        add("subtype", entry.get("adv_type"))
        add("region", entry.get("origin_country"))
        add("language", entry.get("origin_lang"))
        add("catalog_code", entry.get("isbn"))
        add("homepage", entry.get("homepage"))
        add("engine", entry.get("engine"))
        add("audience", AUDIENCE.get(str(entry.get("audience") or "")))
        add("reading_mode", READING_MODE.get(str(entry.get("reading_mode") or "")))
        if entry.get("nsfw") is True:
            add("content_notice", "成人内容")
        for platform in entry.get("platforms") or []:
            add("platform", _display_name(platform) if isinstance(platform, dict) else platform)
        if entry.get("homepage"):
            add("official_link", entry.get("homepage"), "官网", role="官网")
        for link in entry.get("external_links") or []:
            if isinstance(link, dict):
                add("official_link", link.get("url"), str(link.get("name") or link.get("label") or "外部链接"), role=str(link.get("name") or link.get("label") or "外部链接"))

        for alias in entry.get("aliases") or entry.get("other_names") or []:
            add("alias", alias)

        # 分卷数:轻小说与漫画有 `total_volumes`。
        add("volume_count", entry.get("total_volumes"))

        for member in self._staff(kind, number):
            raw_role = str(member.get("role") or member.get("relation") or "")
            role = STAFF_ROLES.get(raw_role) or (raw_role.strip() if raw_role.strip() else None)
            name = _display_name(member.get("person"))
            if role and name:
                add("creator", name, f"Hikarinagi staff.role={member.get('role')}", role=role)

        for organization in self._organizations(kind, number):
            raw_role = str(organization.get("role") or organization.get("relation") or "")
            role = ORG_ROLES.get(raw_role, raw_role)
            name = _display_name(organization.get("producer") or organization.get("organization") or organization)
            if name:
                add("organization", name, role, role=role)
                if not any(item.field == "org" for item in found):
                    add("org", name, role)

        for tag in (entry.get("tags") or [])[:TAG_LIMIT]:
            if isinstance(tag, dict):
                # 标签只有 `{likes, name}`,没有译名 —— `_display_name` 会落回 `name`。
                add("tag", _display_name(tag), "Hikarinagi 标签")

        add("cover_url", _cover_url(entry))

        return found

    def _staff(self, kind: str, number: str) -> list[dict]:
        """制作人员。只有 galgame 有 `/staff`;另两类是 `/people`(同一个形状的另一个名字)。"""
        path = "staff" if kind == "galgame" else "people"
        return self._items(f"/{TYPE_PATH[kind]}/{number}/{path}")

    def _organizations(self, kind: str, number: str) -> list[dict]:
        """Organizations are edition facts; keep their source role rather than flattening all to one name."""
        return self._items(f"/{TYPE_PATH[kind]}/{number}/producers")


# ---- 小工具 ---------------------------------------------------------------


def _token_failure(answer: object, status: int | None) -> str:
    """换令牌为什么没成,写成一句给人看的话。"""
    detail = ""
    if isinstance(answer, dict):
        detail = str(answer.get("error_description") or answer.get("error") or "").strip()
    if status in (400, 401, 403):
        return (
            f"Hikarinagi 不认这一对凭据({status})"
            + (f":{detail}" if detail else "。检查 client_id 与 client_secret,以及应用是否勾了 catalog:full。")
        )
    if status is None:
        return "连不上 Hikarinagi,没法换访问令牌。网络通了再试。"
    return f"Hikarinagi 回了 {status},没法换访问令牌" + (f":{detail}" if detail else "。")


def _expiry(answer: dict) -> float:
    """这次换到的令牌什么时候当作过期。

    **提前 60 秒**:留着最后几秒去请求,多半正好撞上它过期 —— 那时请求已经发出去了,
    只能吃一个 401 再重试,白跑一趟。
    """
    lifetime = answer.get("expires_in")
    seconds = float(lifetime) if isinstance(lifetime, (int, float)) and lifetime > 0 else 3600.0
    return time.time() + seconds - TOKEN_EARLY_SECONDS


def _session_from(answer: dict, fallback_refresh: str) -> dict:
    """把一次令牌响应变成要写进会话的那几项。"""
    return {
        "access_token": str(answer.get("access_token") or ""),
        "refresh_token": str(answer.get("refresh_token") or "") or fallback_refresh,
        "expires_at": _expiry(answer),
    }


def _login_failure(answer: dict, status: int | None) -> str:
    """换授权码为什么没成。

    `invalid_grant` 在这个流程里几乎总是同一个原因:**授权码是一次性的**,而且几分钟就过期。
    所以那句提示要直接指向"重新点一次登录",而不是让人去查凭据。
    """
    detail = str(answer.get("error_description") or answer.get("error") or "").strip()
    error = str(answer.get("error") or "")
    if error == "invalid_grant":
        return "那个授权码已经用过了或者过期了(它是一次性的)。回设置页重新点一次登录。"
    if error == "invalid_client":
        return "服务端不认这对凭据。检查 client_id 与 client_secret,以及应用还是不是机密客户端。"
    if error in ("invalid_scope", "invalid_request"):
        return f"授权请求被拒:{detail or error}。检查控制台里 openid 与 offline_access 勾了没有。"
    if status is None:
        return "连不上 Hikarinagi,没法用授权码换令牌。"
    return f"换令牌失败({status})" + (f":{detail}" if detail else "。")


def _refresh_failure(answer: dict, status: int | None) -> str:
    """用 refresh token 续期为什么没成。

    文档第 213 行专门提醒过:**401 不一定等于过期** —— 人去账号中心撤销了授权,刷新同样会失败。
    那时该做的是请人重新登录,而不是反复重试。
    """
    error = str(answer.get("error") or "")
    detail = str(answer.get("error_description") or error or "").strip()
    if error in ("invalid_grant", "invalid_client") or status in (400, 401, 403):
        return "登录已经失效了(授权被撤销,或者太久没用)。去上面重新登录一次。"
    if status is None:
        return "连不上 Hikarinagi,没法续期。网络通了再试。"
    return f"续期失败({status})" + (f":{detail}" if detail else "。")


def _account_shape(profile: dict) -> dict:
    """OIDC userinfo 的原始资料 → 我们那一份缓存的形状。

    **在这里就把形状定下来,页面拿到的永远是同一套键** —— 不然 `avatar` 是个对象这件事会漏到
    前端去,而换个源(比如 Bangumi)那边 `avatar` 也是对象、但键名不同(`large` / `common`),
    页面就得为每个源各写一遍取值逻辑。
    """
    avatar = profile.get("avatar")
    avatar_url = ""
    if isinstance(avatar, dict):
        avatar_url = str(avatar.get("src") or avatar.get("url") or "")
    elif isinstance(profile.get("picture"), str):
        avatar_url = str(profile.get("picture") or "")
    user_id = profile.get("id") or profile.get("sub")
    try:
        numeric_id = int(user_id) if user_id not in (None, "") else None
    except (TypeError, ValueError):
        numeric_id = None
    return {
        "id": numeric_id,
        "name": str(profile.get("preferred_username") or profile.get("name") or ""),
        "nickname": str(profile.get("nickname") or profile.get("name") or ""),
        "avatar_url": avatar_url,
        "bio": str(profile.get("bio") or ""),
        "signature": str(profile.get("signature") or ""),
    }



def _split_id(external_id: str) -> tuple[str | None, str]:
    """`galgame:1` → `("galgame", "1")`。认不出类型就回 None —— 不猜。"""
    head, _, tail = (external_id or "").strip().partition(":")
    kind = head.lower()
    if kind in TYPE_MEDIA and tail.strip():
        return kind, tail.strip()
    return None, ""


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(str(value), safe="")


def _first(*values: object) -> str | None:
    """第一个非空的(去空白之后)。"""
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _display_name(entity: object) -> str | None:
    """一个**人 / 厂商 / 角色**的名字,优先中文。

    **这一层有它自己的约定:译名叫 `trans_name`,不叫 `name_cn`。** 文档里的 `OpenEntityRefDto`
    (staff 的 `person`、`producers` 的 `producer`、`characters` 的 `character`)响应示例都是
    `{"name": …, "trans_name": …}`;`name_cn` 是**条目**那一层才用的(轻小说与漫画的 `name_cn`)。
    只读 `name_cn` 会把每一个人的中文名都丢掉,一律退回原名。

    `name_cn` 仍然排在前面:多认一个不会错,少的那个才会。
    """
    if not isinstance(entity, dict):
        return None
    return _first(entity.get("name_cn"), entity.get("trans_name"), entity.get("name"))


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _date(value: object) -> str | None:
    """日期:它给的是 ISO 串,库里的 `published_on` 只写到知道的那一位,所以截到日。"""
    text = _first(value)
    if not text:
        return None
    head = text.split("T")[0].strip()
    return head or None


def _subtitle_year(value: object) -> str | None:
    """搜索命 `subtitle` 里的年份。

    **这个字段装的是「状态 · 年份」,不是类型**:实测 galgame 一律只有年份(`"2026"`、`"1993"`),
    轻小说与漫画是 `"已完结 · 2011"` / `"连载中 · 2025"`,也有只给状态的(`"已完结"` -> 没有年份)。

    所以取「那一段 4 位数字」而不是拿整串:整串塞进 `kind` 会让每条的类型都变成年份。找不到就
    留空 —— `subtitle` 还会装别的字样,猜错不如不猜。
    """
    text = _first(value)
    if not text:
        return None
    found = re.search(r"(?<!\d)(\d{4})(?!\d)", text)
    return found.group(1) if found else None


def _image(asset: object) -> str | None:
    """封面地址。文档里 `url` 写成 `path/to/asset.jpg`,是相对地址时补上站点域名。"""
    if not isinstance(asset, dict):
        return None
    url = _first(asset.get("url"))
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"{_ASSET_HOST}/{url.lstrip('/')}"


def _cover_url(entry: dict) -> str | None:
    """封面:**条目与分卷都是 `covers[]`**(按得票数由高到低排好,所以取第一张)。

    文档字段表里这两种东西用的都是 `OpenCoverDto[]` —— 分卷**不是**单个 `cover`,照 `cover` 去读
    会永远是 None。`cover` 那一路留着,是因为搜索命里出现过单个 `cover` 的形状。
    """
    covers = entry.get("covers")
    if isinstance(covers, list):
        for cover in covers:
            found = _image(cover)
            if found:
                return found
    return _image(entry.get("cover"))


def _candidate(item: dict, fallback_kind: str, external_id: str = "") -> Candidate | None:
    """搜索命与完整条目共用一个构造:字段名两边不一样,所以每一处都退一步试。

    **搜索命只有** `{cover, developer, id, subtitle, title, type}`(已对着真响应逐字段核过),
    所以:

    - 封面是**单个 `cover`**,而完整条目是 `covers[]` —— `_cover_url` 两种都认。
    - `developer` 在这一层是**一个名字字符串**(不是 `producers[]` 那种对象)。
    - **没有日期字段**,年份只能从 `subtitle` 里抠(见 `_subtitle_year`)。
    - 只有 `title` 一个名字,而**它已经是汉化过的那个**:搜索「约会大作战」时 `galgame:2077`
      回的 `title` 就是「约会大作战　凛祢乌托邦」,该条目的 `trans_title` 也是这串、`origin_title`
      是日文原名 —— 所以搜索这一层不必再分中英日,`title` 直接用。
    - `subtitle` **不是**类型字样:galgame 是 `"2026"`,另两类是 `"已完结 · 2011"` /
      `"连载中 · 2025"`。把整串塞进 `kind` 会让每一条的类型显示成年份(实测踩过这一处)。

    年份因此有两个来源:完整条目有 `release_date` / `publication_date`,搜索命只有 `subtitle`,
    后者抠不出来就留空 —— 不乱猜。
    """
    kind = str(item.get("type") or fallback_kind).lower()
    if kind not in TYPE_MEDIA:
        return None
    number = item.get("id")
    if number is None:
        return None

    chinese = _first(item.get("trans_title"), item.get("name_cn"))
    original = _first(item.get("origin_title"), item.get("name"), item.get("en_title"))
    # 搜索只给一个 `title`;完整条目给上面那些更细的。
    display = chinese or _first(item.get("title")) or original or ""
    year = (_date(item.get("release_date") or item.get("publication_date")) or "")[:4] or _subtitle_year(
        item.get("subtitle")
    )

    mapped: list[tuple[str, str]] = []
    bangumi_id = _first(
        item.get("bangumi_game_id"),
        item.get("bangumi_book_id"),
        item.get("bangumi_subject_id"),
    )
    if bangumi_id:
        mapped.append(("bangumi", bangumi_id))
    vndb_id = _first(item.get("vndb_id"))
    if vndb_id:
        mapped.append(("vndb", vndb_id if vndb_id.lower().startswith("v") else f"v{vndb_id}"))

    return Candidate(
        source="hikarinagi",
        external_id=external_id or f"{kind}:{number}",
        title=display,
        original_title=original,
        year=year,
        # 那边自己的类型字样。**只有 galgame 给得出**：另两类的 `novel_status` / `serial_status`
        # 是连载状态、`adv_type` 是自由文本(实测有「精霊攻略アドベンチャー」这种)。
        kind="galgame" if kind == "galgame" else None,
        cover_url=_cover_url(item),
        media=TYPE_MEDIA[kind],
        # Galgame 本身就是一部作品,没有「系列 / 卷」这一层;另两类有分卷,算得上「这一部」。
        series=kind in VOLUME_TYPES,
        aliases=tuple(
            str(alias)
            for alias in (item.get("aliases") or item.get("other_names") or [])
            if str(alias).strip()
        ),
        external_refs=tuple(mapped),
    )


#: 连载状态 → 库里 `release_status` 用的词。它自己的枚举见开发者文档的 `NovelStatus`。
_STATUS = {
    "SERIALIZING": "连载中",
    "FINISHED": "已完结",
    "PAUSED": "休刊",
    "ABANDONED": "休刊",
}
