# Task review t044（reviewer_focus: 测试）

- task：`t044_e2e_parallel_execution`
- spec：`docs/tasks/t044_e2e_parallel_execution/task.md`
- diff_anchor：`98a9df796d46b2b451a5620f39e2801816155536`
- target：`git -C '/Users/karson/kar/code/CBrowser_t044' diff 98a9df796d46b2b451a5620f39e2801816155536`
- round：1
- reviewed_at：2026-11-06T21:45:00+08:00

reviewed_scope: 2d0e65481bb01c5c

## Findings

本轮 **0 finding**（clean review，禁止凑数）。已按 `t044_test_fNNN` / severity / 位置 / 说明 结构化字段逐条扫描危险模式、改测方向与全部 15 条 AC 的测试可信性，调查后均判定放行、无进表项；逐项调查记录见「结论」。

|finding_id|severity|位置|说明|
|---|---|---|---|
|—|—|—|零发现，无 `t044_test_fNNN` 条目|

## 结论

- 改测方向复核：无「迁就实现」的改测。逐处判定：`test_t026_supervisor_convergence.py:194,344` 两处私有字典访问随 `RegistrationState` 重构改为 `.known` / `.lost_at`，断言仍为 `is True` 与「老化时间后 `start_stream` in calls」，语义不变，且新增 3 个红测覆盖新语义（符合「新增覆盖新语义 / 整体删除写明理由」）；`test_t028_run_gates_evidence.py:140,152` 的 `design:tokens in log → not in log` 反转、suite 列表去 `design_tokens` 加 `requirements_check`，归因于 AC-015 规格变化（门禁移除生成步骤、接入 requirements_check），非迎合实现，且 `assert suites["integration"]["exit_code"] == 3` 失败记录断言原样保留、新增 `requirements_check exit 0` 与 `design:tokens not in log` 断言；`test_control_handoff_e2e.py:1158` → `exc.value.rcvd.code`（值仍 4403）为 AC-012 弃用 API 适配，非加忽略规则绕过告警；`test_fingerprint_platform_e2e.py` / `test_runtime_profile_defaults_e2e.py` / `test_supervisor_event_shutdown_e2e.py` 删除的是内联前置 `pytest.skip` 辅助逻辑（非测试断言），由 `require_e2e_env` / `require_e2e_available` 等价替代，归因于 AC-005 失败封闭。全 diff 无 `def test_` 块删除、无注释/反转/弱化断言迎合实现、无 `.only`、无新增 `# type: ignore` / `eslint-disable`。
- 本轮新发现：0 条。
- 未进表的提示：
    - 调查后放行（低置信度观察，不构成危险模式命中）：① `test_t044_status_constants.py::test_new_422_constant_value_is_422` 含 `if value is None: pytest.skip(...)`；查 `junit/unit.xml` 该用例实际 **PASS**（门禁 fastapi 0.162.0 暴露新常量，skip 未触发），且 AC-012 另由两条源码断言、`test_deprecation_warning_policy`、以及全量门禁在 `error::DeprecationWarning` 下 1141 用例 0 failure 共同覆盖，非掩盖失败，放行。② `test_t044_verify_image_packages.py::test_main_*` 用 `patch.object(_vip, "image_freeze")` 注入模块内函数；被测 `main()` 的比较/退出码逻辑真实执行、断言随输入变化（差异→1、匹配→0，非恒真），`image_freeze` 另有 `test_image_freeze_runs_docker_pip_freeze_with_timeout` 覆盖其 docker 命令构造，未 mock 掉被测逻辑本身，放行。③ `test_t044_gate_contract.py` 与 `test_four_lifecycle_cleanup_points_use_the_single_state_object` 用源码字符串 / `count >= 4` 断言；均会被实现缺陷触发（删参数、删类即失败），且上下文区「测试策略」明确批准门禁脚本参数、时序标注收集、资源命名唯一性的静态契约，配合门禁真实运行证据（manifest / junit / logs），放行。
    - progress 核对：实施笔记第 41 行明确把首轮 13 failures + 1 error 归因为「并行化回归（t044 自身 AC-002/AC-003 问题），非已登记遗留」，第 42 行要求失败集合不超串行基线、明确「不得记为 t032 已登记遗留」；未把并行化回归写成已登记遗留。
    - 失败集合核对：最终 `junit/e2e.xml` 101 用例、仅 `test_t019_switch_and_refresh_first_frame_within_2s_host_only` 1 项失败（t036 串行基线同项，3.344s > 2.0s）、0 error、2 个 t029 探针开关 skip；`manifest.json` 除 `e2e`(1) 外 9 个 suite 全 exit 0、`suites.tsv` 10 行与 manifest 一致；不超 t036 仅 t019 / t043·t041 0 失败的串行基线。
    - 可选覆盖扩展（非阻断、不进表）：AC-012 前半「未登记来源 DeprecationWarning 时测试失败」目前靠 `pyproject.toml` 配置字符串断言 + 全量门禁间接验证，未用子进程真实发出未登记警告验证其被提升为 error；属「可补一个 case」，不阻断。
