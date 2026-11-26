#!/usr/bin/env python3
"""CoalByte Minecraft 专项：每小时检查，最后一小时续期，并检查真实电源状态。"""
import sys
import time
import urllib.parse
import renew_coalbyte as cb

RENEW_WINDOW_SECONDS = 3600


def maintain(ident, name, listed_exp):
    print(f'-- [{ident}] {name} --', flush=True)
    ok = True
    try:
        direct = cb.req(f'{cb.BASE}/api/pelican/renew?' + urllib.parse.urlencode({'id': ident}), retries=1)
        direct_exp = direct.get('expiresAt')
        expiry = cb.as_timestamp(direct_exp)
        if direct.get('success') is not True or expiry is None:
            raise RuntimeError('单服续期状态无效')
        remaining = expiry - time.time()
        print(f'单服到期 {direct_exp} · 剩余 {remaining/60:.1f} 分钟 · 列表到期 {listed_exp}', flush=True)
        if remaining <= RENEW_WINDOW_SECONDS:
            if direct.get('canRenew') is False:
                print('❌ 站点不允许续期，仍会尝试启动', flush=True)
                ok = False
            else:
                result = cb.renew(ident, cb.EMAIL, 'minecraft')
                if result.get('success') is not True:
                    print(f"❌ 续期失败: {result.get('error') or '接口未确认成功'}", flush=True)
                    ok = False
                else:
                    verified, detail = cb.verify_renewal(ident, direct_exp, result)
                    if verified:
                        print(f'✅ 两处记录核验通过，新到期 {detail}', flush=True)
                    else:
                        print(f'❌ 续期记录未核验: {detail}', flush=True)
                        ok = False
        else:
            print('⏳ 尚未进入最后一小时，不重复续期', flush=True)
            listed_t = cb.as_timestamp(listed_exp)
            if listed_t is None or abs(listed_t - expiry) > 5:
                print('❌ 服务器列表与单服到期时间不一致', flush=True)
                ok = False
    except Exception as exc:
        print(f'❌ 续期检查失败: {type(exc).__name__}', flush=True)
        ok = False
    # 即便续期失败或未到窗口，也尝试启动；不只相信 HTTP 200。
    if not cb.ensure_running(ident):
        ok = False
    return ok


def main():
    if not cb.EMAIL:
        print('❌ 缺少 COALBYTE_EMAIL，无法安全发现名下 Minecraft 服务器', flush=True)
        return 3
    try:
        rows = [r for r in cb.discover() if r[4] == 'minecraft']
    except Exception as exc:
        print(f'❌ 无法发现服务器: {type(exc).__name__}', flush=True)
        return 3
    if not rows:
        print('❌ 名下未发现 Minecraft 服务器，请人工检查', flush=True)
        return 3
    results = []
    for ident, name, exp, _, _ in rows:
        results.append(maintain(ident, name, exp))
    print(f'确认正常 {sum(results)}/{len(results)}', flush=True)
    return 0 if all(results) else 2


if __name__ == '__main__':
    sys.exit(main())
