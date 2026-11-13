# Task review t068（reviewer_focus: 代码）

- task：`t068_profile_fingerprint_verification`
- spec：`docs/tasks/t068_profile_fingerprint_verification/task.md`
- diff_anchor：`c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- target：`git -C '<worktree>' diff c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- round：1
- reviewed_at：2026-11-14T00:48:59+08:00

reviewed_scope: e91443e8fc8639b8

## Findings

### t068_code_f001 - 多样本聚合 HTTP 请求头仅取末样本，吞掉部分缺测与样本间漂移

- 严重度：important
- 锚点：AC-001（「产出可定位 API/请求层的差异报告，缺测和不支持上下文明确区分，不作为无漂移」）、AC-002（「有未经批准的漂移、未测指标或不确定结果时阻断直接升级...非确定性指标先报告重复采样分布」）
- 位置：`src/backend/cbrowser/fingerprint_verification/probe_collector.py:353-360`、`src/backend/cbrowser/fingerprint_verification/comparator.py:223-250`
- 问题：`aggregate_samples` 对 JS 指标（`probe_collector.py:283-351`）逐样本检查 `status != "ok"` 标 `missing` 并以 `unique_values` 标记 `non_deterministic`，但对 `http_headers`（`probe_collector.py:353-360`）仅取最后一个非空样本 `observed[-1]`，既未检查 `len(observed) == len(samples)`（部分样本缺测请求类），也未检查多种样本之间同一请求类的请求头集合是否一致。在内存中以真实 `baseline.json` 配置构造 2 样本实跑复现（`aggregate_samples` + `compare_reports`）：① 当样本 0 缺失 `main_after_ch`（模拟 `Critical-CH` 重试偶发未触发）而样本 1 正常时，`compare_reports(..., approved_rules={"tls_extension_shuffle_via_ja4": True})` 输出 `upgrade_decision="approved"`、`missing_count=0`、`diffs=[]`；② 当样本 0 的 `main_after_ch["sec-ch-ua-platform"]` 为 `"Linux"` 而样本 1 为 `"Windows"` 时，同组比对同样输出 `upgrade_decision="approved"`、`diffs=[]` 且 `evaluate_tls_ua_ch_consistency` 判 `consistent`。
- 建议：在 `aggregate_samples` 中为每个请求类记录采样完整性（`len(observed) == len(samples)`）与去重采样分布（`unique_values` / `determinism`）；在 `compare_reports` 中对部分样本缺测（`missing_measurement`）及未经批准的样本间请求头方差（`non_deterministic_variance`）默认阻断，保留 `http_headers[req_cls]` 兼容仅限全样本完整且一致时，或同步携带每请求类的采样元数据供比对器消费。

### t068_code_f002 - 一致性评估跨上下文校验不完整、部分缺测被误标不一致及存在死变量

- 严重度：minor
- 锚点：行为缺陷（状态分类混淆与冗余存储）及 AC-006 跨层比对完整性
- 位置：`src/backend/cbrowser/fingerprint_verification/consistency.py:62,69-149`
- 问题：① 第 62 行初始化 `js_ch_platforms: dict[str, Any] = {}`，第 91 行写入后从未被读取（dead store）；② 第 69 行仅当 `userAgent` 的 `status != "ok"` 时记录 `"missing"`，若 `userAgent` 正常而 `platform`/`uaDataLow`/`uaDataHigh` 处于 `missing`/`error` 状态，`canonical_value` 为 `None` 会落入第 84-110 行被判为 `"inconsistent"` 而非 `"missing"`，导致 `verdict` 变成 `"inconsistent"` 而非 `"inconclusive"`；③ 第 61 行收集了四个上下文的 `js_ua_values`，但第 130 行只比较 `js_ua_values.get("main")` 与 HTTP `main_after_ch`，未核对 `iframe`/`worker`/`service_worker` 与 `main` 的 `userAgent` 是否一致，也未检查 `iframe_doc`/`main_fetch`/`worker_fetch`/`sw_fetch` 的 `User-Agent` 头。
- 建议：移除未使用的 `js_ch_platforms`；对 `platform`/`uaDataLow`/`uaDataHigh` 先判定 `status != "ok"` 记 `"missing"`；补充四上下文间 `userAgent` 与各 HTTP 请求类 `User-Agent` 的交叉校验。

### t068_code_f003 - `parse_tls_client_hello` 解析奇数字节或截断扩展时可抛出 `struct.error`

