# bundle_local_template_support

## responsibilities

- 本单元是 repo_template 工具链的支撑面：15 个 skill 正文（.repo_template/skills/*/SKILL.md）定义任务全生命周期流程（pending 登记、task 创建/调度/执行/合并/集成、仓库清理与卫生、模板同步、模板问题上报），registry.json 是角色与调用图的唯一事实源
- 模板文档层：usage.md 是消费仓使用接口与恢复权威，architecture.md 解释执行拓扑/attempt/review/合并机制，review_prompts/ 是 reviewer 提示词模板（code/test/general 三轴 + share 共享规则），task_template/ 与 spike_report_template.md 是工作项文件模板
- 宿主入口层：.opencode/commands/ 的 12 个文件是由 repo_sync.py 从 public skill 的 description 生成的 OpenCode 触发器存根；.claude/settings.json 配置 Claude Code 的 PostToolUse worktree 跟踪 hook；.repo_template/hooks/pre-commit 在 commit 时对 staged .md 执行 md_kx 格式化；.md_kx.toml 是格式化风格约定

## interfaces

- skill 组合契约：父流程直接读取子流程 canonical SKILL.md 正文执行，禁止经宿主原生 Skill 工具嵌套；调用边只接受 registry.json 登记的 7 条边，原样传递 tid/attempt/execution_id/owner_id/写域
- skill 到脚本的 CLI 接口：task.py（add/edit/preflight/effective-status/recovery/plan/view/start/attempt/limits/finish/merge-backlog/graph-transaction/goal/goal-check/ledger/review-upgrade/integrate/integrate-chain/cleanup-worktree）、pending.py（new --kind/archive --resolution --fix-ref --reason --write/park/rename）、findings.py new、spikes.py new、repo_cleanup.py scan/apply、repo_hygiene.py、repo_sync.py（status/plan/apply/install-hooks/link-skills/transaction）、skill_registry.py --write、md_format.py（--changed/--check 及 format_paths 库函数）、track_worktree.py --write --agent
- review prompt 渲染接口：四个 prompt 文件使用 {tid}/{repo_root}/{diff_anchor}/{spec_path}/{task_dir}/{task_dir_rel}/{slug}/{review_level} 占位符，share_prompt.txt 另用 {contract_section}/{context_section}/{review_scope_fingerprint}，由 render_review_prompts.py 注入（脚本属其它单元）
- hook 接口：pre-commit 经 core.hooksPath 启用（repo_sync.py install-hooks），依赖 md_format.py 的 format_paths/MdFormatError/_is_blacklisted/REPO_ROOT；.claude/settings.json hook 调用 track_worktree.py

## dependencies

- .repo_template/scripts/ 全部被引用的脚本与子命令经静态核对均真实存在（task.py 及其 repo_task/cli.py 子命令与 --creation/--allow-backlog/--require-verified/--owner-id/--executor/--attempt/--execution-id/--sources/--confirm-stopped/--replace-owner/--review/--verify 等 flag、pending.py/findings.py/spikes.py 子命令、repo_sync.py 的 install-hooks 与 link-skills、md_format.py 的 --changed/--check 与库符号）
- .claude/skills 与 .agents/skills 软链目录实际存在并指向 .repo_template/skills/（已抽查 .agents/skills 软链目标）
- 外部运行时依赖：Python 3.9+、Git 2.38+、md_kx 二进制（PATH）、gh CLI（仅 template-issue-report 发布时）

## flows

- 用户入口流：OpenCode /命令或宿主显式入口 → 读取对应 public SKILL.md → 按 registry 调用图直接读子流程正文（task-run→task-work/task-integrate、task-from-pending→bug-to-pending/task-create、pending-record→bug-to-pending、bug-to-pending→task-create、repo-template-sync→repo-template-sync-core）
- 提交流：git commit → pre-commit 按 staged .md 选文件 → 工作区/index 一致性检查 → md_format.format_paths 格式化 → git add 重新暂存；无 staged .md 直接放行
- review 流：task-work 按 review_level 渲染 review_prompts（single→general，full→code+test，share 注入三者）→ reviewer 只读审查并写 review_*.md → check_review_status.py 按 reviewed_scope 指纹判定 PASS 有效性

## constraints

- 全部 skill 均 disable-model-invocation: true 且 opencode/autoinvoke=false，自然语言匹配 description 不构成执行授权；internal skill（task-work/task-integrate/repo-template-sync-core）另有 user-invocable: false
- merge 必须另行取得用户明确授权，不包含在 task-run 启动授权内；工具链任何流程不 push
- front matter 只经 task.py 修改；pending/findings/spike 编号只经对应脚本在锁内分配，不复用
- 生成物纪律：.opencode/commands 与 usage.md 的 skill 登记表为生成产物，只改源（SKILL.md/registry.json）后重跑生成器；本次核对 12 个命令文件的 description 与对应 SKILL.md 逐字一致，usage.md 登记表与 registry.json 的角色/调用边完全一致

## decisions

- registry.json 单一权威：角色（12 public/3 internal）与调用图只在 registry 定义，usage.md 表格与各 skill 的组合契约段落均指向它
- 文档分工（architecture.md 权威分工节）：AGENTS 存长期不变量与写权，architecture 解释机制，usage 说明接口与恢复，SKILL 说明阶段动作与授权，机械状态以脚本检查与持久事务日志为准
- pre-commit 采用失败即阻断而非静默跳过：有 staged .md 但 md_kx 缺失/格式化失败时阻断提交；工作区与 index 不一致时拒绝格式化防未暂存 hunk 混入

## evidence

- .repo_template/skills/registry.json:1-74（15 skill 角色与 7 条调用边，与磁盘 15 个 SKILL.md 目录一一对应）
- .opencode/commands/*.md 与 .repo_template/skills/*/SKILL.md 的 description 程序化比对：12/12 逐字一致
- .repo_template/docs/usage.md:63-91 生成的 skill 登记表与 registry.json 角色/调用边一致
- .repo_template/scripts/repo_task/cli.py 静态核对：skills 与 usage 引用的 task.py 子命令及 flag 全部存在；repo_sync.py 含 install-hooks/link-skills；md_format.py 含 format_paths/MdFormatError/_is_blacklisted/REPO_ROOT/--changed/--check
- .repo_template/hooks/pre-commit:1-97 全文（选文件、一致性拒绝、格式化回暂存逻辑）
- .claude/settings.json:1-16（仅 PostToolUse Bash hook 调 track_worktree.py --write --agent claude-code，无 secret，JSON 结构合法）
- .md_kx.toml:1-5 与 usage.md:51 的格式约定（4 空格/compact/number）一致
- git config core.hooksPath 在本 clone 未设置（退出码 1），.git/hooks/ 仅有 *.sample 文件

