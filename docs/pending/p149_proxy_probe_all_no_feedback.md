---
pid: "p149"
slug: "proxy_probe_all_no_feedback"
status: "closed"
resolution: "transferred"
reason: "已核实 main(HEAD b297639) 上两条问题均仍有效、无等价 active/backlog task；按用户 2026-11-20 授权依开发铁律聚合为一个根因重构 task，并纳入 useBatchActions 环境批量与沙箱依赖测试改写，已转交 t094"
fix_ref: "t094"
---
# p149 代理管理批量测速被降格为客户端串行循环：异步作业编排缺位致无进度反馈、超时错配与全量语义破损

- 来源：用户 2026-11-20 反馈「点了代理管理右上角的测速按钮，半天没结果，好像必须逐行点才行」；bug-to-pending 分析登记。未在本次分析修改生产代码。
- 现象：点击代理管理右上角「全部测速」（Zap 图标）后，列表长时间无可见变化、无结果提示；改点每行闪电按钮则立刻有反馈（该行按钮禁用、单条 toast）。期望全局按钮立即给出可感知的启动反馈、逐条进度与最终结果；实际整批跑完才出现唯一一次 toast，单次探测耗时较长时表现为“半天没结果”。
- 影响：代理管理全局测速交互与用户判断；批量期间行按钮仍可点，可能对同一代理并发探测；单次探测超 30s 时前端记失败、后端仍继续写观测，列表与后端状态不一致；代理总数 >50 时“全部测速”实际只测当前页且无提示。探测真实耗时受部署环境 Supervisor/helper 容器冷启动放大，但根因在架构分层，不在环境配置。

## 根因（架构层）

表征（无进度、30s/90s 错配、只测当前页）是症状。根因只有一条：**把应由服务端编排的异步批量作业，降格成客户端 `for` 循环；服务端已有的 observation 状态机 + SSE 基础设施未被用作进度权威源，客户端另造了一套状态机。**

1. **作业编排层错位** — `src/frontend/src/features/proxies/ProxyListPage.tsx:269-287` 把“批量测速”建模为 N 次串行 HTTP 调用。客户端编排长耗时批量的固有缺陷：进度无法可靠回传、超时/取消/重试要在客户端重建、串行度被锁死、页面卸载即失联、N×RTT 放大。不是参数问题，是分层错误。
2. **双重状态机** — 后端已有 `proxy_egress_observations` 的 `pending → ok/failed` + `observed_at` + TTL（`src/backend/cbrowser/services/profile_service.py:1740-1820`、迁移 `0006/0010`），是天然的作业状态载体。前端却用 `probingAll` / `probingId` 局部 `useState`（`ProxyListPage.tsx:157-158`）另造状态，两套状态靠 `invalidateProxyLists` 触发 refetch 同步（`src/frontend/src/features/profiles/useProfilesQuery.ts:1133-1136`），产生 UI 抖动与状态漂移。
3. **同步请求-响应模型承载分钟级操作** — `POST /proxies/{id}/probe` 同步等待 Runner（最长 90s，`src/backend/cbrowser/services/egress_probe.py:90`）。HTTP 请求-响应不适合长作业；30s 超时错配（`src/frontend/src/shared/api/client.ts:98,664-668`）是“慢操作硬塞进同步模型”的必然结果，不是漏配参数。
4. **超时策略散落调用点** — `defaultTimeoutMs` / `uploadTimeoutMs` / `longOperationTimeoutMs` 各调用点手工选（`client.ts:98-100,398`），契约中无“预期耗时”元数据，无法确定真相；任何新增长操作都可能漏配。
5. **分页视图与全量操作语义冲突** — “全部”作用于 `visible`（当前页 50 条，`ProxyListPage.tsx:138-148,206`），作业作用域被错误绑定到视图分页。profile 侧已有全量遍历 `useAllProfilesCollectionQuery`，proxy 侧缺失，同一分层的对称破损。

## 修复方向（架构级，破坏性，不留兼容路径）

- **API 契约重定义** — 删除同步单条 `/probe`；新增批量作业端点，入参为过滤条件/选择集（非当前页 id），立即返回 `job_id` + `202`；作业整体状态（total/completed/failed/state）持久化，逐项进度写入现有 observation 表。长耗时从请求路径消失，超时错配从根上不复存在。
- **UI 单一状态源** — 删除 `probingAll` / `probingId`；行状态直接读服务端 `observation_status === "pending"`，批量进度读 job 状态，经已有 SSE 通道实时推送。按钮提交作业后立即反馈“已提交 N 项”，不再等待、不再靠 refetch 同步；路由切换/刷新后由 observation 恢复，作业不中断。
- **全量语义归位** — 作业作用域由服务端过滤条件定义，分页只作视图；“全部”即过滤后全集。
- **超时收敛进契约** — 作业提交是毫秒级短请求；长操作兜底超时由契约集中声明，调用点不再手工选择。
- **同类位点一并重构** — `src/frontend/src/features/profiles/useBatchActions.ts:40-85` 的环境批量 start/stop/moveToGroup 同样改为服务端作业 + 进度事件，共用同一进度 UI 组件，删除客户端串行循环。

