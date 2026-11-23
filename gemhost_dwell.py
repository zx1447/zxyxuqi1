#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GemHost 长驻守护：单轮驻留，会话到期前主动续期，永不停机。

为什么需要它：
  免费会话硬上限 360 分钟，而 GitHub cron 派发间隔实测约 6 小时（`*/6` 会被饿），
  两者等长 → 每轮之间必然停机 0~6 小时。只靠 cron 拉起只是「事后补救」。

本脚本做法：
  驻留 DWELL_MINUTES（默认 60）分钟，每 CHECK_SECONDS（默认 60）秒查一次状态；
  剩余 < RENEW_BEFORE（默认 20 分钟）→ stop → start 拿新的满额 360 分钟会话。
  这样在驻留窗口内永远不会让会话自然耗尽。

⚠️ restart 不可用（会让服务器变 offline 且 free_session=None，不会自己起来），
   续期必须用 stop → start。

环境变量：
  GEMHOST_EMAIL / GEMHOST_PASSWORD  登录凭据（必填）
  GEMHOST_BASE                      默认 https://panel.gemhost.pl
  DWELL_MINUTES                     驻留时长，默认 60
  CHECK_SECONDS                     巡检间隔，默认 60
  RENEW_BEFORE                      剩余多少分钟时续期，默认 20

退出码：0 正常；2 有失败；3 登录失败
"""
from __future__ import annotations

import json
import os
import sys
import time

# 复用同目录 gemhost_keepalive.py 的 Session / login / 状态解析
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemhost_keepalive as G

DWELL_MINUTES = int(os.environ.get("DWELL_MINUTES") or 60)
CHECK_SECONDS = int(os.environ.get("CHECK_SECONDS") or 60)
RENEW_BEFORE = int(os.environ.get("RENEW_BEFORE") or 20)

OK_STATES = {"running", "starting"}


def log(*a):
    G.log(*a)


def renew_by_stopstart(sess, sid):
    """stop → start 拿新的满额会话。返回 (ok, ends_at)。"""
    log("  🔄 会话快到期 → stop → start 换新会话")
    try:
        r = sess.request(f"/api/servers/{sid}/power", method="POST",
                         body={"action": "stop"})
        log(f"     stop : {json.dumps(r, ensure_ascii=False)[:120]}")
    except Exception as exc:                       # noqa: BLE001
        log(f"     stop 异常: {type(exc).__name__}: {exc}")
    time.sleep(10)

    for attempt in (1, 2, 3):
        try:
            r = sess.request(f"/api/servers/{sid}/power", method="POST",
                             body={"action": "start"})
            log(f"     start[{attempt}]: {json.dumps(r, ensure_ascii=False)[:120]}")
            break
        except Exception as exc:                   # noqa: BLE001
            log(f"     start[{attempt}] 异常: {type(exc).__name__}: {exc}")
            time.sleep(3 * attempt)

    for _ in range(10):
        time.sleep(10)
        try:
            st = sess.request(f"/api/servers/{sid}/status")
        except Exception:                          # noqa: BLE001
            continue
        status = (st.get("status") or "?").lower()
        fs = st.get("free_session") or {}
        ends = fs.get("ends_at") or "-"
        log(f"     复查: status={status} | 会话至 {ends}")
        if status in OK_STATES and ends != "-":
            return True, ends
    return False, "-"


def main():
    log(f"🎯 GemHost 长驻守护 · 驻留 {DWELL_MINUTES} 分钟 · "
        f"每 {CHECK_SECONDS}s 巡检 · 剩余 <{RENEW_BEFORE}min 续期")

    sess = G.Session()
    st = G.load_state()
    sess.cookies = dict(st.get("cookies") or {})

    if not G.session_alive(sess):
        if not G.login(sess):
            log("❌ 登录失败")
            return 3
        G.save_state(sess, st.get("servers") or [])

    servers = st.get("servers") or []
    if not servers:
        lst = sess.request("/api/servers/list")
        servers = [{"id": s["id"], "name": s.get("name", "?")}
                   for s in (lst.get("servers") or [])]
        G.save_state(sess, servers)
    log(f"📋 服务器: {', '.join(str(s['id']) for s in servers)}")

    deadline = time.time() + DWELL_MINUTES * 60
    n = 0
    try:
        while time.time() < deadline:
            n += 1
            log(f"—— 第 {n} 次巡检 ——")
            for s in servers:
                sid = s["id"]
                try:
                    info = sess.request(f"/api/servers/{sid}/status")
                except Exception as exc:           # noqa: BLE001
                    log(f"  读状态失败: {type(exc).__name__}: {exc}")
                    continue
                status = (info.get("status") or "?").lower()
                fs = info.get("free_session") or {}
                ends = fs.get("ends_at") or "-"
                remain = fs.get("remaining_ms")
                remain_min = (round(remain / 60000, 1)
                              if isinstance(remain, (int, float)) else None)
                log(f"  [{sid}] status={status} | 会话至 {ends}"
                    + (f" | 剩余 {remain_min}min" if remain_min is not None else ""))

                if status not in OK_STATES:
                    log("  🚀 未运行 → 拉起")
                    try:
                        sess.request(f"/api/servers/{sid}/power", method="POST",
                                     body={"action": "start"})
                    except Exception as exc:       # noqa: BLE001
                        log(f"     拉起异常: {type(exc).__name__}: {exc}")
                    continue

                if remain_min is not None and remain_min <= RENEW_BEFORE:
                    renew_by_stopstart(sess, sid)
                else:
                    log("  ✅ 运行中")
                G.save_state(sess, servers)
            rest = deadline - time.time()
            if rest <= 0:
                break
            time.sleep(min(CHECK_SECONDS, rest))
    finally:
        G.save_state(sess, servers)
    log(f"✅ 驻留结束（巡检 {n} 次）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
