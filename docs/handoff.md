# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-02T14:50:00+08:00 t008/t013完成并合入；t014因AC-002/003/004证据缺口阻塞

### 主仓与已合入

- main 在本交接提交前为 `c629fe5`。t008 `a448db7`、t013 `c629fe5` 已本地合入，未 push；两条 task 分支执行 commit 分别为 `986d3e2`、`6d28f59`，分支已删除。
- t008：Artifact Service/Store/API、下载校验和与 Agent 重启对账、认证 CDP 入口、Selkies file_transfers=none、`/profiles/:id/files` 与 `/automation/:id` 页面；unit 469、integration 79、frontend 116、真实 Chrome E2E 1、两轴 full review Round 3 PASS。
- t013：配置复制/状态复制/重置、幂等键、前端确认面板；unit 489、integration 85、frontend 117、真实 API+容器 Cookie E2E 1、两轴 full review Round 5 PASS。

### t014 当前阻塞

- worktree `/Users/karson/kar/code/CBrowser_t014`，branch `t014_v2_clipboard_input`，base `6d28f59`；attempt 1，execution_id `5c4ef9fdabd5406bb58816597111d2a1`，owner `opencode_t014_2f32e2581975`。attempt 已 terminal stopped、report blocked，worktree 保留。
- 已实现并通过：Profile `clipboard_sync` -> Selkies `enable_clipboard=true/false`、`enable_binary_clipboard=false|locked`、`clipboard_seamless=false|locked`；Stream 入口 CLI；前端只读权限提示（denied/prompt、监听权限变化、不读写剪贴板、按 Profile 关闭隐藏）。
- 未完成：AC-002/003/004 未勾选。缺少本 task 真实 Chrome 证据：地址栏/普通输入框/受控输入框/富文本四类 composition/预编辑取消/标点/失败提示；纯文本粘贴无截断/重复；真实权限拒绝/后台恢复/切换 Profile 的剪贴板隔离。已登记 `docs/pending/todo/p015_t014_input_clipboard_e2e.md`。
- review：两轴 Round 2 FAIL，缺上述证据；t014 不能 finish/merge。

### 后续行动

- 先按 p015 补真实 Chrome E2E，或在用户明确接受范围收缩后调整 AC；完成后重新 reserve attempt、实施、review、finish、cleanup、合入。
- 队列保持 t014 → t009 → t010 → t011 → t012；t009 的 1000 次输入/剪贴板压力不替代 p015 的场景覆盖。
