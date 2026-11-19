# Task review t092（reviewer_focus: 通用）

- task：`t092_real_engine_probe_font_fixture`
- spec：`docs/tasks/t092_real_engine_probe_font_fixture/task.md`
- diff_anchor：`f11e4f4f1857d8de7c8d832cdb81de41be5e6473`
- target：`git diff f11e4f4f1857d8de7c8d832cdb81de41be5e6473`
- round：1
- reviewed_at：2026-11-19T22:27:30+08:00

reviewed_scope: 13f35e130f50a287

## Findings

### t092_gen_f001 - 非法字体集目录可遮蔽同根有效字体集

- 严重度：minor
- 锚点：AC-002 的异常存储布局
- 位置：`scripts/automation_probe_evidence.py:79-84`、`src/backend/cbrowser/font_sets/manifest.py:399-416`
- 问题：先按登记时间选定默认集，再用 `get_font_set` 校验选中目录的 ID。用真实导入器生成两个字体集后，将较新集合手工改为非法目录名，校验文件内容仍成功，探针返回空并拒绝预检，较早有效集合仍在同一根目录。正常导入生成合法内容寻址目录，此异常只在手工改动资产布局后触发。
- 建议：按有效目录身份过滤候选，再使用共享默认选择规则。

## 结论

- 本轮新发现：1 条 minor。
- 未进表的提示：已复核契约、输入处理、资源边界、测试和文档，Shell 语法检查、Git diff 检查及探针相关单测 70 项通过。真实浏览器执行采用现有 JUnit 和探针证据复核，未另起容器。
- 总体判断：已导入的有效资产按同一字体集标识完成只读挂载和快照绑定，两项验收成立。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。以独立 Docker CLI 替身隔离容器后执行真实脚本预检，目录不存在、空目录和已导入资产字节遭修改三种输入均退出 2，预检只报告缺字体且未进入执行阶段。
- AC-002：TICK-VALID，re_verified。独立复跑快照测试验证绑定字段，查证 `scripts/run_automation_probe.sh:124-132` 使用同一 ID 拼出只读挂载和快照环境，独立解析已有 arm64 探针 JUnit 为 2 通过、链路子套件 16 通过、均零跳过。

coverage = 2 / 2

verdict: PASS

## Round 2 (2026-11-20T01:44:18+08:00)

reviewed_scope: f3326e6656a24b73

### 前轮 finding 复核

- t092_gen_f001（非法/非规范字体集目录遮蔽同根有效集）：已消除。`select_probe_font_set`（`scripts/automation_probe_evidence.py:73-97`）不再先按时间选默认集再校验目录名，而是对每个候选执行 `get_font_set` 并以 `compute_set_id(manifest["files"]) == item["set_id"]` 交叉校验集合身份：非法目录名被 `SET_ID_PATTERN` 拒绝，非规范 64-hex 目录（`test_newer_noncanonical_directory_does_not_shadow_valid_asset` 中 `"a"*64`）因内容哈希不符被拒，损坏资产被 `integrity.ok` 过滤；仅身份自洽的候选进入 `pick_default_font_set`。根因（信任目录名作集合身份而无内容校验）已消除。
- 验证证据：`tests/unit/test_a38_probe_evidence.py:155-179` 的 `test_newer_noncanonical_directory_does_not_shadow_valid_asset` 用真实导入器生成两个集合、将较新集合目录重命名为非规范名后断言选中较早有效集合，全程无 mock。独立执行 `pytest tests/unit/test_a38_probe_evidence.py::test_newer_noncanonical_directory_does_not_shadow_valid_asset` 与 `::test_newer_directory_with_invalid_id_does_not_shadow_valid_asset` 均 PASSED；`test_a38_probe_evidence.py` + `test_automation_probe_harness.py` 共 38 项全绿。

### 本轮新发现

本轮新发现：0 条。修复集中在 `select_probe_font_set` 重写及两条新测试，未引入新问题。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`scripts/automation_probe_evidence.py:73-97` 对空/损坏/非 windows 资产返回 None（`test_probe_selects_only_integrity_verified_windows_fonts` 覆盖），`preflight_problems` 增补字体缺失项（`test_preflight_rejects_missing_verified_font_asset` 覆盖），`scripts/run_automation_probe.sh:74-81` 在必跑模式以 exit 2 结束；相关单测独立跑通过。
- AC-002：TICK-VALID，re_verified。`scripts/run_automation_probe.sh:124,128,132` 用同一 `font_set_id` 完成只读挂载与快照 env 绑定，`test_probe_snapshot_binds_selected_font_set` 断言快照写入 `fingerprint_platform=windows` 与 `font_set_id`；`evaluate_evidence` 的 JUnit 门禁拒绝 skip/xfail，相关单测独立跑通过。

coverage = 2 / 2

verdict: PASS
