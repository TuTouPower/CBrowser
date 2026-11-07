# Task review t038（reviewer_focus: 代码）

- task：`t038_proxy_library_ui`
- spec：`docs/tasks/t038_proxy_library_ui/task.md`
- diff_anchor：`1ca4cb4fd4212ddfb7ad4b6c9bcfcbcc9b1df65d`
- target：`git diff 1ca4cb4fd4212ddfb7ad4b6c9bcfcbcc9b1df65d`
- round：1
- reviewed_at：2026-11-07T12:17:00+08:00

reviewed_scope: 4a70d17b9064ad06

落点校验：`git rev-parse --show-toplevel`（不带 `-C`）= `t038 worktree` ✓。`git status --short` 全部 23 个交付文件已 staged（`M ` / `A `），无 reviewer 看不到的未跟踪交付文件，不判 INCOMPLETE。指纹经 `review_scope_fingerprint()` 只读重算 = `4a70d17b9064ad06`，与下行一致。

## Findings

### t038_code_f001 - `isSocks5Unsupported` 把任意 HTTP 422 误判为「引擎不支持 SOCKS5」

- 严重度：minor
- 锚点：行为缺陷（错误提示错配）；关联 AC-002 错误展示与 AC-007 降级入口
- 位置：`src/frontend/src/features/proxies/ProxyFormDialog.tsx:143-159`（第 145 行 `if (err.status === 422) return true;`）、`:271-277`（catch）、`src/frontend/src/i18n.tsx:410,760`
- 问题：`isSocks5Unsupported` 对任何 `ApiError.status === 422` 直接返回 true，catch 据此把 banner 置为 `t("proxySocks5Unsupported")`（"当前引擎不支持带认证 SOCKS5"），`describeError` 分支被跳过。但 422 在代理 API 上更常见于 FastAPI/Pydantic 请求体校验失败，而非 socks5 不支持（d031 / ADR 023 已确认后端不会因 `socks5`+凭据返回 422）。可复现：协议选 http、用户名填 300 字符提交 → 后端 `models.py:108` 的 `max_length=255` 触发 422 → 界面显示与原因完全无关的 SOCKS5 文案，真实校验错误被隐藏。属可观测的错误答案，但仅影响边缘输入与提示文案，评 minor。
- 建议：把 422 判定收窄到明确的不支持信号（`detail.code` / `errorCode` / 文案命中 socks5+unsupported），其余 422 走 `describeError`；配合 f002 补齐前端校验后由后端 detail 展示真实原因。

### t038_code_f002 - 前端字段校验未覆盖后端 `username` / `region_label` 的 255 上限

- 严重度：minor
- 锚点：AC-002（「字段校验与后端规则一致，错误在对应字段旁显示」）
- 位置：`src/frontend/src/features/proxies/ProxyFormDialog.tsx:47`（`FieldKey`）、`:83-105`（`validate()`）、`:283-294`（`fieldError`）；后端 `src/backend/cbrowser/domain/models.py:108,111,129`
- 问题：`validate()` 与 `FieldKey` 只覆盖 name / host / port / country-code / scheme 五项，且与 `models.py:104-110` 及 `PROXY_SCHEMES`（`:52`）一致；但后端对 `username`（create/update 均 `max_length=255`）、`region_label`（create `max_length=255`）另有长度约束，前端既不校验、也无字段旁错误位。可复现：新建代理填 300 字符用户名 → 前端放行 → 后端 422 → 错误以 banner 呈现（且被 f001 误标），不满足 AC-002 的字段旁展示语义。主 5 项规则与后端一致、AC 主体已落地，故不判 TICK-VOID，仅记 minor 完整性缺口。
- 建议：补 `username` / `region_label` 长度校验并扩 `FieldKey` 增字段旁错误位，或明确以服务端校验为准并同步修正 422 展示路径。

### t038_code_f003 - task.md AC-007 字面措辞与权威结论冲突（spec 过时）

