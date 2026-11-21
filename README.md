# bkt（BlackHost）自动续期 + 自动启动

[dash.blackhost.pl](https://dash.blackhost.pl) 免费 Minecraft 服务器。

## 规则

| 项 | 值 |
|---|---|
| 单次续期 | **+8 小时** |
| 续期窗口 | 到期前 **2 小时**开放 |
| 过期后 | 暂停但保留，`deleteAfter` 前可救回 |

## 关键接口

```
GET  /api/v1/servers/game/free/status        会话状态 + canRenew
POST /api/v1/servers/game/free/renew         {"turnstileToken":"..."}  需过 Turnstile
GET  /api/v1/servers/game/{数字ID}/stats     运行状态（running/offline/starting）
POST /api/v1/servers/game/{数字ID}/power     {"action":"start"}  → 204
```

⚠️ `{数字ID}` 是 **1188**，不是 uuid `d7351490`。

## 两条通道

| 通道 | 续期 | 电源 | 说明 |
|---|---|---|---|
| `BH_PAT`（API key） | ❌ `apiKeyActionForbidden` | ✅ | 站点明令禁止用 key 续期 |
| `BH_COOKIE`（浏览器会话） | ✅ 需 Turnstile | ✅ | 唯一能续期的路 |

## 续期方案

`BH_SOLVER=browser` + `BH_PROXY=1`：

```
家宽订阅 → xray SOCKS5 → 住宅 IP
  → undetected-chromedriver
  → pyautogui 点 Turnstile 复选框
  → POST /renew → +8h
```

## 续期后自动启动

`BH_AUTO_START=1`（默认开）：续期成功后、以及每次巡检时，都会检查
`/stats` 的 `status`，若是 `stopped`/`offline` 就发 `/power {"action":"start"}`。

## 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `BH_COOKIE` | ✅ | `__Secure-better-auth.session_token=...` |
| `BH_PAT` | 启动用 | `bh_pat_...`，用于读状态和启动 |
| `BH_SERVER_ID` | — | 数字 id，默认 `1188` |
| `BH_SOLVER` | — | `browser` / `capsolver` / `2captcha` / `manual` |
| `BH_PROXY` | — | `1` 强制家宽，`0` 直连，`auto` 默认 |
| `BH_AUTO_START` | — | `0` 关闭自动启动 |

## 已修的 bug

1. `preexec_fn=os.setsid` → xray 以 exit 23 退出，改 `start_new_session=True`
2. `geoip:private` 缺 `geoip.dat` → 改内网 CIDR 字面量
3. Chrome 版本不匹配 → `version_main` 需与浏览器一致
