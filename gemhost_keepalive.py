#!/usr/bin/env python3
# GemHost.pl 免费服守护：只做一件事 —— 停了就启动
#
# 策略（2026-11-22 按用户要求简化）：
#   cron 每 6 小时跑一次 → 登录 → 查状态 → status=offline 就 POST start
#   不做主动续期（restart / stop→start 全部移除）。
#   理由：免费会话硬上限 360 分钟，GitHub cron 实际派发间隔会被饿到 ~6 小时，
#   主动续期只是把「停机时刻」提前，不能真正避免停机；
#   而 start 一定分配一个满额 360 分钟会话，靠 cron 定期兜底拉起最可靠。
#
# 实测时间线（证明 cron 派发间隔 ≈ 6h）：
#   11-21 19:12 cron → offline → 拉起 → 会话至 11-22 01:13
#   11-22 01:16 cron → offline → 拉起 → 会话至 11-22 07:16
#   11-22 07:16 会话到期停机
#
# API：
#   POST {base}/api/auth/login {"email","password"}
#     → Set-Cookie: gemhost_access(JWT,7天) + gemhost_csrf
#   GET  {base}/api/servers/list                      名下全部服务器
#   GET  {base}/api/servers/<id>/status               {status, is_suspended, free_session{...}}
#   POST {base}/api/servers/<id>/power {"action":"start|stop|restart|kill"}
#     ⚠️ restart 是陷阱：会让服务器变 offline 且 free_session=None（清零不是重置），
#        且不会自己起来 —— 已弃用。
#   变更类请求带 X-CSRF-Token: <gemhost_csrf cookie 值>
#
# 环境变量：
#   GEMHOST_EMAIL / GEMHOST_PASSWORD   登录凭据（必填）
#   GEMHOST_BASE                       默认 https://panel.gemhost.pl
#
# 退出码：0 全部正常/拉起成功；2 有失败；3 登录失败/无凭据

import http.cookiejar
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = os.environ.get("GEMHOST_BASE", "https://panel.gemhost.pl").rstrip("/")
EMAIL = os.environ.get("GEMHOST_EMAIL", "").strip()
PASSWORD = os.environ.get("GEMHOST_PASSWORD", "").strip()
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gemhost_state.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0")

# 视为"活着"的状态；stopping 等本轮放过（下轮自然变 offline 再拉）
# 拉起后等待服务回到 running 的最长秒数
RENEW_WAIT_SECONDS = int(os.environ.get("RENEW_WAIT_SECONDS", "90"))
# 单轮内的复查间隔（秒）；cron 才是主力，这里只防「刚发出 start 还没起来」
WAKE_SECONDS = int(os.environ.get("WAKE_SECONDS", "60"))

OK_STATES = {"running", "starting"}
SKIP_STATES = {"stopping", "installing", "restoring"}


def log(msg):
    print(msg, flush=True)


class Session:
    """极简 cookie 会话（gemhost_access / gemhost_csrf 两个命名 cookie）"""

    def __init__(self):
        self.cookies = {}

    def request(self, path, method="GET", body=None, retries=3):
        url = f"{BASE}{path}"
        data = json.dumps(body).encode() if body is not None else None
        last = None
        for i in range(retries):
            req = urllib.request.Request(url, data=data, method=method, headers={
                "User-Agent": UA,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": BASE,
                "Referer": f"{BASE}/",
            })
            if self.cookies:
                req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in self.cookies.items()))
            if method != "GET" and self.cookies.get("gemhost_csrf"):
                req.add_header("X-CSRF-Token", self.cookies["gemhost_csrf"])
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    self._absorb(resp)
                    raw = resp.read().decode("utf-8", "replace")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                self._absorb(e)
                raw = e.read().decode("utf-8", "replace")
                try:
                    return json.loads(raw) if raw else {"http_error": e.code}
                except Exception:  # noqa: BLE001
                    return {"http_error": e.code, "body": raw[:300]}
            except Exception as e:  # noqa: BLE001
                last = e
                log(f"  [网络重试 {i + 1}/{retries}] {type(e).__name__}: {e}")
                time.sleep(2 + i * 2)
        raise last

    def _absorb(self, resp):
        # http.client 的 headers：get_all 拿全部 Set-Cookie；空值=清除，跳过
        hdrs = getattr(resp, "headers", None)
        if not hdrs:
            return
        for line in (hdrs.get_all("Set-Cookie") or []):
            name, _, rest = line.partition("=")
            value = rest.split(";")[0].strip()
            name = name.strip()
            if name and value:
                self.cookies[name] = value