- 严重度：minor
- 锚点：AC-007（措辞）/ 文档与规格一致性
- 位置：`docs/tasks/t038_proxy_library_ui/task.md:42`；对照 `docs/findings/d031_authenticated_socks5_supported.md:5`、`docs/spikes/s013_authenticated_socks5_engine_probe/report.md:9,27`、`docs/blueprint/decisions.md:280,282`、`docs/specs/profile_management.md:63`、`docs/specs/proxy_management.md:31-35`
- 问题：task.md AC-007 附带「引擎不支持时阻止提交并说明原因」沿用 plan 旧假设；d031 / s013 / ADR 023 实测结论为 CloakBrowser 0.6.4 / Chromium 146 **支持**带认证 SOCKS5、API 不以 422 拒绝，ADR 023 明确把「一律 422 拒绝」列为未采用选项。实现按权威结论做「默认允许 `socks5`+账密提交 + 仅后端 422 时降级说明并保持表单」（`ProxyFormDialog.tsx:103` 无 socks5 阻止、`:143-159,271-277` 降级入口），与 `proxy_management.md` §5 完全一致，真实满足「与 t035 结论一致」，AC-007 判 TICK-VALID。仅 task.md 字面未同步，属 spec 过时，按「实现合理但与 spec 描述不符 → 改 spec，不计 FAIL」处置。
- 建议：改 spec 文字，把 task.md AC-007 改为与 `proxy_management.md` §5 一致的表述（默认允许 + 后端 422 / 明确不支持时降级说明）；不改实现，不计 FAIL。

## 结论

- 本轮新发现：3 条，均 minor（f001 / f002 / f003），无 critical / important。
- 未进表的提示：
    - 文件过大（按降级规则只列路径与行数，不进表）：`src/frontend/src/features/proxies/ProxyFormDialog.tsx` 487 行，新建即 ≥400、\<800；其余新增源码 / 测试均低于阈值（`ProxyFormDialog.test.tsx` 397、`ProxyListPage.test.tsx` 391、`test_proxy_library_e2e.py` 331 等均 \<600）。
    - 圈复杂度：`parseProxyUrl.ts:21-98` 手算近似 McCabe ≈20，但为扁平 guard 链、无嵌套分叉、无可观测缺陷；按「≥10 结论段提示 / 复杂度本身不 blocking」仅此提示，不进 finding 表。
    - 范围外观察：跨 task 格式修复 `docs/tasks/t045_e2e_gate_stability_cleanup/review_code.md` / `review_test.md` 共 7 处 home 绝对路径改 `t045 worktree` 占位；`git diff` 核实仅路径字符串变化，`verdict: PASS`、Findings、AC 复验结论、处置文字均未动，已在 `progress.md` 披露，不计 finding。
    - 范围核对：diff 23 文件均属代理库界面、路由 / i18n / API 客户端 / 类型 / mutation、文档闭环与 AC-008 E2E，无范围外功能、无关模块顺手改动，未见 YAGNI 额外功能。
    - 门禁上下文：`manifest.json` 9 个非 E2E suite 全 exit 0，`frontend_test.log` 54 文件 356 测试全过；E2E 102 例 FAIL=2（`test_t019...` 3.352s = t032 已登记基线、`test_runtime_coordinator_docker_e2e` NotFound = p051 已记录证据缺陷复现）、SKIP=2、ERROR=0，AC-008 `test_ac008_proxy_library_outbound_via_ui` PASS。独立复跑：`npx tsc -p tsconfig.test.json --noEmit` 通过、`npx vitest run src/features/proxies` 3 文件 55 测试通过。i18n en / zh 各补 48 键、键集相等（`TranslationKey = keyof typeof en` + zh `satisfies`）；`DESIGN.md` 语义 token / 无调色板与颜色字面量 / 无命名尺寸类与任意值经 `design_lint` exit 0 与 `design_check` exit 0 核验；`ProxyTable` 地址与 used_by 用 `MonoValue`、认证有「有 / 无」文字，符合 `DESIGN.md:719`。
