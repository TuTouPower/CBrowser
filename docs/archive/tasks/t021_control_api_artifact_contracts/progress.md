---
tid: "t021"
slug: "control_api_artifact_contracts"
title: "统一控制 API 与文件交换契约"
status: "done"
branch: "t021_control_api_artifact_contracts"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "a644f7c3df22c65482cca22b2f10e3b507bc21c4"
depends_on: ""
conflicts_with: "t020"
note: "review_20261103_185924：A2/A4/A5/A6/A7/A12/A31/A40/A41/A42/A46/A54；用户授权分组立项，不实施"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

2026-11-03：用户授权按职责合并立项，本 task 为 53 项采纳结论中 12 项的唯一主承接；完整范围与 AC 对应见 task.md。现有 t019/t020 保留，原 A36/A37 拒绝；本轮未 start、未实现、未跑业务测试。

创建验证：`task.py preflight t021 --creation` 为 PASS；工作区未提交提示属于本批新建文档。无待外部用户决定的产品选项。

2026-11-04 实施（attempt 1，execution_id 2ea8f300c33449ff8c033b3315f07973，owner exec-main-20261104-t021，base=t020_profile_font_bundles@a644f7c）：按 TDD 逐项落地 A2/A4/A5/A6/A7/A12/A31/A40/A41/A42/A46/A54，12 条 AC 全部实现并打勾。要点：

- A2：删除 ProfileUpdateRequest 的 normalize 过滤器（保留严格校验）；ProfileConfig 对显式 null 的 launch_args/extension_paths 归一为 []，修复合并路径 null→500；PATCH 三态（absent/null/list）由 HTTP 参数化测试钉住。
- A4/A46：四集合关系 noload+passive_deletes，普通读取显式 selectinload(tags)；Artifact 存在性改标量查询、下载去重下推 SQL；幂等审计匹配收敛单一 helper，删后重放语义定版（update→None、create→按审计 entity_id 确定性重建含竞争恢复）；utc_now_iso 收敛领域单一实现。
- A5：Argon2 校验/哑元/bootstrap 哈希全部 asyncio.to_thread 卸载，阻塞探针测试（慢哈希下 ticker 推进）钉住。
- A6：新建 cbrowser/service_errors.py 的 ServiceNotConfiguredError，内部三面未配置统一 503 service_not_configured/retryable=false；database_busy 保留。
- A7：Referer 回退加 urlsplit ValueError 防护，畸形 Referer 403 不 500；Referer-only 同源放行用例证明进入来源校验分支。
- A12：下载游标仅在完整成功扫描后修剪，glob 失败 profile 豁免修剪、早退不修剪；单例锁名单改引 volume_spec.SINGLETON_LOCK_NAMES 单一来源。
- A31：runtime DTO 状态改领域枚举；OpenAPI 后处理按路径标注 Supervisor/Gateway 真实 scheme 并删除通用 serviceBearer；重新导出双 OpenAPI 与前端类型。连带修复：前端 useBrowserSession 删除已不存在的 failed/ready 死比较（枚举定版后 tsc 报错，行为不变）。
- A40：Artifact 删除两阶段状态机（迁移 0008 delete_requested_at；意图→删文件→删行，lifespan 启动续跑，逃逸路径拒绝保留意图）；下载入库实例信任（当前绑定或 runtime_events 历史，未知→rejected）；授权审计全类别覆盖，未知/非法令牌按 (reason, source) 有界聚合（不存令牌/哈希），成功授权不再清除限速失败记录。两处旧测试断言与新政策冲突，按政策变更整体改写并注明（聚合审计断言、ingest 集成用例先绑定实例 i1）。
- A41：三协议导出统一为 $defs 规范定义 + messages 按名索引（$id+$ref）+ 文档 version（supervisor 1.0.0 / runtime agent 2.0.0 / stream v2），删除顶层 anyOf；$id 经实测不能放进 $defs（会改变嵌套 $ref 解析），故置于 messages 条目、$defs 保持规范原样；stream 测试改按消息入口逐条校验，supervisor/runtime 补同类入口测试；export_openapi.py 补尾换行。
- A42：运行事件日志迁入包内 cbrowser/runtime_event_log.py，删除顶层 diagnostics.py（其余内容无引用方，已全仓 grep 核实）；删除 internal automation-authorize 路由/DTO/内部 OpenAPI 条目与网关 fixture 假面（真实 CDP 入口为 v1 automation_router）；authorize_viewer 双边 normalize_origin 归一化；删 gateway api_client 冗余 .strip()。
- A54：删除 DANGEROUS_CONTENT_TYPES 拒绝与下载侧 octet-stream 强制重标，两入口共用 validate_content_type 规范化（去参数/小写/缺省/非法 header 值拒绝）；旧政策测试按裁决整体删除并换新政策测试（unit 拆 quota-only + 可执行上传/下载保留声明类型、integration 拆 oversize-only + 可执行 round-trip）。

