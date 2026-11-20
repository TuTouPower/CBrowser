---
pid: "p155"
slug: "profile_create_runtime_status_stale"
status: "todo"
---
# p155 新建或启动环境后列表状态不自动刷新且SSE事件被丢弃

- 现象：用户在“环境管理”页面点击“新建环境”，填写表单后点击“创建并启动”；弹窗关闭后，新创建的环境出现在环境列表表格中，但其运行状态固定显示为灰色的“已停止”（stopped），未能自动变为黄色的“启动中”（starting）或绿色的“运行中”（running）。即使后端已成功拉起容器并通过 SSE 广播 `runtime_state` 事件，前端列表依然无任何响应。用户必须手动刷新整个浏览器页面（F5），触发全量重新拉取，才能看到状态变为黄色“启动中”或绿色“运行中”。同理，新建未启动环境后在列表直接点击“启动”，状态同样不会动态变为启动中。
- 影响：
    1. 用户体验严重受阻：环境创建并启动后，用户误以为启动失败或卡死在 stopped 态，被迫频繁手动刷新页面。
    2. 读模型与实时通信断联：环境列表读模型 `runtimeSummary` 无法动态感知新环境的运行时生命周期流转。
    3. 统计计数漂移：`runtimeSummary.running_count` 无法及时计入新启动的环境。
    4. 影响范围涵盖所有增删改动作：新建环境（`useCreateProfileMutation`）、复制环境（`useDuplicateProfileMutation`）、删除环境（`useDeleteProfileMutation` / `useDeletionBatchQuery`）、直接改状态（`useSetDesiredStateMutation` / `useStopProfileMutation`）。
- 根因（开发铁律深度剖析）：
    产品缺陷（历史为规避 N+1 引入分裂读模型与多头缓存导致的架构反噬）。
    1. **顶层架构缺陷：读模型分裂（Split Read Model）**：在环境管理列表页中，呈现一行环境本该是一个内聚的实体视图，但历史演进（t076）为了避免逐环境发 HTTP 请求，将读模型切成两半：一半走分页配置 `GET /profiles/collection`，另一半走全量未分页的 `GET /profiles/runtime-summary`（全库运行状态打包下拉）。前端被迫在客户端做类似数据库的 Hash Join（`summaryById.get(item.id)`）拼装成 Row，使前端沦为伪数据库。
    2. **多头缓存与时序脱节**：前端 React Query 被迫维护 `collection` 与 `runtimeSummary` 两份互不相干的缓存。新建环境时 `invalidateProfileLists` 只失效了分页列表，**从未失效 `profileKeys.runtimeSummary()`**。新环境进入列表分页后，摘要缓存中完全没有该环境的条目。
    3. **SSE 增量同步防御过度与丢弃机制**：在 `useProfileEventsSync`（`src/frontend/src/features/profiles/useProfilesQuery.ts:690-706, 808-846`）中，为了防范为未缓存环境臆造条目，要求必须已存在 `summaryEntry` 才处理。当新 Profile 的 SSE `starting` 事件到达时，由于 `summary.entries` 中尚无此条目，事件被直接判定无效并静默丢弃；且 `entries.map` 也绝不会插入新项。
    4. **渲染兜底掩盖真相**：列表页从 `summaryById` 中查不到新环境，`row.runtime` 为 `undefined`，而在 `EnvironmentTable.tsx` / `EnvironmentCard.tsx` 中 `row.runtime?.observed_state ?? "stopped"` 兜底为 "stopped"。
        已确认同类位点清单：
    - 位点 1（新建）：`useCreateProfileMutation` 成功后未同步失效或更新 `runtimeSummary`。
    - 位点 2（复制）：`useDuplicateProfileMutation` 成功后未同步失效或更新 `runtimeSummary`。
    - 位点 3（删除）：`useDeleteProfileMutation` / `useDeletionBatchQuery` 成功后未同步失效或清理 `runtimeSummary` 中的残留条目。
    - 位点 4（期望状态与启动）：`useSetDesiredStateMutation` / `useStopProfileMutation` 成功后仅更新 `profileKeys.runtime(id)`，未更新或失效 `runtimeSummary`。
    - 位点 5（SSE 同步器）：`useProfileEventsSync` 中对未在 `summary.entries` 的条目直接忽略，无法动态插入新条目并重新计算 `running_count`。
    - 位点 6（失效助手）：`invalidateProfileLists` 语义未涵盖 `runtimeSummary`，导致所有依赖其失效的流程均存在状态滞后。