- 总体判断：测试与验证层 15 条 AC 打勾均真实，测试触达生产逻辑、断言可被实现缺陷触发、无 mock 掉被测逻辑、无就地弱化/删除旧断言迎合实现，门禁证据与失败集合一致且未污染基线；无未解决 critical / important，PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。最终门禁 E2E 由 `run_gate_suite` 以 `-n 4 -m "not serial"` + `-n 0 -m "serial"` 两阶段执行；独立复验 `--collect-only` 得 101 = 53 serial + 48 并行、disjoint 且 union==full，`junit/e2e.xml` 恰 101 testcase，`junit/unit.xml` 1141 全绿。
- AC-002：TICK-VALID，re_verified。53 个时序敏感 E2E 用例由模块级 `pytestmark = pytest.mark.serial` 标注、串行阶段 `-n 0 -m "serial"` 单进程执行；`test_serial_marker_partitions_e2e_collection` 独立复验集合完全划分，执行期不与并行阶段重叠。
- AC-003：TICK-VALID，re_verified。`worker_resource_offsets` 的 `test_t044_e2e_prerequisites.py` 单测断言 gw0/gw1/gw2 的 UDP/HTTP 基值与 media 子网两两互斥，`test_pytest_configure_repartitions_inherited_ports_on_workers` 验证 worker 强制覆盖 controller 继承基值；最终门禁无端口/容器名冲突残留失败。
- AC-004：TICK-VALID，re_verified。`test_t044_merge_junit.py` 三测验证两阶段 junit 合并保留全部用例及各自 failure/skipped/error、计数与 time 求和；`e2e.xml` 101 用例各带结果、t019 失败可定位，`manifest.json` 与 `suites.tsv` 的 suite 名与退出码语义一致。
- AC-005：TICK-VALID，re_verified。`test_t044_e2e_prerequisites.py` 18 测覆盖变量/路径/Docker/字体四类前置在必跑 `pytest.fail`、非必跑 `pytest.skip` 且消息列出缺项；`test_e2e_prerequisites_have_no_bare_skip` 扫描绕开封闭；最终门禁仅 2 个开关探针 skip、0 error。
- AC-006：TICK-VALID，re_verified。`test_fingerprint_platform_e2e.py` 移除全部 `.scratch` / `win_fonts` / `t032` 硬编码，改走 `CBROWSER_E2E_FONTS_DIR` + `fonts_platform` 导入集；`e2e.xml` 中 3 个指纹平台用例真实 PASS。
- AC-007：TICK-VALID，re_verified。`run_gate_suite` 对 unit/integration 同样两阶段 xdist，`unit.xml` 1141、`integration.xml` 全绿，t026 与 `test_v2_api_subprocess.py` 标 serial；collect 与执行集合一致。
- AC-008：TICK-VALID，re_verified。`t044_gate_final.log` 显示 design_lint/design_check 与 contract/unit 交错（前后端组并发），`test_gate_runs_backend_and_frontend_groups_concurrently` 断言两 `wait` 先于 image_packages/e2e；e2e exit 1 时 manifest 仍逐 suite 记录、总退出码非零。
- AC-009：TICK-VALID，re_verified。`logs/environment.log` 仅 `reuse cached venv ... (no dependency download)`；`test_gate_reuses_shared_uv_cache` 校验 `UV_CACHE_DIR` / `REQ_HASH` / `STAMP` 契约。
- AC-010：TICK-VALID，re_verified。t026 先红后绿红测 `test_stale_registration_timestamp_does_not_defer_replacement_after_boundary`（旧实现下 `last_error != "registration_recovery_grace"` 与 `start_stream` 断言失败）+ 单状态对象测 + 4 清理点静态断言，`unit.xml` 35 passed；两处私有字典访问改名断言语义不变。
- AC-011：TICK-VALID，re_verified。`requirements_check.log` 6 组 requirements ok、`image_packages.log` 5 镜像 OK，`test_t044_verify_image_packages.py` 8 测验证 normalise/image_freeze/main 差异返回 1、匹配返回 0；`generate_requirements.sh --check` 与 `verify_image_packages_all` 已接入门禁。
- AC-012：TICK-VALID，re_verified。`pyproject.toml` 为 `error::DeprecationWarning` + 3 条精确第三方 ignore、无 blanket ignore，`test_deprecation_warning_policy` 与 `test_t044_status_constants.py` 3 测（含 PASS 的 `value == 422`）验证；`test_control_handoff_e2e.py` 改用 `exc.value.rcvd.code` 而非靠忽略规则绕过告警。
- AC-013：TICK-VALID，re_verified。`test_t044_selkies_asset_probe.py` 5 测以 Docker SDK FakeClient 为边界，验证 `find` 定位路径、`get_archive` 用返回路径取归档、exec_run/get_archive 出错均 `remove(force=True)`。
- AC-014：TICK-VALID，re_verified。`test_baseline_runtime_regressions.py` 新增断言 fixture Dockerfile FROM 行与生产 `config/docker/api_runtime/Dockerfile` FROM 行全等（3.15/trixie digest），`unit.xml` PASS。
- AC-015：TICK-VALID，re_verified。`t044_pre_gate_status.txt` / `t044_post_gate_status*.txt` 前后完全一致（受跟踪文件不变），`t044_design_check_fail.log` 显示 design_tokens.css 过期时 `design:check` 失败，`t044_gate_final.log` 无 design:tokens 步骤且 `test_gate_never_runs_design_tokens_generation` 静态守护。

