# Task review t038（reviewer_focus: 测试）

- task：`t038_proxy_library_ui`
- spec：`docs/tasks/t038_proxy_library_ui/task.md`
- diff_anchor：`1ca4cb4fd4212ddfb7ad4b6c9bcfcbcc9b1df65d`
- target：`git diff 1ca4cb4fd4212ddfb7ad4b6c9bcfcbcc9b1df65d`
- round：1
- reviewed_at：2026-11-07T12:12:06+08:00
- 落点校验：`git rev-parse --show-toplevel`（不带 `-C`）= `t038 worktree` ✓；`git status --short` 无 `??`，23 个交付文件（含 `git add -N` 新文件）全部出现在 `git diff` 中，无隐藏交付文件，不判 INCOMPLETE；指纹经 `check_review_status.current_scope_fingerprint` 只读重算 = `4a70d17b9064ad06`，与本报告一致。

reviewed_scope: 4a70d17b9064ad06

## Findings

### t038_test_f001 - AC-007 契约区字面沿用 plan 旧假设，与已批准裁决冲突

- 严重度：minor（按共享规则「实现合理但与 spec 描述不符（spec 过时）」处置为改 spec，不计 FAIL，不阻断）
- 锚点：AC-007
- 位置：`docs/tasks/t038_proxy_library_ui/task.md:42`；`docs/findings/d031_authenticated_socks5_supported.md:5`；`docs/blueprint/decisions.md:280`；`docs/specs/proxy_management.md:31-35`
- 问题：`task.md:42` 字面要求「引擎不支持时阻止提交并说明原因」，沿用 plan 旧假设。ADR 023（`decisions.md:280`「不采用 422 拒绝创建的降级路径」）、d031（Chromium 146 实测支持带认证 SOCKS5）与 `docs/specs/proxy_management.md` 第 5 节（上下文区已获批准的决策）裁定为「默认允许 + 仅后端 422 时降级提示」。实施按裁决实现（`ProxyFormDialog.tsx:257-277` 无条件提交、`isSocks5Unsupported` 于 `:143-159` 捕获 422）。测试在裁决下覆盖正确行为：`ProxyFormDialog.test.tsx:322-341` 断言 socks5 + 用户名/密码正常提交且无 banner，`:343-369` 断言 422 展示 `proxySocks5Unsupported` 且弹窗不关闭、字段保留；无「因旧假设漏测」——按裁决本不应存在「前端阻止提交」的测试。打勾在裁决下成立，故本条仅要求文档对齐，不改代码、不计 FAIL。
- 建议：把 `task.md` AC-007 文字改为与 `docs/specs/proxy_management.md` 第 5 节一致（默认允许、422 降级），或注明字面为历史假设、以 ADR 023 为准。

## 结论

