---
tid: "t040"
slug: "environment_preview_thumbnails"
title: "环境实时缩略图"
status: "done"
branch: "t040_environment_preview_thumbnails"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "d9e0843545275d26f64d7b2932fa933c4e3263fb"
depends_on: "t037"
conflicts_with: "t038,t039"
note: "来源 plan_20261105_ui_redesign WP13"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 前置 spike（s016 / d035）

- t040 `UNVERIFIED-SPIKE` 用当前产品 Browser Runtime 镜像（同 Chromium 146 引擎）在容器内实测两组：headless 与容器 Xvfb 虚拟显示，均不弹宿主窗口、不抢焦点。结论：CDP `Target.getTargets` 无 active/foreground 字段、页面 visibility/focus 在多标签下恒真，「当前活动标签页」须由产品自维护；`Page.captureScreenshot` 对前台/后台页均返回有效 JPEG 且截图前后可见性/焦点/页面事件/target 列表不变，只截 viewport。材料 `docs/spikes/s016_cdp_active_tab_capture_probe/`（report + 两份 probe + run 脚本 + 两份结果 JSON），结论 `docs/findings/d035_cdp_active_tab_capture_screenshot.md`，契约区已回填，`preflight t040 --require-verified` 严格 PASS。

### 实施（基础层 + 三个不相交并行模块）

- 基础层（主会话）：`src/backend/cbrowser/preview.py` 共享纯函数（策略文件、0600 原子写、commit 前重读 policy 丢弃迟到写入、读取校验、CDP clip.scale=480/vw）；`ProfileModel.capture_preview_epoch`（PATCH 变化 +1，不进配置版本/不暴露 DTO）、`ProfileRuntimeModel.preview_captured_at`；`ProfileRuntimeResponse.preview_captured_at`；baseline migration 加两列；`get_preview_policy` / `record_preview_capture` / `clear_preview_capture` repository 方法；OpenAPI + 前端 generated 类型重生成。TDD 红→绿：`tests/unit/test_preview.py`（12）、`tests/unit/test_preview_repository.py`（2）。
- Supervisor + Agent（子代理）：`volume_spec.py` 独立挂载 `/data/preview`（不进 user data dir）、`docker_adapter.prepare_profile_directories` 建目录、`path_validator` getter；`control_server` 新 `POST /supervisor/v1/profiles/{id}/preview-policy` + `core.apply_preview_policy`（写 policy、disabled 清预览、`/control` UDS 即时下发，instance + request_id 双重 fence）；health `details.preview_captured_at` 变化 → 校验 meta/policy → POST API 内部通知；`runtime_agent/preview_capture.py` 15s 循环（`Target.getTargets` 首个 page、`attachToTarget`、`getLayoutMetrics`、`captureScreenshot` 480px q70、不调 activate/bringToFront、日志不含内容/路径）。测试 `test_supervisor_preview_policy.py` / `test_runtime_agent_preview.py`（13）。
- API + SSE（子代理）：`preview_router.py`（登录 + FileResponse + no-store + ETag + 304 + 404）、PATCH 变化即时下发、`runtime_coordinator.publish_transient`（`profile_preview` 只实时扇出、**不进重放环**）、内部通知端点（迟到写入丢弃并清预览）、`profile_service` reset/delete 清除、停止后保留最后一帧。测试 `test_preview_router.py` / `integration/test_preview_late_writes.py`（12）。
- 前端（子代理）：`sse.ts` 解析 `event:` 按类型分发（`onPreviewEvent`）、`useProfilesQuery` 订阅刷新、`EnvironmentCard` 用 `?v=captured_at` 渲染 img / 无值占位不请求 / onError 回退；`sse_preview.test.ts` / `EnvironmentCard.preview.test.tsx`。
- 整合修复（主会话）：`ProfilePreviewEvent` DTO 归位（曾误插入 `RuntimeEventResponse` 尾部字段）、public preview 端点纳入 OpenAPI（tags 保持 `profiles` 通过契约守卫）、`bind_runtime_instance` 写初始 policy（首次启动可采集）、`publish_profile_preview` 使用契约 DTO、`agent_protocol.json` 重生成。

### 镜像与 harness 拓扑对齐（用户监督纠正）

- 问题：E2E 用固定 digest 镜像，容器内跑旧代码，worktree 的 supervisor/runtime_agent/api 改动不生效；诊断确认宿主 preview 目录空、容器无 `/data/preview` 挂载、health 无 `preview_captured_at`。
- 处置：从当前源码重建 API / Supervisor / Browser 三个运行时镜像并更新 E2E env digest；`config/docker/supervisor_runtime/Dockerfile` + `Dockerfile.dockerignore` 补 `preview.py`（否则 Supervisor ImportError 启动失败）；`scripts/export_runtime_agent_protocol.py` 产物同步。
- 用户纠正（`CBROWSER_PREVIEW_ROOT` 补丁）：撤销该专用旋钮（app.py 恢复 `data_root=resolved_db.parent`），根因是 `GatewayTopologyHarness` 把 API DB 放 `/metadata/control.db` 偏离生产 compose（`/data/cbrowser.db`、data_root 挂 `/data`）。改 harness 与生产一致：API 容器挂 `data_dir → /data`、`CBROWSER_DB_PATH=/data/cbrowser.db`，DB / artifacts / preview 同由单一数据根派生；删除 `metadata_dir` 死代码。文档/env 无该变量残留。重建镜像后 unit 1199 / E2E 2 passed。

