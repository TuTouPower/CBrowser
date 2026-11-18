# Task review t076（reviewer_focus: 测试）

- task：`t076_collection_queries_references_and_scale`
- spec：`docs/tasks/t076_collection_queries_references_and_scale/task.md`
- diff_anchor：`0445346773ab1c1152be2cbcfd4357395dc31b20`
- target：`git diff 0445346773ab1c1152be2cbcfd4357395dc31b20`
- round：1
- reviewed_at：2026-11-18T02:57:25+08:00

reviewed_scope: 76c92b68bd25644a

## Findings

### t076_test_f001 - created 排序断言恒真，未真正钉住创建时间顺序

- 严重度：minor
- 锚点：AC-001（排序稳定）
- 位置：`tests/unit/test_t076_collection_queries.py:286`，`test_profiles_collection_page_sorts`
- 问题：`assert by_created.items[0].config.name in ("a-name", "b-name")` 在只有 2 条数据时恒真，`sort="created"` 的实际顺序从未被验证；同函数的 `sort="name"`（精确列表比对）与 `sort="recent"`（精确列表比对）是强的，只有 created 这一路是弱断言。
- 建议：给两条数据以可区分的创建时间（如先后创建、或直接写不同的 `created_at`），断言 `sort="created"` 返回的确切顺序；或在注释中说明 created 顺序不在本 task 约束内。

### t076_test_f002 - AC-006 候选断言寄生在 scheme 过滤测试内，函数名与内容不符

- 严重度：minor
- 锚点：AC-006（有界候选找到末项）
- 位置：`tests/unit/test_t076_collection_queries.py:302-330`，`test_proxies_collection_page_scheme_filter`（游离 docstring 在 `:318`）
- 问题：60 条候选里找 `cand-059`、limit 500 截断为 50 的断言写在 scheme 过滤测试函数体内，前置还有一句游离的 `"""AC-006: ..."""` 字符串（不是测试说明，只是无操作字符串字面量）。断言本身真实且通过，但候选覆盖与函数名无关：日后重构 scheme 测试时容易连带删掉 AC-006 的唯一后端覆盖，且从测试名看不出 AC-006 已覆盖。
- 建议：把 `:312-330` 的候选部分抽成独立测试（如 `test_proxy_candidates_find_last_item_bounded`），删掉游离 docstring。

### t076_test_f003 - AC-003 重连后快照一致缺少 hook 级端到端用例

