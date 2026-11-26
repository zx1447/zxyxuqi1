# Rellact

- 控制台： https://console.rellact.xyz/
- AFK 页面： https://console.rellact.xyz/billing/rewards/afk
- 账号与密码保存在 GitHub Actions Secrets `RELLACT_EMAIL`、`RELLACT_PASSWORD`，不写入代码或日志。
- 此分支是独立干净分支；仓库有手动单次测试工作流，没有定时任务。

## 站点公开信息（2026-11-26）

- AFK 页面描述：打开页面时进行验证并保持页面打开；积分每隔几分钟进入团队钱包，具体奖励及上限以账号页面为准。
- 当前登录与 AFK 可能需要 ALTCHA 验证，能否使用账号尚未验证。
- 官方服务条款第 7 节禁止使用脚本或自动化刷积分或奖励，违反可能导致积分移除、服务器暂停或账号关闭： https://rellact.xyz/terms/
- main 有仅手动触发的单次浏览器测试 `.github/workflows/rellact_test.yml`；站点条款禁止自动刷奖励，未配置定时挂机。
- GitHub Actions 直连测试时登录页 Cloudflare 返回 403，尚未验证登录或余额。

## 纯 HTTP 诊断（尚未配置定时挂机）

- `rellact_afk.py`：按站点 ALTCHA 协议完成验证，登录后读取今日 AFK 累计和钱包余额，再 start、按网页的 30 秒间隔 heartbeat、复核累计，并 stop。
- workflow 位于 main 的 `.github/workflows/rellact_http_test.yml`，仅手动触发。
- GitHub runner 直连安全验证接口返回 HTTP 403，尚未完成登录或到账验证。站点邮箱登录在本地新出口返回邮箱二次验证，不能自动完成。
- 可选 Secret `RELLACT_SESSION_TOKEN` 可用于已有站点会话，但会话有效期及能否从 GitHub 出口使用尚未验证；会话凭据不得贴到公开代码或日志。
- 尚未部署定时挂机；服务条款禁止脚本刷奖励。