- 严重度：minor
- 锚点：边界条件（畸形/截断 ClientHello 输入未按契约返回 `None`）
- 位置：`src/backend/cbrowser/fingerprint_verification/tls_capture.py:73-76,96-143`
- 问题：`parse_tls_client_hello` 在第 49-95 行对短记录返回 `None`，但在遍历 `ciphers_raw`（第 73 行）、`supported_groups`（第 115 行）、`signature_algorithms`（第 124 行）、`supported_versions`（第 140 行）时未校验待解包字节长度为偶数，且第 96-99 行未校验 `offset + elen <= ext_end`。当收到 `cs_len` 为奇数或 `elen` 导致 `edata` 截断为奇数长度的畸形包时，`struct.unpack("!H", ...)` 会抛出未捕获 `struct.error` 而非返回 `None`。
- 建议：校验 `cs_len` 为偶数、`offset + elen <= ext_end`，以及各 16-bit 扩展切片长度为偶数，不满足则返回 `None`。

### t068_code_f004 - `compare_reports` 未防空 `metrics` 字典且 `probe_collector.py` 存在冗余赋值

- 严重度：minor
- 锚点：边界条件与死代码（空测量矩阵护栏缺失、无用变量构造）
- 位置：`src/backend/cbrowser/fingerprint_verification/comparator.py:88-95`、`src/backend/cbrowser/fingerprint_verification/probe_collector.py:489-497`
- 问题：① `compare_reports` 在第 209 行显式拒绝对空 `http_headers` 放行，但第 88-90 行当输入双方均被截断为空 `metrics={}`（且 `http_headers`/`tls_evidence` 有数据时），`all_keys` 为空集合，循环零次且 `missing_count=0`，不会阻断；② `probe_collector.py:490-496` 在 `except EngineArtifactError` 分支构造局部 `engine_artifact` 字典后紧接 `raise EngineArtifactError(...)`，该字典从未被使用。
- 建议：在 `compare_reports` 中对空 `metrics` 或缺失预期 4x18 上下文键显式按 `missing_measurement` 阻断；删除 `probe_collector.py:490-496` 未使用的 `engine_artifact` 赋值。

## 结论

- 本轮新发现：4 条（1 important、3 minor）。
- 未进表的提示：
    - 文件过大（物理行数 `wc -l`，降级不进 finding 表）：新建 `src/backend/cbrowser/engine_artifacts.py`（599 行）、`src/backend/cbrowser/fingerprint_verification/comparator.py`（425 行）、`src/backend/cbrowser/fingerprint_verification/probe_collector.py`（604 行）、`src/backend/cbrowser/fingerprint_verification/tls_capture.py`（707 行，含约 307 行内嵌 JS/HTML 探针模板）；既有超 800 行且本轮净增行的文件：`src/backend/cbrowser/supervisor/docker_adapter.py`（2683 行）、`scripts/deploy.sh`（1044 行）（`src/backend/cbrowser/runtime_agent/runner.py` 1132 行但本轮净减行，不命中）。测试文件中 t068 新增与改动均低于 600 行阈值。
    - 圈复杂度（近似 McCabe ≥ 10，降级不进表；`aggregate_samples` 因触发功能缺失另立 `t068_code_f001`）：`compare_reports`（80）、`parse_tls_client_hello`（61）、`evaluate_tls_ua_ch_consistency`（49）、`aggregate_samples`（45）、`verify_extracted_engine_cache`（28）、`DockerAdapter.__init__`（24）、`check_forbidden_engine_env`（22）、`start_browser_container`（22）、`_aggregate_tls_samples`（20）、`measure_profile_with_browser_runner`（15）、`collect_offline_font_evidence`（15）、`classify_http_records`（14）、`engine_artifacts.main`（12）、`TLSObservingProbeServer.__enter__`（11）、`render_diff_markdown`（10）、`do_GET`（10）。
    - 范围外基线与已批准边界：
        - 既有 main 基线失败（非本 task 引入，不进 finding 表、不据此 FAIL）：`unit` 中的 `test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip`（核对基线 `c5f8329` 原文确认其未初始化 `harness.data_dir`）；全量 `e2e` 11 项失败（`test_artifact_download_chain_e2e`、`test_profile_preview_e2e`×2、`test_browser_runtime_e2e`×3、`test_frontend_app_e2e`×4、`test_stream_runtime_e2e`）。`t068` 自身 13 项 unit 与 2 项真实 Docker E2E 在门禁与独立复跑中全通过。
        - 已获批准边界：本机仅有一套已获准 `linux-arm64` 制品（ADR 021 锁 `cloakbrowser==0.6.4` / `146.0.7680.177.3`），跨版本真实放行、`linux-x64` 解压件摘要与第三方检测站均未验证并在 `measurement_report.md` §6 与 `TRUST_SOURCE_X64_ARCHIVE_ONLY` 如实标明；已核对 `.scratch/t068/evidence/` 下 14 份证据文件 SHA-256 与 `measurement_report.md` §7 完全一致，且 `gate_evidence/manifest.json`（run_id `5c22ebc247cc414eb849078dde924af1`）、`junit/*.xml`（contract 258、unit 2069、integration 199、e2e 103）、`logs/*.log` 实数一致。
        - 已知工具链异常与既有文档格式漂移：`findings.py new` 因 main 分支既有重复编号 `d037`/`d038` 拒绝分配，未手工建 `dNNN`、未改工具链，`task.md` 未知契约清单已完整回填结论无 `UNVERIFIED` 残留；`md_format.py --check` 仅对历史旧文件（`docs/specs/fingerprint_platform.md` 及 t051–t059 旧文档）报格式漂移，t068 新增及修改文档格式全部干净。
