---
tid: "t082"
slug: "persistent_namespace_policy_agents"
title: "网络策略改为随命名空间常驻的受限执行与观测"
status: "done"
branch: "t082_persistent_namespace_policy_agents"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "c2d7c892b08ab2df34465b6b08620cc2d43de0d2"
spec_source_sha: "ab3bd3c6e9ae8d0a1de2ba72b1880d9d62f6438a"
depends_on: "t080"
conflicts_with: "t075,t078,t081"
note: "2026-11-18 用户授权详细立项；仅创建 backlog，不实施、不发布。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 创建记录：2026-11-18T00:31:35+08:00，用户要求按已核实资源问题与架构方案详细立项；仅创建 backlog，尚未实施、验证业务 AC 或获得本批 commit/push 授权。
- 跨 task 契约与脱敏现场基线：docs/tasks/t080_linux_native_runtime_storage/architecture_scope.md。长期 specs/blueprint/ADR 在对应实施 finalization 同步，本批不预写生效结论。
- 外部能力仍需正式 spike：见 task.md 未知契约清单。创建门禁通过不等于 SDK/subpath 或最小权限已经实测。
- 实施（2026-11-18，云端，基 t080 finish c2d7c89）：每目标 netns 一个常驻 Policy Agent 替代一次性 policy helper 与巡检 docker exec DNS。新增 `supervisor/policy_agent_protocol.py`（版本化线协议：health/resolve/install/inspect/fail_close、身份全等、64 KiB 上限、裸 hostname 解析输入校验、spec 摘要）、`supervisor/policy_agent.py`（Agent 状态机：修订围栏、幂等 install、replace 刷新、fail-close 确认；身份只读创建环境）、`supervisor/policy_agent_client.py`（UDS 同步客户端，Unavailable/Rejected 类型化二分）；协议 schema 经 `scripts/export_policy_agent_protocol.py` 导出并纳入 run_gates 漂移检查。`network_policy.py` 收敛为纯规则库：新增 `verify_fail_closed()` 与 `replace_policy()`（先备份双族表、全量替换、失败回滚、回滚失败才失败封闭），删除一次性 CLI `main()`。
- 适配器（docker_adapter）：Agent 生命周期（ensure/健康复用/标签全等 + health 回显接管/同名冲突删旧建新/孤儿清理/Profile 拆除与探针结束同步删除）、冻结派生（上游未变零 DNS、上游变化走 resolve→install 新修订→成功才冻结的刷新事务、失败保留旧冻结 spec）、verify 走 Agent inspect + 修订证明、fail-close 须 Agent 确认、pause/unpause 直通；出口探测先建 probe 专属 Agent 再派生安装、结束删除。Supervisor 挂载 runtime 卷 `policy-agents` 子路径（storage_layout `RUNTIME_POLICY_AGENTS_PREFIX` + MountPlanner `policy_agent_root`，compose 新增 `CBROWSER_POLICY_AGENT_ROOT`）。
- 核心收敛（core/runner）：verify 失败先定点修复 Agent 重试一次；不可确认状态 30 秒预算（`_POLICY_ISOLATION_BUDGET_SEC`）内 recovering、超预算 Browser 暂停精确目标隔离、Stream 走 Stream-only 有界替换；漂移且 fail-close 未确认改暂停隔离（替代旧 `browser_policy_drift_unmitigated` 无缓解语义）；本机制暂停仅在仍是当前 desired=running 实例且复验（必要时先重装一次）通过后恢复，用户暂停与他实例记录永不触碰。runner 新增 Agent 拓扑事件定点唤醒（`note_policy_agent_event`），不触发全量扫描（p057 防自激不变）。
- 决策（ADR 039，`docs/blueprint/decisions/20261118_namespace_policy_agent.md`）：常驻化形态、协议、修订围栏/刷新事务、接管与孤儿、隔离/恢复所有权、CLI 删除面与 spike 延期口径。blueprint（architecture/supervisor/security/testing）与 specs（runtime_lifecycle/proxy_management）已同步 finalization。
- [deploy] 与 spike 处置：AC-010 及两项 UNVERIFIED-SPIKE（仅 NET_ADMIN 完整能力、pause 冻结语义）云端无 Docker 不可验，按用户 2026-11-18 裁定先登记 pending 再在 task.md 契约区加处置注记：p132（两项 spike 本地实证）、p133（AC-010 本地补验）。打勾只表示云端可做部分完成、按裁定视为流程完成，不表示已实测通过。
- 旧测试处置（仓内 TDD 铁律：语义失效整体删除并写明理由，禁止就地改预期）：删除 `tests/unit/test_a11_policy_timeout.py` 全文件（6 测，主题即临时 helper 的超时/删除/日志语义，机制已不存在）；删除 `test_t055_supervisor_runtime_robustness.py` 中 5 个 `_run_policy_helper`/install-helper-log 测试（同上）；删除 `test_supervisor_docker_boundaries.py::test_policy_verification_helper_has_deterministic_managed_name`（临时校验 helper 命名已不存在）；删除 `test_t026_network_policy_verify.py::test_fail_closed_cli_exits_3_on_restore_failure`（CLI 已删除，严格库行为由同文件兄弟测试覆盖）；删除 `test_t051_docker_error_detail.py::test_policy_helper_run_failure_keeps_docker_detail`（直测 `_run_policy_helper` 本身，方法已随机制删除；其 docker 详情保留契约由同文件 policy install 失败测试在新路径上继续覆盖）；删除 `test_t026_supervisor_convergence.py::test_browser_fail_close_failure_is_retried_not_marked`（旧无缓解重试语义被 AC-006 暂停隔离取代，新语义由 `test_t082_supervisor_policy_convergence.py` 覆盖）。其余受影响测试只做 harness 适配（fake 容器补 name/labels/status、构造补 deployment_instance_id、共享进程内 Agent rig `tests/unit/policy_agent_test_support.py`），断言值不变；egress parity 测断言的 spec dict 逐字不变。适配中抓到并修复一个真实缺陷：冻结派生返回 JSON 模式 dict（元组变列表）与新鲜派生形状不一致，统一为 python 模式。
- 审阅修复轮（round 1 双轴 FAIL 后）：code f001（important）——本机制暂停的 Browser 在生产接线下不可达恢复：Docker scan 状态为 paused，而 `_reconcile_profile` 同代分支只在全 running 时调 `_converge_session`，且先把 paused 误报 container_exit。根因修复：同代分支在误报前先判本机制暂停记录（浏览器 paused + Stream running → 直接进收敛做复验恢复）；恢复分支（Supervisor 重启）在 scan 到 paused Browser 时重登记暂停所有权（本系统内只有本机制会 pause Browser，stop 流程是 stop/remove），收敛据此复验恢复；`_converge_session` 暂停分支加显式 desired=running 围栏（AC-008）。新增接线级测试 `test_reconcile_routes_paused_browser_to_verified_resume`（经 `_reconcile_profile` + API runtime 驱动，断言 unpause、无 container_exit 终态报告、transport ready）——原收敛测试以恒 running 的 scan 直调 `_converge_session`，正是漏检原因，已在测试文件注释中写明。code f002：ADR 编号统一为 039（6 处源码注释 + p132 正文误写 031）。code f003：删 docker_adapter 未用 import `policy_helper_labels`（函数本体仍由 t050 使用，保留）。code f004：`PolicyAgentClient.resolve` 校验回执地址必须为 IP 字面量，畸形回执归一为 PolicyAgentUnavailable 并加归一化，新增 stub 客户端测试。test f001：新增 `_install_network_policy` ready 标记测试（Agent 成功后才写 ready.json、失败不写且 gate 保持关闭）。test f002：新增 Stream 替换预算耗尽 → failed 不再替换测试。test f003：由 desired 围栏修复覆盖，新增 desired=stopped 不恢复测试。test f004：身份伪造测试扩展为 6 字段 × 5 op 全参数化（原仅 profile_id × fail_close）。test f005：删 t055 中 A4 节死 harness（`_Helper`/`_policy_adapter`/`_install`/`_gate`，零调用方）。
- 审阅修复轮 2（round 2 代码轴 FAIL 后；测试轴 round 2 已 PASS）：code f005（important）——重启所有权重登记被 `_reconcile_profile` 无会话路径的 any-not-running 门禁（报 container_exit 并 return）挡在 restore 分支之前，结构性不可达（reviewer 以探针实证）。修复：该门禁对「Browser paused + Stream running」放行落入 restore 流程（重登记 + 复验恢复），其余组合不变；新增接线测试 `test_reconcile_restores_paused_browser_after_supervisor_restart`（无会话无记录驱动 `_reconcile_profile`，断言会话恢复、unpause、无 exit 报告、transport ready），变异校验（关闸门条件）确认该测试能抓旧行为。code f006（minor）：本机制暂停期间 Stream 退出无修复路径——同代分支新增「暂停中 + Stream 非 running → Stream-only 有界替换」一档（预算语义不变，Browser 保持暂停），新增接线测试 `test_stream_loss_during_browser_isolation_repairs_stream_only`，同样过变异校验。
- e2e 改写（云端不可跑，归 p133 本地验）：`test_supervisor_namespace_policy_e2e.py` 与 `test_supervisor_ipv6_policy_e2e.py` 改由生产 `PolicyAgentClient` 驱动真实 Agent（install/inspect/修订围栏拒绝/Agent 移除后规则持续），内核正负断言不变；`test_supervisor_policy_failure_e2e.py` 失败注入仍为无效 policy 镜像（语义变为 Agent 永不健康），不变量不变。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

