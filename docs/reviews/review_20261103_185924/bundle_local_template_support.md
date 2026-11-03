# bundle_local_template_support

## responsibilities

- 模板支撑面：repo_template 工具链对宿主与消费者的全部声明性接口——15 个 skill 的 canonical 正文（SKILL.md）、技能注册表（registry.json，角色与调用图唯一事实源）、12 个由 SKILL.md description 生成的 OpenCode 命令入口、模板文档（architecture.md 执行拓扑、usage.md 消费手册）、review prompt 模板（code/test/general/share 四件）、task 与 spike 报告模板、md 格式门禁 pre-commit hook、Claude Code 状态行 hook 接线（.claude/settings.json）与 md_kx 格式配置（.md_kx.toml）。
- 本单元不含实现脚本本体（task.py/repo_sync.py/md_format.py 等在其他单元）；它定义这些脚本的使用契约、授权边界与写权归属，是一致性与文档纪律的承载层。

## interfaces

- registry.json：skills 角色表（public 12 / internal 3）+ calls 调用边 7 条，是 skill 组合契约的唯一权威
- SKILL.md front matter：name/description/disable-model-invocation；internal 技能另带 user-invocable: false；全部带 metadata.opencode/autoinvoke=false
- .opencode/commands/*.md：自动生成 stub（标注 repo_sync.py 生成、勿手改），经宿主 skill 工具加载对应 SKILL.md，透传 $ARGUMENTS
- review prompt 占位符集：{tid}/{slug}/{repo_root}/{diff_anchor}/{spec_path}/{task_dir}/{review_level}/{contract_section}/{context_section}/{review_scope_fingerprint}，由渲染器注入后派给 reviewer
- task_template/note.md front matter schema：tid/slug/title/status/branch/worktree/review_level/review_limit/verify_limit/diff_anchor/depends_on/conflicts_with，只经 task.py 修改
- pre-commit hook 进程契约：exit 0 放行 / exit 1 阻断并在 stderr 给出原因与修复提示

## dependencies

- .repo_template/scripts/ 下的实现（task.py、pending.py、repo_sync.py、md_format.py、track_worktree.py、skill_registry.py 等，均在本单元外，被本单元文件广泛引用为权威实现）
- 外部二进制 md_kx（PATH 上独立工具，.md_kx.toml 为其仓库级配置）
- 宿主加载面：.claude/skills/ 与 .agents/skills/ 下指向 .repo_template/skills/ 的软链（已实查：两处各 15 条软链齐全且目标正确，share_prompt.txt 引用的 .agents/skills/task-work/SKILL.md 路径可达）
- Git 2.38+ 语义（merge-tree、diff rename 检测）与 core.hooksPath 安装状态

## flows

- 用户入口 → OpenCode 命令或宿主 skill 入口 → 按 registry 调用边由父流程直接读取子流程 canonical SKILL.md 执行（禁止宿主原生 Skill 工具嵌套调用，授权不经组合扩大）
- task 生命周期：task-create 立项 → task-schedule 写图 → task-run 串行 start/reserve/claim → task-work 在 worktree 实施并过测试/黑盒/review 三道门禁 → finish 一个执行 commit → task-integrate 经单独授权 merge
- 模板同步：repo-template-sync（启动器，解析并固定来源 SHA）→ 直接读取来源 repo-template-sync-core → status/plan/裁定/apply 事务/审批
- 提交路径：git commit →（hooksPath 已安装时）pre-commit 对 staged .md 跑 md_kx 格式化并重新暂存，工作区与 index 不一致则拒绝

## constraints

- registry.json 是角色与调用图的唯一事实源；正文 prose 声称的调用关系不产生授权（usage.md「只接受注册调用边」）
- merge 必须另行获得用户明确授权，不包含在 task-run 启动授权内；破坏性操作（cleanup/hygiene/pending 归档）默认 dry-run 或先确认
- front matter 只经脚本修改；派生文件（opencode 命令、usage.md 中 skill_registry 表、tasks_index）只由生成器维护，禁止手改
- 模板占位示例不得占用真实 tid/sid/pNNN 编号（usage.md 命名与格式节）

## decisions

- review 质量门禁设计：share_prompt.txt 以 reviewed_scope 指纹绑定 PASS 有效性（交付内容变化即 PASS 失效）、blocking 硬阈值（须锚定 AC 或给出可观测行为缺陷）、AC 复验方式强制披露（re_verified/trust_prior 及覆盖率）
- AGENTS.md 同步三分区协议：项目介绍绝不更新、目录与读写规则只报差异由 Agent 语义合并、开发原则每次同步强制更新（usage.md）
- 严重度三级（critical/important/minor）+ 危险测试模式最低 important 的统一标尺，由 code/test/general 三份 prompt 共享 share_prompt 规则

## evidence

- 注册表一致性逐项核对通过：registry.json 的 15 个 skill ↔ 15 份 SKILL.md ↔ usage.md 中 skill_registry 生成表的角色（用户入口 12 / 内部正文流程 3）↔ 12 个 .opencode/commands 文件，三者集合与角色完全一致；calls 的 7 条边与 usage.md 调用表逐条一致
- 12 个 opencode 命令的 description 与对应 SKILL.md 的 description 逐字一致（生成无漂移）；各 SKILL.md 正文内提到的跨 skill 调用（task-from-pending→bug-to-pending/task-create、pending-record→bug-to-pending、bug-to-pending→task-create、task-run→task-work/task-integrate、repo-template-sync→repo-template-sync-core）均有注册边
- .md_kx.toml 的 number/table_mode=compact/indent_width=4 与 usage.md 的格式声明一致；pre-commit 文件具可执行位（-rwxrwx---）
- 安全面 grep 核查：40 个文件无真实凭据、私有邮箱、本机绝对路径或 secret 值（仅有评审标准中对 secret 的泛称与 template-issue-report 的脱敏要求本身）
- tests 视角说明：本单元无可执行测试文件；其测试相关内容为规范性文本（test_prompt.txt、task-work 的项目测试门禁、share_prompt 的危险模式标尺），已全量阅读并按测试可信/危险模式标准审阅，未见与 AGENTS.md 的 TDD 纪律冲突的表述
- .repo_template/hooks/pre-commit:22-46 的 staged 选择、脏检与重新暂存逻辑，以及 .claude/settings.json:1-17 的 PostToolUse 接线均已逐行阅读

## uncertainties

- usage.md 称 opencode 命令在改 SKILL.md 后重跑 `link-skills` 再生，而生成文件头标注为 repo_sync.py 生成；link-skills 是 repo_sync.py 的子命令还是独立脚本，在本单元文本内无从判定（实现脚本在其他单元），两个名称未在任何单元内文本中互相说明
- usage.md 对状态行 hook 的「毫秒级短路/零副作用」行为声明，其实现 track_worktree.py 在本单元外，仅核对了 .claude/settings.json 的接线，未核对脚本本体
- review prompt 的占位符替换与指纹计算实现（render_review_prompts.py / check_review_status.py，在本单元外）未核对；本单元只按模板文本审阅 prompt 本身

## Findings

- [Low][90] .repo_template/skills/bug-to-pending/SKILL.md:20 — bug-to-pending 声称 task-work 是其 analysis-only 模式的内部调用方，但注册表无此调用边且 task-work 正文从不引用它
  - ID: f_template_support_01; verification: static
  - Evidence: .repo_template/skills/bug-to-pending/SKILL.md:20 称 analysis-only 模式「供 `task-work`、`pending-record` 等内部调用」; .repo_template/skills/registry.json 的 calls 数组中指向 bug-to-pending 的边只有 task-from-pending→bug-to-pending 与 pending-record→bug-to-pending，无 task-work→bug-to-pending; grep 核实 task-work 与 task-run 的 SKILL.md 全文均未出现 bug-to-pending；task-work 实施步 6 只泛称「登记 pending 或 finding」; usage.md 与 architecture.md 均声明 registry.json 是角色/调用图唯一事实源、「只接受注册调用边」
  - Impact: 权威注册表与 skill 正文对同一调用关系给出相反结论：按正文行事的 agent 会走一条未注册的组合路径，按注册表行事则该模式的一个声称调用方永远不会触发；后续维护者无法判断应补注册边还是删正文声明，组合契约的可信度被削弱。
  - Fix: 二选一并保持单一权威：若 task-work 确应在遇 bug 时走 analysis-only，则在 registry.json 补 task-work→bug-to-pending 边并在 task-work 正文写明调用点；否则删除 bug-to-pending 第 20 行中对 task-work 的声称。

- [Low][95] .repo_template/docs/usage.md:51 — usage.md 称 commit 由 pre-commit hook「强制」执行 md 格式门禁，但本仓未启用 hooksPath，门禁实际未生效
  - ID: f_template_support_02; verification: static
  - Evidence: .repo_template/docs/usage.md:51 写「commit 由 pre-commit hook 强制（.repo_template/hooks/pre-commit …）」，同句后半才提到需先 repo_sync.py install-hooks 启用 core.hooksPath; 本仓实查：git config core.hooksPath 未设置（退出码 1），.git/hooks/ 下只有 *.sample 文件，无生效的 pre-commit; AGENTS.md 与 usage.md 多处流程（md 格式统一、commit 前 --check 为绿）以该 hook 的强制存在为前提叙述
  - Impact: 在当前消费仓克隆中，md_kx 格式门禁并不像文档所述那样被强制：未格式化的 Markdown 可直接提交，后续同步/合并时才以格式漂移形式暴露；「强制」表述使读者高估门禁的实际覆盖（hooksPath 是逐克隆本地配置，任何新克隆默认同样未启用）。
  - Fix: 在本仓执行 install-hooks 启用门禁，或把 usage.md 的表述改为与状态一致的条件式说明（如「启用 hooksPath 后，commit 由 pre-commit hook 强制」），并在消费仓接入清单中把 install-hooks 列为必做项。

- [Low][85] .repo_template/hooks/pre-commit:18 — pre-commit 在模块顶层无条件 import md_format，模块缺失或导入失败时将阻断全部提交（含不涉及 .md 的提交）
  - ID: f_template_support_03; verification: static
  - Evidence: .repo_template/hooks/pre-commit:15-18 在顶层组装 sys.path 并 `import md_format`，发生在 main() 的「staged 无 .md 时快速放行」判断（第 49-52 行）之前; 文件 docstring 声明的行为是「staged 无 .md 时快速放行；有 .md 但格式化失败（含 md_kx 缺失）阻断提交并引导安装」——md_kx 二进制缺失由 format_paths 抛 MdFormatError 处理（第 60-63 行），但 md_format 模块本身缺失/损坏不在此列; 模板被部分复制、scripts/ 不完整或 md_format.py 引入新的导入错误时，hook 以未捕获的 ImportError 栈退出非零，git 对所有 commit 一律拒绝
  - Impact: 门禁脚本的故障域大于其职责域：一个只应管 Markdown 格式的 hook 能在模板状态异常时冻结整个仓库的提交能力，且报错是 Python 栈而非 docstring 承诺的安装引导，增加排查成本。
  - Fix: 把 import md_format 延迟到 staged_md() 确认存在 staged .md 之后（或包一层 try/except，导入失败时输出与 MdFormatError 一致的引导信息再退出 1）；无 .md 的提交应在任何模板模块加载前直接放行。

- [Low][75] .repo_template/hooks/pre-commit:31 — pre-commit 的 staged 文件选择用 --diff-filter=ACM，纯重命名或重命名加修改的 .md 会绕过格式门禁
  - ID: f_template_support_04; verification: static
  - Evidence: .repo_template/hooks/pre-commit:31 用 `git diff --cached --name-only -z --diff-filter=ACM -- *.md` 选文件，过滤器不含 R（rename）; Git 在 diff 中默认开启重命名检测（diff.renames 自 Git 2.9 默认 true）：重命名且改内容的 .md 以 R 状态出现，被 ACM 过滤静默排除，既不格式化也不做 dirty_vs_index 检查; docstring 与 usage.md 对该 hook 的描述均为「格式化本次 commit 涉及的 .md」，未声明排除重命名
  - Impact: 通过 git mv 并顺手改内容的 Markdown 文件可未经 md_kx 格式化进入仓库，与门禁宣称的覆盖范围不符；影响仅限格式一致性，故评 Low。注：若消费仓显式关闭 diff.renames，文件会以 A+D 出现而被捕获，故该缺口与本地 git 配置相关。
  - Fix: 将过滤器改为 ACMR（或去掉 --diff-filter 并在代码中排除 D），并对 R 的新路径取 diff 的目标路径格式化；同时补一条重命名场景的说明或测试。

- [Info][80] .repo_template/docs/spike_report_template.md:27 — spike 报告模板用「如 t001」作后续 task 示例编号，与 usage.md「占位示例不得占用真实 tid」的命名规则相冲突
  - ID: f_template_support_05; verification: static
  - Evidence: .repo_template/docs/spike_report_template.md:27 写「后续 task：{采纳时填写 {tid}，如 t001；否则写“无”}」，把真实编号段的 t001 用作示例; .repo_template/docs/usage.md 命名与格式节规定「占位示例（模板、示例行）不得占用真实 tid / sid / pNNN，也不得当作 active 工作项执行」; 同为模板的 task_template/note.md 则使用 t000 作占位 tid，与规则一致，两模板口径不一致
  - Impact: 影响极小：读者可能把示例 t001 误认作真实引用目标，或在复制模板时把示例值带入正式 spike 报告，造成一条指向无关 task 的假关联。
  - Fix: 把 spike_report_template.md 的示例改为不占用真实编号的写法（如「如 {tid}」或 t000），与 task_template 的占位口径统一。

## views

```json
{
  "contracts": {
    "reviewer": "83a6c941-b4d1-48c5-89aa-f0a47ac04a06",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "83a6c941-b4d1-48c5-89aa-f0a47ac04a06",
    "status": "completed"
  },
  "design": {
    "reviewer": "83a6c941-b4d1-48c5-89aa-f0a47ac04a06",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "83a6c941-b4d1-48c5-89aa-f0a47ac04a06",
    "status": "completed"
  },
  "performance": {
    "reviewer": "83a6c941-b4d1-48c5-89aa-f0a47ac04a06",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "83a6c941-b4d1-48c5-89aa-f0a47ac04a06",
    "status": "completed"
  },
  "security": {
    "reviewer": "83a6c941-b4d1-48c5-89aa-f0a47ac04a06",
    "status": "completed"
  },
  "tests": {
    "reviewer": "83a6c941-b4d1-48c5-89aa-f0a47ac04a06",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  ".claude/settings.json",
  ".md_kx.toml",
  ".opencode/commands/bug-to-pending.md",
  ".opencode/commands/pending-record.md",
  ".opencode/commands/repo-cleanup.md",
  ".opencode/commands/repo-hygiene.md",
  ".opencode/commands/repo-template-sync.md",
  ".opencode/commands/task-create.md",
  ".opencode/commands/task-from-pending.md",
  ".opencode/commands/task-merge.md",
  ".opencode/commands/task-preflight.md",
  ".opencode/commands/task-run.md",
  ".opencode/commands/task-schedule.md",
  ".opencode/commands/template-issue-report.md",
  ".repo_template/docs/architecture.md",
  ".repo_template/docs/review_prompts/code_prompt.txt",
  ".repo_template/docs/review_prompts/general_prompt.txt",
  ".repo_template/docs/review_prompts/share_prompt.txt",
  ".repo_template/docs/review_prompts/test_prompt.txt",
  ".repo_template/docs/spike_report_template.md",
  ".repo_template/docs/task_template/note.md",
  ".repo_template/docs/task_template/task.md",
  ".repo_template/docs/usage.md",
  ".repo_template/hooks/pre-commit",
  ".repo_template/skills/bug-to-pending/SKILL.md",
  ".repo_template/skills/pending-record/SKILL.md",
  ".repo_template/skills/registry.json",
  ".repo_template/skills/repo-cleanup/SKILL.md",
  ".repo_template/skills/repo-hygiene/SKILL.md",
  ".repo_template/skills/repo-template-sync-core/SKILL.md",
  ".repo_template/skills/repo-template-sync/SKILL.md",
  ".repo_template/skills/task-create/SKILL.md",
  ".repo_template/skills/task-from-pending/SKILL.md",
  ".repo_template/skills/task-integrate/SKILL.md",
  ".repo_template/skills/task-merge/SKILL.md",
  ".repo_template/skills/task-preflight/SKILL.md",
  ".repo_template/skills/task-run/SKILL.md",
  ".repo_template/skills/task-schedule/SKILL.md",
  ".repo_template/skills/task-work/SKILL.md",
  ".repo_template/skills/template-issue-report/SKILL.md"
]
```
