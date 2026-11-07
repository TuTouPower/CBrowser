# Task review t045（reviewer_focus: 代码）

- task：`t045_e2e_gate_stability_cleanup`
- spec：`docs/tasks/t045_e2e_gate_stability_cleanup/task.md`
- diff_anchor：`a361058152631d6b4c2621a78cd1609e975621e0`
- target：`git -C '/Users/karson/kar/code/CBrowser_t045' diff a361058152631d6b4c2621a78cd1609e975621e0`
- round：1
- reviewed_at：2026-11-07T08:53:49+08:00

reviewed_scope: 7108a0e4e26fc648

## Findings

### t045_code_f001 - 容器归属 label 查询失败时清理退化为按名字删，绕过归属校验

- 严重度：minor
- 锚点：行为缺陷 + AC-002 不变量「其它会话命名的资源不被删除」张力
- 位置：`scripts/gate_container_cleanup.py:109-117`（`collect_targets`）、`scripts/gate_container_cleanup.py:78-83`（`select_cleanup_targets._owned`）
- 问题：`collect_targets` 在 `_list_container_labels` 抛异常时把 `labels` 置为 `{}`，仍传给 `select_cleanup_targets`；`_owned` 仅在 `name in container_labels` 为真时才校验 `com.cbrowser.prefix`，否则 `return True`。于是 label 查询失败、或某容器未被 labels 字典收录时，名字命中白名单前缀即被删除，归属校验被绕过——其它会话中碰巧以 `t007-` / `t006-` 前缀命名且此刻未被收录的容器会被误删。单测 `test_leftover_prefix_containers_are_selected` 等以 `collect_targets(object())` 触发该退化路径（`object()` 无 `.containers`），恰好依赖此行为通过；真实门禁路径（label 查询成功）由 `test_run_cleanup_deletes_only_whitelisted_resources` 覆盖。置信度低：需 docker SDK 二次 `containers.list` 异常这一注入故障，第 5 轮 `container_deletions.jsonl` 95 条删除 label/cleanup prefix 全一致、0 生产容器删除，未观察到误删。
- 建议：异常路径改为 fail-closed（label 不可用时跳过清理或仅删除已确认归属的容器），补一条以真实 `_FakeClient` 走 label 成功路径的残留清理单测，同步调整依赖退化路径的断言。

## 结论

- 前轮 finding 复核：Round 1，无前轮。
- 本轮新发现：1 条（minor 1，important/critical 0）。
- 未进表的提示：
    - 文件过大（降级，仅列路径行数）：`tests/e2e/test_frontend_app_e2e.py` 1412、`tests/e2e/test_supervisor_recovery_e2e.py` 1169、`tests/fixtures/gateway_probe/topology.py` 701、`tests/e2e/test_stream_selkies_tokens_e2e.py` 657、`tests/e2e/test_frontend_session_e2e.py` 628（均 ≥600 测试源码阈值且本 task 净增；按降级规则不进 finding 表）。
    - 圈复杂度：`vendor_selkies_web` 因新增 `allow_download` 分支整体偏高（约 CC≥15），结论段提示，不 blocking，无可观测缺陷。
    - 范围外观察：`docs/tasks/t037_environment_management_ui/review_code.md` / `review_test.md` 各 1 行 home 路径脱敏，不属 t045 spec 范围且触及已完成 task 的 review 报告，仅在结论段提示，不进表。
    - 端口根因复核：`find_free_port` 进程内唯一集合 + 线程锁有效、脱离 `CBROWSER_E2E_HTTP_BASE` 固定段后跨 worker 无系统性争用；`test_stream_selkies_tokens_e2e.py` 改 `-p 127.0.0.1::<container>` + `docker port` 回读宿主端口，`self.port` 为容器内部端口（server 监听同值），回读正确，ac010 第 5 轮 PASS；`test_t045_e2e_host_port_allocation.py` AST 静态防回归真实覆盖（定向实跑 16 passed）。残留 TOCTOU（bind(0)→close→docker bind）为端口预选方案固有、非本次引入，未引入新 regress。
    - `collect_targets` 单测走 label 查询失败退化分支属 test 轴覆盖观察（见 f001），不另出 finding；`p051_e2e_container_vanish_during_gate.md` 为本次新增未解决观察项，不属 AC-007 四条之列；progress.md / task.md 打勾按模板属 claim/流程文件，未作证据。
    - 7 视角（规格合规、代码质量、实现正确性、安全、契约·Breaking、性能·资源、架构·可维护性、健壮性·可观测、文档·规格一致）已全量扫过：无注入/越权/secret 泄漏（诊断日志仅记容器名/label/caller/worker，`docker port` 用列表参数无 shell），`allow_download=True` 默认值保持向后兼容，未命中其它 blocking 项。
