---
pid: "p148"
slug: "runtime_download_e2e_partial_file_race"
status: "todo"
---
# p148 下载 E2E 提前把 Chromium 临时文件判为完成

- 现象：全量真实 Docker E2E 的 `test_ac004_download_capture_and_recovery` 把 0 字节 `.crdownload` 选为第一个下载文件并失败，随后使用同一 Browser 镜像独立复跑通过。
- 影响：下载捕获与重连用例可在正常下载过程中误报失败。同文件的 `test_t008_download_reconcile_after_agent_restart` 路径也存在先取目录首文件、后等待完成事件的检查顺序，清理断言可能检查到已经由 Chromium 重命名的临时路径。
- 根因：第一个下载路径使用 `glob("*")` 把文件出现作为完成条件，Chrome 在内容写入完毕前就会暴露临时路径。后续下载虽然匹配内容，仍在目录枚举和读取的间隔暴露于临时文件重命名。现有生产下载扫描排除临时后缀。
- 测试缺口：以完成事件关联路径与实际内容验证下载。分别覆盖临时文件先出现、最终文件重命名和转发清理，确保断言落在完成产物。
- 线索：`.scratch/t091_all_gates/junit/e2e.xml` 原失败、`.scratch/t091_failed_e2e_recheck_eCHRtV/junit.xml` 同镜像复跑证据。
- 处理：未开