- 总体判断：FAIL。AC-003 制品三处 SHA-256 校验/防绕过与 AC-006 本地 TLS/UA/CH 一致性绑定实现扎实，但 `t068_code_f001` 证实 `aggregate_samples` 聚合重复采样的 `http_headers` 时仅取 `observed[-1]`，导致部分样本缺测请求类或样本间请求头漂移被静默放行，修复并补齐验证前阻断 PASS。
- 系统性 follow-up：无（`t068_code_f001..f004` 均在本 task 交付模块内直接修复）。

### 七视角检查

- 安全：核对 `verify_extracted_engine_cache` 的 symlink 拒绝、`relative_to` 目录逃逸防护、ELF 架构头与 15 文件 SHA-256、`enforce_pinned_engine_env` 禁用绕过变量与自动更新 marker 拒绝、`BrowserRunner._browser_environment` 剥离绕过环境变量并强制 `CLOAKBROWSER_AUTO_UPDATE=false`、`sanitize_config_summary` 不泄漏代理凭据、`tls_capture` 仅监听 `127.0.0.1` 临时自签证书且不落盘私密，未发现注入、越权或家目录路径泄漏。
- 正确性：核对三处制品固定校验链路与 `compare_reports` 对缺测/上下文翻转/未批准方差/HTTPS 不可采样的阻断逻辑，确认 `t068_code_f001` 请求层多样本聚合漏洞及 `t068_code_f002`/`f003`/`f004` 边界处理缺陷。
- 契约与 Breaking：核对 `compose.yaml` 新增 `CLOAKBROWSER_AUTO_UPDATE`/`CBROWSER_ENGINE_BUILD`/`CBROWSER_ENGINE_BINARY_SHA256`、`deploy.sh` release manifest `engine` 块、`browser_command(..., engine_build=...)`、`cache_init_environment(..., engine_build=...)` 及双 Dockerfile/dockerignore 白名单，现有相关单测与契约（含 `test_t027_release_controller.py`、`test_a26_browser_image_modules.py`、`test_runtime_persistence_guards.py`、`test_refactor_behavior_equivalence.py`）独立重跑 100+24 项全部通过。
- 性能与资源：核对 `measure_profile_with_browser_runner` 每样本独立 `BrowserRunner` 启动/停止、`pulseaudio --kill`、临时工作目录与字体软链 `finally` 清理，以及 `TLSObservingProbeServer.__exit__` 关闭服务器并清理证书临时目录；核对 `_ProbeHTTPServer.get_request` 在 accept 主循环做 5s 超时 `MSG_PEEK` + `wrap_socket`（本地单浏览器探针可接受）。
- 架构与可维护性：`engine_artifacts.py` 作为唯一权威清单供 `deploy.sh`、Supervisor `cache_init` 与 `BrowserRunner` 复用（lazy import `cloakbrowser` 避免侵入 `supervisor_runtime` 镜像），`fingerprint_verification/` 分离采集/一致性/对比/CLI 四层；文件规模与高圈复杂度函数见上方提示。
- 健壮性与可观测：核对 `BrowserRunner` 与 `DockerAdapter` 在制品损坏/绕过变量/自动更新 marker 下的 fail-closed 退出路径与稳定错误码、`aggregate_samples` 对探针超时的降级标记（`status="error"`）；请求头部分缺测与一致性缺测分类误标见 `t068_code_f001`/`f002`。
- 测试、文档与规格：核对 `docs/specs/engine_upgrade_fingerprint_gate.md`、`docs/specs_index.md`、`docs/blueprint/{testing,security,decisions}.md`（ADR 032）、`measurement_report.md`、`task.md`（无 `UNVERIFIED` 残留）及整体替换 `test_container_spec_cache_specs`/`test_browser_image_ships_only_runtime_closure` 的语义理由，实现与文档表述一致；`t068_code_f001` 为实现与 AC-001/AC-002 请求层语义的具体差距。

