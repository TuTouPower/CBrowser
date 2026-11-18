---
tid: "t081"
slug: "immutable_font_resource_lifecycle"
title: "平台字体发布、审计与消费统一为不可变资源生命周期"
status: "done"
branch: "t081_immutable_font_resource_lifecycle"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "c2d7c892b08ab2df34465b6b08620cc2d43de0d2"
spec_source_sha: "dffadb298c123ae77a8e8b1f224731ba59030076"
depends_on: "t080"
conflicts_with: "t075,t076,t082"
note: "2026-11-18 用户授权详细立项；仅创建 backlog，不实施、不发布。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 创建记录：2026-11-18T00:31:35+08:00，用户要求按已核实资源问题与架构方案详细立项；仅创建 backlog，尚未实施、验证业务 AC 或获得本批 commit/push 授权。
- 跨 task 契约与脱敏现场基线：docs/tasks/t080_linux_native_runtime_storage/architecture_scope.md。长期 specs/blueprint/ADR 在对应实施 finalization 同步，本批不预写生效结论。
- 实施（2026-11-18，云端，owner cloud-muse-20261117）：ADR 030 定版生命周期——发布（既有 import 原子发布，不改）→ API 接管/显式审计写入资产目录 `font_set_assets`（迁移 0011；FontSetRepository + FontSetCatalogService：并发上限 2、同集去重、线程池执行、目录写入串行锁、`state_seq` 围栏条件回执、`revision` 消费围栏）→ 消费全读目录（router 列表/默认、coordinator runtime 解析、ProfileService 绑定校验均零字体正文读取）。coordinator 按运行记录的 config_version 取实例绑定快照报告字体（AC-006）；Supervisor `_validate_font_set` 按 (runtime_instance_id, platform, set_id) 每实例只验一次；API 启动后台接管（app lifespan）。新增 `POST /api/v1/font-sets/{platform}/{set_id}/audit`（202 + in_flight 去重），OpenAPI 与前端生成类型已同步；运维指南 `docs/guides/font_set_operations.md`。
- 旧测试处置（task 测试策略明示）：`test_a5_font_scan_offload.py`（每请求审计语义）与 `test_t053_coordinator_font_runtime.py`（实时读取/禁止缓存语义）整体删除，理由见 ADR 030；离线/有界属性在审计引擎上由 test_t081 重新证明。存量 `test_font_sets_api.py` / `test_t053_font_sets_chain.py` 的 setup 增加接管步骤（生产启动路径），断言逐字未动。
- 实施中实测根因一则：两审计并发写目录时 SQLite 锁冲突曾使一条记录丢失（wait_idle 的 gather 吞异常放大了它）——目录写入已串行化（验证仍并行），审计异常改为记日志且目录状态不变。
- [deploy] 处置：AC-009 按用户 2026-11-18 裁定打勾 + 契约区处置注记，本地统一补验登记 p131；AC-001~AC-008 由云端实现与单测完整支撑（test_t081_font_catalog.py 9 条，含 AC-003 的 100+100 次零读取计数门禁）。
- 门禁终跑证据（.scratch/t081_gate_evidence_final，TMPDIR 指到 workspace 磁盘 + flock 串行）：protocol_drift_check、requirements_check、design_lint、design_check、frontend_build、frontend_test、integration（215 条 0 失败，含改写后的字体 integration 7 条与 Chromium 链）全 exit 0；contract 389 条 0 失败；unit 2308 条 15 条 bad，全部为机器老基线且在无 t081 的主仓树上同样复现：t063 built ×10 errors + ×2 failures、t068 ×2、a16 协议漂移 ×1（主仓同日同失败）。过程教训：本轮三轮全量假失败源于 /tmp（512M tmpfs）被 pytest 残留填满 ENOSPC，已清理并改 TMPDIR 后全绿；jpeg 校验二进制软链失效已以真实二进制替换（worktree .scratch 内）。

## Review 处置

