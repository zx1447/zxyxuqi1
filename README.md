# RKing Industries — 服务器 55

独立分支 `rking`，主分支工作流 `.github/workflows/rking_keepalive.yml` 检出本分支。

- 每 8 小时检查一次：`19 */8 * * *`（UTC），支持手动运行。
- 每轮一次检查，任务上限 6 分钟，不自派发、不串接任务。
- 使用 GitHub Secrets `RKING_USERNAME` / `RKING_PASSWORD` 登录，不将账号密码写入代码。
- 同时读取服务器 55 详情及实时统计；只有两者均 `online` 且统计有运行时长才算成功。
- 两者均 `offline` 时请求一次面板 Start；无论启动请求是否成功，轮询确认实际状态，不能重复盲发。
- `starting`、`crashed` 等过渡状态等待复查，不算在线。状态不一致不盲目启动。
- 即使计划过期也会尝试启动，存储超限时按照面板限制停止操作并报告失败。
- 服务器目前在线；真实离线开机链尚未实测，不会为了测试而关机。
- 本地测试：`python -m unittest discover -v`。
