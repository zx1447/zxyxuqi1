#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AcoreHost 路由枚举：找出「面板点启动」对应的真实接口。

技巧：对只接受 POST 的路由发 GET，会返回 405 (Method Not Allowed) 而不是 404，
      所以用 GET 就能无副作用地把路由存在性嗅出来。

背景：API key 调 POST /power 和 GET /resources 全 409 "server is suspended"，
      但面板网页上能点启动 → 面板走的是另一条（扩展）路由，或用了会话认证。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE = (os.environ.get("ACORE_BASE") or "https://dash.acorehosting.com").rstrip("/")
KEY = (os.environ.get("ACORE_API_KEY") or "").strip().strip("'\"").strip()
UUID = os.environ.get("ACORE_UUID") or "23a11fd8-5b0f-458f-8a04-f0d422b2d07e"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0")


def call(path, method="GET", auth=True):
    h = {"User-Agent": UA, "Accept": "application/json"}
    if auth:
        h["Authorization"] = f"Bearer {KEY}"
    if method != "GET":
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + path, data=b"{}" if method != "GET" else None,
                               method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            raw = x.read().decode("utf-8", "replace")
            return x.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:                       # noqa: BLE001
            return e.code, {"raw": raw[:120]}
    except Exception as e:                      # noqa: BLE001
        return 0, {"err": type(e).__name__}


def main():
    print("=== ① key 完整权限（判断是不是权限问题）===")
    c, d = call("/api/client/account/api-keys")
    if c == 200:
        for k in ((d.get("api_keys") or {}).get("data") or []):
            print(f"  key: {k.get('name')} start={k.get('key_start')} "
                  f"enabled={k.get('enabled')}")
            print(f"  user_permissions = {k.get('user_permissions')}")
    else:
        print(f"  {c} {d}")

    EXT = "/api/client/extensions/dev.sqidgeon.serverplans"
    print("\n=== ② 扩展路由枚举（GET 探存在性：405=存在, 404=不存在）===")
    words = ["start", "stop", "restart", "wake", "boot", "power", "unmount",
             "unsuspend", "activate", "enable", "launch", "resume", "resume-server",
             "start-server", "server-start", "deploy", "restore", "renew", "status",
             "server", "servers", "plan", "plans", "info", "config"]
    hits = []
    for w in words:
        for path in (f"{EXT}/{w}", f"{EXT}/server/{UUID}/{w}",
                     f"{EXT}/servers/{UUID}/{w}"):
            c, d = call(path)
            mark = ""
            if c == 405:
                mark = "  ⬅ ✅ 存在（仅接受 POST）"
                hits.append(path)
            elif c == 200:
                mark = "  ⬅ ✅ 存在（GET 可用）"
                hits.append(path)
            if c not in (404,):
                print(f"  GET {path.replace(EXT, '<EXT>').replace(UUID, '<uuid>'):52} "
                      f"{c}  {json.dumps(d, ensure_ascii=False)[:90]}{mark}")

    print("\n=== ③ 客户端路由枚举（找有没有非 power 的启动入口）===")
    for path in [f"/api/client/servers/{UUID}/suspend",
                 f"/api/client/servers/{UUID}/unsuspend",
                 f"/api/client/servers/{UUID}/renew",
                 f"/api/client/servers/{UUID}/restore",
                 f"/api/client/servers/{UUID}/wake",
                 f"/api/client/servers/{UUID}/billing",
                 f"/api/client/servers/{UUID}/plan"]:
        c, d = call(path)
        if c != 404:
            print(f"  GET {path.split(UUID)[0]}<uuid>{path.split(UUID)[1]:16} {c}  "
                  f"{json.dumps(d, ensure_ascii=False)[:120]}")

    print("\n=== ④ 不带鉴权试试（看是不是被 key 的 middleware 拦）===")
    for path in [f"/api/client/servers/{UUID}/resources",
                 f"/api/client/servers/{UUID}/power"]:
        c, d = call(path, method="GET" if "resources" in path else "POST", auth=False)
        print(f"  无鉴权 {path.split(UUID)[0]}<uuid>{path.split(UUID)[1]:14} {c}  "
              f"{json.dumps(d, ensure_ascii=False)[:120]}")

    print(f"\n汇总：存在性命中 {len(hits)} 条")
    for h in hits:
        print(f"  • {h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
