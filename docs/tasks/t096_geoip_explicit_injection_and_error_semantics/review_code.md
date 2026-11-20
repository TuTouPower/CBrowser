# Task review t096（reviewer_focus: 代码）

- task：`t096_geoip_explicit_injection_and_error_semantics`
- spec：`docs/tasks/t096_geoip_explicit_injection_and_error_semantics/task.md`
- diff_anchor：`482fe068aeef0a87f6c4c6de0493559b5f1306e4`
- target：`git diff 482fe068aeef0a87f6c4c6de0493559b5f1306e4`
- round：2
- reviewed_at：2026-11-20T22:07:13+08:00

## Round 2 (2026-11-20T22:07:13+08:00)

## Findings

无。

## 结论

- 前轮 finding 复核：Round 1 为 PASS、0 finding，无遗留 finding 需复核或撤回。相对 Round 1，交付代码未变；仅 `task.md` 按 `[deploy]` 处置注记补齐 AC-001/006 打勾、`progress.md` 填入 Round 1 处置。契约区 AC 原文一字未改，drift 仅为上述打勾与注记（依 p153 / p151 已批准口径），不按未确认变更判 blocking。Round 1 的 re_verified 证据因代码未变继续成立。
- 本轮新发现：0 条
- 未进表的提示：无。diff 触及文件均未达文件过大阈值（`test_t096` 179 行、`egress_probe.py` 152 行、`shared/egress.py` 376 行 < 400）；相关函数未达圈复杂度阈值；无范围外改动、死代码或残留 env 直读（`resolve_geoip_db_path` 的 env 读取仅存在于 resolver，生产唯一调用点 `api/app.py:325`）。
- 总体判断：显式构造注入、compose 谁用谁配、资源类错误码本地化与真实路径查找两态测试均已落地且与 AC-001~005 一致；全量门禁 EXIT=0，无未解决 critical / important。AC-006 按 p151 处置型判 TICK-VALID。可 PASS。
- 系统性 follow-up：无。AC-001/006 的生产规模验收按既定口径由 p151（`docs/pending/p151_t094_deploy_e2e_verification.md`）跟踪，非本轮新缺口。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`tests/unit/test_t096_geoip_explicit_injection.py::test_injected_real_mmdb_path_completes_geoip_lookup` 注入真实 mmdb 路径后断言 egress_ip=203.0.113.7 / JP / Japan / Tokyo，证明 API 探测可完成 GeoIP 查询且不再 `geoip_db_missing`；「生产 84 例转成功」属 [deploy] 成分，按 task.md 处置注记由 p151 跟踪，本机机制复验成立。
- AC-002：TICK-VALID，re_verified。`src/backend/cbrowser/shared/egress.py:107` 的 `GeoIpLookup.__init__` 仅保存注入的 `db_path`，不再读取隐藏 env；`src/backend/cbrowser/services/egress_probe.py:100` 的 `geoip` 为必填 kw-only 参数；唯一生产构造点 `src/backend/cbrowser/api/runtime_coordinator.py:480` 注入 `GeoIpLookup(db_path=self.geoip_db_path)`；未配置时 `src/backend/cbrowser/shared/egress.py:111` / `:137` 抛 `geoip_db_missing` 资源类失败而非崩溃。
- AC-003：TICK-VALID，re_verified。`compose.yaml:42` api 声明 `CBROWSER_GEOIP_CACHE: /data/engine-cache/geoip` 且 `:63` 挂载 `data:/data`；`:146` supervisor 声明 `${CBROWSER_DATA_ROOT}/engine-cache/geoip` 且 `:162` 挂载同一 data 卷，两者落在同一物理 mmdb。`test_compose_api_declares_geoip_cache_like_supervisor` 通过。
- AC-004：TICK-VALID，re_verified。`src/frontend/src/shared/presentation.ts:54` / `:55` 将 `geoip_db_missing` / `geoip2_missing` 分别映射到 `proxyErrorGeoipDbMissing` / `proxyErrorGeoip2Missing`，与 `echo_unreachable` 等网络失败及既有 `geoip_lookup_failed` 区分；`src/frontend/src/i18n.tsx:533-534`（en）与 `:1096-1097`（zh）中英双语文案齐备，未知码才回落 `proxyProbeFailed`。`presentation.test.ts` 独立重跑 12/12 通过。
- AC-005：TICK-VALID，re_verified。`tests/unit/test_t096_geoip_explicit_injection.py` 用真实 `GeoIpLookup`，`db_path.is_file()` 为真实路径判定、仅伪造 geoip2 的 `Reader`；覆盖「env 指向真实 mmdb 但未注入仍 `geoip_db_missing`」与「注入真实 mmdb → 成功完成 GeoIP 查询」两态，独立重跑 7/7 通过。
- AC-006：TICK-VALID，trust_prior。[deploy] 生产规模（约 88 代理）本机不可实测；`task.md` 处置注记声明云端契约/实现/单元·集成·前端门禁/显式注入两态测试已全部完成，真实验证由 p151 跟踪，按处置型判 TICK-VALID，非实现缺失。

coverage = 5/6

reviewed_scope: 9317a2d7b46971fe

verdict: PASS