### AC 复验方式

- AC-001：TICK-VOID，re_verified。`probe_collector.py:353-360` 聚合多样本 `http_headers` 仅取 `observed[-1]`，复现证实部分样本缺失 `main_after_ch` 时 `compare_reports` 仍返回 `upgrade_decision="approved"`、`missing_count=0`，未完全守住请求层缺测不作无漂移契约（见 `t068_code_f001`）。
- AC-002：TICK-VOID，re_verified。四上下文矩阵与 JS/TLS 非确定分布阻断已实现，但 `probe_collector.py:353-360` 对请求层多样本方差仅保留末样本并丢弃样本间漂移，复现证实单样本请求头漂移仍输出 `approved`（见 `t068_code_f001`）。
- AC-003：TICK-VALID，re_verified。核查 `engine_artifacts.py`、`scripts/deploy.sh:356-385,807,869`、`compose.yaml:127-129`、`docker_adapter.py:989-1065` 与 `runtime_agent/runner.py:216-232,460-487`，三处独立执行 15 文件 SHA-256/ELF/`--version` 校验并拒绝 `latest_version*` 与绕过环境变量，信任分层如实披露，独立重跑 `test_t068_engine_artifact_pinning.py` 与 `test_t027_release_controller.py` 全通过。
- AC-006：TICK-VALID，re_verified。核查 `tls_capture.py:47-208,579-684` 与 `consistency.py:32-208` 并核对 `evidence/baseline.json` 与 `evidence/candidate_no_tls.json`，一致性结论绑定真实 `ClientHello`（JA4/TLS 版本/ALPN）、HTTP 头与 `engine_build`/`binary_sha256`/`config_version`/`probe_version`，无本地 TLS 采集时标 `inconclusive` 且不引用厂商通过率，独立重跑 `test_t068_fingerprint_verification.py` 全通过。

coverage = 4 / 4

verdict: FAIL

## Round 2 (2026-11-14T01:14:02+08:00)

