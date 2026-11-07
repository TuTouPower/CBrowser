# Task review t045（reviewer_focus: 测试）

- task：`t045_e2e_gate_stability_cleanup`
- spec：`docs/tasks/t045_e2e_gate_stability_cleanup/task.md`
- diff_anchor：`a361058152631d6b4c2621a78cd1609e975621e0`
- target：`git -C '/Users/karson/kar/code/CBrowser_t045' diff a361058152631d6b4c2621a78cd1609e975621e0`
- round：1
- reviewed_at：2026-11-07T08:54:20+08:00

reviewed_scope: 7108a0e4e26fc648

## Findings

### t045_test_f001 - AC-001 `run_gate_suite` exit 5 对称处理缺入库回归测试

- 严重度：minor
- 锚点：AC-001
- 位置：`.scratch/t045_verify/p046_check.sh:39-63`、`.scratch/t045_verify/run_gate_suite.sh:15-18`、`.scratch/t045_verify/out/{allserial,empty,mixed}.xml`；对照 `tests/unit/test_t045_*.py`（4 个文件均无 `run_gate_suite` / exit 5 用例）
- 问题：`scripts/run_gates.sh:82-84` 的 exit 5 分支实现正确（c1=c2=5 → `return 5`；单阶段 5 不假失败；真失败退出码保留），但入库单测为零。三场景验证全在 `.scratch/t045_verify/`：`p046_check.sh:39` 用 `sed` 抽取**真实** `run_gate_suite()` 函数体，构造 `allserial`（全 `serial`）、`empty`（两阶段皆空）、`mixed` 三个 suite，`check` 期望 rc 0 / 5 / 0；产物 `out/allserial.xml`（merged tests=2，含 `test_serial_one`/`test_serial_two`）、`out/empty.xml`（tests=0）、`out/mixed.xml`（tests=2，parallel+serial）证明 junit 仍合并串行用例。`.scratch/` 被 `.gitignore:4` 忽略，脚本与产物不随交付入库，`run_gate_suite` 后续改动无回归守护。证据本身有效（抽取的是真实函数而非平行实现，junit 产物可查；第 5 轮完整门禁 e2e 亦为 serial/parallel 双阶段 merged 101），故按 minor，不阻断，AC-001 打勾成立。
- 建议：把三场景落为 `tests/unit/test_t045_gate_suite_exit5.py`（subprocess 调 `run_gate_suite` 函数体或最小 stub 断言 rc 与合并 junit），或在仓库内固化该验证脚本并在 `docs/blueprint/testing.md` 登记为门禁必跑项。

## 结论