- 总体判断：8 条 AC 打勾在实现层均真实支撑；AC-007 按 d031 / s013 / ADR 023 / `proxy_management.md` §5 的权威结论判 TICK-VOID 不成立（判 TICK-VALID），task.md 字面过时仅以 minor f003 记「改 spec」。无未解决 critical / important，PASS。
- 系统性 follow-up：`p051_e2e_container_vanish_during_gate`、t032 基线 t019、模板缺陷 issue #89 均已在 `progress.md` 登记；本轮无新增系统性缺口。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`ProxyTable.tsx:34-40,44-131` 列齐名称 / 协议 / 地址(`MonoValue`) / 认证(有/无) / 地区(码+标签) / 使用环境数 / 操作；`ProxyListPage.tsx:18-31` `filterProxies` 先按 scheme、再对 name/host/region_label 大小写不敏感匹配，二者可组合；`proxy_management.md:8` 明确搜索为「地区标签」，故不搜 country_code 属规格本意；proxies vitest 重跑通过。
- AC-002：TICK-VALID，re_verified。`ProxyFormDialog.tsx:83-105` name 1-255 / host 1-512 / port 1-65535 / country_code 2 字母 / scheme 白名单与 `models.py:52,104-110` 一致，错误经 `fieldError`(`:283-294`) 显示在对应字段旁(`:340-428`)；`useProfilesQuery.ts:557-585` mutation 失效 `proxyKeys.lists()` 与 `profileKeys.lists()` 即时刷新；缺 username/region_label 255 上限记 minor f002，主规则成立不判 VOID。
- AC-003：TICK-VALID，re_verified。`ProxyResponse`(`models.py:84-99`) 无 password 字段、仅 `has_password`；`toFields`(`:68-81`) 密码恒为 ""，`handleSubmit`(`:257-267`) 三态（留空省略键 / `clearPassword`→`null` / 非空→字符串）；密码框 `type="password"`、编辑态值空、无已存密码进 state / react-query 缓存 / DOM / URL，`clearLocalState`(`:193-209`) 关闭清空；AC-008 E2E 与 ProxyFormDialog 单测覆盖。
- AC-004：TICK-VALID，re_verified。`parseProxyUrl.ts:17-19,29-32` scheme 白名单、`:66-73` IPv6 方括号、`:52-61` `decodeURIComponent` 账密、`:81-85` port 1-65535、失败结果不含部分字段；`ProxyFormDialog.tsx:216-233` 仅 `result.ok` 时覆盖字段，非法只置 `pasteError`、已填字段不变（`ProxyFormDialog.test.tsx:287-303` 实证）；33 条表驱动用例重跑通过。
- AC-005：TICK-VALID，re_verified。`ProxyTable.tsx:46,103-119` `used_by_count>0` 禁用删除并提示先改绑；`ProxyListPage.tsx:33-48` `proxyInUseCount` 从 `ApiError.detail` / `.data.detail` 读 `code="proxy_in_use"` + `used_by_count`，不依赖 `errorCode`；`client.ts:180-187` 把 `payload.detail` 赋给 `.detail`，后端 `proxies_router.py:83-86` 的 409 body `{"detail":{"code":"proxy_in_use","used_by_count":N}}` 形状吻合；`confirmDelete`(`:94-100`) 用 `proxyInUse` 文案显示引用数。
- AC-006：TICK-VALID，re_verified。`ProxyTable.tsx:85-92` `<Link to={"/?proxy="+encodeURIComponent(id)}>`；`useEnvironmentFilters.ts:63` `searchParams.get("proxy")` 读取该参数、`:141` 按 `proxy_id` 过滤，`EnvironmentListPage.test.tsx:482-483` 有 `/?proxy=px2` 覆盖，闭环成立。
- AC-007：TICK-VALID，re_verified。`d031:5`、s013 `report.md:9,27`、`decisions.md:280,282`、`profile_management.md:63` 一致确认引擎支持带认证 SOCKS5 且 422 拒绝为未采用选项；`proxy_management.md:31-35` 规定「默认允许 + 仅后端 422 降级说明并保持表单」；实现 `validate()`(`:103`) 无 socks5 阻止、`isSocks5Unsupported` + banner(`:143-159,271-277`) 为该降级入口，真实满足「与 t035 结论一致」；task.md 字面过时另记 f003（改 spec，不计 FAIL）。
- AC-008：TICK-VALID，trust_prior。独立解析第 2 轮冻结门禁 `junit/e2e.xml`：102 例中 `test_ac008_proxy_library_outbound_via_ui` PASS（2 FAIL 为 t019 3.352s 基线与 p051 已记录 NotFound、2 SKIP）；通读 `test_proxy_library_e2e.py:259-322` 确认真实栈（FrontendAppTopologyHarness + 无头 Chrome + 本地记录代理）经 CDP `Page.navigate` 断言 `PROXY_GET` 日志，非假绿。真实栈执行属部署态，本会话未重跑，依赖冻结门禁产物。