- target：`git -C '<worktree>' diff c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- round：2
- reviewed_at：2026-11-14T01:14:02+08:00

reviewed_scope: f71e97eb625cd280

### Findings

#### t068_code_f005 - `parse_tls_client_hello` 遇零长 ALPN 条目在 `_alpn_tag` 抛出 `IndexError`

- 严重度：minor
- 锚点：边界条件（畸形 ClientHello 扩展输入未按 `dict | None` 契约返回 `None`）
- 位置：`src/backend/cbrowser/fingerprint_verification/tls_capture.py:44,154-160`
- 问题：ALPN 扩展（`0x0010`）解析仅校验 `pos + plen > 2 + alen`，未校验 `plen > 0`（RFC 7301 `ProtocolName` 至少 1 字节）。当收到首条 `plen == 0` 的畸形 ALPN 负载（如 `b"\x00\x01\x00"`）时，第 158 行向 `alpn_protocols` 追加空字符串 `""`；第 200 行调用 `_alpn_tag([""])` 时 `all(ch.isalnum() for ch in "")` 虽为真但 `len("") < 2`，落入第 43-44 行对空串 `encoded = b""` 下标访问 `encoded[0]`，独立实测复现抛出未捕获 `IndexError: index out of range`（在 `_ProbeHTTPServer.get_request` 中将直接打断处理线程），而非返回 `None`。因真实 Chromium/BoringSSL 在受控本地 TLS 探针中不会发送零长 ALPN 条目，仅属解析器畸形输入加固项，定级 `minor`。
- 建议：在 `tls_capture.py:154-156` 增加 `if plen == 0 or pos + plen > 2 + alen: return None`，并在 `_alpn_tag` 兜底空字符串防护。

### 结论

- 前轮 finding 复核：
    - `t068_code_f001`（important）：**已消除**。核查 `src/backend/cbrowser/fingerprint_verification/probe_collector.py:351-405` 与 `src/backend/cbrowser/fingerprint_verification/comparator.py:19-47,243-323`：`aggregate_samples` 现按全部样本完整性（`sample_count > 0 and len(observed) == sample_count`）与去重分布（`unique_values`）构建 `http_header_samples[req_cls]`（`status="missing"` 或 `determinism="non_deterministic"` 时不再写入 `http_headers`）；`compare_reports` 通过 `all_req_classes` 合并 `http_headers` 与 `http_header_samples` 键集并由 `_http_summary_for_diff` 优先读取样本聚合元信息，显式阻断 `missing_measurement:http.<req_cls>` 与 `non_deterministic_variance:http.<req_cls>`。以 `baseline.json` 配置构造 2 样本场景独立内存实跑复现 Round 1 两条路径：① 样本 0 缺失 `main_after_ch` → `upgrade_decision="blocked"`（`missing_measurement:http.main_after_ch`、`consistency.verdict="inconclusive"`）；② 样本 0 的 `sec-ch-ua-platform` 漂移为 `"Linux"` → `upgrade_decision="blocked"`（`non_deterministic_variance:http.main_after_ch`、`consistency.verdict="inconsistent"`）。
    - `t068_code_f002`（minor）：**已消除**。核查 `src/backend/cbrowser/fingerprint_verification/consistency.py:61-252`：死变量 `js_ch_platforms` 已删除；`platform`（第 85-96 行）、`uaDataLow`（第 98-111 行）、`uaDataHigh`（第 113-132 行）均先校验 `status != "ok"` 标为 `"missing"` 产出 `"inconclusive"` 而非误判 `"inconsistent"`；第 134-139 行补充四上下文间 `userAgent` 交叉一致性校验（`js.cross_context`）；第 141-252 行补充 `http_header_samples` 缺测/样本方差判定（含 `main_reported_bad` 去重）及 `iframe_doc`/`main_fetch`/`worker_script`/`worker_fetch`/`sw_script`/`sw_fetch` 的 `User-Agent` 与可选 `Sec-CH-UA-Platform` 校验。
    - `t068_code_f003`（minor）：**已消除**。核查 `src/backend/cbrowser/fingerprint_verification/tls_capture.py:75,106,113,120,129,137,142,150,156,164`：`cs_len`/`glen`/`slen`/`vlen` 奇数字节校验、`offset + elen <= ext_end` 与各扩展子切片越界校验已全部补齐并返回 `None`。
    - `t068_code_f004`（minor）：**已消除**。核查 `src/backend/cbrowser/fingerprint_verification/comparator.py:10-12,125-128` 与 `src/backend/cbrowser/fingerprint_verification/probe_collector.py:488-493`：定义 `EXPECTED_METRIC_KEYS`（4×18=72 键）并入 `all_keys`，独立内存实跑确认双侧 `metrics={}` 输出 `upgrade_decision="blocked"`、`missing_count=72`；`probe_collector.py` 异常处理分支未使用的 `engine_artifact` 局部字典已删除。
- 本轮新发现：1 条（0 critical、0 important、1 minor：`t068_code_f005`）。
- 未进表的提示：
    - 文件过大（物理行数 `wc -l`，降级不进表；仅列本轮触及或新建实现文件）：`src/backend/cbrowser/engine_artifacts.py`（599 行）、`src/backend/cbrowser/fingerprint_verification/comparator.py`（497 行）、`src/backend/cbrowser/fingerprint_verification/probe_collector.py`（639 行）、`src/backend/cbrowser/fingerprint_verification/tls_capture.py`（733 行，含约 307 行内嵌 JS/HTML 探针模板）；超 800 行既有净增行文件：`src/backend/cbrowser/supervisor/docker_adapter.py`（2683 行）、`scripts/deploy.sh`（1044 行）（`src/backend/cbrowser/runtime_agent/runner.py` 1132 行仍净减行）。测试文件 `tests/unit/test_t068_fingerprint_verification.py` 增至 667 行（≥ 600 minor 阈值、未达 1200 important 阈值，同作降级提示）。
    - 圈复杂度（AST McCabe ≥ 10，降级不进表）：`compare_reports`（87）、`parse_tls_client_hello`（78）、`evaluate_tls_ua_ch_consistency`（77）、`aggregate_samples`（55）、`verify_extracted_engine_cache`（28）、`DockerAdapter.__init__`（24）、`check_forbidden_engine_env`（22）、`start_browser_container`（22）、`_aggregate_tls_samples`（20）、`collect_offline_font_evidence`（15）、`classify_http_records`（14）、`measure_profile_with_browser_runner`（14）、`engine_artifacts.main`（12）、`TLSObservingProbeServer.__enter__`（11）、`render_diff_markdown`（10）、`do_GET`（10）。
    - Round 2 变更范围与门禁复核：
        - `git diff` 覆盖 Round 1 修复及对应 unit 补强，未超出 task 范围；`git status --short` 无除 `review_code.md`/`review_test.md` 外的未跟踪交付文件。
        - 独立重跑 `tests/unit/test_t068_engine_artifact_pinning.py`、`tests/unit/test_t068_fingerprint_verification.py`、`tests/unit/test_a26_browser_image_modules.py`、`tests/unit/test_repo_hygiene.py`、`tests/unit/test_t051_generation_hygiene.py` 共 33 项全部通过。
        - 核对 `.scratch/t068/gate_evidence_r2/manifest.json`（`run_id=fdcc5d7518f247d7ac370846969305c3`、`cleanup_exit_code=0`，镜像 ID 与 `measurement_report.md` §1 一致）：`protocol_drift_check`、`requirements_check`、`contract`（257 passed / 1 skipped）、`integration`（177 passed / 18 skipped + 4 serial passed）、`design_lint`、`design_check`、`frontend_test`（81 文件 623 passed）、`frontend_build` 全过；`unit` 仅存在既有 `main` 基线失败 `test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip`（2003 passed + 64 serial passed）；`real_engine` 在无 `CBROWSER_PROBE_TEST_IMAGE` 默认套失败后，于 `.scratch/t068/real_engine_r2/evidence.json`（`probe.xml` 2/2 passed）单独验证通过；`.scratch/t068/gate_evidence_r2/junit/e2e_targeted.xml` 显示 3 项 t068/cache_init 真实 Docker E2E 全过（既有全量 E2E 11 项基线失败与本 task 无关）。
        - 逐一校验 `.scratch/t068/evidence/` 下 14 份证据文件（含新增 `http_header_samples` 的 `baseline.json` 等）SHA-256 与 `measurement_report.md` §7 完全一致；以实产 `baseline.json` 与 `candidate_same.json` 验证新实现下 strict=`blocked`（`non_deterministic_variance:tls.ja3_raw`）、approved=`approved`、`consistency="consistent"`。
        - 已获批准边界同 Round 1：本机仅一套 `linux-arm64` 制品（`146.0.7680.177.3`），`linux-x64` 标注 `TRUST_SOURCE_X64_ARCHIVE_ONLY`、跨版本真实放行与第三方检测站均未宣称通过。
- 七视角复扫：
    - 安全：新增/修改路径无注入、凭证泄漏或目录逃逸；三处制品校验与防绕过守卫未松动。
    - 正确性：Round 1 缺陷（`t068_code_f001..f004`）均已在实现层修正并经内存复现与单测验证；仅 `t068_code_f005` 零长 ALPN 边缘解析抛出 `IndexError`（`minor`）。
    - 契约与 Breaking：`http_header_samples` 为报告新增结构并保留完整 `http_headers`（仅全样本完整且确定时写入），`_http_summary_for_diff` 兼容旧格式单样本报告字典，无破坏性回归。
    - 性能与资源：`http_header_samples` 按样本数 O(N) 聚合与正则 JSON 序列化，本地 2–3 样本开销可忽略，未引入同步阻塞或资源泄漏。
    - 架构与可维护性：`probe_collector` → `consistency` / `comparator` 职责边界清晰，但 `compare_reports`、`parse_tls_client_hello`、`evaluate_tls_ua_ch_consistency`、`aggregate_samples` 圈复杂度均超过 50，建议后续迭代拆分（不阻断）。
    - 健壮性与可观测：缺失状态现准确区分 `missing`（`inconclusive`）与 `inconsistent`，空 `metrics={}` 与部分缺测 HTTP 请求类均 fail-closed 阻断。
    - 测试、文档与规格：`measurement_report.md` §7 SHA-256、门禁 R2 证据与源码现状完全吻合；4 条 AC 的 `- [x]` 勾选均有真实代码路径支撑。
- 总体判断：PASS。Round 1 的 1 条 important 与 3 条 minor finding 均已实质修复，Round 2 仅发现 1 条畸形零长 ALPN 边界 `minor`（`t068_code_f005`），无未解决 critical / important 缺陷。
- 系统性 follow-up：无（`t068_code_f005` 属单行边界加固，可在后续维护顺带修补；`main` 基线遗留见 `review_test.md`）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。核查 `probe_collector.py:281-405` 与 `comparator.py:10-47,125-323` 并以 `baseline.json` 内存构造部分缺测与空 `metrics` 场景实跑确认：4×18 上下文/指标、9 类 HTTP 请求头完整记录 `http_header_samples` 及 `unsupported_context`/`missing`/`error` 区分，部分样本缺测 `main_after_ch` 与空 `metrics={}` 均触发 `missing_measurement` 阻断升级，不作无漂移处理，33 项相关 unit 与 R2 证据链路一致。
- AC-002：TICK-VALID，re_verified。核查 `probe_collector.py:335-405`、`comparator.py:178-407` 并独立实跑确认：`context_matrix` 与 `context_matrix_diff` 覆盖 `main`/`iframe`/`worker`/`service_worker` 全量 72 项真实适用性，非确定 JS/HTTP/TLS 指标以分布记录；样本间 `sec-ch-ua-platform` 漂移触发 `non_deterministic_variance:http.main_after_ch` 阻断，raw `ja3` 默认阻断且仅显式批准 `tls_extension_shuffle_via_ja4` 才放行同制品重复，无虚构阈值放行。
- AC-003：TICK-VALID，re_verified。核查 `engine_artifacts.py`、`scripts/deploy.sh:356-385,807,869`、`compose.yaml:127-129`、`docker_adapter.py:989-1090` 与 `runtime_agent/runner.py:216-232,460-487`，三处独立校验 `146.0.7680.177.3` 15 文件 SHA-256/ELF/`--version` 并拒绝 `latest_version*` 与绕过变量，`linux-x64` 如实标 `TRUST_SOURCE_X64_ARCHIVE_ONLY` 拆解下载层 Ed25519 与解压件仓库清单信任来源；独立重跑 `test_t068_engine_artifact_pinning.py` 与 `test_a26_browser_image_modules.py` 全过且 R2 `e2e_targeted.xml` 真实容器 `cache_init` 通过。
- AC-006：TICK-VALID，re_verified。核查 `tls_capture.py:47-208,591-733` 与 `consistency.py:32-310` 并核对 R2 `baseline.json`、`candidate_no_tls.json` 及单测：`evaluate_tls_ua_ch_consistency` 现完整校验四上下文跨层 `userAgent`、全部 HTTP 请求类 `User-Agent`/样本方差与本地 TLS `ClientHello`（JA4/TLS 版本/ALPN），绑定 `engine_build`/`binary_sha256`/`config_version`/`probe_version`；缺失项准确归 `inconclusive`、无本地 TLS 采集标 `inconclusive` 且不引用厂商通过率。

coverage = 4 / 4

verdict: PASS

## Round 3 (2026-11-14T01:26:33+08:00)

- target：`git -C '<worktree>' diff c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- round：3
- reviewed_at：2026-11-14T01:26:33+08:00

