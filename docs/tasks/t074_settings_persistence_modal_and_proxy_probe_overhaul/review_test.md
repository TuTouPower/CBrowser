# Task review t074（reviewer_focus: 测试）

- task：`t074_settings_persistence_modal_and_proxy_probe_overhaul`
- spec：`docs/tasks/t074_settings_persistence_modal_and_proxy_probe_overhaul/task.md`
- diff_anchor：`4bd5358b83377210899a3dbaaa204117e3126d36`
- target：`git -C '../cbrowser_t074' diff 4bd5358b83377210899a3dbaaa204117e3126d36`
- round：1
- reviewed_at：2026-11-16T19:10:00+08:00

reviewed_scope: 981786923676a0d6

## Findings

Round 1 零 finding。

## 结论

- 前轮复核：N/A（round 1，无前轮 finding 可复核）。
- 改测方向复核：**无「迁就实现」的改测**。逐处判定为合法的「规格变更导致旧测试语义失效 → 整体替换为新语义测试（含书面理由），非就地改旧断言为当前输出」：`AppLayout.shell.test.tsx`（删 `href="/settings"` 断言，新增「按钮打开 `settings-dialog` 且不导航」）、`router.test.tsx`（`/settings` 由「渲染 settings-page」反转为「重定向 `/`、无 settings-page」；页脚锚点改弹窗触发按钮）、`auth_guard.test.tsx`（登出入口改弹窗内 `settings-logout`、断言路径仍为 `/`；登录回跳示例路径 `/settings`→`/proxies`）、`ProxyListPage.test.tsx`（6→8 列、`filterProxies` 签名对象化、删除旧 `?proxy=` 链接测试改 `0/1/2+` 三态、`proxyCountryUnknown/Probing`→`proxyStatusUnknown/Pending`）、`test_t052_*`（2-tuple→`EgressProbeOutcome` 结构化返回、exact dict→逐字段断言）、`test_t054_migration.py`/`test_t056_migrations.py`/`test_t035_openapi_contract.py`（0010 新 head `8c3f1d0a7b92`、golden 增列、`settings` 资源组）。`latency_ms >= 1` 是对 `max(1, round(monotonic Δ))` 非确定测量值的合法下界断言，非弱化。红灯归因：`ProxyListPage.test.tsx`「filters independently by country and city through linked toolbar selects」暴露 `useProxyFilters.ts` 单 tick 两次 `setFilter` 互相覆盖 `country` 的真实实现 bug，经 atomic `setFilters` 修复，属 TDD 红→绿，非弱化断言。危险模式扫描：改测中无 `.skip`/`.only`/`@ts-ignore`/`eslint-disable`/`pytest.mark.skip`、无恒真断言（`expect(true)`/`assert True`/裸 `toBeDefined` 当证据）、无注释掉断言、无条件跳过弱化、无 `toMatchObject`/`toBeTruthy` 滥用、无 `.value=` 冒充交互、无 mock 被测逻辑本身（mock 仅限系统边界：TestClient 临时 SQLite DB、Docker adapter、外部 mmdb reader、API client stub）。
- 本轮新发现：0 条。
- 未进表的提示：（1）可选覆盖扩展，不阻断、非本轮 finding：spec Step 6 曾要求独立 `SettingsDialog.test.tsx` 与 `session_audio` 刷新保静音专项测试，交付 diff 未新增此类专项文件；但 AC-001 弹窗已由 `AppLayout.shell`/`router`/`auth_guard` 的 dialog-open 断言覆盖、AC-002 已由既有 `session_audio_control.test.tsx`「two independent hook instances」触达 `useBrowserSession` 生产 hook 覆盖，均经全量门禁 84 files/665 tests 全绿，属「可再加更细 case」，按 prompt 不阻断。（2）范围外：`t073 .../review_general.md` 仅删开发者家目录绝对路径（hygiene，继承自主干），非 t074 交付，不计本轴。（3）gate 日志 `real_engine NOT_RUN` 与 AC-006 的 NOT_RUN/USER_WAIVED 披露一致，非测试缺口。
- 总体判断：全量门禁 9 suites `all_passed=true`（unit 2264 passed/5 skipped、integration 全绿、Vitest 84 files/665 tests、frontend build），逐条 AC 均有真实可信测试或诚实替代验证支撑，改测均为合法新语义替换、无未解决 critical/important，「AC 复验方式」全部 TICK-VALID，PASS。
- 系统性 follow-up：无（AC-006 `[deploy]` 顺延已由 `docs/pending/todo/p112_t074_deploy_proxy_probe_e2e.md` 承接，不重复立项）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。junit `integration.xml` 中 `test_t074_settings_api` 6 case（401/403 CSRF/422 未知键/GET 默认值/PATCH 回读跨会话持久化）全绿；前端 `AppLayout.shell`/`router`/`auth_guard` 三处断言侧栏按钮打开 `settings-dialog` 且路径不导航；全量门禁 all_passed=true。
- AC-002：TICK-VALID，re_verified。`useBrowserSession.ts:2862-2890` 以 `sessionStorage` 每页签键读写 `audioMuted`，既有 `session_audio_control.test.tsx`「two independent hook instances keep their own mute state」在 Vitest 665 tests 全绿中触达该生产 hook，刷新保静音由 sessionStorage 真源首帧读取保证。
- AC-003：TICK-VALID，re_verified。`unit.xml` 中 `test_head_is_0010_and_single`/`test_fresh_db_schema_matches_golden_except_intended_changes`/`test_helper_prints_full_observation` 全绿，既有 `test_t052_egress_observation.py` 与 `test_t052_proxy_api.py` 覆盖端点/凭据变更使 observation 失效，前端「restores q/scheme/country/city from URL」持久化测试。
- AC-004：TICK-VALID，re_verified。`unit.xml` `test_probe_helper_exit_1_json_error_code_is_preserved` 断言 `EgressProbeFailure.code=="echo_unreachable"`（修 exit_code=1 吞错），前端「HTTP 200 返回 observation_status=failed 不误报成功」toast 测试与「128ms text-success / proxy_auth_failed text-danger」断言。
- AC-005：TICK-VALID，re_verified。`ProxyListPage.test.tsx` 重写：8 列断言、国家/城市独立联动筛选、URL 持久化、`0` span/`1` 直进/`2+` popover 三态、ok 绿延迟/failed 红错误码；`test_t035_openapi_contract.py` 纳入 `settings` 资源组且契约导出门禁全绿。
- AC-006：TICK-VALID，trust_prior。task.md 打勾但 `p112` 明确 NOT_RUN/USER_WAIVED「仍未验、不冒充已验」，task.md 未知契约清单两处「归 AC-006 [deploy] 验证，不冒充已验」，gate `real_engine NOT_RUN`；s023 真实代理出口 GeoIP 实测 / s024 真实 Docker 容器隔离原型报告为替代验证（t066 顺延口径），未声称已部署验证，披露诚实。

