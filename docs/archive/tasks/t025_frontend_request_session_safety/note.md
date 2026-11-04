---
tid: "t025"
slug: "frontend_request_session_safety"
title: "修复前端请求安全边界与会话动作残余缺陷"
status: "done"
branch: "t025_frontend_request_session_safety"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "e171d1a1a3268afa3693626c8e72e80feca3b0b9"
depends_on: ""
conflicts_with: "t026,t031"
note: "来源 p018；云端 Muse 实施，真实拓扑统一交 t032 验收"
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-04：从 p018 聚合立项，核实基线 main@c6a9322；只创建 backlog，不 start。
- 云端范围与本地最终 t032 分离；真实环境未执行不能按通过回填。
- 2026-11-04：按三方审阅修订：背景更正 apply 重试根因（服务端重放 no-op，客户端空等 stopped）；AC-001 扩到 SSE 与 downloadUrl；AC-003 补 AppLayout/ProfileDetailPage；AC-005 收窄到生产 AppProviders 默认 retry；红测证据须记入本笔记。
- 2026-11-04 执行（attempt 1 / exec-main-20261104-t025，base=main@e171d1a）：preflight PASS。基线（未改实现）前端全量：test:types 零错误、Vitest 28 文件 164 全过、build 见收尾。
- 红测证据（AC-006，修复前实现上运行新增回归，命令 `NODE_OPTIONS=--no-experimental-webstorage npx vitest run <files>`）：
  - `src/shared/api/client.sameorigin.test.ts`：4 条反斜杠变体（`/\evil.example`、`\evil.example`、`/\evil.example` 混合、`\\evil.example\...`）在 fetch 前未被拒绝（fetch 被调用）；跨源 baseUrl 配置下 fetch 直达 evil.example；downloadUrl 产出跨源链接；logout 网络失败后内存 CSRF token 未清（`tok-1` 残留）。绝对/协议相对/https: 变体与相对同源正例为既有守卫，红测时已通过。
  - `src/shared/api/sse.sameorigin.test.ts`：2 条全红——绝对跨源 url 与 `/\evil.example` 变体 url 均被 fetch。
  - `src/app/providers.unauthorized.test.tsx`：1 条全红——SSE 401 触发 logout 且 HTTP 失败后，`getCsrfToken()` 仍为 `tok-xyz`（且 `void logout()` 的 rejection 无处置）。
  - `src/features/profiles/useProfilesQuery.applyresume.test.tsx`：3 红 2 绿——「start 已生效但响应丢失」重试时重发 stop 后空等 stopped 直至 20s 测试超时（即 p018 复现形态）；「stop 已生效、start 未生效」重试重发 stop（stop 调用 2 次）；「状态查询持续失败」仍发送 stop（应先观测、有界报错）。守卫 2 条（stop 未生效重跑、等待期瞬时查询失败容忍）红测时已通过。
  - `src/features/profiles/BrowserSessionPage.isolation.test.tsx`、`src/app/AppLayout.isolation.test.tsx`、`src/features/profiles/ProfileDetailPage.isolation.test.tsx`：各 2 条全红——A 的 error 在切换 B 后仍渲染（`session-start-error` / `display-apply-error` / `profile-display-apply-error` 元素非空），A pending 时 B 的按钮被禁用，A 迟到失败污染 B。
  - `src/app/providers.defaults.test.tsx`（AC-005 接线补测，非缺陷回归）：红测时 2 条已通过，属缺测补齐。