coverage = re_verified / 15

verdict: PASS

## Round 2 (2026-11-06T21:50:00+08:00)

本轮为 scope 重绑定复核。Round 1 判定 PASS、15/15 AC TICK-VALID、0 finding；前轮无未解决 blocker（code 轴唯一 `t044_code_f001` 为 minor，已按处置表登记 `p046` 遗留，非阻断；test 轴零 finding）。implementer 收尾把 `docs/specs_index.md` 的 15 个「最后更新时间」由 ISO 带时区归一为 `YYYY-MM-DD`（纯格式迁移，属 `finish` 的 specs_index 契约要求），并给 `progress.md` 补回模板固定说明（流程文件，排除于指纹计算）；无 spec 增删、无测试/实现改动。交付指纹由 `2d0e65481bb01c5c` 重绑定为 `d432a53e9ed380fd`，本轮范围指纹按重绑定值照抄，无新 finding、前轮无未解决 blocker，交付变化仅为文档格式归一。

独立复核（只读，未跑门禁、未改 git）：`docs/specs_index.md` 15 行日期均为 `YYYY-MM-DD`、slug 集合与 `docs/specs/` 下 15 份 spec 文件一致，无 spec 增删；最终门禁证据 `.scratch/t044_evidence_final_gate/manifest.json` 仍为 10 suite（requirements_check/contract/unit/integration/design_lint/design_check/frontend_test/frontend_build/image_packages 九项 exit 0、e2e exit 1、all_passed=false）；`junit/e2e.xml` 解析得 101 testcase、1 failure（`test_t019_switch_and_refresh_first_frame_within_2s_host_only`，首帧 3.344s > 2.0s，t032 已登记遗留、t036 串行基线同项）、0 error、2 skipped（均 `test_automation_compatibility_probe_e2e` 的 t029 探针开关例外），失败集合不超串行基线；`progress.md` 收尾报告「测试/黑盒/review」三行非空，第 68 行明确「首轮 13 / 重验 11 项并行化回归逐项按失败日志根因修复…不记为遗留」，未把并行回归写成已登记遗留。交付变化仅为文档格式归一，15 条 AC 的测试与证据未受影响，逐条 re_verified 仍成立。本轮新发现：0 条；前轮 finding 复核：test 轴零 finding、code 轴 1 条 minor 已登记遗留、非 blocker；改测方向复核：无。

