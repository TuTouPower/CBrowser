# Task review t044（reviewer_focus: 代码）

- task：`t044_e2e_parallel_execution`
- spec：`docs/tasks/t044_e2e_parallel_execution/task.md`
- diff_anchor：`98a9df796d46b2b451a5620f39e2801816155536`
- target：`git -C '<repo>_t044' diff 98a9df796d46b2b451a5620f39e2801816155536`
- round：1
- reviewed_at：2026-11-06T21:47:45+08:00

reviewed_scope: 2d0e65481bb01c5c

## Findings

### t044_code_f001 - 两阶段退出码处理不对称，无并行用例的 suite 会被误判失败

- 严重度：minor
- 锚点：行为缺陷（`-m "not serial"` 收集为空时 suite 假失败）
- 位置：`scripts/run_gates.sh:67`（对照 `:68`）
- 问题：`run_gate_suite` 串行阶段 `:68` 显式容忍 `c2==5`（pytest 无用例收集返回 5），并行阶段 `:67` 的 `c1` 未做同样容忍。若某 suite 的用例全部标注 `pytest.mark.serial`，或后续用例集合变化使 `-m "not serial"` 收集为 0，并行阶段 pytest 返回 5，`c1=5` 使 `run_gate_suite` 直接 `return 5`：该 suite 被记为失败、`suites.tsv` 退出码非零、总门禁失败，而实际 0 个用例失败。当前 E2E/unit/integration 集合均有 non-serial 用例（最终门禁 `unit`/`integration` exit 0、`e2e` exit 1 来自真实用例失败而非 5），且有 `test_serial_marker_partitions_e2e_collection` 断言 `parallel` 非空守护，故当前交付不触发；属两阶段处理不对称的边界不一致，不阻断 PASS。
- 建议：`if [ "$c1" != 0 ] && [ "$c1" != 5 ]; then return "$c1"; fi`，与串行阶段对称；或在 `merge_junit.py` 前对空 phase 做归一化。

## 结论

- 前轮 finding 复核：首轮（Round 1），无前轮。
- 本轮新发现：1 条（critical 0 / important 0 / minor 1）。
- 未进表的提示：
    - 文件过大：`src/backend/cbrowser/supervisor/core.py` 既有 2564 行（≥800 阈值），本 task 仅净增少量重构行，非本 task 新建或堆大，按降级规则不进表，仅列路径行数；其余 diff 触及文件最大为 `tests/fixtures/e2e_env.py` 293 行、`tests/unit/test_t044_e2e_prerequisites.py` 279 行、`scripts/run_gates.sh` 226 行，均未达阈值。
    - 圈复杂度：`SupervisorCore._converge_session` 分支较密但属既有函数，本 task 未增加分支（仅替换注册状态访问），不进表。
    - 7 视角（安全/正确性/契约·Breaking/性能·资源/架构·可维护性/健壮性·可观测/文档·规格）均已扫描：无外部输入直达执行或拼接、无凭证入日志、无公开签名/配置键 breaking 无迁移、无循环内查库、无空 catch/静默吞错，未命中项不进表。
    - 范围外观察（不进表）：`run_suite`（`run_gates.sh:82`）对 `redact_evidence.py` 无 `|| code=$?` 保护，极端情况下后台 group 提前退出、该 suite 不写 TSV 片段，`finish_evidence` 遍历现有片段不察觉漏跑 suite 而可能误 PASS；属既有 run_suite 结构、非本 task 引入。默认模式（非 evidence）不跑 `image_packages`，为 `docs/blueprint/testing.md` 记载的有意分叉。`models.py` 3 处 `lazy="noload"→"raise"` 语义差异：已 grep 确认 `config_versions`/`runtime`/`artifacts` 三关系在 `src/backend` 无任何属性访问点，无行为影响，且为清除 `DeprecationWarning` 的必要根因修复。`e2e.log` 1 条既有 `PytestWarning`（sync 测试误标 asyncio）非 DeprecationWarning。`UV_CACHE_DIR` 默认落在 worktree 本地 `.scratch`，跨 worktree 共享需 `CBROWSER_GATE_UV_CACHE` 覆盖。
    - 完整 E2E 门禁（约 20 分钟 Docker + 持久字体集）未由本 reviewer 重跑；已独立解析 `junit/e2e.xml`、`manifest.json`、`suites.tsv` 与各 `logs/` 机器证据，并复跑全部可复跑的 99 个定向单测，未采信 `progress.md` 自述作为降级依据。唯一 E2E 失败 `test_t019_switch_and_refresh_first_frame_within_2s_host_only`（3.344s > 2.0s）为 t032 基线遗留，2 个 skip 为显式开关探针例外，均非本 task 并行化回归（`t044_diag*.log` 显示其余回归已按根因修复）。