coverage = 5 / 6

verdict: PASS

## Round 2 (2026-11-16T19:22:00+08:00)

- round：2（确认轮：md_kx 格式规范化后的指纹重认）
- reviewed_at：2026-11-16T19:22:00+08:00

reviewed_scope: 6343a38bcc6ebd1f

- 增量核对：`md_format.py --changed` 仅对 `security.md` / `supervisor.md` / `review_code.md` 做格式规范化（列表续行缩进、表格单元格补空格、bullet 前空行、嵌套列表缩进）；`review_test.md` 无漂移未改；无测试 / 源码 / AC 文案 / spec 语义变化，危险模式扫描结论不变（0 命中）。
- 指纹核对：本人执行指定命令输出 `6343a38bcc6ebd1f`，与期望一致。
- 前轮 finding 复核：Round 1 零 finding，无需处置；改测方向复核仍为「无迁就实现」。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`integration.xml` 中 `test_t074_settings_api` 6 case（401/403 CSRF/422 未知键/GET 默认值/PATCH 回读跨会话持久化）全绿，`AppLayout.shell`/`router`/`auth_guard` 三处断言侧栏按钮打开 `settings-dialog` 且路径不导航。
- AC-002：TICK-VALID，re_verified。`useBrowserSession.ts` 以 `sessionStorage` 每页签键读写 `audioMuted`，既有 `session_audio_control.test.tsx`「two independent hook instances」触达生产 hook，刷新首帧读 sessionStorage 真源保静音。
- AC-003：TICK-VALID，re_verified。`unit.xml` 中 `test_head_is_0010_and_single`/`test_fresh_db_schema_matches_golden_except_intended_changes`/`test_helper_prints_full_observation` 全绿，前端「restores q/scheme/country/city from URL」持久化测试在位。
- AC-004：TICK-VALID，re_verified。`test_probe_helper_exit_1_json_error_code_is_preserved` 断言 `EgressProbeFailure.code=="echo_unreachable"`，前端「HTTP 200 返回 observation_status=failed 不误报成功」toast 与「128ms 绿 / proxy_auth_failed 红」延迟错误码断言。
- AC-005：TICK-VALID，re_verified。`ProxyListPage.test.tsx` 8 列 / 国家城市独立联动 / URL 持久化 / `0`span-`1`直进-`2+`popover 三态，`test_t035_openapi_contract.py` 纳入 `settings` 资源组且契约导出门禁全绿。
- AC-006：TICK-VALID，trust_prior。`[deploy]` 顺延 p112、NOT_RUN/USER_WAIVED 如实披露，s023/s024 替代证据，未谎称部署已验。

coverage = 5 / 6

verdict: PASS
