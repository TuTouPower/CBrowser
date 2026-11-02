# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-02T20:12:30+08:00 t014 已 drop；剪贴板改 seamless 同步；下一步 t009

### 主仓

- branch `main`，交出时 head_commit `7535802`（本交接单独提交）。仅 main 分支，无 task worktree。origin/main 停在 `60b5024`，本节 commit 未 push。
- 本节 commit：`856757d` t014 drop 与 t009 AC-003 降级；`7535802` 剪贴板 seamless 同步。

### 用户决定（2026-11-02）

- CBrowser 仅本人单机使用。t014 AC-001/005 已随 `e7f58ce` 合入；AC-002/003/004 自动化 E2E 不做。t014 原 branch/worktree 已删，active 状态无法在 main 直接 drop，经 `rewind --to backlog` 后 drop；p015 以 transferred 归档到 t009。
- t009 依赖改为 t013；AC-003 改为真实 Chrome 手动清单（四类输入框中文提交/预编辑取消/标点、双页同时输入、剪贴板双向同步无截断、关闭时无传输）。
- 剪贴板：`clipboard_sync` 开启时 `SELKIES_CLIPBOARD_SEAMLESS=true|locked`，纯文本双向自动同步（直接 Cmd+C/V，Selkies `mac_cmd_as_ctrl` 默认开启）；关闭时 `enable_clipboard=false`；二进制保持 `false|locked`。见 decisions 012；计划 8.4/19.3 原“剪贴板原内容保护/后台不覆盖”作废。按用户指示小改动直接在 main 修改，未走 task 流程。

### 验证

- unit 491 passed；frontend Vitest 17 files / 121 passed；md_kx check 与 `git diff --check` 通过。
- 未跑 tsc 构建（仅改文案）与真实 Chrome 剪贴板 E2E；实际同步行为由 t009 AC-003 手动清单验收。
- 正在运行的 `cbrowser:latest` 容器是旧版 VNC，不受影响；v2 栈未运行，下次构建 Stream 镜像并启动 v2 时生效。

### 遗留与队列

- `docs/pending/todo/p014_v2_upload_picker_access.md`：上传文件是否须在容器 GTK 文件选择器中可选，待用户决定范围。
- 队列：t009 → t010 → t011 → t012。`docs/runtime/goal_queue.json`（gitignored）冻结快照仍含 t014，`goal-check` 输出 `GOAL_QUEUE_STOPPED: t014=dropped`；走 /goal 前须 `task.py goal --reset` 或按新成员重建。
- t009 其余 AC（8 小时压测、1/3/10 路性能、完整安全矩阵、网络/重启黑盒）对单人使用偏重，开工前与用户确认是否降级。
