#!/usr/bin/env python3
"""Read-only CoalByte renewal feasibility check; never patches the database."""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = 'https://coalbyte.com'
SERVERS = {'c3f65fbb': 'Minecraft', '6995c463': 'Discord Bot'}
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'


def get(url, headers=None):
    req = urllib.request.Request(url, headers={'User-Agent': UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''


def discover():
    code, html = get(BASE + '/en/dashboard/server')
    if code != 200: raise RuntimeError('dashboard HTTP ' + str(code))
    chunks = set(re.findall(r'/_next/static/chunks/[^"\\\s]+\.js', html))
    pattern = re.compile(r'https://([a-z0-9]{15,})\.supabase\.co"\s*,\s*"(eyJ[A-Za-z0-9_\-\.]{80,})"')
    configs = set()
    for path in chunks:
        code, js = get(BASE + path)
        if code == 200:
            configs.update(pattern.findall(js))
    if len(configs) != 1:
        raise RuntimeError('no unique Supabase configuration')
    project, key = configs.pop()
    return 'https://' + project + '.supabase.co', key


def date(value):
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo is not None else None
    except (ValueError, TypeError): return None


def decision(row, email, now):
    if not isinstance(row,dict): return 'NO_RECORD'
    if (row.get('user_email') or '').lower() != email.lower(): return 'EMAIL_MISMATCH_OR_MISSING'
    if row.get('status') != 'active': return 'NOT_ACTIVE'
    expiry = date(row.get('expires_at'))
    if expiry is None: return 'EXPIRY_UNKNOWN'
    if (expiry - now).total_seconds() > 48 * 3600: return 'TOO_EARLY'
    return 'IN_WINDOW'


def main():
    email = os.environ.get('COALBYTE_EMAIL', '').strip()
    if not email: print('ERROR missing COALBYTE_EMAIL'); return 2
    q=urllib.parse.urlencode({'email':email})
    code,raw=get(BASE+'/api/pelican/servers?'+q)
    if code!=200: print('ERROR server list HTTP',code); return 2
    obj=json.loads(raw)
    if not obj.get('success') or not obj.get('userFound'): print('ERROR account not found'); return 2
    owned={s.get('identifier') for s in obj.get('servers',[]) if isinstance(s,dict)}
    url,key=discover()
    h={'apikey':key,'Authorization':'Bearer '+key,'Accept':'application/json'}
    for sid,kind in SERVERS.items():
        if sid not in owned:
            print(sid,kind,'NOT_IN_ACCOUNT');continue
        q=urllib.parse.urlencode({'select':'server_id,user_email,status,expires_at,last_renewed_at','server_id':'eq.'+sid})
        status,raw=get(url+'/rest/v1/server_renewals?'+q,h)
        if status!=200: print(sid,kind,'DB_READ_HTTP',status); continue
        rows=json.loads(raw)
        if not isinstance(rows,list) or len(rows)!=1: print(sid,kind,'ROW_COUNT',len(rows) if isinstance(rows,list) else '?');continue
        row=rows[0]
        print(sid,kind,'status',row.get('status'),'expires',row.get('expires_at'),'result',decision(row,email,datetime.now(timezone.utc)))
    print('READ ONLY: no renewal, status change, or power request sent')
    return 0

if __name__ == '__main__': sys.exit(main())
