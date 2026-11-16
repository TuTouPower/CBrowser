---
tid: "t074"
slug: "settings_persistence_modal_and_proxy_probe_overhaul"
title: "系统设置持久化弹窗化与代理轻量测速/国家城市/列表交互全栈重构"
status: "done"
branch: "t074_settings_persistence_modal_and_proxy_probe_overhaul"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "4bd5358b83377210899a3dbaaa204117e3126d36"
depends_on: "t073"
conflicts_with: ""
note: "聚合 p104、p105（设置弹窗/代理表单）、p106、p110、p111；涵盖 settings API、0010 迁移、轻量测速、GeoIP 国家城市服务与代理列表/筛选持久化重构"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 阻塞（2026-11-16T11:11:42+08:00）：本 task 在本次会话无法开工。`finish` 内置严格 preflight（`--require-verified`）因 `task.md` 未知契约清单有 2 项 `UNVERIFIED-SPIKE` 而 FAIL；实测 `task.py preflight t074 --owner-id ...` 为 PASS（1 WARN），追加 `--require-verified` 为 FAIL（1 项）。
- 原因：Step 1 两项 spike 需要「经真实代理」访问公网免 Key HTTPS GeoIP 服务（`ipwho.is` / `api.ip.sb/geoip` / `freeipapi.com`）并实测字段稳定性、单次 RTT、429 限流，以及用真实 Docker 容器验证池化轻量探针的网络隔离边界与毫秒级计时；本会话无真实可用代理、无 `GeoLite2-City.mmdb`、无 GeoIP 缓存（`.env` 无代理配置、`data/` 无 mmdb、E2E 必需模式收集期实测缺 13 项不可变镜像/缓存前置），属 `testing.md` `verification_notes` 的 NOT_RUN / USER_WAIVED 与 AC-006 `[deploy]` 范围。不伪写 spike 结论、不绕过门禁、不降级 `review_level`。
- 恢复入口：在具备真实代理 + 公网 GeoIP 服务 + Docker 的环境按 Step 1 用 `.repo_template/scripts/spikes.py new` 建立两个 spike（结论经 `findings.py` 入 `docs/findings/`），把 `task.md` 未知契约清单两项改写为「结论 + 验证方式」并注明真实公网/代理表现归 AC-006 `[deploy]`；再 `task.py preflight t074 --owner-id <新会话 owner_id> --require-verified` 严格 PASS 后按 Step 2–6 实施。恢复用 `task.py recovery t074` 判定 phase 为 `retry_ready` 后以 `attempt reserve` / `attempt claim` 开新 attempt，不重置 review/verify 历史。
- 上游 t073 已 done 并合入 `main`（merge `ae02d42`）。注意：合并后门禁因归档的 `review_general.md` 泄漏开发者家目录绝对路径失败，按 skill「验证失败则 abort 保留分支修复」仅修订该 review 过程文件并 amend 同一实现 commit，t073 tip 由 `4bd5358b` 变为 `f2c9f11`。本 task 分支仍以旧 tip `4bd5358b` 为基线（无自身 commit），与 `main` 成兄弟；恢复时须先把本 worktree 基线对齐到合并后的 `main`（或重建 worktree），再续做 Step 2–6，否则后续 `integrate-chain` 会因链不连续/成员目录归档冲突失败。本 task 无任何自身实现 commit，对齐基线不丢交付内容。
- 未写任何实现代码、测试或契约导出；worktree 与分支保留，未勾选任何 AC。
- 恢复轮次（2026-11-16T16:20:00+08:00）：`task.py recovery t074` 判 `retry_ready` → `attempt reserve` / `attempt claim` 开 attempt 2（owner_id `223f993643be45f8b0c32526dfe3ac7e`）；严格 `preflight --require-verified` PASS。用户裁决「回退 rebase」：`git stash -u` 保护交付 → `reset --hard 4bd5358b` → `stash pop`，HEAD 与 `diff_anchor` 重新匹配，attempt 2 保持 `executing`。
- Step 1 前置 spike 已闭环：`spikes.py new` 建 `s023_t074_geoip_service_contract`（5 个真实代理出口实测三家 GeoIP 服务、429 限流、本地 mmdb 兜底）与 `s024_t074_lightweight_probe_isolation`（真实 `cbrowser-api` 容器原型的私有地址拦截、热切换双出口、毫秒计时、凭据不进 argv）；结论经 `findings.py` 登记 `d048` / `d049`；`task.md` 两项 `UNVERIFIED-SPIKE` 改写为「结论 + 验证方式」，真实公网/代理表现归 AC-006 `[deploy]`。
- Step 2 后端骨架（本批）：`UserSettingsResponse` / `UserSettingsUpdateRequest`、`ProxyResponse` 观测字段、`EgressObservation` / `ProxyEgressObservationModel` 新字段、Alembic `0010`（`down_revision=796adb0bf159`）、`repository.get_settings` / `update_settings`（`BEGIN IMMEDIATE`）、`ProfileService` 薄封装、`settings_router`（会话鉴权 + CSRF）挂载；`supervisor/protocol.py` / `services/egress_probe.py` / `profile_service.py` 字段贯通。
- Step 4 契约导出（本批）：`export_openapi.py`（含 `/api/v1/settings`）、`export_supervisor_protocol.py`、`export_runtime_agent_protocol.py`、`npm run generate:api`；`export_supervisor_protocol.py --check` 与 `npm run check:api` 一致。
- 测试（本批）：新建 `tests/integration/test_t074_settings_api.py`（401 / 403 CSRF / 422 未知键 / GET 默认值 / PATCH 回读与跨会话持久化，6 passed）；按 TDD 规则整体替换 `test_t054_migration.py::test_head_is_0009_and_single` → `test_head_is_0010_and_single` 与 `test_t056_migrations.py::test_fresh_db_schema_matches_before_except_display_number` → `test_fresh_db_schema_matches_golden_except_intended_changes`（写明 0010 新增 3 列理由，不就地改旧断言）；`test_t035_openapi_contract.py` 的 `PUBLIC_GROUPS` 纳入新资源组 `settings`。
- 验证（本批）：全量 `tests/unit` 2263 passed / 5 skipped、全量 `tests/integration` 197 passed / 18 skipped（均带 jpeginfo PATH 与 worktree `.scratch` 缓存软链，环境性无网依赖已就绪）；严格 preflight PASS（1 条警告：为修复回退 rebase 后继承的 t073 旧版 `review_general.md` 家目录路径泄漏，按 main 已脱敏版本对齐，属现场基线修复）；`md_format.py --check --changed` 格式一致、`git diff --check` 通过。
- Step 3 后端探测重构（本批）：`shared/egress.py` 新增 `GEO_SERVICE_URLS` / `GeoLocation` / `EgressProbeDetail` / `fetch_egress_ip_timed` / `probe_egress_detail` / `GeoIpLookup.location()`，主链「IP 回显 + 本地 `GeoLite2-City.mmdb` 完整读取 country/city」，在线只读服务仅作可选城市补充；`runtime_agent/egress_probe.py` 输出完整观测 JSON；`docker_adapter.py` 新增 `EgressProbeOutcome`，`_exec_probe_helper` 在 `exit_code != 0` 且 stdout 为含 `error_code` 的合法 JSON 时保留输出交给 `_parse_probe_output`，修复 `probe_failed` 吞错；`supervisor/core.py` 回传完整字段。计时只由 `time.monotonic()` 包裹实际 HTTP 往返，不池化容器（避免内核白名单按代理累积）。`test_t052_egress_probe_helper.py` / `test_t052_supervisor_probe.py` 按 TDD 规则整体替换为 full-observation 与 `exit_code=1` JSON 错误码保留用例（旧 tuple/JSON 断言语义失效）。
- Step 5 前端全量（本批）：`client.ts` / `types.ts` 增 settings API；`providers.tsx` 重排为 `ApiClientContext` / `AuthProvider` 外层 + 独立 `I18nProvider` / `ThemeProvider` + `SettingsSync`（登录后 hydrate、后续写服务端，未登录不发 401）；`SettingsDialog`（`Dialog size="lg"` 三块宽布局）替代 `/settings` 窄页，`AppLayout` 侧栏按钮直开弹窗、`router.tsx` 旧路由 `<Navigate to="/" replace />`；`useBrowserSession` 的 `audioMuted` 按标签页隔离写 `sessionStorage`；新增 `useProxyFilters`（URL SearchParams）/ `useProxyLayout`（localStorage）；`ProxyListToolbar` 拆独立国家/城市筛选；`ProxyTable` 8 列 + `ok` 绿色延迟 / `failed` 红色错误码 / `0/1/2+` 使用环境交互 + `ProxyUsedByPopover`；`ProxyListPage` 删 `speedResults` 与 `Date.now() - startedAt`、HTTP 200 `failed` 不误报成功；`ProxyFormDialog` / `SessionDetailsPanel` 适配国家/城市/延迟/失败态。
- Step 6 门禁与旧测试整体替换（本批）：Step 5 语义变更使旧测试失效，按 TDD 规则整体替换并写明理由，不就地改预期：`AppLayout.shell.test.tsx`（`href="/settings"` → 按钮打开宽弹窗）、`router.test.tsx`（`/settings` → 回落首页 + 侧栏按钮开弹窗）、`auth_guard.test.tsx`（登出入口改设置弹窗、`next=/settings` 改 `/proxies` 有效受保护路由）、`ProxyListPage.test.tsx`（6 列 → 8 列、使用环境链接 → `0/1/2+`、未知/探测中 → `proxyStatusUnknown` / `proxyStatusPending`），并新增国家/城市独立筛选 + URL 持久化、绿色延迟/红色失败、HTTP 200 `failed` 不误报等用例。`app_error_boundary.test.tsx` 的「所有嵌套子路由须包 `RouteErrorBoundary`」结构不变式不动测试，改为把 `/settings` 的 `<Navigate>` 同样包入边界。
- Step 6 实现级 bug（先红后绿）：新增「国家/城市联动筛选」红灯暴露 `onCountryChange` 在同一 tick 两次调用 `setFilter` → 两次 `setSearchParams` 都读同一份 stale `location.search`，后者把前者的 `country` 覆盖丢失。修复为 `useProxyFilters` 新增 `setFilters(patch)` 单次原子提交，`onCountryChange` 改 `setFilters({ country, city: "all" })`，`setFilter` 委托 `setFilters`；不是改测试迁就实现。
- 验证（本批）：前端 `npm run test:types --prefix src/frontend` 与 Vitest 84 files / 665 tests 全绿；后端 `tests/unit` 2264 passed / 5 skipped、`tests/integration` 全绿；全量 `scripts/run_gates.sh`（evidence `.scratch/t074_step356/gate_evidence/manifest.json`，`run_id=dd53c7d1cc09443f9c57e5ba6d303824`）9 suite 全部 exit 0 / `all_passed=true`（`protocol_drift_check`、`requirements_check`、`contract`、`unit`、`integration`、`design_lint`、`design_check`、`frontend_test`、`frontend_build`）。所有门禁/测试输出写日志到 `.scratch/t074_step356/logs/`。
- 长期文档闭环（本批）：按 `task.md` Finalization 清单更新 `decisions.md`（ADR 029 t074 修订）、`domain.md`、`persistence.md`、`supervisor.md`、`security.md`、`frontend.md`；累积 `docs/specs/proxy_management.md` §10 与 `docs/specs/ui_design_system.md` §2.7；`docs/specs_index.md` 按 t065/t069 先例不新增行（见收尾报告）。`p112` 登记 AC-006 `[deploy]` 真实部署端到端补验顺延。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-16T19:18:00+08:00)

