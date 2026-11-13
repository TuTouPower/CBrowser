---
tid: "t068"
slug: "profile_fingerprint_verification"
title: "本地指纹基线与引擎升级回归门禁"
status: "done"
branch: "t068_profile_fingerprint_verification"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "c5f83296ece80a9a0ed9f1e48d957ce332f858c4"
depends_on: ""
conflicts_with: "t062,t063,t065"
note: "p081 引擎升级工程门禁；p085 Persona、p086 预热自检已按用户要求取消，t071/t072 dropped"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-13 审阅修订：原 AC-004 转 t071 AC-001，AC-005 与自检部分转 t072；AC-006 仅保留本地 TLS/请求层证据，退休编号不复用。拒绝 t066↔t068 循环依赖，以现有 config version 解除耦合。

- 本次仅维护 backlog；不 start、不实现；旧归档来源只追加转办链，不改写历史。

- 调度字段经 task.py edit 写入；plan 的 runnable 只指依赖/冲突候选，不代表产品 BLOCKING 已解决。

- 调度依据：基线使用当前配置版本，无新身份模型依赖；引擎/Dockerfile/runner 与 t062/t063/t065 重叠；Persona/预热/用户自检已取消。

- 用户最新裁决：Persona/预热/用户自检取消，t071/t072 已 dropped，不转 pending；保留引擎升级工程门禁。

- 2026-11-13T20:36:00+08:00：进入 worktree `../CBrowser_t068`（分支 `t068_profile_fingerprint_verification`，基线 `main=c5f8329`，owner `muse-cloud-t068`，attempt 1，`execution_id=f08a59e0fe66490a8d076e9a72de4a85`）。`preflight t068 --owner-id muse-cloud-t068` 返回 `PASS（1 条警告：2 项 UNVERIFIED-SPIKE）`；`doctor_cmd`（`pytest .repo_template/tests -q --collect-only -m contract` 收集 258 项 + `md_kx`）通过。

- 工具链异常记录（不静默绕过，不改工具链）：尝试执行 `python3 .repo_template/scripts/findings.py new` 登记技术发现时失败退出，原因为基线分支 `main` 已存在历史重复编号（`d037` 同时存在 `d037_dockerignore_leaf_allowlists.md` 与 `d037_sqlite_extended_error_codes_and_log_safety.md`；`d038` 同时存在 `d038_deterministic_deployment_identity_and_media_pools.md` 与 `d038_target_engine_tab_visibility_unreliable.md`），触发 `_id_scan.py` 全仓重复校验拒绝分配新号。按仓规不手工绕过建 `dNNN` 文件，临时实验材料保留在 `.scratch/`，结论已完整回填 `task.md` 未知契约清单，并将在最终消息中如实向用户报告。

- 2026-11-13T20:45:00+08:00：完成两项技术 SPIKE 实测并消除 `UNVERIFIED-SPIKE`：① 核查 `cloakbrowser==0.6.4` 源码、对 `chromium-v146.0.7680.177.3` 执行 Ed25519 验签（`SHA256SUMS` + `SHA256SUMS.sig` 通过 `BINARY_SIGNING_PUBKEYS`）、计算本地唯一已获准 `linux-arm64` 二进制 `chrome` SHA-256（`3cf5231598c4fd44be1ed10c58cab4a1d59cd18b05a4800c73b946e0bfc4d34f`），并在容器内实测 `ensure_binary` 命中损坏非 ELF 伪文件与 `latest_version_<tag>` 标记时的绕过缺陷；② 在 `browser_runtime` 容器 + Xvfb + `chromium-146.0.7680.177.3` + 本地受控 TLS `ClientHello` HTTPS 服务完成 4 上下文矩阵、HTTP 头与 TLS JA3/JA4 重复采样（`.scratch/spike2_results.json`、`.scratch/spike2_followup.json`），验证 BoringSSL 扩展洗牌导致 `ja3` 每次握手不同而 `ja4` 收敛为 `{initial, resumption}` 稳定对、Worker/SW 仅部分 API 适用且不发 `Sec-CH-UA*`、复用 `user_data_dir` 时 `storageEstimate.usage` 变化。已准备运行 `--require-verified` 严格 preflight。

