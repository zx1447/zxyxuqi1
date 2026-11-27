# BlackFlame Studio

独立分支仅包含 BlackFlame 脚本和测试；任务从 main 的 `.github/workflows/checkin_blackflame.yml` 检出 `blackflame`。

- 使用现有 Discord Secret `BFLAME_DISCORD_TOKEN`；直连不可达时沿用原有 Cloudflare WARP。
- 启动前从已登录 dashboard 的 JS 中提取当前 `startAdWatch` 和 `verifyAndRewardAdWatch` 的 Server Action ID；缺失或冲突则停止，不使用旧 ID。
- 只重试只读 GET；POST 不重试，避免超时后重复领取。响应异常时结束任务并显式报错。
- 每轮必须同时看到领取成功响应和账号余额相对本轮开始增加才算核实；并发扣费可能掩盖到账，此时报告未核实，不能据此断言没有奖励。
- 这是已有的站点 Server Action 交互，不证明实际播放过广告。
- 保持既有 6 小时 cron 和 15 分钟单轮上限；无自派发或 job 接力。
- 测试 `python -m unittest discover -v`。运行 `BFLAME_RUN_MINUTES=0 BFLAME_WATCHES=1 python checkin_blackflame.py` 将执行一次真实领奖。