reviewed_scope: 61a38f1d38c2afba

### Findings

Round 3 零新 finding。

### 结论

- 前轮 finding 复核：
    - `t068_code_f005`（minor）：**已消除**。核查 `src/backend/cbrowser/fingerprint_verification/tls_capture.py:35-44,154-160`：`_alpn_tag` 新增 `if not alpn_protocols or not alpn_protocols[0]: return "00"`，对空字符串与空列表直接返回 `"00"`，非空首协议经 `encode("ascii", "replace")` 后长度必 `>= 1`，不再在 `encoded[0]` / `encoded[-1]` 发生下标越界；`parse_tls_client_hello` 在 ALPN 扩展（`0x0010`）解析循环增加 `if plen == 0 or pos + plen > 2 + alen: return None`，按 RFC 7301 拒绝零长 `ProtocolName` 条目。独立内存构造 `ClientHello`（含 `b"\x00\x01\x00"` 与 `b"\x00\x04\x02h2\x00"` ALPN 负载）调用 `parse_tls_client_hello` 均返回 `None`、调用 `_alpn_tag([""])` 返回 `"00"`，合法 ALPN `b"\x00\x03\x02h2"` 仍正常解析并返回 `alpn=["h2"]` 与 `ja4`，不再抛出 `IndexError`。