- 改测方向复核：无「迁就实现」的改测。唯一既有测试改动 `src/frontend/src/app/router.test.tsx:189-200` 把 `/proxies` 从 `placeholder-page` 循环移出、单独断言 `proxy-list-page`，与 `src/frontend/src/app/router.tsx:36-38` 同批把路由元素由 `PlaceholderPage` 改为 `ProxyListPage` 对应，属旧断言语义失效后的合理语义替换（prompt 亦声明）；新页面由 `ProxyListPage.test.tsx` 12 例与 E2E 另行覆盖，非就地把预期改成当前实现输出。其余扩散于 `i18n.test.tsx`（既有键集兜底，未改）、`useProfilesQuery.ts`（生产 hooks，非测试）。
- 本轮新发现：1 条（minor）。无 critical / important。
- 未进表的提示：
    - (1) 测试可信 / mock 边界：`ProxyFormDialog.test.tsx:90-101` 与 `ProxyListPage.test.tsx:127-141` 的 `makeStub` / `renderPage` 在 `ApiClientContext` 边界注入每例独立 stub，走真实 `useCreateProxyMutation` / `useUpdateProxyMutation` / `useDeleteProxyMutation`（`useProfilesQuery.ts:557-599`）与真实 `useProxiesQuery`，未 `vi.mock` 数据 hooks 模块、未对共享单例赋方法；夹具 `proxyFixture` 为生成类型 `ProxyResponse` 完整线形状（`ProxyFormDialog.test.tsx:51-69`），与 `EnvironmentListPage.test.tsx:162-163,177,252` 范式一致，符合 `docs/blueprint/frontend.md:51`。
    - (2) 弱鉴别力（可选覆盖扩展，不阻断）：`ProxyFormDialog.test.tsx:220-248` 的 query cache 断言所用 `queryData` 由测试自身 `setQueryData` 注入且不含 `password` 字段，对「生产是否把密码写进 cache」鉴别力有限；但该例的 DOM / 表单 state 断言真实触达生产（`toFields` 于 `ProxyFormDialog.tsx:68-81` 忽略 `proxy.password`，`:391-401` 密码框值空、`type="password"`）。更严格可让 `stub.list` 返回意外携带 password 的响应再断言 cache 不残留。属「可再加 case」，按规则不 blocking。
    - (3) AC-002「保存后列表即时更新」在 Vitest 层未直接断言 `proxyKeys.lists()` 失效（`useProfilesQuery.ts:563-566`），但 AC-008 E2E `_create_proxy_via_ui` 等待 `proxy-row-<id>` 出现（`test_proxy_library_e2e.py:166-170`）在真实栈覆盖即时更新；属可选扩展。
    - (4) AC-003「清除密码保存后 `has_password` 为 false」属后端响应状态，前端测试以 `ProxyUpdateRequest.password === null`（`ProxyFormDialog.test.tsx:205-218`）覆盖清除语义（spec 第 3 节三态）；未断言后端响应，范围在 t035 后端。
    - (5) AC-006 仅断言 `<Link href>` 含 `?proxy=<id>`（`ProxyListPage.test.tsx:350-372`，生产 `ProxyTable.tsx:85-92`），未做点击后按代理筛选的端到端；`useEnvironmentFilters` 的 `proxy` URL 参数由 t037 交付，属依赖范围外。
    - (6) 危险模式扫描全量（调查后判定，非语法命中）：无 `.skip` / `.only` / `vi.mock` / `jest.mock` / `expect(true).toBe(true)` / `assert True` / 注释掉的 expect / 删或反转 expect / `@ts-ignore` / `eslint-disable` / 阈值增大掩盖 / 程序赋值替代交互。`parseProxyUrl.test.ts:140,151` 的 `if (result.ok)` / `if (!result.ok)` 是判别联合类型收窄且前置有 `expect(result.ok).toBe(...)` 强制断言（`:139`、`:148`），不命中「条件跳过弱化断言」；`router.test.tsx:241` 的 `toBeTruthy` 是既有导航锚点断言、不在本 task diff；`test_proxy_library_e2e.py:305,328` 两处 `# noqa: BLE001` 经查为 CDP 就绪重试与 finally best-effort 清理的 broad-except 标注，重试失败经 `poll_until`（`tests/fixtures/wait.py:42-64`）超时暴露、清理异常不影响断言，不命中「静默错误」，不掩盖失败。
    - (7) 回归独立复验：本轮重跑 `cd src/frontend && npm test` → `Test Files 54 passed (54)` / `Tests 356 passed (356)`，且先执行 `tsc -p tsconfig.test.json` 严格类型检查通过；`npm run design:lint` → `0 error / 0 warning; 79 files clean`、`npm run design:check` → `design_tokens.css is up to date`。冻结证据 `.scratch/t038_evidence_20261107_113648/manifest.json` 9 个非 E2E suite 全 `exit_code: 0`（含 unit / contract / integration / frontend_test / frontend_build / design_lint / design_check），`suites.tsv` 一致。
    - (8) 第 2 轮 junit 独立解析：`junit/e2e.xml` merged `tests=102 failures=2 errors=0 skipped=2`；两 FAIL 为 `test_t019_switch_and_refresh_first_frame_within_2s_host_only`（`assert 3.3515 <= 2.0`，t032 已登记基线，p051 / t045 task.md 均引用）与 `test_runtime_coordinator_docker_e2e`（`docker.errors.NotFound` 404，p051 已登记观察项复现，`p051` 明载 t038 改动不创建 / 删除 `t007-be-coord` 容器、排除本 task 引入）；2 skip 为 `test_t032_probe_*_recheck`。`tests.e2e.test_proxy_library_e2e::test_ac008_proxy_library_outbound_via_ui` = PASS（`time=20.780`，无 skip / failure 节点）。`manifest.json` `all_passed=false` 仅由上述两个既登记失败导致，不构成 AC-008 假绿或失败掩盖。
    - (9) AC-008 静态查证：`test_proxy_library_e2e.py:150-170` 走 `/proxies` UI（`proxy-add` → 填表 → `proxy-form-submit`）新建代理并返回 `proxy-row-<id>` 的 id，`:173-191` 走 `env-new` UI 让环境引用该代理，`:136-140` 走 `session-launch-btn` UI 启动，`:213-256` CDP `Page.navigate` 驱动容器内 Chrome，`:268,319-322` `wait_for_log` 等 `PROXY_GET http://cbrowser-ac008.invalid/ac008` 并断言 needle（`wait.py:67-84` 超时抛 `TimeoutError`，非恒真）；`_launch_browser` `channel="chrome", headless=True`（`:104-113`）、`pytestmark = pytest.mark.serial`（`:30`）、全文无 `asyncio.sleep` / `time.sleep` 固定兜底（仅 `poll_until` / `wait_for_log` 带 deadline 轮询）；`TARGET_HOST` 为 `.invalid` 保留域，不经代理则无 `PROXY_GET`，断言有鉴别力。
    - (10) 范围外观察：diff 含 `docs/tasks/t045_e2e_gate_stability_cleanup/review_code.md`、`review_test.md` 各 3 行 `target` 路径脱敏改动，属流程文件、与 t038 测试轴无关，不进 finding 表。
