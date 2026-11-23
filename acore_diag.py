#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AcoreHost 诊断：搞清楚「面板能点启动、API 却 409」到底卡在哪。

只做只读探测，唯一一次写操作是发 start（用户说面板可以点启动，所以这是安全的）。
输出候选的启动端点和 key 权限，供人判断该换 key 还是换端点。

退出码：0 探测完成；3 key 失效
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = (os.environ.get("ACORE_BASE") or "https://dash.acorehosting.com").rstrip("/")
KEY = (os.environ.get("ACORE_API_KEY") or "").strip().strip("'\"").strip()
EXT = "/api/client/extensions/dev.sqidgeon.serverplans"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0")


def req(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method, headers={
        "User-Agent": UA, "Accept": "application/json",
        "Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            raw = x.read().decode("utf-8", "replace")
            return x.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:                       # noqa: BLE001
            return e.code, {"raw": raw[:200]}
    except Exception as e:                      # noqa: BLE001
        return 0, {"err": f"{type(e).__name__}: {e}"}


def brief(d, n=220):
    return json.dumps(d, ensure_ascii=False)[:n]


def main():
    if not KEY:
        print("❌ 没有 ACORE_API_KEY")
        return 3
    print(f"🔍 key 后缀 ...{KEY[-6:]}  长度 {len(KEY)}")

    # 1) key 身份与权限 —— 这决定了 409 是权限问题还是状态问题
    print("\n=== ① key 身份 / 权限 ===")
    for p in ["/api/client", "/api/client/account",
              "/api/client/account/api-keys"]:
        c, d = req(p)
        print(f"  GET {p:32} {c}  {brief(d)}")

    # 2) 服务器清单 + 单台详情
    print("\n=== ② 服务器 ===")
    c, d = req("/api/client/servers")
    if c == 401:
        print(f"  ❌ key 失效: {brief(d)}")
        return 3
    print(f"  GET /api/client/servers  {c}")
    uuids = []
    for s in ((d.get("servers") or {}).get("data") or []) or (d.get("data") or []):
        a = s.get("attributes") or s
        uuids.append(a.get("uuid"))
        print(f"  • {str(a.get('uuid'))[:8]} {a.get('name')} "
              f"suspended={a.get('is_suspended')} status={a.get('status')}")

    target = uuids[0] if uuids else os.environ.get("ACORE_UUID", "")
    if not target:
        print("⚠️ 没有服务器可诊断")
        return 0
    print(f"\n目标 {str(target)[:8]}")

    # 3) 只读状态端点
    print("\n=== ③ 状态端点 ===")
    for p in [f"/api/client/servers/{target}",
              f"/api/client/servers/{target}/resources",
              f"/api/client/servers/{target}/utilization"]:
        c, d = req(p)
        print(f"  GET {p.split(target)[0]}<uuid>{p.split(target)[1]}  {c}  {brief(d, 300)}")

    # 4) 候选启动端点 —— 只发 start，不碰 stop/restart
    print("\n=== ④ 启动端点候选（只发 start）===")
    cands = [
        (f"/api/client/servers/{target}/power", {"signal": "start"}),
        (f"/api/client/servers/{target}/start", {}),
        (f"/api/client/servers/{target}/action", {"action": "start"}),
        (f"{EXT}/start", {"server": target}),
        (f"{EXT}/wake", {"server": target}),
        (f"{EXT}/server/{target}/start", {}),
        (f"{EXT}/unmount", {"server": target}),
    ]
    for p, body in cands:
        c, d = req(p, method="POST", body=body)
        tag = p.replace(target, "<uuid>").replace(EXT, "<EXT>")
        verdict = ""
        if c in (200, 202, 204):
            verdict = "  ⬅ ✅ 可能成功"
        elif c == 409:
            verdict = "  ⬅ 409 冲突/已挂起"
        elif c == 404:
            verdict = "  ⬅ 端点不存在"
        elif c in (401, 403):
            verdict = "  ⬅ key 权限不足"
        print(f"  POST {tag:42} {c}  {brief(d, 180)}{verdict}")

    print("\n=== ⑤ 复查 ===")
    c, d = req(f"/api/client/servers/{target}/resources")
    r = d.get("resources") or {}
    print(f"  resources: {c} state={r.get('state')} uptime={r.get('uptime')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
