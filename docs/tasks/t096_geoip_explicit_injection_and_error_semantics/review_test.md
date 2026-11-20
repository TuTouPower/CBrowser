# Task review t096（reviewer_focus: 测试）

- task：`t096_geoip_explicit_injection_and_error_semantics`
- spec：`docs/tasks/t096_geoip_explicit_injection_and_error_semantics/task.md`
- diff_anchor：`482fe068aeef0a87f6c4c6de0493559b5f1306e4`
- target：`git diff 482fe068aeef0a87f6c4c6de0493559b5f1306e4`
- round：2
- reviewed_at：2026-11-20T22:10:26+08:00

## Round 2 (2026-11-20T22:10:26+08:00)

### Findings

无。

### 结论

- 前轮 finding 复核（Round 2）：Round 1 为 0 finding、verdict PASS，无 finding 需复核。AC 打勾变化复核：相对 diff_anchor，AC-001/006 由 `- [ ]` 补为 `- [x]`，并新增 `[deploy]` AC 打勾处置注记（契约修订，2026-11-20）；6 条 AC 验收原文一字未改，drift 仅为打勾与处置注记，属用户确认的处置型变更，非未确认的 AC 改写。AC-006 依 p151（`docs/pending/p151_t094_deploy_e2e_verification.md`）处置型判 `TICK-VALID`（trust_prior），与注记口径一致。
- 改测方向复核：无迁就实现的改测。`tests/unit/test_t052_egress_probe_helper.py`、`tests/unit/test_t052_supervisor_runner.py` 的改动仅为 `InProcessEgressProbeRunner(...)` 构造点补 `geoip=_StubGeoIp()` 以适配必填依赖，所有断言原样保留，属构造签名同步；`src/frontend/src/shared/presentation.test.ts` 为纯新增断言，无删除/反转/弱化。全仓无遗留无参构造点（仅 `tests/unit/test_t096_geoip_explicit_injection.py::test_runner_requires_explicit_geoip_at_construction` 故意断言 TypeError）。
- 危险模式扫描：无命中。无恒真断言、删/反转/注释断言、`.skip`/`.only`、静默错误指令、阈值掩盖、条件跳过弱化或存在即通过；`real_mmdb` 夹具仅在系统边界伪造 geoip2 的 `Reader`，未 mock 被测逻辑。
- 本轮新发现：0 条
- 未进表的提示：
    - `src/backend/cbrowser/api/app.py:325` 组合根 `geoip_db_path=resolve_geoip_db_path()` 单行未由测试直接覆盖，但 resolver（`test_resolve_geoip_db_path_reads_cache_env`）与 coordinator 注入（`test_coordinator_injects_resolved_path_into_runner`）各有独立用例，接线由 code reviewer 复验；属可选覆盖扩展，不阻断。
    - `test_compose_api_declares_geoip_cache_like_supervisor` 仅静态断言两服务 environment 均含 `CBROWSER_GEOIP_CACHE`，未直接断言卷挂载落到同一物理 mmdb；卷同源已由 code reviewer 依据 `compose.yaml:63`/`:162` 复验，保留为后续增强。
- 总体判断：相对 diff_anchor 的完整交付内容上，AC-002~005 两态失败语义、真实路径查找、compose 配置断言与前端文案映射均有可信测试；AC-001 本机机制由注入真实 mmdb 路径的端到端测试覆盖；AC-006 按 p151 处置型判 TICK-VALID。全量门禁 EXIT=0，6 条 AC 全部 `TICK-VALID`，无未解决 critical / important。可 PASS。
- 系统性 follow-up：无。AC-001/006 的生产规模部分按 p151 既定口径跟踪，非本轮新缺口。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`tests/unit/test_t096_geoip_explicit_injection.py::test_injected_real_mmdb_path_completes_geoip_lookup` 经真实 echo 夹具取出口 IP `203.0.113.7`，再用真实 `GeoIpLookup`（仅伪造系统边界的 geoip2 `Reader`）完成 `JP`/`Japan`/`Tokyo` 查询，证明本机 API 探测可完成 GeoIP 查询且不再 `geoip_db_missing`；「生产 84 例转成功」属 [deploy] 成分，按处置注记纳入 p151 补验。
- AC-002：TICK-VALID，re_verified。`test_runner_requires_explicit_geoip_at_construction` 断言无参构造抛 TypeError；`test_geoip_lookup_never_reads_hidden_env` 证明 `GeoIpLookup()` 不读隐藏 env；`test_unconfigured_path_is_resource_failure_even_when_env_has_db` 证明 env 指向真实 mmdb 仍判 `geoip_db_missing` 资源失败而非崩溃；生产唯一构造点由 `test_coordinator_injects_resolved_path_into_runner` 覆盖。
- AC-003：TICK-VALID，re_verified。`test_compose_api_declares_geoip_cache_like_supervisor` 断言 api 与 supervisor 均声明 `CBROWSER_GEOIP_CACHE` 指向 `.+/engine-cache/geoip`；`test_resolve_geoip_db_path_reads_cache_env` 断言解析得到 `/data/engine-cache/geoip/GeoLite2-City.mmdb`，配置层断言成立。
- AC-004：TICK-VALID，re_verified。`src/frontend/src/shared/presentation.test.ts` 新增断言 `geoip_db_missing`→`proxyErrorGeoipDbMissing`、`geoip2_missing`→`proxyErrorGeoip2Missing`，与既有 `geoip_lookup_failed` 独立映射及 `echo_unreachable` 网络失败、通用 `proxyProbeFailed` 区分；中英文案在 `src/frontend/src/i18n.tsx` 双份齐备，`zh satisfies Record<TranslationKey,string>` 由类型门禁保障键齐全。独立重跑 12/12 通过。
- AC-005：TICK-VALID，re_verified。`tests/unit/test_t096_geoip_explicit_injection.py` 覆盖「路径未注入 → `geoip_db_missing`（即使 env 指向真实 mmdb）」与「注入真实 mmdb → 成功完成 GeoIP 查询」两态；`real_mmdb` 夹具只在系统边界伪造 geoip2 `Reader`，`db_path.is_file()` 路径判定与 `GeoIpLookup.location` 全链路为真实逻辑，无假对象绕过。
- AC-006：TICK-VALID，trust_prior。[deploy] 生产规模（约 88 代理）本机不可实测；按 `[deploy]` AC 打勾处置注记与 p151（`docs/pending/p151_t094_deploy_e2e_verification.md`），云端可做的契约、实现、单元/集成/前端门禁与显式注入两态测试已完成、p151 已登记，按流程视为完成，判处置型 TICK-VALID；真实验证延期由 p151 以隔离真实拓扑与不可变镜像 ID 补验，不以 mock/skip/历史结果代替。

coverage = 5/6

reviewed_scope: 9317a2d7b46971fe

verdict: PASS
