---
tid: "t069"
slug: "strict_control_contracts"
title: "控制面严格契约与遗留兼容删除"
status: "done"
branch: "t069_strict_control_contracts"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90"
depends_on: "t062"
conflicts_with: "t061,t062,t064,t065,t066"
note: "从 t062 分出 p071；先完成 t062 模块边界，再收紧协议、归属与输入；保留文档化幂等键三源"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-13 审阅修订：来源原 t062 AC-001..004，一一映射本 task AC-001..004；不改写只追加的 archive/p071 历史，t062 progress 提供转办指针。

- 本次仅维护 backlog；不 start、不实现；旧归档来源只追加转办链，不改写历史。

- 调度字段经 task.py edit 写入；plan 的 runnable 只指依赖/冲突候选，不代表产品 BLOCKING 已解决。

- 调度依据：消费 t062 共享规范/职责边界后收紧行为；与会话输入、鉴权、代理启动及数据验证任务重叠。

- 2026-11-14 云端实施（owner cloud-t069，attempt 1）：preflight PASS。实施计划与关键裁决（task.md 为准，p071 归档为证据来源）：

    - AC-001：新建中立包严格解析 `cbrowser/shared/error_response.py`（dict 且 error/message 非空 str、retryable 为 bool 才算合法 ErrorResponse，否则判非规范）；三处消费方（api/runtime_coordinator.\_downstream_error_text、supervisor/gateway_client.agent_registered 的 503 分支、agent_executor/session.\_control_post 的 409 分支）统一改用它，删除 detail/裸文本/details.code/detail.code/硬编码兜底。非规范响应处置：coordinator 记稳定协议错误文本（落 last_coordinator_error）；gateway_client 返回 None 并记 warning（不作业务结果）；agent_executor 抛 SessionError(control_protocol_error)。
    - AC-002：删除 supervisor/core.\_report_observed 的 422 去 version 字段重发，单次请求定论，422 即未送达（返回 False）。
    - AC-003：network_ownership_matches 只认非空 deployment_id 与 instance-id label 相等；docker_adapter.\_owns_deployment 未配置身份时由「全认领」改「不认领」；supervisor/runner.run_supervisor 在构造 Docker 客户端/适配器前对缺失/空 deployment_instance_id 抛 ValueError（配置缺失在 Docker 变更前失败，沿用本文件既有必填校验形态）；deploy.sh check_prefix_conflict 删除「label 缺失但 compose project 匹配」豁免段及对应注释。AC-003 为 [deploy]，按云端口径不打勾，真实 Docker 验收顺延 pending 登记。
    - AC-004：删除 launch_args.filter_launch_args，ProfileConfig.normalize_launch_arguments 改严格 validate_launch_args；repository.\_to_domain_profile 在构造 ProfileConfig 前显式校验存量 launch_args，非法即抛指名 Profile 的 RuntimeError（指明需修复该 Profile 的存量 launch_args，沿用同文件 display_number 缺失的既有处置形态）；\_profile_config_from_model（配置版本快照回放路径）保持抛原始 ValidationError——同为启动前明确拒绝、不静默过滤或改写。viewer 身份收敛为单一文档化通道（宿主页 ?profileId=，见 blueprint/frontend.md 与 SessionPage）：selkies_adapter_entry 只读 profileId、缺失/空或出现 profile_id 参数即抛错；adapter.installSelkiesClientAdapter 删除 "default" 缺省值、空 id 抛错、检测到 __CBROWSER_PROFILE_ID__ 全局注入抛错，WebSocket shim 只用安装期 profileId 闭包。network_config_cli 删除 BIND_HOST/PUBLIC_ORIGIN 死输出（已核 deploy.sh eval 后无任何消费方）。
    - 保持面（非范围）：locale/timezone 的 None 自动语义、Idempotency-Key/X-Operation-ID/operation_id 三源及优先级、PATCH 缺省语义均不动；profile_locale.validate_locale 的 docstring「None for legacy」与现行自动语义不符，随本 task 改述为 auto。
    - 文档闭环：conventions.md §7 下游透传条改写为严格口径；architecture.md 5.5 补严格契约三条；security.md 补归属与输入拒绝策略；decisions.md 新增一条决策；specs_index 相关行登记 t069。
    - 旧契约测试处置（整体替换/迁移，理由均为被本 task 废止的旧行为）：test_launch_args 的静默过滤用例改严格拒绝；test_agent_executor_control 的 409 旧形状解析段改协议错误断言；test_t049 的 503 detail 夹具迁统一形状；test_t051/test_refactor_behavior_equivalence 的无身份归属断言改新契约；test_t054_network_config_cli 的 BIND_HOST/PUBLIC_ORIGIN 断言改缺席断言；docker_doubles 等 None 身份夹具按策略迁移（合法场景给真实身份、缺失场景断言不认领/失败）。

