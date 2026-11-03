# d019 coturn 本机中继须明确实际 relay 地址与映射

- 来源：t004 真实 Mac Chrome / OrbStack Browser03 / Stream07 / coturn 独立验证。
- 结论：隔离本机测试使用真实容器 relay-ip，并显式配置 external-ip=127.0.0.1/容器地址；relay-ip=0.0.0.0 配单一 external-ip 的旧量具虽能分配，却在 CREATE_PERMISSION/CHANNEL_BIND 403，不能据此判定生产 ICE 适配失败。相同镜像与代码仅更正映射后，新代实际接管。
- 版本差异：coturn 4.6.3 启用 allow-loopback-peers 且无 CLI 密码时拒绝启动，隔离夹具须 no-cli；4.18 默认 CLI 行为不同。未知 no-ip-check 参数未采纳。该 loopback 配置只限隔离测试，不是公网部署建议。
- 验证：固定 arm64 coturn/coturn:4.6-alpine 的实际不可变镜像 e2bca2f79a4269d7240de5872ab60a9305013ad37296d2acf14f9510874346be，Root正式完整E2E PASS96.13秒；独立冻结候选 PASS96.58秒。连续generation2/3/4均先精确commit、旧close+sendreject，再验证新ufrag双relay与重新采样的帧/音频/pair字节增长，同PC/DTLS/Track不变。
- 负例：独立服务端错误HMAC导致真实401/无fresh offer，客户端错误HMAC导致真实401/无新代commit；pytest分别非零。旧connected不能使轮换假绿。
- 证据：tests/fixtures/stream_probe/chrome_relay.py、tests/e2e/test_stream_runtime_e2e.py；独立validation worktree的.scratch/t004_relay_independent/results.json与retained_evidence/{positive,server,client}/。后续t006/t012沿实际可达地址与代栅栏复验，公网/原生x86未测。
- 现状：有效。

- 后续（t024 文档收敛）：本条所述 TURN/ICE 代次机制已由 ADR 013（同机直连，见 docs/blueprint/decisions.md）整体删除；本条仅作历史实验事实保留，不再构成现行实现或验收要求，文中指向未来 task 的指令已失效。
