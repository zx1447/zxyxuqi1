#!/usr/bin/env python3
"""NSHST: check every accessible server and start it if not running.

This cannot renew the 7-day panel login requirement: the client API does not
expose expiry and it is unknown whether an API request counts as panel login.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://dash.nshst.com'
TOKEN = os.environ.get('NSHST_API_KEY', '').strip()


def request(path, method='GET', body=None):
    headers = {'Authorization': 'Bearer ' + TOKEN, 'Accept': 'application/json',
               'User-Agent': 'NSHST-server-monitor/1.0'}
    payload = None
    if body is not None:
        payload = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(BASE + path, data=payload, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        return response.status, json.loads(raw) if raw else {}


def list_servers():
    result, page = [], 1
    while True:
        _, data = request('/api/client?' + urllib.parse.urlencode({'per_page': 100, 'page': page}))
        rows = data.get('data')
        if not isinstance(rows, list):
            raise ValueError('服务器列表格式异常')
        result.extend(x.get('attributes') or {} for x in rows)
        last = int(((data.get('meta') or {}).get('pagination') or {}).get('total_pages') or 1)
        if page >= last:
            return result
        page += 1


def status(identifier):
    _, data = request('/api/client/servers/' + identifier + '/resources')
    attrs = data.get('attributes')
    if not isinstance(attrs, dict) or not attrs.get('current_state'):
        raise ValueError('资源状态缺失')
    return attrs['current_state'], attrs.get('is_suspended')


def check(server):
    ident = server.get('identifier')
    if not ident or any(c not in '0123456789abcdefABCDEF-' for c in ident):
        print('❌ 服务器标识异常', flush=True)
        return False
    ident = urllib.parse.quote(ident, safe='')
    try:
        current, suspended = status(ident)
        print(f'[{ident}] {server.get("name", "?")} · 状态={current} · suspended={suspended}', flush=True)
        if current == 'running' and suspended is False:
            return True
    except Exception as exc:
        print(f'⚠️ [{ident}] 状态读取失败: {type(exc).__name__}', flush=True)
        current = None
    # 不因续期接口未知或状态读取异常而跳过启动尝试。
    if current != 'starting':
        try:
            code, _ = request('/api/client/servers/' + ident + '/power', 'POST', {'signal': 'start'})
            print(f'[{ident}] 启动请求 HTTP {code}；等待状态确认', flush=True)
        except urllib.error.HTTPError as exc:
            print(f'❌ [{ident}] 启动请求 HTTP {exc.code}', flush=True)
        except Exception as exc:
            print(f'❌ [{ident}] 启动请求异常: {type(exc).__name__}', flush=True)
    for attempt in range(12):
        time.sleep(10)
        try:
            current, suspended = status(ident)
            print(f'[{ident}] 复查 {attempt+1}: {current}, suspended={suspended}', flush=True)
            if current == 'running' and suspended is False:
                print(f'✅ [{ident}] 已确认 running', flush=True)
                return True
        except Exception as exc:
            print(f'⚠️ [{ident}] 复查失败: {type(exc).__name__}', flush=True)
    print(f'❌ [{ident}] 无法确认服务器 running', flush=True)
    return False


def main():
    if not TOKEN:
        print('❌ 缺少 NSHST_API_KEY', flush=True)
        return 2
    try:
        servers = list_servers()
    except urllib.error.HTTPError as exc:
        print(f'❌ 服务器列表 HTTP {exc.code}', flush=True)
        return 2
    except Exception as exc:
        print(f'❌ 服务器列表读取失败: {type(exc).__name__}', flush=True)
        return 2
    print(f'服务器数量: {len(servers)}', flush=True)
    if not servers:
        print('❌ 未发现服务器', flush=True)
        return 2
    results = [check(s) for s in servers]
    print('⚠️ 续期/7天面板登录要求尚未自动化，也无法通过当前 API 核验到期日。', flush=True)
    return 0 if all(results) else 2


if __name__ == '__main__':
    sys.exit(main())