- 总体判断：8 条 AC 打勾在测试与验证层均有真实、触达生产逻辑、非假绿的证据支撑；打勾测试复核逐条通过（含 URL 非法 22 例、密码三态、409 含 "3"、`?proxy=` 链接、add/edit 弹窗、socks5 提交、422 降级、AC-008 真实栈 junit PASS）；无未解决 critical / important，唯一 minor 为规格文字过时（按共享规则不计 FAIL），PASS。
- 系统性 follow-up：`docs/pending/todo/p051_e2e_container_vanish_during_gate.md`（已登记观察项，本轮 E2E 失败集合中的 `test_runtime_coordinator_docker_e2e` 归此，无需新建）；无新增。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`ProxyListPage.test.tsx:187-279` 断言 7 列表头与 px1/px2 行内容（host:port / 认证 / 国家码+标签 / 使用数 / 2）、按 name/host/region 大小写不敏感搜索、`proxy-scheme-filter` 与搜索组合、`filterProxies` 纯逻辑；生产 `ProxyListPage.tsx:18-31` 与 `ProxyTable.tsx:31-92` 真实被渲染触达，本轮 `npm test` 356 全过。
- AC-002：TICK-VALID，re_verified。`ProxyFormDialog.test.tsx:154-183` 断言 create payload（name/scheme/host/port、`port` 为 number、不含 password）、`onOpenChange(false)` 与成功 toast；`:305-320` 断言 name 空时 `proxy-form-name-error` 字段旁错误 + `proxy-form-error` 汇总且不提交；校验实现 `ProxyFormDialog.tsx:83-105`、提交 `:235-277` 真实触达；`router.test.tsx:198-200` 断言 `/proxies` 渲染 `proxy-list-page`。
- AC-003：TICK-VALID，re_verified。`ProxyFormDialog.test.tsx:185-203` 留空保存断言 update payload 不含 `password` 键；`:205-218` 点 `proxy-form-clear-password` 断言 `data.password === null`；`:220-248` 注入含 secret 的 proxy 断言密码框空、`document.body.textContent` 与 `queryClient` cache 不含 secret / `"password"`，生产 `toFields`（`:68-81`）与三态提交（`:259-266`）真实触达。
- AC-004：TICK-VALID，re_verified。`parseProxyUrl.test.ts:4-105` 10 组合法（含 IPv6 方括号、百分号编码账密、大小写 scheme、路径/片段、多冒号密码）与 `:107-130` 22 组非法（空 / 缺 scheme / 无端口 / 端口越界 / 非法 scheme / 坏编码 / 多 @ / 未闭合括号 / 裸 IPv6）表驱动 `it.each` 断言判别联合结果形状，共 33 例；`ProxyFormDialog.test.tsx:250-303` 通过 `proxy-paste-url-apply` 走 UI 断言合法 URL 填字段且不覆盖 name/country/region/notes、非法 URL 显示 `proxyPasteUrlInvalid` 且已填字段保持不变。
- AC-005：TICK-VALID，re_verified。`ProxyListPage.test.tsx:283-294` 断言 `used_by_count>0` 行 `proxy-delete-px1` / `px4` disabled 且显示 `proxyDeleteBlocked`、未引用行可点；`:329-347` 以 `new ApiError("Conflict",409,{detail:{code:"proxy_in_use",used_by_count:3}})` 在 ApiClient 边界注入 409，断言 `proxy-list-error` 文本含 `"3"`、`"environments"` 与 `en.proxyInUse.replace("{count}","3")`，真实触达 `ProxyListPage.tsx:33-48` 的 `proxyInUseCount`。
- AC-006：TICK-VALID，re_verified。`ProxyListPage.test.tsx:350-372` 断言 `proxy-used-by-px1` / `px3` 的 href 含 `?proxy=<id>`，特殊 id `px/a b` 编码后无空格，触达 `ProxyTable.tsx:85-92` 的 `<Link to={"/?proxy="+encodeURIComponent(id)}>`。
- AC-007：TICK-VALID，re_verified。按 ADR 023（`decisions.md:280`）/ d031 / `docs/specs/proxy_management.md:31-35` 裁决（默认允许 + 422 降级）复核：`ProxyFormDialog.test.tsx:322-341` 断言 socks5 + alice/s3cret 正常提交进入 update payload 且无 `proxy-form-banner`，`:343-369` 注入 422 `ApiError` 断言 `proxySocks5Unsupported` banner、`onOpenChange` 不关闭、name/host 保留，触达 `ProxyFormDialog.tsx:143-159,257-277`；裁决分支均有测试、未因旧假设漏测（详见 f001，spec 文字过时不计 FAIL）。
- AC-008：TICK-VALID，trust_prior。真实栈 E2E 需完整 Docker 拓扑，本轮未重跑实跑；依赖第 2 轮冻结证据 `junit/e2e.xml`（本轮独立解析：`test_ac008_proxy_library_outbound_via_ui` PASS、`time=20.780`、失败集合仅 t019 基线 + p051 记录项）与 `manifest.json`（9 个非 E2E suite 全 exit 0）。E2E 代码本身已静态独立查证：`test_proxy_library_e2e.py` 走 UI 新建代理 / UI 引用 / UI 启动、CDP 导航、断言本地记录代理 `PROXY_GET`、`headless=True`、serial、无固定 sleep 兜底，非直接 POST 伪造、非假绿。