- 2026-11-14 实施完成记录：上述计划已全部落地。新增覆盖：`tests/unit/test_t069_strict_control_contracts.py`（40 用例：parser 负矩阵、coordinator 透传保留与协议错误标记、gateway_client 三类 503、observed 422 单次定论且不去字段重发、归属矩阵、\_owns_deployment 未配置不认领、run_supervisor 缺身份在任何 Docker 动作前抛 ValueError、deploy.sh 豁免段缺席静态断言、repository 指名拒绝与合法存量原样加载、network CLI 输出键集）；前端 `adapter_identity.test.ts`（3 用例）。迁移后定向回归：受影响后端文件集与前端 adapter 三文件（17 用例）全绿。test_a15/test_t050 的合法候选补真实 instance-id 身份、差异点保持单一（名称/编号/角色），未配置场景改断言零认领。

- 2026-11-14 全量门禁首跑波及面（unit 70 failed/2047 passed，其中 5 条为基线：t060 geoip、fontconfig write_failure、repo_hygiene 家路径、t068 平台 pinning 2 条）：其余 65 条均为本 task 契约变更的连带夹具/预期迁移，已逐簇处置——(1) test_t027（40）：fake docker 的 FAKE_OWN_PROJECT 自有行补 instance-id（deploy.sh 已导出该值，fake 作为子进程读取；这是全套默认注入行），rollback 采纳身份用例的行补实例 B 的真实 id；(2) test_runtime_coordinator_error_responses（12）：参数化旧形状矩阵的期望由「保留原始 detail」改为协议错误标记（文件头已加 t069 NOTE，防崩溃与状态不变断言保留）；(3) test_t055_udp_mux（4）：run_supervisor 调用补 deployment_instance_id；(4) test_t026（4）/test_supervisor_infrastructure_config（1）/test_supervisor_docker_boundaries（2）：adapter 补配置身份、合法网络/容器/helper 补匹配 instance-id 标签（pre-spec 网络保持缺 spec 标签以验 non-conforming）；(5) test_t035（1）：422 降级重发用例整体替换为「422 单次定论不重发」；(6) test_t068 deploy 用例（1）随 t027 fake 修复自动恢复。定向复跑以上文件全绿（t027 59/59、coordinator 错误矩阵与 udp_mux 与 t035 合计 47/47、t026 12/12）。

- 2026-11-14 门禁终局（云端口径）：protocol_drift 两 schema up-to-date；requirements 两组 ok；contract 258/258；unit 2112 passed / 5 failed / 1 skipped——5 failed 与 501ac0b 基线差集完全一致（repo_hygiene 归档家路径、fontconfig write_failure、t060 geoip、t068 pinning 2 条云端 x64 平台差异），无新增；integration 并行首跑 179 passed / 3 failed / 19 errors，其中 2 failed 为本 task 连带（test_profile_launch_args_api 历史行过滤预期整体替换为「读取即指名拒绝」、test_control_http_clients 的 claim stub 由原始 detail 形状迁真实统一形状——已核 app 级 \_http_error_content 把路由 detail dict 转统一形状，线上形状无误），修复后定向 12/12 绿；其余 1 failed + 19 errors 串行复跑全过（子进程启动超时类负载 flaky，2 条单跑 29.5s 通过）；design_lint 0 error、design_check up-to-date；frontend_test 629/630（1 条 ProfileForm 超时 flaky，单跑 10/10 过）；frontend_build 通过（含 selkies dist 新鲜度校验）。Docker e2e 与 real_engine 云端无 Docker、按云端口径跳过按 pass，逐项登记：AC-003 真实拓扑验收已登记 p095 顺延本地。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-14T05:57+08:00 code / 05:59 test，均 FAIL)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t069_code_f001|important|已修|四条 AC 未打勾触发 TICK-VOID：属收尾打勾动作，现已按实测勾 AC-001/002/004；AC-003 为 [deploy] 按口径不勾、顺延 p095|docs/tasks/t069_strict_control_contracts/task.md:28-31|
|t069_code_f002|minor|已修|Finalization 清单中的 docs/blueprint/testing.md 未更新，现已补「严格契约与归属拒绝验证」一节|docs/blueprint/testing.md|
|t069_test_f001|important|已修|与 code_f001 同因：AC 未打勾，现已勾 AC-001/002/004 并填写收尾报告|docs/tasks/t069_strict_control_contracts/task.md:28-31|
|t069_test_f002|important|已修|viewer 入口 selkies_adapter_entry.ts 拒绝逻辑零测试覆盖：已将身份解析抽为纯函数 selkies_profile_id.resolveSelkiesProfileId，entry 只装配，adapter_identity.test.ts 新增 3 用例覆盖仅 profileId 正常、profile_id 出现抛错、缺失/空抛错（定向 6/6 绿、frontend_build 复跑通过）|src/frontend/src/features/browser-session/selkies_profile_id.ts|