- 严重度：minor
- 锚点：AC-003（重连恢复后页面保持正确）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:357`（围栏测试）与 `src/frontend/src/shared/api/sse.test.ts:79`（既有传输层重连测试，未被本 diff 改动）
- 问题：AC-003 的新增行为（原地更新、版本/实例围栏、重复事件无副作用）都有新测试覆盖；但“断线重连后页面保持正确”这一肢只有分片证据：传输层重连带 `Last-Event-ID`（既有测试）、围栏拒绝迟到事件（新测试），没有一个用例驱动一次 SSE 断开→重连走过 `useProfileEventsSync`，断言摘要缓存最终一致且不触发完整列表重取。属于“还可以再加一个 case”，不阻断。
- 建议：补一个 hook 级用例：先断开 SSE 再重连并重放事件，断言摘要缓存与最新状态一致、`getRuntimeSummary` 不被多余调用。

## 结论

- 改测方向复核：三处改测均为 spec 驱动、有据可查，不属于迁就实现。（1）`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:228` 删除旧测试“invalidates the runtime query so an SSE event refetches authoritative state”，整替为原地更新且不重取的新测试——AC-003 明确要求“不触发无关完整列表重取”，旧断言与新契约直接冲突，删除处有注释说明理由；（2）`src/frontend/src/app/AppLayout.shell.test.tsx:184` 把 `getRuntime` 调用 2 次的期望改为 `getRuntimeSummary` 调用 1 次——AC-002 要求不再逐环境扇出 runtime 请求；（3）`tests/unit/test_api_models_and_sse.py` 期望字典补 `"config_version": 1`——该字段本身是本 task 交付的 SSE 围栏字段。除此之外无其他删除/反转断言。
- 本轮新发现：3 条，均为 minor，无 critical / important。
- 未进表的提示：无。
- 总体判断：测试本身无阻断问题，AC-001–AC-007 全部独立复验通过；唯一阻断项是 [deploy] AC-008 未勾选、待 Mac 补验（p126），按判定规则 verdict 为 FAIL。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。后端分页/搜索/排序/过滤测试真实触达仓储（120 条分页 3×50 无重复遗漏、page_size 5000 截断为 100、空搜索 total 0），集成测试复核 collection 端点截断；本人重跑后端 17/17 通过。
- AC-002：TICK-VALID，re_verified。EnvironmentListPage 测试断言 `getRuntime` 未调用、`getRuntimeSummary` 恰 1 次；EnvironmentSwitcher 关闭时只读当前环境、打开后摘要恰 1 次；AppLayout 横幅读摘要缓存；本人重跑前端受影响 6 文件 76/76 与全量 670/670 通过。
- AC-003：TICK-VALID，re_verified。SSE 原地更新不重取、旧版本/旧实例/重复事件三路围栏测试均直接跑生产同步逻辑；重连肢见 minor f003，仅缺 hook 级串联用例，分片证据完整。
- AC-004：TICK-VALID，re_verified。union 语义（current/bound/both、去重）、解绑后释放、计数一致均以真实仓储断言；集成测试复核 used-by 端点（含 404）。
- AC-005：TICK-VALID，re_verified。20 代理与 100 代理下 `list_proxies` SELECT 数相等且 ≤8；1000 规模矩阵（1000 代理/100 绑定运行行）SELECT 数 ≤8、1000 环境 10×100 分页无重复遗漏；本人重跑通过。
- AC-006：TICK-VALID，re_verified。60 候选找末项 `cand-059`、limit 截断 50、国家→城市范围按稳定代码、集成 candidates/countries 端点均真实断言；仅测试组织问题见 minor f002。
- AC-007：TICK-VALID，re_verified。1000 规模矩阵覆盖分页/搜索/候选无截断；0/1 规模由空搜索（total 0）与单项 union 用例覆盖；本人重跑通过。
- AC-008：TICK-VOID，trust_prior。task.md 中未勾选；p126（`docs/pending/p126_t076_ac008_real_runtime_chain_verification.md`，状态 todo）已登记待 Mac 补验，云端无 Docker/Chrome/真实运行实例无法验证。

coverage = 7 / 8

verdict: FAIL

## Round 2 (2026-11-18T05:18:54+08:00)

- task：`t076_collection_queries_references_and_scale`
- spec：`docs/tasks/t076_collection_queries_references_and_scale/task.md`
- diff_anchor：`0445346773ab1c1152be2cbcfd4357395dc31b20`
- target：`git diff 0445346773ab1c1152be2cbcfd4357395dc31b20`
- round：2
- reviewed_at：2026-11-18T05:18:54+08:00

reviewed_scope: d2c4842386bbbb51

## Findings

本轮无新 finding（0 条）。

## 结论

- 前轮 finding 复核（Round 1 测试轴 3 条，全部已消除，以 diff 与单跑为准，不采信处置表自称）：
    - t076_test_f001（minor，created 排序恒真）：已消除。`tests/unit/test_t076_collection_queries.py:276-310` 的 `test_profiles_collection_page_sorts` 现给两行可区分的 `created_at`（a-name 行 `2026-11-02T00:00:00+00:00`、b-name 行 `2026-11-01T00:00:00+00:00`），断言 `sort="created"` 的确切顺序 `["a-name", "b-name"]`；生产侧 `src/backend/cbrowser/adapters/database/repository.py:491-493` 确认 `sort="created"` 按 `created_at.desc()`，即后建先出，与断言一致。本人单跑该文件通过（见下）。
    - t076_test_f002（minor，AC-006 候选断言寄生）：已消除。候选断言已抽成独立测试 `tests/unit/test_t076_collection_queries.py:333-348` `test_proxy_candidates_find_last_item_bounded`（60 条候选找 `cand-059`、limit 500 截断为 50）；`test_proxies_collection_page_scheme_filter`（`:314-330`）现只剩 scheme 过滤断言，游离 docstring 已删。
    - t076_test_f003（minor，缺 hook 级断线重连用例）：已消除。`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:521-596` 新增 `recovers the summary across an SSE disconnect and reconnect without refetching`：卸载/重挂真实 `useProfileEventsSync` hook（走 `useEffect` 订阅/取消订阅，`mockSseClient.onEvent` 只 mock 传输边界），重连后重放状态事件，断言摘要缓存最终一致（`observed_state: running`、`runtime_instance_id: inst-9`、`running_count: 1`）且重放事件后 `getRuntimeSummary` 调用次数不再增加。本人单跑该文件 13/13 通过。
- 改测方向复核：本轮无新增改测。diff 内删除的测试仍只有 Round 1 已复核的两处（`useProfilesQuery.test.tsx` 的 SSE 后重取旧用例整替为原地更新断言；`AppLayout.shell.test.tsx` 的逐环境 `getRuntime` 2 次改为摘要 1 次），均为 AC-002/AC-003 新契约直接废止旧语义，合规；无「迁就实现」的改测。新增的 50ms settle 等待（`useProfilesQuery.test.tsx` 旧用例替换处，`setTimeout(resolve, 50)` 后断言 `runtimeCallCount` 不变）是否定性断言的短窗口，不是超时放大掩盖失败。
- 本轮新发现：0 条。
- 危险模式复扫：对 diff 内 9 个测试文件做模式扫描，无 `.only` / `.skip` / 恒真断言 / 注释掉的断言 / mock 被测逻辑；`toContain` 命中均为渲染文本/类名/分页号的子串断言，且均与精确断言（`toHaveLength(50)`、`toMatchObject({page: 1, page_size: 50})`、`toHaveBeenCalledTimes(1)`、`not.toHaveBeenCalled()`）并列，不是弱化。`test_api_models_and_sse.py` 仅补 `"config_version": 1` 期望字段（本 task 交付的围栏字段），无断言弱化。
- 未进表的提示：新重连用例名 `without refetching` 用词略松——重挂时确有 1 次 `getRuntimeSummary` 调用（重连快照，契约要求“冷启动与重连取一致快照”）；用例注释已写明“重放事件后不再多调”，断言本身正确，仅用例名可日后改为 `without an extra refetch after replay`。不进 finding。
- 总体判断：三条前轮 finding 均真实落地，AC-001–AC-007 测试证据完整且本人独立重跑通过；唯一阻断项仍是 [deploy] AC-008 未勾选、待 Mac 补验（p126，状态 todo），按判定规则 verdict 为 FAIL。
- 系统性 follow-up：无。
- 本轮独立重跑实数：后端 `tests/unit/test_t076_collection_queries.py` + `tests/integration/test_t076_collection_api.py` 22/22 通过（gate venv pytest，9.25s）；前端 `useProfilesQuery.test.tsx` 13/13 通过；其余 5 个受影响前端测试文件（EnvironmentListPage / ProxyListPage / EnvironmentSwitcher / SessionEntryPage / AppLayout.shell）67/67 通过。未重跑全量门禁（耗时，沿用返修 evidence4 结论）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。后端分页/搜索/排序/过滤测试真实触达仓储（120 条分页 3×50 无重复遗漏、page_size 5000 截断为 100、空搜索 total 0）；f001 修复后 created 排序断言为确切顺序；本人重跑后端 22/22 通过。
- AC-002：TICK-VALID，re_verified。EnvironmentListPage 测试断言 `getRuntime` 未调用、`getRuntimeSummary` 恰 1 次；EnvironmentSwitcher 关闭时只读当前环境、打开后摘要恰 1 次；AppLayout 横幅读摘要缓存；本人重跑相关前端 80/80 通过。
- AC-003：TICK-VALID，re_verified。SSE 原地更新不重取、旧版本/旧实例/重复事件三路围栏测试均直接跑生产同步逻辑；f003 修复后新增 hook 级断线重连用例（卸载/重挂 + 重放事件，摘要最终一致且不额外重取）；本人重跑 13/13 通过。
- AC-004：TICK-VALID，re_verified。union 语义（current/bound/both、去重）、解绑后释放、计数一致均以真实仓储断言；集成测试复核 used-by 端点（含 404）；本人重跑通过。
- AC-005：TICK-VALID，re_verified。20 代理与 100 代理下 `list_proxies` SELECT 数相等且 ≤8；1000 规模矩阵（1000 代理/100 绑定运行行）SELECT 数 ≤8、1000 环境 10×100 分页无重复遗漏；本人重跑通过。
- AC-006：TICK-VALID，re_verified。60 候选找末项 `cand-059`、limit 截断 50、国家→城市范围按稳定代码、集成 candidates/countries 端点均真实断言；f002 修复后候选断言为独立测试；本人重跑通过。
- AC-007：TICK-VALID，re_verified。1000 规模矩阵覆盖分页/搜索/候选无截断；0/1 规模由空搜索（total 0）与单项 union 用例覆盖；本人重跑通过。
- AC-008：TICK-VOID，trust_prior。task.md 中未勾选；p126（`docs/pending/p126_t076_ac008_real_runtime_chain_verification.md`，状态 todo）已登记待 Mac 补验，云端无 Docker/Chrome/真实运行实例无法验证。

coverage = 7 / 8

verdict: FAIL

## Round 3 (2026-11-18T06:26:04+08:00)

- task：`t076_collection_queries_references_and_scale`
- spec：`docs/tasks/t076_collection_queries_references_and_scale/task.md`
- diff_anchor：`0445346773ab1c1152be2cbcfd4357395dc31b20`
- target：`git diff 0445346773ab1c1152be2cbcfd4357395dc31b20`
- round：3
- reviewed_at：2026-11-18T06:26:04+08:00

reviewed_scope: 4945cf0e4ab78b2b

## Findings

### t076_test_f010 - 无版本 SSE 事件的围栏分支无测试覆盖

- 严重度：minor
- 锚点：AC-003（版本/实例围栏）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:637`（生产分支），测试缺口见 `src/frontend/src/features/profiles/useProfilesQuery.test.tsx` 全文 9 处 `sseCallback?.({...})` 调用
- 问题：生产围栏 `event.config_version ?? cached.config_version` 明确把无版本事件当作当前版本放行（注释“Events without a version predate the fence”），且生成类型 `ProfileRuntimeStatusEvent.config_version` 为可选（`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts:2011`，`config_version?: number | null`），即无版本事件是类型合法输入；但测试文件 9 处事件发送全部带 `config_version`，无一例发送缺失该字段的事件，该分支从未被执行。AC-003 只要求旧版本/旧实例/重复事件，不含无版本事件，故不阻断。
- 建议：补一个用例：两份缓存均有版本时发送无 `config_version` 的状态变化事件，断言两份缓存按“视为当前”正常更新（或按契约应拒绝时断言拒绝）。

