#!/usr/bin/env python3
# BlackFlame Studio 自动签到（看广告领金币）
#
# 机制（2026-11 实测）：
#   Next.js Server Action 三步走 —— startAdWatch → 等 requiredSeconds(30s) → verifyAndRewardAdWatch
#   服务端只校验时间间隔；广告弹窗只是前端摆设。
#   奖励：2026-11-16 实测站点把 adCoins 改成 1（旧版是 5）→ 每轮 +1 coin
#         ≈ 2 币/分钟 ≈ 120 币/小时；脚本用余额差算真实增量，不硬编码数额。
#
# 会话链：Discord Token →（NextAuth OAuth 自动授权）→ 站点会话（约 6 小时短命，故每次现换）
#
# 环境变量：
#   BFLAME_DISCORD_TOKEN   必需  Discord 账号 token（MTxx... 格式）
#   BFLAME_RUN_MINUTES     可选  >0 = 持续循环跑多少分钟（一直运行模式）
#   BFLAME_WATCHES         可选  RUN_MINUTES=0 时的轮数，默认 1（每轮约 32 秒，+1 币）
#   BFLAME_BASE            可选  站点地址，默认 https://dashbord.blackflamestudio.us.ci
#
# 节奏：每轮 startAdWatch → 等 requiredSeconds(30s) → verify，+1 coin；
#       无冷却（实测连刷可用），循环模式下会话 4h 主动重登（会话 6h 过期）。
#
# 退出码：0 成功；2 有轮次失败；3 登录链失败

import json
import os
import re
import sys
import time
import http.cookiejar
import urllib.request
import urllib.error
import urllib.parse

BASE = os.environ.get("BFLAME_BASE", "https://dashbord.blackflamestudio.us.ci").rstrip("/")
WATCHES = int(os.environ.get("BFLAME_WATCHES", "1"))
RUN_MINUTES = int(os.environ.get("BFLAME_RUN_MINUTES", "0"))
TOKEN = os.environ.get("BFLAME_DISCORD_TOKEN", "").strip()

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

# Server Action ID（站点 chunk 0.deue4ydm.nr.js 内 createServerReference 硬编码；
# 站点重新构建后会变，脚本带自动重发现兜底）
ACT_START = None
ACT_CANCEL = None
ACT_VERIFY = None

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def log(msg):
    print(msg, flush=True)


def req(url, method="GET", headers=None, data=None, timeout=30, retries=5):
    """GET 可重试网络错误；POST 不重试，避免请求已送达时重复执行。"""
    attempts = retries if method.upper() == "GET" else 1
    last = None
    for i in range(attempts):
        try:
            r = urllib.request.Request(url, data=data, method=method, headers=headers or {})
            with opener.open(r, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            log(f"  网络错误 {i + 1}/{attempts}: {type(e).__name__}")
            if i + 1 < attempts:
                time.sleep(2 + i * 2)
    raise last


def site(path, method="GET", headers=None, data=None):
    h = {"User-Agent": UA, "Origin": BASE, "Referer": BASE + "/dashboard"}
    h.update(headers or {})
    return req(BASE + path, method=method, headers=h, data=data)


def flight_error(text):
    """从 RSC flight 载荷提取 {"error":"..."}；$undefined 等引用值不是错误"""
    for m in re.finditer(r'"error"\s*:\s*"([^"]+)"', text):
        v = m.group(1)
        if not v.startswith("$"):
            return v
    return None


# ---------- 登录链 ----------
def login():
    log("== 登录链：Discord Token → 站点会话 ==")
    # 0) 验 Discord token
    try:
        st, txt = req("https://discord.com/api/v9/users/@me",
                      headers={"Authorization": TOKEN, "User-Agent": UA}, retries=2)
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "code", None)
        if code in (401, 403):
            log(f"❌ Discord token 已失效（HTTP {code}）—— 请更新 secret BFLAME_DISCORD_TOKEN")
        else:
            log(f"❌ Discord 请求失败: {type(e).__name__}: {e}")
        sys.exit(3)
    if st != 200:
        log(f"❌ Discord 身份请求未成功（HTTP {st}），请检查授权与网络")
        sys.exit(3)
    me = json.loads(txt)
    log(f"  Discord: {me['username']} (id {me['id']})")

    # 1) CSRF
    st, txt = site("/api/auth/csrf")
    csrf = json.loads(txt)["csrfToken"]

    # 2) 拿 Discord 授权 URL
    body = urllib.parse.urlencode({
        "csrfToken": csrf, "callbackUrl": "/dashboard", "json": "true"}).encode()
    st, txt = site("/api/auth/signin/discord", method="POST",
                   headers={"Content-Type": "application/x-www-form-urlencoded"}, data=body)
    auth_url = json.loads(txt)["url"]
    parsed_auth = urllib.parse.urlsplit(auth_url)
    if parsed_auth.scheme != "https" or parsed_auth.hostname not in ("discord.com", "discordapp.com"):
        raise RuntimeError("unexpected Discord authorization host")

    # 3) Discord 侧自动批准
    st, txt = req(auth_url, method="POST",
                  headers={"Authorization": TOKEN, "User-Agent": UA,
                           "Content-Type": "application/json",
                           "Origin": "https://discord.com"},
                  data=json.dumps({"permissions": "0", "authorize": True,
                                   "integration_type": 0}).encode())
    grant = json.loads(txt)
    if "location" not in grant:
        log(f"❌ OAuth 自动授权失败: {json.dumps(grant, ensure_ascii=False)[:300]}")
        sys.exit(3)

    # 4) 回调换会话
    loc = urllib.parse.urlparse(grant["location"])
    site(loc.path + ("?" + loc.query if loc.query else ""))

    # 5) 校验
    st, txt = site("/api/auth/session")
    sess = json.loads(txt)
    if "user" not in sess:
        log(f"❌ 会话未建立: {txt[:200]}")
        sys.exit(3)
    log(f"  会话: {sess['user']['name']} | coins={sess['user']['coins']} "
        f"| expires={sess.get('expires')}")
    return sess