- 总体判断：7 条 AC 实现层均真实落地，第 5 轮冻结代码完整门禁（manifest all_passed=true、e2e FAIL=0/ERROR=0）证据充分，无未解决 critical/important，PASS。
- 系统性 follow-up：已有 `p051_e2e_container_vanish_during_gate`（容器消失归因未决，诊断与 label 加固已就位），结论引用，不重复报告。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`scripts/run_gates.sh:82-85` 两阶段对称容忍 exit 5 且 `c1=5&&c2=5` 时 return 5；实测判定组合 c1=5/c2=0→0、c1=0/c2=5→0、c1=5/c2=5→5、c1=1→1；`run_gates.sh:80` merge_junit 无条件执行，实测 pytest exit 5 仍产出 junitxml 文件，串行用例结果可合并。
- AC-002：TICK-VALID，re_verified。`gate_container_cleanup.py:29-59` 前缀白名单精确匹配（trailing `-`）+ `PRODUCTION_CONTAINERS` 保护 + `:62-70` `com.cbrowser.prefix` 归属校验；`run_gates.sh:13-35` EXIT/INT/TERM trap 幂等清理、`:182` 启动清理、`:199` evidence 模式设诊断 env；单测 9 条定向实跑通过，第 5 轮 `container_deletions.jsonl` 95 条删除 label/cleanup prefix 全一致、0 生产容器删除、caller/worker 齐全。
- AC-003：TICK-VALID，re_verified。`test_frontend_session_e2e.py:128` 增 module-scope `shared_stack`，3 用例共享一套栈并按 `case_key` 经 `reset_profile_state` 只重置自身 Profile；grep 确认 `test_frontend_app_e2e/app_auth/media/display_apply` 本就 module-scope；`test_t045_e2e_shared_stack.py` 覆盖启停各一次/只删目标 profile；第 5 轮三个 session 用例全 PASS。
- AC-004：TICK-VALID，re_verified。`scripts/vendor_selkies_web.py:198-222` `allow_download=False` 仅取本地锁定 SHA256 wheel、缺失时 raise 并列出缺项，if/elif 链不进公网 Strategy 1~4；`e2e_env.py:30` `require_e2e_available` 必跑 `pytest.fail`/非必跑 skip，`test_frontend_adapter_build.py` 三用例与 conftest collection preflight 均接入；`test_t045_selkies_wheel_cache.py` monkeypatch `download_wheel`+`urlopen` 实证 0 调用、缺失失败封闭；第 5 轮 `test_vendor_replaces_stale_destination_contents` PASS。
- AC-005：TICK-VALID，re_verified。两处就绪判定改 `poll_until`（media timeout=45、supervisor health timeout=10=原 100×0.1，均未加长/上调）；`real_api_and_sup` fixture（`test_supervisor_recovery_e2e.py:96`）未被本次 diff 改动、原语义还原，回归用例 `test_real_api_and_sup_finally...` 第 5 轮 PASS；`test_ac007_lifecycle_resume_and_isolated_media_diagnostics` 与 `test_supervisor_dual_profile_port_invariance_on_sigkill` 第 5 轮 PASS。
- AC-006：TICK-VALID，re_verified。第 5 轮冻结代码完整门禁 `.scratch/t045_evidence_20261107_081934/manifest.json` `all_passed=true`、10 个 suite 全 exit 0；`junit/e2e.xml` 101 用例 FAIL=0/ERROR=0/SKIP=2（两 skip 为 t032 probe recheck）；AC-004/005 三个目标用例全 PASS（非定向单跑），t019 首帧也 PASS、E2E 失败集合为空不超 t032 基线；前四轮仅作诊断不作 finish 依据。
- AC-007：TICK-VALID，re_verified。`docs/archive/pending/` 内 p046/p048/p049/p050 四条齐备，diff 确认 `resolution=transferred` + 备注写明转入 t045 与核实结论；`docs/pending/todo/` 仅剩 `p051`（本次新增观察项，不属四条之列）。

