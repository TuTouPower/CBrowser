# p108 环境列表页搜索栏下方孤立渲染纯数字运行计数

- 现象：环境管理页（`EnvironmentListPage`）搜索工具栏下方、环境表格/空状态上方渲染了一个孤立的纯数字（如 `1` 或 `0`），没有任何前缀标签、单位、状态点或图标说明其含义。
- 影响：用户在环境管理页看到来历不明的裸数字，易误解为页面错乱或残留调试输出，无法直接理解其代表“运行中环境数量”。全前端已扫描排查，无其他同类孤立裸数字统计渲染位点。
- 根因：产品代码缺陷（`src/frontend/src/features/profiles/EnvironmentListPage.tsx:253-258`）。
    - 机制核实：`EnvironmentListPage` 直接将 `useRuntimeSnapshot(client)` 返回的整数 `snapshot.runningCount` 渲染进 `<div data-testid="env-running-count" className="font-ui text-label-sm text-on-surface-muted">{snapshot.runningCount}</div>`（自 `c797eb3e` 引入起即如此），未调用已有的 `t("runningProfiles", { count: snapshot.runningCount })`（`src/frontend/src/i18n.tsx:233` 英文 `"Running: {count}"`、`:729` 中文 `"运行中：{count}"`），也未附带标签、图标或单位。此前 `AppLayout.tsx` 侧栏底部曾用 `t("runningProfiles", { count: runningCount })` 展示运行计数，在 `12231821` 精简侧栏移除后，`runningProfiles` 键在全前端已无人使用，而列表页的裸数字 `env-running-count` 保留至今。
    - 全前端扫描结论：已扫无同类。逐一核查 `src/frontend/src/` 非测试 `.tsx` 文件中的数值/计数渲染：`ProxyListPage.tsx:367-368` 与 `ProxyTable.tsx:138-139` 的 `<MonoValue>{proxy.used_by_count}</MonoValue>` 紧邻 `<span>{t("proxyUsedByLink")}</span>`；`SettingsPage.tsx:273-283` 的 `fontSet.file_count` / `fontSet.used_by_count` 在 `<dl>` 内与 `<dt>{t("fontSetFileCount")}</dt>` / `<dt>{t("fontSetUsedBy")}</dt>` 成对展示；`ProfileAutomationTab.tsx:181-184` 的 `control.generation` 在 `<dl>` 内与 `<dt>{t("controlGeneration")}:</dt>` 成对展示；`BatchActionBar.tsx:26` 与 `GroupManagerDialog.tsx:201,286,293` 均使用带文案的 i18n 模板（`envSelected` / `groupUsedBy` / `groupDeleteConfirm` / `groupAffectedCount`）。
- 测试缺口：
    - 漏过原因：`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx:608` 与 `:627` 仅使用弱子串断言 `expect(screen.getByTestId("env-running-count").textContent).toContain("1")` 与 `.toContain("0")`，未校验标签前缀、单位或禁止纯数字文本，导致节点只输出 `"1"` / `"0"` 时 23 条用例全部通过。
    - 应补验证：在组件单测 `EnvironmentListPage.test.tsx`（含初始渲染及 `AC-004 SSE 增量`）改用完整语义断言，校验 `env-running-count` 渲染内容匹配本地化带标签文本（如英文 `"Running: 1"` / `"Running: 0"`、中文 `"运行中：1"` / `"运行中：0"`）且不匹配纯数字 `/^\d+$/`。
- 线索：`.scratch/repro_env_running_count.test.tsx`（配套 `.scratch/repro_env_running_count.vitest.config.ts`，执行 `./src/frontend/node_modules/.bin/vitest run --config .scratch/repro_env_running_count.vitest.config.ts --root .` 验证 `env-running-count` 的 `textContent` 为 `"1"` 且不含 `"Running"`）
- 处理：t073；resolution=transferred；reason=已合并转交 t073（设计系统与工作台/环境管理重构）