- 解决方案（开发铁律：架构至上、拒绝妥协、零兼容性负担）：
    - **拒绝妥协**：严禁在 Mutation 处塞 `invalidateQueries(runtimeSummary)` 或在 SSE 处 `summary.entries.push` 打局部补丁（此类补丁无法消除 SSE 与 HTTP 重新拉取的网络时序竞争 Race Condition，且会加剧客户端伪数据库复杂度）。
    - **彻底重构**：
        1. **统一聚合读模型**：破坏性改造 `GET /api/v1/profiles/collection` 接口契约，后端查询在 SQL 层面直接 `outerjoin(ProfileRuntimeModel)`，使分页返回项（如 `ProfileCollectionItemResponse`）直接嵌套原生完整 `runtime: ProfileRuntimeResponse` 字段。一次请求，配置与状态原子到达。
        2. **彻底废除列表对全量 Summary 的依赖**：前端环境列表直接消费 `item.runtime`，彻底删除前端 `summaryById` / `summaryToRuntime` 胶水拼接逻辑。
        3. **单一响应式流更新**：重构 `useProfileEventsSync`，删除针对 summary 数组的 200 行代次映射与复杂双轨逻辑。SSE 收到 `runtime_state` 事件直接定向就地更新 `collection` 缓存中对应 `profile_id` 项的 `runtime` 字段，实现零撕裂流转。
        4. **全局指标解耦**：全局正在运行环境数（`running_count`）若需保留，降级为独立轻量度量（Metrics），与环境列表行彻底解耦。
- 测试缺口：
    1. 现有测试 `src/frontend/src/features/profiles/useProfilesQuery.test.tsx` 在测试 `runtimeSummary` 时，全部在触发事件前先通过 `setQueryData` 人为预置了包含目标 Profile 的 `summary.entries`（如 line 307-328），掩盖了未预置条目时的丢弃行为。
    2. 同文件 line 277 甚至将“未缓存 Profile 不凭空构造数据”作为断言，未区分“全局未知的 profile”与“新创建但列表已展示的 profile”。
    3. 组件测试（`ProfileCreateDialog.test.tsx`）只断言了弹窗内部状态和 API 调用参数，未挂载列表与 SSE 做联动验证。
        应补验证：
    - 前端单元测试（`useProfilesQuery.test.tsx`）：
        - 断言在已有集合缓存前提下，新建并启动新环境后，集合缓存中新项能够立即带有 starting 状态。
        - 断言对集合缓存中已有的环境，收到其 SSE `runtime_state` 事件后能够直接就地更新其 `runtime`，状态由 starting 自动变为 running。
    - 前端组件/页面测试（`EnvironmentListPage.test.tsx`）：
        - 模拟停留在列表页、打开新建弹窗、点击“创建并启动”、随后收到 SSE `starting` 事件，在不刷新页面的情况下断言目标行的 Badge 状态自动变为黄色的“启动中”。
- 线索：
    - 最小复现测试：`.scratch/repro_create_status/repro.test.tsx`，配合配置 `.scratch/repro_create_status/vitest.config.mjs`。
    - 执行命令：`cd src/frontend && npx vitest run --config ../../.scratch/repro_create_status/vitest.config.mjs`。
    - 实测输出：`AssertionError: expected undefined to be defined`，精准复现 `runtimeSummary` 中条目丢失、状态无法从 stopped 更新到 starting 的事实。
- 处理：未开