def load_state():
    try:
        d = json.load(open(STATE, encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_state(sess, servers_seen):
    out = {"cookies": sess.cookies, "servers": servers_seen,
           "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def login(sess):
    log(f"== 登录 {EMAIL} ==")
    d = sess.request("/api/auth/login", method="POST",
                     body={"email": EMAIL, "password": PASSWORD})
    if "gemhost_access" not in sess.cookies:
        log(f"❌ 登录失败: {json.dumps(d, ensure_ascii=False)[:300]}")
        return False
    log(f"✅ {d.get('message', 'ok')}（user id {(d.get('user') or {}).get('id')}）")
    return True


def session_alive(sess):
    """缓存 cookie 是否还能用：能拉到服务器列表就算活。"""
    if not sess.cookies:
        return False
    try:
        lst = sess.request("/api/servers/list")
        return bool((lst.get("servers") is not None)
                    or lst.get("success")
                    or "servers" in json.dumps(lst, ensure_ascii=False).lower())
    except Exception:                              # noqa: BLE001
        return False


def wait_until_up(sess, sid, limit=RENEW_WAIT_SECONDS):
    """轮询到服务回到 OK_STATES，返回 (status, free_session)。"""
    waited = 0
    stt = {}
    while waited < limit:
        time.sleep(6)
        waited += 6
        stt = sess.request(f"/api/servers/{sid}/status")
        st = (stt.get("status") or "?").lower()
        if st in OK_STATES:
            return st, stt.get("free_session") or {}
    return (stt.get("status") or "?").lower(), stt.get("free_session") or {}


def main():
    if not EMAIL or not PASSWORD:
        log("❌ 缺 GEMHOST_EMAIL / GEMHOST_PASSWORD")
        sys.exit(3)

    sess = Session()
    st = load_state()
    sess.cookies = dict(st.get("cookies") or {})

    # 先试缓存 cookie；401/无内容则重登录
    lst = sess.request("/api/servers/list")
    if not isinstance(lst, dict) or "servers" not in lst:
        log("缓存会话失效，重新登录")
        if not login(sess):
            sys.exit(3)
        lst = sess.request("/api/servers/list")

    servers = lst.get("servers") or []
    if not servers:
        log("⚠️ 名下没有服务器")
        save_state(sess, [])
        sys.exit(0)

    log(f"== GemHost 守护 x{len(servers)}（{BASE}）==")
    ok = 0
    rows = []
    seen = []
    # 本轮观测到的最小会话剩余时间（分钟），用于算下一轮该睡多久
    min_remain_min = None
    for s in servers:
        sid, name = s["id"], s.get("name", "?")
        seen.append({"id": sid, "name": name})
        stt = sess.request(f"/api/servers/{sid}/status")
        status = (stt.get("status") or "?").lower()
        susp = stt.get("is_suspended")
        fs = stt.get("free_session") or {}
        ends = fs.get("ends_at") or "-"
        remain_ms = fs.get("remaining_ms")
        remain_min = round(remain_ms / 60000, 1) if isinstance(remain_ms, (int, float)) else None
        log(f"-- [{sid}] {name} | status={status} | suspended={susp} | 会话至 {ends}"
            + (f" | 剩余 {remain_min}min" if remain_min is not None else ""))
        if remain_min is not None and (min_remain_min is None or remain_min < min_remain_min):
            min_remain_min = remain_min

        if susp:
            log("  ⏭ 已挂起（suspended），跳过")
            rows.append((sid, name, status, "⏭ 挂起", ends))
            ok += 1
            continue

        if status in OK_STATES:
            # 运行中就不动（用户要求：只做「停了就启动」，不做主动续期）
            log(f"  ✅ 运行中，无需动作"
                + (f"（剩余 {remain_min}min）" if remain_min is not None else ""))
            rows.append((sid, name, status, "—", ends))
            ok += 1
            continue
        if status in SKIP_STATES:
            log("  ⏭ 过渡状态，下轮复查")
            rows.append((sid, name, status, "⏭ 等下轮", ends))
            ok += 1
            continue

        log(f"  🚀 检测到停止 → 拉起")
        # 最多试 3 次：CI 上偶发网络抖动会让 urlopen 直接抛异常，
        # 原来抛出去会被外层吞掉 → 日志里只有「检测到停止」却没有任何响应体
        started = False
        for attempt in (1, 2, 3):
            try:
                r = sess.request(f"/api/servers/{sid}/power", method="POST",
                                 body={"action": "start"})
                log(f"     [{attempt}] start 响应: "
                    f"{json.dumps(r, ensure_ascii=False)[:200]}")
                started = True
                break
            except Exception as exc:            # noqa: BLE001
                log(f"     [{attempt}] start 异常: {type(exc).__name__}: {exc}")
                time.sleep(3 * attempt)
        if not started:
            log("     ⚠️ start 三次均失败，补发最后一次")
            try:
                sess.request(f"/api/servers/{sid}/power", method="POST",
                             body={"action": "start"})
            except Exception as exc:            # noqa: BLE001
                log(f"     补发也失败: {type(exc).__name__}: {exc}")
        time.sleep(10)
        try:
            stt2 = sess.request(f"/api/servers/{sid}/status")
        except Exception as exc:                # noqa: BLE001
            log(f"     复查失败: {type(exc).__name__}: {exc}")
            stt2 = {}
        status2 = (stt2.get("status") or "?").lower()
        fs2 = stt2.get("free_session") or {}
        ends2 = fs2.get("ends_at") or "-"
        log(f"     复查: status={status2} | 新会话至 {ends2}")
        if status2 in OK_STATES:
            ok += 1
            rows.append((sid, name, status, "🚀 已拉起", ends2))
        else:
            rows.append((sid, name, status, f"❌ 拉起后 {status2}", ends2))
            log(f"     ❌ 拉起未成功，状态仍为 {status2}")
        time.sleep(1)

    save_state(sess, seen)
    log(f"\n== 完成 {ok}/{len(servers)} ==")

    # ── 下一轮唤醒：固定间隔（不再按会话剩余时间自适应）──
    # cron 每 6 小时一轮，脚本单轮很快（几秒），无需轮内长驻。
    next_wake_seconds = WAKE_SECONDS
    log(f"[wake] 固定 {next_wake_seconds}s（{next_wake_seconds//60} 分钟）后复查")

    # 供 workflow 读取（写进 $GITHUB_OUTPUT）
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"next_wake_seconds={next_wake_seconds or 1800}\n")
            f.write(f"min_remain_min={min_remain_min if min_remain_min is not None else ''}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## GemHost 守护结果\n\n")
            f.write("| 服务器 | 名称 | 原状态 | 动作 | 会话至 |\n|---|---|---|---|---|\n")
            for r in rows:
                f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |\n")
    sys.exit(0 if ok == len(servers) else 2)


if __name__ == "__main__":
    main()