## uncertainties

- render_review_prompts.py 是否覆盖四个 prompt 文件用到的全部占位符（含 share_prompt.txt 的 {review_scope_fingerprint}/{contract_section}/{context_section}）无法在本单元内验证：渲染器属 template_scripts_ops 单元，本单元只能确认占位符集合与 task-work 对渲染结果的消费方式自洽
- pre-commit 在 import 后猴补 md_format.REPO_ROOT = Path.cwd()；md_format.py 是否在 import 期已用 REPO_ROOT 派生其它常量无法在本单元确认（md_format.py 属其它单元），若存在 import 期派生，hooksPath 指向非消费仓根时格式化目标可能漂移
- usage.md 状态行一节称跟踪结果输出到状态行，但本单元 .claude/settings.json 无 statusLine 配置；状态行可能由用户级 ~/.claude/settings.json 提供，仓内无法证实或证伪
- pre-commit 未在本 clone 启用是本 clone 的状态事实；其它 clone 是否已运行 install-hooks 未核查

## Findings

- [Medium][85] .repo_template/skills/bug-to-pending/SKILL.md:20-20 — bug-to-pending 声称 task-work 是其 analysis-only 的内部调用方，但 registry.json 无此调用边，与全套 skill 的组合契约冲突
  - ID: f_template_support_01; verification: static
  - Evidence: bug-to-pending/SKILL.md:20：analysis-only 模式「供 `task-work`、`pending-record` 等内部调用」; registry.json 的 calls 仅 7 条边（task-run→task-work、task-run→task-integrate、task-from-pending→bug-to-pending、task-from-pending→task-create、pending-record→bug-to-pending、bug-to-pending→task-create、repo-template-sync→repo-template-sync-core），无 task-work→bug-to-pending; 每个 SKILL.md 的组合契约均声明「调用关系以 .repo_template/skills/registry.json 为权威」，usage.md skill 调用节亦称「只接受注册调用边」; task-work/SKILL.md:45（实施第 6 步）只写「登记 pending 或 finding」，全文未引用 bug-to-pending，与被声称的调用方身份不符
  - Impact: 执行 task-work 的 agent 按 bug-to-pending 正文会以为在 task 执行期调用 analysis-only 已获登记授权，而按 registry 权威则该调用边不存在、应停止；两种读法得出相反结论，破坏调用图作为单一事实源的可判断性，后续新增调用方还会继续照此模式漂移。
  - Fix: 二选一并保持一致：确为合法调用则在 registry.json 增加 task-work→bug-to-pending 边并重跑 skill_registry.py --write 更新 usage.md 登记表，同时在 task-work 正文中写明调用点；否则把 bug-to-pending:20 的「task-work、」删去，仅保留已登记的 pending-record。

