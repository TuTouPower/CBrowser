# bundle_followup_q_evolution_02

## Summary

精查证实：仓内不存在 doctor 文档一致性校验（doctor_cmd 只是环境预检），结构一致性来自任务收尾硬校验与索引重建；门禁命令在任务生命周期内从未被执行（新 Medium）。

## Findings

- [Medium][80] .repo_template/scripts/repo_task/validation.py:62-77 (run_checks) 与其全部调用点 — 门禁命令（doctor_cmd/test_cmd/blackbox_verify）在 task 流程内从不被执行，唯一执行器是模板同步路径
  - ID: f_followup_q_evolution_02_01; verification: static
  - Evidence: 全仓 grep 显示 validation.run_checks 仅被 repo_sync.py:1893 与 1961 调用（repo-template 同步 apply 流程）；task.py 的 preflight/finish/integrate 路径只调 load_policy/parse_policy 校验 testing.md 章节形状（lifecycle.py:434-439、530-531；integration.py:131-133、219-221），不执行命令本体。; 本仓其余自动执行路径均缺席：ci.yml 两 job 指向不存在的 backend/、frontend/ 路径且不引用 .repo_template；pre-commit hook 只做 md_format 且在本 clone 未激活（core.hooksPath 未设）。; 后果：testing.md 自述的『质量门禁』在本仓的实际触发完全依赖 repo_sync 运行或 agent 按 skill 口头流程手动执行，task 状态机自身从不验证门禁是否跑过——门禁存在性被 parse 校验冒充为门禁执行（与 template_tests 单元『fixture 中 configure_project_verification 禁用全部项目门禁』互为表里）。
  - Impact: 项目以 AGENTS.md/testing.md 把 doctor_cmd/test_cmd 宣称为门禁锚点，但任何一次 task 收尾都可以在从未运行这些命令的情况下通过形状校验；契约套件与黑盒验证是否真的执行过，只能靠执行者自述，仓库内无机械证据。
  - Fix: 在 task finish/preflight 的验证环节实际调用 run_checks（或记录其在 exact attempt 内的运行证据并由 finish 校验），至少让 test_cmd 成为收尾硬门；或在 testing.md/AGENTS.md 中如实降级表述为『由执行者手动运行的命令清单』而非门禁。（验证：static：grep run_checks/load_policy/parse_policy 全部调用点 + 阅读 lifecycle.py/integration.py 对应代码段确认无命令执行路径。）

## evidence

```json
[
  "不存在 repo_task/task.py 的 doctor 子命令：task.py --help 的子命令清单（recovery/add/start/preflight/finish/... 共 26 个）无 doctor；『doctor』只是 docs/blueprint/testing.md 中 doctor_cmd 章节的项目自定义命令块，由 .repo_template/scripts/repo_task/validation.py 的 run_checks() 以 bash -e -o pipefail 执行。",
  "doctor_cmd 本体只做环境前置、零文档一致性校验（testing.md:29-37 自述『环境前置检查』）：两条实质命令是 `pytest .repo_template/tests -q --collect-only -m contract`（仅收集契约测试、并不运行）与 `command -v md_kx`（确认格式化二进制在 PATH），另加一个开发者个人路径的 TMPDIR。它不校验任何索引、目录或文档内容。",
  "结构校验确实存在，但不在 doctor 里，而在 task 状态机的写/收尾路径：(1) specs_index↔spec 文件——finalization.py:49-81 在 task finish 时硬校验（specs_index 缺失、行格式错误/重复、引用不存在的 spec、当前 task 未入索引且 note 无 not_applicable 说明均 raise）；(2) tasks_index.json——由 store.rebuild_index() 在 graph.py:80、integration.py:394/578、lifecycle.py 多处状态变更后派生重建，一致性靠构造而非校验；(3) handoff 新鲜度无任何自动校验（docs_current 单元为人工实查）。",
  "契约套件（-m contract，test_cmd 与 repo_sync 实际运行的门禁）对真实仓的文档类校验仅限『门禁命令的形状』：test_contract_suite.py:74-97 断言真实 testing.md 的 doctor 章节 pytest 行恰为 collect-only 行、含 command -v md_kx、test_cmd 的 pytest 行恰为 contract 行（本仓无 sync_state.json，该用例不跳过）；其余 contract 模块（task_save/unverified/document_validation/archive_dir/plan/view_server/check_review_status/repo_cleanup）均在 fake repo/fixture 上测状态机，不读真实仓文档内容。",
  "blueprint 内容断言零交叉校验（问题给出的降级反证条件不成立）：grep `failure_count` 于 .repo_template/tests/ 与 .repo_template/scripts/ 零命中；无任何测试或脚本读取 docs/blueprint/*.md 的内容断言（阈值、级联语义、交付状态）与代码/ADR/spec 对照；门禁唯一读取的 blueprint 文件是 testing.md 本身且只看门禁命令出行。md_format 只管 Markdown 格式（表格 compact/标题语法），不管语义。",
  "执行接线在本仓基本缺席：validation.run_checks（三个门禁命令的唯一执行器）全仓只有 repo_sync.py:1893/1961 两处调用（模板同步流程）；task lifecycle/integration 对 testing.md 只调 load_policy/parse_policy 做『章节存在且为可执行 bash 块』的形状校验（lifecycle.py:434-439/530-531、integration.py:131-133/219-221），从不执行门禁命令本体；.github/workflows/ci.yml 两 job 引用重组前不存在的 backend/、frontend/ 路径，不含 doctor/contract/.repo_template 任何字样；.repo_template/hooks/pre-commit 只做 staged .md 的 md_format，且本 clone 未设 core.hooksPath（git config 返回空）、.git/hooks 只有 samples，hook 实际未生效（与 template_support 单元结论一致）。",
  "template_tests 对 doctor 的覆盖与上述分工一致：test_contract_suite 测真实 testing.md 的命令形状，test_task_start_flow 测 fake testing.md 的章节占位/缺失检出（_missing_testing_sections 语义），review_support.py 的 fake 仓把三门禁直接写『无』；没有任何用例断言 doctor 能发现文档内容失真。"
]
```

## result

```json
"confirmed"
```

## limitations

```json
[
  "静态审阅：未实际运行 task.py finish、repo_sync 或契约套件，『finish 时 specs_index 校验真实触发』『run_checks 经 repo_sync 可正常执行』均为代码路径推断，无运行记录佐证（仓内亦未检索到门禁运行日志类工件）。",
  "skill 层（.repo_template/skills/*/SKILL.md）可能以流程文本要求 agent 手动执行 test_cmd 并记录验证证据；本精查核对的是脚本/CI/hook 的机械接线，skill 文本级要求未逐份通读，故 finding 01 表述限于『无机械执行/校验路径』，不否定流程文本层面的要求存在。",
  "其他消费仓可能以 sync_state.json 定制 testing.md 并自建 CI 接线；本结论仅限 CBrowser 本仓当前 HEAD。"
]
```