### 验证（定向）

- unit 1199 passed、integration 144 passed / 18 skipped、frontend 61 files / 417 tests、build / design:lint 84 clean、`git diff --check` OK。
- 真实栈 E2E `tests/e2e/test_profile_preview_e2e.py` 2 passed（70s）：采集→JPEG 宽 480 / no-store / ETag / 304 / 未登录拒绝 / 0600 / 页面 marker 存活；撤销策略 404、重开恢复、停止后保留最后一帧、截图前后 visibility/focus/活动标签不变。
- 诊断证据 `.scratch/t040_diag5.log`：policy 0600、15s 周期新帧、health `preview_captured_at`、Supervisor→API 内部端点 200、runtime 响应字段更新。

### 用户监督纠正（JPEG 字节相似度 → 像素语义）

- 用户判定 E2E 用 JPEG 字节一致率 0.97 是脆弱启发式（编码非确定、阈值无语义）。撤掉 `cdp_reference` 参考截图与字节比对；改用项目现有 `pillow==13.0.0`（`config/docker/stream_runtime/requirements.txt`）在 stream_runtime 容器内解码 JPEG，校验中心 50% 区域平均色与期望色在 ±20/通道容差内、宽 480；用两个不同纯色页面（`#003300` → `#cc0000`）验证预览随当前活动标签页变色而更新。期间曾尝试把 Pillow 加进 gate 依赖组，因 `uv lock --offline` 缺 stream 组缓存失败，已撤回 `pyproject.toml` 改动（依赖契约文件保持干净，`generate_requirements.sh --check` 通过）。
- 定向 E2E 2 passed（97s）；unit 1202 passed、integration 145 passed / 18 skipped。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-08T02:10:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t040_code_f001|important|已修|`_apply_preview_policy` 吞掉全部异常、PATCH 仍 200；本地写/清预览失败改为冒泡 500，RPC 失败存 pending 并由 `trigger_reconcile` → `reconcile_profile_now` → `flush_pending_preview_policy` 补发|`api/v1/router.py:66-95,407-416`、`api/runtime_coordinator.py:773-855`|
|t040_code_f002|important|已修|`core.apply_preview_policy` 在 fence 之前写 policy 且无 epoch 单调校验；改为 stale epoch / 重复 request_id / stale instance 三重 fence 全部前置到任何写操作前，disabled 的 `clear_preview` 仅在 fence 通过后执行|`supervisor/core.py:1806-1860`|
|t040_code_f003|minor|已修|`set_policy` 内存策略不被 `capture_once` 消费；改为 `set_policy` 同时 `write_policy` 落文件，采集以共享 policy 文件为准|`runtime_agent/preview_capture.py:74-90`|
|t040_test_f001|important|已修|AC-001 真实栈 E2E 仅断言宽 480 + 字节长度，未比对已知页面内容；改为用 stream_runtime 镜像现有 Pillow 解码 JPEG 中心区域平均色（纯色 A `#003300` / 纯色 B `#cc0000` 双页，明确容差 ±20/通道）+ 宽 480 + 页面变色后预览跟着变（验证当前活动标签页）。撤掉 JPEG 字节相似度启发式|`tests/e2e/test_profile_preview_e2e.py`|
|t040_test_f002|minor|已修|AC-005 reset/delete 清除无测试能捕获回归；补 integration 两例直接断言清除效果|`tests/integration/test_preview_clear_on_lifecycle.py`|

结论段提示处置：OpenAPI 未声明 304 / `no-store` / ETag —— `FileResponse` + headers 实测由 `test_preview_router.py` 覆盖，响应头非 schema 可声明内容，不扩契约；`cdp_send_from_proxy` 访问代理私有成员 —— 与 `CdpProxyManager.send_command` 同通道，作为 follow-up（不改本次交付面）；多标签「活动标签页」精确识别 —— 依据 d035 结论由产品自维护，精确识别需外部焦点上报，留独立 follow-up。

### Round 2 (2026-11-08T03:20:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t040_code_f004|important|已修|Round 1 f003 让 `set_policy` 无条件写 `policy.json`，乱序 UDS 回退代次致撤销后采集恢复、`latest.jpg`/`meta.json` 重现；改为 Agent **不写** policy（API/Supervisor 单一写者），`set_policy` 加 epoch 单调、`capture_once` 用内存策略，`commit_preview` 仍以共享文件为最终 fence；重建 Browser 镜像并更新 E2E env digest；补 `test_stale_uds_cannot_reenable_capture_after_revocation` 复现验证|`runtime_agent/preview_capture.py:74-90`、`tests/unit/test_runtime_agent_preview.py`|