- 改测方向复核：无「迁就实现」改测。`test_frontend_app_e2e.py:1006-1058` 把 `deadline` 循环改 `poll_until(timeout=45.0, interval=0.5)`，原 `assert final_fault_stats is not None` 与 `assert discarded_count > 0` 全保留，且把 `discarded_count>0` 升为就绪条件（强化）；`test_supervisor_recovery_e2e.py:566`、`621` 两处 `for _ in range(100)+sleep(0.1)` 改 `poll_until(timeout=10.0)`，原循环无断言、改造后超时抛 `TimeoutError`（强化）；`test_frontend_session_e2e.py` 只替换 fixture 参数与 `finally` 清理，断言主体未动；`test_frontend_adapter_build.py` 只加 `wheel_path`/`allow_download=False`，未改断言（其 version-agnostic 注释属基线，非本 task diff）；`test_stream_selkies_tokens_e2e.py` 只改端口映射，未删断言。`tests/fixtures/wait.py:42-64` `poll_until` 超时抛 `TimeoutError` 而非返回末次观测，无恒真断言假绿。
- 本轮新发现：1 条（minor）
- 未进表的提示：(1) AC-002 的 EXIT/INT/TERM trap「同一套清理」仅 `.scratch/t045_verify/trap_check.py` + `trap_normal.log`/`trap_sigint.log` smoke（各 `scratch`/`containers` 一次），未入库；AC-002 明确要求的两类单测（残留容器被清 / 非白名单不被删）已由 9 条入库单测覆盖，trap 未列入「有单测覆盖」要求，故不进表。(2) `tests/fixtures/gateway_probe/topology.py:396` 仍为 `ports={"443/tcp": ("127.0.0.1", self.caddy_host_port)}` 显式宿主端口绑定；端口 guard 仅验证 `find_free_port` 内 `bind(0)` 与不读 `CBROWSER_E2E_HTTP_BASE`（`test_t045_e2e_host_port_allocation.py:124-167`），未覆盖实际 docker 绑定形态，属可选覆盖扩展，非本 task 引入的假行为。(3) 危险模式扫描全量：diff 无删除断言 / 删测试 / `.skip` / `.only` / 恒真断言 / `type: ignore` / 阈值（timeout/重试/容差）增大掩盖。`test_frontend_session_e2e.py` 删除每用例 `harness.cleanup()` 由 spec 共享栈要求驱动，已由 module `shared_stack.cleanup()` 与 `test_t045_e2e_shared_stack.py` 等价补回，合法。(4) 端口防回归 3 条单测真实触达：ast.parse 遍历真实 `tests/e2e/test_*.py` 与 `topology.py`；`_pinned_literal_ports` 覆盖 `ports=` 字面量固定端口与非 0 `bind`，`_fixed_range_port_scans` 覆盖 `find_free_port(start,end)` 带参调用，`_pinned_cli_port_mappings` 覆盖 `f"127.0.0.1:{a}:{b}"` 双端口；实测 helper 命中 `test_stream_runtime_e2e.py` 的 `f'127.0.0.1:{udp_mux_port}:{udp_mux_port}/udp'` 且该模块 `pytestmark = pytest.mark.serial`，`test_non_serial_e2e_modules_do_not_pin_host_ports` 正确跳过、`test_modules_with_pinned_host_ports_are_serial` 通过；改回固定范围扫描会同时触发 `_bind_zero` 缺失与「不得 bind 固定端口」断言，非假绿。
- 总体判断：7 条 AC 打勾在测试与验证层均有真实证据支撑；唯一 minor 为 AC-001 验证未入库，无未解决 critical / important，PASS。
- 系统性 follow-up：`docs/pending/todo/p051_e2e_container_vanish_during_gate.md`（观察项，已登记）。前四轮完整门禁曾出现「容器运行期消失」超基线失败，根因未定；第 5 轮冻结门禁未复现。AC-006 按第 5 轮证据判定成立，但稳定性仍依赖后续门禁按 p051 归因，不据一次全绿结案根因。
- 复核执行：落点仓库 `git rev-parse --show-toplevel` = `/Users/karson/kar/code/CBrowser_t045` ✓；`env PYTHONPATH=src/backend .scratch/gate_venv/bin/python -m pytest tests/unit/test_t045_*.py -q` → 16 passed；`tests/unit -q -n 4` → 1159 passed；`bash -n scripts/run_gates.sh` → OK。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`scripts/run_gates.sh:82-84` exit 5 对称实现 + `.scratch/t045_verify/p046_check.sh` 抽取真实 `run_gate_suite()` 三场景 rc 0/5/0 + `out/*.xml` junit 合并证据 + 第 5 轮 e2e 双阶段 merged 101；入库单测缺口按 minor 记（f001）。
- AC-002：TICK-VALID，re_verified。`tests/unit/test_t045_gate_container_cleanup.py` 9 条（含 `test_foreign_session_container_is_not_a_gate_leftover`、`test_gate_start_cleanup_never_targets_later_worker_containers`、生产容器保护）经 importlib 加载真实 `scripts/gate_container_cleanup.py`，monkeypatch 仅落在 Docker 名字/label 边界，断言 plan/calls 精确；16 passed 复跑 + 第 5 轮 `container_deletions.jsonl` 95 条删除全为 t006/t007 测试前缀、0 生产容器 + `t045_gate_final.log` 启动/退出各 `removed 0`。
- AC-003：TICK-VALID，re_verified。`tests/unit/test_t045_e2e_shared_stack.py` 2 条直接 import 真实 `SharedContainerStack`，断言 start/cleanup 各 1 次、`reset_profile_state` 只删 `p-b` 且保留 `case_a`/`case_c`；`test_frontend_session_e2e.py` 三用例改 module `shared_stack`；第 5 轮 e2e junit 三个 `test_frontend_session_*` 用例 PASS。
- AC-004：TICK-VALID，re_verified。`tests/unit/test_t045_selkies_wheel_cache.py` 2 条（本地 wheel 命中 `calls==[]` 且生成 index.html / 缺失 `RuntimeError('download disabled')` 列缺项且无网络）+ `test_frontend_adapter_build.py` 四例 `allow_download=False` + `tests/e2e/conftest.py:195-223` 必跑模式 `pytest.exit(returncode=2)` 失败封闭 + `require_e2e_available` 必跑 fail / 非必跑 skip；16 passed 复跑、第 5 轮 `test_vendor_replaces_stale_destination_contents` PASS。
- AC-005：TICK-VALID，re_verified。`test_frontend_app_e2e.py:1006-1058` 与 `test_supervisor_recovery_e2e.py:566,621` 改 `poll_until`（45.0 / 10.0，无超时上调、无 sleep 加长），`wait.py:42-64` 超时抛 TimeoutError；原断言全保留；`test_real_api_and_sup_finally_propagates_cleanup_error_and_reaps_remaining` 第 5 轮 PASS（`real_api_and_sup` fixture 原语义未改，不误判）；三个 AC-005 相关 E2E 用例第 5 轮 PASS。
- AC-006：TICK-VALID，re_verified。第 5 轮（冻结代码、finish 依据）`.scratch/t045_evidence_20261107_081934/manifest.json` `all_passed=true`，`junit/e2e.xml` merged `tests=101 failures=0 errors=0 skipped=2`（2 skip 为 `test_t032_probe_*_recheck`，非 t019）；三目标用例 `test_vendor_replaces_stale_destination_contents` / `test_ac007_lifecycle_resume_and_isolated_media_diagnostics` / `test_supervisor_dual_profile_port_invariance_on_sigkill` 全 PASS，t019 `test_t019_switch_and_refresh_first_frame_within_2s_host_only` 与 WS1006 `test_e2e_ac010_selkies_server_token_semantics_with_emulated_injection` 亦 PASS，失败集合空 ⊆ t032 基线；`test_t045_e2e_host_port_allocation.py` 3 条静态 AST 防回归有效非假绿（见结论提示 4）。
- AC-007：TICK-VALID，re_verified。`git status --short` 四条 `R docs/pending/todo/p0NN -> docs/archive/pending/p0NN`（p046/p048/p049/p050），`docs/pending/todo/` 无残留；归档备注「t045；resolution=transferred；已核实仍有效并转交 t045」含转入 tid 与核实结论；p051 为本次新增的另一条观察 todo，不属四条之列。

