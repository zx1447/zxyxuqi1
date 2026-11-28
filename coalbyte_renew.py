#!/usr/bin/env python3
"""CoalByte: scoped DB renewal, final 48-hour gate, and actual power checks."""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from coalbyte_probe import BASE, SERVERS, UA, date, decision, discover, get

EMAIL = os.environ.get('COALBYTE_EMAIL', '').strip()
BOT_ID = '6995c463'


def read_json(url, headers=None):
    code, raw = get(url, headers)
    if code != 200: raise RuntimeError('GET HTTP ' + str(code))
    return json.loads(raw)


def row_url(sb, sid, email=None, status=None, expiry=None):
    params = {'server_id':'eq.' + sid}
    if email is not None: params['user_email']='eq.' + email
    if status is not None: params['status']='eq.' + status
    if expiry is not None: params['expires_at']='eq.' + expiry
    return sb + '/rest/v1/server_renewals?' + urllib.parse.urlencode(params)


def read_row(sb,key,sid):
    headers={'apikey':key,'Authorization':'Bearer '+key,'Accept':'application/json'}
    rows=read_json(row_url(sb,sid),headers)
    if not isinstance(rows,list) or len(rows)!=1: raise RuntimeError('renewal row not unique')
    return rows[0]


def public_renewal(sid):
    j=read_json(BASE+'/api/pelican/renew?'+urllib.parse.urlencode({'id':sid}))
    if not j.get('success'): raise RuntimeError('renewal status unavailable')
    return j


def can_write(sid, row, email, now, public):
    if sid not in SERVERS: return 'NOT_IN_ALLOWLIST'
    state=decision(row,email,now)
    if state != 'IN_WINDOW': return state
    if sid != BOT_ID: return 'PLAN_DURATION_UNCONFIRMED'
    direct=date(public.get('expiresAt'))
    prior=date(row.get('expires_at'))
    if public.get('status') != 'active' or direct is None or abs((direct-prior).total_seconds())>2:
        return 'PUBLIC_STATUS_MISMATCH'
    return 'READY'


def patch_row(sb,key,sid,email,old_expiry,now):
    """One PATCH only, optimistic condition prevents overwriting changed expiry."""
    new=(now+timedelta(days=5)).isoformat(timespec='milliseconds')
    body=json.dumps({'expires_at':new,'last_renewed_at':now.isoformat(timespec='milliseconds')}).encode()
    h={'User-Agent':UA,'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json','Prefer':'return=representation'}
    req=urllib.request.Request(row_url(sb,sid,email,'active',old_expiry),data=body,method='PATCH',headers=h)
    try:
        with urllib.request.urlopen(req,timeout=30) as resp: raw=resp.read().decode()
    except urllib.error.HTTPError as e:
        raise RuntimeError('PATCH HTTP '+str(e.code)) from None
    # Never retry a mutation if the response is missing, malformed, or ambiguous.
    try: rows=json.loads(raw)
    except ValueError: raise RuntimeError('PATCH response unknown') from None
    if not isinstance(rows,list) or len(rows)!=1: raise RuntimeError('PATCH affected no unique row')
    return date(new)


def renew_one(sb,key,sid,email,now=None):
    now=now or datetime.now(timezone.utc)
    row=read_row(sb,key,sid);public=public_renewal(sid)
    print(sid,'status',row.get('status'),'expiry',row.get('expires_at'),flush=True)
    reason=can_write(sid,row,email,now,public)
    if reason=='TOO_EARLY': print('  >48h, no renewal',flush=True);return True
    if reason!='READY': print('  renewal NOT verified:',reason,flush=True);return False
    old=date(row['expires_at'])
    try:
        expected=patch_row(sb,key,sid,email,row['expires_at'],now)
    except Exception as exc:
        print('  PATCH result unknown or failed:',type(exc).__name__,flush=True);return False
    # Both authoritative record and service's own public renewal view must agree.
    try:
        checked=read_row(sb,key,sid);direct=public_renewal(sid)
        got=date(checked.get('expires_at'));app=date(direct.get('expiresAt'))
        ok=(expected is not None and got is not None and app is not None and got>old
            and abs((got-expected).total_seconds())<2 and abs((app-got).total_seconds())<2
            and checked.get('status')=='active' and direct.get('status')=='active')
        if ok: print('  renewal VERIFIED:',old.isoformat(),'->',got.isoformat(),flush=True);return True
    except Exception as exc: print('  renewal verification error:',type(exc).__name__,flush=True)
    print('  renewal NOT verified after PATCH',flush=True);return False