coverage = 7 / 7

verdict: PASS

## Round 2 (2026-11-07T09:00:00+08:00)

reviewed_scope: ad5ba37ad33167c0

- round：2；reviewer_focus：代码；diff_anchor：`a361058152631d6b4c2621a78cd1609e975621e0`
- target：`git -C '/Users/karson/kar/code/CBrowser_t045' diff a361058152631d6b4c2621a78cd1609e975621e0`（完整 worktree，含 staged 新交付文件）
- 落点校验：`git rev-parse --show-toplevel`（不带 `-C`）输出精确等于 `/Users/karson/kar/code/CBrowser_t045` ✓
- 范围：相对 Round 1 的 f001/f002 修复改动逐项核实 + 7 条 AC 独立复验。`git status --short` 仅 `review_code.md` / `review_test.md` 两份 review 报告未跟踪（流程文件，可见、非交付物），无隐藏交付文件，不判 INCOMPLETE。

### Findings

#### t045_code_f002 - 去掉 `|| true` 后 `set -e` 令 trap 退出码在清理失败路径被改写

- 严重度：minor
- 锚点：行为缺陷（无 AC 违反；spec 未约束门禁清理失败时的退出码）
- 位置：`scripts/run_gates.sh:2`（`set -euo pipefail`）、`:13-17`（`cleanup_containers`）、`:19-24`（`cleanup_gate_resources` 末条命令为 `cleanup_containers`）、`:33-35`（EXIT/INT/TERM trap）、`:182`（启动裸调用）
- 问题：去掉 `|| true` 后，`cleanup_containers` 在 `gate_container_cleanup.py` 抛 `LabelLookupError`（`main()` 返回 1）时返回 1。因脚本 `set -e`，EXIT trap 的 `cleanup_gate_resources` 以失败命令收尾会把原本 `exit 0` 的全绿门禁（`manifest.json all_passed=true`）翻成 shell 退出 1；INT/TERM trap 中 `cleanup_gate_resources; exit 130/143` 的显式退出被 `set -e` 抢先，中断退出码降级为 1。`run_gates.sh` shebang 为 `#!/bin/bash`，宿主实测 `/bin/bash` 3.2.57：cleanup 成功→EXIT 保持 0、INT 保持 130；cleanup 失败（真实外部命令 `python3 -c 'sys.exit(1)'`，忠实于 `"$PY" gate_container_cleanup.py`）→EXIT `exit 0` 得 rc=1、INT 得 rc=1（非 130）。触发条件为 label 查询异常或两次 `containers.list()` 间容器消失的 TOCTOU（第 5 轮证据未复现），结果仍为 fail-closed 非零、非假通过、无误删，故评 minor 不阻断。
- 建议：`cleanup_gate_resources` 入口捕获 `$?`，trap 内以 `return`/`exit $rc` 恢复原退出码（启动 `:182` 保留裸调用以让失败可传导）；INT/TERM trap 忽略 `cleanup_gate_resources` 返回后再 `exit 130/143`。或保留现状并在 progress 处置表记「遗留」引 follow-up。

### 结论

