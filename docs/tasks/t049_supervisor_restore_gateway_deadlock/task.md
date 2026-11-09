# Task spec

## 背景

部署升级（`docker compose up -d` 重建 Gateway 与 Supervisor）后，存在 desired=running 的存量 Profile 时，部署卡在 `verify_readiness`，满 300s 超时；Profile 诊断持续为 `session_instance_mismatch`、`gateway_not_attached_at_fixed_endpoint`、`policy_unverifiable`、`agent_not_registered`。2026-11-10 核对代码确认环形依赖：

1. 重建后的 Gateway 只连接主干网络，不在存量 Profile 的媒体网络 `cbrowser-net-{profile_id}` 上；Stream Agent 连不上固定端点，无法注册。
2. Supervisor 重启后 `_sessions` 为空。`scan_and_reconcile_existing` 恢复存量沙箱时，在实例化 `ActiveSession` 前调用 `gateway_control.has_foreground_viewers`；Agent 未注册时 Gateway visibility 返回 503，捕获 `httpx.HTTPError` 后直接 `return`（`supervisor/core.py` 恢复分支）。该调用返回值未被使用，只起阻断作用；源自 `3b5576e` 初版。
3. API 在线时，Gateway 重新接入媒体网络只发生在 `_converge_session`（要求已有 session）与 Stream-only 替换中；`_recover_attachment_offline` 仅在 API 不可达时调用。无 session 则永不重新挂载，死锁闭合。

只重启 Gateway 时 Supervisor 仍持有 session，`_converge_session` 能重新挂载；两者同时重建（即部署升级）才触发。现有单元/集成测试把 `has_foreground_viewers` 打桩为直接返回值，从未覆盖 503；E2E 全为冷启动，无带载升级场景。

按核心架构铁律根治：基础设施拓扑收敛（媒体网络挂载）不得依赖上层业务可见性状态，也不得依赖 Supervisor 内存 session 是否存在。

## 契约区

### 范围

- 删除存量沙箱恢复路径中 `has_foreground_viewers` 前置阻断（及仅为其服务的 `gateway_control is None` 抛错）；实例一致性仍由容器 label 与 API fence 保证，Agent 注册状态由 `_converge_session` 的 `agent_registered` 判定。
- 恢复为确定性单向流程：label/instance/API fence 校验 → policy_ready 宽限 → 恢复 UDP mux 端口 → 实例化 `ActiveSession` → 同一轮立即执行 `_converge_session`。
- 媒体网络挂载收敛抽为单一实现，不依赖内存 session，由 API 离线恢复路径与 `_converge_session` 共用；消除 `_recover_attachment_offline` 与 `_converge_session` 中重复的挂载逻辑。媒体网络不存在或不合规时仍走既有 Stream-only 替换语义，不盲目挂载。
- 单元测试：Supervisor 重启后无 session、Gateway visibility 返回真实 503、Gateway 未挂载到媒体网络的场景。
- E2E：带载升级场景，在 Profile 运行中重建 Gateway 与 Supervisor 后验证自愈。

### 非范围

- 不改 Gateway visibility / registration 路由语义与状态码。
- 不改 Stream Agent 重连策略。
- 不改部署脚本 readiness 超时值。
- 不改网络版本哈希契约（见 t048）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：Supervisor 无该 Profile 内存 session、API 返回 desired=running 且实例一致、Gateway visibility 对该实例返回 503（Agent 未注册）时，一次对账即恢复该 Profile 的 session 并恢复其 UDP mux 端口。
- [ ] AC-002：AC-001 场景中 Gateway 当前容器未挂载到该 Profile 合规媒体网络时，同一次对账内 Gateway 被挂载到固定端点，transport 状态为 `recovering`，不依赖下一轮对账。
- [ ] AC-003：Gateway 容器缺失或控制接口不可达时，存量沙箱恢复不被中断，session 仍建立，transport 状态反映 `gateway_missing` / `gateway_unreachable`，容器不被拆除。
- [ ] AC-004：API 不可达时，存量沙箱只做媒体网络挂载恢复，不建立 session、不上报生命周期，行为与改动前一致。
- [ ] AC-005：媒体网络不存在或不合规时，恢复后的收敛走 Stream-only 替换（受替换预算约束），不对不合规网络执行挂载。
- [ ] AC-006：实例 label 不一致或 API fence 不一致的沙箱仍不被恢复为 session。
- [ ] AC-007：真实拓扑中 Profile 运行期间强制重建 Gateway 与 Supervisor 容器后，Supervisor readiness 在部署 readiness 截止时间（300s）内恢复 ready，诊断中不再出现 `session_instance_mismatch`、`gateway_not_attached_at_fixed_endpoint`、`agent_not_registered`，且该 Profile 可重新获得画面。
- [ ] AC-008：全量门禁（`CBROWSER_RUN_E2E=1 scripts/run_gates.sh`）通过。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：用户 2026-11-10 提交的部署故障分析（Bug 2）；同日核对 `supervisor/core.py` 恢复分支、`_converge_session`、`_recover_attachment_offline`、`gateway/server.py` visibility 路由与 `gateway_client.py`，环形依赖属实。

### 有意不测

- 无。

### 测试策略

- 单元：Gateway 控制客户端注入真实 `httpx.HTTPStatusError(503)`，不得把 `has_foreground_viewers` 打桩为直接返回值来绕过；断言 session 建立、`attach_profile_infrastructure` 调用与 transport 状态（AC-001..006）。先在当前实现上跑红再修复。
- E2E：基于统一 `FrontendAppTopologyHarness` / `GatewayTopologyHarness` 与 `cleanup_prefixed_resources`（t046 铁律），禁止用例自建 Docker 编排与清理；启动 Profile → 强制重建 Gateway 与 Supervisor 容器 → 轮询 readiness 与画面（AC-007）。浏览器测试一律 headless。
- 门禁：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh`。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无

### 风险与回退

- 风险：删除前置探测后，恢复期 Agent 注册失败转由 `_converge_session` 处理，可能在注册宽限期后触发 Stream-only 替换；需确认宽限期覆盖 Gateway 挂载后 Agent 重连耗时。
- 风险：现有 harness 未必支持在运行中重建 Gateway/Supervisor，需在 harness 内补能力而非用例私建。
- 回退：revert 本 task 实现 commit。

### 依赖与约束

- 无前置 task。与 t048 无文件交集，可并行。
- E2E 遵守 t046 统一 Harness 铁律；浏览器测试 headless。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md` §5.4 或 Supervisor 相关章节：存量沙箱恢复单向流程；媒体挂载收敛独立于 session 与业务可见性。
- `docs/blueprint/testing.md` Supervisor 阶段验证：带载升级 E2E 入口与要求。
