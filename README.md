# CoalByte — 独立分支

代码独立存于 `coalbyte` 分支；main 中的工作流每 6 小时检查一次，每轮最多 15 分钟，不自派发。邮箱使用 `COALBYTE_EMAIL` Secret。仅处理用户账户清单中且在脚本明确列出的两台服务器。

- 参考 `guanxi660-crypto/coalbyte-renew` 从公开页面发现 Supabase anon key；Bot 的记录邮箱匹配、状态 active、可读真实到期且剩余不超过 48 小时时才考虑直接 PATCH 到期时间到当前时间加 5 天。先要求站点接口与数据库的状态和旧到期一致；条件写入防并发覆盖。发送一次 PATCH，不自动重试。
- PATCH 后要重新读取数据库和站点续期查询接口，确认新到期值一致且大于旧值，才报告续期已核实。数据库变更并不保证后台其他动作完成。
- Minecraft 记录目前 `suspended` 且邮箱为空；参考方法没有对应记录且不支持挂起服，脚本不会猜它的状态或直接写入。即便记录以后变成 active，也不会使用 Bot 的 5 天规则，需确认该计划的续期办法。
- 不论是否续期，均通过 Wings WebSocket 查询实际状态。offline/stopped 时尝试 start 并复查；starting 等过渡状态不重复启动；无法读取真实状态时不盲目发送启动。只有 running 才算运行核实。
- 测试：`python3 -m unittest -v test_coalbyte_probe test_coalbyte_renew`；手动运行需安装 `websocket-client`。`coalbyte_probe.py` 始终只读。
- 目前真实 PATCH 续期尚未实测：Bot 超过 48 小时、Minecraft 不符合条件。站点曾要求 Turnstile；绕过常规流程可能违反其规则或停止工作。