- 前轮 finding 复核（Round 2，以 diff/代码为准，不采信处置表自称「已修」）：
    - `t045_code_f001`（Round 1 minor）：**已消除 / 从根因真修**。`scripts/gate_container_cleanup.py:25` 新增 `LabelLookupError`；`:117-132` `collect_targets` 在 `_list_container_labels` 抛异常或 label map 缺容器（`missing`）时抛 `LabelLookupError`，不再回落按名字前缀删；`:161-167` `run_cleanup` 先 `collect_targets` 成功才进入删除循环，失败时零删除；`:170-186` `main()` 把 `except LabelLookupError`（排在 `except Exception` 之前）记 error 并 `return 1`。3 条新单测（`test_label_lookup_failure_deletes_nothing` / `test_incomplete_label_lookup_deletes_nothing` / `test_main_returns_failure_on_label_lookup_error`）实证 `deleted == []` 且 `main() == 1`。f001 所述「标签查询失败退回按名字删、p051 跨 worker 误删路径」已从根因 fail-closed 封闭。
    - `t045_test_f001`（Round 1 test 轴 minor，用户所述「f002」）：**已消除 / 真修**。`tests/unit/test_t045_run_gate_suite_exit5.py`（新，98 行）`_shell_function()` 从 `scripts/run_gates.sh` 抽取真实 `run_gate_suite()`，写 bash driver 以真实 `sys.executable` + `WORKERS=2` 驱动 mini pytest suite；3 条用例分别覆盖全 serial（并行空 c1=5/c2=0→0）、全 not serial（串行空 c1=0/c2=5→0）、两阶段皆空（→5），并断言 junit 合并出对应用例名。真实入库回归、断言非空非恒真、未 mock 被测逻辑，非假绿；实跑 3 passed。
    - 编号说明：`t045_code_f002` 为 code 轴跨轮全局续编（Round 1 已有 `t045_code_f001`），与 test 轴 `t045_test_f001` 不同，勿与用户简称「f002」混淆。