Round 1 零 finding。full 级双路独立 reviewer（`review_code.md` / `review_test.md`）均 `verdict: PASS`，零 critical / important / minor；`check_review_status.py` `overall=PASS` / `review_scope=ok` / `ac_review=ok` / `next_action=finalize`，指纹 `981786923676a0d6`。两轴逐条 `TICK-VALID` 复核 AC-001..005（`re_verified`）与 AC-006（`trust_prior`，`[deploy]` 顺延 p112，未谎称部署已验）。

### Round 2 (2026-11-16T19:22:00+08:00)

确认轮。`md_format.py --changed` 按项目标准修正 `md_kx` 格式漂移（`security.md` / `supervisor.md` / `review_code.md` 仅列表续行缩进、表格单元格空格、bullet 前空行、嵌套列表缩进，无语义 / 代码 / 测试 / AC 文案变化；与 t066 Round 3 同口径），scope 指纹由 `981786923676a0d6` 移至 `6343a38bcc6ebd1f`。双路 reviewer 各自独立复算指纹并追加 `## Round 2` 确认段，零新 finding，`verdict: PASS`；`check_review_status.py` `overall=PASS` / `review_scope=ok` / `ac_review=ok` / `round=2` / `next_action=finalize`。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（6/6 AC 已打勾；AC-006 `[deploy]` 真实部署端到端按项目口径顺延 `p112`，不冒充已验）
- 测试：前端 `npm run test:types --prefix src/frontend` 与 Vitest 84 files / 665 tests 全绿；后端 `tests/unit` 2264 passed / 5 skipped、`tests/integration` 197 passed / 18 skipped；全量门禁 `scripts/run_gates.sh`（`.scratch/t074_step356/gate_evidence/manifest.json`，`run_id=dd53c7d1cc09443f9c57e5ba6d303824`）9 suite 全部 exit 0 / `all_passed=true`：`protocol_drift_check`、`requirements_check`、`contract`、`unit`、`integration`、`design_lint`、`design_check`、`frontend_test`、`frontend_build`。全部输出写日志到 `.scratch/t074_step356/logs/`。
- 黑盒：NOT_RUN / USER_WAIVED。按 `docs/blueprint/testing.md` `verification_notes` 与 t066 `[deploy]` 顺延口径，AC-006 要求的真实重部署端到端（真实可用/不可用代理单条与批量测速、毫秒级延迟、准确国家城市、红色失败原因、刷新持久化、容器隔离与私有地址阻断、宽弹窗人工布局核对）本会话未配置正式部署环境，顺延 `docs/pending/todo/p112_t074_deploy_proxy_probe_e2e.md` 并如实记录，不以本机门禁或 spike 原型冒充已验。替代验收：s023 用 5 个真实代理出口实测三家 GeoIP 服务 / 429 限流 / 本地 mmdb 兜底（`docs/spikes/s023_t074_geoip_service_contract/code/results.json`）、s024 用真实 `cbrowser-api` Docker 容器原型实测私有地址拦截 / 热切换双出口 / 390–520ms 网络 RTT / 凭据不进 argv（`docs/spikes/s024_t074_lightweight_probe_isolation/code/results.json`）；全量门禁 + 受控 HTTPS GeoIP 夹具单测/集成测试触达 AC-001..005。
- review：full 级双路独立 reviewer Round 1 均 `PASS`、零 finding；`md_kx` 格式规范化（仅格式、无内容变化）后 Round 2 双路各自复算指纹并追加确认段，仍 `PASS`、零新 finding；`check_review_status.py` `overall=PASS` / `review_scope=ok` / `ac_review=ok` / `round=2` / `next_action=finalize`，`reviewed_scope` 指纹 `6343a38bcc6ebd1f`；报告见 `review_code.md` / `review_test.md`。
- AC 判定：6/6 已打勾，双路 reviewer 逐条 `TICK-VALID` 复核（AC-001..005 `re_verified`；AC-006 `trust_prior`，以云端可验部分 + `p112` 顺延为凭据，与 t066 同口径）。