8 条 AC 中 7 条 re_verified、1 条 trust_prior（AC-008）；trust_prior 占比 12.5%，未超 30%。

coverage = re_verified / 8

verdict: PASS

## Round 2 (2026-11-07T12:45:00+08:00)

- 落点校验：`git rev-parse --show-toplevel`（不带 `-C`，workdir=t038）输出精确等于 `t038 worktree` ✓；`git status --short` 25 个交付文件全部 staged（`M`/`A`）、无 `??`，无 reviewer 看不到的未跟踪交付文件，不判 INCOMPLETE。
- 指纹：只读调用 `review_scope_fingerprint()`（diff_anchor `1ca4cb4f…`）独立重算 = `b0716cf278d4ae49`，与本行一致；Round 1 旧指纹 `4a70d17b9064ad06` 已失效，按「取全文最后一条」规则本行覆盖前轮。并发会话于 13:06 向 `review_test.md` 追加其 Round 2（本人未改他人报告）；该文件属 `REVIEW_PROCESS_FILES` 排除项，写前/写后重算指纹均不变。
- 本轮独立复跑（非采信 implementer 自述）：`npx tsc -p tsconfig.test.json --noEmit` exit 0；`npx vitest run src/features/proxies` 3 文件 55 passed；`npm test` 54 文件 356 passed；`npm run design:lint` 0 error / 0 warning、79 files clean；`npm run design:check` up to date；`pytest tests/unit/test_repo_hygiene.py -q` 8 passed；`pytest tests/unit -q -n 4` 1165 passed；`.repo_template/tests -m contract` 257 passed / 1 skipped。
- 冻结门禁自行解析（第 3 轮 `.scratch/t038_evidence_20261107_123112/`）：`junit/e2e.xml` merged `tests=102 failures=1 errors=0 skipped=2`，唯一 FAIL `test_t019_switch_and_refresh_first_frame_within_2s_host_only`（`assert 3.363 <= 2.0`，t032 已登记基线），`test_runtime_coordinator_docker_e2e` 本轮未复现（PASS），2 skip 为 `test_t032_probe_*_recheck`；`tests.e2e.test_proxy_library_e2e::test_ac008_proxy_library_outbound_via_ui` PASS（`time=37.126`，无 failure/error/skipped 节点）。`manifest.json` / `suites.tsv`：8 个非 E2E suite（contract / integration / design_lint / design_check / frontend_test / frontend_build / requirements_check / image_packages）全 exit 0，unit=1、e2e=1；`t038_gate_final.log` 一致。
- 删除推测性降级路径核实（监督纠正项）：`ProxyFormDialog.tsx:147-154` 仅存 `describeError()`，`:266-268` catch 唯一出口 `setBanner(describeError(err))`，全文无 `isSocks5Unsupported`；`i18n.tsx` en/zh 无 `proxySocks5Unsupported` 键；`ProxyFormDialog.test.tsx` 仅 10 个 `it`，2 条专属测试名零命中，`submits authenticated socks5 without any frontend blocking`(`:322`) 与 `rejects username and region_label longer than 255`(`:370`) 保留；`docs/specs/proxy_management.md:31-35` 与 `docs/blueprint/frontend.md:88` 写明「直接支持、无降级路径」；`src/backend/cbrowser/api/v1/proxies_router.py:31-91` 409 仅 `proxy_name_in_use` / `proxy_in_use`，无 socks5 拒绝分支。相对 diff_anchor 的 `git diff` 三文件推测性符号计数全为 0；排除 `node_modules/.vitest-cache`（gitignore、未跟踪构建缓存）后全仓 `src/`+`tests/` 零命中。
- f002 修复保留核实：`validate()`(`:90-118`) 含 `username`/`region_label` ≤255（`:110-115`），`FieldKey`(`:47-54`) 已扩 2 键，`fieldError()`(`:274-285`) 字段旁错误在 `:380`/`:431` 渲染，`:370-387` 回归用例保留且本轮复跑通过。
- 测试处置清单 / 收尾核实（`progress.md` claim 仅作对照，结论以代码与门禁为准）：`:57-58` 2 条删除测试逐条写明「契约前提已被 d031 推翻 / 降级路径整体删除后无被测对象」；`:50-51` f003 与 test_f001 撤回理由含 d031 实测与「后端无 socks5 拒绝分支」；`:48` f001 处置为「已修：删除推测性降级路径」；`:69` 收尾报告写明 .md-only 理由（只改 3 个 .md、产品/测试代码零变化、按监督不重跑完整 E2E、同 t041 先例、finish 依据 = 第 3 轮完整门禁 + contract/unit 定向复跑）。第 3 轮 `logs/unit.log` 失败唯一为 `test_repo_hygiene` 命中 review 报告 home 路径（#89），`1 failed, 1129 passed`、`junit/unit.xml` 1165 tests / 1 failure；当前 3 个 .md home 绝对路径零命中；冻结 `frontend_test.log` 54/356 与本轮独立 `npm test` 54/356 一致，产品/测试代码零变化交叉验证成立 → .md-only 收尾判定成立。