coverage = 7 / 7

verdict: PASS

## Round 2 (2026-11-07T09:00:00+08:00)

reviewed_scope: ad5ba37ad33167c0

- 落点校验：`git rev-parse --show-toplevel`（不带 -C）= `/Users/karson/kar/code/CBrowser_t045` ✓。指纹经 `check_review_status.current_scope_fingerprint` 只读重算 = `ad5ba37ad33167c0`，与本轮行精确一致；派审前脚本 `review_scope=stale`（报告仍为 Round 1 指纹 `7108a0e4e26fc648`），追加本轮行后转 ok。

## Findings（Round 2）

- 本轮新发现：0 条（clean review）；critical 0 / important 0 / minor 0。

## 结论

- 前轮 finding 复核（以 diff/代码为准，不采信处置表自称）：
    - `t045_test_f001`（Round 1，minor，AC-001 `run_gate_suite` exit 5 缺入库回归测试）→ 已消除。新增 `tests/unit/test_t045_run_gate_suite_exit5.py`（`A`，仓库内，非 `.scratch` 一次性脚本）：`_shell_function()`（:20-24）从 `scripts/run_gates.sh` 抽取真实 `run_gate_suite()` 函数体到行首 `}`；本轮只读验证抽取 = 19 行，首 `run_gate_suite() {`、末 `}`，含 `return 5`（:82）与 `merge_junit.py`（:80）调用，`scripts/merge_junit.py` 存在，函数体内部无行首 `}` 干扰，抽取完整、非平行实现。`_drive`（:27-62）以 `sys.executable` 生成临时脚本（`PY`/`WORKERS=2`/`cd REPO_ROOT`，4 参数对齐函数签名 `target/pp/junit/basetemp`）驱动 mini pytest suite。三场景全覆盖：`test_all_serial_suite_does_not_false_fail`（全 serial→并行空 rc 0 + junit 含 `test_serial_only`）、`test_all_parallel_suite_does_not_false_fail`（全 not serial→串行空 rc 0 + junit 含 `test_parallel_only`）、`test_both_phases_empty_suite_fails`（两阶段皆空→rc 5）。`_case_names`（:65-71）用 `ET.parse(junit).iter("testcase")` 断言，junit 缺失/无用例即空集致断言失败，非恒真；生成脚本无 `set -e` 但两阶段 pytest 各有 `|| c1=$?`/`|| c2=$?` 捕获 rc，函数抽取不全会 rc 127≠0/5 致失败，故 15 passed 证明 rc 与合并 junit 真实。
    - `t045_code_f001`（Round 1，minor，label 查询失败退化按名字删）→ 已消除。`scripts/gate_container_cleanup.py:117-132` `collect_targets` 改为 label 抛错/`missing` 非空即 `raise LabelLookupError`；`:177-183` `main()` `except LabelLookupError: return 1`；配套 3 条新增单测。
