# CoalByte — 独立只读调查

此分支只包含调查脚本与测试，不含自动任务，不含密钥。参考项目通过 Supabase anon key 直接更新 `server_renewals`，并跳过非 active 记录；本站官方续期曾要求 Turnstile，直写可能不符合站点规则。

`COALBYTE_EMAIL=... python3 coalbyte_probe.py` 仅通过面板清单与 Supabase GET 检查用户的两台服务器；不会发送 PATCH、续期、解除挂起或启动。不会因 HTTP 200 就判断续期成功。账号邮箱通过环境变量传入；anon key 仅在内存从公开页面发现。

参考方案不能直接套用到已挂起且记录无邮箱的 Minecraft 服务器：它会跳过非 active 行，默认 5 天也与此前 Minecraft 约 90 分钟的续期行为不一致。Bot 尚未进入最后 48 小时，不能提前续。具体如何安全解除挂起及实际延长期尚待确认。

单元测试：`python3 -m unittest -v test_coalbyte_probe`
