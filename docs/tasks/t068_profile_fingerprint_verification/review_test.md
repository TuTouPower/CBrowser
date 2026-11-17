# Task review t068（reviewer_focus: 测试）

- task：`t068_profile_fingerprint_verification`
- spec：`docs/tasks/t068_profile_fingerprint_verification/task.md`
- diff_anchor：`c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- target：`git -C '<worktree>' diff c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- round：1
- reviewed_at：2026-11-14T00:49:21+08:00

## Findings

### t068_test_f001 - `aggregate_samples` 缺测/非确定采样聚合及 HTTP/字体 comparator 分支缺独立单测

- 严重度：minor
- 锚点：AC-001 / AC-002 覆盖边界扩展建议
- 位置：`tests/unit/test_t068_fingerprint_verification.py:212-289`（对应生产代码 `src/backend/cbrowser/fingerprint_verification/probe_collector.py:266-392`、`src/backend/cbrowser/fingerprint_verification/comparator.py:162-177,206-251,336-365`）
- 问题：`test_comparator_blocks_missing_drift_nondeterminism_and_distinguishes_unsupported` 使用手工构造的报告字典覆盖了 `compare_reports` 对 `missing` / `unapproved_drift` / `context_support_changed` / `ja3_raw` 非确定方差的阻断，但 `probe_collector.aggregate_samples` 在单元测试中未被直接调用，导致采样出现单次超时/报错时的 `determinism="missing"` 归类、`unique_count > 1` 的 JS 指标分布汇总（`min`/`max`），以及 `compare_reports` 中 `http_header` 漂移/缺失、`font_evidence` 漂移与 `ignore_stateful_storage_usage` 仅放行同 `quota` 场景缺乏独立单测（虽然真实 E2E 已通过 CLI 触发 `aggregate_samples` 正常采样与四上下文/HTTP 矩阵采集）。
- 建议：在 `tests/unit/test_t068_fingerprint_verification.py` 增补直接调用 `aggregate_samples`（含缺失/错误样本与多次采样分布漂移）及 `compare_reports` 对 `http_header`、`font_evidence`、`ignore_stateful_storage_usage` 边界的单元测试。

### t068_test_f002 - `test_ac003` E2E 篡改与更新标记负向未复入容器路径，且缺少 `--version` 探针失配负例

- 严重度：minor
- 锚点：AC-003 覆盖边界扩展建议
- 位置：`tests/e2e/test_t068_fingerprint_gate_e2e.py:146-171`、`tests/unit/test_t068_engine_artifact_pinning.py:97-130`（对应生产代码 `src/backend/cbrowser/engine_artifacts.py:470-491`）
- 问题：`test_ac003_cache_init_and_runner_pinning_fail_closed` 在真实 `cache_init` 容器跑通后，对篡改 `libGLESv2.so`、篡改 `chrome` 与放置 `latest_version_linux-arm64` 均在宿主机直接调用 `verify_extracted_engine_cache(..., run_version_probe=False)` 断言报错，未再次通过 `DockerAdapter.ensure_runtime_cache` 走容器内 `cache_init` 失败路径（该脚本仅在单测 `test_docker_adapter_cache_init_rejects_corrupted_binary_in_script` 以宿主机子进程实跑验证过）；此外全仓测试对 `verify_extracted_engine_cache` 的主动负向调用均传入 `run_version_probe=False`，未触发 `engine_artifacts.py:470-491` 的 `version_probe_mismatch` 分支（该分支在容器正例中以 `run_version_probe=True` 运行通过）。
- 建议：在 `tests/unit/test_t068_engine_artifact_pinning.py` 增补 `--version` 输出不匹配触发 `version_probe_mismatch` 与 `BrowserRunner.resolve_engine_binary()` 拒绝篡改支持库/marker 的单测，并视运行时间允许在 `test_ac003` E2E 补充损坏缓存触发 `adapter.ensure_runtime_cache` 失败的容器闭环断言。

## 结论