### t076_test_f011 - 入口页逐页走访缺少“总数恰为页大小整数倍”的边界用例

- 严重度：minor
- 锚点：AC-001（分页无重复遗漏）、AC-007（无数据截断或遗漏）
- 位置：`src/frontend/src/features/browser-session/SessionEntryPage.test.tsx`（f008 用例“lists every running environment when the running bucket exceeds one page”）；生产循环见 `src/frontend/src/features/profiles/useProfilesQuery.ts:131-136`
- 问题：新用例覆盖总数 105（100+5 部分末页）与空页（总数 0 时走空状态用例）两端，但未覆盖总数恰为 100（`page * page_size >= total` 在第一页即成立、应恰好只发 1 次请求）的边界；用例也只断言调用次数 `>= 2` 而非恰好 2 次。生产循环的终止条件写错为 `>` 时会在总数 100 下多发一次空页请求——该多余请求返回空页即停，不产生错数据、不死循环，仅多一次请求，故属“还可以再加一个 case”，不阻断。
- 建议：补一个总数恰为 100 的用例，断言 `listCollection` 恰好调用 1 次且 100 行全部出现；或把现有用例的调用次数断言收紧为恰好 2 次。

## 结论

- 前轮 finding 复核（以 diff 与本人单跑为准，不采信处置表自称）：
    - Round 1 测试轴 3 条 minor，仍已消除：f001（created 排序确切顺序）仍在 `tests/unit/test_t076_collection_queries.py:276-310`；f002（候选独立测试）仍在 `tests/unit/test_t076_collection_queries.py:364` `test_proxy_candidates_find_last_item_bounded`；f003（hook 级断线重连用例）仍在 `src/frontend/src/features/profiles/useProfilesQuery.test.tsx:525`。三者均未被本轮返修改动。
    - Round 2 代码轴 f008/f009 的新增测试均真实落地，逐项核对如下：
        - f008：仓储 `tests/unit/test_t076_collection_queries.py:276-305`（running 桶 total 2、running_exact total 1 且仅含 run-one）与 HTTP 层 `tests/integration/test_t076_collection_api.py:132-168`（running_exact total 1、running 桶 total 2）均直接跑生产仓储/真实 TestClient，断言精确；入口页 `SessionEntryPage.test.tsx`（105 running + 10 starting，桶 115 行）断言 105 条链接、末行 `p-run-104` 出现、无 `start-0`、调用均带 `status=running_exact` 且含 page 2。桩忠实模拟服务端契约：`running_exact` 仅匹配 observed running、`running` 桶为 running+starting（与 `repository.py:457-461` 的桶定义逐字一致）、按 page/page_size 切片并返回过滤后总数；桩只 mock `ApiClient` 边界（系统边界），被测的 `useAllProfilesCollectionQuery` 逐页循环与 `SessionEntryPage` 过滤均为生产代码。空页路径由总数 0 的空状态用例覆盖；总数边界缺口见 minor f011。
        - f009：两用例（`useProfilesQuery.test.tsx:740` runtime v1/summary v2；`:813` runtime v2/summary v1）均渲染真实 `useProfileEventsSync` hook、真实 QueryClient，两份缓存用 `setQueryData` 预置，事件经捕获的 `sseCallback` 送入（仅 mock 传输边界 `onEvent`/`start`/`close`）；断言精确到每份缓存的 observed_state、config_version、instance_id、running_count 与 last_stopped_at，且双向各断言“动的一侧动了、不动的一侧分毫未变”。两份缓存均无的边界已有旧用例覆盖（`:274` “does not fabricate runtime state”，无缓存时不合成、不崩溃）；无版本事件分支缺口见 minor f010。
        - 先红后绿：磁盘上无 f008/f009 的红灯运行记录（evidence5 只有修后绿灯门禁日志），无法直接查证红灯；但逻辑上两组新断言对修前代码均敏感——修前单共享围栏会把迟到 v1 事件同时写进两份缓存（f009 用例的摘要会倒退为 stopped，断言失败），修前入口页只读桶第一页（f008 用例只能看到 90 running 行且含 starting 行，105 条与无 starting 断言均失败）。记为过程观察，不进 finding。