- 总体判断：15 条 AC 实现层均真实完整，无空心壳、恒真断言、mock 掉被测逻辑、就地弱化旧断言或整文件删测试；无未解决 critical/important，仅 1 条 minor 边界不一致，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`scripts/run_gates.sh:61` 并行 `-n "$WORKERS" -m "not serial"` + `:63` 串行阶段 + `merge_junit.py` 合并；独立解析 `junit/e2e.xml` 得 `tests=101`，单测 `test_serial_marker_partitions_e2e_collection` 断言 `serial | parallel == full`（99 个定向单测实跑通过）。
- AC-002：TICK-VALID，re_verified。20 个 E2E 文件模块级 `pytestmark = pytest.mark.serial`（如 `tests/e2e/test_frontend_app_e2e.py:29`），`run_gates.sh:63` 串行阶段 `-n 0 -m "serial"` 单进程且与并行阶段顺序执行，单测断言 `serial.isdisjoint(parallel)` 通过。
- AC-003：TICK-VALID，re_verified。`tests/fixtures/e2e_env.py:165-184` `worker_resource_offsets` 派生 30000/35000/`10.{251+idx}` 分区，`tests/e2e/conftest.py:49-62` worker 强制覆盖 controller 继承值，单测 `test_pytest_configure_repartitions_inherited_ports_on_workers` 通过，最终门禁无端口冲突回归。
- AC-004：TICK-VALID，re_verified。`scripts/merge_junit.py:273-302` 累加 counters 并 append 全部 testcase；独立解析 `e2e.xml` 得 101 testcase 且 1 failure 可精确定位到 `test_t019_...`，`suites.tsv` 11 行 suite 名/退出码与 `manifest.json` 一致。
- AC-005：TICK-VALID，re_verified。`tests/fixtures/e2e_env.py:30-43` `require_e2e_available` 必跑 fail/非必跑 skip，`tests/e2e/conftest.py:128-199` 必跑汇总缺项 `pytest.exit(2)`，`run_gates.sh:114-121` 单进程 collection preflight；`test_e2e_prerequisites_have_no_bare_skip` 通过，`e2e.xml` 仅 2 个 `test_automation_compatibility_probe_e2e` 开关例外 skip。
- AC-006：TICK-VALID，re_verified。`test_fingerprint_platform_e2e.py` 已移除 `.scratch`/`win_fonts`，改 `require_e2e_env(..., fonts_platform="windows")` 读 `CBROWSER_E2E_FONTS_DIR`，`run_gates.sh:536` `unset CBROWSER_FONTS_DIR`；`e2e.xml` 中 3 个 `test_fingerprint_platform_e2e` 用例均 PASS，单测 `test_fingerprint_e2e_uses_persistent_fonts` 通过。
- AC-007：TICK-VALID，re_verified。`run_gates.sh:61-64` 同一两阶段 `run_gate_suite` 覆盖 unit/integration，`:578-581` 传 `-n $WORKERS`；`manifest.json` 中 `unit`/`integration` exit 0，`test_t028_run_gates_evidence.py` stub 契约同步且在 99 个定向单测中通过。
- AC-008：TICK-VALID，re_verified。`run_gates.sh:574-594` `backend_group &` / `frontend_group &` 加两次 `wait` 后才进 E2E，`:124-141` `finish_evidence` 按 `SUITE_ORDER` 合并 `suites.d/*.tsv` 并逐片段判失败返回非零；单测 `test_gate_runs_backend_and_frontend_groups_concurrently` 通过。
- AC-009：TICK-VALID，re_verified。`run_gates.sh:381-397` `prepare_env` 以 `REQ_HASH`/`STAMP` 复用 gate venv；`logs/environment.log` 实测仅 `reuse cached venv ... (no dependency download)`，单测 `test_gate_reuses_shared_uv_cache` 通过。
- AC-010：TICK-VALID，re_verified。`src/backend/cbrowser/supervisor/core.py:833-848` 新增单一 `RegistrationState` + `_registration`，`:406`/`:524`/`:541`/`:2387` 四清理点整体 pop/重置（已读 `_converge_session` 确认 pop 后同名重启 `previously_known=False` 且不进宽限）；3 个红测含 `test_stale_registration_timestamp_does_not_defer_replacement_after_boundary` 在 99 个定向单测中通过。
- AC-011：TICK-VALID，re_verified。`run_gates.sh:560` `requirements_check` 跑 `generate_requirements.sh --check`（脚本 `:48-55` 漂移即 `rc=1`）、`:600` `image_packages` 跑 `verify_image_packages.py`（`:89-92` 不一致即 return 1）；`requirements_check.log` 6 组 ok、`image_packages.log` 5 镜像 OK，单测 `test_main_returns_1_when_packages_differ` 通过。
- AC-012：TICK-VALID，re_verified。`pyproject.toml:216-222` `error::DeprecationWarning` + 3 条精确第三方 ignore；全仓 grep 确认 `src/backend` 无 `HTTP_422_UNPROCESSABLE_ENTITY`（11 处已换 CONTENT）；`agent.py:355,853` `ClientWSTimeout(ws_close=IO_TIMEOUT)` 保持旧语义、`test_control_handoff_e2e.py:1156` `rcvd.code`、`models.py` `lazy="raise"`、`migrations.py:662` `path_separator` 均为根因修复而非忽略掩盖。
- AC-013：TICK-VALID，re_verified。`scripts/vendor_selkies_web.py:148-174` find 定位 / `get_archive(found.splitlines()[0])` / `finally: container.remove(force=True)`；`test_t044_selkies_asset_probe.py` 5 个 Docker SDK 边界单测（注入 `client_factory`，非 mock 被测逻辑）在 99 个定向单测中通过。
- AC-014：TICK-VALID，re_verified。`tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile:1` 与 `config/docker/api_runtime/Dockerfile:1` 的 `FROM python:3.15-slim-trixie@sha256:8c13...` 独立 grep 比对全等；`test_baseline_runtime_regressions.py` FROM 全等断言通过。
- AC-015：TICK-VALID，re_verified。`run_gates.sh` 全文无 `npm run design:tokens`（单测 `test_gate_never_runs_design_tokens_generation` 与 `test_t028` `not in log` 断言通过），保留只读 `design:check`（`logs/design_check.log` 实测 `up to date`）；交付 diff 中 `design_tokens.css` 未被写入，`generate_requirements.sh --check` 只读。