reviewed_scope: b0716cf278d4ae49

## Findings

本轮 0 条新 finding（clean review，禁止凑数）。Round 1 三条 minor 全部以 diff / 代码核实已消除或按撤回流程作废，无残留 blocker，修复过程未引入新问题。

## 结论

- 前轮 finding 复核（以 diff / 代码为准，不采信处置表自称「已修」）：
    - `t038_code_f001`（minor，任意 422 误判 SOCKS5 不支持）：**已消除**。按监督纠正从根因删除整条推测性降级路径而非打文本匹配补丁：`isSocks5Unsupported` 函数与 catch 降级分支删除、`proxySocks5Unsupported` en/zh 键删除、2 条专属测试删除，所有错误统一 `describeError()`；后端无拒绝分支使该路径永不可达。核实见上。
    - `t038_code_f002`（minor，缺 `username`/`region_label` ≤255 校验）：**已消除**。校验、`FieldKey` 扩展、字段旁错误与回归用例均在最终交付代码中，本轮独立复跑通过。
    - `t038_code_f003`（minor，task.md AC-007 字面沿用 plan 旧假设）：**同意撤回**。`task.md:42` 字面仍未改，但按 d031（`docs/findings/d031_authenticated_socks5_supported.md:5`，Chromium 146 实测支持、API 不以 422 拒绝）、ADR 023（`decisions.md:280` 不采用 422 拒绝创建的降级路径）、`proxies_router.py` 无 socks5 拒绝分支，及监督「task.md 字面沿用旧假设、以权威结论为准」裁决，实现「直接支持、无降级」才与 t035 结论一致；裁决依据与「无拒绝分支」事实已写入 `proxy_management.md` 第 5 节、`frontend.md` 第 8 节与实施笔记。按共享规则「实现合理但与 spec 描述不符（spec 过时）→ 处置为改 spec / 以权威 ADR 为准，不计 FAIL」，本轮不计未解决 finding。
    - 测试轴 `t038_test_f001`（另一 reviewer Round 2 已复核同意撤回）与 code 轴 f003 同源，撤回理由含 d031 与「无拒绝分支」，一致。