- 本轮新发现：1 条（minor 1，important/critical 0）。
- f001/f002 修复核实结论：两条均从根因真修；`tests/unit/test_t045_gate_container_cleanup.py` 的 `inject_names` fixture 仅补 `_list_container_labels` 注入（`:35-41`，返回完整 label map 命中 `com.cbrowser.prefix` 前缀），4 条旧单测断言逐字未改，新增 3 条，合计 12 条全过（断言预期未改、仅补齐前置条件成立）。
- `run_gates.sh` 副作用核实（监督点）：① 启动清理失败即门禁中止 **成立**（`:182` 裸调用 + `set -e`，实测 rc=1 且后续 suite 不执行）；② trap 退出码 **正常路径未破坏**（cleanup 返回 0 时 EXIT 保持原码、INT/TERM 保持 130/143，实测），**清理失败路径被改写**（见 `t045_code_f002`）。
- 定向复跑：清理+exit5 `15 passed`；`tests/unit -q -n 4` `1165 passed`；`bash -n scripts/run_gates.sh` OK；改动 .py `py_compile` OK。
- AC-006 证据复核：第 5 轮冻结代码 `.scratch/t045_evidence_20261107_081934/manifest.json` `all_passed=true`、10 suite 全 exit 0；独立解析 `junit/e2e.xml` 得 `tests=101 failures=0 errors=0 skipped=2`，三目标用例与 `test_t019_switch_and_refresh_first_frame_within_2s_host_only` 全 PASS、无任何 FAIL/ERROR。第 6 轮完整门禁（因 `run_gates.sh` / `gate_container_cleanup.py` 本轮有改动）将在复审后跑作为 finish 依据；本轮 AC-006 按第 5 轮证据判 TICK-VALID。
- 未进表的提示：`test_t045_gate_container_cleanup.py` 360、`test_t045_run_gate_suite_exit5.py` 98 均远低于 600 测试源码阈值；`gate_container_cleanup.py` 196 低于 400 脚本阈值；`_shell_function()` 以 `\n}\n` 截断函数体属测试层健壮性 nit（test 轴，不另出 finding）；`docs/tasks/t037.../review_code.md` / `review_test.md` 两行 home 路径脱敏自 Round 1 未变，范围外不进表；`p051` 容器消失归因仍未决（结论引用，不重复报告）。7 视角（规格合规/代码质量/实现正确性/安全/契约·Breaking/性能·资源/架构·可维护性/健壮性·可观测/文档·规格一致）已全量扫过：本轮改动未引入注入/越权/secret 泄漏，新增 `except` 均转 `LabelLookupError` 或记日志、无新吞错，`main()` 新增返回 1 与 `run_gates.sh` 去掉 `|| true` 在实施笔记及 `docs/blueprint/testing.md` / `docs/specs/gate_verification.md` 第 9 节有说明。
- 总体判断：f001/f002 真修，7 条 AC 实现层均 TICK-VALID，仅余 1 条 bounded minor（fail-closed 非零退出的附带效应，无 AC 违反、无假通过、无误删），无未解决 critical/important，PASS。
- 系统性 follow-up：已有 `p051_e2e_container_vanish_during_gate`（容器消失归因未决，诊断与 label 加固已就位），结论引用；`t045_code_f002` 如不就地修，建议 follow-up「门禁 trap 退出码与清理失败传导边界」slug `gate_trap_exit_status`。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`scripts/run_gates.sh:76-85` 两阶段对称容忍 exit 5、`c1=5&&c2=5` return 5、merge_junit 无条件执行；实跑 `test_t045_run_gate_suite_exit5.py` 3 passed（全 serial→0 / 全 not serial→0 / 两阶段皆空→5，并断言 junit 含对应用例）。
- AC-002：TICK-VALID，re_verified。`gate_container_cleanup.py:29-55` 精确前缀白名单 + 生产容器保护、`:70-96` `com.cbrowser.prefix` 归属校验、`:117-132` label 查询失败 fail-closed；`run_gates.sh:33-35` EXIT/INT/TERM trap、`:182` 启动清理、`:199` 诊断 env；`test_t045_gate_container_cleanup.py` 12 条实跑全过（含生产容器不删、其它会话容器不删、label 失败零删除）。
- AC-003：TICK-VALID，re_verified。`test_frontend_session_e2e.py` 改 module-scope `SharedContainerStack` + `register_profile` / `reset_profile_state`（3 用例共享一套栈、按 case_key 只重置自身 Profile）；`test_t045_e2e_shared_stack.py` 2 条覆盖启停各一次 / 只删目标 profile，含在 1165 passed；第 5 轮 e2e.xml 无 FAIL/ERROR。
- AC-004：TICK-VALID，re_verified。`scripts/vendor_selkies_web.py:198-222` `allow_download=False` 仅取本地锁定 SHA256 wheel、缺失 raise 列缺项且 if/elif 不进公网；`tests/e2e/conftest.py` 必跑 collection 校验缓存存在与哈希；`test_t045_selkies_wheel_cache.py` monkeypatch `download_wheel`+`urlopen` 实证 0 调用；第 5 轮 `test_vendor_replaces_stale_destination_contents` PASS。
- AC-005：TICK-VALID，re_verified。两处就绪判定改 `poll_until`（media `timeout=45.0`、supervisor health `timeout=10.0`=原 100×0.1，无加长/上调），diff 中 `test_supervisor_recovery_e2e.py` 仅 `+from wait import poll_until` 与 dual_profile 内两处循环改写，`real_api_and_sup` fixture 无 diff hunk（相对 anchor 净未改）；第 5 轮 ac007 与 dual_profile 两目标用例均 PASS。
- AC-006：TICK-VALID，trust_prior。完整 E2E 门禁为真实 Docker + 无头 Chrome 部署态，reviewer 无法重跑；依赖第 5 轮冻结代码证据 `manifest.json` all_passed=true / 10 suite 全 0，已独立解析 `junit/e2e.xml` 得 101 例 FAIL=0/ERROR=0/SKIP=2 且三目标用例 + t019 全 PASS；因 `run_gates.sh` / `gate_container_cleanup.py` 本轮有改动，第 6 轮冻结代码门禁将在复审后跑作为 finish 依据。
- AC-007：TICK-VALID，re_verified。`docs/archive/pending/` 内 p046/p048/p049/p050 四条齐备，逐条 `resolution=transferred` + `处理：t045` + reason 写明「已核实仍有效并转交 t045…核实结论」；`docs/pending/todo/` 仅剩本轮新增观察项 `p051`（不属四条）。

coverage = 6 / 7

verdict: PASS
