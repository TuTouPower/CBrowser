# p036 t026 终态去重 key 释放改前缀清除（防御性硬化）

- 来源：t026 遗留（t026_code_f016，Round 5 code review minor）
- 内容：Supervisor core 在权威观测恢复时释放 error 锁存并 discard 终态去重 key `(profile, instance, bound_version)`；回落分支写 key 时 config_version 可 fallback 到 session 版本、释放时 bound_version fallback 到标签版本，来源不对称。当前 API 契约下（内部 runtime 端点 config_version 必填、session/标签版本同源于启动版本）两者恒等、漏清不可达，Round 5 已判 PASS 不阻断。硬化方向：discard 改为按 `(profile, instance)` 前缀清除全部版本 key（与 forget_instance_events 同构），消除未来契约演化时的复发面；改后补一条「rt 缺 config_version 且标签版本≠session 版本」的回归测试。
- 处理：main@0dd5df8；resolution=resolved；reason=已实现并回归：p035 抽 _watch_network_events 并补停机竞态测试；p036 释放点按 (profile, instance) 前缀清除终态去重 key 并补版本不对称回归测试
