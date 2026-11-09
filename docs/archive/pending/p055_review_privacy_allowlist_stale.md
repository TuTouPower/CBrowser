# p055 t047 归档后隐私 allowlist 未同步，全量门禁红灯

- 现象：`tests/unit/test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths` 在 main 13e6316 失败：`docs/archive/handoff.md` 36 处、`docs/archive/tasks/t047_ui_theme_omni_restyle/review_general.md` 1 处、`.../task.md` 2 处出现开发者主目录前缀（扫描器 POSIX home 形态）。
- 影响：全量门禁 unit suite 失败，阻塞所有 task 的 AC「全量门禁通过」；不影响运行时代码。
- 根因：t047 集成把 task 文件移入 `docs/archive/` 并改写 `docs/archive/handoff.md`，但未同步 `tests/unit/review_privacy_allowlist.txt` 的 (path, sha256) 精确指纹；`3c8e33f` 改 handoff 内容后旧指纹即失效，t047 归档文件从未登记。
- 测试缺口：现有 allowlist 精确指纹机制本身能检出漏登记，属于发布流程遗漏而非测试缺口；修复只需登记当前字节 fingerprint。
- 线索：`TMPDIR=/tmp PYTHONPATH=src/backend <gate-python> -m pytest tests/unit/test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths -q`
- 处理：main；resolution=resolved；reason=登记 t047 归档文件与更新后 handoff 的精确字节指纹；tests/unit/test_repo_hygiene.py 8 passed