- 改测方向复核：本轮无新增改测。diff 内删除的测试仍只有 Round 1 已复核的两处（`useProfilesQuery.test.tsx` 的 SSE 后重取旧用例整替为原地更新断言；`AppLayout.shell.test.tsx` 的逐环境 `getRuntime` 2 次改为摘要 1 次），均为 AC-002/AC-003 新契约直接废止旧语义，合规；无「迁就实现」的改测。
- 本轮新发现：2 条，均为 minor，无 critical / important。
- 危险模式复扫：对 diff 内 9 个测试文件（后端 3 个、前端 6 个）做模式扫描，无 `.only` / `.skip` / 恒真断言 / 注释掉的断言 / mock 被测逻辑 / `eslint-disable` / `ts-ignore` / `.value =` 替代交互；`SessionEntryPage.test.tsx` 的 `expect(...some(...)).toBe(true)` 与 `expect(...every(...)).toBe(true)` 均是对真实计算结果的布尔断言，且与精确断言（105 条链接、`p-run-104` 出现、`start-0` 缺席）并列，不是恒真。删除/反转断言检查：diff 内 `-` 行的 expect 只有上述两处已复核项。
- 未进表的提示：Round 2 结论提到的重连用例名 `without refetching` 用词略松（重挂时确有 1 次重连快照调用）仍在，未改名，不影响断言正确性。f008/f009 红灯无运行记录，见上。
- 总体判断：本轮返修的 4 个新增测试（后端 2、前 2）全部真实落地且断言有效，AC-001–AC-007 测试证据完整，本人独立重跑通过；唯一阻断项仍是 [deploy] AC-008 未勾选、待 Mac 补验（p126，状态 todo），按判定规则 verdict 为 FAIL。
- 系统性 follow-up：无。
- 本轮独立重跑实数：后端 gate venv pytest，`tests/unit/test_t076_collection_queries.py` + `tests/integration/test_t076_collection_api.py` 24/24 通过（Round 2 的 22/22 + 新增 f008 两用例，10.90s）；前端 Node 26.13.0（`~/workspace/tools/node-26.13.0/bin` 置顶），`useProfilesQuery.test.tsx` 15/15 + `SessionEntryPage.test.tsx` 3/3，共 18/18 通过（Round 2 的 13+2，新增 f009 两用例与 f008 一用例）。未重跑全量门禁（耗时）；返修 evidence5 门禁日志复核：contract 388 通过/1 跳过、unit 2210 通过/1 跳过/4 失败/10 错误（t063/t068 老基线，日志尾行实数一致）、integration 210 通过/7 跳过/0 错误、frontend 677 通过/0 失败，与 progress.md 声称一致。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。后端分页/搜索/排序/过滤测试真实触达仓储（120 条分页 3×50 无重复遗漏、page_size 5000 截断为 100、空搜索 total 0、created 确切顺序）；f008 新增 running_exact 仓储与 HTTP 测试；本人重跑后端 24/24 通过。
- AC-002：TICK-VALID，re_verified。EnvironmentListPage 测试断言 `getRuntime` 未调用、`getRuntimeSummary` 恰 1 次；EnvironmentSwitcher 关闭时只读当前环境、打开后摘要恰 1 次；AppLayout 横幅读摘要缓存；入口页改读 running_exact 集合页 + 批量摘要。
- AC-003：TICK-VALID，re_verified。SSE 原地更新不重取、旧版本/旧实例/重复事件三路围栏、hook 级断线重连用例均直接跑生产同步逻辑；f009 混合版本双向用例新增后本人重跑 15/15 通过；仅缺无版本事件用例，见 minor f010。
- AC-004：TICK-VALID，re_verified。union 语义（current/bound/both、去重）、解绑后释放、计数一致均以真实仓储断言；集成测试复核 used-by 端点（含 404）；本人重跑通过。
- AC-005：TICK-VALID，re_verified。20 代理与 100 代理下 `list_proxies` SELECT 数相等且 ≤8；1000 规模矩阵（1000 代理/100 绑定运行行）SELECT 数 ≤8、1000 环境 10×100 分页无重复遗漏；本人重跑通过。
- AC-006：TICK-VALID，re_verified。60 候选找末项 `cand-059`、limit 截断 50、国家→城市范围按稳定代码、集成 candidates/countries 端点均真实断言；候选断言为独立测试；本人重跑通过。
- AC-007：TICK-VALID，re_verified。1000 规模矩阵覆盖分页/搜索/候选无截断；0/1 规模由空搜索（total 0）与单项 union 用例覆盖；入口页 105 行逐页走访无截断；本人重跑通过。
- AC-008：TICK-VOID，trust_prior。task.md 中未勾选；p126（`docs/pending/p126_t076_ac008_real_runtime_chain_verification.md`，状态 todo）已登记待 Mac 补验，云端无 Docker/Chrome/真实运行实例无法验证。