reviewed_scope: d432a53e9ed380fd

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`e2e.xml` 仍 101 testcase、两阶段 xdist 并行+串行收集 union 恰为全量，本轮无测试改动、收集集合不变。
- AC-002：TICK-VALID，re_verified。53 个时序敏感用例模块级 `pytestmark = pytest.mark.serial`、串行阶段 `-n 0 -m "serial"` 单进程执行，标注未变。
- AC-003：TICK-VALID，re_verified。worker 端口/子网互斥单测与最终门禁无容器/网络残留冲突证据未变，本轮无实现改动。
- AC-004：TICK-VALID，re_verified。`e2e.xml` 101 用例各带结果、t019 失败可定位，`manifest.json` 10 suite 名与退出码语义、`suites.tsv` 一致。
- AC-005：TICK-VALID，re_verified。`e2e.xml` 仅 2 个 t029 探针开关 skip、0 error、1 failure 为基线项；必跑/非必跑前置封闭单测未变。
- AC-006：TICK-VALID，re_verified。指纹平台 3 用例在 `e2e.xml` 真实 PASS、走 `CBROWSER_E2E_FONTS_DIR` 持久集，无 `.scratch` 依赖改动。
- AC-007：TICK-VALID，re_verified。`unit.xml` 1141 / `integration.xml` 全绿、集合与 collect 一致，本轮无测试改动。
- AC-008：TICK-VALID，re_verified。`t044_gate_final.log` 前后端组并发、e2e exit 1 时 `manifest.json` 逐 suite 记录、总退出码非零，证据文件未变。
- AC-009：TICK-VALID，re_verified。`environment.log` 仅 `reuse cached venv ... (no dependency download)`，共享 uv 缓存契约未变。
- AC-010：TICK-VALID，re_verified。t026 红测 + 单一 `RegistrationState` 对象 + 4 清理点静态断言，`unit.xml` 35 passed，无实现改动。
- AC-011：TICK-VALID，re_verified。requirements_check / image_packages 在 `manifest.json` 中 exit 0，锁漂移与镜像包比对单测未变。
- AC-012：TICK-VALID，re_verified。`error::DeprecationWarning` + 3 条精确第三方 ignore、源码无 `HTTP_422_UNPROCESSABLE_ENTITY`，门禁除基线 t019 外 0 failure。
- AC-013：TICK-VALID，re_verified。Selkies Docker SDK 边界 5 测（find 定位 / get_archive / 出错强制 remove）未变。
- AC-014：TICK-VALID，re_verified。fixture FROM 行与生产 `config/docker/api_runtime/Dockerfile` 全等断言，`unit.xml` PASS，无夹具改动。
- AC-015：TICK-VALID，re_verified。门禁前后受跟踪文件一致、`design:check` 过期失败路径、门禁无 `design:tokens` 步骤；本轮 specs_index 日期格式归一属门禁运行后的 finish 收尾文档操作，不在门禁运行窗口内。

coverage = re_verified / 15

verdict: PASS