- 2026-11-13T21:00:00+08:00：严格 `preflight --require-verified --owner-id muse-cloud-t068` PASS（0 警告）。TDD 先红：新增 `test_t068_engine_artifact_pinning.py`（8 项）与 `test_t068_fingerprint_verification.py`（5 项）首次 11 failed，随后实现 `cbrowser/engine_artifacts.py`（批准制品清单 + Ed25519 下载信任说明 + 三处 SHA-256 校验 + 禁用自动更新/绕过）、`cbrowser/fingerprint_verification/`（TLS ClientHello JA3/JA4、四上下文探针、差异门禁、AC-006 一致性）并接线 `deploy.sh` / `compose.yaml` / `supervisor` / `runtime_agent` / 三份 Dockerfile。定向 13 passed。

- 删除旧测试理由：`test_refactor_behavior_equivalence.py::test_container_spec_cache_specs` 原样硬编码 5 键 `cache_init_environment` 输出，AC-003 改为钉死版本 + 禁自动更新后语义失效，整体删除并由 t068 新测试接替；`test_a26_browser_image_modules.py::test_browser_image_ships_only_runtime_closure` 原断言「镜像只 ship runtime import 闭包」，t068 离线探针包进入 Browser 镜像后语义失效，整体替换为 `test_browser_image_ships_runtime_closure_and_offline_probe` 并新增探针包存在断言，未就地改旧预期。

- 真实 Docker 测量：本机唯一已获准 `linux-arm64` 制品 `chromium-146.0.7680.177.3`（ADR 021 锁 `cloakbrowser==0.6.4`），三份镜像按本 worktree 源码重建为不可变 ID。实测 4 上下文矩阵（main/iframe 18 ok，worker/SW 13 ok + 5 unsupported）、TLS `ja4` 稳定两值 + `ja3` 逐连接洗牌、字体 Linux 命中 0、`consistency=consistent`。四场景门禁：strict 阻断 raw JA3 方差、显式批准规则后同制品重复通过、HTTP-only（TLS 不可判定）阻断、seed 漂移 16 处跨上下文阻断。完整证据与差异报告在 `.scratch/t068/evidence/`，入库摘要 `measurement_report.md`。

- 真实 E2E `tests/e2e/test_t068_fingerprint_gate_e2e.py` 2 passed（31.41s），覆盖 cache_init 真实 helper + 制品损坏/marker/绕过负向 + 四场景门禁。过程中修正 3 个根因：`libvk_swiftshader.so` 哈希手误（改为实测值并核对 15/15）、`tls_capture` 漏 `import socket`、`font_evidence` 混入随机临时路径（改 `fontconfig_present` 布尔）——均为根因修正，未弱化断言。

- 工具链异常（不静默绕过）：`findings.py new` 因 main 分支既有重复编号 `d037`/`d038` 拒绝分配，未手工建 `dNNN`；结论回填 `task.md` 未知契约清单并在最终消息报告。未改工具链。

- 全量门禁（证据模式，`CBROWSER_RUN_E2E=1`）：worktree 缺 `src/frontend/node_modules` 已以本地软链（gitignore）接主仓；unit suite 出现 2 项失败——`test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip` 为 main 既有基线失败（`GatewayTopologyHarness.data_dir`，`local_verify_evidence_wt` 同项已失败，本 task 未触碰相关文件），`test_a26` 为本 task 契约变更已整体替换并定向 74 passed 复验绿。E2E/真实引擎结果以 manifest 为准，不冒充全绿。

