---
tid: "t008"
slug: "v2_artifacts_automation"
title: "打通 Artifact 文件管理与受控 CDP 自动化"
status: "done"
branch: "t008_v2_artifacts_automation"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "63cbd08e40e5b0448829d06d1faed5851ce973ca"
depends_on: "t007"
conflicts_with: ""
note: ""
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

2026-10-27T15:36:10+08:00：独立覆盖度审查后拆分，原AC-003/004转t014，原AC-005转t013；t008不复用移出编号，完整验收t009依赖两者完成。只维护backlog契约，未实施。

2026-11-02T08:34:30+08:00：用户恢复冻结队列，模型改为opencode-go/deepseek-v4.1-flash/high。attempt=1，execution_id=4fa03b7185dd48399174522182fc4c4d，owner_id=codex_t008_e066017f083d41fb。复用d002已有UDS/CDP真实实验结论，正式接入按本task AC验证；不再补修两处已暂搁基线清理失败，不扩大全库lint/测试。

2026-11-02T09:11:35+08:00：原 owner 会话停止，主控以 owner_id=opencode_t008_a18fb03ee4d7 经 `attempt claim --replace-owner --confirm-stopped` 接管同一 attempt。接管时工作区已有 Artifact Repository/Store/Service/API、下载对账、Supervisor 转发与前端占位页；接管后补齐：Profile ID 路径校验、上传后总量配额、路径+校验和去重、内部 ingest 的 ArtifactError 映射、大小写 Bearer、旧 CDP 薄适配入口、前端 `/profiles/:id/files` 与 `/automation/:id` 实际页面。删除两个占位组件。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round N (YYYY-MM-DDThh:mm:ss+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t000_code_f001|critical/important/minor|已修/遗留/撤回|一句话|文件:行 / pNNN / tid|

无 finding 时写“Round N 零 finding”。

### Round 1 (2026-11-02T10:30:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t008_code_f001|critical|已修|Supervisor 镜像补 websockets 17.4，重建后导入验证通过|config/docker/supervisor_runtime/requirements.{in,txt}|
|t008_code_f002|critical|已修|forwarder 改为持久化已处理 event_id 集合，新增乱序 completed 用例|src/backend/cbrowser/supervisor/artifact_forwarder.py; tests/unit/test_download_reconciler.py|
|t008_code_f003|important|已修|下载 MIME 不再套用上传危险类型 denylist，未知/危险类型记 octet-stream|src/backend/cbrowser/services/artifact_service.py; tests/unit/test_artifact_service.py|
|t008_code_f004|important|已修|下载去重仅按 storage_path + sha256，同名不同路径视为新文件|src/backend/cbrowser/adapters/database/artifact_repository.py; tests/unit/test_artifact_service.py|
|t008_code_f005|critical|已修|DB 写入失败时把已移动文件移回下载源，不删除用户文件|src/backend/cbrowser/services/artifact_service.py; src/backend/cbrowser/adapters/filesystem/artifact_store.py; tests/unit/test_artifact_service.py|
|t008_code_f006|important|已修|Artifact 子目录/文件按 runtime UID/GID 发布并回退可读权限；E2E 验证容器可读 uploads|src/backend/cbrowser/adapters/filesystem/artifact_store.py; tests/e2e/test_browser_runtime_e2e.py|
|t008_code_f007|minor|已修|下载路由声明 FileResponse 与 octet-stream binary schema|src/backend/cbrowser/api/v1/artifact_router.py; schemas/openapi/cbrowser_v1.json|
|t008_code_f008|minor|已修|删除无生产调用的 scan_downloads/iterate_completed_downloads/\_get_auth_service|src/backend/cbrowser/services/artifact_service.py; src/backend/cbrowser/adapters/filesystem/artifact_store.py; src/backend/cbrowser/api/v1/automation_router.py|
|t008_code_f009|minor|已修|下载完成哈希改为 asyncio.to_thread，不再阻塞 CDP 事件循环|src/backend/cbrowser/runtime_agent/cdp_proxy.py|
|t008_code_f010|minor|已修|恢复 tsconfig.tsbuildinfo 到基线，不纳入本 task diff|src/frontend/tsconfig.tsbuildinfo|
|t008_code_f011|minor|已修|移除 CBROWSER_ARTIFACTS_DIR；API 读取 ARTIFACT_MAX\_\* 与 compose 一致|src/backend/cbrowser/api/app.py; docs/blueprint/artifacts.md|
|t008_code_f012|minor|已修|Profile 删除后的 Artifact 清理改为 best-effort 告警|src/backend/cbrowser/api/v1/router.py|
|t008_test_f001|important|已修|E2E 真实 Chrome 下载->forwarder->真实 API DB 断言 Artifact|tests/e2e/test_browser_runtime_e2e.py|
|t008_test_f002|important|已修|E2E 重启扫描->forwarder->API 断言补登 Artifact，且重复重启不重复|tests/e2e/test_browser_runtime_e2e.py|
|t008_test_f003|important|已修|volume 单测断言 /exchange/uploads；E2E 挂载并在容器内读取上传文件|tests/unit/test_refactor_behavior_equivalence.py; tests/e2e/test_browser_runtime_e2e.py|
|t008_test_f004|important|已修|集成测试 control WS -> 真实 Agent app -> fake Chrome 完整 CDP 往返；真实 Agent/Chrome 由既有 UDS E2E 覆盖|tests/integration/test_automation_cdp_flow.py|
|t008_test_f005|important|已修|磁盘空间用例改为具体异常、size_hint 与实际 free 组合|tests/unit/test_artifact_service.py|
|t008_test_f006|minor|已修|删除后断言磁盘目录消失；前端删除后断言行消失|tests/integration/test_artifacts_api.py; src/frontend/src/features/artifacts/ProfileFilesPage.test.tsx|
|t008_test_f007|minor|已修|补 list/download/delete 401 负例与 automation 无 Authorization 负例|tests/integration/test_artifacts_api.py; tests/integration/test_automation_api.py|
|t008_test_f008|minor|已修|entrypoint 断言排除注释行|tests/unit/test_selkies_file_transfers.py|

### Round 2 (2026-11-02T11:00:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t008_code_f013|important|已修|401/403/408/429 改为可重试，不持久化 processed；name 截断到 255；新增 401→恢复重试用例|src/backend/cbrowser/supervisor/artifact_forwarder.py; tests/unit/test_download_reconciler.py|
|t008_code_f014|minor|已修|蓝图去重键改为 storage_path；删除未使用的 name 参数|docs/blueprint/artifacts.md; src/backend/cbrowser/adapters/database/artifact_repository.py|
|t008_test_f009|minor|撤回|255 字符截断属防御性边界；已有 4xx 重试与 API schema 覆盖，单独单测收益低，且避免终审后改测导致 scope 失效|—|

### Round 3 (2026-11-02T11:15:00+08:00)

code/test 两轴 PASS，零 finding。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：unit 469 passed；integration 79 passed；frontend Vitest 116 passed（16 files）；tsc -b 通过；Ruff E/F/W/I 与 format 通过；OpenAPI 与 runtime agent protocol 重新导出并与应用一致；contract 167 passed + 2 known pre-existing failures（test_task_archive_dir，用户已确认搁置）。
- 黑盒：真实 uvicorn API + 临时 SQLite + Supervisor control + 真实 Agent app/fake Chrome 集成 13 passed；真实 Chrome Browser Runtime E2E `test_t008_download_reconcile_after_agent_restart` 1 passed（真实下载→forwarder→API Artifact DB→重启扫描补登，容器内 /exchange/uploads 可读）；既有 t003 真实下载/恢复 E2E 1 passed；Supervisor 镜像重建后 `import cbrowser.supervisor.control_server` 与 websockets 17.4 通过。
- review：Full 两轴 Round 3 均 PASS，Round 1/2 全部 critical/important 已修，零 blocking；minor t008_test_f009 撤回；reviewed_scope=80bdf0894cda099f（code 轴 checker PASS/review_scope ok）。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 交付 Artifact Repository/Store/Service/API、独立自动化 CDP 入口、下载事件校验和与 Agent 重启对账、Selkies file_transfers=none 证据，以及 /profiles/:id/files 与 /automation/:id 实际页面；无本 task 未闭环遗留，文件选择器可达性待确认登记 p014。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