- [Low][90] .repo_template/docs/usage.md:51-51 — usage.md 称 commit 由 pre-commit hook「强制」格式化，但本仓 clone 未安装该 hook（core.hooksPath 未设置），门禁实际不在生效状态
  - ID: f_template_support_02; verification: static
  - Evidence: usage.md:51：「commit 由 pre-commit hook 强制（.repo_template/hooks/pre-commit，…），需先 python3 .repo_template/scripts/repo_sync.py install-hooks 启用 core.hooksPath」; 本 clone 实测：git config core.hooksPath 退出码 1（未设置）；.git/hooks/ 下只有 *.sample 文件，无 pre-commit; usage.md:153 支持边界表亦承认「hooks 需显式 install-hooks」，与同页 51 行的「强制」表述口径不一致
  - Impact: 在本 clone 内工作的 agent 或人提交 .md 时不会触发任何格式化或拦截，却可能依据 usage.md 的「强制」表述误以为格式门禁已兜底，未格式化的 Markdown 可直接入库且无任何信号。
  - Fix: 在仓内落地启用（运行 install-hooks 并把启用状态纳入 doctor/状态检查），或把 usage.md:51 的表述改为与支持边界一致的条件式（「启用 install-hooks 后，commit 由 pre-commit hook 强制…」），并给出可核查的启用状态命令。

- [Low][75] .repo_template/hooks/pre-commit:15-18 — pre-commit 在判断有无 staged .md 之前就无条件 import md_format，导入失败会阻断全部提交，与自身「无 .md 快速放行」的 docstring 承诺不符
  - ID: f_template_support_03; verification: static
  - Evidence: hooks/pre-commit:3-7 docstring：「staged 无 .md 时快速放行；有 .md 但格式化失败（含 md_kx 缺失）阻断提交」; hooks/pre-commit:15-18 在模块顶层组装 sys.path 并 import md_format，发生在 main() 调用 staged_md() 之前；MdFormatError 的捕获只包住 format_paths 调用（main 内），导入期异常（md_format.py 自身导入错误、Python 版本不兼容等）不在捕获范围; 结果是：md_format 模块不可导入时，连不含任何 .md 的提交也会以未处理的 traceback 非零退出，与「快速放行」承诺相反，且报错不含 docstring 承诺的安装引导
  - Impact: 工具链自身损坏或环境异常时，消费仓的全部 git commit 被一个 Markdown 格式化 hook 阻断，故障面从「.md 提交」放大到「所有提交」，且错误形态误导排查方向。
  - Fix: 把 md_format 的导入推迟到 staged_md() 确认存在待格式化文件之后，并对 ImportError 捕获后输出与 MdFormatError 一致的引导信息再非零退出；无 .md 时不触碰 md_format。

