# GemHost 免费服守护

[panel.gemhost.pl](https://panel.gemhost.pl) 免费 Minecraft 服务器。

## 一句话策略

**停了就启动。** 不做主动续期。

```yaml
cron: '23 */6 * * *'      # 每 6 小时
```

## 为什么不做主动续期

免费会话硬上限 **360 分钟**，而 GitHub cron 的实际派发间隔会被饿到 **~6 小时**：

| 时刻 (UTC) | 实测事件 |
|---|---|
| 11-21 19:12 | cron → offline → 拉起 → 会话至 11-22 01:13 |
| 11-22 01:16 | cron → offline → 拉起 → 会话至 11-22 07:16 |
| 11-22 07:16 | 会话到期停机 |

两轮间隔实测 **6 小时**（我配的是每 3 小时，被饿到 6 小时）。
既然派发间隔 ≈ 会话时长，主动续期只是把停机时刻提前，并不能真正避免停机。

而 `start` **一定**分配一个满额 360 分钟会话 —— 靠 cron 定期兜底拉起最可靠。

## 陷阱：不要用 restart

```
POST /api/servers/<id>/power {"action":"restart"}
```

实测会让服务器变 `offline` 且 `free_session` 变 `None`（**清零，不是重置**），
而且**不会自己起来**。这个坑之前踩过，已从脚本中彻底移除。

## API

```
POST /api/auth/login            {"email","password"}  → gemhost_access(JWT,7天) + gemhost_csrf
GET  /api/servers/list                                名下全部服务器
GET  /api/servers/<id>/status                         status / is_suspended / free_session
POST /api/servers/<id>/power    {"action":"start"}    拉起 = 新满额 360min 会话
```

变更类请求需带 `X-CSRF-Token: <gemhost_csrf cookie 值>`。

## 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `GEMHOST_EMAIL` | ✅ | 登录邮箱 |
| `GEMHOST_PASSWORD` | ✅ | 密码 |
| `GEMHOST_BASE` | — | 默认 `https://panel.gemhost.pl` |
| `WAKE_SECONDS` | — | 单轮内复查间隔，默认 60 |

## 退出码

`0` 正常/拉起成功 · `2` 有失败 · `3` 登录失败