- 改测方向复核：无「迁就实现」改测。`tests/unit/test_refactor_behavior_equivalence.py::test_container_spec_cache_specs` 原硬编码无防绕过字段的旧 5 键输出，因 AC-003 变更为锁定版本与 `CLOAKBROWSER_AUTO_UPDATE=false` 而整体删除，并由 `tests/unit/test_t068_engine_artifact_pinning.py::test_cache_init_environment_disables_auto_update_and_pins_version` 覆盖新契约；`tests/unit/test_a26_browser_image_modules.py::test_browser_image_ships_only_runtime_closure` 因离线探针包 `fingerprint_verification` 需入 Browser 镜像以便同拓扑测量而整体替换为 `test_browser_image_ships_runtime_closure_and_offline_probe`，保留了顶层文件严格集合等式并新增探针包存在断言。两处均属规格变更驱动的合法整体替换，未就地改旧预期。
- 本轮新发现：2 条（0 critical，0 important，2 minor）
- 未进表的提示：① 范围外既有 `main` 基线失败：`tests/unit/test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip`（复跑仍为 `GatewayTopologyHarness.data_dir` `AttributeError`）与全量 E2E 11 项既有基线失败（`test_artifact_download_chain_e2e` / `test_profile_preview_e2e`×2 / `test_browser_runtime_e2e`×3 / `test_frontend_app_e2e`×4 / `test_stream_runtime_e2e`）均属 `main` 基线遗留问题，与 t068 变更及测试可信度无关；② 依据 ADR 021 及 `task.md`「不下载未批准版本」约束，本机仅有一套已获准 `linux-arm64` 制品（`146.0.7680.177.3`），真实跨版本引擎升级放行及 `linux-x64` 解压产物逐文件摘要在 `docs/tasks/t068_profile_fingerprint_verification/measurement_report.md` 第 6 节如实列为未验证项，门禁以同制品重复 + 受控输入漂移 + 制品损坏验证两条分支；③ `.scratch/t068/gate_evidence/manifest.json` 记录的全量门禁快照先于 `test_a26` 整体替换与最后一次 `browser_runtime` 镜像重建（`manifest.json` 镜像 ID 与 `measurement_report.md` 记录的 `sha256:53aec49d6439e72dba82433ee5ed63c772cb478f168c53b264c6721af0164735` 不一致），本次已独立核验最新镜像内 5 个核心源码 SHA-256 与 worktree 完全一致，并在该最新镜像与当前完整 worktree 上独立复跑通过全部 t068 unit/E2E/关联回归；④ 工具链异常：`findings.py new` 因 `main` 分支既有重复编号 `d037`/`d038` 拒绝分配，实施方未手工建 `dNNN` 亦未改工具链，已核实结论完整回填 `task.md` 未知契约清单。
- 总体判断：无 critical/important 阻断，4 条 AC 测试与真实 Docker/Chrome/引擎及本地证据均经独立复核成立，建议 PASS。
- 系统性 follow-up：经 `.repo_template/scripts/task.py list` 核对，当前 backlog 尚无专门处理 `main` 基线 `test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip`（`GatewayTopologyHarness.data_dir`）及 `findings.py` 既有重复编号 `d037`/`d038` 的 task，建议后续另行立项收敛（不阻断 t068）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。独立复跑 `tests/e2e/test_t068_fingerprint_gate_e2e.py::test_ac001_ac002_ac006_real_engine_multicontext_baseline_and_drift_gate` 在真实 Docker/Xvfb/`chromium-146.0.7680.177.3` 容器内对 `prof-e2e-01` v1 重复产出报告并定位 `canvas2d` 等漂移；`tests/unit/test_t068_fingerprint_verification.py::test_comparator_blocks_missing_drift_nondeterminism_and_distinguishes_unsupported` 验证 `missing_measurement` 与 `expected_unsupported_context=10` 严格区分且不作无漂移；`.scratch/t068/evidence/` 14 份基线与 diff 文件 SHA-256 与 `measurement_report.md` 第 7 节逐一校验匹配（含 16 处受控 seed 漂移可定位 diffs）。
- AC-002：TICK-VALID，re_verified。独立复跑 E2E 与 unit 证实 main/iframe 全 18 项 API 与 worker/service_worker（13 `ok` + 5 `unsupported_context`）及 `worker_fetch`/`sw_fetch` 不含 `sec-ch-ua-platform` 的完整矩阵；默认严格模式因 `ja3_raw` 非确定方差 `blocked`，仅显式传入 `tls_extension_shuffle_via_ja4=True` 后同制品重复 `approved`；`candidate_notls`（`inconclusive:tls_capture`）与 seed 漂移均 `blocked`；unit 另验证缺测、上下文支持翻转与未获批方差均阻断且 `ja4`/`ja3_sorted` 与 raw `ja3` 分布分离记录。
- AC-003：TICK-VALID，re_verified。独立复跑 `tests/unit/test_t068_engine_artifact_pinning.py`（8 项全过，含真实 `scripts/deploy.sh` 拦截损坏缓存与 `CLOAKBROWSER_AUTO_UPDATE=true` 并写入 `manifest["engine"]`、实际子进程执行 `DockerAdapter` 注入脚本遇损坏二进制退出非 0、`BrowserRunner` 拒绝 bypass 变量、ADR 021 `0.6.4` 与 `linux-arm64` 15 文件摘要锁定）、`tests/e2e/test_t068_fingerprint_gate_e2e.py::test_ac003_cache_init_and_runner_pinning_fail_closed` 与 `tests/e2e/test_supervisor_cache_initialization_e2e.py::test_fresh_pinned_engine_and_geoip_cache_complete_once`（真实容器 `cache_init` 在 `need_geoip=False/True` 下完成 15 文件校验与 `--version` 探针，损坏 `libGLESv2.so`/`chrome`、`latest_version_linux-arm64` 与绕过环境均被拒），且 `engine_artifacts.py` 与 `measurement_report.md` 如实分层说明“下载层 Ed25519 + 解压件仓库 SHA-256 清单”。
- AC-006：TICK-VALID，re_verified。独立复跑 `test_t068_fingerprint_verification.py` 与 `test_t068_fingerprint_gate_e2e.py` 验证受控 HTTPS 下捕获真实 BoringSSL `ClientHello`（GREASE 过滤与扩展乱序下 `ja4` 收敛双值、`ja3_sorted` 稳定、`ja3_raw` 逐连接变化），`consistency.verdict == "consistent"` 与 `tls_status == "verified"` 且绑定 `engine_build`/`binary_sha256`/`config_version`/`probe_version`；真实 `--no-tls` HTTP-only 容器实跑返回 `tls_evidence.status == "inconclusive"` 与 `consistency.verdict == "inconclusive"` 并阻断升级；篡改 HTTP `sec-ch-ua-platform` 判 `inconsistent`，全程未引用任何厂商通过率。