### 结果摘要

- 单一原子全栈交付：启用 `settings` 表并暴露受会话鉴权 + CSRF 保护的 settings API；设置改 `Dialog size="lg"` 宽弹窗、偏好服务端持久化、会话静音按标签页 `sessionStorage`；代理观测 `0010` 迁移新增国家名 / 城市 / 毫秒延迟与结构化错误码；探针计时内移 + `exit_code=1` JSON 错误码透传 + 白名单只读 HTTPS GeoIP（本地 mmdb 主链）；代理列表 8 列、独立国家/城市筛选 URL 持久化、`0/1/2+` 使用环境交互、`ok` 绿延迟 / `failed` 红错误、删 `speedResults` 伪测速与 HTTP 200 `failed` 误报；OpenAPI / Supervisor 协议 / TS 类型同步导出。
- 遗留：`p112` 真实部署端到端补验（AC-006 `[deploy]`），按项目口径顺延，非本 task 缺陷。

### 长期文档闭环

- specs_index: not_applicable: 本 task 的 spec 累积在 `docs/specs/proxy_management.md`（§10）与 `docs/specs/ui_design_system.md`（§2.7），二者本就不在 `docs/specs_index.md` 表内（表中仅 `browser_isolation` 与 `webrtc_remote_display` 两行，与 t065 / t069 先例一致）；长期约束已落入 `docs/blueprint/`。
- blueprint：`decisions.md` ADR 029 追加 t074 修订；`domain.md` 新增 `UserSettings` 契约并扩展观测字段；`persistence.md` 记录 settings 实际读写与 `0010`；`supervisor.md` / `security.md` 记录轻量探针计时/错误码解析与白名单只读 HTTPS GeoIP 外连边界；`frontend.md` §6 / §8 / §9 更新设置宽弹窗与偏好同步、`audioMuted` 每页签 `sessionStorage`、代理国家/城市列与独立筛选 URL 持久化、`ok` / `failed` 状态色与 `0/1/2+` 交互。
- 正式 spike：`s023_t074_geoip_service_contract` / `s024_t074_lightweight_probe_isolation` 报告、实验代码与 `d048` / `d049` finding 已入库，结论回填 `task.md` 未知契约清单。
