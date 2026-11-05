---
tid: "t028"
slug: "runtime_isolation_quota_regression"
title: "补齐历史实跑入口、配额与 Agent 替换回归及门禁证据"
status: "done"
branch: "t028_runtime_isolation_quota_regression"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "2bbce465d16d958866691dd97bdbfd1cd7693616"
depends_on: ""
conflicts_with: "t027"
note: "来源 p016；云端 Muse，真实环境执行交 t032"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-04：从 p016 聚合立项，核实基线 main@c6a9322；只创建 backlog，不 start。
- 云端范围与本地最终 t032 分离；真实环境未执行不能按通过回填。
- 2026-11-04：按三方审阅修订：新拓扑附网/回滚用例移交 t026 并解除对 t026 的硬依赖；新增历史真实链入口、required 模式 sha256 fail-closed 与 run_gates 证据模式；与 t027 互斥。
- 2026-11-04（执行）：base=t027 tip 2bbce46，attempt 1（execution_id a59874837e7e4f70895bd1b913919b62，owner exec-main-20261104-t028），preflight PASS。
- AC-002：`test_gateway_signaling.py::test_agent_replacement_closes_old_viewers` 恢复 251fa0f 四项精确断言（close 1001、新 conn_id、下行回复、旧 Agent 退出后新 Viewer 续传），单测实跑通过。
- AC-003：重写孤儿探针 `supervisor_resource_probe/stream_monitor.py`，投递改走生产 `GatewayControlClient.set_quota`（删除 mock socket 旁路），CPU burn/恢复/帧窗断言与 proof JSON 保留；新建 `test_supervisor_quota_chain_e2e.py`（真实拓扑：配额 15 生效、客户端越权不突破、清 cap 恢复、motion/static 切换、CPU policy 腿）。云端 collect-only 通过，实跑归 t032 AC-008。
- AC-004：新建五个真实入口：`test_x11_helper_permissions_e2e.py`（真实 DockerAdapter 权限收敛 + 坏镜像负例）、`test_gateway_registration_budget_e2e.py`（在途 4→429、失败 20→429、重启后自动重注册）、`test_artifact_download_chain_e2e.py`（真实 Chrome 下载→入库→API 字节/sha256 比对）、`test_search_defaults_retry_live_e2e.py`（CSRF 403、幂等键终态 applied、重放不重复）、`test_artifact_delete_resume_e2e.py`（真实 API 子进程两段启停续跑删除，云端实跑通过）。
- 删除续跑排障结论（云端实测，非产品缺陷）：失败腿 DELETE 返回 500（`IsADirectoryError` 未被 ArtifactError 映射捕获、由应用通用 handler 返回 internal_server_error），意图已持久化故重启续跑成立；Starlette ServerErrorMiddleware 发出 500 后 re-raise、uvicorn 关闭该 keep-alive 连接，同连接下一请求会被重置，测试在失败 DELETE 后换新 client。另：本云 VM 以 root 运行且 /home 挂载禁 chown，ArtifactStore 在 root 下 chown 到 runtime uid 被拒（目标环境非 root 时代码按守卫跳过 chown），云端实跑将 basetemp 置于 /tmp 规避。
- AC-005：`e2e_env.image_identity_problems`（格式/本地存在/可解析三类 fail-closed）接入 required 模式收集期；删除 `frontend_probe/harness.py` 的 `.scratch/images_env.txt` 旁路读取；新增 unit 9 条全过；required 模式以 tag 值实测被明确拒绝。
- AC-006：`run_gates.sh` 证据模式（`CBROWSER_GATE_EVIDENCE_DIR`）：逐 suite 跑完、脱敏 log、JUnit、manifest.json（命令/退出码/路径/image_identity/all_passed），任一失败总退出非零；默认 fail-fast 行为不变。新增 `scripts/redact_evidence.py`、`scripts/gate_evidence_manifest.py` 与 unit 4 条（PATH stub 驱动真实脚本）全过。
- AC-001/AC-007：testing.md 新增「历史实跑覆盖矩阵（t028）」与「t032 运行映射（t028）」两节；修正 testing.md 资源压力段与两份 validation guide 的失真表述（配额证据归属改为配额链 E2E 与生产投递路径）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-04T12:38:28+08:00) test 路 FAIL → 已修待重审

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t028_test_f001|important|已修|矩阵与 t032 映射引用不存在的 test_supervisor_network_protection_e2e.py 与 test_search_defaults_runtime_chain.py，经核实属实（实施笔记依据的早期记录有误）：网络行改列现行 browser_network/network_ownership/namespace/ipv6/policy_failure 五入口，search-defaults 行改列 test_api_search_defaults_routes.py 与 test_runtime_coordinator_integration.py，AC-008 指令同步改正|docs/blueprint/testing.md 覆盖矩阵与 t032 运行映射|
|t028_test_f002|important|已修|资源段误称旧三个 resource E2E 已退役且引用不存在的提交号，经核实三文件仍在且可收集：改写为三层准确表述（unit 算法层、resource 三 E2E 的真实采样/决策但 monitor 投递腿为本地回调、配额投递链归 quota chain E2E 与生产投递），删除虚假提交号|docs/blueprint/testing.md Supervisor 阶段验证资源段|
|t028_test_f003|minor|已修|AC-002「旧 Agent 退出不误关新 Viewer」无延迟误关窗口：旧 Agent 关闭后加 0.5s 静默窗口断言（不得收到 CLOSE/CLOSING/CLOSED 帧）再做存活往返，全文件 16 条复跑通过|tests/integration/test_gateway_signaling.py|
|t028_test_f004|minor|已修|配额链保留证据只记 CPU 采样窗数量：改为嵌入完整 windows（counter 与决策明细），证据不依赖临时 proof 文件存活|tests/e2e/test_supervisor_quota_chain_e2e.py|

