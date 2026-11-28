# MineLy keepalive

独立分支只管理 MineLy 服务器 AZll。main 中的工作流北京时间每天 09:00（01:00 UTC）运行，单轮上限 6 分钟，不自派发、不轮询驻留。

- 登录账号密码分别存于 GitHub Actions Secrets `MINELY_USERNAME` 与 `MINELY_PASSWORD`，不写入仓库。
- 使用面板登录表单与 CSRF；认证后确认账号首页有目标服务器，然后请求其真实 health 接口。
- running 才算成功；只有明确 offline 才发送一次 `start`。starting / stopping 等待复查；node 离线、安装中、状态未知不盲目启动。
- 即使启动接口返回 200，仍须复查为 running 才成功；请求结果未知不重复发送。
- 单元测试：`python3 -m unittest -v test_minely_keepalive`。真实离线启动需等实际停机时验证，不能通过人为关机测试。
