# DragonHost 续期（dragonhost）

DragonHost 免费 Minecraft 服务器续期。

## 规则

**仅最后一天可续。**提前会失败。

## 文件

| 文件 | 说明 |
|---|---|
| `renew_dragonhost.py` | 续期脚本 |
| `dragonhost_state.json` | 状态缓存 |

## 环境变量

| 变量 | 说明 |
|---|---|
| `DRAGONHOST_EMAIL` | 登录邮箱 |
| `DRAGONHOST_PASSWORD` | 密码（**不带尾 Y**，注意与 GemHost 相反） |
| `DRAGONHOST_SESSION_KEY` | 会话加密 key |

## 运行

```bash
python3 renew_dragonhost.py
```

workflow 在 `main` 分支（`.github/workflows/renew_dragonhost.yml`），cron `37 */6 * * *`。
