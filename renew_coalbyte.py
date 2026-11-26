#!/usr/bin/env python3
# CoalByte 自动续期（Pelican 免费游戏服）
#
# 续期请求必须携带 serverType：minecraft 当前为 90 分钟，discord 为 5 天。
# 续期后核对单服和列表数据，随后用 WebSocket 检查实际状态；没启动则发 start。
# 即使续期失败也尝试启动。续期计划 cron 保持原样。
#
# 环境变量：
#   COALBYTE_EMAIL     可选  用于自动发现名下全部服务器（推荐）
#   COALBYTE_SERVERS   可选  逗号分隔 serverId 列表（email 未配时的兜底）
#   COALBYTE_BASE      可选  默认 https://coalbyte.com
#
# 退出码：0 全部成功；2 有失败；3 没有可续的服务器/配置

import json
from datetime import datetime
import os
import re
import sys
import time
import urllib.request
import urllib.parse
import websocket

BASE = os.environ.get("COALBYTE_BASE", "https://coalbyte.com").rstrip("/")
EMAIL = os.environ.get("COALBYTE_EMAIL", "").strip()
SERVERS = [s.strip() for s in os.environ.get("COALBYTE_SERVERS", "").split(",") if s.strip()]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0")


def log(msg):
    print(msg, flush=True)


