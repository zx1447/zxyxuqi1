#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扒 AcoreHost 面板前端，找「点启动」实际调用的接口。

背景：面板网页能点启动，但 API key 的 POST /power 返回 409 server is suspended，
连只读的 /resources 也 409。说明面板走的不是 key 认证，而是会话(session)。
这里把前端 JS 拉下来，搜 power/start/suspended 相关的 URL 构造。

只读，不改任何状态。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

BASE = "https://dash.acorehosting.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0")


def get(path, accept="text/html,application/xhtml+xml,*/*;q=0.8"):
    r = urllib.request.Request(BASE + path, headers={
        "User-Agent": UA, "Accept": accept, "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "sec-ch-ua": '"Chromium";v="157", "Microsoft Edge";v="157"',
        "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"})
    try:
        with urllib.request.urlopen(r, timeout=40) as x:
            return x.status, x.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                      # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def main():
    print("=== ① 首页 ===")
    c, h = get("/")
    print(f"  GET /  {c}  长度 {len(h)}")
    if c != 200:
        print(f"  内容: {h[:200]}")
        print("  ⚠️ 首页拿不到，跳过前端分析")
        return 0

    js = re.findall(r'<script[^>]+src="([^"]+)"', h)
    js += re.findall(r'<link[^>]+href="([^"]+\.js)"', h)
    js = [u for u in dict.fromkeys(js)]
    print(f"  发现 {len(js)} 个脚本: {js[:6]}")

    # 也看看内联 script 里有没有 window.__ 配置
    inline = re.findall(r"<script[^>]*>(.{0,4000}?)</script>", h, re.S)
    for i, s in enumerate(inline[:4]):
        s2 = " ".join(s.split())
        if len(s2) > 40:
            print(f"  内联[{i}]: {s2[:300]}")

    print("\n=== ② 搜脚本内容里的关键路径 ===")
    pats = [r'[/"\'](api/client/[^"\'\s]{0,60})',
            r'(suspended[^"\']{0,40})',
            r'(["\']\S*power\S*["\'])',
            r'(["\']\S*serverplans\S*["\'])']
    seen = set()
    for u in js[:8]:
        full = u if u.startswith("http") else BASE + ("" if u.startswith("/") else "/") + u
        cc, body = get(full.replace(BASE, ""), accept="*/*")
        print(f"\n  -- {u}  HTTP {cc}  长度 {len(body)}")
        if cc != 200:
            continue
        for p in pats:
            for m in re.findall(p, body)[:6]:
                v = m if isinstance(m, str) else str(m)
                if v not in seen and len(v) < 80:
                    seen.add(v)
                    print(f"     {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
