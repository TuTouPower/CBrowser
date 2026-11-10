---
tid: "t050"
slug: "sandbox_compose_grouping"
title: "Profile 沙箱容器聚合到独立 compose 分组"
status: "done"
branch: "t050_sandbox_compose_grouping"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "4aae2d122a2c91d4c5f934caeceada87e6326f26"
depends_on: ""
conflicts_with: ""
note: "用户需求：所有 Profile 沙箱在 Docker UI 统一聚合到 <prefix>-profiles 分组，同时保持部署 prefix 冲突判断与清理语义"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 2026-11-10T16:50:00+08:00 实施

- 编号：`profiles.display_number` 唯一列（迁移 0005，按 created_at,id 回填 1..N）；repository 创建时取 max+1；删除不复用。API Profile/内部 runtime 暴露 `display_number`，Coordinator 启动请求带 `profile_number`，Supervisor `StartProfileRequest` 必填。
- 命名与标签：`<prefix>-<NNNN>-browser|stream`，新增 `com.cbrowser.profile-number` 与聚合标签 `com.docker.compose.project=<prefix>-profiles` / `service=browser|stream`；adapter 从容器标签恢复编号，扫描/启动/停止不依赖 UUID 命名。
- 部署：`scripts/deploy.sh` prefix 冲突检查放行 `<PROJECT>-profiles` + sandbox 角色；fake Docker CLI 覆盖放行与异项目拒绝。
- 前端：Profile 卡片/表格显示 `#NNNN`；重新生成 OpenAPI TS 类型与 dist。
- 验证：unit 1601 passed；integration 178 passed / 18 skipped；frontend 499 passed；build 通过；`scripts/deploy.sh deploy` readiness ready；真实 Profile 停止→启动后容器为 `cbrowser-0001-browser/stream`，标签含 `profile-number=0001` 与 `cbrowser-profiles`，Profile 名称/配置版本不变，observed=running。
- Round 1 复审修复后：unit 1607 / integration 178 / frontend 499 全绿；重新 deploy 成功；用最终代码停止 Profile 后 `cbrowser-0001-*` 容器被正确删除，再启动复用 0001 且 observed=running（AC-003/006 实测）。
- 迁移注意：升级时旧 UUID 命名沙箱不带编号标签，扫描会拒绝；需停止→启动一次完成迁移（本机已执行）。启动过程中曾遇一次 supervisor 内存 session 残留导致 409，重启 supervisor 后恢复；属既有启动失败残留路径，另行记录。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-10T17:00:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t050_code_f001|critical|已修|cleanup_container_by_name 改用 profile-number 推导期望名，停止/替换可正确删除新命名容器|docker_adapter.py:1713|
|t050_code_f002|important|已修|新增 profile_display_sequence 单调分配表，删除最大编号后不复用|migrations/0005, repository.py:211|
|t050_code_f003|important|已修|deploy 冲突放行比较改为 `$PREFIX-profiles`，与沙箱标签一致|deploy.sh:387|
|t050_code_f004|important|已修|移除 adapter 静默编造编号；Recovery 从 profile_info.display_number 传入|docker_adapter.py:650, recovery_coordinator.py:595|
|t050_code_f005|important|已修|实例观察改为按 prefix/profile/role 标签查 Browser，不再拼名字|core.py:1793|
|t050_code_f006|important|已修|ProfileRuntimeResponse.display_number 改为必填 int；ProfileRuntime 携带编号|domain/models.py:221,694|
|t050_code_f007|important|已修|迁移 0005 纳入暂存与交付 diff|-|
|t050_code_f008|minor|已修|Profile 列表与表格显示 #NNNN|-|
|t050_code_f009|minor|已修|移除 `m.display_number or 1` 静默兜底|-|
|t050_test_f001|critical|已修|新增迁移回填/新分配/删除不复用测试；迁移文件纳入交付|test_domain_and_repository.py|
|t050_test_f002|important|已修|新增 StartProfileRequest/ProfileRuntimeResponse 字段测试|test_t050_sandbox_grouping.py|
|t050_test_f003|important|已修|新增 0007 精确命名断言；部署后重启编号不变由真实验证记录|test_t050_sandbox_grouping.py|
|t050_test_f004|important|已修|移除 fallback；新增编号标签解析正负例；标签恢复由 scan 路径与真实 inspect 验证|test_t050_sandbox_grouping.py|
|t050_test_f005|important|已修|前端 EnvironmentListPage 断言 #0001/#0002；前端测试全绿|EnvironmentListPage.test.tsx|
|t050_test_f006|important|已修|deploy 放行用例改为 prefix≠project 场景，验证比较键为 prefix|test_t027_release_controller.py|
|t050_test_f007|minor|已修|放行用例断言 build 继续（returncode 0）|test_t027_release_controller.py|
|t050_test_f008|minor|已修|progress 记录真实部署即停止→启动、配置版本/名称不变、readiness ready|本文件实施笔记|