coverage = re_verified / 15

verdict: PASS

## Round 2 (2026-11-06T21:50:00+08:00)

reviewed_scope: d432a53e9ed380fd

- 本轮性质：review_scope 重绑定复核。Round 1（旧指纹 `2d0e65481bb01c5c`）判定 PASS、15/15 AC TICK-VALID；implementer 收尾为通过 finish 的 specs_index 契约，把 `docs/specs_index.md` 的 15 个「最后更新时间」由 ISO 带时区归一为 `YYYY-MM-DD`，并给 `progress.md` 补回模板固定说明（流程文件，不进指纹），交付内容指纹变为 `d432a53e9ed380fd`，`check_review_status` 判 review_scope=stale，故本轮重绑 scope 重审。
- 独立复核唯一交付内容变化（`git diff 98a9df796d46b2b451a5620f39e2801816155536 -- docs/specs_index.md`）：14 个既有 spec 行仅「最后更新时间」列由 `YYYY-MM-DDThh:mm:ss+08:00` 归一为 `YYYY-MM-DD`，slug 列与 task 清单列逐行比对无变化；`|gate_verification|t044|2026-11-06|` 行为本 task Round 1 已纳入的 spec 条目（`progress.md` 收尾报告记载），本轮同样仅日期列归一。无 spec 条目增删、无 task 清单变化、无实现/测试源码改动，属纯格式迁移、无语义变化。
- 前轮 finding 复核：`t044_code_f001`（minor，两阶段空并行集合 exit 5 处理不对称）本轮未改代码（diff 未触及 `scripts/run_gates.sh`），以 diff/代码核实仍为未修遗留状态；处置表（Round 1）登记为「遗留 → p046」，`docs/pending/todo/p046_gate_parallel_empty_phase_exit_code.md` 存在且写明修复方案（c1 与 c2 对称处理 exit 5），`progress.md` 模板固定说明与处置表均已填。minor 非阻断，允许遗留，不构成 FAIL；不采信处置表自称，以 diff 核实。
- 本轮新发现：0 条（critical 0 / important 0 / minor 0）。修复过程仅做文档格式归一，未引入新问题，7 视角与文件过大/圈复杂度提示沿用 Round 1，无新增观察。
- 总体判断：本轮无新 blocker；前轮唯一 minor 已按处置表登记 `p046`（minor 非阻断，允许遗留）；唯一交付变化为 specs_index 日期格式归一，实现/测试内容与全部 AC 证据未变；无未解决 critical/important，PASS。
- 系统性 follow-up：`p046`（已登记）。