coverage = 4 / 4

reviewed_scope: e91443e8fc8639b8
verdict: PASS

## Round 2 (2026-11-14T01:16:15+08:00)

- round：2
- reviewed_at：2026-11-14T01:16:15+08:00
- target：`git -C '<worktree>' diff c5f83296ece80a9a0ed9f1e48d957ce332f858c4`

### 前轮 finding 复核

- `t068_test_f001`（minor）→ **已消除**：核实 `tests/unit/test_t068_fingerprint_verification.py:357-667` 新增回归测试直接触达生产代码且无恒真断言、弱化断言或 mock 掉被测逻辑：① `test_aggregate_samples_catches_partial_http_missing_header_variance_and_js_states`（435-534 行）直接调用 `probe_collector.aggregate_samples`，实测覆盖正常一致聚合、样本 0 缺失 `main_after_ch`（`status="missing"`、`missing_sample_indices=[0]`、不写入 `http_headers`、`consistency["verdict"]=="inconclusive"` 且 `compare_reports` 以 `missing_measurement:http.main_after_ch` 阻断）、样本间 HTTP 请求头漂移（`determinism="non_deterministic"`、`unique_count=2`、`consistency["verdict"]=="inconsistent"` 且 `compare_reports` 以 `non_deterministic_variance:http.main_after_ch` 阻断）、单样本 JS 错误（`audio="error"` → `determinism="missing"`）与多样本分布统计（数值 `min=10.5`/`max=12.0` 与字符 `unique_count=2`）；② `test_comparator_edge_cases_empty_metrics_http_font_and_storage_quota`（537-614 行）覆盖空 `metrics={}` 护栏（`blocked` 且 `missing_count >= 72`）、`worker_fetch` 请求头漂移、`font_evidence` 缺失/漂移，以及 `ignore_stateful_storage_usage=True` 下同 `quota` 放行与异 `quota` 阻断边界；③ `test_consistency_missing_vs_inconsistent_and_cross_context_checks`（616-641 行）与 `test_parse_tls_client_hello_rejects_odd_lengths_and_truncated_extensions`（643-667 行）覆盖缺失 vs 不一致分离、跨上下文 UA / 次级 HTTP UA 校验及截断/奇数字节 TLS ClientHello 拒绝；④ 核对 ALPN 编码真实性：`tests/unit/test_t068_fingerprint_verification.py:180-181,412-413` 中 `alpn_list = b"\x02h2\x08http/1.1"` 总长为精确 `3 + 9 = 12` 字节，`alpn_payload = struct.pack("!H", len(alpn_list)) + alpn_list` 与 RFC 7301 线格式及 `parse_tls_client_hello` 严格长度校验完全一致。
- `t068_test_f002`（minor）→ **已消除**：核实 `tests/e2e/test_t068_fingerprint_gate_e2e.py:146-156` 在篡改 `libGLESv2.so` 后重置 `adapter._binary_ready = False` 并重入真实 Docker `ensure_runtime_cache(need_geoip=False)` 容器路径断言 `DockerSandboxError`（193-195 行恢复后复验通过）；`tests/unit/test_t068_engine_artifact_pinning.py:132-157` 增补 `--version` 输出不匹配（`"Chromium 145.0.0.0\n"`）触发 `EngineArtifactError(code="version_probe_mismatch")` 单测（仅在外部 OS `subprocess.run` 边界注入 `--version` 返回值，因 macOS 宿主机无法直接 `execve` 通过 ELF aarch64 头校验的 Linux 二进制，真实 Linux ELF `--version` 探针已由 Docker E2E 与 `cache_init` 实跑覆盖）；`tests/unit/test_t068_engine_artifact_pinning.py:300-310` 增补 `BrowserRunner.resolve_engine_binary()` 拒绝损坏非 ELF `chrome` 与 `latest_version_linux-arm64` 自动更新 marker（`auto_update_marker_present`）单测。

