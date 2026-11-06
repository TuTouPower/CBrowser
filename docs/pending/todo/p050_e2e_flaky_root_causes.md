# p050 E2E 三项反复/负载失败根因（含公网依赖）

- 来源：用户监督补充（t037 门禁 v8 的 3 项非基线失败 + t035 同类失败）。
- 内容：t037 门禁 v8 的 3 项非 t019 基线失败不能只凭单跑通过放过，需从根因修：
    1. `tests/e2e/test_frontend_adapter_build.py::test_vendor_replaces_stale_destination_contents`：用例每次从公网下载官方 Selkies wheel（`urllib.error.URLError: [SSL: UNEXPECTED_EOF_WHILE_READING]`），t035 门禁也出现过同类失败。E2E 不应依赖公网：改为使用已锁定 SHA256 的本地缓存 wheel（复用 `config/selkies/selkies_web_sha256.txt` / `.scratch/selkies_wheels/`），缓存缺失时按必跑模式失败封闭（列出缺失项，不静默 skip、不回落公网）。
    2. `tests/e2e/test_frontend_app_e2e.py::test_ac007_lifecycle_resume_and_isolated_media_diagnostics`：媒体帧时序失败（`AssertionError: Worker must have discarded encoded frames, got 0`），在门禁负载下出现、单跑通过。定位负载下的等待与就绪判定根因，改为事件或就绪条件驱动（等首帧 / 帧计数变化 / SSE 状态），不要靠加长超时。
    3. `tests/e2e/test_supervisor_recovery_e2e.py::test_supervisor_dual_profile_port_invariance_on_sigkill`：setup 阶段 `httpx.ReadTimeout: timed out`。同样定位负载下 harness 启动就绪判定根因，改为健康检查 / 事件就绪条件驱动，不加长超时。
- 验收标准：**聚合 task 的完整门禁（`CBROWSER_RUN_E2E=1 scripts/run_gates.sh`）中这三项都通过**（不是仅定向单跑通过）。
- 已知证据：t037 v8 三项失败与定向重跑 `3 passed in 213.30s`；t035 同类 SSL EOF；t044 最终门禁同一批用例通过（说明是负载/网络波动，非稳定回归）。
- 处理：待转入聚合 task 解决。
