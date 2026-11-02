# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-02T20:00:00+08:00 t008/t013 已合入；t014 部分合入并保留阻塞

### 主仓

- 主分支最新：`e7f58ce`（t014 partial merge）在本交接提交前。已合入：t008 `a448db7`、t013 `c629fe5`、t014 部分 `e7f58ce`（执行 commit `ad39d63`）。未 push。
- 仓库仅保留 main 分支；t008/t013/t014 工作分支已删除，worktree 已清理。

### 已完成

- t008：Artifact/CDP 自动化，AC 全勾，full review Round 3 两轴 PASS。
- t013：Profile 复制/状态复制/重置，AC 全勾，full review Round 5 两轴 PASS。
- t014 已交付部分：Profile `clipboard_sync` → Selkies `enable_clipboard=true/false`、`enable_binary_clipboard=false|locked`、`clipboard_seamless=false|locked`；Stream 入口 CLI；前端只读权限提示（denied/prompt、权限变化监听、不读写剪贴板、Profile 关闭时隐藏）。AC-001/AC-005 已勾。

### t014 阻塞

- AC-002/003/004 仍未勾选：缺独立真实 Chrome E2E（四类输入目标、预编辑取消/标点/失败提示、纯文本粘贴截断/重复、真实权限拒绝/后台恢复/跨 Profile 剪贴板隔离）。曾尝试扩展 t004 单体 E2E，IME 阶段后 CDP target 失效，实验已回滚。
- 待办：`docs/pending/todo/p015_t014_input_clipboard_e2e.md`。恢复时建议从 main 新建独立 t014 worktree，先写独立 Browser+Stream+双 Profile E2E harness，再完成 review/finish。
- t009–t012 仍 backlog，t009 依赖 t014 完成，不能提前开工。

### 队列

- t014（阻塞）→ t009 → t010 → t011 → t012。