- 本轮新发现：0 条，无 critical / important / minor。
- 未进表的提示：
    - 文件过大（降级规则只列路径与行数）：`src/frontend/src/features/proxies/ProxyFormDialog.tsx` 480 行，新建即 ≥400、\<800；其余新增源码 / 测试均低于阈值。
    - 圈复杂度：`parseProxyUrl.ts:21-98` 手算近似 McCabe ≈20，扁平 guard 链、无嵌套分叉、无可观测缺陷，按「≥10 结论段提示 / 不 blocking」仅此提示（Round 1 已记）。
    - 范围外观察：`review_code.md:60`（Round 1）仍叙述当时 `isSocks5Unsupported` 降级入口，属历史内容，按「不删改 Round 1」保留；当前产品代码为 `describeError()` 统一展示，不构成当前缺陷。`node_modules/.vitest-cache` 内 7 处推测性符号为 gitignore 构建缓存，非交付源码。`manifest.json` `all_passed=false` 仅由 t019 基线（t032 已登记）与 #89 unit（已定向复跑转绿）导致。`docs/tasks/t045…/review_*.md` 7 处去路径格式修复、p051 观察项均已登记，无新增。
    - 门禁状态：本小节追加前 `check_review_status.py` 报 `code_verdict=PASS` / `test_verdict=PASS` / `ac_review=ok` / `round=2` 但 `review_scope=stale` / `overall=INCOMPLETE`，根因为本报告最后一条 `reviewed_scope` 仍为 Round 1 旧值；本行写入后按「取全文最后一条」应转 `review_scope=ok` / `overall=PASS`。属流程状态，非代码缺陷。
