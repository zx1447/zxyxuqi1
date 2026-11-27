#!/usr/bin/env python3
"""RKing server 55: check actual state, start once when offline, verify online."""
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://rkingindustries.com'
SERVER_ID = 55
WAIT_SECONDS = 150
POLL_SECONDS = 10
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'


def log(message):
    print(message, flush=True)


class Client:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, *, method='GET', data=None):
        request = urllib.request.Request(BASE + path, data=data, method=method, headers={
            'User-Agent': UA, 'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded' if path == '/api/login' else 'application/json',
        })
        try:
            with self.opener.open(request, timeout=20) as response:
                raw = response.read().decode('utf-8', 'replace')
                status = response.status
        except urllib.error.HTTPError as error:
            raw = error.read().decode('utf-8', 'replace')
            status = error.code
        try:
            result = json.loads(raw) if raw else {}
        except (ValueError, TypeError):
            result = {}
        return status, result

    def login(self, username, password):
        body = urllib.parse.urlencode({'username': username, 'password': password, 'stay_logged_in': 'false'}).encode()
        code, result = self.request('/api/login', method='POST', data=body)
        if code != 200 or not isinstance(result, dict) or result.get('ok') is not True:
            raise RuntimeError(f'login failed (HTTP {code})')

    def snapshot(self):
        code, detail = self.request(f'/api/minecraft/servers/{SERVER_ID}')
        stat_code, stats = self.request(f'/api/minecraft/servers/{SERVER_ID}/stats')
        if code != 200 or stat_code != 200 or not isinstance(detail, dict) or not isinstance(stats, dict):
            raise RuntimeError(f'status query failed (detail HTTP {code}, stats HTTP {stat_code})')
        if detail.get('id') != SERVER_ID or stats.get('ok') is not True:
            raise RuntimeError('server ID or live statistics could not be verified')
        return detail, stats

    def start(self):
        # Same POST as the site's Start button; do not retry a possibly delivered request.
        return self.request(f'/api/minecraft/servers/{SERVER_ID}/start', method='POST')


def maintain(client, max_checks=None):
    if max_checks is None:
        max_checks = WAIT_SECONDS // POLL_SECONDS + 1
    start_sent = False
    for attempt in range(max_checks):
        try:
            detail, stats = client.snapshot()
        except Exception as error:
            log(f'❌ 无法验证状态: {type(error).__name__}')
            return False
        state = str(detail.get('state') or '?').lower()
        real_state = str(stats.get('state') or '?').lower()
        uptime = stats.get('uptime_seconds')
        log(f'服务器 {SERVER_ID} · 面板={state} · 实时统计={real_state} · uptime={uptime}')
        if state == 'online' and real_state == 'online' and isinstance(uptime, (int, float)) and not isinstance(uptime, bool) and uptime > 0:
            log('✅ 已确认 online，且实时统计显示运行时长')
            return True
        if state == 'offline' and real_state == 'offline' and not start_sent:
            if detail.get('disk_over'):
                log('❌ 存储超限，面板禁止启动；需先处理存储空间')
                return False
            install = (detail.get('modpack') or {}).get('install') if isinstance(detail.get('modpack'), dict) else None
            if isinstance(install, dict) and not install.get('error') and not install.get('pending'):
                log('⏳ 模组包安装中，等待站点自动启动，不重复下发')
            else:
                if detail.get('expired'):
                    log('⚠️ 面板显示计划已过期，仍尝试一次启动并核查结果')
                start_sent = True
                try:
                    code, result = client.start()
                    log(f'启动请求 HTTP {code}；以复查状态为准')
                except Exception as error:
                    log(f'⚠️ 启动请求结果未知: {type(error).__name__}；不重复发送')
        else:
            log('⏳ 状态未完全在线；启动中或状态不一致时不重复发送启动')
        if attempt + 1 < max_checks:
            time.sleep(POLL_SECONDS)
    log('❌ 等待后仍未确认 online')
    return False


def main():
    username = os.environ.get('RKING_USERNAME', '').strip()
    password = os.environ.get('RKING_PASSWORD', '')
    if not username or not password:
        log('❌ 缺少 RKing 登录 Secrets')
        return 3
    client = Client()
    try:
        client.login(username, password)
    except Exception as error:
        log(f'❌ 登录失败: {type(error).__name__}')
        return 3
    return 0 if maintain(client) else 2


if __name__ == '__main__':
    sys.exit(main())
