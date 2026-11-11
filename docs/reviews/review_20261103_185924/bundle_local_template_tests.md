# bundle_local_template_tests

## responsibilities

- 本单元是 .repo_template 工具链（task.py / repo_task 包 / repo_sync / repo_cleanup / 看板 view_server / precommit hook / md 格式化等脚本）自身的回归与契约测试套件，共 32 个模板侧文件，外加产品仓根 tests/unit/test_repo_hygiene.py 这一个隐私守卫测试。
- 测试风格以行为级断言为主：大量用例在 tmp_path 里建真实 git 仓库、经子进程跑真实 CLI（task.py、hook、repo_state.py），断言退出码、stderr 关键文案、front matter 字段、ledger 事件与文件系统终态；纯函数层（compute_batch_plan、compute_schedule、front matter 编解码、未知契约解析、看板 classify）走进程内单测。
- pytest.ini 只注册 contract marker：9 个模块（test_contract_suite 的 allowlist）构成消费仓轻量契约（不起真实 HTTP 服务，多数不建真实 worktree），其余重型真实 git 套件不在该契约内——这是 pytest.ini 注释明示的设计口径，不是遗漏。
- 安全回归密度高：tar 解包穿越/软链/硬链接拒绝、sync_dir 软链目标拒绝、spec 路径越界与软链逃逸拒绝、原子写拒绝软链目标、看板 /task-doc session token 与非 loopback 绑定门禁、.env 受控软链识别等均有专门用例。

## interfaces

- 被测公开面：.repo_template/scripts/task.py CLI 子命令（start/finish/integrate/integrate-chain/cleanup-worktree/attempt/preflight/view/list/show/add/edit/drop/rewind/limits/recovery/goal 等）、repo_task 包内模块函数（documents/scheduling/monitoring/store/integration/lifecycle/view_server 等）、repo_sync.py 与 check_review_status.py 的模块级函数与常量。
- 测试间接口：test_workflow_contracts.py 直接 import test_dispatch_integration 的 git_repo fixture 与 \_git/\_task_cli/\_prepare_done/\_cleanup/\_reserve/\_handoff/\_read_ledger 等下划线私有 helper；test_task_scheduling.py 与多处 fixture import review_support 的 configure_project_verification。
- 共享 fixture 契约：review_support.ensure_review_evidence(worktree, task_dir, anchor) 为真实 git fixture 合成 review 证据；configure_project_verification(repo) 统一改写 fixture 仓的 docs/blueprint/testing.md 与 specs_index 豁免。

## dependencies

- pytest（含 contract marker）、git CLI、node（test_chain_plan 的 JS 展示辅助回归，缺失时 skipif 跳过）、python 标准库 subprocess/shutil/tarfile 等。
- 被测脚本位于 .repo_template/scripts/（task.py、repo_task/、repo_sync.py 等），测试经 sys.path.insert 注入 SCRIPTS_DIR 后 import，或以子进程方式执行其副本。
- tests/unit/test_repo_hygiene.py 依赖 git ls-files 列举 tracked 文件，并读取同目录 review_privacy_allowlist.txt。

## flows

- 典型端到端流（test_dispatch_integration/test_task_start_flow/test_workflow_contracts）：建仓→写 task→start→attempt reserve→改 worktree→finish→ensure_review_evidence 合成 PASS 证据→写 handoff→commit→terminal→report→cleanup-worktree→integrate/integrate-chain→断言 ledger integrated 事件与分支清理。
- 失败补偿流：monkeypatch 注入 worktree 创建/软链/索引重建/目录移动/shutil.move/os.replace/os.fsync 失败，断言主仓未修改、front matter 回滚、临时文件清理、审计标记（rewind_failed）落盘。
- 契约流（contract marker 子集）：collect-only 子进程核对 allowlist 模块集合、sync 默认命令与 CONSUMER_TEST_COMMAND 一致、全部 skill 带 disable-model-invocation。

## constraints