环境与门禁：本机无 Docker，E2E 黑盒按用户 2026-11-03 指令跳过按 pass 计，真实环境义务立 p023。/tmp 为 512M tmpfs，门禁 TMPDIR/UV_CACHE_DIR 指向 ~/workspace/.gates-t021；本机 root 运行，chmod 类故障注入以 monkeypatch 替代。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-04T02:19:53+08:00，reviewed_scope d730af7080310f72)

code 路与 test 路均 verdict PASS；共 8 条 finding，全部 minor（critical/important 0）。处置后内容变更使 Round 1 指纹过期，Round 2 在最终指纹上重签。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t021_code_f001|minor|已修|采纳「写回契约」方案：HTTP 行为不变（完成后重复 DELETE 为 404），删除 docstring 的无条件幂等措辞，口径定版为「意图未完成期间重试幂等、完成后 404」并写入 blueprint/specs，补完成后重复删除断言|artifact_service.py delete docstring；docs/blueprint/artifacts.md；docs/specs/storage_and_artifacts.md；test_artifact_service.py::test_delete_after_completion_reports_not_found|
|t021_code_f002|minor|已修|未知令牌聚合审计改尽力而为：写失败记日志吞掉，授权仍返回原拒绝原因且限速计数不跳过；补 DB 故障注入回归|auth/service.py \_audit_unknown_token_denied；test_auth_service.py::test_unknown_token_audit_failure_keeps_clean_denial|
|t021_code_f003|minor|已修|resume_pending_deletions 对清单读取失败改为记 warning 返回 0，启动续跑严格尽力而为、意图留待下次启动|artifact_service.py resume_pending_deletions；test_artifact_service.py::test_resume_survives_pending_list_failure|
|t021_test_f001|minor|已修|补确定性竞争注入：审计预检首呼必失手制造真实 audit 主键 IntegrityError，调用计数断言证明走恢复分支（第二次匹配）而非顺序重放|test_repository_idempotency.py::test_create_commit_race_recovers_through_integrity_error|
|t021_test_f002|minor|已修|补 DB 阶段失败注入（文件已删、删行首呼抛错→意图保留→resume 收敛）与完成后重复删除语义断言（同 code_f001）|test_artifact_service.py::test_delete_db_stage_failure_keeps_intent_and_resume_completes|
|t021_test_f003|minor|已修|runtime/supervisor 两协议补齐全量逐消息 valid 包入口校验（各 7 条），五份导出文件补「恰一个尾换行」断言|test_supervisor_schema.py；test_runtime_agent_protocol_export.py|
|t021_test_f004|minor|已修|补 emit_runtime_event_log 的 caplog 直测（净化 id/reason、不含原始值）；打包（wheel/镜像）级导入验证并入真实环境清单|test_exit_reason_allowlist.py::test_emit_runtime_event_log_writes_sanitized_json；p023|
|t021_test_f005|minor|已修|新增 useBrowserSession hook 级测试：五种 observed_state 的 stage 迁移全覆盖|src/frontend/src/features/browser-session/useBrowserSession.test.tsx|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：12 条 AC 全部实现并验证通过（见 task.md 行内打勾）
- 测试：模板契约 169 passed；v2 unit 610 passed + 2 failed（test_repo_hygiene home 路径口径、test_runtime_persistence_guards terminal_storage_failure——与干净 main c7ec89b 及 base a644f7c 基线同 ID，为存量失败，零新增；610 含 review Round 1 处置新增的 7 条测试）；integration 105 passed + 1 failed（test_ac009_api_supervisor_start_and_stop_coordination，已在干净 base a644f7c 同签名复现，为存量失败，非本 task 回归）；前端 Vitest 102 passed（97 + hook 新测 5）、npm run build 通过；git diff --check 通过；md_format 漂移仅存量 review 归档文件，本 task 文档无漂移
- 黑盒：E2E（CBROWSER_RUN_E2E=1）依赖 Docker/真实拓扑，本机无 Docker，按用户 2026-11-03 指令跳过按 pass 计；真实环境执行义务见 p023
- review：full review 见 Review 处置节
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 控制 API 与文件交换契约统一完成：PATCH 三态与严格校验、Argon2 非阻塞、内部服务未配置 503 与双令牌身份、Referer/Origin 归一化、状态枚举与 OpenAPI 身份标注、协议文档消息入口约定、事件日志入包、无消费者授权面删除、Artifact 可恢复删除/实例信任/审计聚合、内容类型统一规范化。
- 遗留：p023（真实环境 E2E 执行义务）；基线存量失败 3 条（unit 2 + integration 1）不在本 task 范围，未动。

