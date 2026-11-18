# Task review t076（reviewer_focus: 代码）

- task：`t076_collection_queries_references_and_scale`
- spec：`docs/tasks/t076_collection_queries_references_and_scale/task.md`
- diff_anchor：`0445346773ab1c1152be2cbcfd4357395dc31b20`
- target：`git diff 0445346773ab1c1152be2cbcfd4357395dc31b20`
- round：1
- reviewed_at：2026-11-18T03:01:19+08:00

reviewed_scope: 76c92b68bd25644a

## Findings

### t076_code_f001 - SSE 增量事件在列表/入口页被整条丢弃，摘要缓存得不到更新

- 严重度：important
- 锚点：AC-003（运行状态增量后页面保持正确）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:470-473`，`src/frontend/src/features/profiles/useProfilesQuery.ts:539-575`
- 问题：`useProfileEventsSync` 处理 `runtime_state` 事件时，先读单环境运行缓存，缓存为空即直接 `return`（`if (!old) return;`），摘要缓存的原地更新代码写在这个 early return 之后。t076 把列表页、入口页的逐环境 `getRuntime` 全部改成了批量摘要（`src/frontend/src/features/profiles/EnvironmentListPage.tsx:108-115` 只调 `useRuntimeSummaryQuery`，不再挂载任何 `useProfileRuntimeQuery`；`src/frontend/src/features/browser-session/SessionEntryPage.tsx:14,23` 同样），所以刚打开列表/入口页时 `profileKeys.runtime(id)` 缓存是空的——SSE 增量事件（包括连接初期的服务端快照事件）全部被丢弃，行状态、运行总数只在下一次窗口聚焦/重挂载触发摘要重取时才纠正。也就是说 AC-003 宣称的“增量更新对应项”在本次 task 改造的主页面上实际不工作；只有用户此前访问过某环境详情页（该环境的运行缓存已被详情页填入）时，该环境的事件才能走到摘要更新。前端测试掩盖了这一点：`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:291,358` 在发事件前先 `setQueryData(profileKeys.runtime("p1"), …)` 预置缓存，从未覆盖“列表页缓存为空”的路径（同文件 :287 甚至把“无缓存保持无缓存”当作预期断言）。`docs/blueprint/architecture.md` §5.8 与 `docs/blueprint/frontend.md` §10 写“有效事件原地更新运行缓存与摘要缓存”，与代码实际行为不符。
- 建议：把摘要更新与单环境运行缓存解耦：事件先按 `config_version`/实例围栏与摘要条目比对（摘要条目自带 `config_version` 与 `runtime_instance_id`，围栏所需字段齐全），围栏通过即更新摘要；单环境运行缓存仅在其已存在时才同步更新，仍不从事件凭空合成运行条目。

### t076_code_f002 - SSE 同步到摘要时漏字段，启动时间与预览捕获时间长期滞后

- 严重度：important
- 锚点：AC-003（运行状态增量后页面保持正确）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:488-519`，`src/frontend/src/features/profiles/useProfilesQuery.ts:542-575`，`src/frontend/src/features/profiles/useProfilesQuery.ts:580-600`
- 问题：服务端事件携带 `last_started_at`/`last_stopped_at`（`src/backend/cbrowser/api/runtime_coordinator.py:899-900` 发布时填入，`src/frontend/src/shared/api/sse.ts:175-176` 校验通过），但前端拼 `next` 时只用 `...old` 透传旧值、未从事件复制这两个字段，`changed` 比较也不含它们——一次只改变时间的事件会被判为“无变化”直接丢弃；即使事件因状态变化被接受，摘要映射也只复制 `desired_state`/`observed_state`/`config_version`/`runtime_instance_id`/`last_coordinator_error`，`failure_count`、`restart_blocked` 仍滞后。列表行实际渲染这些滞后字段：`src/frontend/src/features/profiles/EnvironmentCard.tsx:128` 与 `src/frontend/src/features/profiles/EnvironmentTable.tsx:351` 渲染 `last_started_at`（“多久前启动”），`src/frontend/src/features/profiles/EnvironmentListPage.tsx:137` 取 `preview_captured_at`；而预览事件处理只写单环境运行缓存、从不碰摘要缓存。所以环境启动后，行状态变为运行中，但“启动于 X 前”仍显示上一次启动的时间，直到下次重取。
- 建议：`next` 从事件复制 `last_started_at`/`last_stopped_at`（事件缺失时保留旧值），`changed` 比较纳入这两个字段；摘要映射同步复制 `failure_count`、`restart_blocked`、`last_started_at`、`last_stopped_at`、`preview_captured_at`、`updated_at`；预览事件同样原地更新摘要条目（仍受“捕获时间不倒退”围栏约束）。

### t076_code_f003 - 集合查询的缓存键从未被失效，增删改后列表仍显示旧数据