- 本轮为静态审阅：未运行任何测试/构建，套件在 HEAD b473408 的实际通过状态未经执行验证。
- AGENTS.md 仓规要求 TDD 纪律（禁止就地把旧测试预期改成实现输出）；套件中确有带归因注释的改测（如 test_task_start_flow 中 RT-006 改写 reserve 顺序语义并注明原用例固化的是被审查判定为 bug 的行为），属有归因改测。
- contract 子集须保持轻量：不起真实 HTTP 服务（test_view_server 只测纯函数与 FakeHandler），不建真实 git worktree 的模块才可入册。

## decisions

- review_support.ensure_review_evidence 只在证据文件不存在时写入，调用方刻意提供的 stale/FAIL 证据不会被覆盖——合成 PASS 与负向证据测试因此可以共存。
- fixture 仓统一经 configure_project_verification 把项目验证门禁设为「无」，理由写在 testing.md 里：隔离 Git 契约场景，断言由外层 pytest 执行。
- test_dispatch_integration 中保留了一段注释，记录曾删除一个『假绿』escalated 手工 integrate 测试及删除理由，显示套件维护者对假绿有自觉清理。
- test_chain_plan 的 JS 文件只做展示辅助回归，调度算法权威测试在 test_plan.py，避免双份权威。

## evidence

- .repo_template/tests/review_support.py:13-35 合成证据与关闭门禁的 fixture 逻辑
- .repo_template/tests/test_task_start_flow.py:1234-1265 drop 索引重建失败用例未驱动 cmd_drop 且断言为析取式
- .repo_template/tests/test_contract_suite.py:99-105 co_names 字节码名字表断言
- tests/unit/test_repo_hygiene.py:9-33 隐私守卫正则与 8192 字节二进制判定
- .repo_template/tests/test_workflow_contracts.py:7-10 跨测试模块 import 私有 helper
- .repo_template/tests/test_check_review_status.py:351,419,489,506,521,538,558,574,589,613 main 路径大面积 monkeypatch current_scope_fingerprint
- .repo_template/tests/pytest.ini contract marker 的适用范围声明

## uncertainties

- 静态审阅未执行套件：各用例在当前 HEAD 是否真实通过、是否有 skip/xfail 掩盖失败，未核实；finding 均为代码阅读层面的测试可信度判断，不代表有用例当前正在失败。
- ensure_review_evidence 合成 PASS 的影响范围取决于被测脚本里还有哪些路径会自行产生/校验 review 证据（如 finish/cleanup 的 report 内容校验在 test_workflow_contracts 有单独用例读真实 report 文件）；本单元内证据指向『生产侧审阅者产出证据』这一环确实从未在 E2E 中被真实执行，但其严重度最终取决于其他单元对该生产路径的覆盖，未在本单元范围内核实。
- test_view_server 的 serve 相关用例用 FakeServer 替代 ThreadingHTTPServer，真实 HTTP 绑定/并发行为不在本单元覆盖内（与 pytest.ini 不起真实 HTTP 服务的口径一致），是否另有集成覆盖未核实。

## Findings