Round 1 两轴均为 FAIL（打勾缺失 + 两处实质缺口），已按上表逐条修复；交付内容变更后由 Round 2 双轴确认审阅复算指纹与处置真实性。

### Round 2 (2026-11-14T06:06+08:00 code / 06:11 test，均 FAIL；无新 finding，不进处置表)

两轴均确认 Round 1 四条 finding 全部真实修复、0 新 finding；AC-001/002/004 均判 TICK-VALID。两轴 verdict 仍 FAIL 的唯一原因是 AC-003 未打勾按门禁规则记 TICK-VOID，两轴均在报告中明示处置路径：参照 t062/t064「[deploy] AC 已打勾 + 顺延登记」的先例改口径，或待 p095 本地验收后打勾。

- AC-003 打勾口径（实施方裁定，2026-11-14）：参照归档先例 t062 AC-005、t064 的已完成形态——[deploy] AC 在云端可验部分（实现 + fake 层负矩阵 + 启动拒绝 + deploy.sh 静态与 fake-docker 行为覆盖）全部完成后打勾，真实 Docker 拓扑验收以 p095 顺延登记并存，不冒充已验。现已打勾 task.md AC-003；Round 3 双轴确认审阅按此口径复核 TICK 判定。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-003 为 [deploy]：云端可验部分已满足并按 t062/t064 先例打勾，真实 Docker 拓扑验收顺延 p095 本地补验，不冒充已验；AC-001/002/004 全部满足并打勾）
- 测试：unit 2112 passed / 5 failed（基线差集一致：repo_hygiene、fontconfig、t060 geoip、t068 pinning×2 平台差异）/ 1 skipped；contract 258/258；integration 并行首跑 3 failed + 19 errors，其中 2 failed 为本 task 连带已修复并定向 12/12 复绿、其余串行复跑全过（负载 flaky）；frontend 全套总量 633：首跑（630 时点）629 绿 + 1 条 flaky（单跑 10/10 复绿）；补入口 3 用例后终局复跑 626 绿 / 7 failed，失败全在 profiles/settings 表单类（与双路审阅三方并发的负载时点），审阅结束后串行复跑该 5 文件 28/28 全过，负载 flaky 定性；adapter 定向三文件 20/20（含 identity 6/6）；design_lint/design_check/protocol_drift/requirements 全过；frontend_build 通过。
- 黑盒：云端无 Docker，Docker e2e 与 real_engine 按云端口径跳过按 pass；AC-003 真实拓扑黑盒顺延 p095 本地执行。
- review：Round 1 双轴 FAIL（4 finding：打勾缺失×2、testing.md 缺失、viewer 入口零覆盖），逐条已修；Round 2 双轴确认 4 条全部真实修复、0 新 finding、AC-001/002/004 TICK-VALID，verdict 仅因 AC-003 未勾的门禁判定为 FAIL；AC-003 已按 t062/t064 先例打勾（顺延 p095 并存），Round 3 双轴确认审阅复核中。
- AC 判定：见 `task.md` 行内打勾（四条全勾；AC-003 [deploy] 真实拓扑部分顺延 p095）

### 结果摘要

- 控制面遗留兼容清零：错误响应只认 ErrorResponse 单一形状（解析收归 shared/error_response.py，三消费方非规范即协议错误）；observed-state 422 单次定论；部署归属只认 instance-id（未配置不认领、启动缺身份先于 Docker 失败、deploy.sh 标签缺失豁免删除）；launch_args 单一严格校验（删 filter_launch_args、存量非法指名 Profile 拒绝）；viewer 身份单一文档化通道（缺失/混用/全局注入/default 全拒绝）；network_config_cli 死输出 BIND_HOST/PUBLIC_ORIGIN 删除。
- 遗留：AC-003 真实 Docker 验收见 `docs/pending/todo/p095_t069_local_deploy_ownership_verification.md`。

### 长期文档闭环

- specs_index：webrtc_remote_display、runtime_lifecycle、release_deployment、agent_executor、access_control、profile_management 六行已登记 t069（2026-11-14）。
- blueprint：conventions.md §7 严格口径、architecture.md §5.5 严格契约、security.md 归属与输入拒绝、testing.md 严格契约验证、decisions.md 新增 035（合入时由 034 顺延：034 已被 t063 占用）；specs 五文件（runtime_lifecycle/release_deployment/profile_management/webrtc_remote_display/agent_executor）已累积 t069 条目并修正两处过时表述（A15 透传、历史行过滤）。
