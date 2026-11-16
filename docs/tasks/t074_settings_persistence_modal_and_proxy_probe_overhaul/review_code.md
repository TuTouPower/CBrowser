# Task review t074（reviewer_focus: 代码）

- task：`t074_settings_persistence_modal_and_proxy_probe_overhaul`
- spec：`docs/tasks/t074_settings_persistence_modal_and_proxy_probe_overhaul/task.md`
- diff_anchor：`4bd5358b83377210899a3dbaaa204117e3126d36`
- target：`git -C '../CBrowser_t074' diff 4bd5358b83377210899a3dbaaa204117e3126d36`
- round：1
- reviewed_at：2026-11-16T19:10:00+08:00

reviewed_scope: 981786923676a0d6

## Findings

Round 1 零 finding

## 结论

- 前轮 finding 复核：N/A（Round 1，无前轮）
- 本轮新发现：0 条
- 未进表的提示：
    - 文件过大（按降级规则只列路径与行数，不进表）：`src/frontend/src/features/proxies/ProxyListPage.tsx` 508 行（净增 81）、`src/backend/cbrowser/supervisor/docker_adapter.py` 2719 行（净增 17，既有巨型文件，本轮仅局部改动）、`src/frontend/src/features/proxies/ProxyListPage.test.tsx` 670 行（净增 178，测试阈值 600）；均未因体积直接产生可观测缺陷，不按缺陷定级。其余新建文件 `SettingsDialog.tsx` 292 行、`shared/egress.py` 365 行、`useProxyFilters.ts` 87 行均低于 400 阈值。
    - 圈复杂度：本轮新增/改动函数无 ≥15 者；`probe_egress_detail` / `run_egress_probe` 的分支为线性回落与 try/finally，未达提示阈值。
    - 范围外观察：`docs/tasks/t073.../review_general.md` 仅移除开发者家目录绝对路径，属 main 继承的基线 hygiene，非 t074 交付内容；`docs/specs_index.md` 未改为有意（spec 正文在 `docs/specs/` 累积、索引沿用 t065/t069 口径），不构成文档与实现不一致。
    - 实现层观察（非 finding）：`docker_adapter.py:567-579` 每次测速仍新建网络与 helper 容器；`latency_ms` 已在 helper 内由 `shared/egress.py:253-269` 的 `time.monotonic()` 只包 HTTP 往返，AC-004 的报表数值不含容器建毁；s024 的池化容器设想归后续性能优化，无 AC 对其打勾，不据此出 finding。
- 总体判断：实现层逐项复核（settings 鉴权/CSRF、0010 迁移、exit_code=1 错误码透传、GeoIP 白名单与 trust_env=False、凭据不进 argv/stdout、计时内移、provider 层级、筛选 URL 原子持久化、0/1/2+ 三态、HTTP 200 `failed` 不误报）均成立，无未解决 critical/important，全部打勾成立，判 PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`settings_router.py:12-16` 路由级会话鉴权且 `require_csrf_and_origin` 仅对写方法生效（GET 放行）、`repository.py:1636-1665` 以 `BEGIN IMMEDIATE` 读写 `SettingModel`，`test_t074_settings_api.py` 的 401/403/422/GET 默认值/PATCH 跨会话回读 6 例通过；`AppLayout.tsx:222-235` 侧栏按钮直接开 `SettingsDialog`（`Dialog size="lg"`）且 `AppLayout.shell.test.tsx`/`auth_guard.test.tsx` 新语义用例验证不离开当前路由，全量门禁 9/9 pass（`manifest.json all_passed=true`）。
- AC-002：TICK-VALID，re_verified。`useBrowserSession.ts:62-70` 按 `profileId` 键读写 `sessionStorage`（标签页天然隔离）、`useBrowserSession.ts:592-596` 在 `connected` 时按 `audioMutedRef` 回灌音频管线使刷新后真实静音，双页独立由既有会话 E2E 口径覆盖，门禁 unit/integration/frontend_test 全绿。
- AC-003：TICK-VALID，re_verified。`0010_proxy_observation_city_latency.py:18-33` 加 3 列且 `down_revision="796adb0bf159"` 只进不退、`repository.py:1329-1341` 全字段读回、`_visible_observation`（`repository.py:1372-1390`）在端点指纹/凭据/TTL 失配时隐藏旧 ok 观测使位置与延迟立即失效；`useProxyFilters.ts`/`useProxyLayout.ts` 将 q/scheme/country/city 与视图写入 URL/localStorage，`test_t054_migration.py`/`test_t056_migrations.py` 按新 head 整体替换，9 门禁 pass。
- AC-004：TICK-VALID，re_verified。`shared/egress.py:253-269` 用 `time.monotonic()` 仅包 helper 内探测 HTTP 往返并 `max(1, round(...))`，`docker_adapter.py:785-797` 在 `exit_code=1` 解析合法 JSON `error_code` → `_parse_probe_output` 抛 `EgressProbeFailure` → `core.py:2509-2510` 原样透传，`ProxyListPage.tsx:222-236` 对 HTTP 200 `observation_status="failed"` 标红且不再提示成功；`test_t052_supervisor_probe.py` 新增 exit1 用例，门禁全绿。
- AC-005：TICK-VALID，re_verified。`ProxyTable.tsx` 拆出国家/城市/状态/使用环境列（`ok` 绿字 `{latency_ms}ms`、`failed` 红字错误码、`unknown` 中性提示），`0` 禁点 / `1` 直进 `/profiles/:id/config` / `>=2` 弹 `ProxyUsedByPopover`（含绿/灰运行点）三态齐备，`ProxyListToolbar.tsx` 独立国家与城市筛选且 `ProxyListPage.tsx:270-272` 用单次 `setFilters` 原子联动，OpenAPI/Protocol/TS 类型导出与实现一致（`cbrowser_v1.json` 含 `/api/v1/settings` 与全部新字段），9 门禁 pass。
- AC-006：TICK-VALID，trust_prior。`[deploy]` 真实重部署 E2E 被明确顺延而非谎称已验：`docs/pending/todo/p112_t074_deploy_proxy_probe_e2e.md` 明写「仍未验」「不以本机门禁或 spike 原型冒充已验」，`task.md` 可测试性声明与未知契约清单、progress.md 均标 `NOT_RUN / USER_WAIVED` 并以 s023（真实代理出口 GeoIP 实测）/ s024（真实 Docker 容器隔离与毫秒计时原型）作替代证据，依 `docs/blueprint/testing.md` `verification_notes` 与 t066→p093 先例成立；本机无法独立复验部署态，故 trust_prior。