coverage = 7 / 8

verdict: FAIL

## Round 4 (2026-11-18T07:00:12+08:00)

- task：`t076_collection_queries_references_and_scale`
- spec：`docs/tasks/t076_collection_queries_references_and_scale/task.md`
- diff_anchor：`0445346773ab1c1152be2cbcfd4357395dc31b20`
- target：`git diff 0445346773ab1c1152be2cbcfd4357395dc31b20`
- round：4
- reviewed_at：2026-11-18T07:00:12+08:00

reviewed_scope: 3c6834b56be76d09

## Findings

本轮无新 finding（0 条）。

## 结论

- 前轮 finding 复核（以 diff、代码与本人单跑/变异验证为准，不采信处置表自称）：
    - t076_test_f010（minor，无版本 SSE 事件围栏分支无测试）：已消除。`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:898` 新增 `treats a version-less SSE event as current for both caches`：两份缓存均预置 config_version 2 / inst-2 / running，发送无 `config_version` 的 stopped 事件，断言两份缓存均更新为 stopped、config_version 保持 2、running_count 归 0。用例真实跑生产逻辑：渲染真实 `useProfileEventsSync` hook 与真实 QueryClient，仅 mock SSE 传输边界（`sseCallback` 捕获）；断言同时钉住围栏 `??` 分支（`useProfilesQuery.ts:637`）与合并 `??` 分支（`:664`）。
    - f010 的 d.ts 引用纠正属实，本人独立核对：`cbrowser_v1.d.ts:1627` 的 `config_version: number;`（必填）位于 `ProfileRuntimeStatusEvent`（约 :1607 起）内；Round 3 finding 所引 `:2011` 的 `config_version?: number | null;`（可选）位于 `SessionResponse`（:1965 起）内，与 SSE 事件无关。Round 3 的“生成类型里该字段为可选”说法有误，予以纠正；该错误不影响 f010 本身成立（分支确实无测试），只影响引用。
    - f010 的 `as ProfileRuntimeEvent` 构造合法，非 mock 被测逻辑：`ProfileRuntimeEvent` 即 `ProfileRuntimeStatusEvent`（`src/frontend/src/shared/api/sse.ts:8`）；线上传输解析 `parseProfileRuntimeEvent`（`sse.ts:171-187`）只校验核心字段（`hasValidCoreFields`，`sse.ts:143-160`：profile_id / desired_state / observed_state / failure_count / restart_blocked / updated_at，不含 config_version），可选字段仅在出现时才校验类型，末尾 `return raw as ProfileRuntimeEvent`——无版本事件是真实可达输入，测试里的 cast 只复现该线形，不绕过围栏/合并逻辑。用例注释已写明此依据。
    - t076_test_f011（minor，入口页缺“总数恰为页大小整数倍”边界用例）：已消除。`src/frontend/src/features/browser-session/SessionEntryPage.test.tsx:310` 新增 `lists every running environment when the total is exactly one page`：100 running、0 starting，断言 `listCollection` 恰好调用 1 次、100 行全部出现（含末行 `/session/p-run-099`）、每次调用均带 `status=running_exact`。现有 f008 用例（`:261`）调用次数断言由 `>= 2` 收紧为 `expect(calls.length).toBe(2)`（`:288`），是加强而非弱化。桩忠实模拟服务端契约：`running_exact` 仅匹配 observed running、按 page/page_size 切片并返回过滤后总数；被测的 `useAllProfilesCollectionQuery` 逐页循环（`useProfilesQuery.ts:111-141`，终止条件 `page * chunk.page_size >= chunk.total`，`:133`）与 `SessionEntryPage` 均为生产代码，桩只 mock `ApiClient` 边界。
    - 变异红灯验证（本人亲手复做，返修方自称的红灯无磁盘记录，本轮以实测为准）：f010 把围栏 `:637` 的 `?? cached.config_version` 改为 `?? 0` 后，新用例失败、其余 15 通过（16 tests：1 failed / 15 passed）；f011 把终止条件 `:133` 的 `>=` 改为 `>` 后，新用例失败、其余 3 通过（4 tests：1 failed / 3 passed）。两次变异后生产代码均已还原，还原后复核见下。附注：`>` 变异下 f008 用例仍通过（总数 105 时第 2 页 `200 > 105` 仍成立、调用次数仍为 2），即 f011 新用例是 `>=`/`>` 区分的唯一守卫——这正是补该用例的价值，不是缺陷。
    - 前三轮测试 finding 抽查仍在（未被本轮返修改动）：f001（`tests/unit/test_t076_collection_queries.py:307` created 确切顺序）、f002（`:364` 候选独立测试）、f003（`useProfilesQuery.test.tsx:525` 断线重连用例）、f008（`SessionEntryPage.test.tsx:261`）、f009（`useProfilesQuery.test.tsx:740` 与 `:813` 混合版本双向用例）。本轮返修只加测试、生产代码零改动：与 Round 3 记录的生产关键行一致（围栏 `:637`、合并 `:664`、分页终止 `:133`）。
