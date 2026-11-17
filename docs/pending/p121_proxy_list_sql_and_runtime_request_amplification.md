---
pid: "p121"
slug: "proxy_list_sql_and_runtime_request_amplification"
status: "closed"
resolution: "transferred"
reason: "已核实根因、同类范围与验收契约，按用户授权聚合转交 t076（环境代理集合读模型、引用一致性与规模适配）；转办不表示实现完成"
fix_ref: "t076"
---
# p121 代理列表重复扫描运行绑定快照，环境状态按条取数导致请求放大

- 来源：2026-11-17 用户要求检查大量环境/代理时所有入口是否适配，pending-record 分析登记。
- 现象：代理列表 SQL 数量随代理数和运行绑定数相乘增长；环境相关页面/切换器冷缓存按每个环境单独拉 runtime，切换器未展开也发起全量环境状态请求。
- 影响：代理列表和任何消费 proxies.list 的环境表单/筛选；环境列表、全局 AppLayout 状态、会话入口、环境切换器、代理使用环境浮层。已确认查询/请求数放大，尚未在目标大数据规模测出具体页面耗时、内存或卡死阈值，不能夸大为已验证的卡死。
- 根因：数据库层 list_proxies 为每代理调用 \_proxy_used_by；该函数先查当前引用，再查所有 runtime，并对每 runtime 逐次查 bound config_version 快照，形成重复扫描。前端多个 useQueries 对全部 profiles 创建 runtime 查询，EnvironmentSwitcher 的 enabled 仅判断 profiles.length，与 open 状态无关。

## 复现与同类扫描

1. 真实 `ProfileRepository` + `.scratch/` 临时 SQLite，用 SQLAlchemy before_cursor_execute 计数：10代理/5运行绑定，list_proxies 返回10项，执行72次 SELECT；20代理/10运行绑定，返回20项，执行242次 SELECT。当前探针数据满足 `SELECT数 = 2 + P × (2 + R)`；不含造数阶段查询，P=代理数、R=运行绑定行数。
2. `repository.py:1525` list_proxies → `_proxy_used_by:1501` → `_proxy_used_by_bound:1476` 每代理重复取全部 runtime，再逐条版本查询。`_current_observations` 已批量取每代理最新观测，不是本次重复查询根因；不能将已修的观测 N+1 再报一遍。
3. 真实 `EnvironmentSwitcher` 渲染100个环境，弹层保持关闭、QueryClient 冷缓存，mock getRuntime 实际调用100次。探针断言100个不同 profile ID；未请求任何真实服务。
4. 确认同机制消费方：`EnvironmentListPage.tsx:64`、`app/useRuntimeSnapshot.ts:22`（AppLayout 即消费）、`SessionEntryPage.tsx:20`、`EnvironmentSwitcher.tsx:84` 对全部 profiles 创建查询；`ProxyUsedByPopover.tsx:21` 在打开时对全部关联环境查询。
5. 相同 QueryClient + queryKey 的并发请求可去重，不能把各组件简单相加宣称多个 N；staleTime=5000 也不是并发上限。已确认冷缓存最少随集合逐条取数，不在本条推断实际浏览器连接并发数。
6. 其他未实测的增长项：EnvironmentListPage 对每环境 groups.find/proxies.find，GroupManagerDialog 逐组扫描 profiles，以及全量 DOM 渲染。记录在 p119 规模验证范围，不仅凭缺少虚拟列表判为独立 bug。

## 修复与验证要求

- 代理使用引用聚合应避免对每代理重复扫描所有绑定版本，保持“当前配置引用 ∪ 运行绑定引用”去重计数与删除保护语义，不能只统计当前配置以减少 SQL。
- 环境状态取数按实际消费需要、已有状态分发机制和目标规模规划；减少关闭浮层无关工作及每条独立请求放大，不预先指定分页或新协议。若改跨服务契约，后续须走 task 流程。
- 补真实 repository 查询计数测试，覆盖代理数/绑定数增长、无绑定、同环境当前/绑定同代理去重、旧绑定仍保护代理；不能只测返回结果而漏查复杂度。
- 补组件冷/热缓存、浮层开关、切换/筛选行为与网络请求数量验证；对目标规模再测耗时/资源，不能以 mock API 速度证明真实性能已通过。
- 现有 repository 测试覆盖使用计数和删除保护，但缺少 P×R 组合及 SELECT 数约束；UI 测试以少量环境为主，未断言关闭浮层时不为所有环境取状态。
- 线索：`.scratch/repro_large_list_query_amplification.py`（`PYTHONPATH=src/backend .venv/bin/python .scratch/repro_large_list_query_amplification.py`）；`.scratch/repro_collection_query_and_reference.test.tsx` 与对应 vitest config（2 passed，包含本项与 p122 组件复现）。数据库探针仅用临时目录造数，无用户数据写入。
- 关联：p119 规模验证总表；p122 需要保留的 bound-only 引用语义。
- 处理：t076；resolution=transferred；reason=已核实根因、同类范围与验收契约，按用户授权聚合转交 t076（环境代理集合读模型、引用一致性与规模适配）；转办不表示实现完成