- [Medium][80] .repo_template/tests/review_support.py:13-35 — 真实 git 端到端套件的 review PASS 证据由测试支持代码合成、项目验证门禁被整体关闭，生产侧『审阅产出证据+执行项目验证命令』路径从未被端到端执行

    - ID: f_template_tests_01; verification: static
    - Evidence: ensure_review_evidence 计算真实 scope 指纹后，直接写出内容为 '## Round 1\\nreviewed_scope: {scope}\\nverdict: PASS' 的 review_code.md/review_test.md/review_general.md，不存在任何审阅者环节; configure_project_verification 把每个真实 git fixture 仓的 testing.md 中 doctor_cmd/test_cmd/blackbox_verify 全部写为『无』，并给每个 task 追加 specs_index not_applicable 豁免行；test_dispatch_integration、test_task_start_flow、test_task_scheduling、test_goal、test_evidence_repair 等全部真实 git 套件都调用它; 缓解事实：指纹是按真实内容算出的（非写死），且函数明确不覆盖已存在的 stale/FAIL 证据；test_check_review_status、test_evidence_repair、test_review_scope_fingerprint 对门禁校验逻辑本身（stale 拒绝、FAIL 拒绝、amend 修复）有扎实覆盖——缺的是『证据由真实审阅产生』与『项目验证命令被真实执行』这两环
    - Impact: task 工作流最核心的质量门禁（review 证据产生、项目 test_cmd/blackbox 命令执行）在整套 E2E 中恒为合成 PASS/无命令状态：若生产代码在调用审阅者、解析真实 review 报告或执行项目验证命令的环节退化，这套测试仍会全绿。门禁校验逻辑有覆盖，但门禁的上游产出链没有。
    - Fix: 至少补少量冒烟级端到端用例：fixture 仓配置真实可执行的 test_cmd（如一条必然通过/必然失败的命令），断言 finish/report 流真的执行该命令且失败时被门禁拒绝；review 证据侧保留合成方式时，在 review_support docstring 与套件文档中显式声明该边界，避免读者高估覆盖。

- [Medium][85] .repo_template/tests/test_task_start_flow.py:1234-1265 — test_drop_keeps_archived_state_when_index_rebuild_fails 未驱动 cmd_drop 本身且最终断言为析取式，标题声称的回归实际未被覆盖

    - ID: f_template_tests_02; verification: static
    - Evidence: 用例没有调用 lifecycle.cmd_drop：它手动 store.load_task 后用 shutil.move 把目录搬到 archive，再直接调用被 monkeypatch 成抛 OSError 的 rebuild_index，验证的只是『rebuild_index 抛错不改 front matter』; 函数前半段定义的 fake_rebuild_index 与 calls 计数器从未被使用（死脚手架），注释自承『改为在主仓 patch 后经进程内调用验证』; 关键断言为 assert got['status'] in ('dropped', 'backlog')：无论 drop 实现把状态写成 dropped 还是干脆没写，都通过，无法区分『归档状态保持』与『状态根本没落盘』; 对照：紧邻的 test_drop_moves_back_front_matter_when_archive_move_fails（1267 行起）确实驱动了 cmd_drop 并断言确切状态，说明本用例的写法是孤例而非套件惯例
    - Impact: 『drop 在索引重建失败时保持已归档状态并报告索引待修复』这一行为若在 cmd_drop 内退化（如重建失败时反向搬回目录、或异常被吞），不会有任何用例变红；该用例给人已覆盖的印象，属于验证假行为。
    - Fix: 改用子进程或进程内调用真实 cmd_drop：在 drop 完成目录移动后让 rebuild_index 抛错（patch lifecycle 模块内引用），断言退出信息含『索引待修复』类提示、目录留在 archive、front matter status 恰为 'dropped'（单一值断言），并删除未使用的 fake_rebuild_index 脚手架。

- [Low][90] .repo_template/tests/test_contract_suite.py:99-105 — 用 __code__.co_names 字节码名字表断言 repo_sync.\_run_tests 引用了 CONSUMER_TEST_COMMAND，是白盒脆弱断言

    - ID: f_template_tests_03; verification: static
    - Evidence: test_sync_apply_runs_contract_suite 取 rs.\_run_tests.__code__.co_names 并断言 'CONSUMER_TEST_COMMAND' 在其中，只证明函数字节码的名字表里出现过该常量名，不证明运行时真的用它拼了测试命令; 等价重构（别名导入、getattr、把常量内联到另一 helper）会让用例变红而行为不变；反之保留一个无用引用也能让用例保持绿而行为已改
    - Impact: 契约套件中最关键的一条『sync apply 真跑契约测试命令』保证实际由实现细节而非行为背书，重构时产生假红、行为漂移时可能假绿，侵蚀 contract marker 子集的可信度。
    - Fix: 改为行为断言：在 tmp 仓上以可观察方式运行 \_run_tests/apply 路径（如注入假的命令执行记录点或用一个只含契约模块的最小仓断言其实际执行的命令与 CONSUMER_TEST_COMMAND 相等），或至少断言 \_run_tests 源码经 inspect 解析后该常量出现在命令构造表达式中。