- 本轮重点复核（f001/f002 修复的测试质量）：
    - `test_t045_gate_container_cleanup.py` 新增 3 条（:288/:321/:342）真实触达生产逻辑、非假绿、覆盖「标签查询失败时不删除任何容器」：`test_label_lookup_failure_deletes_nothing` 令 `_list_container_labels` 抛 `RuntimeError`，断言 `pytest.raises(LabelLookupError)` + `deleted == []`；`test_incomplete_label_lookup_deletes_nothing` 令 label map 返回 `{}`，真实触达 `collect_targets` `missing` 分支（:126-131），同样零删除；`test_main_returns_failure_on_label_lookup_error` 注入 fake `docker` 模块（`from_env` 返回 object），label 抛错，断言 `main() == 1`（真实触达 :177-183）。mock 仅落 Docker SDK 边界（`_list_container_labels`）与删除副作用（`_delete_container`/`_delete_network`），未 mock 被测逻辑 `run_cleanup→collect_targets`；`deleted == []` 有区分力（若实现抛错前/后仍删除则非空）。
    - `inject_names` fixture 补 `_list_container_labels` 注入（:35-41，label 值=容器名，命中前缀者同时命中白名单）后，旧 4 条（`:107/:133/:154/:180`）断言预期保持不变：均为精确 `frozenset` / `in` / `not in` 白名单语义，未空集化、未弱化、未改成就近实现输出。该文件相对 `a361058...` 为 `new file`、无 git 历史可逐字对比；据 Round 1 报告（记 9 条、断言 plan/calls 精确）、code review f001 对 Round 1 退化路径的描述、当前断言语义三者，判定为 fixture 基础设施适配（生产 `collect_targets` 现强制 label 完整，旧测试需注入完整 label map 才不抛 `LabelLookupError`），非「就地改旧预期迁就实现」。前 9 条 = Round 1 的 9 条，后 3 条为纯追加。改测方向复核：无迁就实现的改测。
    - `test_t045_e2e_host_port_allocation.py` 3 条（:109/:124/:170）与其余 t045 单测仍有效：AST 遍历真实 `tests/e2e/test_*.py` 与 `topology.py`、import 真实 `SharedContainerStack`（`test_t045_e2e_shared_stack.py` 断言 start/cleanup 各 1 次、reset 只删 p-b）、`test_t045_selkies_wheel_cache.py` 公网下载守卫抛 `AssertionError` + `calls == []`；无恒真断言 / `.skip` / 删 expect / 阈值放大 / `type: ignore`。5 个 t045 unit 文件全跑 22 passed（Round 1 的 16 + 新增 3 + f002 新文件 3）、unit 全量 1165 passed、`bash -n scripts/run_gates.sh` OK。
