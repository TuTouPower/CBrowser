# Task spec

## 背景

2026-11-07 用户授权把当前全部仍有效的 pending todo 聚合为一个 task 解决（依赖 t037，t038 depends_on 加上本 task）。四条来源均已核实仍有效：p046（t044 review minor：`run_gate_suite` 并行阶段 c1=exit 5 未与串行 c2 对称处理，全 serial 的 suite 会假失败）、p048（t037 门禁 v6 被中止后残留整套 E2E 容器占用 UDP 30000，污染 v7 门禁；门禁启动时无前缀清理、无中断 trap）、p049（前端 E2E 文件每个用例各自起停整套拓扑，串行阶段开销大）、p050（v8 三项非基线失败：`test_vendor_replaces_stale_destination_contents` 每次从公网下载 wheel 触发 SSL EOF（t035 同类）、`test_ac007...` 媒体帧时序、`test_supervisor_recovery_e2e::...sigkill` setup ReadTimeout；监督裁决不能只凭单跑通过放过）。本 task 从根因修这四类门禁稳定性问题。

## 契约区

### 范围

- `scripts/run_gates.sh`：`run_gate_suite` 两阶段 exit 5 对称处理。
- 门禁启动与中断清理：按明确测试前缀白名单清理上一轮遗留容器/网络，SIGTERM/SIGINT/EXIT trap 执行同一套清理；绝不触碰生产部署容器与其它会话资源。
- 前端 E2E（`test_frontend_app_e2e`、`test_frontend_session_e2e`、`test_frontend_media_e2e` 等）：同一文件内共享一套容器栈（module/session fixture），用例间只重置状态（独立 Profile id / 显式清理），不重复起停容器、不串扰。
- `test_frontend_adapter_build::test_vendor_replaces_stale_destination_contents`：改用已锁定 SHA256 的本地缓存 wheel，缺失时必跑模式失败封闭（列出缺项，不 skip、不回落公网）。
- `test_frontend_app_e2e::test_ac007...` 与 `test_supervisor_recovery_e2e::...sigkill`：负载下的等待改为事件 / 就绪条件驱动（首帧、帧计数变化、SSE 状态、健康就绪），不靠加长超时。
- 四条 pending 在本 task worktree 内按规则归档（transferred，注明转入 t045）。

### 非范围

- 不修改产品运行时行为（Supervisor/API/Gateway 业务逻辑）。
- 不改变既有用例覆盖的行为与断言语义，不弱化断言，不整文件删测试。
- 不新设性能指标；不引入公网下载路径。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：`run_gate_suite` 的并行阶段（c1）与串行阶段（c2）对 pytest exit 5（no tests collected）对称处理；构造一个全部用例标 `serial` 的 suite 时，门禁不假失败，且 junit 仍合并该 suite 的串行用例结果。
- [ ] AC-002：门禁启动时检测并清理上一轮遗留的测试前缀容器与网络（按前缀白名单精确匹配）；`cbrowser-supervisor/gateway/api/caddy` 生产部署容器与其它会话命名的资源不被删除；SIGTERM/SIGINT/EXIT 中断时也执行同一套清理；有单测覆盖「残留容器存在时被清」「非白名单容器不被删」。
- [ ] AC-003：前端 E2E 文件内共享一套容器栈，用例间只重置状态；串行阶段整套容器启停次数显著低于改造前（同一文件内多次用例不再各起一套）；文件内全部用例通过且无跨用例 Profile / 状态串扰（有隔离语义测试覆盖）。
- [ ] AC-004：`test_vendor_replaces_stale_destination_contents` 不再发起任何公网请求，使用本地已锁定 SHA256 的缓存 wheel；缓存缺失且必跑模式时用例失败并列出缺失项，非必跑模式才 skip；不回落公网。
- [ ] AC-005：`test_ac007_lifecycle_resume_and_isolated_media_diagnostics` 的媒体帧判定与 `test_supervisor_recovery_e2e::test_supervisor_dual_profile_port_invariance_on_sigkill` 的 setup 就绪判定改为事件 / 就绪条件驱动，无 `sleep` 加长或超时上调；负载下稳定通过。
- [ ] AC-006：合并 task 的完整门禁（`CBROWSER_RUN_E2E=1 scripts/run_gates.sh`）中 AC-004、AC-005 涉及的三个 E2E 用例都通过（非仅定向单跑通过），E2E 失败集合不超出 t032 已登记基线（t019 首帧）。
- [ ] AC-007：p046 / p048 / p049 / p050 四条 pending 在收尾前按 `pending.py archive --resolution transferred --fix-ref t045` 归档（p046 在 t044 与 t037 分支的重复只归档本 worktree 内一份），归档备注写明转入 tid 与核实结论。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：p046、p048、p049、p050（2026-11-07 于 main 与 t037/t044 分支核实：p046 的 `if [ "$c1" != 0 ]` 仍缺 exit 5 兜底；p048 的 `run_gates.sh` 仅有 `rm -rf "$SCRATCH"` EXIT trap，无容器清理；p049 的 harness 仍为函数级 fixture；p050 的 wheel 仍走公网）；用户 2026-11-07 授权聚合。

### 有意不测

- 无。

### 测试策略

- unit：门禁脚本 exit 5 分支、前缀清理白名单（含生产容器保护）、共享栈 fixture 的状态重置与隔离（stub Docker 边界）。
- E2E：完整门禁必跑模式验证 AC-003~006；本地 wheel 缓存缺失的失败封闭路径。
- 浏览器测试一律无头。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无

### 风险与回退

- 风险：共享栈用例间清理不彻底会引入串扰；前缀清理误删其它会话资源；就绪条件驱动改动让原本靠超时兜底的用例暴露真实缺陷。
- 回退：回退本 task commit；前缀清理白名单以精确前缀匹配收窄。

### 依赖与约束

- 依赖 t037（t037 分支已 done，作为本 task 的 `--base`）。t038 的 `depends_on` 已追加 t045。
- 遵守 testing.md 的必跑模式失败封闭规则；不引入公网依赖；不弱化既有断言。

### Finalization 时更新的 blueprint

- `docs/blueprint/testing.md`：门禁 exit 5 对称处理、启动/中断前缀清理、前端 E2E 共享栈、本地 wheel 缓存与失败封闭、就绪条件驱动（不靠加长超时）。