- [Low][85] tests/unit/test_repo_hygiene.py:9-33 — 开发者 home 路径隐私守卫的覆盖边界多处收窄：仅匹配 /(Users|home)/<name>/、二进制判定只看前 8192 字节、docs/archive/ 整体豁免

    - ID: f_template_tests_04; verification: static
    - Evidence: HOME_PATH = re.compile(r'/(?:Users|home)/([A-Za-z0-9.\_-]+)/')：不匹配 /root/、Windows 盘符路径（C:\\Users\\...）、~ 相对写法与转义过的路径形态; tracked_text_files 只读文件前 8192 字节查 NUL 判二进制：文本文件若在前 8192 字节内含 NUL 会被整体跳过，其后出现的 home 路径泄漏不被检查；反之大文件第 8192 字节之后的泄漏虽能查到，但分类依据仅此一次嗅探; name.startswith('docs/archive/') 的文件整体跳过，注释称历史快照按约定不可变（A44）——属明示取舍，但意味着归档区新增内容同样不受守卫约束; allowlist 文件 review_privacy_allowlist.txt 在测试内被无条件读取，若该文件缺失整个守卫以异常失败而非跳过（fail-closed，可接受，但与守卫『静默守护』定位有张力）
    - Impact: 该守卫是公开仓防开发者路径泄漏的唯一自动化防线（视角1 开源隐私项）；其盲区形态（/root/、Windows 路径、含 NUL 的文本文件）恰是跨平台开发者最易真实泄漏的形态，守卫全绿不等于无泄漏。
    - Fix: 扩展正则覆盖 /root/ 与 Windows Users 路径；二进制判定改为对候选文本文件全量扫描（仓库规模下成本可控）或按扩展名+嗅探双判；对 docs/archive/ 豁免保留但在测试 docstring 中显式列明盲区清单，让豁免成为可审计的决定而非隐含行为。

- [Low][75] .repo_template/tests/test_workflow_contracts.py:7-10 — 测试模块间直接 import 另一测试模块的私有 helper 与 fixture，且 test_task_start_flow 另有一份近重复脚手架，双份维护易漂移

    - ID: f_template_tests_05; verification: static
    - Evidence: test_workflow_contracts 从 test_dispatch_integration import git_repo fixture 及 \_git、\_task_cli、\_prepare_done、\_cleanup、\_worktree、\_reserve、\_identity_args、\_handoff、\_read_ledger 共十个名字，其中九个是下划线私有 helper; test_task_start_flow.py 则自带一份功能高度重叠的 git_repo fixture 与 \_git/\_task_cli/\_reserve/\_handoff/\_terminal/\_worktree_path 实现（细节不同：模板拷贝方式、task 集合、testing.md 注入点均有差异），两份脚手架对同一被测流的准备步骤各行其是; test 收集依赖模块级 import 成功：test_dispatch_integration 顶层若引入导入期副作用或改名 helper，test_workflow_contracts 会在收集期整体失败而非单用例失败
    - Impact: 同一工作流的 fixture 语义存在两个权威版本：一处修了准备步骤（如 handoff 字段、review 证据注入方式）另一处不跟随，会造成两套测试对同一生产行为给出不同前提，回归定位成本上升；跨模块私有 import 也使重命名/拆分测试文件的成本被低估。
    - Fix: 把共享的 git_repo fixture 与 CLI/ledger helper 下沉到 conftest.py 或 review_support 一类的测试支持模块，两个套件共同引用；test_task_start_flow 的差异部分以参数或局部 fixture 覆盖表达，而不是整份复制。