### 本轮新发现

Round 2 零新 finding。

## 结论

- 前轮 finding 复核：`t068_test_f001`（minor）已消除；`t068_test_f002`（minor）已消除。
- 改测方向复核：无「迁就实现」改测（`tests/unit/test_a26_browser_image_modules.py` 与 `tests/unit/test_refactor_behavior_equivalence.py` 维持 Round 1 合法整体替换结论，本轮新增测试均严格断言修复后生产契约与负向拒绝路径）。
- 本轮新发现：0 条（Round 2 零新 finding）。
- 独立复跑与证据核对：
    - 定向单测复跑：`tests/unit/test_t068_engine_artifact_pinning.py`、`tests/unit/test_t068_fingerprint_verification.py`、`tests/unit/test_a26_browser_image_modules.py`、`tests/unit/test_refactor_behavior_equivalence.py`、`tests/unit/test_repo_hygiene.py` 共 42 passed（3.99s）。
    - 真实 Docker E2E 复跑（最新重建镜像 `sha256:f6621ccd52a99831406b64719bf6a30c9b727ade1fcb23b4fc2bd86f0b0672a7` + stream `sha256:30ca77f8b40f8cb388c04f02e30cabfb9267c0df46c0ae63dad2092333e11f28`）：`tests/e2e/test_t068_fingerprint_gate_e2e.py`（2 项）与 `tests/e2e/test_supervisor_cache_initialization_e2e.py`（1 项）共 3 passed（33.21s）。
    - 镜像源码一致性：实测 `browser_runtime` 镜像内 `engine_artifacts.py`、`runtime_agent/runner.py`、`fingerprint_verification/` 7 个模块与 `supervisor_runtime` 镜像（`sha256:197e57f79adcaf60cedaf5ef192fe7e998b5006c46f8b7d04d5ba2277d98a70a`）内 `engine_artifacts.py`、`supervisor/{container_spec,docker_adapter,runner}.py` 的 SHA-256 与 `<worktree>` 完全一致。
    - R2 门禁与实测证据：`.scratch/t068/gate_evidence_r2/manifest.json` 及 `junit/*.xml` 显示 `protocol_drift_check` / `requirements_check` / `design_lint` / `design_check` / `frontend_build` 均 exit 0，`contract` 257 passed / 1 skipped（258 tests），`integration` 181 passed / 18 skipped（199 tests），`frontend_test` 81 文件 623 passed，`e2e_targeted.xml` 3 passed；`unit.xml` 2073 tests 中 2067 passed / 5 skipped / 1 failed（仅范围外 `main` 基线遗留 `tests/unit/test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip`）；`manifest.json` 中 `real_engine` 因未注入 `CBROWSER_PROBE_TEST_IMAGE` 退出 1，独立执行的 `.scratch/t068/real_engine_r2/evidence.json` + `probe.xml` 为 `all_passed=true`（2 passed）。`.scratch/t068/evidence/` 14 份证据文件 SHA-256 与 `docs/tasks/t068_profile_fingerprint_verification/measurement_report.md` §7 逐一完全匹配。