coverage = 7 / 8

verdict: PASS

## Round 2 (2026-11-07T12:45:00+08:00)

- 落点校验：`git rev-parse --show-toplevel`（不带 `-C`，workdir=t038）= `t038 worktree` ✓；`git status --short` 25 个交付文件全部 staged（`M` / `A`）、无 `??`，无隐藏交付文件，不判 INCOMPLETE。
- 指纹：只读调用 `check_review_status.current_scope_fingerprint(diff_anchor)` 重算 = `b0716cf278d4ae49`，与本轮 reviewed_scope 一致；Round 1 旧指纹 `4a70d17b9064ad06` 已失效，按「取全文最后一条」规则本行覆盖前轮。
- 本轮独立重跑：先 `npx tsc -p tsconfig.test.json` 通过；`cd src/frontend && npm test` → `Test Files 54 passed (54)` / `Tests 356 passed (356)`；`npx vitest run src/features/proxies` → `3 passed / 55 passed`；`pytest tests/unit/test_repo_hygiene.py -q` → `8 passed`；`.repo_template/tests -m contract` → `257 passed, 1 skipped`；`pytest tests/unit -q -n 4` → `1165 passed, 4 warnings`。

reviewed_scope: b0716cf278d4ae49

## Findings

本轮 0 条新 finding（clean review，禁止凑数）。危险模式「删测试」语法命中 2 条 `it`，按 prompt 调查后判定为合法删除，理由见结论，不进 finding 表。