- 改测方向复核：本轮无新增改测。唯一改动既有断言处是 f008 的 `>= 2` 收紧为恰好 2 次，属于加强断言，不是迁就实现。diff 内删除的测试仍只有 Round 1 已复核的两处（SSE 后重取旧用例整替；`AppLayout.shell.test.tsx` 逐环境 `getRuntime` 2 次改为摘要 1 次），均为 AC-002/AC-003 新契约直接废止旧语义，合规。
- 本轮新发现：0 条。
- 危险模式复扫：对本轮改动的两个测试文件做模式扫描，无 `.only` / `.skip` / 恒真断言 / 注释掉的断言 / mock 被测逻辑 / `eslint-disable` / `ts-ignore` / `.value =` 替代交互；f011 的 `expect(links.some(...)).toBe(true)` 与 f008 同款，是对真实渲染结果的布尔断言，且与精确断言（100 行、`p-run-099` 出现、调用恰 1 次）并列，不是恒真；f010 的 `as ProfileRuntimeEvent` 已如上核实为线形模拟。
- 未进表的提示：无。
- 总体判断：f010/f011 两条前轮 finding 均真实落地且断言经变异验证有效，AC-001–AC-007 测试证据完整，本人独立重跑通过；唯一阻断项仍是 [deploy] AC-008 未勾选、待 Mac 补验（p126，状态 todo），按判定规则 verdict 为 FAIL。
- 系统性 follow-up：无。
- 本轮独立重跑实数：前端 Node 26.13.0（`~/workspace/tools/node-26.13.0/bin` 置顶），`useProfilesQuery.test.tsx` 16/16 + `SessionEntryPage.test.tsx` 4/4，共 20/20 通过；后端 gate venv pytest，`tests/unit/test_t076_collection_queries.py` + `tests/integration/test_t076_collection_api.py` 24/24 通过（55.46s）；`npm run test:types`（tsc）通过。未重跑全量门禁（本轮零生产改动，沿用 evidence5 结论）。
- 审阅过程说明（审阅者本人操作失误，已恢复并验证，非任务交付问题，不进 finding 表）：本轮变异验证中，我第一次还原 f010 变异时误用 `git checkout -- src/frontend/src/features/profiles/useProfilesQuery.ts`，该命令把未提交的 t076 实现整文件恢复到了基线（664 行、t076 标记 0 处），随后一次 `SessionEntryPage.test.tsx` 4/4 失败即为该误操作所致，该次运行结果作废、不是任务证据。我随即从 `/tmp/useProfilesQuery.ts.bak`（与 `.bak2` 同 md5 `c92af5d4cd5a5119de2be3db7856a27f`，1073 行，含全部 t076 标记）恢复该文件；恢复验证：`git diff 0445346 -- <该文件>` 恰为本轮开始时记录的 478 insertions / 69 deletions，工作区全量 diff 回到 45 files / 9665 insertions / 1816 deletions（与本轮开始时一致），其后前端 20/20、后端 24/24 重新全绿。第二次变异还原改用 cp 该备份文件，不再对未提交文件使用 `git checkout`。除该文件外无其他文件被触碰。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。后端分页/搜索/排序/过滤测试真实触达仓储（120 条分页 3×50 无重复遗漏、page_size 5000 截断为 100、空搜索 total 0、created 确切顺序）；f008/f011 入口页逐页走访覆盖 105 与恰 100 两边界；本人重跑后端 24/24 与前端 20/20 通过。
- AC-002：TICK-VALID，re_verified。EnvironmentListPage 测试断言 `getRuntime` 未调用、`getRuntimeSummary` 恰 1 次；EnvironmentSwitcher 关闭时只读当前环境、打开后摘要恰 1 次；AppLayout 横幅读摘要缓存；入口页改读 running_exact 集合页 + 批量摘要。
- AC-003：TICK-VALID，re_verified。SSE 原地更新不重取、旧版本/旧实例/重复事件三路围栏、hook 级断线重连用例均直接跑生产同步逻辑；f009 混合版本双向用例与 f010 无版本事件用例新增后本人重跑 16/16 通过，两处变异红灯均由本人亲手复现。
- AC-004：TICK-VALID，re_verified。union 语义（current/bound/both、去重）、解绑后释放、计数一致均以真实仓储断言；集成测试复核 used-by 端点（含 404）；本人重跑通过。
- AC-005：TICK-VALID，re_verified。20 代理与 100 代理下 `list_proxies` SELECT 数相等且 ≤8；1000 规模矩阵（1000 代理/100 绑定运行行）SELECT 数 ≤8、1000 环境 10×100 分页无重复遗漏；本人重跑通过。
- AC-006：TICK-VALID，re_verified。60 候选找末项 `cand-059`、limit 截断 50、国家→城市范围按稳定代码、集成 candidates/countries 端点均真实断言；候选断言为独立测试；本人重跑通过。
- AC-007：TICK-VALID，re_verified。1000 规模矩阵覆盖分页/搜索/候选无截断；0/1 规模由空搜索（total 0）与单项 union 用例覆盖；入口页 105 行与恰 100 行逐页走访无截断；本人重跑通过。
- AC-008：TICK-VOID，trust_prior。task.md 中未勾选；p126（`docs/pending/p126_t076_ac008_real_runtime_chain_verification.md`，状态 todo）已登记待 Mac 补验，云端无 Docker/Chrome/真实运行实例无法验证。