### Round 1 (2026-11-04T12:45:05+08:00) code 路 FAIL → 已修待重审

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t028_code_f001|important|已修|与 t028_test_f001 同题（矩阵/映射引用不存在的两个测试文件），已按该条修复并逐一复核其余引用存在|docs/blueprint/testing.md|
|t028_code_f002|minor|已修|manifest 身份收集异常被无条件吞为空 map：改为显式记录 `image_identity.error`（类型+消息），空 map 只表示无镜像变量，unit 复跑通过|scripts/gate_evidence_manifest.py|
|t028_code_f003|minor|已修|证据模式 environment.log 未脱敏：构建输出先落 raw 文件、经 redact_evidence.py 脱敏后保留并删 raw，失败路径同样执行；unit 补断言（stub uv 输出秘密形状行）复跑通过|scripts/run_gates.sh、tests/unit/test_t028_run_gates_evidence.py|

### Round 2 (2026-11-04T12:48:40+08:00) 双路 PASS 后新 minor → 已修待 Round 3 重审

Round 2：code 路 PASS（新 minor 1 条）、test 路 PASS（零新 finding），Round 1 全部 7 条 finding 经双路复核消除。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t028_code_f004|minor|已修|environment.log 脱敏失败时 `|| cp` 回退会静默保留未脱敏原文：改为脱敏失败即写显式占位行并 stderr 告警，raw 永不进入证据目录；t028 相关 29 条测试复跑通过|scripts/run_gates.sh|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（云端交付范围；真实环境执行按 task 约定归 t032，不在本 task 认领 PASS）
- 测试：contract 169 passed；unit 853 passed / 1 skipped / 1 failed（test_repo_hygiene 为干净 base 2bbce46 同 ID 存量失败，源于 t027 归档 review 报告含本机绝对路径，非本 task 引入）；integration 129 passed / 1 failed（test_ac009_api_supervisor_start_and_stop_coordination 为干净 base 同 ID 同签名存量失败，协调器收敛超时、环境性）；前端 Vitest 204 passed + test:types + 生产 build 通过；E2E collect-only 97 条（新入口 7 条）；删除续跑用例以真实 API 子进程在云端实跑通过；required 模式镜像身份 fail-closed 经 tag 值实测拒绝。零新增失败。
- 黑盒：真实 Docker/Chrome 黑盒依赖 Docker，本机无 Docker，按用户 2026-11-03 豁免口径跳过并按 pass 计；真实执行义务已逐项映射到 t032（testing.md「t032 运行映射」），不在本 task 重复立项。
- review：full review 三轮：Round 1 双路 FAIL（code important 1/minor 2、test important 2/minor 2，共 7 条）→ 全部已修；Round 2 双路 PASS（code 新 minor 1 条 t028_code_f004）→ 已修；Round 3 双路 PASS、零新 finding；check_review_status overall=PASS、review_scope=ok、round=3。Round 3 test 路留一条非阻断建议（f004 脱敏失败分支补常驻 unit 用例），已记于 review_test.md，未立项。
- AC 判定：见 `task.md` 行内打勾（AC-001~AC-007 全勾；review 复核 coverage：code 6/7、test 5/7，trust_prior 项为 AC-003 与 AC-004 的真实环境实跑部分，按 task 测试策略归 t032 判定）

### 结果摘要

- Agent 替换精确断言恢复（AC-002）；孤儿配额探针接回生产投递路径并新建配额链 E2E（AC-003）；五个历史真实入口补齐（AC-004）；required 模式镜像身份 fail-closed + 删除 .scratch 旁路（AC-005）；run_gates 证据模式与 manifest（AC-006）；testing.md 覆盖矩阵、t032 运行映射与三处失真表述修正（AC-001/AC-007）。
- 遗留：真实环境执行义务归 t032（见 testing.md 映射表）；基线 hygiene 失败（t027 归档报告绝对路径）为链级存量，建议随整链收尾按 t024 先例以独立登记提交处置，本 task 未动他人文件。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

- specs_index: not_applicable: 本 task 交付测试入口、探针接线与门禁证据契约，无需求级 spec 变更；长期真相按 task.md Finalization 更新 docs/blueprint/testing.md 与两份 validation guide。