## 结论

- 前轮 finding 复核：
    - `t038_test_f001`（Round 1，minor，AC-007 契约区字面沿用 plan 旧假设）：`task.md:42` 字面仍未改（仍写「引擎不支持时阻止提交并说明原因」），文字层面「仍存在」；实施侧按 `progress.md:51` 撤回，依据 d031 / ADR 023 / `docs/specs/proxy_management.md:31-35` 已写入裁决与「后端无拒绝分支」事实，且改 AC 措辞影响编号永久归属与 review 基准。独立核实 `docs/findings/d031_authenticated_socks5_supported.md:5`（Chromium 146 实测支持、API 不以 422 拒绝 socks5+凭据）、`docs/blueprint/decisions.md:280`（不采用 422 拒绝创建的降级路径）、`src/backend/cbrowser/api/v1/proxies_router.py:31-91`（409 仅 `proxy_name_in_use` / `proxy_in_use`，无 socks5 拒绝分支）全部属实。按共享规则「实现合理但与 spec 描述不符（spec 过时）→ 处置为改 spec，不计 FAIL」，且本轴为测试层，spec 字面不影响测试覆盖真实性 → 同意撤回，不计未解决 finding。
    - code 轴 Round 1 三条（非本轴 finding，按 diff 核实）：`t038_code_f001`（任意 422 误标 SOCKS5 不支持）→ 降级路径整体删除，已消除；`t038_code_f002`（缺 username/region_label ≤255）→ `ProxyFormDialog.tsx:110-115` 补校验 + `ProxyFormDialog.test.tsx:370-387` 回归测试，本轮独立复跑通过，已消除；`t038_code_f003`（spec 字面过时）→ 同 test_f001 撤回。