# ---------- Server Action ----------
def action(action_id):
    return site("/dashboard", method="POST",
                headers={"Next-Action": action_id,
                         "Content-Type": "text/plain;charset=UTF-8",
                         "Accept": "text/x-component"},
                data=b"[]")


def coins_now():
    st, txt = site("/api/auth/session")
    return json.loads(txt)["user"]["coins"]


# ---------- Server Action ID 自动重发现 ----------
ACTION_RE = re.compile(
    r'createServerReference\)\("([0-9a-f]{40,64})",[\s\S]{0,180}?"(startAdWatch|cancelAdWatch|verifyAndRewardAdWatch)"\)'
)
CHUNK_RE = re.compile(r"/_next/static/chunks/[^\"'\\ )]+\.js")


def parse_action_ids(js):
    """从明确的 createServerReference 映射提取 ID，不按位置猜。"""
    result = {}
    for action_id, name in ACTION_RE.findall(js):
        if name in result and result[name] != action_id:
            raise RuntimeError('conflicting action IDs')
        result[name] = action_id
    return result


def rediscover_ids():
    global ACT_START, ACT_CANCEL, ACT_VERIFY
    code, html = site('/dashboard')
    if code != 200:
        raise RuntimeError(f'dashboard HTTP {code}')
    chunks = sorted(set(CHUNK_RE.findall(html)))
    if not chunks:
        raise RuntimeError('dashboard has no JS chunks')
    found = {}
    for chunk in chunks:
        code, js = req(BASE + chunk, headers={'User-Agent': UA}, retries=2)
        if code != 200:
            continue
        for name, action_id in parse_action_ids(js).items():
            if name in found and found[name] != action_id:
                raise RuntimeError('conflicting action IDs across chunks')
            found[name] = action_id
    if not all(name in found for name in ('startAdWatch', 'verifyAndRewardAdWatch')):
        raise RuntimeError('required action IDs not found')
    ACT_START = found['startAdWatch']
    ACT_VERIFY = found['verifyAndRewardAdWatch']
    ACT_CANCEL = found.get('cancelAdWatch')
    log('✅ 已从当前页面发现签到操作 ID')


def flight_objects(raw):
    out = []
    for line in raw.splitlines():
        if ':' not in line:
            continue
        try:
            obj = json.loads(line.split(':', 1)[1])
            if isinstance(obj, dict): out.append(obj)
        except (ValueError, TypeError):
            pass
    return out


def find_success(objects):
    return next((obj for obj in objects if obj.get('success') is True), None)


def one_round(index):
    """一次请求不重复提交；只有响应和余额均确认才算到账。"""
    log(f'-- 第 {index} 轮 --')
    before = coins_now()
    status, raw = action(ACT_START)
    objects = flight_objects(raw)
    result = find_success(objects)
    error = flight_error(raw)
    need = result.get('requiredSeconds') if result else None
    if status != 200 or error or isinstance(need, bool) or not isinstance(need, int) or not 1 <= need <= 300:
        log(f'❌ 开始请求未确认（HTTP {status}，原因 {str(error or "响应格式不符")[:120]}），停止本轮任务')
        return False, 0
    log(f'开始请求已确认，等待 {need} 秒')
    time.sleep(need + 2)
    # 不重试 POST；网络异常可能表示已提交，调用方会终止后续轮次。
    status, raw = action(ACT_VERIFY)
    objects = flight_objects(raw)
    result = find_success(objects)
    error = flight_error(raw)
    after = coins_now()
    delta = after - before
    log(f'复核余额: {before} → {after}（净变化 {delta:+}）')
    if status != 200 or error or result is None:
        log(f'❌ 领取接口未确认（HTTP {status}，原因 {str(error or "响应格式不符")[:120]}）')
        return False, 0
    if delta <= 0:
        log('❌ 净余额未增加，可能有并发扣费；不能独立核实到账')
        return False, 0
    log('✅ 接口成功且余额增加，已核实本轮到账')
    return True, delta


def main():
    if not TOKEN:
        log('❌ 缺 BFLAME_DISCORD_TOKEN')
        return 3
    try:
        login()
        rediscover_ids()
        before = coins_now()
    except Exception as e:
        log(f'❌ 登录或发现操作 ID 失败: {type(e).__name__}')
        return 3
    started = time.monotonic()
    deadline = started + max(RUN_MINUTES, 0) * 60
    successful = 0
    attempted = 0
    verified_gain = 0
    all_ok = True
    while (time.monotonic() < deadline if RUN_MINUTES > 0 else attempted < WATCHES):
        attempted += 1
        try:
            good, delta = one_round(attempted)
        except Exception as e:
            log(f'❌ 本轮结果未知: {type(e).__name__}；不重试任何 POST')
            good, delta = False, 0
        if not good:
            all_ok = False
            break
        successful += 1
        verified_gain += delta
        if RUN_MINUTES > 0 and time.monotonic() < deadline:
            time.sleep(2)
    try:
        after = coins_now()
        net = f'{after - before:+}'
    except Exception:
        after = '?'
        net = '?'
        all_ok = False
    log(f'完成 {successful}/{attempted} 轮 · 余额 {before} → {after} · 净变化 {net} · 已核实正向变化合计 {verified_gain}')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as f:
            f.write('## BlackFlame 签到结果\n\n')
            f.write(f'确认到账轮数：{successful}/{attempted}；余额：{before} → {after}；净变化：{net}。\n')
    return 0 if all_ok and attempted > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