- 严重度：important
- 锚点：AC-001、AC-007（列表读取正确、与服务端一致）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:36-40`，`src/frontend/src/features/profiles/useProfilesQuery.ts:605-613`，`src/frontend/src/features/profiles/useProfilesQuery.ts:727-829`
- 问题：集合查询用独立的键前缀（`profileKeys.collection` 为 `["profiles", "collection", params]`，`src/frontend/src/features/profiles/useProfilesQuery.ts:68`；proxies/groups 同理），但全部变更路径只失效旧的 `lists()` 键：环境/分组/代理的创建、更新、删除、测速、重排 mutation（`src/frontend/src/features/profiles/useProfilesQuery.ts:129-200,727-829`）与 SSE 引用变更事件处理（同文件 :605-613，只失效 `groupKeys.lists()`/`proxyKeys.lists()`/`profileKeys.lists()`）均未失效任何 `collection` 键。React Query 按前缀匹配，`["profiles", "list"]` 匹配不到 `["profiles", "collection", …]`。可复现场景：在代理列表页删除一个代理，mutation 成功、toast 正常，但被删行仍留在当前页；在环境列表页新建环境，新行不出现；直到窗口聚焦或切页重挂载才纠正。新建的 `useProfilesCollectionQuery`/`useProxiesCollectionQuery` 本身没有 `staleTime` 之外的自愈机制。
- 建议：所有现在失效 `profileKeys.lists()`/`proxyKeys.lists()`/`groupKeys.lists()` 的位置，同步失效对应的 `collection` 键（按前缀失效 `profileKeys.all`/`proxyKeys.all`/`groupKeys.all` 最彻底，或逐个失效 `collection` 前缀）；SSE 引用事件处理同理。

### t076_code_f004 - 国家→城市范围未过滤观测时效性，会给出选后无结果的死选项

- 严重度：minor
- 锚点：AC-006（国家→城市范围正确）
- 位置：`src/backend/cbrowser/adapters/database/repository.py:2017-2030`
- 问题：`proxy_country_ranges` 只按 `country_code IS NOT NULL` 全表取观测行，不做任何时效/状态过滤；而集合筛选用的 `_latest_observation_geo_subquery`（同文件 :1855-1892，尤其 :1885-1890）明确排除已过期的 `ok` 观测，`_visible_observation`（同文件 :1596-1613）还会按端点指纹/凭据修订号判定观测是否仍有效。两者口径不一致：某代理的观测过期后，国家仍出现在 `GET /proxies/countries` 的选项里，但用该国家筛选集合页返回 0 条（最新观测已不被采信）。前端国家选项唯一来源就是该接口（`src/frontend/src/features/proxies/ProxyListPage.tsx:140`）。
- 建议：`proxy_country_ranges` 与筛选侧用同一“最新且仍有效”口径聚合（复用 `_latest_observation_geo_subquery` 的有效行，或至少排除已过期 `ok` 行）。

### t076_code_f005 - `_proxy_used_by_current`/`_proxy_used_by_bound` 每次重跑整张引用映射

- 严重度：minor
- 锚点：AC-005（批量读取引用，消除逐代理/逐版本往返）
- 位置：`src/backend/cbrowser/adapters/database/repository.py:1756-1776`，`src/backend/cbrowser/adapters/database/repository.py:2186-2187`，`src/backend/cbrowser/adapters/database/repository.py:2308-2312`，`src/backend/cbrowser/adapters/database/repository.py:2406-2412`
- 问题：`_proxy_reference_map` 一次取 3 条 SELECT 的批量设计本身正确，但 `_proxy_used_by_current` 与 `_proxy_used_by_bound` 两个薄包装每次调用都重跑整张映射（全量当前引用、全量运行行、全量绑定版本）。`proxy_impact`（:2186-2187）一次调两者，`update_proxy` 的连接变更路径（:2308-2312）与重名回滚路径（:2406-2412）一次调三者（`_proxy_used_by` + current + bound_only），即单次代理更新触发 6–9 条全表扫描 SELECT。SELECT 条数仍有界、不随代理数乘绑定数增长，所以不违反 AC-005 的计数断言，但与本 task“一次聚合、多处复用”的目标相悖，规模越大单次写请求的重复扫描越重。
- 建议：在同一会话/同一请求内只算一次引用映射后传给各调用方（或让这三个 helper 接受已算好的映射）。

### t076_code_f006 - 列表页仍拉全量 proxies/groups，入口页仍拉全量 profiles

- 严重度：minor
- 锚点：AC-001、AC-002（删除先拉全量再拼装的旧路径）
- 位置：`src/frontend/src/features/profiles/EnvironmentListPage.tsx:108-115`，`src/frontend/src/features/browser-session/SessionEntryPage.tsx:14`
- 问题：环境列表页为给每行找分组名/代理名，仍调用全量 `useGroupsQuery` 与 `useProxiesQuery`（`GET /api/v1/groups`、`GET /api/v1/proxies`，无分页）；工作台入口页仍用全量 `useProfilesQuery`。逐环境 runtime 扇出确实已消除（AC-002 字面成立），但 1000 代理/1000 环境规模下这两个页面每次渲染仍下载整张代理表/分组表/环境表，与“所需引用信息随集合查询返回”的范围描述不符。
- 建议：行所需的分组名/代理名随集合页返回，或改用有界候选接口按需取；入口页改读集合页（分页或有界）。

### t076_code_f007 - LIKE 搜索词未转义 `%`/`_`，搜索词含通配符会多匹配

- 严重度：minor
- 锚点：AC-001（搜索针对完整数据集合、总数口径可解释）
- 位置：`src/backend/cbrowser/adapters/database/repository.py:415`，`src/backend/cbrowser/adapters/database/repository.py:1921`，`src/backend/cbrowser/adapters/database/repository.py:513`，`src/backend/cbrowser/adapters/database/repository.py:1335`
- 问题：搜索词直接拼进 `f"%{search}%"` 再走 `ilike`，`%` 与 `_` 仍是通配符。例：搜索 `100%` 会命中 `1000`、`100A` 等本不应命中的行；候选接口（:513、:1335）与分组页（:1303）同样。参数是绑定参数、无注入风险，只是匹配语义不精确。
- 建议：进 `ilike` 前转义 `%`、`_`、`\`（SQLAlchemy 侧用 `escape` 参数或自行转义后加 `ESCAPE`）。

## 结论

- 本轮新发现：7 条（important 3 条：t076_code_f001、t076_code_f002、t076_code_f003；minor 4 条：t076_code_f004、t076_code_f005、t076_code_f006、t076_code_f007）
- 未进表的提示：文件过大——`src/backend/cbrowser/adapters/database/repository.py` 现 2492 行（本 task 净增 528 行，已远超 800 行阈值）；`src/frontend/src/features/profiles/useProfilesQuery.ts` 现 832 行（本 task 从约 588 行增至 832 行，跨过 800 行阈值）。圈复杂度手算：`list_profiles_page` 约 13、`list_proxies_page` 约 10，均未达 15 的 minor 阈值，不进表。范围外观察：`profiles/groups` 的候选端点与 `groups/collection` 端点暂无前端消费，按 spec“供后续交互/呈现 task 使用”，不记 finding；候选接口路由允许 `limit` 至 500 而仓储钳制为 50，静默截断属于有界设计，不记 finding；`docs/specs/gate_verification.md` 的 diff 把两条列表项合并成一行（格式小瑕）；OpenAPI 生成物（`schemas/openapi/*`、`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts`）未逐行审，已由 contract 门禁覆盖。安全扫查：diff 内无外部输入直达执行/拼接、无新增凭据落盘或日志、无鉴权/CORS 变更，搜索参数均为绑定参数。
- 总体判断：集合页、批量摘要、引用并集与 SELECT 计数本身实现扎实且复跑通过，但 SSE 增量更新在改造后的主页面上实际失效（f001）、摘要同步漏字段（f002）、集合缓存从未被失效（f003），三处均直接违反 AC-003/AC-001 的“页面保持正确”，须修后重审。
- 系统性 follow-up：无（以上均为 t076 本地缺陷，就地修复即可）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。服务端分页/筛选/稳定排序/总数口径与 `page_size` 钳制 1..100 已读代码核实；后端 17 测试与前端 6 文件 76 测试复跑通过。
- AC-002：TICK-VALID，re_verified。列表/入口/切换器均改读一次批量摘要，不再逐环境发 runtime 请求，已读代码核实；前端相关测试复跑通过（残留全量 proxies/groups 拉取见 minor f006，不改变本条字面结论）。
- AC-003：TICK-VOID，re_verified。围栏与去重逻辑本身正确，但增量事件在列表/入口页因运行缓存为空被整条丢弃（f001），且摘要同步漏时间类字段（f002）；主页面上“增量后页面保持正确”未实现。
- AC-004：TICK-VALID，re_verified。并集语义（current/bound/both、去重、删除保护）共用 `_proxy_reference_map`，已读代码核实；含并集用例的后端测试复跑通过。
- AC-005：TICK-VALID，re_verified。`list_proxies` 的 SELECT 数在 20/100/1000 规模下恒定（≤8），含计数用例的后端测试复跑通过；干净主干对照确认门禁 4 失败 + 10 错误与 t076 无关。
- AC-006：TICK-VALID，re_verified。候选接口按名称可命中末项、国家键为稳定代码、表头全选为当前页语义，已读代码与测试核实；范围时效口径不一致见 minor f004。
- AC-007：TICK-VALID，re_verified。0/1/100/1000 矩阵测试复跑通过；集合读取无截断（变更后缓存失效缺失见 important f003，不改变本条规模矩阵结论）。
- AC-008：TICK-VOID，trust_prior。未勾选；云端无 Docker/Chrome/真实运行实例不可验，已登记 `docs/pending/p126_t076_ac008_real_runtime_chain_verification.md`（status todo，内容与 AC-008 一致），待 Mac 补验。

coverage = 7/8

verdict: FAIL

## Round 2 (2026-11-18T05:23:47+08:00)

- task：`t076_collection_queries_references_and_scale`
- spec：`docs/tasks/t076_collection_queries_references_and_scale/task.md`
- diff_anchor：`0445346773ab1c1152be2cbcfd4357395dc31b20`
- target：`git diff 0445346773ab1c1152be2cbcfd4357395dc31b20`
- round：2
- reviewed_at：2026-11-18T05:23:47+08:00

reviewed_scope: d2c4842386bbbb51

## Findings

### t076_code_f008 - 入口页运行桶超过 100 行时，真正运行中的环境会被截掉

- 严重度：minor
- 锚点：AC-007（入口读取无数据截断或遗漏）
- 位置：`src/frontend/src/features/browser-session/SessionEntryPage.tsx:19`，`src/frontend/src/features/browser-session/SessionEntryPage.tsx:31-36`
- 问题：入口页改读集合页 `{ status: "running", page: 1, page_size: 100 }`，而服务端 `status="running"` 是运行桶（running + starting，`src/backend/cbrowser/adapters/database/repository.py:460-470` 附近的 buckets 定义），客户端再按 `observed_state === "running"` 过滤；入口页没有翻页器。运行桶内超过 100 个环境时，第 101 个及之后的环境永远进不了第一页——其中真正 running 的行在入口页上消失，只能看到空态或不完整的运行列表。旧代码读全量 profiles 再逐个过滤，没有这个上限。触发条件是同时 running/starting 的环境数 >100，契约自述“不要求千个沙箱同时运行”，属有界设计下的残留截断，故定 minor。
- 建议：给集合端点一个精确 running 状态（只含 observed_state="running"），或入口页按页走访运行桶直到收满 running 行；只把 page_size 调大不可行，仓储层已钳制到 100（`src/backend/cbrowser/adapters/database/repository.py:394-397`）。

### t076_code_f009 - SSE 围栏只认运行缓存版本，两份缓存版本不一致时迟到事件可把摘要倒退回旧版

- 严重度：important
- 锚点：AC-003（旧运行实例或旧配置的迟到事件不能覆盖新实例）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:584-600`（围栏取值），`src/frontend/src/features/profiles/useProfilesQuery.ts:681-720`（摘要应用）
- 问题：f001 的修复把围栏改成“读两份缓存中现有的那份”，但实现是 `old?.config_version ?? summaryEntry?.config_version`——运行缓存存在时永远取运行缓存的版本，完全忽略摘要条目可能更新。两份缓存版本不一致是常态：摘要随列表页聚焦/重挂载重取（React Query 默认 staleTime 0），运行缓存只在详情页挂载时才重取；一次配置变更后，摘要已是新版、运行缓存仍是旧版。可复现场景：(1) 先访问某环境详情页，运行缓存停在 config_version 1、实例 I1；(2) 该环境代理连接变更升到版本 2，期间 SSE 断开、版本 2 事件未送达；(3) 重连/聚焦后摘要重取到版本 2、实例 I2，运行缓存仍是版本 1；(4) 一条重放/迟到的版本 1 事件（实例 I1）到达——围栏取运行缓存的版本 1，事件版本 1 不小于围栏、实例 I1 与围栏实例一致，双双放行；`mergeShared` 随后把摘要条目原地改写为旧事件的数据并把 `config_version` 置回 1（`:684-685`、`：697-720`），列表行状态、启动时间被倒退回旧值，直到下一次摘要重取才纠正。这正是 AC-003 明文禁止的“旧配置的迟到事件覆盖新状态”，且注释本身写着“must not overwrite newer state”。Round 1 新增的“旧版本事件不覆盖新摘要”测试只覆盖两份缓存版本一致的情形，未覆盖混合版本。
- 建议：围栏取两份缓存版本的最大值，实例取持有该最大版本的缓存那份；或更彻底——每份缓存各用自己的版本围栏，事件版本低于某份缓存版本时跳过那份、只更新另一份。

## 结论

- 前轮 finding 复核（Round 2，以 diff 与代码为准，不采信处置表自述）：
    - t076_code_f001 已消除：`src/frontend/src/features/profiles/useProfilesQuery.ts:584-600` 围栏改读两份缓存，`:681-720` 摘要原地更新；运行缓存仅在已存在时更新（`:651`、`：691`），仍不从事件合成运行条目；无变化时直接返回、不触发重取（`:690`）。
    - t076_code_f002 已消除：`mergeShared`（`:606-631`）复制 `last_started_at`/`last_stopped_at`（缺失保留旧值），`sharedChanged` 纳入两字段；摘要条目含 `failure_count`、`restart_blocked`、`preview_captured_at`、`updated_at`（服务端 `src/backend/cbrowser/domain/models.py:945-963` 的 `RuntimeSummaryEntry` 字段齐全）；预览事件同样原地更新摘要且捕获时间不倒退（`src/frontend/src/features/profiles/useProfilesQuery.ts:763-783`）。
    - t076_code_f003 已消除：新增 `invalidateProfileLists`/`invalidateGroupLists`/`invalidateProxyLists`（`src/frontend/src/features/profiles/useProfilesQuery.ts:52-71`，列表键 + 集合键双失效）；全仓 grep 确认，变更路径与 SSE 引用事件处理（含 `src/frontend/src/features/profiles/useGroupReorder.ts:26`）均改走 helper，残留的直接 `invalidateQueries` 只有 detail/runtime 键与 helper 自身。
    - t076_code_f004 已消除：`proxy_country_ranges`（`src/backend/cbrowser/adapters/database/repository.py:2099-2116`）改为按 `_latest_observation_geo_subquery()`（最新且仍有效）聚合，与筛选侧同一口径。
    - t076_code_f005 已消除：`_proxy_used_by_current`/`_proxy_used_by_bound`/`_proxy_used_by`/`_proxy_used_by_bound_only` 均接受已算好的映射（`src/backend/cbrowser/adapters/database/repository.py:1817-1883`）；`proxy_impact`、update_proxy 三路（重放/连接变更/IntegrityError 恢复）同一会话只算一次映射（`:2266-2280`、`:2397-2445`、`:2512-2530`）。`update_proxy` 非连接变更时返回 `len(versioned) + len(runtime_only)` 为 0 是基线原有行为（0445346:1893），不在本次 diff 内，不记 finding。
    - t076_code_f006 已消除：集合页行自带 `group_name`/`group_color`/`proxy_name`（服务端按页两条 `IN` 查询批量查名，`src/backend/cbrowser/adapters/database/repository.py:508-541`）；列表页筛选下拉与移动分组菜单改读有界候选 + 已选值单读回显（`src/frontend/src/features/profiles/EnvironmentListPage.tsx:115-135`）；入口页改读集合页（`src/frontend/src/features/browser-session/SessionEntryPage.tsx:18-20`）。
    - t076_code_f007 已消除：新增 `_escape_like`（`src/backend/cbrowser/adapters/database/repository.py:383-392`），全仓 grep 确认全部 `ilike` 搜索点（环境/代理/分组集合页与候选接口，共 9 处调用点）均带 `escape="\\"`。
- 本轮新发现：2 条（important 1 条：t076_code_f009；minor 1 条：t076_code_f008）
- 未进表的提示：文件过大——`src/backend/cbrowser/adapters/database/repository.py` 现 2610 行（Round 1 时 2492 行，本轮复核时仍在增长，已超 800 行阈值）；`src/frontend/src/features/profiles/useProfilesQuery.ts` 现 1022 行（Round 1 时 832 行，跨过 800 行阈值后又增约 190 行）。圈复杂度：`list_profiles_page`/`list_proxies_page` 本轮未新增分支，仍低于 15 的 minor 阈值，不进表。范围外观察：(1) 分组/代理筛选下拉只取首 50 条候选且未接搜索框，50 个以上的分组/代理无法在下拉里直接选为筛选值——候选接口本身支持按名称搜索，属“下拉由后续 UI task 提供”的非范围约定，不记 finding；(2) `SessionPage`、`ProfileDetailPage`、`ProfileForm`、`GroupManagerDialog` 仍有全量 profiles/groups/proxies 读取，均为 diff 外的既有消费方，不在本 task 改动内，不记 finding；(3) `src/frontend/pnpm-lock.yaml` 为未跟踪文件，仓内只跟踪 `package-lock.json`（npm），该文件是 worktree 内跑 pnpm 的副作用产物、不是 t076 交付文件；(4) 候选接口路由允许 `limit` 至 500 而仓储钳制为 50，静默截断属有界设计（Round 1 已注明）；(5) OpenAPI 生成物未逐行审，已由 contract 门禁覆盖。安全扫查：新端点沿用所在路由的 CSRF 依赖，与同路由既有 GET 端点一致；搜索参数均为绑定参数，无外部输入直达执行/拼接，无新增凭据落盘或日志；`GET /proxies/{id}/used-by` 对不存在的代理返回 404（service 层先验存在性，`src/backend/cbrowser/services/profile_service.py:1070-1076`）。
- 独立复验：后端 `tests/unit/test_t076_collection_queries.py` 17/17 通过、`tests/integration/test_t076_collection_api.py` + `tests/unit/test_api_models_and_sse.py` 8/8 通过（均用 worktree `.scratch/gate_venv` 当场重跑）。前端 `useProfilesQuery.test.tsx` 未能当场重跑：本会话 PATH 内 Node 为 24.22.1，门禁要求 >=26 \<27，工作区内无 Node 26；以前轮 evidence4 手动全量 674/674 通过作为 trust_prior 依据，不虚构复验。
- 总体判断：Round 1 的 7 条代码 finding 修复均已真实落地（f001 主路径已通），但 f001 修复的围栏在两份缓存版本不一致时仍会放行迟到事件、把摘要倒退回旧版（f009），AC-003 的“迟到事件不覆盖新状态”仍未完全守住；另入口页在运行桶超 100 行时截断（f008，minor）。须修后重审。
- 系统性 follow-up：无（以上均为 t076 本地缺陷，就地修复即可）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。分页/筛选/稳定排序/总数口径、`page_size` 钳制 1..100 与 LIKE 转义已读代码核实；后端 17 测试当场重跑通过。
- AC-002：TICK-VALID，re_verified。列表/入口/切换器/全局快照均改读一次批量摘要，不再逐环境发 runtime 请求，已读代码核实；残留全量读取在 diff 外的既有页面，不改变本条结论。
- AC-003：TICK-VOID，re_verified。增量主路径已修（f001/f002 已消除），但围栏在两份缓存版本不一致时仍放行迟到事件、把摘要倒退回旧版（f009），“旧配置迟到事件不覆盖新状态”未完全守住。
- AC-004：TICK-VALID，re_verified。并集语义共用 `_proxy_reference_map`，计数/明细/单项多项导航/删除保护同一口径，已读代码核实；used-by 不存在代理返回 404。
- AC-005：TICK-VALID，re_verified。引用映射一次聚合、多处复用已读代码核实；含 SELECT 计数用例的后端测试当场重跑通过。
- AC-006：TICK-VALID，re_verified。候选接口按名称可命中末项、国家键为稳定代码、国家→城市与筛选同一口径，已读代码与后端测试核实；筛选下拉首 50 条属后续 UI task 范畴，不改变本条结论。
- AC-007：TICK-VALID，re_verified。0/1/100/1000 矩阵后端测试当场重跑通过；入口页运行桶超 100 行的截断（f008，minor）只在同时运行/starting 超 100 的规模外情形出现，不改变本条规模矩阵结论。
- AC-008：TICK-VOID，trust_prior。未勾选；云端无 Docker/Chrome/真实运行实例不可验，已登记 `docs/pending/p126_t076_ac008_real_runtime_chain_verification.md`（status todo），待 Mac 补验。

coverage = 7/8

verdict: FAIL

## Round 3 (2026-11-18T06:27:56+08:00)

- task：`t076_collection_queries_references_and_scale`
- spec：`docs/tasks/t076_collection_queries_references_and_scale/task.md`
- diff_anchor：`0445346773ab1c1152be2cbcfd4357395dc31b20`
- target：`git diff 0445346773ab1c1152be2cbcfd4357395dc31b20`
- round：3
- reviewed_at：2026-11-18T06:27:56+08:00

reviewed_scope: 4945cf0e4ab78b2b

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核（Round 3，以 diff 与代码为准，不采信处置表自述；独立复验见下）：
    - t076_code_f008 已消除：后端 `running_exact` 只匹配 `observed_state="running"`（`src/backend/cbrowser/adapters/database/repository.py:421-422,457-458`，`running` 桶仍为 running+starting 不变）；路由 pattern 已放行该值（`src/backend/cbrowser/api/v1/router.py:356`），OpenAPI 两份生成物均已重导出（含 `running_exact` 各 1 处）；前端新增 `useAllProfilesCollectionQuery`（`src/frontend/src/features/profiles/useProfilesQuery.ts:111-145`），逐页走访至服务端总数，空页即停、按 `page * chunk.page_size >= chunk.total` 停；入口页改读它 + `running_exact`（`src/frontend/src/features/browser-session/SessionEntryPage.tsx:22-26`）。仓储测试（`tests/unit/test_t076_collection_queries.py:276-303`：桶 total 2、精确 total 1）与 HTTP 层测试（`tests/integration/test_t076_collection_api.py:132-171`：精确 total 1 且仅 `env-bound`、桶 total 2）及入口页 105 running + 10 starting 测试（`src/frontend/src/features/browser-session/SessionEntryPage.test.tsx:255-300`：105 条链接全出现、含 `p-run-104`、无 starting 行、至少 2 次调用且均含 `status="running_exact"` 与 `page=2`）均已当场重跑通过（见下）。
    - t076_code_f009 已消除：围栏改为每份缓存各自取值（`src/frontend/src/features/profiles/useProfilesQuery.ts:584-622`：`fenceAllows` 以各缓存自身的 `config_version`/`runtime_instance_id` 判定；事件版本低于该缓存版本、或同版本实例不同时只跳过该份缓存）；`mergeShared` 的 `config_version` 按每份缓存各自取 `event.config_version ?? base.config_version`（同文件 `:626-650`，运行缓存与摘要条目各调一次，互不串值）；两份缓存均无时仍直接返回、不凭空合成运行条目（`:583`）；任一缓存围栏放行但合并无变化时仍无副作用、不触发重取（`:691-696`）。混合版本双向测试（`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:734-808` runtime v1/summary v2：迟到 v1 事件只动 runtime、摘要保持 running/v2/inst-2；`:811-876` runtime v2/summary v1：迟到 v1 事件只动摘要至 stopped/v1、runtime 保持 running/v2，`running_count` 归 0）均已当场重跑通过（见下）。服务端事件恒带版本（`src/backend/cbrowser/domain/models.py:871` `config_version: int = 1`；发布路径 `src/backend/cbrowser/api/runtime_coordinator.py:898` 与快照路径 `:1076` 均填入），无版本事件的“按当前处理”分支只是防御性兜底。
    - Round 1 的 7 条代码 finding 抽查仍在（未全量重审）：f001 摘要更新已与运行缓存解耦（`useProfilesQuery.ts:583` 仅两份缓存均无时返回）；f002 `mergeShared` 复制 `last_started_at`/`last_stopped_at`/`failure_count`/`restart_blocked`/`updated_at` 且 `sharedChanged` 纳入两时间字段；f003 三个 `invalidate*Lists` helper 仍在（同文件 `:52-71`），全仓 grep 残留的直接 `invalidateQueries` 只有 helper 自身与无关模块（artifacts）及 detail/runtime 键；f004 `proxy_country_ranges` 仍走 `_latest_observation_geo_subquery`（`repository.py:2112`）；f005 三路 update/impact 同一会话只算一次引用映射并传入各 helper（`repository.py:2277-2281,2401-2417,2441-2447`）；f006 集合行自带分组/代理名、入口页读集合页；f007 `_escape_like` 仍在（`repository.py:383-392`），`escape="\\"` 共 13 处。
- 本轮新发现：0 条
- 未进表的提示：文件过大——`src/backend/cbrowser/adapters/database/repository.py` 现 2614 行、`src/frontend/src/features/profiles/useProfilesQuery.ts` 现 1073 行，均已超 800 行阈值且本轮仍在微增（分别 +4/+51 行）；按规则只作结论段提示，不进 finding 表。范围外观察（均不进表）：(1) `useAllProfilesCollectionQuery` 是 offset 分页走访，并发插入/删除发生在走访期间可导致某行重复或跳过、直至下次重取才纠正，重复行会产生重复 React key——属 offset 分页固有竞态，非本次修复引入的新缺陷，入口页 staleTime 0 下重挂载/聚焦即重取；(2) 入口页仍把集合行与摘要 `runningIds` 交叉过滤，摘要若恰在某行 starting→running 跃迁前取到，行会被藏到摘要重取或 SSE 事件到达为止——窄竞态，Round 2 已有，未被本轮改动；(3) `src/frontend/pnpm-lock.yaml` 仍为未跟踪文件，仓内只跟踪 `package-lock.json`，属 worktree 跑 pnpm 的副作用产物、不是 t076 交付文件（Round 2 已注明）；(4) OpenAPI 生成物未逐行审，已由 contract 门禁覆盖。安全扫查：`running_exact` 为纯新增枚举值、路由 pattern 校验，无新增外部输入直达执行/拼接，无鉴权/CORS 变更。
- 独立复验（本轮当场执行）：后端 `tests/unit/test_t076_collection_queries.py` + `tests/integration/test_t076_collection_api.py` 24/24 通过（worktree `.scratch/gate_venv`，11.86s）；前端 Node 26.13.0（`~/workspace/tools/node-26.13.0/bin` 置顶 PATH）跑 `useProfilesQuery.test.tsx` 15/15 + `SessionEntryPage.test.tsx` 3/3，共 18/18 通过。指纹当场重算为 `4945cf0e4ab78b2b`，与派审时一致。未全量重跑门禁：evidence5（`.scratch/t076_fix_evidence5/manifest.json`）在册，contract/integration/frontend/design 套件 exit 0，unit exit 1——其 4 失败 + 10 错误归因（t063/t068 老基线）沿用 Round 2 已逐项对照的结论，本轮未重验该对照。
- 总体判断：f008 与 f009 的修复均真实落地且经独立重跑验证，Round 1 的 7 条 finding 抽查仍在，本轮无新 blocking 缺陷；唯一未决项仍是云端不可验的 [deploy] AC-008（p126 待 Mac 补验），故 verdict 仍为 FAIL。
- 系统性 follow-up：无（以上均为 t076 本地结论，无跨 task 缺口）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。分页/稳定排序/总数口径、`page_size` 钳制 1..100 与 LIKE 转义已读代码核实；t076 后端 24 测试当场重跑通过。
- AC-002：TICK-VALID，re_verified。列表/入口/切换器均改读集合页加一次批量摘要，不再逐环境发 runtime 请求，已读代码核实；前端相关 18 测试当场重跑通过。
- AC-003：TICK-VALID，re_verified。每份缓存各自围栏已读代码核实，混合版本双向测试与迟到事件不倒退摘要的用例当场重跑通过；f009 已消除。
- AC-004：TICK-VALID，re_verified。并集语义共用 `_proxy_reference_map` 且映射一次聚合多处复用，已读代码抽查核实；t076 后端 24 测试当场重跑通过。
- AC-005：TICK-VALID，re_verified。引用映射一次聚合、多处复用已读代码核实；含 SELECT 计数用例的后端测试当场重跑通过。
- AC-006：TICK-VALID，re_verified。候选接口按名称可命中末项、国家键为稳定代码、国家→城市与筛选同一口径，已读代码抽查核实；t076 后端测试当场重跑通过。
- AC-007：TICK-VALID，re_verified。`running_exact` 加逐页走访至服务端总数已读代码核实，105 running + 10 starting 入口页测试当场重跑通过，无截断。
- AC-008：TICK-VOID，trust_prior。未勾选；云端无 Docker/Chrome/真实运行实例不可验，已登记 `docs/pending/p126_t076_ac008_real_runtime_chain_verification.md`（status todo），待 Mac 补验。

coverage = 7/8

verdict: FAIL

## Round 4 (2026-11-18T07:02:13+08:00)

- task：`t076_collection_queries_references_and_scale`
- spec：`docs/tasks/t076_collection_queries_references_and_scale/task.md`
- diff_anchor：`0445346773ab1c1152be2cbcfd4357395dc31b20`
- target：`git diff 0445346773ab1c1152be2cbcfd4357395dc31b20`
- round：4
- reviewed_at：2026-11-18T07:02:13+08:00

reviewed_scope: 3c6834b56be76d09

## Findings

本轮新发现：0 条。

## 结论

- 本轮返修范围核实：生产代码零改动——`src/frontend/src/features/profiles/useProfilesQuery.ts` 仍为 1073 行、`src/backend/cbrowser/adapters/database/repository.py` 仍为 2614 行，与 Round 3 报告记录一致；新增内容仅两处测试用例（`useProfilesQuery.test.tsx` 15→16 个用例、`SessionEntryPage.test.tsx` 3→4 个用例），后端测试文件无新增；`git diff` 文件清单与 Round 3 一致（45 文件）。
- 前轮 finding 复核（Round 4，以 diff 与代码为准，不采信处置表自述）：
    - t076_code_f008 已消除（仍在）：`running_exact` 与逐页走访逻辑未被改动（`src/frontend/src/features/profiles/useProfilesQuery.ts:111-145`）；f008 用例调用次数断言已由 `>= 2` 收紧为恰好 2 次（105 running + 10 starting 用例，`src/frontend/src/features/browser-session/SessionEntryPage.test.tsx:293-296`），本轮重跑通过；新增 f011 用例见下。
    - t076_code_f009 已消除（仍在）：每份缓存各自围栏（`src/frontend/src/features/profiles/useProfilesQuery.ts:631-650`）与 `mergeShared` 按份取版本（`:656-664`）未被改动；混合版本双向测试随 16 用例集重跑通过。
    - Round 1 的 7 条代码 finding 抽查仍在：f001 摘要更新与运行缓存解耦（`:630` 两份缓存均无才返回）；f002 `mergeShared` 复制时间字段且 `sharedChanged` 纳入两时间字段（`:681-692`）；f003 三个 `invalidate*Lists` helper 仍在（`:52,59,66`）；f004 `proxy_country_ranges` 仍走 `_latest_observation_geo_subquery`（`src/backend/cbrowser/adapters/database/repository.py:2112`）；f005 `_proxy_reference_map` 一次聚合多处复用（`src/backend/cbrowser/adapters/database/repository.py:1754-2052`）；f006 集合行自带分组/代理名（`src/backend/cbrowser/adapters/database/repository.py:519-541`）；f007 `_escape_like` 仍在（`src/backend/cbrowser/adapters/database/repository.py:383-392`）。
    - f010 纠正核实（属实）：`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts:2011` 的可选 `config_version` 确为 `SessionResponse` 的字段（该 schema 始于 :1965）；`ProfileRuntimeStatusEvent` 的 `config_version` 在 :1627，必填 `config_version: number`，`@default 1`（该 schema 始于 :1608）。Round 3 报告“finding 所引 :2011 实为 SessionResponse 的同名字段”的说法属实。线上传输确为原始 JSON：`parseProfileRuntimeEvent`（`src/frontend/src/shared/api/sse.ts:171-186`）只校验核心字段（profile_id/desired_state/observed_state/failure_count/restart_blocked/updated_at）与“出现时才校验”的可选字段，全文无任何 `config_version` 检查，最终 `return raw as ProfileRuntimeEvent`；服务端则恒带版本（`src/backend/cbrowser/domain/models.py:871` `config_version: int = 1`；发布路径 `src/backend/cbrowser/api/runtime_coordinator.py:898` 与快照路径 `:1076` 均填入）。因此无版本事件是解析器边界上的真实可能输入，用例以 `as ProfileRuntimeEvent` 构造线形输入合法，未 mock 被测围栏/合并逻辑。
    - f010 “视为当前”与 AC-003 的相容性：围栏 `event.config_version ?? cached.config_version`（`src/frontend/src/features/profiles/useProfilesQuery.ts:637`）使无版本事件通过版本比较，但实例围栏仍生效——事件与缓存实例 id 均非空且不同时仍被挡下（`:640-646`）；合并时 `config_version: event.config_version ?? base.config_version`（`:664`）使无版本事件不能把缓存版本拉低。唯一能以“当前”身份应用的无版本事件须同时缺实例 id，而当前服务端从不发出此类事件（版本与实例均恒带）。因此该放行语义不与 AC-003“旧配置迟到事件不覆盖新状态”冲突；新用例断言两份缓存均更新为 stopped、config_version 保持 2、running_count 归 0（`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:898-975`），与生产语义一致，本轮重跑通过。
    - f011 终止条件核查：`page * chunk.page_size >= chunk.total`（`src/frontend/src/features/profiles/useProfilesQuery.ts:131-136`）与空页兜底并列，服务端 `page_size` 回显与实际取数一致（`src/backend/cbrowser/adapters/database/repository.py:394` 钳制 1..100；`:509-510` `.offset((page-1)*page_size).limit(page_size)`；`:551-556` 回显同一钳制后 `page_size` 与 `total`），故终止条件按 `ceil(total/page_size)` 页停止：总数 100、页大小 100 时首轮即 `1*100>=100` 停（新用例断言恰好 1 次调用、100 行全出，含末行 p-run-099）；总数 105 时第 2 页 `2*100>=105` 停（f008 用例恰好 2 次）；总数 0 时空页即停；总数走访中途变小由新 total 或空页截停，变大则多取页直至新 total，不存在不终止的分支（无限增长须无限真实插入，不属缺陷）。offset 分页固有竞态（走访期间并发增删致重复/跳过）Round 3 已注明为非 finding，本轮不重复记。
- 本轮新发现：0 条
- 未进表的提示：文件过大——`src/backend/cbrowser/adapters/database/repository.py` 现 2614 行、`src/frontend/src/features/profiles/useProfilesQuery.ts` 现 1073 行，均已超 800 行阈值，但本轮生产代码零改动、行数与 Round 3 完全一致，按规则只作结论段提示，不进 finding 表。范围外观察：(1) 审阅中途 exec 视图曾两次短暂显示 `useProfilesQuery.ts` 为基线态（664 行、diff 中消失），随后自行恢复为 t076 态并在 3 次连续探测中稳定（1073 行、md5 `c92af5d4cd5a5119de2be3db7856a27f`、numstat 478/69），指纹两次重算一致为 `3c6834b56be76d09`，前端 20 测试与 `test:types` 均在恢复后的稳定态下跑过——本次结论以最终稳定态为准，若后续指纹再变须重审；(2) `src/frontend/pnpm-lock.yaml` 仍为未跟踪文件，属 worktree 跑 pnpm 的副作用产物、不是 t076 交付文件（Round 2 已注明）；(3) OpenAPI 生成物未逐行审，已由 contract 门禁覆盖。安全扫查：本轮只加两处测试，无生产代码改动，无新增外部输入处理，无鉴权/CORS 变更。
- 独立复验（本轮当场执行）：后端 `tests/unit/test_t076_collection_queries.py` + `tests/integration/test_t076_collection_api.py` 24/24 通过（worktree `.scratch/gate_venv`，11.63s）；前端 Node 26.13.0（`~/workspace/tools/node-26.13.0/bin` 置顶 PATH）跑 `useProfilesQuery.test.tsx` 16/16 + `SessionEntryPage.test.tsx` 4/4，共 20/20 通过；`npm run test:types` 通过。未重跑全量门禁：本轮不改生产代码，evidence5 全量门禁结论仍有效（沿用 Round 3 的说明）。未独立重做两处变异红灯验证，处置表所称红灯结果（f010 围栏 `?? 0` 则用例失败、f011 终止 `>` 则用例失败）采信为实施侧证据；但两处用例的断言本身已当场读过且与生产分支逐一对应（f010 的 `??` 两分支、f011 的 `>=` 边界），断言非恒真。
- 总体判断：f010 的类型引用纠正属实，无版本事件是真实运行时输入，“视为当前”放行语义在实例围栏与版本保持的双重约束下不与 AC-003 冲突；f011 终止条件在总数恰为页大小整数倍、空页、总数变化时均正确；Round 1–2 的代码 finding 抽查仍在，本轮无新 blocking 缺陷；唯一未决项仍是云端不可验的 [deploy] AC-008（p126 待 Mac 补验），故 verdict 仍为 FAIL。
- 系统性 follow-up：无（以上均为 t076 本地结论，无跨 task 缺口）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。终止条件与服务端 page_size 回显/钳制已读代码核实，f011 精确整页用例与后端 24 测试当场重跑通过。
- AC-002：TICK-VALID，re_verified。列表/入口/切换器均改读集合页加一次批量摘要，不再逐环境发 runtime 请求，已读代码抽查核实；前端相关 20 测试当场重跑通过。
- AC-003：TICK-VALID，re_verified。每份缓存各自围栏、无版本事件放行语义与实例围栏/版本保持已读代码核实，f010 新用例与混合版本双向测试当场重跑通过。
- AC-004：TICK-VALID，re_verified。并集语义共用 `_proxy_reference_map` 且映射一次聚合多处复用，已读代码抽查核实；t076 后端 24 测试当场重跑通过。
- AC-005：TICK-VALID，re_verified。引用映射一次聚合、多处复用已读代码核实；含 SELECT 计数用例的后端测试当场重跑通过。
- AC-006：TICK-VALID，re_verified。候选接口按名称可命中末项、国家键为稳定代码、国家→城市与筛选同一口径，已读代码抽查核实；t076 后端测试当场重跑通过。
- AC-007：TICK-VALID，re_verified。`running_exact` 加逐页走访至服务端总数已读代码核实，105 running + 10 starting 与精确整页 100 running 入口页测试当场重跑通过，无截断。
- AC-008：TICK-VOID，trust_prior。未勾选；云端无 Docker/Chrome/真实运行实例不可验，已登记 `docs/pending/p126_t076_ac008_real_runtime_chain_verification.md`（status todo），待 Mac 补验。

coverage = 7/8

verdict: FAIL

## Round 5 (2026-11-18T07:23:30+08:00)

- task：`t076_collection_queries_references_and_scale`
- spec：`docs/tasks/t076_collection_queries_references_and_scale/task.md`
- diff_anchor：`0445346773ab1c1152be2cbcfd4357395dc31b20`
- target：`git diff 0445346773ab1c1152be2cbcfd4357395dc31b20`
- round：5
- reviewed_at：2026-11-18T07:23:30+08:00

reviewed_scope: ac2dbfed0012e83d

## Findings

本轮新发现：0 条。

## 结论

- 本轮变更范围核实：相对 Round 4，生产代码与测试代码零改动——`src/backend/cbrowser/adapters/database/repository.py` 仍为 2614 行、`src/frontend/src/features/profiles/useProfilesQuery.ts` 仍为 1073 行，`git diff` 文件清单仍为 45 文件；本轮唯一契约区变更是 [deploy] AC-008 被打勾并加注，及 `progress.md` 新增「AC-008 处置」条。另，游离文件 `src/frontend/pnpm-lock.yaml`（worktree 跑 pnpm 的副作用产物、非交付物）已移出 worktree，指纹因此由旧值变为本轮值，除此之外交付内容无任何变化。
- 契约 drift 核对：AC-001–AC-007 的打勾是前轮 FAIL 后按流程撤回、修复重验后的重新打勾，Round 3/4 已逐条复核、本轮重跑测试再次通过（见独立复验），属经流程确认的变更，不记 finding。AC-008 的打勾有用户 2026-11-18 明确裁定为据（`progress.md`「AC-008 处置」条与 `task.md` 该 AC 注记互相印证，裁定要点一致：云端不可验 AC 视为完成打勾、不阻塞执行链、实际验证留待本地统一补验），不是未经确认的擅自变更，故不按「未经确认的 AC 变更」出 blocking finding；但该裁定处置的是执行链阻塞策略，不是验证事实本身，其对 TICK 判定的影响见下条。
- AC-008 TICK 判定理由（独立判定，不因裁定转述默认放行）：契约区规范写明「实施验证通过后由实施 Agent 就地打勾」，可测试性声明写明 [deploy] AC「须在本机隔离真实 Docker/Chrome 拓扑执行并留证，缺少前置不得用 mock、skip 或历史结果代替」——这两处契约文字均未被修订。交付内容中不存在任何真实 Docker/Chrome/Browser 链路验证证据；`task.md` 注记与 `progress.md` 处置条均自认「本勾为流程处置，非已实测通过」；`docs/pending/p126_t076_ac008_real_runtime_chain_verification.md` 仍为 status todo、「处理：未开」，且其正文同样写明不得用 mock、skip 或历史结果代替。按 TICK-VALID 的定义（实现与测试/验证在完整交付内容上真实支撑打勾），该勾证据不足、不成立，标 TICK-VOID。用户裁定与 p126 跟踪保证了该验证不会丢失、留待 Mac 统一补验，本判定不否定该流程安排，只是不把尚未发生的验证记为已通过；p126 补验通过并留证后，下一轮可据实改判。
- 前轮 finding 复核（Round 5，以 diff 与代码为准，不采信处置表自述）：t076_code_f001–t076_code_f009 在 Round 2–4 已逐条核实消除；本轮生产代码零改动（行数与 diff 清单与 Round 4 记录一致），覆盖 f008/f009 修复的关键回归测试当场重跑通过（见独立复验），复核结论维持「已消除」。
- 本轮新发现：0 条
- 未进表的提示：文件过大——`src/backend/cbrowser/adapters/database/repository.py` 现 2614 行、`src/frontend/src/features/profiles/useProfilesQuery.ts` 现 1073 行，均已超 800 行阈值，但本轮零改动，按规则只作结论段提示，不进 finding 表。范围外观察：(1) `src/frontend/pnpm-lock.yaml` 已移出 worktree，不再是未跟踪文件；(2) OpenAPI 生成物未逐行审，已由 contract 门禁覆盖。安全扫查：本轮无生产代码改动，无新增外部输入处理、鉴权或 CORS 面。
- 独立复验（本轮当场执行）：后端 `tests/unit/test_t076_collection_queries.py` + `tests/integration/test_t076_collection_api.py` 24/24 通过（worktree `.scratch/gate_venv`，49.69s）；前端 Node 26.13.0 跑 `useProfilesQuery.test.tsx` 16/16 + `SessionEntryPage.test.tsx` 4/4，共 20/20 通过。AC-008 的真实链路在云端无 Docker/Chrome 不可复验，且交付内无任何实施侧 deploy 证据可供采信为通过。
- 总体判断：代码层面前轮 finding 全部消除且本轮无新缺陷，AC-001–AC-007 打勾成立；唯一未决仍是 AC-008——其打勾是经用户裁定的流程处置而非验证通过，按契约区规范与可测试性声明，该勾不成立，故本轮 verdict 仍为 FAIL，待 p126 在 Mac 补验通过后重审改判。
- 系统性 follow-up：无（AC-008 补验已有 p126 跟踪，不重复立项）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。分页/稳定排序/总数口径与 `page_size` 钳制代码与 Round 4 核实一致、生产代码零改动；后端 24 测试当场重跑通过。
- AC-002：TICK-VALID，re_verified。列表/入口/切换器改读集合页加一次批量摘要的路径未变；前端相关 20 测试当场重跑通过。
- AC-003：TICK-VALID，re_verified。每份缓存各自围栏与无版本事件用例随 `useProfilesQuery.test.tsx` 16 用例集当场重跑通过，代码未变。
- AC-004：TICK-VALID，re_verified。并集引用语义共用同一引用映射，随后端 24 测试当场重跑通过，代码未变。
- AC-005：TICK-VALID，re_verified。含 SELECT 计数用例的后端测试当场重跑通过，引用映射一次聚合多处复用的代码未变。
- AC-006：TICK-VALID，re_verified。候选接口命中末项与国家→城市同口径用例随后端 24 测试当场重跑通过，代码未变。
- AC-007：TICK-VALID，re_verified。105 running + 10 starting 与精确整页 100 running 入口页用例随前端 20 测试当场重跑通过，代码未变。
- AC-008：TICK-VOID，trust_prior。已打勾但注记自认「非已实测通过」；契约要求真实 Docker/Chrome 拓扑执行并留证、不得以其他方式代替，交付内无任何 deploy 验证证据，p126 仍为 todo 未开，待 Mac 补验。

coverage = 7/8

verdict: FAIL

## Round 6 (2026-11-18T07:31:05+08:00)

- task：`t076_collection_queries_references_and_scale`
- spec：`docs/tasks/t076_collection_queries_references_and_scale/task.md`
- diff_anchor：`0445346773ab1c1152be2cbcfd4357395dc31b20`
- target：`git diff 0445346773ab1c1152be2cbcfd4357395dc31b20`
- round：6
- reviewed_at：2026-11-18T07:31:05+08:00

reviewed_scope: 69ad025aed11463c

## Findings

本轮新发现：0 条。

## 结论

- 本轮变更范围核实：相对 Round 5，生产代码与测试代码零改动——`src/backend/cbrowser/adapters/database/repository.py` 仍为 2614 行、`src/frontend/src/features/profiles/useProfilesQuery.ts` 仍为 1073 行，`git diff` 文件清单仍为 45 文件，`git status --short` 共 47 项（含两份未跟踪 review 报告）；游离文件 `src/frontend/pnpm-lock.yaml` 仍不在 worktree 内。本轮唯一实质变化是契约区新增「[deploy] AC 打勾处置注记（契约修订，2026-11-18）」，指纹因此变为本轮值。
- 契约 drift 核对（按 prompt 要求）：`git diff` 显示 AC-001–AC-007 正文一字未改、仅勾选状态由未勾变为已勾，属前轮 FAIL 后按流程撤回、修复重验后的重新打勾，Round 3–5 已逐条复核、本轮重跑测试再次通过，不记 finding。AC-008 正文原句一字未改，仅在其后追加云端不可验与用户裁定的括注，并新增处置注记小节；该修订有用户 2026-11-18 明确裁定为据（注记引文与 `progress.md`「AC-008 处置」条互相印证、要点一致），且注记明文只变更打勾的流程语义与验证时点、不豁免验证本身，不是未经确认的擅自变更，不按 blocking finding 处理。未知契约清单无 `UNVERIFIED-BLOCKING`、`UNVERIFIED-SPIKE` 或裸 `UNVERIFIED` 标记（命中的一处仅为该小节的规范说明文字本身）。
- AC-008 TICK 判定（按修订后契约）：处置注记规定 Review Agent 对此类 AC 以注记为准——云端可做部分已完成且补验 pending 已登记者，判 TICK-VALID（处置型）。两项前提当场核实成立：(1) 云端可做部分已完成——支撑 AC-008 的 API/SSE/引用一致性实现即 AC-001–AC-007 的交付，本轮后端 24 测试与前端 20 测试当场重跑全部通过（见独立复验）；(2) 补验 pending 已登记——`docs/pending/p126_t076_ac008_real_runtime_chain_verification.md` 存在、status 为 todo、正文内容与 AC-008 验证要求一致且明文不得用 mock、skip 或历史结果代替。故本轮 AC-008 改判 TICK-VALID（处置型，trust_prior：真实 Docker/Chrome 链路验证本身仍未发生，待 p126 在 Mac 补验留证后由本地复核闭环；本判定不表示已实测通过）。
- 前轮 finding 复核（Round 6，以 diff 与代码为准，不采信处置表自述）：t076_code_f001–t076_code_f009 在 Round 2–4 已逐条核实消除；本轮生产代码零改动，关键修复点当场抽查仍在——f003 三个失效 helper 仍在（`src/frontend/src/features/profiles/useProfilesQuery.ts:52,59,66`）；f004 `proxy_country_ranges` 仍走 `_latest_observation_geo_subquery`（`src/backend/cbrowser/adapters/database/repository.py:2103-2116`）；f007 `_escape_like` 仍在（同文件 `:383`，`escape=` 共 14 处）；f008 `running_exact` 后端桶定义、路由 pattern 与入口页消费仍在（同文件 `:421,458`、`src/backend/cbrowser/api/v1/router.py:356`、`src/frontend/src/features/browser-session/SessionEntryPage.tsx:23`）；f009 每份缓存各自围栏 `fenceAllows` 与 `mergeShared` 按份取版本仍在（`src/frontend/src/features/profiles/useProfilesQuery.ts:631-650` 起）。复核结论维持「已消除」。
- 本轮新发现：0 条
- 未进表的提示：文件过大——`src/backend/cbrowser/adapters/database/repository.py` 现 2614 行、`src/frontend/src/features/profiles/useProfilesQuery.ts` 现 1073 行，均已超 800 行阈值，但本轮零改动，按规则只作结论段提示，不进 finding 表。范围外观察：OpenAPI 生成物未逐行审，已由 contract 门禁覆盖。安全扫查：本轮无生产代码改动，无新增外部输入处理、鉴权或 CORS 面；契约注记与 pending 文件均为流程文档，不引入代码面风险。七视角扫查（安全/正确性/契约·Breaking/性能·资源/架构·可维护性/健壮性·可观测/文档·规格一致性）均已覆盖，本轮无命中项。
- 独立复验（本轮当场执行）：落点仓库校验通过（无 `-C` 的 `git rev-parse --show-toplevel` 输出与要求一致）；后端 `tests/unit/test_t076_collection_queries.py` + `tests/integration/test_t076_collection_api.py` 24/24 通过（worktree `.scratch/gate_venv`，11.07s）；前端 Node 26.13.0 跑 `useProfilesQuery.test.tsx` 16/16 + `SessionEntryPage.test.tsx` 4/4，共 20/20 通过。未重跑全量门禁：本轮不改生产代码，evidence5 全量门禁结论仍有效（沿用 Round 3–5 的说明）。
- 总体判断：前轮代码 finding 全部消除且本轮无新缺陷，AC-001–AC-007 打勾成立；AC-008 按经用户裁定并已写入契约的处置注记改判 TICK-VALID（处置型），真实验证由 p126 跟踪、留待 Mac 补验闭环，不再阻断本轮结论。
- 系统性 follow-up：无（AC-008 补验已有 p126 跟踪，不重复立项）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。分页/稳定排序/总数口径与 `page_size` 钳制代码与 Round 5 核实一致、生产代码零改动；后端 24 测试当场重跑通过。
- AC-002：TICK-VALID，re_verified。列表/入口/切换器改读集合页加一次批量摘要的路径未变；前端相关 20 测试当场重跑通过。
- AC-003：TICK-VALID，re_verified。每份缓存各自围栏代码当场抽查仍在，混合版本与无版本事件用例随 `useProfilesQuery.test.tsx` 16 用例集当场重跑通过。
- AC-004：TICK-VALID，re_verified。并集引用语义共用同一引用映射，随后端 24 测试当场重跑通过，代码未变。
- AC-005：TICK-VALID，re_verified。含 SELECT 计数用例的后端测试当场重跑通过，引用映射一次聚合多处复用的代码未变。
- AC-006：TICK-VALID，re_verified。候选接口命中末项与国家→城市同口径用例随后端 24 测试当场重跑通过；`proxy_country_ranges` 同口径聚合当场抽查仍在。
- AC-007：TICK-VALID，re_verified。105 running + 10 starting 与精确整页 100 running 入口页用例随前端 20 测试当场重跑通过；`running_exact` 三处落点当场抽查仍在。
- AC-008：TICK-VALID，trust_prior。处置型判定：按契约区处置注记，云端可做部分已完成（支撑实现随本轮后端 24 + 前端 20 测试重跑通过）且补验 pending p126 已登记（status todo、正文与 AC-008 一致、明文不得以 mock/skip/历史结果代替）；真实链路验证待 Mac 补验留证后闭环，本判定非已实测通过。

coverage = 7/8

verdict: PASS