### AC 复验方式

本轮为 review_scope 重绑定复核（`2d0e65481bb01c5c` → `d432a53e9ed380fd`）：独立复核 `git diff` 确认相对 Round 1 唯一交付内容变化为 `docs/specs_index.md` 日期格式归一，实现/测试源码、junit / manifest / `suites.tsv` 证据与全部 AC 支撑未变，故 Round 1 的 15 条独立复验证据在本轮继续成立；下列 15 行均为本轮 scope 重绑定复核下继续成立、判定维持 TICK-VALID 且 re_verified 的结论，证据逐条沿用 Round 1。

- AC-001：TICK-VALID，re_verified。`scripts/run_gates.sh:61` 并行 `-n "$WORKERS" -m "not serial"` + `:63` 串行阶段 + `merge_junit.py` 合并；独立解析 `junit/e2e.xml` 得 `tests=101`，单测 `test_serial_marker_partitions_e2e_collection` 断言 `serial | parallel == full`（99 个定向单测实跑通过）。
- AC-002：TICK-VALID，re_verified。20 个 E2E 文件模块级 `pytestmark = pytest.mark.serial`（如 `tests/e2e/test_frontend_app_e2e.py:29`），`run_gates.sh:63` 串行阶段 `-n 0 -m "serial"` 单进程且与并行阶段顺序执行，单测断言 `serial.isdisjoint(parallel)` 通过。
- AC-003：TICK-VALID，re_verified。`tests/fixtures/e2e_env.py:165-184` `worker_resource_offsets` 派生 30000/35000/`10.{251+idx}` 分区，`tests/e2e/conftest.py:49-62` worker 强制覆盖 controller 继承值，单测 `test_pytest_configure_repartitions_inherited_ports_on_workers` 通过，最终门禁无端口冲突回归。
- AC-004：TICK-VALID，re_verified。`scripts/merge_junit.py:273-302` 累加 counters 并 append 全部 testcase；独立解析 `e2e.xml` 得 101 testcase 且 1 failure 可精确定位到 `test_t019_...`，`suites.tsv` 11 行 suite 名/退出码与 `manifest.json` 一致。
- AC-005：TICK-VALID，re_verified。`tests/fixtures/e2e_env.py:30-43` `require_e2e_available` 必跑 fail/非必跑 skip，`tests/e2e/conftest.py:128-199` 必跑汇总缺项 `pytest.exit(2)`，`run_gates.sh:114-121` 单进程 collection preflight；`test_e2e_prerequisites_have_no_bare_skip` 通过，`e2e.xml` 仅 2 个 `test_automation_compatibility_probe_e2e` 开关例外 skip。
- AC-006：TICK-VALID，re_verified。`test_fingerprint_platform_e2e.py` 已移除 `.scratch`/`win_fonts`，改 `require_e2e_env(..., fonts_platform="windows")` 读 `CBROWSER_E2E_FONTS_DIR`，`run_gates.sh:536` `unset CBROWSER_FONTS_DIR`；`e2e.xml` 中 3 个 `test_fingerprint_platform_e2e` 用例均 PASS，单测 `test_fingerprint_e2e_uses_persistent_fonts` 通过。
- AC-007：TICK-VALID，re_verified。`run_gates.sh:61-64` 同一两阶段 `run_gate_suite` 覆盖 unit/integration，`:578-581` 传 `-n $WORKERS`；`manifest.json` 中 `unit`/`integration` exit 0，`test_t028_run_gates_evidence.py` stub 契约同步且在 99 个定向单测中通过。
- AC-008：TICK-VALID，re_verified。`run_gates.sh:574-594` `backend_group &` / `frontend_group &` 加两次 `wait` 后才进 E2E，`:124-141` `finish_evidence` 按 `SUITE_ORDER` 合并 `suites.d/*.tsv` 并逐片段判失败返回非零；单测 `test_gate_runs_backend_and_frontend_groups_concurrently` 通过。
- AC-009：TICK-VALID，re_verified。`run_gates.sh:381-397` `prepare_env` 以 `REQ_HASH`/`STAMP` 复用 gate venv；`logs/environment.log` 实测仅 `reuse cached venv ... (no dependency download)`，单测 `test_gate_reuses_shared_uv_cache` 通过。
- AC-010：TICK-VALID，re_verified。`src/backend/cbrowser/supervisor/core.py:833-848` 新增单一 `RegistrationState` + `_registration`，`:406`/`:524`/`:541`/`:2387` 四清理点整体 pop/重置（已读 `_converge_session` 确认 pop 后同名重启 `previously_known=False` 且不进宽限）；3 个红测含 `test_stale_registration_timestamp_does_not_defer_replacement_after_boundary` 在 99 个定向单测中通过。
- AC-011：TICK-VALID，re_verified。`run_gates.sh:560` `requirements_check` 跑 `generate_requirements.sh --check`（脚本 `:48-55` 漂移即 `rc=1`）、`:600` `image_packages` 跑 `verify_image_packages.py`（`:89-92` 不一致即 return 1）；`requirements_check.log` 6 组 ok、`image_packages.log` 5 镜像 OK，单测 `test_main_returns_1_when_packages_differ` 通过。
- AC-012：TICK-VALID，re_verified。`pyproject.toml:216-222` `error::DeprecationWarning` + 3 条精确第三方 ignore；全仓 grep 确认 `src/backend` 无 `HTTP_422_UNPROCESSABLE_ENTITY`（11 处已换 CONTENT）；`agent.py:355,853` `ClientWSTimeout(ws_close=IO_TIMEOUT)` 保持旧语义、`test_control_handoff_e2e.py:1156` `rcvd.code`、`models.py` `lazy="raise"`、`migrations.py:662` `path_separator` 均为根因修复而非忽略掩盖。
- AC-013：TICK-VALID，re_verified。`scripts/vendor_selkies_web.py:148-174` find 定位 / `get_archive(found.splitlines()[0])` / `finally: container.remove(force=True)`；`test_t044_selkies_asset_probe.py` 5 个 Docker SDK 边界单测（注入 `client_factory`，非 mock 被测逻辑）在 99 个定向单测中通过。
- AC-014：TICK-VALID，re_verified。`tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile:1` 与 `config/docker/api_runtime/Dockerfile:1` 的 `FROM python:3.15-slim-trixie@sha256:8c13...` 独立 grep 比对全等；`test_baseline_runtime_regressions.py` FROM 全等断言通过。
- AC-015：TICK-VALID，re_verified。`run_gates.sh` 全文无 `npm run design:tokens`（单测 `test_gate_never_runs_design_tokens_generation` 与 `test_t028` `not in log` 断言通过），保留只读 `design:check`（`logs/design_check.log` 实测 `up to date`）；交付 diff 中 `design_tokens.css` 未被写入，`generate_requirements.sh --check` 只读。

coverage = re_verified / 15

verdict: PASS
