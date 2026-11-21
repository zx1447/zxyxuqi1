#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BotStable 免费服务器自动续期。

站点:  https://botstable.eu
机制:  Discord OAuth (PKCE) → 会话 Cookie → /api/renew/servers → /api/renew/renew

规则（站点 API 返回，renew.js / _renew_rules.js）:
  period_hours = 120   每续一次给 5 天（从点击时刻重新计时，不是累加！）
  window_hours = 48    剩余 ≤48 小时才开放续期
  keep_days    = 7     过期后挂起保留 7 天，期间续期可恢复

⚠️ 因为续期是「重置为 now+5d」而非累加，早续会白白丢掉剩余时间。
   脚本只在 can_renew=true 或 now>=opens_at 时才真正点击续期。

环境变量:
  BOTSTABLE_DISCORD_TOKEN  必需  Discord 账号 token（MTxx... 格式）
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.parse

import requests

BASE = os.environ.get("BOTSTABLE_BASE", "https://botstable.eu").rstrip("/")
TOKEN = os.environ.get("BOTSTABLE_DISCORD_TOKEN", "").strip()
FORCE = os.environ.get("FORCE_RUN", "false").strip().lower() == "true"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DISCORD_API = "https://discord.com/api/v10"

PERIOD_HOURS = 120
WINDOW_HOURS = 48
KEEP_DAYS = 7


class BotStableError(RuntimeError):
    pass


class NotOpenYet(BotStableError):
    """还没到 48 小时窗口，属于正常跳过。"""
    pass


def log(message: str) -> None:
    print(message, flush=True)


def now_str() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def fmt_span(seconds: float) -> str:
    seconds = max(0, int(seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}天{h}小时{m}分"
    if h:
        return f"{h}小时{m}分"
    return f"{m}分"


def ts(epoch: int | float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def make_session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    return s


def verify_discord_token() -> dict:
    r = requests.get(
        f"{DISCORD_API}/users/@me",
        headers={"Authorization": TOKEN, "User-Agent": UA},
        timeout=25,
    )
    if r.status_code in (401, 403):
        raise BotStableError(f"Discord token 已失效（HTTP {r.status_code}）—— 请更新 BOTSTABLE_DISCORD_TOKEN")
    if r.status_code != 200:
        raise BotStableError(f"Discord 验证失败：HTTP {r.status_code} {r.text[:150]}")
    return r.json()


def login() -> requests.Session:
    """Discord Token → OAuth 自动批准（PKCE）→ __Host-renew 会话。"""
    if not TOKEN:
        raise BotStableError("缺少环境变量 BOTSTABLE_DISCORD_TOKEN")

    me = verify_discord_token()
    log(f"  Discord: {me['username']} (id {me['id']})")

    s = make_session()

    # 1) 取授权跳转（带 PKCE 参数与 state Cookie）
    r = s.get(f"{BASE}/api/renew/login", allow_redirects=False, timeout=25)
    if r.status_code != 302:
        raise BotStableError(f"取授权页失败：HTTP {r.status_code}")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r.headers.get("location", "")).query)
    for key in ("client_id", "redirect_uri", "state", "code_challenge"):
        if key not in q:
            raise BotStableError(f"授权跳转缺少参数 {key}")

    # 2) Discord 侧自动批准
    #    permissions/authorize/integration_type 缺一不可，否则返回 access_denied
    auth_url = f"{DISCORD_API}/oauth2/authorize?" + urllib.parse.urlencode(
        {
            "client_id": q["client_id"][0],
            "response_type": "code",
            "redirect_uri": q["redirect_uri"][0],
            "scope": q.get("scope", ["identify"])[0],
            "state": q["state"][0],
            "code_challenge": q["code_challenge"][0],
            "code_challenge_method": q.get("code_challenge_method", ["S256"])[0],
        }
    )
    r = requests.post(
        auth_url,
        headers={
            "Authorization": TOKEN,
            "User-Agent": UA,
            "Content-Type": "application/json",
            "Origin": "https://discord.com",
        },
        json={"permissions": "0", "authorize": True, "integration_type": 0},
        timeout=25,
    )
    if r.status_code != 200:
        raise BotStableError(f"OAuth 授权失败：HTTP {r.status_code} {r.text[:200]}")
    try:
        location = r.json().get("location", "")
    except ValueError:
        raise BotStableError(f"OAuth 返回非 JSON：{r.text[:200]}")
    if "code=" not in location:
        raise BotStableError(f"OAuth 未返回授权码：{location[:200]}")

    # 3) 回调换会话（PKCE verifier 在 state Cookie 里）
    r = s.get(location, allow_redirects=True, timeout=25)
    if "__Host-renew" not in s.cookies:
        raise BotStableError(f"回调未建立会话（HTTP {r.status_code}，URL {r.url[:80]}）")
    log("  ✅ 会话已建立")
    return s


