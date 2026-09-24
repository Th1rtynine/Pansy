"""手动完成一次 Hikarinagi 用户级登录 —— 在浏览器打不开回调时用它。

**为什么需要这个**:登录的最后一步是浏览器跳到本机那个回调地址,而这一步没法由脚本代替
(要人在 Hikarinagi 页面上点「同意」)。脚本能做的:

1. 让后端生成一次授权(它会记下 PKCE 的 verifier 与 state);
2. 把那个跳转地址打出来 —— 你自己点开、登录、点同意;
3. Hikarinagi 会把你跳到 `127.0.0.1:8000/api/sources/hikarinagi/callback?code=...&state=...`。
   正常情况下后端会接住并显示一页「登录成功」;
4. **如果那一页没出来**(比如浏览器把它当下载、或者你只是把地址复制走了),
   把地址栏里那条完整地址整条粘给这个脚本,它替你完成第 3 步。

用法:

    python scripts/hikari-login.py            # 第 1~2 步:生成地址
    python scripts/hikari-login.py "<回调地址>"  # 第 4 步:拿那条地址完成兑换
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"


def call(path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(BASE + path, timeout=30) as answer:
            return answer.status, answer.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except Exception as error:  # noqa: BLE001
        return 0, f"连不上后端:{error}"


argument = " ".join(sys.argv[1:]).strip()

if not argument:
    status, body = call("/api/sources/hikarinagi/login")
    if status != 200:
        print("后端没答上来:", status, body[:300])
        raise SystemExit(1)
    answer = json.loads(body)
    if not answer.get("url"):
        print("现在没法开始登录:", answer.get("detail") or "(没说为什么)")
        raise SystemExit(1)
    print("=" * 74)
    print("把这个地址贴进浏览器,在 Hikarinagi 页面上点一次「同意」:")
    print("=" * 74)
    print(answer["url"])
    print()
    print("点完之后浏览器会跳到本机那个回调地址,后端会接住并显示结果。")
    print("如果那一页没出来,把地址栏里那条完整地址再跑一次:")
    print("    python scripts/hikari-login.py \"http://127.0.0.1:8000/api/sources/hikarinagi/callback?code=...&state=...\"")
    raise SystemExit(0)

# ---- 第二段:拿那条回调地址去敲后端 ----
pieces = urllib.parse.urlsplit(argument)
params = urllib.parse.parse_qs(pieces.query)
code = (params.get("code") or [""])[0]
state = (params.get("state") or [""])[0]
if not code or not state:
    print("这条地址里没有 code 或 state,粘贴错了?")
    print("收到的:", argument[:200])
    raise SystemExit(1)

status, body = call(f"/api/sources/hikarinagi/callback?code={urllib.parse.quote(code)}&state={urllib.parse.quote(state)}")
print("回调返回 HTTP", status)
for line in body.splitlines():
    stripped = line.strip()
    if stripped.startswith("<h1>") or (stripped.startswith("<p>") and "dim" not in stripped):
        clean = stripped.replace("<h1>", "").replace("</h1>", "").replace("<p>", "").replace("</p>", "")
        if clean:
            print("   ", clean)

status, body = call("/api/settings")
if status == 200:
    account = json.loads(body).get("hikarinagi_account") or {}
    print()
    print("后端现在记着的账号:")
    print("   logged_in =", account.get("logged_in"))
    print("   nickname  =", account.get("nickname"))
    print("   name      =", account.get("name"))
    print("   id        =", account.get("id"))
    print("   avatar    =", (account.get("avatar_url") or "")[:80])