- 2026-11-14T01:10:00+08:00 Round 1 review 处置与复验：code 轴 FAIL（`t068_code_f001` important + 3 minor），test 轴 PASS（2 minor）。先撤回 `task.md` 全部 AC 打勾并按 6 条 finding 逐一从根因修复：① `probe_collector.py` 新增 `http_header_samples` 逐样本完整性与跨样本分布统计（部分缺测或样本间漂移不再覆写为末样本），清理 `measure_profile_with_browser_runner` 冗余 `engine_artifact` 赋值与未使用 import；② `comparator.py` 新增 `EXPECTED_METRIC_KEYS`（4×18）护栏防空 `metrics={}` 绕过，并基于 `_http_summary_for_diff` 阻断 HTTP 部分缺测（`missing_measurement`）与样本间请求头漂移（`non_deterministic_variance`）；③ `consistency.py` 删除死变量 `js_ch_platforms`，将 `platform`/`uaDataLow`/`uaDataHigh` 非 `ok` 正确归为 `missing`（`inconclusive`），补充四上下文 `userAgent` 交叉校验、全部次级 HTTP 请求类 `User-Agent` 校验及 `http_header_samples` 缺失/波动校验；④ `tls_capture.py` 补全 `parse_tls_client_hello` 记录/握手长度及各扩展偶数字节与越界检查（截断/奇数字节返回 `None`，不抛 `struct.error`），并修正测试 fixture 中 ALPN 长度 typo（11→12）；⑤ 增补单测（`test_t068_fingerprint_verification.py` 覆盖 `aggregate_samples`、comparator 边缘分支、consistency 与畸形 ClientHello；`test_t068_engine_artifact_pinning.py` 覆盖 `--version` 失配与 `BrowserRunner.resolve_engine_binary` 篡改/marker 拒绝）及 E2E `cache_init` 容器损坏负向路径；⑥ 重建 `browser_runtime` 镜像（`sha256:f6621ccd52a99831406b64719bf6a30c9b727ade1fcb23b4fc2bd86f0b0672a7`），重生成 `.scratch/t068/evidence/` 14 份证据并更新 `measurement_report.md` §7 SHA-256，复跑 `scripts/run_gates.sh`（`run_id=fdcc5d7518f247d7ac370846969305c3`）、`verify_image_packages.py`、`run_automation_probe.sh`（2 passed）及 t068/supervisor 定向 E2E（3 passed）后重新打勾 AC。

- 2026-11-14T01:22:00+08:00 Round 2 review 处置与复验：Round 2 code 轴 PASS（新发现 1 条 minor：`t068_code_f005`）、test 轴 PASS（0 新 finding）。为不遗留任何代码层面缺陷，撤回 AC 后修复 `t068_code_f005`：`tls_capture.py:35-44,154-160` 拒绝 ALPN 零长条目（`plen == 0` 返回 `None`）并在 `_alpn_tag` 防护空串；`tests/unit/test_t068_fingerprint_verification.py:669-673` 增补断言；重建 `browser_runtime` 镜像 `sha256:cf7a4dd7383e3c2c1aab2f2a0c38a437ba9bbbcf510a39ca077b4296fd46b1b4`，通过 `verify_image_packages.py`、128 项相关单测、3 项真实 Docker E2E（31.02s），重生成 14 份证据与 `measurement_report.md` §1/§7 后重新打勾 AC，提交 Round 3 复审。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-14T01:10:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t068_code_f001|important|已修|新增 `http_header_samples` 记录请求类采样完整性与去重分布，comparator 与 consistency 默认阻断部分缺测及样本间请求头波动|`probe_collector.py:353-433`, `comparator.py:19-40,248-323`, `consistency.py:142-182`|
|t068_code_f002|minor|已修|移除死变量 `js_ch_platforms`，缺失状态按 `missing` 归入 `inconclusive`，补齐跨上下文 JS UA 与次级 HTTP 请求类校验|`consistency.py:61-235`|
|t068_code_f003|minor|已修|`parse_tls_client_hello` 校验记录/握手长度及 16-bit 扩展偶数字节与越界，畸形包统一返回 `None`|`tls_capture.py:51-155`|
|t068_code_f004|minor|已修|`compare_reports` 以 `EXPECTED_METRIC_KEYS` 防空 `metrics` 漏检，并移除 `measure_profile_with_browser_runner` 冗余异常分支|`comparator.py:10-12,127`, `probe_collector.py:512-520`|
|t068_test_f001|minor|已修|增补直接调用 `aggregate_samples`（含缺失/错误与分布方差）及 `compare_reports` HTTP/字体/storage quota 边缘单测|`tests/unit/test_t068_fingerprint_verification.py:435-626`|
|t068_test_f002|minor|已修|增补 `version_probe_mismatch`、`BrowserRunner.resolve_engine_binary` 坏缓存/marker 单测及 E2E `cache_init` 容器负向路径|`tests/unit/test_t068_engine_artifact_pinning.py:132-160,295-307`, `tests/e2e/test_t068_fingerprint_gate_e2e.py:146-156`|

