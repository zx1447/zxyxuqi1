#!/usr/bin/env python3
"""手动单次浏览器测试；不会自派发，也没有定时任务。"""
import os
import sys
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE = 'https://console.rellact.xyz'


def log(*args):
    print(*args, flush=True)


def verify_widget(page):
    widget = page.locator('altcha-widget')
    if not widget.count():
        return True
    try:
        # 正常点击页面原生验证控件；不伪造验证结果。
        widget.locator('input[type=checkbox]').click(timeout=10000)
    except Exception as exc:
        log('❌ 验证控件点击失败:', type(exc).__name__)
        return False
    for _ in range(30):
        page.wait_for_timeout(1000)
        if page.get_by_text('Verified', exact=False).count() or not widget.is_visible():
            return True
        if page.locator('input[name=altcha]').count():
            if page.locator('input[name=altcha]').first.input_value():
                return True
    log('❌ 安全验证未完成')
    return False


def numeric_earned(data):
    if not isinstance(data, dict):
        return None
    candidates = [data, data.get('afk'), data.get('data')]
    if isinstance(data.get('data'), dict):
        candidates.append(data['data'].get('afk'))
    for obj in candidates:
        if isinstance(obj, dict) and isinstance(obj.get('earnedTodayCents'), (int, float)):
            return obj['earnedTodayCents']
    return None


def main():
    email, password = os.getenv('RELLACT_EMAIL'), os.getenv('RELLACT_PASSWORD')
    if not email or not password:
        log('❌ 缺少账号或密码 Secret')
        return 2
    status_calls = []
    observations = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = browser.new_context()
        page = ctx.new_page()

        def capture(response):
            u = urlparse(response.url)
            if not (u.hostname and (u.hostname == 'rellact.xyz' or u.hostname.endswith('.rellact.xyz'))):
                return
            path = u.path.lower()
            if '/rewards' not in path:
                return
            if '/afk/' in path:
                log('AFK 接口:', path.rsplit('/',1)[-1], 'HTTP', response.status)
            if response.request.method == 'GET' and response.status == 200:
                try:
                    value = numeric_earned(response.json())
                    if value is not None:
                        observations.append(value)
                        headers = response.request.all_headers()
                        auth = headers.get('authorization')
                        if auth:
                            status_calls[:] = [(response.url, auth)]
                except Exception:
                    pass

        page.on('response', capture)
        try:
            page.goto(BASE + '/login', wait_until='domcontentloaded', timeout=45000)
            page.locator('#identifier').fill(email, timeout=30000)
            page.locator('#password').fill(password)
            if not verify_widget(page):
                return 2
            button = page.get_by_role('button', name='Log in', exact=False)
            for _ in range(20):
                if button.is_enabled():
                    break
                page.wait_for_timeout(1000)
            if not button.is_enabled():
                log('❌ 登录按钮未解锁'); return 2
            button.click(timeout=10000)
            page.wait_for_timeout(10000)
            if '/login' in urlparse(page.url).path:
                text = page.locator('body').inner_text().lower()
                if 'verification code' in text or 'two-factor' in text or '6-digit' in text:
                    log('❌ 需要额外验证码或二次验证')
                else:
                    log('❌ 未确认登录成功，请检查账号或登录验证')
                return 2
            log('✅ 登录成功')
            page.goto(BASE+'/billing/rewards/afk', wait_until='domcontentloaded', timeout=45000)
            page.wait_for_timeout(5000)
            if '/login' in urlparse(page.url).path:
                log('❌ AFK 页面要求重新登录'); return 2
            if not verify_widget(page):
                return 2
            page.wait_for_timeout(6000)
            text = page.locator('body').inner_text().lower()
            if 'earning now' not in text:
                log('❌ AFK 未显示 Earning now'); return 2
            log('✅ AFK 页面显示 Earning now，开始复核服务端累计值')
            before = observations[-1] if observations else None
            # 只用于本次试运行；不配置长期挂机或定时任务。
            for _ in range(15):
                page.wait_for_timeout(10000)
            after = None
            if status_calls:
                url, auth = status_calls[-1]
                res = ctx.request.get(url, headers={'Authorization': auth, 'Accept':'application/json'}, timeout=30000)
                if res.ok:
                    after = numeric_earned(res.json())
            log('服务端今日 AFK 累计（分）:', before, '→', after)
            if before is None or after is None:
                log('❌ 无法核实实际到账'); return 2
            if after <= before:
                log('❌ 本次未核实累计增加'); return 2
            log('✅ 已核实服务端累计增加')
            return 0
        except Exception as exc:
            log('❌ 测试异常:',type(exc).__name__)
            return 2
        finally:
            ctx.close()
            browser.close()

if __name__ == '__main__':
    sys.exit(main())