- [Low][85] .repo_template/hooks/pre-commit:29-35 — pre-commit 选文件用 --diff-filter=ACM 排除了重命名（R），纯重命名或重命名入库的 .md 不会被格式化
  - ID: f_template_support_04; verification: static
  - Evidence: hooks/pre-commit:31：git diff --cached --name-only -z --diff-filter=ACM -- "*.md"; ACM 只含 Added/Copied/Modified；git 在重命名检测开启时把「改名+小改」记为 R，改名文件即使内容同时有修改也不在 ACM 集合内（大改动才回落为 A/D）; usage.md:51 对该 hook 的描述是「格式化本次 staged 的 .md」，未声明重命名例外
  - Impact: 通过 git mv 迁移文档（repo-hygiene 归档、spec 迁移等高频场景）时若顺手改内容，未格式化的 .md 可绕过门禁入库，格式一致性出现静默缺口。
  - Fix: 把过滤改为 ACMR 并对 R 取目标路径（--name-only 对 R 输出目标名），或显式关闭重命名检测（--no-renames）使改名呈现为 A+D 后自然落入 ACM；同步在 hook docstring 注明口径。

- [Info][90] .repo_template/docs/architecture.md:57-57 — architecture.md 使用未定义术语 `withdraw_rate`，全 .repo_template 内仅此一处出现，读者无法判断被排除的门禁是什么
  - ID: f_template_support_05; verification: static
  - Evidence: architecture.md:57：「门禁不含 `withdraw_rate` 与自动 prompt hint。」; 对整个 .repo_template/ 静态检索 withdraw_rate 只有这一处命中，无定义、无引用、无对应脚本检查项; 同句的「自动 prompt hint」同样未在本文或 usage.md 中定义（task-work 与 share_prompt.txt 只有 review/verify 轮次上限概念）
  - Impact: 现行机制文档中出现无法回查的内部术语，后续维护者无法判断这是已删除机制的残留、外部系统概念还是笔误，容易误判 review 门禁的实际组成。
  - Fix: 删除该残留短句，或补一句定义并给出权威位置链接；若是历史机制，标注其移除版本/提交以便追溯。

- [Low][60] .repo_template/docs/usage.md:158-163 — usage.md 称 .claude/settings.json 的 hook 将 worktree 映射「输出到状态行」，但该配置文件内没有任何 statusLine 配置，状态行一环在仓内无落点
  - ID: f_template_support_06; verification: suspected
  - Evidence: usage.md:158-160：「## 状态行 Hook 与执行范围」「模板在 .claude/settings.json 中配置了 PostToolUse hook（调用 track_worktree.py），用于跟踪多 worktree 环境下各会话对应的 task 目录并输出到状态行」; .claude/settings.json:1-16 全文只有 PostToolUse/Bash 一条 hook，无 statusLine 键；本单元内也没有其它宿主配置定义状态行命令; 该节随后只描述映射文件 .scratch/statusline_workdir.jsonl 的写入条件，未给出谁读取该文件并渲染状态行
  - Impact: 按仓内文档在新环境复现时，映射文件可能正常写入却没有任何状态行展示，使用者无法从仓内资料判断缺的是哪一环（可能依赖用户级设置，但文档未声明这一前提）。
  - Fix: 在 usage.md 该节补明状态行的配置归属：若由用户级 settings 提供 statusLine 命令，写明前提与最小配置示例；若已废弃，删除「输出到状态行」表述，只保留 worktree 映射的实际用途。

## views

```json
{
  "contracts": {
    "reviewer": "87ca24f5-7744-4c00-8b21-96ee6f4b014b",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "87ca24f5-7744-4c00-8b21-96ee6f4b014b",
    "status": "completed"
  },
  "design": {
    "reviewer": "87ca24f5-7744-4c00-8b21-96ee6f4b014b",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "87ca24f5-7744-4c00-8b21-96ee6f4b014b",
    "status": "completed"
  },
  "performance": {
    "reviewer": "87ca24f5-7744-4c00-8b21-96ee6f4b014b",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "87ca24f5-7744-4c00-8b21-96ee6f4b014b",
    "status": "completed"
  },
  "security": {
    "reviewer": "87ca24f5-7744-4c00-8b21-96ee6f4b014b",
    "status": "completed"
  },
  "tests": {
    "reviewer": "87ca24f5-7744-4c00-8b21-96ee6f4b014b",
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
