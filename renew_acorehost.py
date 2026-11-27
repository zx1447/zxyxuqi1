#!/usr/bin/env python3
"""AcoreHost 独立续期检查：站点窗口、到期复查与启动状态核验。

每台只计一次；不能续也检查并尝试启动。starting 不等于 running。
接口未暴露计划到期时，沿用站点曾返回的最后 8 小时限制，
续期返回成功后若不能核对到期日期则明确报错，不作成功结论。
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = os.environ.get("ACORE_BASE", "https://dash.acorehosting.com").rstrip("/")
# 使用 Actions Secret；保留现有 API key 回退以兼容原配置。
KEY = os.environ.get(
    "ACORE_API_KEY",
    "c7sp_xLaU1QmpQq5IX1apkfOZ2PVW8IXwgHsUgYqLm6LwA9F").strip().strip("'\"").strip()

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0")

EXT = "/api/client/extensions/dev.sqidgeon.serverplans"


class AuthError(Exception):
    pass


def log(msg):
    print(msg, flush=True)


def req(path, method="GET", body=None, retries=3):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for i in range(retries):
        r = urllib.request.Request(url, data=data, method=method, headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {KEY}",
        })
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                return e.code, (json.loads(raw) if raw else {})
            except Exception:  # noqa: BLE001
                return e.code, {"raw": raw[:300]}
        except Exception as e:  # noqa: BLE001
            last = e
            log(f"  [网络重试 {i + 1}/{retries}] {type(e).__name__}: {e}")
            time.sleep(2 + i * 2)
    raise last


def errmsg(d):
    if isinstance(d, dict):
        e = d.get("errors")
        if isinstance(e, list) and e:
            return str(e[0])
        return str(d.get("message") or d.get("error") or d)
    return str(d)


# 单服只计一次；只有 confirmed running 才算运行成功。
POWER_WAIT = 90


def get_state(uuid):
    try:
        code, d = req(f'/api/client/servers/{uuid}/resources', retries=1)
        r = d.get('resources') or {} if isinstance(d, dict) else {}
        if code != 200 or not isinstance(r, dict):
            return '?', 0, 0
        return str(r.get('state') or '?').lower(), r.get('uptime') or 0, round((r.get('memory_bytes') or 0) / 1048576)
    except Exception:
        return '?', 0, 0


def get_details(uuid):
    try:
        code, data = req(f'/api/client/servers/{uuid}', retries=1)
        if code == 200 and isinstance(data, dict):
            return data.get('server') or {}
    except Exception:
        pass
    return {}


def expiry_from(server):
    """只接受明确的计划到期字段；不猜 created/updated/节点运行时间。"""
    from datetime import datetime, timezone
    if not isinstance(server, dict):
        return None
    candidates = []
    for key in ('expires_at', 'expiry_at', 'expiration_date', 'expiresAt', 'plan_expires_at', 'plan_expiry'):
        if server.get(key) is not None:
            candidates.append(server[key])
    for key in ('plan', 'server_plan', 'serverplans', 'renewal'):
        nested = server.get(key)
        if isinstance(nested, dict):
            for field in ('expires_at', 'expiry_at', 'expiration_date', 'expiresAt'):
                if nested.get(field) is not None:
                    candidates.append(nested[field])
    for value in candidates:
        try:
            if isinstance(value, (int,float)) and not isinstance(value,bool):
                stamp = float(value)
                if stamp > 1e11: stamp /= 1000
                if 946684800 < stamp < 4102444800: return stamp
            if isinstance(value,str):
                parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
                if parsed.tzinfo is not None: return parsed.astimezone(timezone.utc).timestamp()
        except (ValueError, OverflowError):
            pass
    return None


def status_summary(state, uptime, memory):
    log(f'  📊 实际资源状态: {state} | uptime={uptime/3600000:.1f}h | 内存={memory}MB')


def wait_running(uuid, seconds=POWER_WAIT):
    final = '?'
    for i in range(max(1, seconds // 10)):
        time.sleep(10)
        final, uptime, mem = get_state(uuid)
        log(f'  运行复查 {(i+1)*10}s: {final}')
        if final == 'running': return True
    return False


def ensure_running(uuid, listed_suspended):
    state, uptime, mem = get_state(uuid)
    status_summary(state, uptime, mem)
    if state == 'running' and not listed_suspended:
        log('  ✅ 已确认 running')
        return True
    if state == 'starting':
        log('  ⏳ starting 不是 running，先短暂复查')
        if wait_running(uuid, 30): return True
    # 即使续期失败或未到窗口，也尝试启动；不发送 restart/stop。
    if listed_suspended:
        try:
            code, body = req(f'{EXT}/storage/start', method='POST', body={'server':uuid}, retries=1)
            log(f'  storage/start HTTP {code}')
            if code in (200,204) or 'storage transfer' in errmsg(body).lower():
                if wait_running(uuid): return True
        except Exception as e:
            log(f'  ⚠️ storage/start 异常: {type(e).__name__}')
    try:
        code, _ = req(f'/api/client/servers/{uuid}/power', method='POST', body={'signal':'start'}, retries=1)
        log(f'  power/start HTTP {code}，以状态复查为准')
    except Exception as e:
        log(f'  ⚠️ power/start 异常: {type(e).__name__}')
    if wait_running(uuid):
        log('  ✅ 已确认 running')
        return True
    log('  ❌ 不能确认服务器 running')
    return False


def renew_server(uuid, old_expiry):
    # 此站历史实测 422 提示仅最后 8 小时开放，保留原站点窗口判断。
    # 如果能获取可信到期时间，再明确执行用户最后 48 小时策略。
    if old_expiry is not None and old_expiry - time.time() > 48*3600:
        log('  ⏳ 剩余超过 48 小时，本轮不续期')
        return True, 'not_due'
    if old_expiry is None:
        log('  ⚠️ 计划到期时间不可读；沿用站点服务端续期窗口，但无法独立验证 48 小时门槛')
    try:
        code, data = req(f'{EXT}/renew', method='POST', body={'server':uuid}, retries=1)
    except Exception as e:
        log(f'  ❌ 续期请求异常: {type(e).__name__}')
        return False, 'error'
    msg = errmsg(data)
    if code == 422 and 'renewal is available when less than 8 hours remain' in msg.lower():
        log('  ⏳ 站点返回未到续期窗口')
        return True, 'not_due'
    if code != 200 or not isinstance(data,dict) or data.get('renewed') is not True:
        log(f'  ❌ 续期未确认: HTTP {code}, {msg[:150]}')
        return False, 'error'
    log('  ⏳ 续期接口报告 renewed=true，正在复核计划到期时间')
    time.sleep(3)
    new_expiry = expiry_from(get_details(uuid))
    if old_expiry is None or new_expiry is None:
        log('  ❌ 到期时间不可读，无法核实续期是否生效')
        return False, 'unverified'
    if new_expiry <= old_expiry:
        log('  ❌ 到期时间未延后，续期未核实')
        return False, 'unverified'
    log(f'  ✅ 已核实到期时间后移: {old_expiry:.0f} → {new_expiry:.0f}')
    return True, 'renewed'


def inspect_server(server):
    uuid = server.get('uuid')
    if not isinstance(uuid,str) or not uuid:
        log('❌ 服务器 ID 缺失')
        return False, ('—',server.get('name','?'),'❌','缺 ID')
    name=server.get('name','?');suspended=server.get('is_suspended') is True
    log(f'-- [{uuid[:8]}] {name} | suspended={suspended} --')
    old_expiry = expiry_from(get_details(uuid)) or expiry_from(server)
    renew_ok, renew_state = renew_server(uuid, old_expiry)
    if suspended and renew_state not in ('renewed','unverified'):
        try:
            code, data = req(f'{EXT}/restore', method='POST', body={'server':uuid}, retries=1)
            log(f'  restore HTTP {code}（将继续核实启动状态）')
        except Exception as e:
            log(f'  ⚠️ restore 异常: {type(e).__name__}')
    latest = get_details(uuid)
    if isinstance(latest.get('is_suspended'), bool):
        suspended = latest['is_suspended']
    try:
        running = ensure_running(uuid, suspended)
    except Exception as e:
        log(f'  ❌ 运行状态检查异常: {type(e).__name__}')
        running = False
    ok = renew_ok and running
    return ok, (uuid[:8], name, '✅' if ok else '❌', f'续期={renew_state}, running={running}')


def pass_once():
    try:
        code, data = req('/api/client/servers', retries=1)
    except Exception as e:
        log(f'❌ 无法读取服务器清单: {type(e).__name__}')
        return 0,0,[]
    if code != 200 or not isinstance(data,dict):
        log(f'❌ 服务器清单 HTTP {code}')
        return 0,0,[]
    servers=(data.get('servers') or {}).get('data') or []
    if not isinstance(servers,list) or not servers:
        log('❌ 未发现服务器')
        return 0,0,[]
    results=[]
    for server in servers:
        try:
            results.append(inspect_server(server))
        except Exception as e:
            log(f'❌ 单服检查异常: {type(e).__name__}')
            results.append((False,('—','—','❌','单服检查异常')))
    return sum(bool(ok) for ok,_ in results),len(servers),[row for _,row in results]


def main():
    if not KEY:
        log('❌ 缺少 ACORE_API_KEY')
        return 3
    ok,total,rows=pass_once()
    log(f'单服综合通过 {ok}/{total}')
    return 0 if total>0 and ok==total else 2


if __name__=='__main__':
    sys.exit(main())
