# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-02T20:50:00+08:00 p014 闭环（页面文件选择对话框）；下一步 t009

### 主仓

- branch `main`，交出时 head_commit `8ccb9ae`（本交接单独提交）。仅 main 分支，无 task worktree。origin/main 在 `5136766`；`8ccb9ae` 与本交接 commit 未 push。
- 今日 main 直接修改（用户指示小改动不走 task 流程）：`856757d` t014 drop 与 t009 AC-003 降级；`7535802` 剪贴板 seamless 同步（decisions 012）；`8ccb9ae` 页面文件选择对话框。

### p014 结论

- 实测原 Browser Runtime 镜像无 GTK/xdg portal，页面 `<input type=file>` 点击无反应，网站上传完全不可用。镜像加 `libgtk-3-0`；入口写 `$XDG_CONFIG_HOME/gtk-3.0/bookmarks`（`Uploads` -> `/exchange/uploads`）。
- 加 GTK 后 Chromium 按键走 GTK IME，Selkies 组合输入重映射键码后读到过期键表，提交错误汉字（stream composition E2E 实测“一丁丂”变“一丒专”）。Runtime Agent 固定注入 `--disable-gtk-ime` 修复。
- 验证：新增 `test_p014_file_input_opens_chooser_with_uploads_bookmark`（旧镜像红、新镜像绿）；browser runtime E2E 16 passed；stream runtime/keymap E2E 2 passed；unit 491 passed；截图确认侧栏 Uploads 可用。测试镜像 `cbrowser-p014-browser:e2e`（`sha256:b9f74092…`）仅本地验证用，正式交付由 t012 重建。
- 上传文件位于 `/exchange/uploads/<UUID>/<文件名>`，对话框中需先进 UUID 文件夹；未做扁平视图。

### 队列

- t009 → t010 → t011 → t012；`docs/pending/todo/` 为空。
- `docs/runtime/goal_queue.json`（gitignored）冻结快照仍含 t014，`goal-check` 输出 `GOAL_QUEUE_STOPPED: t014=dropped`；走 /goal 前须 `task.py goal --reset` 或按新成员重建。
- t009 其余 AC（8 小时压测、1/3/10 路性能、完整安全矩阵、网络/重启黑盒）对单人使用偏重，开工前与用户确认是否降级。