def real_state(sid):
    import websocket
    creds=read_json(BASE+'/api/pelican/websocket?'+urllib.parse.urlencode({'id':sid}))
    if not creds.get('success') or not creds.get('socket') or not creds.get('token'):raise RuntimeError('WebSocket credentials unavailable')
    address=urllib.parse.urlsplit(creds['socket'])
    if address.scheme!='wss' or not address.hostname:raise RuntimeError('unexpected websocket address')
    ws=websocket.create_connection(creds['socket'],timeout=15,origin=BASE,http_no_proxy=['*'])
    try:
        ws.send(json.dumps({'event':'auth','args':[creds['token']]}))
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            msg=json.loads(ws.recv());event=msg.get('event');args=msg.get('args') or []
            if event=='auth success':ws.send(json.dumps({'event':'send stats','args':[None]}))
            elif event=='status' and args:return str(args[0]).lower()
            elif event=='stats' and args:
                data=json.loads(args[0]) if isinstance(args[0],str) else args[0]
                if isinstance(data,dict) and data.get('state'):return str(data['state']).lower()
            elif event in ('auth error','daemon error'):raise RuntimeError('websocket auth or daemon error')
        raise RuntimeError('state timeout')
    finally:ws.close()


def ensure_running(sid):
    try: state=real_state(sid)
    except Exception as exc:
        print('  real state unknown:',type(exc).__name__,'; no blind start',flush=True);return False
    print('  real state',state,flush=True)
    if state=='running':return True
    if state not in ('offline','stopped','starting'):
        print('  unexpected state; no blind start',flush=True);return False
    if state!='starting':
        body=json.dumps({'id':sid,'signal':'start'}).encode()
        req=urllib.request.Request(BASE+'/api/pelican/power',data=body,method='POST',headers={'User-Agent':UA,'Content-Type':'application/json','Accept':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=20) as r: print('  start HTTP',r.status,'; will verify state',flush=True)
        except urllib.error.HTTPError as exc: print('  start HTTP',exc.code,'; will verify state',flush=True)
        except Exception as exc: print('  start uncertain:',type(exc).__name__,'; will verify state',flush=True)
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        time.sleep(min(10, max(0, deadline-time.monotonic())))
        if time.monotonic()>=deadline: break
        try:
            state=real_state(sid);print('  recheck',state,flush=True)
            if state=='running':return True
        except Exception as exc: print('  state check failed',type(exc).__name__,flush=True)
    return False


def main():
    if not EMAIL: print('missing COALBYTE_EMAIL');return 2
    try:
        obj=read_json(BASE+'/api/pelican/servers?'+urllib.parse.urlencode({'email':EMAIL}))
        if not obj.get('success') or not obj.get('userFound'):raise RuntimeError('account lookup failed')
        owned={x.get('identifier') for x in obj.get('servers',[]) if isinstance(x,dict)}
        sb,key=discover()
    except Exception as exc:
        print('initial check failed',type(exc).__name__,str(exc)[:100]);return 2
    all_ok=True
    for sid in SERVERS:
        if sid not in owned:
            print(sid,'not in account');all_ok=False;continue
        try: renewed=renew_one(sb,key,sid,EMAIL)
        except Exception as exc: print(sid,'renewal check failed',type(exc).__name__);renewed=False
        try: running=ensure_running(sid)
        except Exception as exc: print(sid,'power check failed',type(exc).__name__);running=False
        print(sid,'renewal_check',renewed,'running_verified',running,flush=True)
        all_ok=all_ok and renewed and running
    return 0 if all_ok else 2

if __name__=='__main__':sys.exit(main())
