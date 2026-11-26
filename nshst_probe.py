#!/usr/bin/env python3
"""只读检查 NSHST 账户下的服务器与实际运行状态。"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://dash.nshst.com'
TOKEN = os.environ.get('NSHST_API_KEY', '').strip()


def get(path):
    request = urllib.request.Request(BASE + path, headers={
        'Authorization': 'Bearer ' + TOKEN,
        'Accept': 'application/json',
        'User-Agent': 'NSHST-status-check/1.0',
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    if not TOKEN:
        print('❌ 缺少 NSHST_API_KEY', flush=True)
        return 2
    try:
        servers = []
        page = 1
        while True:
            data = get('/api/client?' + urllib.parse.urlencode({'per_page': 100, 'page': page}))
            rows = data.get('data')
            if not isinstance(rows, list):
                raise ValueError('服务器列表格式异常')
            servers.extend(x.get('attributes') or {} for x in rows)
            pagination = (data.get('meta') or {}).get('pagination') or {}
            last = int(pagination.get('total_pages') or 1)
            if page >= last:
                break
            page += 1
        print(f'服务器数量: {len(servers)}', flush=True)
        if not servers:
            print('❌ 未发现服务器；请核对 API 权限', flush=True)
            return 2
        errors = 0
        for server in servers:
            ident = server.get('identifier')
            if not ident or any(c not in '0123456789abcdefABCDEF-' for c in ident):
                print('❌ 服务器标识异常', flush=True)
                errors += 1
                continue
            try:
                result = get('/api/client/servers/' + urllib.parse.quote(ident, safe='') + '/resources')
                attr = result.get('attributes') or {}
                current = attr.get('current_state')
                if not current:
                    raise ValueError('运行状态缺失')
                print(f"[{ident}] {server.get('name', '?')} · 状态={current} · suspended={attr.get('is_suspended')}", flush=True)
            except Exception as exc:
                print(f'❌ [{ident}] 状态读取失败: {type(exc).__name__}', flush=True)
                errors += 1
        print('仅只读检查；没有发送续期、启动或停止请求。', flush=True)
        return 2 if errors else 0
    except urllib.error.HTTPError as exc:
        print(f'❌ API HTTP {exc.code}；请检查 API key 和权限', flush=True)
        return 2
    except Exception as exc:
        print(f'❌ API 读取失败: {type(exc).__name__}', flush=True)
        return 2


if __name__ == '__main__':
    sys.exit(main())