### Round 2 (2026-11-14T01:22:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t068_code_f005|minor|已修|拒绝 ALPN `plen == 0` 畸形条目并在 `_alpn_tag` 防护空串，补齐单测断言|`tls_capture.py:35-44,154-160`, `tests/unit/test_t068_fingerprint_verification.py:669-673`|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（4/4 AC）。本机在「只用已获准制品」约束下以同制品重复 + 受控输入漂移完成真实测量与默认阻断验证；跨版本真实放行如实列为未验证项。
- 测试：Round 2/3 最终源码通过 `verify_image_packages.py`（三镜像 exit 0）与 128 项相关单测+卫生/构建回归（含 t068 17 项单测、test_a26 替换与 test_repo_hygiene）；R1 修复后门禁（`.scratch/t068/gate_evidence_r2/manifest.json`，`run_id=fdcc5d7518f247d7ac370846969305c3`）contract 258/257 passed/1 skipped、unit 2073/2067 passed/1 failed（仅 main 既有 `test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip`）/5 skipped、integration 199/181 passed/18 skipped、frontend_test 81 文件 623 passed、protocol_drift_check/requirements_check/design_lint/design_check/frontend_build 均 exit 0、`run_automation_probe.sh`（`.scratch/t068/real_engine_r2/evidence.json`）2 passed（`all_passed=true`）；首轮全量门禁（`5c22ebc247cc414eb849078dde924af1`）e2e 103/90 passed/11 failed（均 main 既有基线）/2 skipped。
- 黑盒：真实 Docker/Chrome/引擎拓扑执行（最新重建镜像 `sha256:cf7a4dd7383e3c2c1aab2f2a0c38a437ba9bbbcf510a39ca077b4296fd46b1b4`）。t068 与 supervisor `cache_init` 专项 E2E 3 passed（31.02s，`.scratch/t068/gate_evidence_r2/junit/e2e_targeted_r3.xml`），覆盖 `cache_init` 真实 helper、容器内外制品损坏/marker/绕过负向与四场景门禁；首轮全量 E2E 11 failed 全为 main 既有基线（`test_artifact_download_chain` / `test_profile_preview`×2 / `test_browser_runtime`×3 / `test_frontend_app`×4 / `test_stream_runtime`，`local_verify_20261113.md` 已记录同源失败），非本 task 引入，不冒充全绿、不放宽断言、不替换故障镜像。
- review：Round 1 code FAIL / test PASS（6 finding 已修）；Round 2 code PASS（`t068_code_f005` minor 已修） / test PASS（0 finding）；Round 3 双路（`review_code.md` / `review_test.md`）均 `PASS`，零新 finding，`reviewed_scope: 61a38f1d38c2afba`，`check_review_status.py` `overall=PASS`。
- AC 判定：4/4 已打勾，双路 reviewer 逐条 `TICK-VALID` 复核。

### 结果摘要

- 交付 `cbrowser/engine_artifacts.py`（ADR 021 批准制品清单 + 下载 Ed25519 信任说明 + 解压 15 文件 SHA-256 校验 + 三处接线 + 禁自动更新/绕过）与 `cbrowser/fingerprint_verification/`（TLS JA3/JA4、四上下文探针、差异门禁、AC-006 一致性）。
- 真实测量与可定位差异报告：`measurement_report.md` + `.scratch/t068/evidence/`（4 份报告、4 份 diff JSON/MD、2 份 config、逐文件 SHA-256 清单）。strict 阻断 raw JA3 方差、显式批准规则后同制品重复通过、HTTP-only（TLS 不可判定）阻断、seed 漂移 16 处跨上下文阻断。
- 未能验证项：真实跨版本引擎升级放行（本机仅一套已获准 linux-arm64 制品）、`linux-x64` 解压件完整性、公网第三方检测站；均逐项列因，不以未确认阈值放行。
- 工具链异常：`findings.py new` 因 main 既有重复编号 `d037`/`d038` 拒绝分配；未手工建 `dNNN`、未改工具链，结论回填 `task.md` 未知契约清单并在最终消息报告。
- 旧测试处置：`test_container_spec_cache_specs`、`test_browser_image_ships_only_runtime_closure` 因语义失效整体替换，未就地改预期（理由见实施笔记）。

### 长期文档闭环

- `docs/specs/engine_upgrade_fingerprint_gate.md` 新建并在 `docs/specs_index.md` 登记 t068（2026-11-13）。
- `docs/blueprint/testing.md` 追加「t068 本地指纹基线与引擎升级回归门禁」；`docs/blueprint/security.md` 追加「引擎制品信任边界（t068）」；`docs/blueprint/decisions.md` 追加 ADR 032。
- 无正式 spike（一次性实验在 `.scratch/`，结论回填 `task.md` 未知契约清单，符合「不建正式 sid」口径）；无 finding 新建（工具链重复编号阻塞，已报告）。
