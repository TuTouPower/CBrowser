---
tid: "t013"
slug: "v2_profile_copy_reset"
title: "实现 Profile 配置复制、状态复制与重置"
status: "done"
branch: "t013_v2_profile_copy_reset"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "986d3e2c1ff7783b6b66606e6591998e449f8b68"
depends_on: "t008"
conflicts_with: "t014"
note: ""
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

2026-11-02T11:20:00+08:00：attempt=1，execution_id=5ad8c70c1adf4e12a7bfb44f451323ef，owner_id=opencode_t013_6092c004fd49。实现配置复制（保留全部配置/标签/种子，不复制用户数据与 Artifact）、状态复制（源 stopped 校验、跳过 Singleton 文件、SHA-256 清单校验、复制后复检运行状态）、重置（用户数据目录原子备份/回滚、重新生成指纹种子并新增配置版本、保留 Artifact 与其他 Profile）、Idempotency-Key 与前端确认面板。

无

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round N (YYYY-MM-DDThh:mm:ss+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t000_code_f001|critical/important/minor|已修/遗留/撤回|一句话|文件:行 / pNNN / tid|

无 finding 时写“Round N 零 finding”。

### Round 1 (2026-11-02T12:35:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t013_code_f001|critical|已修|名称经 strip/非空/255 截断并由 ProfileConfig 校验；HTTP 非法名返回 400 且列表不中毒|src/backend/cbrowser/services/profile_service.py; src/backend/cbrowser/api/v1/router.py; tests/unit/test_profile_copy_reset.py|
|t013_code_f002|important|已修|状态复制后递归收敛 UID/GID 与目录/文件权限，宿主开发回退可读写|src/backend/cbrowser/services/profile_service.py; tests/unit/test_profile_copy_reset.py|
|t013_code_f003|important|已修|仅 desired 与 observed 均为 stopped 才允许；前端同步禁用|src/backend/cbrowser/services/profile_service.py; src/frontend/src/features/profiles/ProfileDetailPage.tsx; tests/unit/test_profile_copy_reset.py|
|t013_code_f004|important|已修|审计按 action/source/payload 校验；reset 用稳定派生种子；锁内预检；跨 action 409|src/backend/cbrowser/services/profile_service.py; src/backend/cbrowser/adapters/database/repository.py; tests/unit/test_profile_copy_reset.py|
|t013_code_f005|important|已修|复制/建行失败与取消清理 staged 目录；同键并发不复制；失败/并发测试|src/backend/cbrowser/services/profile_service.py; tests/unit/test_profile_copy_reset.py|
|t013_code_f006|important|已修|源目录不存在时按空状态复制，不再 500 或留空目录|src/backend/cbrowser/services/profile_service.py; tests/unit/test_profile_copy_reset.py|
|t013_code_f008|important|已修|重置备份删除失败记录日志并返回错误，不静默成功|src/backend/cbrowser/services/profile_service.py|
|t013_code_f009|minor|已修|重置面板列出书签/历史/密码/扩展等全部清除范围|src/frontend/src/i18n.tsx|
|t013_test_f001|critical|已修|非法空白名与 255 字符源名默认克隆名测试；列表保持 200|tests/unit/test_profile_copy_reset.py; tests/integration/test_profile_copy_reset_api.py|
|t013_test_f002|critical|已修|并发同键状态复制断言单 Profile 且无孤儿目录|tests/unit/test_profile_copy_reset.py|
|t013_test_f003|important|已修|同键不同 include_browser_state/name 断言 409|tests/unit/test_profile_copy_reset.py|
|t013_test_f004|important|已修|并发同键 reset 断言同一结果与新种子|tests/unit/test_profile_copy_reset.py|
|t013_test_f005|important|已修|E2E 改走真实 HTTP API duplicate/reset + 真实容器 Cookie；前端 Vitest 覆盖面板与调用|tests/e2e/test_browser_runtime_e2e.py; src/frontend/src/app/router.test.tsx|
|t013_test_f006|important|已修|manifest 不一致、复制后源运行、复制中途 OSError 清理测试|tests/unit/test_profile_copy_reset.py|
|t013_test_f007|important|已修|源 Profile 预置 Artifact，断言两种复制均不复制且源 Artifact 保留|tests/unit/test_profile_copy_reset.py|
|t013_test_f008|minor|已修|前端确认前不执行、确认后执行并断言完整清除文案|src/frontend/src/app/router.test.tsx|
|t013_test_f009|minor|已修|全量 config 比较与配置版本快照断言|tests/unit/test_profile_copy_reset.py|
|t013_test_f010|minor|已修|三种 Singleton 文件均断言跳过；源目录 manifest 比较；observed stopping 拒绝|tests/unit/test_profile_copy_reset.py|
|t013_test_f011|minor|已修|重置断言 config version 2 与快照种子|tests/unit/test_profile_copy_reset.py|

### Round 2 (2026-11-02T12:55:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t013_code_f007|important|已修|bind_runtime_instance 纳入同一 per-Profile 锁；reset 移动目录后再次校验 stopped|src/backend/cbrowser/services/profile_service.py|
|t013_code_f010|critical|已修|权限收敛跳过符号链接并使用 follow_symlinks=False；新增逃逸回归测试|src/backend/cbrowser/services/profile_service.py; tests/unit/test_profile_copy_reset.py|
|t013_code_f012|minor|已修|删除无调用的 get_profile_by_operation|src/backend/cbrowser/adapters/database/repository.py|
|t013_code_f013|minor|已修|duplicate OpenAPI 增加 400 并重新导出/生成类型|src/backend/cbrowser/api/v1/router.py; schemas/openapi/cbrowser_v1.json|
|t013_test_f013|minor|已修|E2E 断言 clone current_config_version 与 fingerprint_seed|tests/e2e/test_browser_runtime_e2e.py|
|t013_test_f014|minor|已修|配置版本快照与 clone.config 整体比较|tests/unit/test_profile_copy_reset.py|
|t013_test_f016|minor|已修|空白名负例断言列表长度仍为 1|tests/integration/test_profile_copy_reset_api.py|
|t013_test_f018|minor|已修|Artifact 测试创建真实 storage 文件并断言不复制|tests/unit/test_profile_copy_reset.py|

### Round 3 (2026-11-02T13:05:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t013_code_f011|minor|已修|duplicate 失败清理改用 \_cleanup_copy，记录 warning 且不覆盖主异常|src/backend/cbrowser/services/profile_service.py|
|t013_code_f014|minor|遗留|长复制阻塞 Supervisor bind 超过客户端 10s 的窄竞争，服务端最终一致；交由 t009 压力/并发验收覆盖|t009|
|t013_test_f012|minor|撤回|config-only 前端动作已测；with-state UI 分支由真实 HTTP API + 容器 E2E 覆盖，纯 minor 覆盖扩展不阻断|—|
|t013_test_f015|minor|已修|状态复制用例增加源/副本 \_manifest 全量比较|tests/unit/test_profile_copy_reset.py|
|t013_test_f017|minor|撤回|确认前不执行与关键数据项已测；运行中禁用由 API 409 与按钮 disabled 实现保证，文本全量属 minor 扩展|—|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：unit 489 passed；integration 85 passed；frontend Vitest 117 passed（16 files）；tsc -b 通过；Ruff E/F/W/I 与 format 通过；OpenAPI 与 generated types 已更新；contract 167 passed + 2 known pre-existing failures（test_task_archive_dir，用户已确认搁置）。
- 黑盒：真实 uvicorn API + 临时 SQLite + 真实 HTTP duplicate/reset + 真实 Chrome Browser Runtime E2E `test_t013_state_copy_restores_cookies_in_clone` 1 passed：源设置 Cookie 后优雅停止、经 API 含状态复制、重建 clone 容器读取 Cookie、经 API 重置源并断言目录清空与种子变化；同时验证 1280x720 容器可启动.
- review：Full 两轴 Round 4 均 PASS，零 blocking，Round 1/2/3 critical/important 全部闭合；minor f014 遗留 t009，f012/f017 撤回（覆盖扩展）；reviewed_scope=68994e2bb7fa7d48。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 交付配置复制/状态复制/重置服务与 API、前端确认面板、幂等键与并发/故障清理；无本 task 未闭环 blocking。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
