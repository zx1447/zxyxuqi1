#!/usr/bin/env python3
# 一次性探针：面板「点启动」的真实接口 = POST {EXT}/storage/start（用户从 DevTools 抓到，200 OK）
# ① GET 探 storage/* 存在性（405=存在，无副作用）
# ② 用 API key POST storage/start（带 {"server": uuid}），看 key 能不能调用、返回什么
# ③ 立刻复查 /resources 状态
import json
import os
import time
import urllib.request
import urllib.error

BASE = "https://dash.acorehosting.com"
KEY = os.environ.get("ACORE_API_KEY", "").strip().strip("'\"").strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0")
EXT = "/api/client/extensions/dev.sqidgeon.serverplans"


def req(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method, headers={
        "User-Agent": UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KEY}",
    })
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, raw[:400]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]
    except Exception as e:  # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}"


def main():
    code, raw = req("/api/client/servers")
    print(f"清单 HTTP {code}", flush=True)
    servers = []
    if code == 200:
        servers = json.loads(raw) if raw.startswith("{") and len(raw) < 400 else []
    # 清单拿完整 body
    r = urllib.request.Request(BASE + "/api/client/servers", headers={
        "User-Agent": UA, "Accept": "application/json",
        "Authorization": f"Bearer {KEY}"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        lst = json.loads(resp.read().decode())
    servers = (lst.get("servers") or {}).get("data") or []
    for s in servers:
        print(f"  server {s.get('uuid')} {s.get('name')} suspended={s.get('is_suspended')}", flush=True)

    print("\n=== ① storage 路由存在性（GET）===", flush=True)
    for w in ["storage", "storage/start", "storage/status", "storage/stop",
              "storage/restart", "storage/power", "storage/info", "storage/server"]:
        c, b = req(f"{EXT}/{w}")
        print(f"  GET {w:18s} {c}  {b[:80]}", flush=True)

    print("\n=== ② POST storage/start（用 key）===", flush=True)
    for s in servers:
        uuid = s.get("uuid")
        print(f"-- [{uuid[:8]}] {s.get('name')}", flush=True)
        for body in ({"server": uuid}, {}):
            c, b = req(f"{EXT}/storage/start", method="POST", body=body)
            print(f"  POST storage/start body={json.dumps(body)} → {c} {b[:200]}", flush=True)
            if c in (200, 204):
                break
        time.sleep(3)
        c, b = req(f"/api/client/servers/{uuid}/resources")
        print(f"  复查 /resources → {c} {b[:200]}", flush=True)
        time.sleep(15)
        c, b = req(f"/api/client/servers/{uuid}/resources")
        print(f"  15s 后 /resources → {c} {b[:200]}", flush=True)


if __name__ == "__main__":
    main()