- 未进表的提示：无新增范围外提示（Round 1 记录的 `main` 基线 `test_t060_gate_boundaries.py`、`findings.py` 重复编号 `d037`/`d038` 与 `measurement_report.md` §6 如实声明的未验证跨版本升级/x64 解压边界延续成立）。
- 总体判断：Round 1 两项 minor finding 均已从根因补测消除，新增测试无危险模式，Round 2 零新 finding，4 条 AC 测试与真实 Docker/Chrome/引擎及本地证据均经独立复核通过，判定 PASS。
- 系统性 follow-up：同 Round 1（无新增）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。独立复跑最新镜像上 `tests/e2e/test_t068_fingerprint_gate_e2e.py::test_ac001_ac002_ac006_real_engine_multicontext_baseline_and_drift_gate` 在真实 Docker/Xvfb/`chromium-146.0.7680.177.3` 容器内对 `prof-e2e-01` v1 重复测量并定位 `canvas2d` 等漂移；`tests/unit/test_t068_fingerprint_verification.py` 直接调用 `aggregate_samples` 与 `compare_reports` 验证样本缺失（`missing_measurement`）、空 `metrics={}` 护栏与 `expected_unsupported_context=10` 区分；`.scratch/t068/evidence/` 14 份证据 SHA-256 与 `measurement_report.md` §7 逐一匹配（`diff_seed_drift.json` 含 16 处可定位漂移）。
- AC-002：TICK-VALID，re_verified。独立复跑 E2E 与 unit 证实 main/iframe 全 18 项 API 与 worker/service_worker（13 `ok` + 5 `unsupported_context`）及 `worker_fetch`/`sw_fetch` 不含 `sec-ch-ua-platform` 的完整矩阵；默认严格模式因 `ja3_raw` 非确定方差 `blocked`，显式批准 `tls_extension_shuffle_via_ja4=True` 后同制品重复 `approved`；单样本 HTTP 缺失/波动、`candidate_notls`（`inconclusive:tls_capture`）、空 `metrics` 与 seed 漂移均 `blocked`，且 `ignore_stateful_storage_usage` 仅放行同 `quota`。
- AC-003：TICK-VALID，re_verified。独立复跑 `tests/unit/test_t068_engine_artifact_pinning.py`（8 项全过，含真实 `scripts/deploy.sh` 拦截损坏缓存与绕过环境、`DockerAdapter` 注入脚本子进程、`BrowserRunner.resolve_engine_binary()` 拒绝非 ELF/marker、`--version` 失配 `version_probe_mismatch`、ADR 021 `0.6.4` 与 15 文件摘要锁定）、`tests/e2e/test_t068_fingerprint_gate_e2e.py::test_ac003_cache_init_and_runner_pinning_fail_closed`（含损坏 `libGLESv2.so` 重入真实容器 `ensure_runtime_cache` 失败闭环）及 `tests/e2e/test_supervisor_cache_initialization_e2e.py`（1 项全过），且 `engine_artifacts.py` 与 `measurement_report.md` 如实分层说明下载层 Ed25519 与解压件仓库 SHA-256 清单。
- AC-006：TICK-VALID，re_verified。独立复跑 `test_t068_fingerprint_verification.py` 与 `test_t068_fingerprint_gate_e2e.py` 验证受控 HTTPS 下真实 BoringSSL `ClientHello` 解析（ALPN 线长 12 字节真实、GREASE 过滤、截断/奇数字节返回 `None`、`ja4` 收敛双值、`ja3_sorted` 稳定、`ja3_raw` 逐连接变化），`consistency.verdict == "consistent"` 与 `tls_status == "verified"` 且绑定 `engine_build`/`binary_sha256`/`config_version`/`probe_version`；真实 `--no-tls` 容器返回 `inconclusive` 并阻断升级；跨上下文 UA、次级 HTTP 请求类 UA 与 `sec-ch-ua-platform` 篡改均判 `inconsistent`，全程不引用任何厂商通过率。