- 本轮新发现：Round 3 零新 finding（0 critical、0 important、0 minor）。
- 未进表的提示：
    - 文件过大与圈复杂度（降级不进表，较 Round 2 仅 `parse_tls_client_hello` AST CC 78→79、`_alpn_tag` CC 7、`tests/unit/test_t068_fingerprint_verification.py` 667→673 行；`tls_capture.py` 维持 733 行，其余均同 Round 2）。
    - Round 3 变更范围、独立复跑与证据核对：
        - `git -C '<worktree>' status --short` 仅 `review_code.md`、`review_test.md` 为未跟踪文件，无未跟踪交付文件。
        - 独立复跑 `tests/unit/test_t068_engine_artifact_pinning.py`、`tests/unit/test_t068_fingerprint_verification.py`、`tests/unit/test_a26_browser_image_modules.py`、`tests/unit/test_repo_hygiene.py`、`tests/unit/test_t051_generation_hygiene.py` 共 33 项全部通过（4.84s）。
        - 核对镜像 `sha256:cf7a4dd7383e3c2c1aab2f2a0c38a437ba9bbbcf510a39ca077b4296fd46b1b4` 与 `measurement_report.md` §1 一致，容器内 `tls_capture.py` SHA-256（`73434ac72b71825af75ee3b3ca50a6fbe9b40060f7426960af25631e2381d6f5`）与 `<worktree>` 源码完全一致；`.scratch/t068/gate_evidence_r2/junit/e2e_targeted_r3.xml` 记录 3 项真实 Docker E2E 全过（30.815s，0 failures / 0 errors / 0 skipped）。
        - 逐一核对 `.scratch/t068/evidence/` 下 14 份证据文件（含 `2026-11-13T17:22:54+00:00` 最新生成报告与 diff 产物）实算 SHA-256 与 `measurement_report.md` §7 完全一致，且以该 4 份报告重算 `compare_reports` 与 `diff_*.json` 决策（`blocked` / `approved` / `blocked` / `blocked`）一致。
        - 已获批准边界同前：本机仅一套 `linux-arm64` 制品（`146.0.7680.177.3`），`linux-x64` 标注 `TRUST_SOURCE_X64_ARCHIVE_ONLY`、跨版本真实放行与第三方检测站均未宣称通过。