def list_servers(s: requests.Session) -> dict:
    r = s.get(f"{BASE}/api/renew/servers", timeout=25)
    if r.status_code == 401:
        raise BotStableError("会话失效（401）")
    if r.status_code == 429:
        raise BotStableError("请求过频（429），稍后再试")
    if r.status_code != 200:
        raise BotStableError(f"读取服务器失败：HTTP {r.status_code} {r.text[:150]}")
    data = r.json()
    if not isinstance(data.get("servers"), list):
        raise BotStableError(f"服务器列表格式异常：{str(data)[:200]}")
    return data


def renew(s: requests.Session, server_id) -> dict:
    r = s.post(
        f"{BASE}/api/renew/renew",
        headers={"Content-Type": "application/json", "Origin": BASE},
        json={"server_id": server_id},
        timeout=30,
    )
    body = {}
    try:
        body = r.json()
    except ValueError:
        pass
    if r.status_code == 200 and body.get("server"):
        return body
    err = body.get("error", "")
    if r.status_code == 409 and err == "not_open_yet":
        raise NotOpenYet(f"尚未开放，还需 {fmt_span(body.get('opens_in_seconds', 0))}")
    if r.status_code == 403 and err == "deadline_missed":
        raise BotStableError("保留期已过，服务器无法再续 —— 需去 Discord 找管理员")
    if r.status_code == 404:
        raise BotStableError("该服务器不在此账号下")
    if r.status_code == 401:
        raise BotStableError("会话失效（401）")
    if r.status_code == 429:
        raise NotOpenYet("请求过频（429），本轮跳过")
    raise BotStableError(f"续期失败：HTTP {r.status_code} {json.dumps(body, ensure_ascii=False)[:200]}")


def main() -> int:
    log("=" * 60)
    log("🚀 BotStable 免费服务器自动续期")
    log(f"🕐 {now_str()}")
    log(f"📋 规则：每续 {PERIOD_HOURS}h（重置不累加） · 剩余 ≤{WINDOW_HOURS}h 才可续 · 过期保留 {KEEP_DAYS} 天")
    log("=" * 60)

    try:
        s = login()
        data = list_servers(s)
        now = data.get("now", int(time.time()))
        servers = data.get("servers", [])
        user = (data.get("user") or {}).get("name", "?")
        log(f"👤 账号：{user} · 共 {len(servers)} 台服务器")

        if not servers:
            log("ℹ️ 该账号下没有服务器")
            return 0

        results = []
        for sv in servers:
            name = sv.get("name", "?")
            sid = sv.get("server_id")
            status = sv.get("status", "?")
            can_renew = bool(sv.get("can_renew"))
            opens_at = sv.get("opens_at")
            expires_at = sv.get("expires_at")
            log("")
            log(f"── {name} (id={sid}) 状态={status} ──")

            if status == "deadline_missed":
                log("❌ 保留期已过，跳过")
                results.append((name, "deadline_missed"))
                continue

            if status == "suspended":
                deadline = sv.get("deadline_at")
                if deadline:
                    log(f"⏰ 挂起中，保留至 {ts(deadline)}（剩 {fmt_span(deadline - now)}）")
                if can_renew or FORCE:
                    log("🔄 挂起服务器，尝试续期恢复…")
                    body = renew(s, sid)
                    log(f"🎉 已恢复，新到期 {ts(body['server'].get('expires_at', 0))}")
                    results.append((name, "unsuspended"))
                else:
                    log("⏳ 当前不可续，跳过")
                    results.append((name, "suspended_wait"))
                continue

            # active
            if expires_at:
                log(f"📅 到期 {ts(expires_at)}（剩 {fmt_span(expires_at - now)}）")
            if can_renew or FORCE:
                if FORCE and not can_renew:
                    log("⚡ FORCE_RUN=true，强制续期（会重置计时器，可能损失剩余时间）")
                else:
                    log("✅ 已进入 48h 窗口，发起续期…")
                body = renew(s, sid)
                new_exp = body["server"].get("expires_at", 0)
                log(f"🎉 续期成功，新到期 {ts(new_exp)}（+{PERIOD_HOURS}h）")
                results.append((name, "renewed"))
            else:
                if opens_at:
                    log(f"⏳ 未到窗口，{ts(opens_at)} 开放（还有 {fmt_span(opens_at - now)}）")
                else:
                    log("⏳ 未到窗口，跳过")
                results.append((name, "waiting"))

        log("")
        log("=" * 60)
        renewed = [n for n, r in results if r in ("renewed", "unsuspended")]
        if renewed:
            log(f"🎉 本轮完成：{', '.join(renewed)}")
        else:
            log("⏳ 本轮无需动作（都不在可续窗口内）")
        return 0

    except NotOpenYet as exc:
        log(f"⏳ 未到续期窗口，正常跳过：{exc}")
        return 0
    except Exception as exc:  # noqa: BLE001
        log(f"❌ BotStable 续期失败：{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