- 2026-11-04 实施完成（红测转绿后全量核验）：新增 `src/frontend/src/shared/api/same_origin.ts`（`resolveSameOriginUrl` 以 URL 解析器按最终解析 URL 判同源，覆盖反斜杠/协议相对/绝对变体）；client.ts 删除 baseUrl 配置、request 先校验同源再附凭据/CSRF、artifacts.downloadUrl 只返回同源 path、auth.logout try/finally 清 token；sse.ts 删除 url 配置、固定 `/api/v1/events` 并同源校验；providers.tsx SSE unauthorized 回调改 `void logout().catch(() => undefined)` 明确处置 rejection；useProfilesQuery.ts 新增导出 `scopeMutationToProfile`（按 mutation variables 目标隔离动作状态）+ apply 阶段跟踪（先观测当前 runtime：已 stopped 跳过 stop、start 已生效且 desired=running 时识别新实例收敛、观测 3 次连续失败有界报错、start 标记在发起前置位）；BrowserSessionPage / AppLayout / ProfileDetailPage 全部改用 scoped 状态，ProfileDetailPage 本地 error/success 横幅随 profileId 变化重置。既有夹具迁移：client/sse 两组测试改用只改写 origin 的 fetch 转发 stub（断言保持），artifacts 测试按规格删除 baseUrl 配置改写为新契约并注释 t025 理由，AppLayout.focus.test 的 mock 改展开真实模块导出（断言未动）。长期文档：access_control.md / profile_management.md 新增 t025 节、blueprint frontend.md/testing.md 补口径、specs_index 两行加 t025 并更新时间戳。
- 门禁实测（2026-11-04）：前端 `npm test` = test:types 零错误 + Vitest 36 文件 192 全过（基线 28 文件 164，净增 8 文件 28 测试）；`npm run build` 通过（含 dist freshness 校验）。仓库总门禁 scripts/run_gates.sh：contract 169 passed；unit 749 passed, 1 skipped（与 base 一致）；integration 115 passed, 1 failed——`test_api_search_defaults_routes::test_retry_route_requires_csrf_and_maps_outcomes` 为干净 base 同 ID 存量失败（t024 已核实），本 task 未触后端代码，非回归；脚本因该存量失败停在 integration 段，前端段已单独实测全过。黑盒 E2E（CBROWSER_RUN_E2E）本机无 Docker/真实拓扑，按用户既定豁免口径跳过按 pass 计；真实拓扑回归统一交 t032。
- Review Round 1（full 双路）：code 路 FAIL（t025_code_f001 important：ProfileDetailPage 本地横幅通道未按 Profile 隔离，处理器 await 后无条件写 setError/setSuccess；t025_code_f002 minor：ApplyStage.preStopInstanceId 只写不读，与 spec「据此识别新实例」口径不符）；test 路 PASS（t025_test_f001 minor：sse.sameorigin 负例断言可真空通过；t025_test_f002 minor：sse_hardening 尾事件 50ms 固定睡眠负载抖动；t025_test_f003 minor：AC-003 回切 A 子句无覆盖）。五条全部在本 task 内修复。
- 修复轮红测证据（修复前实现上运行，命令同上 vitest run 五文件）：ProfileDetailPage.isolation 新增「late update failure/success」2 条全红（B 上出现 A 的错误文案 / profile-save-success）；applyresume 新增「pre-stop instance was externally restored」1 条红（final runtime_instance_id 为 i1 而非 i2，旧判定误跳 stop/start）；BrowserSessionPage 回切 A 用例与 sse.sameorigin 补强（urls.length>0）、sse_hardening 轮询改造在旧实现上即绿（覆盖/可靠性补强，非缺陷红测）。合计 3 红 14 绿。
- 修复轮实施与绿测（2026-11-04）：ProfileDetailPage 五个处理器捕获 targetId、以 activeProfileIdRef 守卫 await 后的横幅写入、导航、dirtyFields 清理与 success 定时器；useProfilesQuery 的 startAlreadyEffective 引入 instanceEvidence（新旧实例 id 均已知须不同、任一未知回退 desired/observed），spec 口径同步更新。定向五文件 17/17 全过；前端全量 npm test 36 文件 196 全过（192+新增 4）、npm run build 通过、git diff --check 干净。
- Review Round 2（full 双路）：code/test 均 PASS、零新 finding，五条 Round 1 finding 全部复核为真实修复（AC 复验 coverage code 5/6、test 6/6）。code 路结论段附范围外观察：sse_hardening 的 401 用例（固定 100ms 睡眠）全量首跑抖动失败一次、单跑与二轮全量均过——与 t025_test_f002 同类同文件，按 f002 处置延伸顺手修复：正向等待改 vi.waitFor 轮询、保留 50ms 负向窗口确认 401 后不重连，断言不变；该文件连续 3 轮复跑全过。此改动使 review scope 变更，按流程进 Round 3 复审。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-04T08:51:16+08:00 code / 2026-11-04T08:52:32+08:00 test)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t025_code_f001|important|已修|五个本地处理器捕获 targetId 并以 activeProfileIdRef 守卫 await 后的横幅/导航/dirtyFields/定时器写入，补迟到失败与迟到成功 2 条回归（先红后绿）|src/frontend/src/features/profiles/ProfileDetailPage.tsx；ProfileDetailPage.isolation.test.tsx|
|t025_code_f002|minor|已修|startAlreadyEffective 引入 instanceEvidence：新旧实例 id 均已知时须不同、任一未知回退 desired/observed；补外部恢复旧实例用例（先红后绿），spec 口径同步|src/frontend/src/features/profiles/useProfilesQuery.ts；useProfilesQuery.applyresume.test.tsx；docs/specs/profile_management.md|
|t025_test_f001|minor|已修|sse.sameorigin 两条负例补 urls.length>0 正向锚点，消除真空通过|src/frontend/src/shared/api/sse.sameorigin.test.ts|
|t025_test_f002|minor|已修|sse_hardening 尾事件用例固定 50ms 睡眠改 vi.waitFor 轮询，断言不变；Round 2 后同文件 401 用例的同类固定 100ms 睡眠按本条延伸一并改轮询（断言不变）|src/frontend/src/shared/api/sse_hardening.test.ts|
|t025_test_f003|minor|已修|BrowserSessionPage 补 A→B→A 回切用例，断言回切后呈现 A 自身动作状态|src/frontend/src/features/profiles/BrowserSessionPage.isolation.test.tsx|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：前端 `npm test`（test:types 零错误 + Vitest 36 文件 196 全过；基线 28 文件 164，净增 8 文件 32 测试，含 review 修复轮新增 4 条）；`npm run build` 通过。仓库总门禁 run_gates.sh（修复轮前口径，修复仅动前端测试与前端实现、后端数字不变）：contract 169 passed、unit 749 passed/1 skipped（与 base 一致）、integration 115 passed + 1 failed（`test_retry_route_requires_csrf_and_maps_outcomes`，干净 base 同 ID 存量失败，本 task 未触后端，非回归）。
- 黑盒：本机无 Docker/真实拓扑，CBROWSER_RUN_E2E 按用户既定豁免口径跳过、按 pass 计；真实拓扑回归按规格统一交 t032 验收。来源 p018 已由立项侧以 resolution=transferred 归档（真实拓扑执行关联 t032），本 task 不重复立项。
- review：full 双路三轮闭环。Round 1：code FAIL（f001 important/f002 minor）、test PASS（f001–f003 minor）；五条 finding 全部已修（处置表 Round 1）。Round 2：双路 PASS、零新 finding。Round 2 后一处同类测试等待机制延伸改动（sse_hardening 401 用例轮询化）进 Round 3：双路 PASS、零新 finding。checker 终态 overall=PASS、review_scope=ok、round=3、next_action=finalize。
- AC 判定：见 `task.md` 行内打勾（AC-001–AC-006 全部 `- [x]`；reviewer 复验 coverage code 5/6（AC-006 trust_prior）、test 6/6）

