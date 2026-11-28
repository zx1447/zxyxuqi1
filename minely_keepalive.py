#!/usr/bin/env python3
"""Check MineLy AZll and start only if confirmed offline."""
import json
import os
import re
import sys
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
import requests

BASE='https://minely.net'
SERVER_ID='vHWIs9iFb_14-s8J_Q_n1'
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'

class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.csrf=''; self.input_token=''; self.links=[]
    def handle_starttag(self, tag, attrs):
        d=dict(attrs)
        if tag=='input' and d.get('name')=='_token': self.input_token=d.get('value','')
        if tag=='meta' and d.get('name')=='csrf-token': self.csrf=d.get('content','')
        if tag=='a' and d.get('href'):self.links.append(d['href'])

def parse_page(text):
    p=Page();p.feed(text);return p

def home_has_server(html, server_id=SERVER_ID):
    expected='/my/s/'+server_id
    for href in parse_page(html).links:
        p=urlsplit(urljoin(BASE,href))
        if p.scheme=='https' and p.hostname=='minely.net' and p.path.rstrip('/')==expected:return True
    return False

def health_state(data):
    if not isinstance(data,dict) or data.get('ok') is not True or data.get('node_lost') is True:
        raise RuntimeError('health unavailable or node disconnected')
    if data.get('installing') is True:raise RuntimeError('server installation in progress')
    r=data.get('resources')
    if not isinstance(r,dict):raise RuntimeError('health has no resources')
    state=r.get('current_state')
    if state not in ('running','offline','starting','stopping'):
        raise RuntimeError('unknown server state')
    return state

class Client:
    def __init__(self):
        self.s=requests.Session();self.s.headers.update({'User-Agent':UA});self.csrf=''
    def login(self, username, password):
        r=self.s.get(BASE+'/my/login',timeout=25);r.raise_for_status()
        token=parse_page(r.text).input_token
        if not token:raise RuntimeError('login CSRF missing')
        r=self.s.post(BASE+'/my/login',data={'_token':token,'email':username,'password':password},headers={'Origin':BASE,'Referer':BASE+'/my/login'},timeout=30,allow_redirects=True)
        r.raise_for_status()
        p=urlsplit(r.url)
        if p.scheme!='https' or p.hostname!='minely.net' or p.path.rstrip('/')=='/my/login':raise RuntimeError('login was not confirmed')
        r=self.s.get(BASE+'/my/home',timeout=25);r.raise_for_status()
        if urlsplit(r.url).path.rstrip('/')=='/my/login' or not home_has_server(r.text):raise RuntimeError('target server not found in authenticated home')
        r=self.s.get(BASE+'/my/s/'+SERVER_ID,timeout=25);r.raise_for_status()
        if urlsplit(r.url).path.rstrip('/')!='/my/s/'+SERVER_ID:raise RuntimeError('server page unavailable')
        self.csrf=parse_page(r.text).csrf
        if not self.csrf:raise RuntimeError('server CSRF missing')
    def headers(self):
        return {'Accept':'application/json','X-Requested-With':'XMLHttpRequest','X-CSRF-TOKEN':self.csrf,'Origin':BASE,'Referer':BASE+'/my/s/'+SERVER_ID}
    def health(self):
        r=self.s.get(BASE+'/my/x/servers/'+SERVER_ID+'/health',headers=self.headers(),timeout=25);r.raise_for_status()
        return health_state(r.json())
    def start(self):
        r=self.s.post(BASE+'/my/x/servers/'+SERVER_ID+'/power',headers=self.headers(),json={'signal':'start'},timeout=30)
        r.raise_for_status()
        return r.status_code

def ensure_running(client, wait_seconds=150, interval=10):
    deadline=time.monotonic()+wait_seconds
    started=False
    while True:
        try: state=client.health()
        except Exception as e:
            print('❌ 无法读取真实状态:',type(e).__name__,flush=True);return False
        print('服务器 AZll 当前状态:',state,flush=True)
        if state=='running':return True
        if state=='offline' and not started:
            # Set first: never repeat POST, even if the response is lost.
            started=True
            try: print('启动请求 HTTP',client.start(),flush=True)
            except Exception as e:print('启动请求失败或结果未知:',type(e).__name__,'；只复查，不重复提交',flush=True)
        elif state=='offline' and started:
            pass
        if time.monotonic()>=deadline:
            print('❌ 在等待时间内未确认 running',flush=True);return False
        time.sleep(min(interval,max(0,deadline-time.monotonic())))

def main():
    username=os.environ.get('MINELY_USERNAME','').strip();password=os.environ.get('MINELY_PASSWORD','')
    if not username or not password:
        print('❌ 缺少账号或密码 Secret');return 3
    client=Client()
    try:client.login(username,password)
    except Exception as e:
        print('❌ 登录或验证服务器失败:',type(e).__name__,flush=True);return 3
    print('✅ 已登录；发现目标服务器 AZll',flush=True)
    if ensure_running(client):print('✅ 已确认服务器 running',flush=True);return 0
    return 2

if __name__=='__main__':sys.exit(main())
