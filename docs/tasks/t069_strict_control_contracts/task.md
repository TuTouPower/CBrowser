# Task spec

## 背景

承接原 t062/p071 的严格协议、资源归属与输入收紧，建立在 t062 中立模块与公共规则上；与包重构分为两个可回退实现 commit。

## 契约区

### 范围

- 统一 ErrorResponse 解析与非规范协议错误；删除 422 去版本字段重发。
- 非空部署 instance-id 是唯一归属凭据，缺失配置变更前拒绝；无标签/不匹配资源不认领不删除。
- 严格验证持久化 launch_args 和 viewer Profile 参数；只移除未经文档化的 profileId/profile_id/全局注入/default 链，不误删文档化的操作幂等键三源；删除 CLI 无消费者输出。

### 非范围

- 保持 Idempotency-Key/X-Operation-ID/operation_id 三源及其优先级，合法 None 自动推导/PATCH 缺省语义不变。
- 不自动修剪或删除非法存量输入，不自动删无标签资源；合法但旧归属测试须整体替换，不能放宽生产规则迎合夹具。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：合法 ErrorResponse 保留字段；旧 detail、裸文本和缺字段响应产生稳定可观测协议错误，不作为合法业务结果解析。
- [x] AC-002：observed-state 的 422 不触发删 browser_product/browser_user_agent 重发；失败不会伪报收敛。
- [x] [deploy] AC-003：缺失/空/不匹配 instance-id 的容器与网络不被认领删除；Supervisor 配置缺失在 Docker 变更前失败，合法匹配资源可恢复清理。
- [x] AC-004：非法持久化 launch_args 在启动前被明确拒绝并指向可修复 Profile，不静默过滤或改写；viewer 缺失/混用未文档化身份参数被拒；合法 locale/timezone None 与文档化幂等键三源保持；BIND_HOST/PUBLIC_ORIGIN 死输出移除。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001：可自动测试，触达生产函数或实际工具入口。
- AC-002：可自动测试，触达生产函数或实际工具入口。
- AC-003：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-004：可自动测试，触达生产函数或实际工具入口。

## 上下文区

- 来源：2026-11-13 审阅复核：p071，经 t062 拆分转办；覆盖 runtime_coordinator、gateway_client、agent_executor.session、core 422 分支、network_spec/docker_adapter/deploy.sh 与 adapter/selkies_assets 的 default fallback。

### 有意不测

- 非范围中的新增产品功能不作为本 task 验收；已声明 AC 不豁免。

### 测试策略

- 生产函数覆盖规范/非规范响应、单次 422、空身份和外国资源负向矩阵；对称路径一并验证。
- 整体替换 test_launch_args 的静默过滤旧契约；迁移 docker_doubles、test_p058_browser_lookup、test_normal_exit_replay、test_t055_supervisor_runtime_robustness、test_a8_terminal_observation 的 None 部署身份夹具，合法场景提供真实身份，缺失场景断言失败。
- fake Docker 验证先拒绝后零变更；真实隔离部署验证合法资源恢复，无标签资源保持未动。
- 按 docs/blueprint/testing.md 的 doctor_cmd/test_cmd/blackbox_verify 执行；本次仅改 backlog，创建校验不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。

### 风险与回退

- 风险：跨模块/制品或状态变更需按上述负向测试与 spike 验证；产品 BLOCKING 未消除不得实施。
- 回退：回退本 task 的完整实现 release；涉及数据先停写者并从已验证成套备份恢复，禁止仅降级数据库或以旧兼容分支兜底。

### 依赖与约束

- 硬依赖和冲突以 progress.md 的 task.py 调度字段为准；不把文件重叠当硬依赖。plan 仅输出图上候选，不能替代 preflight；产品 BLOCKING 必须先确认，SPIKE 先验证并回填。

### Finalization 时更新的 blueprint

- docs/blueprint/conventions.md、docs/blueprint/architecture.md：删除 mixed-version/legacy 行为规范。
- docs/blueprint/security.md、docs/blueprint/testing.md、docs/blueprint/decisions.md：归属与输入拒绝策略。