- 推测性测试删除复核：删 2 条 `it` 命中「删测试」语法，调查后判定合法。`ProxyFormDialog.test.tsx` 现 10 个 `it`，已无 `shows the socks5-unsupported banner on a 422 and keeps the dialog open` 与 `does not mislabel an unrelated 422 as socks5-unsupported`；被测对象 `isSocks5Unsupported` 降级分支与 `proxySocks5Unsupported` 文案键已整体删除，全仓 grep `Socks5Unsupported|proxySocks5|socks5-unsupported|isSocks5` 在 `src/frontend/src` 产品/测试/i18n 零命中（残留仅 `progress.md` 实施笔记/处置表、`review_code.md` / `review_test.md` Round 1 历史叙述，按「不删改 Round 1」保留），无 `en.proxySocks5Unsupported`；`proxies_router.py` 无 socks5 拒绝分支、API 永不返回该专用 422（d031 / ADR 023），2 条属为不存在生产分支补的推测性测试；`progress.md:57-58` 测试处置清单逐条写明删除理由；替代覆盖真实存在（`:322-341` AC-007 正向、`:343-368` describeError 结构化展示、`:370-387` f002 校验），测试总数 356 与第 3 轮冻结 `frontend_test.log`（12:31:16，54/356）及本轮独立重跑完全一致 → 合法删除，不出 finding。
- 保留测试复核（非假绿、真实触达生产逻辑）：`ProxyFormDialog.test.tsx` / `ProxyListPage.test.tsx` / `parseProxyUrl.test.ts` 本轮全文重读 + `npx vitest run src/features/proxies` 55 passed 独立复跑。stub 仅注入 `ApiClientContext` 边界（`makeStub` / `renderPage`），走真实 `useCreateProxyMutation` / `useUpdateProxyMutation` / `useDeleteProxyMutation`（`useProfilesQuery.ts:557-599`，失效 `proxyKeys.lists()` 见 `:564,:582,:595`），未 `vi.mock` 自身模块、未对共享单例赋方法；409 object detail（`:343-368` → `ProxyFormDialog.tsx:147-154,:266-268`）、密码三态（`:185-248` → `toFields:75-88`、提交 `:252-268`）、URL 解析 33 例表驱动（`parseProxyUrl.test.ts:132-156`，`if (result.ok)` 前置 `:139` / `:148` 有 `expect(result.ok).toBe(...)` 强制断言，不命中条件跳过弱化断言）、列与筛选（`ProxyListPage.test.tsx:186-279`）、409 引用数（`:329-347`）、跳转（`:350-372`）、255 校验（`:370-387` → `validate():110-115`）均真实触达生产逻辑；无恒真断言 / `.skip` / `.only` / 注释掉或反转 expect / `@ts-ignore` / `eslint-disable` / 阈值增大 / 程序赋值替代交互；E2E 两处 `# noqa: BLE001`（`test_proxy_library_e2e.py:305,328`）为 CDP 就绪重试与 finally best-effort 清理，重试失败经 `poll_until` 超时暴露，不掩盖失败。
- AC-008 冻结门禁复核：`.scratch/t038_evidence_20261107_123112/junit/e2e.xml` 本轮自行解析，merged `tests=102 failures=1 errors=0 skipped=2`；唯一 FAIL `test_t019_switch_and_refresh_first_frame_within_2s_host_only`（`assert 3.363 <= 2.0`，t032 已登记基线），2 skip 为 `test_t032_probe_*_recheck`；`tests.e2e.test_proxy_library_e2e::test_ac008_proxy_library_outbound_via_ui` PASS（`time=37.126`），无 failure / error / skipped 节点；失败集合仅 t019 基线（第 3 轮 `test_runtime_coordinator_docker_e2e` 未复现），`all_passed=false` 仅由该基线导致，不构成 AC-008 假绿。`manifest.json` / `suites.tsv`：8 个非 E2E suite exit 0、unit=1、e2e=1，`t038_gate_final.log` 一致。静态查证 `test_proxy_library_e2e.py`：`_create_proxy_via_ui:150-170` 走 `/proxies` UI（`proxy-add` → `fill` → `proxy-form-submit` → 等 `proxy-row-<id>` 取 id），非 POST 伪造；`_create_profile_with_proxy_via_ui:173-191` 走 `env-new` UI；`launch_profile_via_ui:136-140` 走 `session-launch-btn`；`_cdp_navigate:213-256` CDP `Page.navigate` 到 `cbrowser-ac008.invalid`；`needle:268` + `wait_for_log:319-322` 断言 `PROXY_GET http://cbrowser-ac008.invalid/ac008`（超时抛错、`:322` `assert needle in text`）；`_launch_browser:104-113` `channel="chrome", headless=True`；`:30` `pytestmark = pytest.mark.serial`；全文无 `asyncio.sleep` / `time.sleep` 固定兜底（仅 `poll_until` / `wait_for_log` 带 deadline 轮询）。
- .md-only 收尾复核：第 3 轮 `logs/unit.log` 失败唯一为 `tests/unit/test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths`（`AssertionError` 集合仅 `docs/tasks/t038_proxy_library_ui/review_code.md` / `review_test.md` 的 home 绝对路径，#89 模板缺陷复现），`1 failed, 1129 passed`，失败集合不含任何产品/测试代码 → 「unit 曾 exit 1 仅因 home 路径」成立。当前 3 个 .md（`review_code.md` / `review_test.md` / `progress.md`）grep home 绝对路径零命中，去路径修复生效（`review_test.md:6,9` 现用 `t038 worktree` 占位、去掉 `git -C '<abs>'`）。产品/测试代码零变化交叉验证：第 3 轮 `logs/frontend_test.log`（12:31:16）`54 passed / 356 passed`，与本轮独立重跑 `npm test` `54 / 356` 完全一致；第 3 轮冻结 E2E junit 与当前 `test_proxy_library_e2e.py` 静态查证一致。定向复跑结论真实（本轮独立重跑）：`test_repo_hygiene` `8 passed`、contract `257 passed, 1 skipped`、unit `1165 passed`。`progress.md:69` 收尾报告写明「只改这 3 个 .md、产品/测试代码零变化、按监督要求不重跑完整 E2E（同 t041 先例）、finish 依据 = 第 3 轮完整门禁 + 本次 contract/unit 复跑」理由 → .md-only 收尾判定成立，不重跑完整 E2E 合理。
- 改测方向复核：无「迁就实现」的改测。删除的 2 条是整体删除并写明理由（符合「旧测试或原样保留或整体删除并写明理由，禁止就地把旧测试预期改成当前实现输出」）；`:343-368` 与 `:370-387` 为新增覆盖新语义的测试；`ProxyListPage.test.tsx` / `parseProxyUrl.test.ts` 既有断言未就地改预期。
- 本轮新发现：0 条（无 critical / important / minor）。
- 未进表的提示：
    - (1) `review_code.md:60`（Round 1 code report）仍描述当时 `:143-159` 的 `isSocks5Unsupported` 降级入口，属历史 Round 1 内容，按「不删改 Round 1 / 不改他人 review 报告」保留；当前产品代码为 `describeError():147-154` 统一错误展示，不构成当前实现缺陷。
    - (2) `manifest.json` 的 `command` 字段含 worktree 绝对路径，属 `.scratch` 冻结证据（gitignore、流程文件），不在 reviewed_scope 指纹计算内，`test_repo_hygiene` 只扫 tracked 文件，本轮定向 `8 passed` 佐证。
    - (3) `docs/tasks/t045_e2e_gate_stability_cleanup/review_code.md` / `review_test.md` 的 7 处去路径格式修复、t019 基线、p051 观察项、#89 模板缺陷均属已登记范围外观察，无新增。
    - (4) 可选覆盖扩展（不阻断）：AC-002 的 `proxyKeys.lists()` 失效在 Vitest 层未直接断言，AC-006 未做点击后按代理筛选的端到端；均 Round 1 已列「可再加 case」，按规则不 blocking。