coverage = 5 / 6

verdict: PASS

## Round 2 (2026-11-16T19:22:00+08:00)

- round：2（确认轮：md_kx 格式规范化后的指纹重认）
- reviewed_at：2026-11-16T19:22:00+08:00

reviewed_scope: 6343a38bcc6ebd1f

- 增量核对：仅 `md_format.py --changed` 对 `security.md` / `supervisor.md` / `review_code.md` 做格式规范化（列表续行缩进、表格单元格补空格、bullet 前空行、嵌套列表缩进），无语义 / 代码 / 测试 / AC 文案变化；t074 新增段落逐字比对一致，交付文件清单未变。
- 指纹核对：本人执行指定命令输出 `6343a38bcc6ebd1f`，与期望一致。
- 前轮 finding 复核：Round 1 零 finding，无需处置。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`settings_router.py` 路由级会话鉴权 + 写方法 `require_csrf_and_origin`（GET 放行），`repository.py` 以 `BEGIN IMMEDIATE` 读写 `SettingModel`，`test_t074_settings_api.py` 401/403/422/GET/PATCH 跨会话回读 6 例通过，门禁 9/9。
- AC-002：TICK-VALID，re_verified。`useBrowserSession.ts` 按 `profileId` 键读写 `sessionStorage`（标签隔离）并在 `connected` 时按 `audioMutedRef` 回灌音频管线实现刷新后真实静音，门禁 unit/integration/frontend_test 全绿。
- AC-003：TICK-VALID，re_verified。`0010_proxy_observation_city_latency.py` 加 3 列且 `down_revision` 单向、`repository.py` 全字段读回并在指纹/凭据/TTL 失配时隐藏旧观测，`useProxyFilters.ts` 将 q/scheme/country/city/视图写 URL/localStorage，`test_t054`/`test_t056` 按新 head 覆盖，9 门禁 pass。
- AC-004：TICK-VALID，re_verified。`shared/egress.py` 用 `time.monotonic()` 仅包 helper 内探测 HTTP 往返，`docker_adapter.py` 在 `exit_code=1` 解析合法 JSON `error_code` → `EgressProbeFailure` → `core.py` 原样透传，`ProxyListPage.tsx` 对 HTTP 200 `failed` 标红不误报，`test_t052_supervisor_probe.py` 新增 exit1 用例。
- AC-005：TICK-VALID，re_verified。`ProxyTable.tsx` 拆国家/城市/状态/使用环境等 8 列、`0` 禁点/`1` 直进 `/profiles/:id/config`/`>=2` 弹 `ProxyUsedByPopover` 三态齐备，`ProxyListPage.tsx` 单次 `setFilters` 原子联动，OpenAPI/Protocol/TS 导出与实现一致，9 门禁 pass。
- AC-006：TICK-VALID，trust_prior。`[deploy]` 顺延 p112、NOT_RUN/USER_WAIVED 如实披露，s023/s024 替代证据，未谎称部署已验。

coverage = 5 / 6

verdict: PASS
