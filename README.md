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