- 总体判断：8 条 AC 在测试与验证层全部 TICK-VALID；推测性测试删除合法且覆盖完整（删 2 补 2、356 总数不变、独立重跑全绿）、保留测试非假绿、真实触达生产逻辑；.md-only 收尾判定成立，定向复跑结论经独立重跑核实真实；AC-008 第 3 轮冻结 junit 自行解析 PASS、失败集合仅 t019 基线；无未解决 critical / important，0 条新 finding → PASS。
- 系统性 follow-up：无新增（`p051_e2e_container_vanish_during_gate`、t032 已登记 t019 基线、`https://github.com/TuTouPower/repo_template/issues/89` 已登记）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`ProxyListPage.test.tsx:186-279` 断言 7 列头与 px1/px2 行内容（host:port / 认证 / 国家码+标签 / 使用数 2）、name/host/region 大小写不敏感搜索、协议筛选与搜索组合、`filterProxies` 纯逻辑；本轮 `npx vitest run src/features/proxies` 55 passed + `npm test` 356 passed 独立重跑，生产 `ProxyListPage.tsx` / `ProxyTable.tsx` 真实渲染触达。
- AC-002：TICK-VALID，re_verified。`ProxyFormDialog.test.tsx:154-183` create payload（name/scheme/host/port 为 number、不含 password）、成功 toast 与关闭；`:305-320` name 空时 `proxy-form-name-error` 字段旁错误 + 汇总且不提交；`:370-387` username/region_label >255 字段旁错误（f002）；`useProfilesQuery.ts:564,582,595` mutation 失效 `proxyKeys.lists()` 支撑「保存后列表即时更新」；本轮独立重跑全绿。
- AC-003：TICK-VALID，re_verified。`ProxyFormDialog.test.tsx:185-203` 留空保存 update payload 无 `password` 键；`:205-218` 清除密码 `data.password === null`；`:220-248` 注入含 `STORED_SECRET_9f3` 的 proxy 断言密码框空、`body.textContent` 与 query cache 均不含 secret / `"password"`，触达 `toFields:75-88` 与三态提交 `:252-268`。
- AC-004：TICK-VALID，re_verified。`parseProxyUrl.test.ts:132-156` 10 合法（IPv6 方括号、百分号编码账密、大小写 scheme、路径/片段、多冒号密码）与 22 非法表驱动共 33 例 + IPv6 去括号用例；`ProxyFormDialog.test.tsx:250-303` 走 `proxy-paste-url-apply` UI 断言合法 URL 填字段且不覆盖 name/country/region/notes、非法 URL 显示 `proxyPasteUrlInvalid` 且已填字段保持；本轮 `npx vitest run src/features/proxies` 独立重跑。
- AC-005：TICK-VALID，re_verified。`ProxyListPage.test.tsx:283-294` `used_by_count>0` 行删除按钮 disabled + `proxyDeleteBlocked`；`:329-347` 在 ApiClient 边界注入 409 `ApiError`（detail `{code:"proxy_in_use",used_by_count:3}`）断言 `proxy-list-error` 含 `"3"` / `"environments"` / `en.proxyInUse.replace("{count}","3")`；`ProxyFormDialog.test.tsx:343-368` 409 object detail 走 `describeError()`；另 `proxies_router.py:79-91` 真实返回该 409 形状。
- AC-006：TICK-VALID，re_verified。`ProxyListPage.test.tsx:350-372` 断言 `proxy-used-by-px1` / `px3` 的 href 含 `?proxy=<id>`，特殊 id `px/a b` 编码后无空格，触达 `ProxyTable.tsx:85-92` 的 `<Link>`。
- AC-007：TICK-VALID，re_verified。按 d031 / ADR 023（`decisions.md:280`）/ `proxy_management.md:31-35` 裁决「直接支持、无降级路径」复核：`ProxyFormDialog.test.tsx:322-341` 断言 socks5 + alice/s3cret 正常进入 update payload 且无 `proxy-form-banner`，不为不存在的 422 补测；`ProxyFormDialog.tsx:90-118` `validate()` 无 socks5 阻止、`:230-269` 无条件提交、`:147-154` `describeError()` 统一错误展示；`proxies_router.py:31-91` 无 socks5 拒绝分支（409 仅 `proxy_name_in_use` / `proxy_in_use`）；源码/测试/i18n 无 `proxySocks5Unsupported` 残留；本轮独立重跑全绿。
- AC-008：TICK-VALID，trust_prior。真实栈 E2E 实跑需完整 Docker 拓扑，本轮按监督要求不重跑；依赖第 3 轮冻结证据 `.scratch/t038_evidence_20261107_123112/junit/e2e.xml`（本轮自行解析：merged 102 / FAIL=1 仅 t019 基线 / SKIP=2；`test_ac008_proxy_library_outbound_via_ui` PASS、`time=37.126`）与 `manifest.json`。E2E 代码本身已独立静态查证：`test_proxy_library_e2e.py:150-170` 走 UI 新建代理（非 POST 伪造）、`:173-191` UI 引用、`:136-140` UI 启动、`:213-256` CDP 导航、`:268,319-322` 断言 `PROXY_GET`、`:104-113` headless Chrome、`:30` serial、全文无固定 sleep。

coverage = 7 / 8

verdict: PASS
