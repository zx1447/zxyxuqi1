# RKing Industries — 独立分支（待登录）

目标：https://rkingindustries.com/minecraft/panel?server=55

## 需求

每 8 小时检查指定服务器 55；只有确认停机时尝试启动，并复查实际状态，starting 不算 running。单轮不超过 15 分钟；不自派发，不影响其他服务。

## 当前情况

- 该分支为无父提交的干净独立分支；尚未实现或启用定时任务。
- 网站登录接口返回 HTTP 401 / Invalid credentials，不能判断哪一项有误。不得反复尝试或猜测密码。
- 用户名和密码仅放 GitHub Actions Secrets：`RKING_USERNAME`、`RKING_PASSWORD`。
- 登录成功后，需要只读核查服务器 55 的控制接口和状态字段，再实现状态检查与停机启动；不能把 HTTP 200 或 starting 当作已运行。
- 等用户确认账号密码并更新 Secret 后再测试，当前无成功登录及有效启动验证。