- 总体判断：8 条 AC 在实现层全部 TICK-VALID；AC-007 按 d031 / ADR 023 /「后端无 socks5 拒绝分支」裁决「直接支持、无降级」成立，AC-008 依第 3 轮冻结真实栈 junit（自行解析 PASS）与 `test_proxy_library_e2e.py:150-322` 静态查证（UI 新建 → UI 引用 → UI 启动 → CDP `Page.navigate` → `PROXY_GET` 断言、headless、serial、无固定 sleep）成立。删除推测性路径核实通过、f002 真实修复保留、.md-only 收尾判定成立、定向复跑结论经独立复跑核实真实；无未解决 critical / important，0 条新 finding → PASS。
- 系统性 follow-up：无新增（`p051_e2e_container_vanish_during_gate`、t032 已登记 t019 基线、`repo_template#89` 已登记）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`ProxyTable.tsx:34-40,49-131` 列齐名称 / 协议 / 地址(`MonoValue`) / 认证(有/无文字) / 地区(码+标签) / 使用环境数 / 操作；`ProxyListPage.tsx:18-31` `filterProxies` 先按 scheme 再对 name/host/region_label 大小写不敏感匹配，可组合；`proxy_management.md:8` 明确搜索为地区标签；本轮 `npx vitest run src/features/proxies` 55 passed 独立复跑。
- AC-002：TICK-VALID，re_verified。`ProxyFormDialog.tsx:90-118` name 1-255 / host 1-512 / port 1-65535 / country_code 2 字母 / scheme 白名单 / username·region_label ≤255 与 `models.py:52,104-111` 一致，字段旁错误经 `fieldError():274-285` 在 `:338` 等渲染；`useProfilesQuery.ts:563-566,581-584` mutation 失效 `proxyKeys.lists()` 与 `profileKeys.lists()` 即时刷新；本轮 `tsc` + `npm test` 356 passed 独立复跑，f002 校验已在最终交付代码。
- AC-003：TICK-VALID，re_verified。`ProxyResponse`(`models.py:84-99`) 无 password 字段、仅 `has_password`；`toFields():75-88` 密码恒 ""，`handleSubmit():252-268` 三态（留空省略键 / `clearPassword`→`null` / 非空→字符串）；密码框 `type="password"`、编辑态值空、`clearLocalState():188-195` 关闭清空；`ProxyFormDialog.test.tsx:220-248` 断言 secret 不进 DOM / query cache，本轮复跑通过。
- AC-004：TICK-VALID，re_verified。`parseProxyUrl.ts:29-32,50-62,64-92` scheme 白名单 / `decodeURIComponent` 账密 / IPv6 方括号 / port 1-65535 / 失败不含部分字段；`ProxyFormDialog.tsx:211-228` 仅 `result.ok` 覆盖字段、非法只置 `pasteError`、已填字段不变（`:287-303` 实证）；33 条表驱动用例本轮复跑通过。
- AC-005：TICK-VALID，re_verified。`ProxyTable.tsx:46,103-119` `used_by_count>0` 禁用删除并提示先改绑；`ProxyListPage.tsx:33-48` `proxyInUseCount` 从 `ApiError.detail` / `.data.detail` 读 `code="proxy_in_use"` + `used_by_count`；`client.ts:180-187` 把 `payload.detail` 赋 `.detail`；`proxies_router.py:83-86` 409 body `{"detail":{"code":"proxy_in_use","used_by_count":N}}` 形状吻合；`confirmDelete():94-100` 用 `proxyInUse` 显示引用数；`ProxyListPage.test.tsx:329-347` 本轮复跑通过。
- AC-006：TICK-VALID，re_verified。`ProxyTable.tsx:85-92` `<Link to={"/?proxy="+encodeURIComponent(id)}>`；`useEnvironmentFilters.ts:63` 读 `searchParams.get("proxy")`、`:141` 按 `proxy_id` 过滤；`ProxyListPage.test.tsx:350-372` 断言 href 含 `?proxy=<id>` 且特殊 id 编码后无空格，本轮复跑通过。
- AC-007：TICK-VALID，re_verified。`d031:5` / `decisions.md:280` / `proxy_management.md:31-35` / `frontend.md:88` 一致确认 Chromium 146 支持带认证 SOCKS5、后端无 socks5 拒绝分支、API 永不返回该专用 422；`ProxyFormDialog.tsx:90-118` 无 socks5 阻止、`:230-269` 无条件提交、`:147-154` `describeError()` 统一错误展示，无降级路径、无「引擎不支持」文案；`ProxyFormDialog.test.tsx:322-341` 断言 socks5 + alice/s3cret 正常进入 payload 且无 banner、`:343-368` 409 object detail 走 `describeError`；相对 diff_anchor 的 diff 与全仓 grep 确认推测性代码零残留；task.md 字面过时按监督裁决撤回（f003），不计 FAIL；本轮独立复跑全绿。
- AC-008：TICK-VALID，trust_prior。真实栈 E2E 实跑需完整 Docker 拓扑，按监督 .md-only 要求本轮不重跑；依赖第 3 轮冻结证据 `.scratch/t038_evidence_20261107_123112/junit/e2e.xml`（本轮自行解析：102 例、FAIL=1 仅 t019 基线、ERROR=0、SKIP=2；`test_ac008_proxy_library_outbound_via_ui` PASS、`time=37.126`）与 `manifest.json`（8 个非 E2E suite exit 0）。E2E 代码独立静态查证：`test_proxy_library_e2e.py:150-170` UI 新建代理（非 POST 伪造）、`:173-191` UI 引用、`:136-140` UI 启动、`:213-256` CDP `Page.navigate`、`:268,319-322` 断言 `PROXY_GET http://cbrowser-ac008.invalid/ac008`（`wait_for_log` 超时抛错、`:322` `assert needle in text`）、`:104-113` `channel="chrome", headless=True`、`:30` serial、全文无固定 sleep。

8 条 AC 中 7 条 re_verified、1 条 trust_prior（AC-008）；trust_prior 占比 12.5%，未超 30%。

coverage = re_verified / 8

verdict: PASS