coverage = 4 / 4

reviewed_scope: f71e97eb625cd280
verdict: PASS

## Round 3 (2026-11-14T01:30:53+08:00)

- round：3
- reviewed_at：2026-11-14T01:30:53+08:00
- target：`git -C '<worktree>' diff c5f83296ece80a9a0ed9f1e48d957ce332f858c4`

### 本轮变更核验（`t068_code_f005` 补测）

- 核实 `tests/unit/test_t068_fingerprint_verification.py:669-673` 新增断言真实触达生产逻辑且无危险模式：
    - 第 670–672 行直接导入并调用生产函数 `cbrowser.fingerprint_verification.tls_capture._alpn_tag`，断言 `_alpn_tag([""]) == "00"`，精确命中 `src/backend/cbrowser/fingerprint_verification/tls_capture.py:36` 的空串兜底分支（防止第 44 行 `encoded[0]` 越界 `IndexError`）；
    - 第 673 行构造合法 ClientHello 帧内嵌零长 ALPN 条目（`0x0010` 扩展载荷 `b"\x00\x01\x00"`，`alen=1`、`plen=0`），调用生产函数 `parse_tls_client_hello` 并严格断言 `is None`，直接命中 `tls_capture.py:156` 的 `plen == 0` 拒绝分支；
    - 危险模式扫描：无 mock、无恒真断言、无条件跳过、无断言弱化（严格 `== "00"` 与 `is None`）、无 `.skip` / `# type: ignore`。

### 本轮新发现

Round 3 零新 finding。

## 结论

- 前轮 finding 复核：Round 1 `t068_test_f001`、`t068_test_f002`（minor）与 Round 2 零新 finding 结论维持有效；针对 Round 2 code 轴 `t068_code_f005` 的补测已核实通过。
- 改测方向复核：无「迁就实现」改测（仅在 `test_parse_tls_client_hello_rejects_odd_lengths_and_truncated_extensions` 末尾追加零长 ALPN 负例，未修改既有断言）。
- 本轮新发现：0 条（Round 3 零新 finding）。
- 独立复跑与证据核对：
    - 定向单测复跑：`tests/unit/test_t068_engine_artifact_pinning.py`、`tests/unit/test_t068_fingerprint_verification.py`、`tests/unit/test_a26_browser_image_modules.py`、`tests/unit/test_refactor_behavior_equivalence.py`、`tests/unit/test_repo_hygiene.py` 共 42 passed（4.78s）。
    - 真实 Docker E2E 复跑（最新镜像 `sha256:cf7a4dd7383e3c2c1aab2f2a0c38a437ba9bbbcf510a39ca077b4296fd46b1b4` + stream `sha256:30ca77f8b40f8cb388c04f02e30cabfb9267c0df46c0ae63dad2092333e11f28`）：`tests/e2e/test_t068_fingerprint_gate_e2e.py`（2 项）与 `tests/e2e/test_supervisor_cache_initialization_e2e.py`（1 项）共 3 passed（30.74s）。
    - 镜像源码一致性：实测最新 `browser_runtime` 镜像内 `tls_capture.py`（SHA-256 `73434ac72b71825af75ee3b3ca50a6fbe9b40060f7426960af25631e2381d6f5`）及 `fingerprint_verification/` 其余 6 模块、`engine_artifacts.py`、`runtime_agent/runner.py`，与 `supervisor_runtime` 镜像（`sha256:197e57f79adcaf60cedaf5ef192fe7e998b5006c46f8b7d04d5ba2277d98a70a`）内 `engine_artifacts.py`、`supervisor/{container_spec,docker_adapter,runner}.py` 的 SHA-256 均与 `<worktree>` 完全一致。
    - 本地实测证据核对：`.scratch/t068/evidence/` 下 14 份证据文件（4 份报告、4 份 diff JSON、4 份 diff Markdown、2 份配置快照）逐一校验 SHA-256 与 `docs/tasks/t068_profile_fingerprint_verification/measurement_report.md` §7 完全一致。
