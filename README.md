# Ajolote 续期（axolotl）

[ajolote.lat](https://ajolote.lat) 免费 Minecraft 服务器续期。

## 规则

看 40 秒广告换续期时长。

## 文件

| 文件 | 说明 |
|---|---|
| `renew_ajolote.py` | 续期脚本 |
| `ajolote_state.json` | 会话 / 状态缓存 |

## 环境变量

| 变量 | 说明 |
|---|---|
| `AJOLOTE_EMAIL` | 登录邮箱 |
| `AJOLOTE_PASSWORD` | 密码 |

## 运行

```bash
python3 renew_ajolote.py          # 正常续期
python3 renew_ajolote.py --force  # 强制（无视窗口）
```

workflow 在 `main` 分支（`.github/workflows/ajolote_renew.yml`），cron `7 */6 * * *`。