def req(url, method="GET", data=None, retries=4):
    """网络请求带指数重试"""
    last = None
    for i in range(retries):
        try:
            r = urllib.request.Request(url, data=data, method=method, headers={
                "User-Agent": UA,
                "Content-Type": "application/json",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(r, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            last = e
            log(f"  [网络重试 {i + 1}/{retries}] {type(e).__name__}: {e}")
            time.sleep(2 + i * 2)
    raise last


def discover():
    """返回 [(identifier, name, expiresAt, canRenew)]"""
    out = []
    if EMAIL:
        q = urllib.parse.urlencode({"email": EMAIL})
        d = req(f"{BASE}/api/pelican/servers?{q}")
        if not d.get("userFound"):
            log(f"⚠️ 邮箱 {EMAIL} 未找到面板用户")
        for s in d.get("servers", []):
            r = s.get("renewal") or {}
            out.append((s["identifier"], s.get("name", "?"),
                        r.get("expiresAt"), r.get("canRenew"), (s.get("service") or {}).get("type")))
    for sid in SERVERS:
        if not any(o[0] == sid for o in out):
            detail = req(f"{BASE}/api/pelican/server?" + urllib.parse.urlencode({"id": sid}))
            info = detail.get("server") or {}
            out.append((sid, "(手动指定)", None, None, (info.get("service") or {}).get("type")))
    return out


def renew(server_id, email, server_type):
    if not server_type:
        raise ValueError("无法确定服务器类型，拒绝按错误类型续期")
    body = {"serverId": server_id, "serverType": server_type}
    if email:
        body["email"] = email
    return req(f"{BASE}/api/pelican/renew", method="POST",
               data=json.dumps(body).encode())


def real_state(ident):
    """使用真实 Wings WebSocket 状态，不依赖列表的默认 online 字段。"""
    creds = req(f"{BASE}/api/pelican/websocket?" + urllib.parse.urlencode({"id": ident}), retries=1)
    if not creds.get("socket") or not creds.get("token"):
        raise RuntimeError("WebSocket 凭据不可用")
    ws = websocket.create_connection(creds["socket"], timeout=15, origin=BASE,
                                     http_no_proxy=["*"])
    try:
        ws.send(json.dumps({"event": "auth", "args": [creds["token"]]}))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            msg = json.loads(ws.recv())
            event, args = msg.get("event"), msg.get("args") or []
            if event == "auth success":
                ws.send(json.dumps({"event": "send stats", "args": [None]}))
            elif event == "status" and args:
                return str(args[0]).lower()
            elif event == "stats" and args:
                stats = json.loads(args[0]) if isinstance(args[0], str) else args[0]
                if isinstance(stats, dict) and stats.get("state"):
                    return str(stats["state"]).lower()
            elif event in ("auth error", "daemon error"):
                raise RuntimeError("WebSocket 鉴权或节点错误")
        raise RuntimeError("WebSocket 未返回状态")
    finally:
        ws.close()


def ensure_running(ident):
    try:
        state = real_state(ident)
        log(f"  🖥 实际电源状态: {state}")
    except Exception as exc:
        state = None
        log(f"  ⚠️ 无法读取实际状态: {type(exc).__name__}")
    if state == "running":
        return True
    if state != "starting":
        try:
            result = req(f"{BASE}/api/pelican/power", method="POST", retries=1,
                         data=json.dumps({"id": ident, "signal": "start"}).encode())
            log(f"  🚀 启动请求: {result.get('message') or result.get('error') or result.get('success')}")
        except Exception as exc:
            log(f"  ❌ 启动请求异常: {type(exc).__name__}")
    for attempt in range(3):
        time.sleep(15)
        try:
            state = real_state(ident)
            log(f"  🖥 启动复查: {state}")
            if state == "running":
                return True
        except Exception as exc:
            log(f"  ⚠️ 启动复查失败: {type(exc).__name__}")
    log("  ❌ 未确认服务器达到 running")
    return False


def as_timestamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, AttributeError):
        return None


def verify_renewal(ident, previous, response):
    """不要只相信 POST：分别核对单服续期和名下列表的数据。"""
    expected = as_timestamp(response.get("expiresAt"))
    old = as_timestamp(previous)
    if expected is None or (old is not None and expected <= old):
        return False, "续期返回的到期时间没有推进"
    reason = "无核验结果"
    for attempt in range(2):
        try:
            direct = req(f"{BASE}/api/pelican/renew?" + urllib.parse.urlencode({"id": ident}), retries=1)
            direct_exp = direct.get("expiresAt")
            direct_t = as_timestamp(direct_exp)
            if not direct.get("success") or direct_t is None or abs(direct_t - expected) > 5:
                reason = f"单服查询与续期结果不一致: {direct_exp}"
            elif EMAIL:
                listing = req(f"{BASE}/api/pelican/servers?" + urllib.parse.urlencode({"email": EMAIL}), retries=1)
                record = next((x for x in listing.get("servers", []) if x.get("identifier") == ident), None)
                listed = (record or {}).get("renewal") or {}
                listed_exp = listed.get("expiresAt")
                listed_t = as_timestamp(listed_exp)
                if not listing.get("userFound") or not record or listed_t is None or abs(listed_t - expected) > 5:
                    reason = f"列表与单服续期数据不一致: 列表={listed_exp}, 单服={direct_exp}"
                else:
                    return True, direct_exp
            else:
                return True, direct_exp
        except Exception as exc:
            reason = f"核验请求失败: {type(exc).__name__}"
        if attempt == 0:
            time.sleep(4)
    return False, reason


def main():
    servers = discover()
    if not servers:
        log("❌ 没有可续的服务器（配 COALBYTE_EMAIL 或 COALBYTE_SERVERS）")
        sys.exit(3)

    log(f"== CoalByte 续期 x{len(servers)}（{BASE}）==")
    ok = 0
    rows = []
    for ident, name, exp, can, server_type in servers:
        log(f"-- [{ident}] {name}（类型 {server_type or '?'} · 列表到期 {exp or '?'} · canRenew={can}）--")
        verified, detail = False, "未尝试"
        try:
            d = renew(ident, EMAIL, server_type)
            if d.get("success"):
                verified, detail = verify_renewal(ident, exp, d)
                if verified:
                    log(f"  ✅ 独立核验通过 → 到期 {detail}")
                else:
                    log(f"  ❌ 续期未核验: {detail}")
            else:
                detail = str(d.get("error") or "续期接口拒绝")
                log(f"  ❌ {detail}")
        except Exception as exc:
            detail = f"续期请求失败: {type(exc).__name__}"
            log(f"  ❌ {detail}")
        # 无论续期是否成功，都检查实际运行状态并尽力启动。
        running = ensure_running(ident)
        if verified and running:
            ok += 1
        rows.append((ident, name, "✅" if verified and running else "❌ 未核验", detail))
        time.sleep(1)

    log(f"\n== 完成 {ok}/{len(servers)} ==")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## CoalByte 续期结果\n\n")
            f.write("| 服务器 | 名称 | 结果 | 新到期 |\n|---|---|---|---|\n")
            for r in rows:
                f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |\n")
    sys.exit(0 if ok == len(servers) else 2)


if __name__ == "__main__":
    main()