### Round 2 (2026-11-10T17:20:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t050_code_f010|important|已修|runtime 幂等/观测返回改为按 Profile 读真实编号（`_runtime_with_number`），不再默认 1|repository.py:975|
|t050_code_f011|minor|已修|实例观察过滤增加 instance-id|core.py:1798|
|t050_test_f009|important|已修|新增 0005 回填测试（created_at,id → 1..N + sequence=max）|test_control_migration.py|
|t050_test_f010|important|已修|Coordinator 启动请求断言 profile_number|test_api_runtime_coordinator.py:155|
|t050_test_f011|important|已修|同 Profile 重建编号/名称不变测试|test_t050_sandbox_grouping.py|
|t050_test_f012|important|已修|scan 标签恢复正例/缺编号负例；FakeDockerAdapter fail-closed|test_t050_sandbox_grouping.py, docker_doubles.py|
|t050_test_f013|important|已修|fake ps 校验 role 格式，新增用例|test_t027_release_controller.py|
|t050_test_f014|minor|已修|cleanup 归属校验正负例|test_t050_sandbox_grouping.py|
|t050_test_f015|minor|已修|放行断言 build 继续；非 sandbox 角色拒绝负例|test_t027_release_controller.py|
|t050_test_f016|minor|已修|真实停止删除/重启复用 0001 证据；详情页编号已完成|本文件|

### Round 3 (2026-11-10T18:00:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t050_test_f017|important|已修|删除手工 remember 的假绿测试；改为两个新 adapter 从容器标签 scan 恢复编号，名称一致且容器名≠格式化名|test_t050_sandbox_grouping.py|
|t050_test_f018|minor|已修|runtime display_number 断言 int 且 >0|test_t050_sandbox_grouping.py|
|t050_test_f019|minor|已修|deploy 放行断言 `_builds(repo)` 非空|test_t027_release_controller.py|
|t050_test_f020|minor|已修|详情页 `profile-detail-number` 断言 #0001|ProfileDetailPage.test.tsx|
|t050_test_f021|minor|已修|scan 测试容器名改为 legacy，证明编号来自标签|test_t050_sandbox_grouping.py|
|t050_test_f022|minor|已修|FakeDockerAdapter 未 remember 时抛错负例|test_t050_sandbox_grouping.py|
|t050_test_f023|minor|已修|Coordinator 用第 2 个 Profile（编号=2），杜绝硬编码 1|test_api_runtime_coordinator.py|
|t050_code_f012|minor|已修|get_runtime 不再回退 1；缺编号即报错|repository.py:612|
|t050_code_f013|minor|遗留|抽取标签定位 helper 属重构，不影响本 task 行为，转 p058|p058|

Round 4 复核前：unit 1613、integration 178、frontend 499、build 通过。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：unit 1613 passed；integration 178 passed / 18 skipped；frontend 499 passed；前端 build 通过
- 黑盒：真实 `scripts/deploy.sh deploy` readiness ready；Profile 停止删除 `cbrowser-0001-*`，重启复用 0001 且 observed=running；容器标签含 profile-number 与 cbrowser-profiles
- review：full 两轴 Round 4 PASS（reviewed_scope 9c4cae2a9465a9d9）
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 待执行时填写；遗留只写引用，不复制正文

### 长期文档闭环

在 specs_index 行的 task 清单中登记当前 tid（格式见 `.repo_template/docs/usage.md`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