coverage = 7 / 8

verdict: FAIL

## Round 6 (2026-11-18T07:34:04+08:00)

- task：`t076_collection_queries_references_and_scale`
- spec：`docs/tasks/t076_collection_queries_references_and_scale/task.md`
- diff_anchor：`0445346773ab1c1152be2cbcfd4357395dc31b20`
- target：`git diff 0445346773ab1c1152be2cbcfd4357395dc31b20`
- round：6
- reviewed_at：2026-11-18T07:34:04+08:00

reviewed_scope: 69ad025aed11463c

## Findings

本轮无新 finding（0 条）。

## 结论

- 本轮变更范围核实（测试轴上一轮为 Round 4；Round 5 仅代码轴就 AC-008 打勾处置出报告，测试轴无单独轮次）：相对 Round 4，生产代码与测试代码零改动——`src/backend/cbrowser/adapters/database/repository.py` 仍为 2614 行、`src/frontend/src/features/profiles/useProfilesQuery.ts` 仍为 1073 行且 md5 为 `c92af5d4cd5a5119de2be3db7856a27f`、相对锚点的 numstat 仍为 478 insertions / 69 deletions，与 Round 4 报告记录逐项一致；`git diff` 文件清单仍为 45 文件、`git status --short` 共 47 项（含两份未跟踪 review 报告）。本轮唯一实质变化是契约区新增「[deploy] AC 打勾处置注记（契约修订，2026-11-18）」，指纹因此变为本轮值。
- 契约 drift 核对（按 prompt 要求）：`git diff` 显示 AC-001–AC-007 正文一字未改、仅勾选状态由未勾变为已勾，属前轮 FAIL 后按流程撤回、修复重验后的重新打勾，Round 1–4 已逐条复核、本轮重跑测试再次通过，不记 finding。AC-008 正文原句一字未改，仅在其后追加云端不可验与用户裁定的括注，并新增处置注记小节；该修订有用户 2026-11-18 明确裁定为据（注记引文与 `progress.md`「AC-008 处置」条互相印证、要点一致），且注记明文只变更打勾的流程语义与验证时点、不豁免验证本身，不是未经确认的擅自变更，不按 blocking finding 处理。未知契约清单无 `UNVERIFIED-BLOCKING`、`UNVERIFIED-SPIKE` 或裸 `UNVERIFIED` 标记（命中的一处仅为该小节的规范说明文字本身）。
- AC-008 TICK 判定（测试轴，按修订后契约）：处置注记规定 Review Agent 对此类 AC 以注记为准——云端可做部分已完成且补验 pending 已登记者，判 TICK-VALID（处置型）。两项前提当场核实成立：(1) 云端可做部分已完成——支撑 AC-008 的 API/SSE/引用一致性测试证据即 AC-001–AC-007 的交付，本轮后端 24 测试与前端 85 测试当场重跑全部通过（见独立复验），无一处以 mock、skip 或历史结果冒充真实链路验证；(2) 补验 pending 已登记——`docs/pending/p126_t076_ac008_real_runtime_chain_verification.md` 存在、status 为 todo、正文内容与 AC-008 验证要求一致且明文不得用 mock、skip 或历史结果代替。故本轮 AC-008 改判 TICK-VALID（处置型，trust_prior：真实 Docker/Chrome/Browser 链路验证本身仍未发生，待 p126 在 Mac 补验留证后由本地复核闭环；本判定不表示已实测通过）。
- 前轮 finding 复核（以 diff、代码与本人单跑为准，不采信处置表自称）：
    - t076_test_f001（minor，created 排序恒真）：仍已消除。`tests/unit/test_t076_collection_queries.py:307-330` 的 `test_profiles_collection_page_sorts` 给两行可区分的 `created_at`，断言 `sort="created"` 的确切顺序 `["a-name", "b-name"]`；本人重跑该文件通过。
    - t076_test_f002（minor，AC-006 候选断言寄生）：仍已消除。候选断言为独立测试 `tests/unit/test_t076_collection_queries.py:364` `test_proxy_candidates_find_last_item_bounded`；本人重跑通过。
    - t076_test_f003（minor，缺 hook 级断线重连用例）：仍已消除。`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:525` 的断线重连用例仍在，随 16 用例集本人重跑通过。
    - t076_test_f010（minor，无版本 SSE 事件围栏分支无测试）：仍已消除。`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:898` 的无版本事件用例仍在，生产围栏 `src/frontend/src/features/profiles/useProfilesQuery.ts:637` 的 `?? cached.config_version` 分支未变；本人重跑通过。
    - t076_test_f011（minor，入口页缺“总数恰为页大小整数倍”边界用例）：仍已消除。`src/frontend/src/features/browser-session/SessionEntryPage.test.tsx:310` 的精确整页用例仍在、f008 用例调用次数断言仍为恰好 2 次；本人重跑 4/4 通过。
    - 代码轴 f008/f009 的回归测试（入口页 105 running 逐页走访、混合版本双向围栏）随本轮前端重跑一并通过，测试证据未回退。