- [Info][90] .repo_template/tests/test_check_review_status.py:351 — check_review_status 的 CLI/main 路径用例大面积 monkeypatch current_scope_fingerprint，CLI 层从不与真实指纹联跑（真实指纹在另一模块单独覆盖）

    - ID: f_template_tests_06; verification: static
    - Evidence: 351、419、489、506、521、538、558、574、589、613 行等十余处把 crs.current_scope_fingerprint 替换为返回常量 SCOPE 或 '0'\*16 的 lambda，main 系列用例的 scope 真值全部来自替身; 真实指纹的性质（排除 review 流程文件、note 正文不入指纹、模式位/软链入指纹、畸形元数据 fail-closed）由 test_review_scope_fingerprint.py 在函数层完整覆盖，因此这是分工事实而非覆盖空白
    - Impact: 若 check_review_status 与 monitoring 指纹实现之间的接线（参数顺序、anchor 传递、task_dir 相对路径）漂移，函数层与 CLI 层各自的测试都可能保持绿而集成已断；影响有限，记录为信息项供全局审阅参考。
    - Fix: 可保留现状；若要补强，只需在 test_check_review_status 增加一条不打 patch、走真实 git fixture 的 main 冒烟用例（stale 与 fresh 各一），把接线纳入回归。

## views

```json
{
  "contracts": {
    "reviewer": "a4cd442d-8af8-4431-9014-ddca0de55bac",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "a4cd442d-8af8-4431-9014-ddca0de55bac",
    "status": "completed"
  },
  "design": {
    "reviewer": "a4cd442d-8af8-4431-9014-ddca0de55bac",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "a4cd442d-8af8-4431-9014-ddca0de55bac",
    "status": "completed"
  },
  "performance": {
    "reviewer": "a4cd442d-8af8-4431-9014-ddca0de55bac",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "a4cd442d-8af8-4431-9014-ddca0de55bac",
    "status": "completed"
  },
  "security": {
    "reviewer": "a4cd442d-8af8-4431-9014-ddca0de55bac",
    "status": "completed"
  },
  "tests": {
    "reviewer": "a4cd442d-8af8-4431-9014-ddca0de55bac",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  ".repo_template/tests/fixtures/spec_pre_workflow_simplification.md",
  ".repo_template/tests/package.json",
  ".repo_template/tests/pytest.ini",
  ".repo_template/tests/review_support.py",
  ".repo_template/tests/test_chain_plan.py",
  ".repo_template/tests/test_chain_plan_cases.js",
  ".repo_template/tests/test_check_review_status.py",
  ".repo_template/tests/test_contract_suite.py",
  ".repo_template/tests/test_design_regressions.py",
  ".repo_template/tests/test_dispatch_integration.py",
  ".repo_template/tests/test_evidence_repair.py",
  ".repo_template/tests/test_goal.py",
  ".repo_template/tests/test_md_format.py",
  ".repo_template/tests/test_pending.py",
  ".repo_template/tests/test_plan.py",
  ".repo_template/tests/test_precommit_hook.py",
  ".repo_template/tests/test_render_review_prompts.py",
  ".repo_template/tests/test_repo_cleanup.py",
  ".repo_template/tests/test_repo_hygiene.py",
  ".repo_template/tests/test_repo_state.py",
  ".repo_template/tests/test_repo_sync.py",
  ".repo_template/tests/test_review_report_regressions.py",
  ".repo_template/tests/test_review_scope_fingerprint.py",
  ".repo_template/tests/test_task_archive_dir.py",
  ".repo_template/tests/test_task_document_validation.py",
  ".repo_template/tests/test_task_modularization.py",
  ".repo_template/tests/test_task_save.py",
  ".repo_template/tests/test_task_scheduling.py",
  ".repo_template/tests/test_task_start_flow.py",
  ".repo_template/tests/test_task_unverified.py",
  ".repo_template/tests/test_view_server.py",
  ".repo_template/tests/test_workflow_contracts.py",
  "tests/unit/test_repo_hygiene.py"
]
```
