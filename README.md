# BotStable 自动续期

[botstable.eu](https://botstable.eu/renew) 免费服务器续期。

## 规则（站点 API 实测）

| 项 | 值 | 含义 |
|---|---|---|
| `period_hours` | **120** | 每续一次重置为 5 天 |
| `window_hours` | **48** | 剩余 ≤48 小时才能点续期 |
| `keep_days` | **7** | 过期后挂起保留 7 天，期间续期可恢复 |

⚠️ **续期是「重置为 now + 5 天」，不是累加。** 早续会白白损失剩余时间。

## 运行节奏（精准续期）

`cron: '23 */5 * * *'` —— 每 5 小时检查一次。

**精准续期逻辑：**

1. 每次运行先读 `opens_at`（窗口开放时刻）
2. 如果距离开放 **≤9 分钟**，脚本原地等待，卡在开放瞬间立刻续期
3. 如果超过 9 分钟，本轮不等待、直接跳过，交给下一次 cron

因为 cron 每 5 小时一次，而窗口开放后到真正到期还有 48 小时，
必然会有一次 cron 落在「开放前 9 分钟内」，那一次就会精准续上。

**为什么不能提前续**：续期是把计时器重置为 `now + 120h`，不是累加。
早续一次就白丢剩余时间。所以脚本严格禁止在 `can_renew=false` 时续期
（除非手动 `force=true`）。

## 登录方式

Discord OAuth（PKCE），用 Discord token 自动批准：

```
GET  /api/renew/login            → 302 到 Discord（带 code_challenge + state Cookie）
POST discord.com/oauth2/authorize → {"permissions":"0","authorize":true,"integration_type":0}
GET  /api/renew/callback?code=…  → 建立 __Host-renew 会话
GET  /api/renew/servers          → 服务器列表（含 can_renew / opens_at / expires_at）
POST /api/renew/renew            → {"server_id": 5}
```

## Secret

| 名称 | 说明 |
|---|---|
| `BOTSTABLE_DISCORD_TOKEN` | Discord 账号 token（`MTxx...` 格式） |

## 错误码

| HTTP | 含义 | 脚本处理 |
|---|---|---|
| 200 | 续期成功 | 打印新到期时间 |
| 409 `not_open_yet` | 还没到 48h 窗口 | 正常跳过，退出码 0 |
| 403 `deadline_missed` | 保留期已过 | 报错，需人工找管理员 |
| 404 | 服务器不在该账号 | 报错 |
| 429 | 请求过频 | 本轮跳过 |