- 改测方向复核：本轮无新增改测（测试代码零改动）。diff 内删除的 expect 仍只有 Round 1 已复核的两处（`AppLayout.shell.test.tsx` 逐环境 `getRuntime` 2 次改为摘要 1 次；`useProfilesQuery.test.tsx` 的 SSE 后重取旧断言整替为原地更新断言），均为 AC-002/AC-003 新契约直接废止旧语义，合规；无「迁就实现」的改测。
- 本轮新发现：0 条。
- 危险模式复扫：对 diff 内全部 9 个测试文件（后端 3 个、前端 6 个）做模式扫描，无 `.only` / `.skip` / 恒真断言 / 注释掉的断言 / mock 被测逻辑 / `eslint-disable` / `ts-ignore` / `.value =` 替代交互；`toContain` 命中均为渲染文本的子串断言（`SessionEntryPage.test.tsx:231-232,249`），且与精确断言（链接条数、末行出现、调用次数）并列，不是弱化。`useProfilesQuery.test.tsx` 中 5 处 `if (sseCallback) { ... }` 经调查放行：回调在 hook 订阅时同步赋值，事件未送达时其后的缓存断言必然失败，不是「前置不满足仍 PASS」的条件跳过弱化，与前轮已接受的测试桩形态一致。阈值类：无 timeout/重试/容差放大新增；否定性断言的 50ms settle 等待沿用 Round 2 已复核结论。
- 未进表的提示：无。
- 总体判断：前轮测试 finding 全部消除且本轮无新缺陷，AC-001–AC-007 测试证据完整、本轮独立重跑通过；AC-008 按经用户裁定并已写入契约的处置注记改判 TICK-VALID（处置型），真实验证由 p126 跟踪、留待 Mac 补验闭环，不再阻断本轮结论。
- 系统性 follow-up：无（AC-008 补验已有 p126 跟踪，不重复立项）。
- 本轮独立重跑实数：落点仓库校验通过（以仓库为工作目录执行不带 `-C` 的 `git rev-parse --show-toplevel`，输出与要求一致）；后端 gate venv pytest，`tests/unit/test_t076_collection_queries.py` + `tests/integration/test_t076_collection_api.py` 24/24 通过（11.65s）；前端 Node 26.13.0 跑 `useProfilesQuery.test.tsx` 16/16 + `SessionEntryPage.test.tsx` 4/4 + `EnvironmentListPage.test.tsx` / `ProxyListPage.test.tsx` / `EnvironmentSwitcher.test.tsx` / `AppLayout.shell.test.tsx` 65/65，共 85/85 通过；`npm run test:types`（tsc）通过。未重跑全量门禁：本轮不改生产/测试代码，evidence5 全量门禁结论仍有效（沿用 Round 3–4 的说明）。
- 变异验证说明：本轮未做变异验证，只做只读核对与重跑。理由：被测生产文件与 Round 4 已由审阅者亲手完成两处变异红灯验证（f010 围栏 `?? 0`、f011 终止条件 `>`）的状态逐字节一致（行数、md5、numstat 三项均与 Round 4 记录相同），变异结论仍然成立，无需在未提交交付文件上重复冒险改动；本轮未修改、创建或删除任何生产/测试文件，无还原复核对象。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。后端分页/搜索/排序/过滤测试真实触达仓储（120 条分页 3×50 无重复遗漏、page_size 5000 截断为 100、空搜索 total 0、created 确切顺序）；入口页逐页走访覆盖 105 与恰 100 两边界；本人重跑后端 24/24 与前端 85/85 通过。
- AC-002：TICK-VALID，re_verified。EnvironmentListPage 测试断言 `getRuntime` 未调用、`getRuntimeSummary` 恰 1 次；EnvironmentSwitcher 关闭时只读当前环境、打开后摘要恰 1 次；AppLayout 横幅读摘要缓存；本人重跑相关前端文件通过。
- AC-003：TICK-VALID，re_verified。SSE 原地更新不重取、旧版本/旧实例/重复事件三路围栏、混合版本双向围栏、无版本事件、hook 级断线重连用例均直接跑生产同步逻辑；本人重跑 `useProfilesQuery.test.tsx` 16/16 通过。
- AC-004：TICK-VALID，re_verified。union 语义（current/bound/both、去重）、解绑后释放、计数一致均以真实仓储断言；集成测试复核 used-by 端点（含 404）；本人重跑通过。
- AC-005：TICK-VALID，re_verified。20 代理与 100 代理下 `list_proxies` SELECT 数相等且 ≤8（断言见 `tests/unit/test_t076_collection_queries.py:73-116`）；1000 规模矩阵 SELECT 数 ≤8、1000 环境分页无重复遗漏；本人重跑通过。
- AC-006：TICK-VALID，re_verified。60 候选找末项 `cand-059`、limit 截断 50、国家→城市范围按稳定代码、集成 candidates/countries 端点均真实断言；候选断言为独立测试；本人重跑通过。
- AC-007：TICK-VALID，re_verified。1000 规模矩阵覆盖分页/搜索/候选无截断；0/1 规模由空搜索（total 0）与单项 union 用例覆盖；入口页 105 行与恰 100 行逐页走访无截断；本人重跑通过。
- AC-008：TICK-VALID，trust_prior。处置型判定：按契约区处置注记，云端可做部分已完成（支撑测试随本轮后端 24 + 前端 85 测试重跑通过，且无 mock/skip/历史结果冒充）且补验 pending p126 已登记（status todo、正文与 AC-008 一致、明文不得以 mock/skip/历史结果代替）；真实链路验证待 Mac 补验留证后闭环，本判定非已实测通过。

coverage = 7 / 8

verdict: PASS