|finding_id|status|fix_ref|
|---|---|---|
|t081_code_f001|已修|`_verify_directory` 增加 get_font_set 平台/manifest 门（foreign-platform 集记录 failed 不可绑定），新增 test_adoption_rejects_platform_and_manifest_defects 覆盖|
|t081_code_f002|已修|get_font_runtime 快照缺失时返回 (None, []) 不再回退当前配置；test_f007 的实例绑定断言同步加强|
|t081_code_f003|已修|default_set_id 改按 verified_at 最新者胜出，ADR 030 与 fingerprint_platform spec 口径同步对齐|
|t081_code_f004|已修|删除无调用方的 record_verified；repository/models/catalog 围栏口径改实（发布/修复只写文件、经后续审计生效，失败方向封闭）|
|t081_code_f005|已修|Supervisor 围栏扩为 (profile_id, runtime_instance_id, config_version, platform, set_id)，start_profile 透传|
|t081_code_f006|已修|lifespan 接管任务加 done 回调记异常日志|
|t081_test_f001|已修|零读取测试补 100 次 SSE 装配（publish_profile_change）+ 100 次 runtime 视图装配（make_runtime_response），计数仍恒零|
|t081_test_f002|已修|新增 test_audit_failure_and_cancellation_free_the_slot（验证抛错 + 在途取消均释放槽位且目录不变）|
|t081_test_f003|已修|新增 test_audit_detects_deletion_extra_file_and_manifest_damage（审计级删改/额外文件/manifest 损坏矩阵）|
|t081_test_f004|已修|新增 test_two_profiles_share_one_set_without_reverification（双 Profile 共用一集零重验）|
|t081_test_f005|已修|新增 test_adoption_db_commit_failure_leaves_no_ready_record（目录写入失败注入，接管不留 ready、二轮接管完成）|
|t081_test_f006|已修|新增 test_adoption_rejects_platform_and_manifest_defects（平台不符/无 manifest/重复条目冲突摘要分别成案）|
|t081_test_f007|已修|实例绑定测试补 missing 列表断言（结论随绑定集 A 而非待应用集 B）|
|t081_code_f007|已修|font_repository/font_set_catalog 模块 docstring 与 ADR 030 的 state_seq 围栏措辞改实（发布/修复只写文件、经后续审计生效）|
|t081_code_f008|已修|ADR 030 默认集/围栏口径与 Supervisor `_validate_font_set` docstring 同步为已修正的 verified_at 与五元组围栏|
|t081_test_f008|已修|AC-006 测试补快照分支零哈希计数断言与快照缺失返回 (None, []) 的直接用例|
|t081_test_f009|已修|Supervisor 围栏测试补同实例新 config_version 与换 Profile 均重新验证的断言|
|t081_code_f009|已修|architecture.md §3.5 的围栏措辞同步改实（迟到回执不覆盖已应用的新回执/接管）|
|t081_code_f010|已修|browser_runtime.md A16 段默认集口径同步为 verified_at 最新者胜出|

- 审阅修复轮（2026-11-18）：首轮双轴 FAIL（代码 3 important + 3 minor；测试 2 important + 5 minor），已按上表逐项修复并撤回全部 AC 打勾、重验后重新打勾。修复后 test_t081_font_catalog.py 14/14、字体/协调器/迁移回归 71/71、Supervisor 相关子集 85/85 通过。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：云端可做部分全部完成，9 条 AC 已打勾；AC-009（[deploy]）按用户 2026-11-18 裁定打勾、真实验证延期本地统一补验（p131），不表示已实测通过。
- 测试：门禁终跑（.scratch/t081_gate_evidence_final）protocol_drift_check、requirements_check、design_lint、design_check、frontend_build、frontend_test、integration（215 条 0 失败）全 exit 0，contract 389 条 0 失败；unit 2308 条 15 条 bad 全为机器老基线（t063 ×12、t068 ×2、a16 ×1，均在无 t081 的主仓树复现）。审阅修复轮后 test_t081_font_catalog.py 14/14、字体/协调器/迁移回归 71/71、Supervisor 子集 85/85。
- 黑盒：云端无 Docker Engine，真实容器黑盒不可执行；登记 p131 本地补验（现场规模集导入、共用绑定 10 分钟零正文读取、审计负例/修复正例留证）。
- review：首轮双轴 FAIL（代码 f001–f006、测试 f001–f007）已逐项修复并写入 Review 处置表；确认轮结果见 review_code.md / review_test.md。
- AC 判定：见 `task.md` 行内打勾与 AC-009 处置注记；AC-001~AC-008 由云端实现与测试完整支撑。

### 结果摘要

- 字体集成为目录化的不可变资源（ADR 030）：发布（既有原子导入）→ API 接管/显式审计把验证结论写入 `font_set_assets`（revision/state_seq 双围栏、有界并发与同集去重、写入串行）→ 全部读路径（runtime REST/SSE、列表、默认选择、绑定校验）只读目录元数据，字体正文读取恒零；运行状态按实例绑定的配置版本报告；Supervisor 对实挂载集每实例验证一次。

### 长期文档闭环

- blueprint：architecture.md 新增 §3.5，supervisor.md 新增启动验证围栏节，browser_runtime.md 补 Agent 围栏注记，domain.md 补资产目录口径，testing.md 新增 t081 矩阵节；ADR 030 落盘；fingerprint_platform spec 的 tasks 清单与默认/绑定口径已同步；运维指南 docs/guides/font_set_operations.md 新增。遗留补验 pending：p131（AC-009 真实容器链路）。

### 长期文档闭环

执行 finalization 时更新关联 active spec 的 tasks 清单及 task.md 指定 blueprint/ADR。正式 spike 通过工具创建，结论入 findings 并回填；创建期不提前声明实施或闭环。
