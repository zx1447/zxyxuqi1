#!/usr/bin/env python3
"""Rellact 纯 HTTP 单次验证：正常解站点 ALTCHA，核验奖励累计。

本程序当前仅接到手动测试 workflow。正式定时任务需验证登录与实际到账。
"""
import base64
import hashlib
import json
import os
import sys
import time

import requests

BASE = 'https://console.rellact.xyz'
TENANT = '951a13a0-b1fd-4c64-bb1c-f393bb609326'


def log(*a): print(*a, flush=True)


def parse(r, label):
    if r.status_code not in (200, 201, 202, 204):
        raise RuntimeError(f'{label}: HTTP {r.status_code}')
    if r.status_code == 204 or not r.content:
        return {}
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError(f'{label}: 响应不是 JSON')
    if not isinstance(data, dict):
        raise RuntimeError(f'{label}: 响应格式异常')
    if data.get('success') is False or data.get('error'):
        raise RuntimeError(f'{label}: 站点返回失败')
    return data


def challenge(s):
    c = parse(s.get(BASE+'/api/auth/captcha/challenge', timeout=30), '获取验证')
    if c.get('algorithm') != 'SHA-256' or not all(isinstance(c.get(k),str) for k in ('challenge','salt','signature')):
        raise RuntimeError('ALTCHA 验证格式不支持')
    limit = int(c.get('maxnumber', 1000000))
    if limit < 0 or limit > 2000000:
        raise RuntimeError('ALTCHA 验证工作量异常')
    prefix = c['salt'].encode(); target = c['challenge']; start = time.monotonic()
    for number in range(limit + 1):
        if hashlib.sha256(prefix + str(number).encode()).hexdigest() == target:
            data = {k:c[k] for k in ('algorithm','challenge','salt','signature')}
            data.update(number=number,took=int((time.monotonic()-start)*1000))
            return base64.b64encode(json.dumps(data,separators=(',',':')).encode()).decode()
    raise RuntimeError('ALTCHA 验证未解出')


def login(s):
    token = os.getenv('RELLACT_SESSION_TOKEN','').strip()
    if token:
        s.headers['Authorization'] = 'Bearer ' + token
        log('使用单独保存的 Rellact 会话')
        return
    email = os.getenv('RELLACT_EMAIL','').strip()
    password = os.getenv('RELLACT_PASSWORD','')
    if not email or not password:
        raise RuntimeError('缺少账号或密码')
    cap = challenge(s)
    data = parse(s.post(BASE+'/api/auth/login', json={'identifier':email,'password':password,'capToken':cap}, timeout=30), '登录')
    if data.get('twoFactorRequired'):
        raise RuntimeError('登录需要邮箱或二次验证码；无法自动完成')
    token = data.get('token')
    if not isinstance(token,str) or not token:
        raise RuntimeError('登录未返回会话')
    s.headers['Authorization'] = 'Bearer ' + token
    log('✅ 账号登录返回会话')


def get_status(s):
    data = parse(s.get(f'{BASE}/api/tenants/{TENANT}/rewards', timeout=30), '奖励状态')
    afk = data.get('afk')
    if not isinstance(afk,dict):
        raise RuntimeError('奖励状态缺少 AFK 数据')
    earned = afk.get('earnedTodayCents')
    if not isinstance(earned,(int,float)) or isinstance(earned,bool):
        raise RuntimeError('服务端 AFK 累计缺失')
    return earned, afk.get('dailyCapCents')


def wallet(s):
    data = parse(s.get(f'{BASE}/api/tenants/{TENANT}/wallet',timeout=30),'钱包')
    value = data.get('balanceCents')
    if not isinstance(value,(int,float)) or isinstance(value,bool):
        raise RuntimeError('钱包余额字段缺失')
    return value


def main():
    s = requests.Session(); s.trust_env=False
    s.headers.update({'User-Agent':'Mozilla/5.0','Accept':'application/json',
                      'Origin':BASE,'Referer':BASE+'/billing/rewards/afk'})
    started = False
    try:
        login(s)
        before, cap = get_status(s)
        before_wallet = wallet(s)
        log('登录核验通过；AFK 今日累计（分）', before, '钱包余额（分）', before_wallet, '每日上限（分）', cap)
        if isinstance(cap,(int,float)) and cap > 0 and before >= cap:
            log('⏳ 站点显示已达到当日上限，未开启 AFK')
            return 0
        proof = challenge(s)
        r = s.post(f'{BASE}/api/tenants/{TENANT}/rewards/afk/start',json={'capToken':proof},timeout=30)
        parse(r,'AFK start'); started=True
        log('AFK start 已接受；等待实际到账核验')
        # 单次诊断，按网页每 30 秒心跳；不是长期挂机。
        for i in range(5):
            time.sleep(30)
            r=s.post(f'{BASE}/api/tenants/{TENANT}/rewards/afk/heartbeat',timeout=30)
            parse(r,'AFK heartbeat')
            log('心跳',i+1,'已接受')
        after,_=get_status(s)
        after_wallet=wallet(s)
        log('服务端 AFK 今日累计（分）:',before,'→',after)
        log('钱包余额（分）:',before_wallet,'→',after_wallet)
        if after <= before:
            log('❌ 无法确认 AFK 累计增加，不能以 200 作为成功')
            return 2
        log('✅ 已确认服务端 AFK 累计增加')
        return 0
    except Exception as e:
        log('❌ 请求测试未完成:',type(e).__name__,str(e)[:160])
        return 2
    finally:
        if started:
            try:
                r=s.post(f'{BASE}/api/tenants/{TENANT}/rewards/afk/stop',timeout=20)
                parse(r,'AFK stop')
                log('AFK 会话已关闭')
            except Exception:
                log('⚠️ AFK stop 未确认')
        s.close()


if __name__ == '__main__': sys.exit(main())