|finding_id|status|处置|
|---|---|---|
|t082_code_f001|已修|暂停路由根因修复（同代分支路由 + 恢复所有权重登记 + desired 围栏），新增 `_reconcile_profile` 接线级恢复测试|
|t082_code_f002|已修|ADR 编号统一 039（源码注释 6 处 + p132 正文）|
|t082_code_f003|已修|删除 docker_adapter 未用 import `policy_helper_labels`|
|t082_code_f004|已修|`PolicyAgentClient.resolve` 回执 IP 字面量校验 + PolicyAgentUnavailable 归一，新增测试|
|t082_test_f001|已修|新增 `_install_network_policy` ready 标记成功/失败双向测试（AC-001）|
|t082_test_f002|已修|新增 Stream 替换预算耗尽转 failed 测试|
|t082_test_f003|已修|新增 desired=stopped 时本机制暂停不恢复测试|
|t082_test_f004|已修|身份伪造扩展为 6 字段 × 5 op 全参数化|
|t082_test_f005|已修|删除 t055 A4 节死 harness（\_Helper/\_policy_adapter/\_install/\_gate）|
|t082_code_f005|已修|无会话 any-not-running 门禁对 paused Browser 放行至 restore（重登记可达），新增重启接线测试 + 变异校验|
|t082_code_f006|已修|同代分支新增暂停期间 Stream-only 有界替换档，新增接线测试 + 变异校验|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：云端可做部分全部完成；AC-001–AC-009 以单元/协议层证据判定，AC-010 按契约区处置注记打勾（本地补验 p133），两项 spike 延期 p132。
- 测试：t082 新测 30 条全绿（协议/状态机 10、适配器生命周期 10、核心收敛 10）；受影响既有套件（t052 probe、t080 mounts、egress parity、t026 收敛、network_policy 相关）适配后全绿；全量门禁实数见收尾时日志（老基线逐项点名于汇报）。
- 黑盒：e2e 三文件已改由 Policy Agent 驱动并可收集（7 测），云端无 Docker 未实跑，归 p133 本地执行。
- review：见 review_code.md / review_test.md（full 级双轴）。
- AC 判定：见 `task.md` 行内打勾。

### 结果摘要

- 一次性 policy helper 与巡检 docker exec DNS 整体退役；每目标一个常驻受限 Policy Agent 承担安装/校验/解析/失败封闭，稳态 verify 零容器创建、零 exec、零重复 DNS。
- 策略状态不可确认与漂移未确认封闭均在 30 秒预算内收敛为精确目标暂停隔离，且恢复所有权严格限于本机制暂停的当前实例。
- 云端不可验部分（AC-010、两项 spike）已逐项登记 p132/p133 留待本地统一补验，未在云端冒充实测。

### 长期文档闭环

- ADR 039 新增；blueprint architecture/supervisor/security/testing 与 specs runtime_lifecycle/proxy_management 已同步；协议 schema 入门禁漂移检查。spike 结论待本地执行后入 findings 并回填（p132）。