- 未进表的提示：无新增范围外提示（Round 1 记录的 `main` 基线 `test_t060_gate_boundaries.py`、`findings.py` 重复编号 `d037`/`d038` 与 `measurement_report.md` §6 如实声明的未验证跨版本升级/x64 解压边界延续成立）。
- 总体判断：Round 3 新增测试真实触达生产 `tls_capture.py` 零长 ALPN 拒绝与 `_alpn_tag` 空串防护路径且无危险模式，Round 3 零新 finding，42 项单测与 3 项最新镜像真实 Docker E2E 独立复跑全过，14 份证据与镜像源码 SHA-256 完全一致，判定 PASS。
- 系统性 follow-up：同 Round 1（无新增）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。独立复跑最新镜像 `sha256:cf7a4dd7383e3c2c1aab2f2a0c38a437ba9bbbcf510a39ca077b4296fd46b1b4` 上 `tests/e2e/test_t068_fingerprint_gate_e2e.py::test_ac001_ac002_ac006_real_engine_multicontext_baseline_and_drift_gate` 在真实 Docker/Xvfb/`chromium-146.0.7680.177.3` 容器内对 `prof-e2e-01` v1 重复测量并定位 `canvas2d` 等漂移；`tests/unit/test_t068_fingerprint_verification.py` 直接调用 `aggregate_samples` 与 `compare_reports` 验证样本缺失（`missing_measurement`）、空 `metrics={}` 护栏与 `expected_unsupported_context=10` 区分；`.scratch/t068/evidence/` 14 份证据 SHA-256 与 `measurement_report.md` §7 逐一匹配（`diff_seed_drift.json` 含 16 处可定位漂移）。
- AC-002：TICK-VALID，re_verified。独立复跑 E2E 与 unit 证实 main/iframe 全 18 项 API 与 worker/service_worker（13 `ok` + 5 `unsupported_context`）及 `worker_fetch`/`sw_fetch` 不含 `sec-ch-ua-platform` 的完整矩阵；默认严格模式因 `ja3_raw` 非确定方差 `blocked`，显式批准 `tls_extension_shuffle_via_ja4=True` 后同制品重复 `approved`；单样本 HTTP 缺失/波动、`candidate_notls`（`inconclusive:tls_capture`）、空 `metrics` 与 seed 漂移均 `blocked`，且 `ignore_stateful_storage_usage` 仅放行同 `quota`。
- AC-003：TICK-VALID，re_verified。独立复跑 `tests/unit/test_t068_engine_artifact_pinning.py`（8 项全过，含真实 `scripts/deploy.sh` 拦截损坏缓存与绕过环境、`DockerAdapter` 注入脚本子进程、`BrowserRunner.resolve_engine_binary()` 拒绝非 ELF/marker、`--version` 失配 `version_probe_mismatch`、ADR 021 `0.6.4` 与 15 文件摘要锁定）、`tests/e2e/test_t068_fingerprint_gate_e2e.py::test_ac003_cache_init_and_runner_pinning_fail_closed`（含损坏 `libGLESv2.so` 重入真实容器 `ensure_runtime_cache` 失败闭环）及 `tests/e2e/test_supervisor_cache_initialization_e2e.py`（1 项全过），且 `engine_artifacts.py` 与 `measurement_report.md` 如实分层说明下载层 Ed25519 与解压件仓库 SHA-256 清单。
- AC-006：TICK-VALID，re_verified。独立复跑 `test_t068_fingerprint_verification.py` 与 `test_t068_fingerprint_gate_e2e.py` 验证受控 HTTPS 下真实 BoringSSL `ClientHello` 解析（ALPN 线长 12 字节真实、零长 ALPN 返回 `None`、`_alpn_tag([""]) == "00"`、GREASE 过滤、截断/奇数字节返回 `None`、`ja4` 收敛双值、`ja3_sorted` 稳定、`ja3_raw` 逐连接变化），`consistency.verdict == "consistent"` 与 `tls_status == "verified"` 且绑定 `engine_build`/`binary_sha256`/`config_version`/`probe_version`；真实 `--no-tls` 容器返回 `inconclusive` 并阻断升级；跨上下文 UA、次级 HTTP 请求类 UA 与 `sec-ch-ua-platform` 篡改均判 `inconsistent`，全程不引用任何厂商通过率。

coverage = 4 / 4

reviewed_scope: 61a38f1d38c2afba
verdict: PASS