拒绝的补丁方案：加进度条、把 30s 改成 120s、改并行、补跨页循环。都保留“客户端编排长作业 + 双重状态机”，只消症状——进度仍靠轮询、卸载仍失联、超时仍散落、分页语义仍错。按项目开发铁律（架构至上、拒绝妥协、零兼容负担），这些属应被拒绝的局部修补。

代价：OpenAPI 契约、前端生成类型、后端作业/队列、E2E 全链路破坏性变更；门禁需重跑 `schemas/openapi` 生成与前后端测试。

## 同类与对照位点

- 确认成立并纳入同一修复范围：`useBatchActions.ts:40-85` 环境批量同为串行循环 + 结束单一 toast（`show(t("envBatchResult", ...))`），批量期间无逐行反馈；动作耗时短、症状弱于测速，但与测速共用同一编排缺陷，应共用服务端作业与进度组件。若用户裁决缩小范围，可拆为独立 pending。
- 对照（非缺陷）：`ProxyListPage.tsx:249-267` 单行 `handleProbe` 有即时 `setProbingId` 与逐条 toast，反馈正常；作业化后此路径一并改为提交单条作业，由同一状态源驱动。
- 已排除：事件绑定（`ProxyListToolbar.tsx:120` 与 `Button.tsx` 的 `{...rest}` 透传）、接口路径（前端 `client.ts:666` / 后端 `proxies_router.py:162-164` / 生成契约一致）、缺 await（`ProxyListPage.tsx:275` 有 await）、只测第一行（`:273` 遍历全部 visible）、actionKey 复用（`src/frontend/src/shared/api/action_key_mutation.ts:57-65` 每次调用 `mintKey()`，probe 无 body 有意不传 key）。
- 历史关联：p110（已转交 t074）记录了批量串行耗时线性放大的计时失真；t074 已把延迟展示改为服务端 `latency_ms`，但串行无反馈、超时错配与作业编排缺位仍在当前实现。本条为架构残留，不改写 p110。

## 测试缺口

`src/frontend/src/features/proxies/ProxyListPage.test.tsx:766-774` 的批量测试只断言 `probe` 被调用 4 次且 mock 立即 resolve，固化了“客户端循环编排”旧模型，无法暴露作业编排、进度、超时与跨页问题。应补：

- 契约层：批量作业端点入参（过滤条件/全集，非当前页）、`job_id` 与 `202` 立即返回、作业总状态与逐项 observation 的 pending → ok/failed 迁移。
- 前端：提交作业后立即反馈、SSE 进度更新、路由切换/刷新后由 observation 恢复、行按钮批量期间禁用、进度组件与 `useBatchActions` 共用行为；删除对 `probingAll` / `probingId` 局部状态的断言。
- 超时：作业提交为短请求，不再依赖 `defaultTimeoutMs`；长操作兜底从契约读取；原 30s/90s 错配场景不再存在。
- 规模：>50 代理跨页时作业作用于过滤后全集，分页只影响视图；批量并发受服务端配额控制而非客户端串行。
- 复现层：现有 `.scratch/` 测试仅证明双重状态机下反馈缺失，重构后应改为验证单一状态源驱动的进度。

## 复现与线索

- `.scratch/repro_batch_probe_feedback/repro.test.tsx`（2 passed）注入延迟 probe 并渲染真实 `ProxyListPage`：点击 `proxy-probe-all` 后探测期间三条行按钮均未 disabled、无 toast，全部 resolve 后才出现唯一 toast；对照单行点击 `proxy-probe-px1` 后该行按钮立即 disabled。执行 `cd .scratch/repro_batch_probe_feedback && ../../src/frontend/node_modules/.bin/vitest run --config vitest.config.ts --root .`；配置 `.scratch/repro_batch_probe_feedback/vitest.config.ts`。

- 静态证据链：`ProxyListPage.tsx:269-287`（串行编排）、`:157-158,206`（双重状态机与当前页作用域）、`client.ts:98,664-668`（超时错配）、`egress_probe.py:90`（后端 90s）、`useBatchActions.ts:40-85`（同类位点）。

- 处理：t094；resolution=transferred；reason=已核实 main(HEAD b297639) 上两条问题均仍有效、无等价 active/backlog task；按用户 2026-11-20 授权依开发铁律聚合为一个根因重构 task，并纳入 useBatchActions 环境批量与沙箱依赖测试改写，已转交 t094