前轮复核：code 轴 f001（本地 500 + pending/reconcile 补发）、f003（采集消费策略）已消除；f002（core fence 前置）已落地，多写者根因由 f004 收敛。test 轴 f001（像素语义双色页）与 f002（delete/reset 清除）已消除，AC-001 由 TICK-VOID 转正。Round 2 test 轴 verdict PASS、code 轴因 f004 判 FAIL；按流程撤回全部 AC、修复、重验、重新打勾，进入 Round 3。

### Round 3 (2026-11-08T04:10:00+08:00)

Round 3 零 finding：两轴 verdict 均 PASS、0 新 finding、7 条 AC 全 `TICK-VALID`、coverage 7/7；前轮 f001 / f002 / f003 / f004 与 test f001 / f002 共 6 条经独立复核全部消除。`check_review_status` overall=PASS / review_scope=ok / ac_review=ok / round=3 / finalize。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：完整门禁 `.scratch/t040_evidence_20261108_032501` 的 design_lint / design_check / frontend_test / frontend_build / requirements_check / image_packages / integration 全 exit 0；unit 因 Round 2 review 报告 home 路径（#89 模板缺陷）失败 1 例，已做 .md-only 清理后按用户监督决定**只补跑 contract + unit**：contract 257 passed / 1 skipped、unit 1203 passed、repo_hygiene 8 passed；`md_format --changed --check` 与 `git diff --check` 通过。
- 黑盒：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh`（证据 `032501`）：并行阶段 50 passed / 2 skipped，串行阶段 52 passed / 52 deselected，2 failed 均为 `tests/e2e/test_frontend_session_e2e.py` 的 `test_frontend_session_independent_input_and_mute` / `test_frontend_session_freeze_resume_and_diagnostics`。根因证据 `e2e.log:371,422,690,741,805` `Sandbox launch failed ... error_type=DockerSandboxError error=Timed out waiting for current Browser instance readiness`、`:379` `Runtime start failed: DockerSandboxError`，与 t039 第 9 轮（222642）同类跨会话 daemon 资源竞争级联；对照 `013227` / `024359` 两轮 junit 同 2 用例均 PASS，且本轮 t019 基线 PASS。按用户监督决定不重跑完整 E2E，沿用本轮结果（代码未变）。
- review：full 两路共 4 轮。Round 1 code FAIL（3 条：f001/f002/f003）、test FAIL（2 条：f001 important 含 AC-001 TICK-VOID、f002 minor）；逐条根因修复、撤回 AC、重验、重新打勾。Round 2 test PASS、code FAIL（f004 important：多写者乱序 UDS 回退代次）；修复为 Agent 不写 policy（单一写者）+ epoch 单调 + 文件 fence，重建镜像、补复现测试。Round 3 两轴均 PASS、0 新 finding、7 条 AC 全 `TICK-VALID`、coverage 7/7。因删除未跟踪的前端运行软链 `src/frontend/node_modules` 导致工作区指纹更新至 `3cfef0709d1ad59b`（源码零变动），Round 4 重验两轴均 PASS、0 新 finding、7 条 AC 全 `TICK-VALID`、coverage 7/7。`check_review_status` overall=PASS / review_scope=ok / ac_review=ok / round=4 / finalize；6 条 finding 全部处置（已修 6、无遗留/撤回）。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 会话实时缩略图全链路落地：即时策略代次 + 独立 0600 预览目录 + Agent 15s CDP 采集（480px q70，只截 viewport）+ Supervisor 即时下发/health 通知 + API 预览端点（no-store / ETag / 404）+ `profile_preview` 只实时扇出不进重放环 + 前端 SSE 按类型分发与卡片刷新；撤销/停止保留/reset 清除/迟到写入丢弃；finalization 5 处 + 新建 spec。
- 遗留：`p052`（Selkies evict close frame 竞态，第 3 次复现证据已追记，根治以独立 follow-up 在收尾阶段实施，本 task 交付面不混入）、`p051`（跨 task 容器消失观察项）、`t019`（t032 登记基线）。无 blocking finding。

### 长期文档闭环

- specs_index：`profile_preview` 行已加 `t040` 并更新 `2026-11-07`；`docs/specs/profile_preview.md` 新建；`docs/blueprint/{browser_runtime,supervisor,security,frontend}.md` 按 finalization 更新。
- 正式 spike `s016`（`docs/spikes/s016_cdp_active_tab_capture_probe/`）有 `report.md`、两组实测 JSON、probe/run 脚本；结论 `docs/findings/d035_cdp_active_tab_capture_screenshot.md`；采纳结论与无需后续理由已写入 spike report（活动标签由产品自维护、`Page.captureScreenshot` 不改可见性/焦点，t040 按此实施；复核条件仅引擎主版本升级或改用真实宿主窗口时重跑。