- 本轮新发现：0 条。
- 未进表的提示：第 6 轮完整门禁（`gate_container_cleanup.py` fail-closed 改动后）复审后补跑作 finish 依据，不属本轮 E2E 实跑范围；`p051` 为本次新增观察 todo、不属 AC-007 四条。系统性 follow-up 沿用 `docs/pending/todo/p051_e2e_container_vanish_during_gate.md`，不重复报告。
- 总体判断：Round 1 两条 minor 均以仓库内真实回归测试 + 生产 fail-closed 修复消除；新增 3 条单测与 f002 回归测试真实触达生产、非假绿、旧断言未迁就实现；7 条 AC 在测试与验证层均有真实证据支撑；无未解决 critical / important；PASS。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`test_t045_run_gate_suite_exit5.py` 入库三场景（并行空/串行空/两阶段皆空→rc 0/0/5 + junit 合并断言）抽取真实 `run_gate_suite()`，`run_gates.sh:82-85` exit 5 对称；定向 15 passed，Round 1 f001 缺口已消除。
- AC-002：TICK-VALID，re_verified。9 条既有 + 3 条新增单测 importlib 加载真实 `gate_container_cleanup.py`，`collect_targets` fail-closed（:117-132）零删除、`main()` 返回 1；22 passed 复跑 + 第 5 轮 `container_deletions.jsonl` 0 生产容器删除。
- AC-003：TICK-VALID，trust_prior。共享栈「整套启停次数显著降低 / 负载下无跨用例串扰」依赖第 5 轮冻结门禁 e2e.xml（三 `test_frontend_session_*` 用例 PASS，本轮解析确认）；隔离语义单测 `test_t045_e2e_shared_stack.py` 本轮 22 passed 复跑，E2E 实跑未在本轮重跑、第 6 轮复审后补。
- AC-004：TICK-VALID，re_verified。`test_t045_selkies_wheel_cache.py` 2 条（本地 wheel `calls == []`、缺失 `RuntimeError('download disabled')` 列缺项）本轮 22 passed 复跑；第 5 轮 e2e.xml `test_vendor_replaces_stale_destination_contents` PASS 本轮解析确认。
- AC-005：TICK-VALID，trust_prior。「负载下稳定通过」依赖第 5 轮冻结门禁 e2e.xml（三目标用例 PASS，本轮解析确认）；`poll_until` 改动 Round 1 已核查、本轮 diff 未触及，E2E 实跑未在本轮重跑、第 6 轮复审后补。
- AC-006：TICK-VALID，re_verified。本轮严格解析 `.scratch/t045_evidence_20261107_081934/manifest.json`（`all_passed=true`、10 suite 全 exit 0）与 `junit/e2e.xml`（`tests=101 failures=0 errors=0 skipped=2`，99 PASS + 2 SKIP 为 `test_t032_probe_*_recheck`），三目标用例 + t019 首帧 + WS1006 全 PASS；第 5 轮冻结代码证据为打勾依据，第 6 轮（fail-closed 改动后）复审后补跑作 finish 依据。
- AC-007：TICK-VALID，re_verified。`git status --short` 四条 `R docs/pending/todo/p0NN -> docs/archive/pending/p0NN`（p046/p048/p049/p050），逐条读归档备注 `处理：t045；resolution=transferred；reason=已核实仍有效并转交 t045…` 含转入 tid 与核实结论；`docs/pending/todo/` 仅剩 `p051`（本次新增观察项，不属四条）。

coverage = 5 / 7

verdict: PASS