### 结果摘要

- 三入口（ApiClient 请求 / SSE / downloadUrl）按最终解析 URL 同源判定，跨源与反斜杠变体在 fetch 前拒绝，删除 baseUrl/url 跨源配置面；logout 失败也清 CSRF token，SSE unauthorized 回调的 rejection 明确处置。
- 会话动作状态按目标 Profile 隔离呈现（scoped mutation + 详情页本地处理器守卫），迟到响应不污染当前 Profile，回切按自身状态呈现。
- apply 阶段跨重试保存：先观测再续跑，start 已生效凭实例证据识别新实例收敛，同 id 旧实例被外部恢复时仍走完整 stop/start；生产 AppProviders 默认 retry 接线补测通过。
- 遗留：真实拓扑回归归 t032（规格既定）；无新增 pending/finding。

### 长期文档闭环

- specs_index：access_control、profile_management 两行关联 task 已加 t025，时间戳已更新。
- specs：access_control.md 新增「前端出站同源边界与注销处置（t025）」节；profile_management.md 新增「会话动作隔离与应用阶段语义（t025）」节（Round 2 修复后同步实例证据口径）。
- blueprint：frontend.md 补三入口同源/动作隔离/apply 阶段语义；testing.md 补 t025 回归、夹具迁移与 t032 真实执行映射。
- spike：无正式 spike（未知契约清单为「无」），不适用。
