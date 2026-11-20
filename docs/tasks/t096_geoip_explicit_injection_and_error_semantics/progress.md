---
tid: "t096"
slug: "geoip_explicit_injection_and_error_semantics"
title: "GeoIP 依赖显式注入与测速失败语义保真"
status: "done"
branch: "t096_geoip_explicit_injection_and_error_semantics"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "482fe068aeef0a87f6c4c6de0493559b5f1306e4"
spec_source_sha: "482fe068aeef0a87f6c4c6de0493559b5f1306e4"
depends_on: ""
conflicts_with: ""
note: "用户 2026-11-20 授权（p153）：测速全失败真因为 t094 把探测迁入 API 进程后，GeoIP 路径靠隐式环境变量传递且只配给 supervisor，api 进程查不到数据库报 geoip_db_missing（84/88），前端兜底成笼统「测速失败」掩盖根因。按开发铁律从根修：依赖显式注入、配置按谁用谁配、错误语义保真、补真实路径查找测试。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-20：来源 p153，生产排查与铁律分析已确认；AC 覆盖显式注入、配置归位、错误语义保真与验证闭环，尚未实施。
- 2026-11-20：TDD 先红后绿。`tests/unit/test_t096_geoip_explicit_injection.py` 先写 6 条红例（构造器必须注入、lookup 不读隐藏 env、env 指向真实 mmdb 仍资源失败、注入真实 mmdb 走完整 `GeoIpLookup.location`、coordinator 注入、compose 配置自洽），前端 `presentation.test.ts` 先写两条红例（`geoip_db_missing` / `geoip2_missing` 文案映射）。
- 2026-11-20：`GeoIpLookup.__init__` 改为只用显式 db_path（不再调 env 解析器）；`resolve_geoip_db_path` 保留为唯一部署配置解析点，仅由 API 组合根调用一次；`InProcessEgressProbeRunner` 把 `geoip` 提升为必填构造依赖；`RuntimeCoordinator` 新增 `geoip_db_path`，`egress_probe_runner()` 构造 lookup 注入；`app.py` 显式解析 env 后接线；compose 给 api 补 `CBROWSER_GEOIP_CACHE: /data/engine-cache/geoip`。旧测试构造点同步补注入（不改断言语义）。
- 2026-11-20：前端补 `proxyErrorGeoipDbMissing` / `proxyErrorGeoip2Missing` 中英文案及 presentation 映射；`geoip_lookup_failed` 原有文案复用。未改 OpenAPI/DTO，故不重导 schema 与生成类型。
- 2026-11-20：全量门禁 `scripts/run_gates.sh` EXIT=0；`git diff --check`、`md_format --check`、`npm run test:types` 均通过。AC-001/006 属生产规模部署验收，本机不可做，按既定口径由 p151 跟踪。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round N (YYYY-MM-DDThh:mm:ss+08:00)

### Round 1 (2026-11-20T21:35:00+08:00)

code/test reviewer 双轴均 PASS，零 finding。AC-001~005 TICK-VALID/re_verified；AC-006 TICK-VALID/trust_prior（[deploy] 本机不可实测，p151 跟踪）。AC-001 依两 reviewer 一致建议打勾（本机真实 mmdb 路径注入测试已证机制，生产 84 例转成功纳入 p151 补验）。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：AC-001~006 全部满足（AC-006 按 [deploy] 处置注记视为流程完成，真实验证由 p151 跟踪）。
- 测试：`scripts/run_gates.sh` 全量 EXIT=0（contract 388 passed/1 skipped；unit 2417+83 passed/13 skipped；integration 216 passed/18 skipped；design_lint/design_check PASS；frontend_test 88 files/730 passed；frontend_build PASS）；`tests/unit/test_t096_geoip_explicit_injection.py` 7/7（含两态真实路径查找）；前端 `presentation.test.ts` / `i18n.test.tsx` 17/17；`npm run test:types`、`git diff --check`、`md_format --check` PASS。
- 黑盒：生产 88 代理规模重测与容器内真实 mmdb 解析属 [deploy]，本机不可执行，按既定口径由 p151 跟踪；云端以注入真实 mmdb 路径的 runner 单测替代，不冒充生产实测。
- review：full 双轴 code/test 均 PASS、零 finding，`review_scope=ok`、`ac_review=ok`、`next_action=finalize`；6 条 AC 全 TICK-VALID（AC-001~005 re_verified，AC-006 trust_prior 处置型）。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 显式注入、资源类失败语义、compose 谁用谁配、前端错误码文案分别落入 `architecture.md` / `domain.md` / `supervisor.md` / `frontend.md`；`proxy_management.md` 与 `gate_verification.md` front matter `tasks` 已登记 t096 并补对应契约。
- 遗留：AC-001/006 [deploy] 生产规模验收由 p151 跟踪；本会话未派 review、未 commit/finish，交主会话处理。

### 长期文档闭环

在 active spec 的 front matter `tasks` 清单中登记当前 tid（`task.py specs list --json`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
