# AcoreHost

源代码独立在 `acorehost` 分支；main `.github/workflows/renew_acorehost.yml` 每 6 小时执行，无自派发。

- 每台服务器只计算一次综合结果，续期和运行状态都应核实。
- 仅 `running` 算运行成功；`starting` 先等待，再尝试 start，复查仍未 running 则失败。
- 已知计划到期时间在 48 小时外时不续；无法读到期时间时沿用站点原有服务端续期窗口（历史返回只在最后 8 小时开放），但无法独立确认这一门槛是否一直有效。
- 接口报告 `renewed=true` 后对比前后到期时间，读不到或没推迟则明确失败，不能将 HTTP 200 当成续期成功。
- 即使续期无法完成，也尽力检查并启动；会核实实际状态。
- 当前 AcoreHost API 暂未找到可读计划到期时间的接口。需要找到该接口才能独立核验 48 小时窗口及续期结果。
- 账号 API key 用现有 Actions Secret。