### 长期文档闭环

- specs_index：storage_and_artifacts、runtime_persistence、access_control、profile_management 四行关联 task 列已加 t021 并更新时间。
- blueprint 已按 task.md 清单更新六篇：domain（字段校验/null/幂等/时间语义）、artifacts（任意内容/附件传输/删除意图/可信历史实例）、persistence（删除状态与迁移/查询加载边界）、security（服务身份/审计脱敏/canonical Origin）、automation（删除无消费者授权面）、testing（真实入口/故障/幂等验证要求）。
- specs 已补 t021 小节：storage_and_artifacts §2.5、access_control「内部服务身份、Origin 与审计」、profile_management「启动参数校验与 PATCH 三态」、runtime_persistence「幂等与加载边界」。

## 接管复核（2026-11-04，attempt 1 同一 execution_id 2ea8f300c33449ff8c033b3315f07973，owner exec-main-20261104-t021-r2 经 --replace-owner --confirm-stopped 接管）

原执行者会话结束无最终回报，接管方对交付内容独立复核后收尾，结论与原记录一致，未发现实质缺陷：

- 指纹：当前 worktree 以 monitoring.review_scope_fingerprint 实算为 7b5dc5f73d104653，与 Round 2 双路重签的 reviewed_scope 逐字一致——交付内容自重签后未变，review 闭环在最终内容上成立。
- 门禁全量重跑（.scratch/run_tests.sh 分层，与 run_gates.sh 同命令）：模板契约 169 passed；unit 610 passed + 2 failed（test_repo_hygiene home 路径、test_runtime_persistence_guards terminal_storage_failure，与原记录同 ID 的基线存量失败，零新增）；integration 105 passed + 1 failed（test_ac009_api_supervisor_start_and_stop_coordination，同基线存量）；前端 Vitest 102 passed；npm run build 通过；git diff --check 通过（排除 docs/archive）。黑盒 E2E 沿用用户指令跳过按 pass 计，义务在 p023。
- diff 全量过目：62 文件全部落在 task.md 范围（控制 API/鉴权/仓储/Artifact/协议导出/生成物/blueprint/specs/finalization/p023），迁移 0008 对称可逆，核心实现（删除两阶段、Argon2 to_thread、审计聚合包装）抽查与 review 记录相符。
- 复核中发现并修正两处过程文件瑕疵（均属指纹排除的过程文件，不影响 reviewed_scope）：①本 note.md 自身存在 md_format 漂移（上方收尾报告「本 task 文档无漂移」一句不确，特此更正），已用 md_format.py 格式化至 --check 通过；其余漂移均为存量 review 文件，未动。②review_test.md Round 2 的 reviewed_scope 行误用全角冒号，check_review_status 无法解析而报 stale，已改为半角冒号（值与声明未变），复查 check_review_status 输出 overall=PASS、review_scope=ok、next_action=finalize。
- preflight --require-verified（owner exec-main-20261104-t021-r2）PASS。
