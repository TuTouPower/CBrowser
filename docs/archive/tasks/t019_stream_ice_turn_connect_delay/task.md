# Task spec

## 背景

切换侧边栏 profile 或刷新会话时，Selkies 页面停留 `Connecting...` 约 5 秒。p020 已定位：Stream entrypoint 启动 Selkies 2.1.0 时沿用其默认外部 STUN/TURN，新 PeerConnection 的 ICE gathering 等待 OpenRelay TURN allocation 超时约 5.003 秒。该行为同时违反 ADR 013：同机媒体应只使用 `127.0.0.1` host 候选，客户端与服务端均不配置 STUN/TURN。

## 契约区

### 范围

- 修正 Stream 运行时的 ICE 配置来源，使新建 PeerConnection 不访问外部 STUN/TURN，仅使用 `127.0.0.1:<udp mux>` host 候选。
- 补足 unit 与真实 Chrome 黑盒测试，覆盖启动参数约束、候选类型、profile 切换与刷新时延。
- 同步 `docs/blueprint/stream_runtime.md` 与 `docs/blueprint/testing.md` 的长期事实与测试要求。

### 非范围

- 不改前端 URL、iframe 路由或 Selkies 客户端适配层。
- 不恢复 coturn、TURN 凭证轮换或 ICE 代次接管；不扩大 ADR 013 的部署包络。
- 不处理 p020 附注中未确认的 capture resume 200ms 重复日志，另立条目。
- 不为 LAN/多主机媒体访问提供新方案。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：Stream 运行时新建 WebRTC 会话的 ICE 配置不包含外部 STUN/TURN 服务器；其 SDP/ICE 候选仅出现 `127.0.0.1:<udp mux>` host 候选，不含 `srflx`、`relay` 或其他主机的候选。
- [x] AC-002：同机真实 Chrome 从点击侧边栏另一个已运行 profile 到媒体帧呈现的耗时不超过 2 秒；同一 profile 刷新重建会话也满足该上限。
- [x] AC-003：unit 门禁能阻止 Stream entrypoint 回退到 Selkies 默认外部 STUN/TURN 配置。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- 全部 AC 可自动测试。

## 上下文区

- 来源：p020（2026-11-03 核实：默认 OpenRelay TURN allocation 超时使 `HELLO`→offer 固定约 5.0s；过滤 TURN 后 0.23s，加 `--webrtc-ice-lite` 后 0.015s）。

### 有意不测

- LAN/多主机访问：ADR 013 当前只保证同机单用户，媒体候选固定 127.0.0.1，不在本 task 扩包络。
- 公共互联网 TURN 可用性：本 task 明确移除该依赖，不测其可达性。
- 未确认的 capture resume 重复日志：与本延迟因果未证实，另立条目。

### 测试策略

- unit：解析 `config/docker/stream_runtime/entrypoint.sh` 与 help/args 装配，断言外部 STUN/TURN 被显式关闭（或等价 ICE-lite 启动参数），并保持现有 dual-mode/file-transfers/clipboard 断言。
- e2e：沿用真实 Browser/Stream 镜像与同机无头 Google Chrome，抓取 offer/ICE 候选，断言仅 host/127.0.0.1；测量切换 profile、刷新到首帧的耗时并断言 ≤2s。
- 回归：确认既有媒体矩阵（多页面、复制标签、可见性暂停/恢复、断线 resume）在 ICE-lite/无 STUN-TURN 下仍通过。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- Selkies 2.1.0 `--webrtc-ice-lite` 与真实 Chrome 的同机媒体连通：已知为启动参数契约，需用 AC-002 的真实 Chrome 黑盒验证；若该参数导致连通失败，回退为显式关闭 TURN（保留/再评估 STUN）并同步调整 AC-001 的候选断言。
- Selkies 默认 STUN/TURN 键值：已在本机 2.1.0 镜像读回（`turn_host=staticauth.openrelay.metered.ca:443`、默认 Google/Cloudflare STUN），非未知。

### 风险与回退

- 风险：ICE-lite 在部分 Chrome/网络组合下可能影响连通；只关闭 TURN 时仍会保留 srflx 公网候选并多约 0.2s；入口参数被测试只做字符串断言，可能与 Selkies 实际解析漂移。
- 回退：若真实 Chrome 在 ICE-lite 下无法建链，改为显式关闭 TURN（必要时连同 STUN）并验证 host 候选仍连通；回退不得恢复外部 TURN 依赖。

### 依赖与约束

- 依赖本机 OrbStack Docker、真实 Browser/Stream 镜像与同机 Google Chrome 黑盒环境（见 `docs/blueprint/testing.md`）。
- Stream 媒体只经 `127.0.0.1:<udp mux>` host 候选；不得引入公网 STUN/TURN 或暴露 srflx 候选。
- 保持现有 Selkies 2.1.0 版本与 Stream 容器网络边界。

### Finalization 时更新的 blueprint

- `docs/blueprint/stream_runtime.md`：把「客户端与服务端均不配置 STUN/TURN」落实到 Stream 启动参数/ICE-lite 的可验证描述。
- `docs/blueprint/testing.md`：补充会话建立时延与候选类型（无 srflx/relay）的黑盒断言要求。