- 七视角复扫（Round 3 增量与回归）：
    - 安全：`_alpn_tag` 与 ALPN 长度校验对畸形 TLS ClientHello 负载 fail-closed 返回 `None`，未引入注入、路径或凭据泄漏；`test_repo_hygiene.py` 与 `test_t051_generation_hygiene.py` 均通过。
    - 正确性：`t068_code_f005` 已完全修复并经内存构造与单测验证，`parse_tls_client_hello` 全部扩展解析边界完整无越界或 `struct.error`/`IndexError`。
    - 契约与 Breaking：`parse_tls_client_hello` 对畸形零长 ALPN 返回 `None` 符合 `dict[str, Any] | None` 契约，合法握手解析行为无变化。
    - 性能与资源：增加常数级 `plen == 0` 与首元素判空检查，无额外内存或 I/O 开销。
    - 架构与可维护性：改动局限在 `tls_capture.py:35-44,154-160` 与对应单测，无跨层侵入。
    - 健壮性与可观测：本地 TLS `_ProbeHTTPServer.get_request` 不再因畸形零长 ALPN 引发 `IndexError` 中断线程。
    - 测试、文档与规格：`measurement_report.md` §1/§7、证据 SHA-256、`e2e_targeted_r3.xml` 与源码完全一致，4 条 AC 的 `- [x]` 勾选均有真实代码与证据支撑。
- 总体判断：PASS。Round 2 遗留的唯一 minor（`t068_code_f005`）已彻底修复，Round 3 零新 finding，无未解决 critical / important / minor 缺陷。
- 系统性 follow-up：无（`main` 基线遗留见 `review_test.md`）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。核查 `probe_collector.py:281-437` 与 `comparator.py:10-47,125-323` 并核对 R3 重建证据 `baseline.json` / `candidate_seed_drift.json` / `diff_seed_drift.json`：4×18 上下文/指标及 9 类 HTTP 请求头均以 `http_header_samples` 与状态标签区分 `ok`/`unsupported_context`/`missing`/`error`，缺测及 16 处漂移精确定位阻断，33 项相关 unit 与 `e2e_targeted_r3.xml` 一致。
- AC-002：TICK-VALID，re_verified。核查 `probe_collector.py:335-408`、`comparator.py:178-407` 并以最新证据重算 `compare_reports`：`context_matrix_diff` 覆盖 4 上下文 72 项真实适用性，非确定 JS/HTTP/TLS 指标先录分布，raw `ja3` 默认阻断，仅显式批准 `tls_extension_shuffle_via_ja4` 放行同制品重复，无虚构阈值放行。
- AC-003：TICK-VALID，re_verified。核查 `engine_artifacts.py`、`scripts/deploy.sh:356-385,807,869`、`compose.yaml:127-129`、`docker_adapter.py:989-1090` 与 `runtime_agent/runner.py:216-232,460-487`：三处独立校验 `146.0.7680.177.3` 15 文件 SHA-256/ELF/`--version` 并拒绝 `latest_version*` 与绕过变量，`linux-x64` 如实标 `TRUST_SOURCE_X64_ARCHIVE_ONLY`，独立重跑 `test_t068_engine_artifact_pinning.py` 与 `test_a26_browser_image_modules.py` 全过且 `e2e_targeted_r3.xml` 真实容器 `cache_init` 通过。
- AC-006：TICK-VALID，re_verified。核查 `tls_capture.py:35-235,591-733` 与 `consistency.py:32-310` 并独立实测畸形 ALPN 解析与最新证据 `baseline.json` / `candidate_no_tls.json`：零长 ALPN 不再崩溃，一致性结论绑定真实 `ClientHello`（JA4/TLS 版本/ALPN）、全量 HTTP 头与 `engine_build`/`binary_sha256`/`config_version`/`probe_version`，无本地 TLS 采集标 `inconclusive` 且不引用厂商通过率。

coverage = 4 / 4

verdict: PASS
