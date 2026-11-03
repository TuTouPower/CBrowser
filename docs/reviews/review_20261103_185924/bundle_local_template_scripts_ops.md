# bundle_local_template_scripts_ops

## responsibilities

- 模板仓运维脚本集：把 repo-template-sync / repo-cleanup / repo-hygiene 三个 skill 的机械动作下沉为确定性脚本（repo_sync.py、repo_cleanup.py、repo_hygiene.py），agent 只保留语义裁定。
- 条目编号的跨分支/跨 worktree 扫描与互斥分配（_id_scan.py，供 pending.py/findings.py 共用），以文件名为编号真相源、legacy 单文件正文编号兜底。
- review 流程支撑：check_review_status.py 读报告+处置表输出 verdict/轮次/下一步；render_review_prompts.py 从 note.md front matter 把契约区/上下文区注入 reviewer prompt 并附契约 drift 警告。
- 模板导出与注册表：export_template.py 只从已提交 git 树导出产品树（拒绝本机状态/.env）；skill_registry.py 校验 registry.json 与 SKILL.md 门禁一致并渲染 usage.md 注册表段；md_format.py 是 md_kx 的仓库内包装（选文件、黑名单、回滚）。

## interfaces

- CLI 子命令：repo_sync.py init/status/plan/apply/transaction/prompt/link-skills/install-hooks；repo_cleanup.py scan/apply [--keep] [--expected-count]；repo_hygiene.py archive-handoff/archive-spike/archive-review [--write]；其余脚本为单用途 CLI 或库函数（_id_scan.allocate/allocate_dir、md_format.format_paths/format_new_file）。
- 状态文件契约：.repo_template/sync_state.json（本机）、sync_manifest.json（可入库溯源）、sync_policy.json（共享 user_prompts）；sync_state 字段级原子更新，禁止整文件覆盖语义。
- 输出契约：check_review_status.py 输出一行一键值（overall/round/next_action/review_scope 等）供处置流程机读；repo_cleanup scan/apply 输出 Markdown 表格与计数，apply 可用 --expected-count 与 scan 结果对账。

## dependencies

- repo_task 包（template_scripts_state 单元）：locks.git_common_lock、file_transaction.FileTransaction/fingerprint、validation.run_checks/validation_environment、documents.atomic_write_text/parse_front_matter、monitoring.review_scope_fingerprint、review.evaluate_review、finalization.validate_spike、context.TaskDataError。
- 同单元内依赖：repo_sync.py import export_template.export_template（clean 源走 git archive 快照）；repo_hygiene.py 延迟 import repo_task.finalization。
- 外部工具：git 子进程（全单元）、md_kx 二进制（md_format.py，PATH 查找）、pytest 契约测试（repo_sync apply 门禁，固定命令与 60s 超时）。

## flows

- repo_sync apply：CONTROL_LOCK 内 → FileTransaction.begin(固定路径清单) 快照 → clean 源先 export_template 快照导出再 _as_product 校验 → 硬同步树覆盖 + workflow schema 强制迁移 + 软链修复 + opencode 命令薄层 + .gitignore/.prettierignore/MCP 机械合并 + 裁定单元按 --decision 写盘 → 契约测试+run_checks → 推进 last_synced_commit 并写 sync_manifest → transaction.applied；异常按 (OSError, ValueError, SyncError, SubprocessError) 回滚。
- repo_cleanup：collect 两遍扫描（bulk 类别整树 + 主 walk 分类，keep/保护名单过滤）→ scan 打印预览；apply 以同一 collect 结果删除（文件先、目录按深度逆序），可选 --expected-count 防 scan→apply 漂移。
- _id_scan.allocate：git 公共目录排他锁内 scan_max_id（全本地分支 ls-tree + 全部 worktree 工作区 + legacy 正文编号）→ tmp 文件写盘 → os.replace 原子落盘后释锁。
- repo_hygiene archive-spike/review：校验（spike 走 validate_spike、review 名格式）→ git mv 整目录 → _move_leftover 并入 gitignore 残留；archive-handoff 按 H2 切节、除最新一节外 append 到 archive 并做 endswith 幂等跳过。

## constraints

- 全部脚本禁止自动 commit；写盘与提交门禁分离（repo_sync transaction accept 要求先提交）。
- 路径 containment：task-dir/spec/out-dir/task 目录等输入均校验必须留在仓库内；export_template 解包逐成员校验（禁 ..、绝对路径、反斜杠、重复路径、父路径非目录，软链最后创建且 resolve 必须落在目标内）。
- 消费仓定制保护：AGENTS.md 项目介绍永不覆盖、目录规则只报告；MCP 已有 server 键保留消费值且模板侧 env 非占位值在新建时占位化；手写 opencode 命令（无 COMMAND_MARKER）永不覆盖/删除。
- 删除类操作的多层防线：repo_cleanup 的 HARD_PROTECTED、docs/ 仅 os/editor、未点名类别不整树、keep 精确/glob/前缀+祖先保护、apply 独立重查。

## decisions

- 硬同步 vs 裁定的二分：.repo_template 树与 .md_kx.toml 树对树全量覆盖（含删除），AGENTS.md/.gitignore 为裁定单元（前者按标题分区协议、后者机械合并+prompt 拦截）。
- clean 源同步必须经 git archive 快照（export_template）而非直接读工作区，dirty 源仅显式 --allow-dirty-source 且不推进 last_synced_commit。
- 编号分配以文件名为准、扫描全分支+全 worktree 取 max+1，跨来源同号允许（合并前暂时重复）、同来源同号报错。
- md_format 格式化失败回滚本次已写文件；库函数 format_new_file 缺 md_kx 时只警告不阻断，CLI 缺失则硬失败。

## evidence

- .repo_template/scripts/repo_sync.py:1845-1940（cmd_apply 事务组装与回滚例外集）
- .repo_template/scripts/repo_sync.py:1351-1418（MCP 合并与 env 占位化）
- .repo_template/scripts/repo_cleanup.py:139-213（collect 两遍扫描与 keep 过滤）
- .repo_template/scripts/export_template.py:14-65（解包成员校验与软链后置校验）
- .repo_template/scripts/_id_scan.py:199-273（scan_max_id 与锁内 allocate 落盘）
- .repo_template/scripts/repo_hygiene.py:97-127（handoff 迁移幂等 append）
- .repo_template/scripts/md_format.py:107-180（快照回滚式 format_paths）

## uncertainties

- FileTransaction 的快照/回滚实现细节在 template_scripts_state 单元，本轮仅以 grep 确认 begin 时对清单路径 copytree/copy2 快照；f_template_scripts_ops_03 中『apply 路径下 rmtree 内容入回滚栈』的判断以此为据，未逐行审 file_transaction.py。
- 本单元脚本的测试断言质量未核（见 tests 视角 partial 理由）；finding 中涉及『无测试拦截』的判断仅基于静态阅读，未运行测试验证。
- md_kx 本体不在本仓，--check 退出码语义（1=漂移）按 md_format.py 的用法推定，未核 md_kx 实现。
- tests 视角由独立 viewfix 补审完成（原审阅者因本单元不含测试文件标 partial）：补审通读了实际行使本单元代码的测试——.repo_template/tests/test_repo_cleanup.py、test_repo_sync.py、test_repo_hygiene.py、test_check_review_status.py、test_render_review_prompts.py、test_md_format.py、test_precommit_hook.py、review_support.py 全文，以及 test_pending.py（_id_scan）、test_design_regressions.py、test_review_report_regressions.py（export_template / skill_registry / shared prompt）中的相关段落，并回查 repo_sync.py、repo_cleanup.py、md_format.py 对应实现行逐项核对覆盖缺口；新增 finding f_template_scripts_ops_13..19 均为测试覆盖缺口（与原 finding 一一对应），结论仅基于静态阅读，未运行任何测试。总体判断：cleanup/hygiene/check_review_status/render_prompts/md_format 的行为级与失败路径覆盖扎实（真实 git、回滚、超时、围栏解析、契约漂移均有用例），_id_scan 与 export_template 虽无同名专用文件但在 test_pending / 回归套件中被实质覆盖；盲区集中在『生产恒走、测试恒绕』的分支——prompt 合并编号、registry 角色过滤、无事务 link-skills 入口、CLI 点名黑名单、嵌套 bulk 树、目标侧文件软链、handoff 围栏切节。

## Findings

- [Medium][85] .repo_template/scripts/repo_cleanup.py:114-124,158-172 — cleanup 主 walk 的剪枝按仓库根相对路径匹配，嵌套 node_modules 与 bulk 目录树不被剪枝，与 docstring 的防误删承诺不符
  - ID: f_template_scripts_ops_01; verification: static
  - Evidence: _prune(relroot, names, excluded) 以完整相对路径 rel 与 excluded 比对；prune 集合为 {".git", ".scratch", "artifacts", "data"} 及未点名时的 "node_modules"，只命中仓库根一级同名目录; 嵌套路径如 src/frontend/node_modules、pkg/.scratch 的 rel 为多段路径，不在 prune 集合中，os.walk 继续下钻; 文件头 docstring 明示『默认扫描不进入未点名的 node_modules 与这三棵目录树（防误删未点名内容）』; 下钻后嵌套 node_modules 内的 *.pyc/*.log/__pycache__ 会被默认类别（pycache/logs）命中并在 apply 时删除；嵌套 .git 内的同类文件同理
  - Impact: 默认 scan/apply 会进入并清理未点名类别的嵌套目录树，违背脚本自述的安全契约；同时全量 walk 巨型 node_modules 使 scan 显著变慢。删除对象多为依赖内缓存/日志，实际损失有限，但契约与实现不一致会误导审批者对 dry-run 结果的信任。
  - Fix: 在 _prune 中按目录名（而非完整相对路径）剪枝 node_modules/三棵 bulk 目录名与 .git，或在 walk 中以 name in prune_names 判断；补嵌套 node_modules 的回归用例。

- [Medium][80] .repo_template/scripts/repo_sync.py:1606,1682,1969-2011 — user_prompts 编号在 status/plan 与 prompt list/revoke 之间不是同一编号空间，revoke 可能作废错误条目
  - ID: f_template_scripts_ops_02; verification: static
  - Evidence: cmd_status:1606 与 cmd_plan:1682 均以 enumerate(active_prompts(state)) 编号——active_prompts 过滤 revoked 并合并 local state 与 sync_policy 的共享 prompts; cmd_prompt 的 list/revoke 以 data.get("user_prompts") 原始列表（未过滤、仅当前 scope）下标为准，revoke 按该下标置 revoked; 只要存在任一已 revoked 条目或共享 prompt，status/plan 打印的 #N 与 prompt revoke --id N 指向不同条目; user_prompts 的 tags 直接驱动 merge_gitignore 的拦截子串（prompt_substrings），作废错条目会改变 .gitignore 同步行为
  - Impact: 操作者按 status/plan 展示的编号执行 revoke，会静默作废另一条站立指令（或漏作废目标条目），且输出无从察觉；站立指令影响后续所有 apply 的 .gitignore 裁定，后果跨轮次持续。
  - Fix: 统一编号语义：status/plan 改为展示原始列表下标（与 revoke 一致），或 prompt list/revoke 改按 active 序号并在输出标注 scope/来源；二选一并在三处输出口径对齐。

- [Medium][75] .repo_template/scripts/repo_sync.py:823-838,2063-2073 — link-skills 路径下 _ensure_symlink 对宿主位真实目录直接 rmtree 且报告谎称『原内容入回滚栈』，该路径根本没有事务
  - ID: f_template_scripts_ops_03; verification: static
  - Evidence: _ensure_symlink:834 对 link.is_dir() 的真实目录执行 shutil.rmtree(link)，reports 固定文案为『旧真实目录已转软链（原内容入回滚栈）』; cmd_link_skills:2063 直接调用 repair_symlinks，未建立 FileTransaction，不存在回滚栈; apply 路径下 FileTransaction.begin 对 .claude/skills/.agents/skills 做了快照（repo_task/file_transaction.py:27-29），文案在该路径才成立; 宿主位真实目录可能是未入库的本地 skill 副本，rmtree 后除 git 已跟踪部分外不可恢复
  - Impact: 用户运行只读语义预期的 link-skills『校验并修复软链』即可永久删除宿主位真实目录内容，且报告误导其以为可回滚；与 apply 路径同一函数两种安全等级，调用方无从区分。
  - Fix: link-skills 路径下遇真实目录时改为报错/跳过并提示走 apply，或先把原目录改名为带时间戳的本机备份再转软链；回滚栈文案只在事务内输出。

- [Medium][70] .repo_template/scripts/repo_sync.py:1096-1097,1919 — sync_opencode_commands 对 registry.json 用 roles[name] 硬下标，registry 缺登记时 KeyError 穿透 apply 的回滚例外集
  - ID: f_template_scripts_ops_04; verification: static
  - Evidence: sync_opencode_commands:1096-1097 以 json.loads(...)["skills"] 与 roles[name]["role"] 硬下标过滤 public skill；目录存在但 registry 未登记的 skill 触发 KeyError; 同文件 opencode_commands_status:1018 的对应逻辑用 roles.get(name, {}) 防御，两条路径防御等级不一致; cmd_apply:1919 的回滚捕捉集为 (OSError, ValueError, SyncError, subprocess.SubprocessError)，main 的兜底为 (SyncError, TaskDataError) 与 OSError；KeyError 均不在其中; sync_opencode_commands 在 _apply_sync_write 内、FileTransaction 已 begin 之后执行
  - Impact: registry 与 skills 目录不一致（模板演进中的常见中间态）时 apply 中途以裸 traceback 崩溃：已写文件不回滚、事务悬挂为 begun 状态，后续 apply/transaction 操作需人工清理。skill_registry.py 本会在独立校验时以 ValueError 报告该不一致，但 apply 路径未先行调用它。
  - Fix: sync_opencode_commands 改用 roles.get(name, {}) 并对缺登记给出 SyncError（或在 _apply_sync_write 前先跑 registry 一致性校验）；同时考虑把 KeyError 纳入 apply 回滚捕捉或在事务边界统一包装。

- [Low][65] .repo_template/scripts/repo_sync.py:761-768,812-819 — sync_dir/sync_skill 复制普通文件时不处理目标侧文件软链，copy2 跟随软链写出树外
  - ID: f_template_scripts_ops_05; verification: static
  - Evidence: sync_dir 对『目标是目录软链且源是真实目录』显式拒绝，但源为普通文件时仅检查 target.exists()/_file_differs 后 shutil.copy2(entry, target)，copy2 默认跟随目标软链; _file_differs 对软链比较 resolve() 结果：消费侧同名路径是指向仓外文件的软链且内容不同时，copy2 会覆写仓外目标文件本体而非替换软链; sync_skill:819 的文件复制分支同样无目标软链检查; 同仓 export_template 与 repo_cleanup 对软链 containment 均有专门防线，此处防御等级不一致
  - Impact: 消费仓在模板同步路径上预置软链（人为或旧布局残留）时，一次 apply 可把模板内容写到 .repo_template 树之外的任意可写路径，绕过 FileTransaction 对清单路径的快照范围（被写出的目标不在事务清单内，回滚也覆盖不到）。触发需消费侧预置软链，影响限于本机文件覆写。
  - Fix: 文件复制前若 target 是软链则先 unlink 再 copy（与软链条目分支一致），或显式拒绝并报错；sync_dir 与 sync_skill 两处统一。

- [Low][90] .repo_template/scripts/md_format.py:195 — md_format CLI 对点名传入的黑名单路径静默过滤，与 format_paths 的显式拒绝契约不一致
  - ID: f_template_scripts_ops_06; verification: static
  - Evidence: main:195 `rels = [p for p in args.paths if not _is_blacklisted(p)]`：点名 docs/archive/ 下路径被无声丢弃，最终打印『无改动』且退出 0; format_paths:118-121 对同一输入抛 MdFormatError『在黑名单，拒绝格式化』，文件头注释亦称黑名单在脚本内解决; pre-commit 等调用方若点名传入 archive 路径，会得到假成功而非预期拒绝
  - Impact: 显式点名格式化被保护路径时静默 no-op，调用方无法区分『已格式化/无漂移』与『被拒绝』；与库函数语义分裂，后续维护者易踩。
  - Fix: main 的 paths 分支删除静默过滤，交给 format_paths 统一抛错；或至少对被过滤路径逐条打印拒绝提示并非 0 退出。

- [Low][85] .repo_template/scripts/repo_sync.py:1990-2002 — prompt add 按 tag 交集静默作废既有站立指令且不汇报
  - ID: f_template_scripts_ops_07; verification: static
  - Evidence: cmd_prompt add:1996-1999 遍历既有 prompts，凡 tags 与新 prompt 有交集且未 revoked 者直接置 revoked=True; 输出只打印新登记条目（2001），不列出被连带作废的条目编号与正文; 被作废条目的 tags 不再进入 prompt_substrings，其 .gitignore 拦截规则自下一轮 apply 起失效
  - Impact: 添加一条新站立指令可能无声撤销多条旧指令，操作者事后只能逐条 list 比对 revoked 标记才发现；与 f_template_scripts_ops_02 的编号漂移叠加后，prompt 账目可审计性差。
  - Fix: add 输出中逐条打印被连带作废的 #id 与 text，或要求显式 --revoke-overlapping 确认后再作废。

- [Low][80] .repo_template/scripts/skill_registry.py:40-46 — skill_registry 在 usage.md 缺注册表标记时以裸 ValueError 崩溃，无诊断信息
  - ID: f_template_scripts_ops_08; verification: static
  - Evidence: main:44-45 `text.split(START, 1)` 与 `tail.split(END, 1)` 在标记缺失时抛 ValueError: not enough values to unpack，无任何上下文提示; render_registry 对 registry 条目缺 role 字段同样以 KeyError 崩溃（entry["role"]）; 该脚本是 usage.md 注册表段的唯一校验/生成入口，崩溃信息无法区分『标记被删』『文件损坏』『registry 结构漂移』
  - Impact: 模板演进或人工编辑 usage.md 误删标记后，校验只给 traceback，定位成本高；不影响数据安全，故 Low。
  - Fix: split 前显式检查 START/END 存在性并抛带文件路径与期望标记的错误；entry 字段用 .get 并报告缺字段的 skill 名。

- [Low][55] .repo_template/scripts/repo_hygiene.py:65-76 — archive-handoff 按任意行首『## 』切节，不识别 fenced code block 内的伪标题
  - ID: f_template_scripts_ops_09; verification: suspected
  - Evidence: _split_handoff 以 line.startswith("## ") 收集节边界，未跟踪代码围栏状态; cmd_archive_handoff 据此把 sections[:-1] 整段迁入 archive 并重写 handoff.md; handoff 节正文若含 fenced 代码块且块内有行首『## 』（如粘贴的 Markdown 示例），会被误判为新节，迁移后 handoff 保留的『最新节』可能只是某节的后半段
  - Impact: 触发条件窄（handoff 正文粘贴含 ## 行的代码块），一旦触发会把半截节留在 handoff、另半截迁入 archive，内容被拆散且 dry-run 输出按错误节标题展示，审批者不易察觉。
  - Fix: _split_handoff 增加与 render_review_prompts.extract_section 相同的围栏跟踪（``` / ~~~ 开闭）后再判 H2 边界。

- [Low][70] .repo_template/scripts/_id_scan.py:199-216,232-273 — 每次 allocate 在全局 ID 锁内对全部本地分支逐个 ls-tree 并扫描全部 worktree，锁持有时间随分支数线性增长
  - ID: f_template_scripts_ops_10; verification: static
  - Evidence: scan_max_id 对 local_branches() 每个分支执行 git ls-tree -r（另加每个 legacy 文件一次 git show），并对每个 worktree 做 rglob/iterdir 扫描; allocate/allocate_dir 在 id_lock 内调用 scan_max_id，扫描全程持锁; pending/findings/spikes/task 四类分配共用同一把 git 公共目录锁，分支多的仓里单次分配可达数十个 git 子进程
  - Impact: 并行 task worktree 场景下编号分配互相排队，慢但不错；属可扩展性上限提示，非正确性问题。分支数达到百级时单次 new 操作延迟会明显可感。
  - Fix: 可缓存单次 CLI 调用内的扫描结果，或先以 for-each-ref + 一次性 ls-tree 多分支批量取数；锁内只保留『复查 max + 落盘』最小临界区。

- [Info][90] .repo_template/scripts/repo_sync.py:78-80 — AGENTS_INTRO_HEADING 常量与 MERGE 标题同值且从未被引用，是误导性死常量
  - ID: f_template_scripts_ops_11; verification: static
  - Evidence: repo_sync.py:78-80 定义 AGENTS_INTRO_HEADING 与 AGENTS_MERGE_HEADING 均为 "## 目录与读写规则"; 全文件仅 AGENTS_MERGE_HEADING/AGENTS_FORCE_HEADING 被 _agents_parts 使用；intro 区实际以『merge 标题之前全部内容』推导; 常量名暗示 intro 有独立标题锚点，后续维护者按名索骥会误判分区协议
  - Impact: 仅可读性/误导风险，无行为影响。
  - Fix: 删除 AGENTS_INTRO_HEADING，或改为注释说明 intro 无标题锚点、按 merge 标题前内容界定。

- [Info][85] .repo_template/scripts/check_review_status.py:13-37 — check_review_status.py 从 repo_task.review 导入十余个未在本文件使用的名字，掩盖真实依赖面
  - ID: f_template_scripts_ops_12; verification: static
  - Evidence: 第 35-37 行的导入列表含 read、visible_markdown_lines、extract_verdicts、regression_rounds、extract_h2_lines、table_cells、is_separator_row、disposition_stats、disposed_findings、reported_findings、reviewed_scope、reviewed_scope_hint 等，本文件正文均未引用; 本文件实际只用 parse_front_matter、VALID_REVIEW_LEVELS、evaluate_review、review_limits、ReviewDataError; REPO_ROOT 赋值夹在两个 import 块之间（第 33 行），导入顺序亦不规整
  - Impact: 读者无法从导入面判断该 CLI 的真实耦合；若为兼容性再导出，应注释声明。仅可维护性问题。
  - Fix: 删除未用导入（或集中注释为兼容再导出），并把 REPO_ROOT 赋值移到导入块之后。

- [Medium][92] .repo_template/tests/test_repo_sync.py:119 — prompt 编号双空间缺陷（f_template_scripts_ops_02）无任何回归测试：显示编号路径从未被驱动
  - ID: f_template_scripts_ops_13; verification: static
  - Evidence: 生产侧已核：cmd_status（repo_sync.py:1606）与 cmd_plan（repo_sync.py:1682）按 active_prompts(state) 枚举打印 #{i}，active_prompts（repo_sync.py:239）返回 local 未作废 + _shared_user_prompts 未作废的合并列表；而 cmd_prompt revoke（repo_sync.py:2004-2010）按 data['user_prompts'] 原始本地列表（含已 revoked 条目）下标作废——两套编号空间只在『存在 shared 条目或已 revoked 条目』时分岔。; 现有 prompt 测试只有 test_prompt_add_supersede_revoke 与 test_prompt_substrings_only_active（test_repo_sync.py:119-146），全部直接以原始列表下标调用 cmd_prompt revoke（id=2 / id=1），从不渲染 status/plan 的编号再据此 revoke。; 全套件唯一的 shared-scope 用例 test_design_regressions.py::test_shared_sync_policy_and_version_survive_local_state_loss 只断言 active_prompts() 按 text 成员包含 shared 条目（验其在 apply/丢 state/重 init 后存活），不涉及编号、列表输出或 revoke。; grep .repo_template/tests 全部 *.py：cmd_status/cmd_plan 仅在无 user_prompts 的场景被调用（test_repo_sync.py:433、1150-1151），带 prompt 的编号输出零断言。
  - Impact: f_02 的错误作废路径（按 status/plan 展示编号 revoke 到另一条站立指令，进而错误驱动 .gitignore 拦截）在测试层完全无网：任何后续重构都无法从测试发现编号空间再次分岔，该 Medium 缺陷只能靠人工复现发现。
  - Fix: 在 test_repo_sync.py 增加用例：构造 local 2 条（其一 revoked）+ shared 1 条的混合 state，捕获 cmd_status/cmd_plan 输出的 prompt 编号，再以该编号调用 prompt revoke，断言被作废的正是展示的那一条；并为 cmd_prompt list 的编号口径补一条与 revoke 一致性的断言。

- [Medium][95] .repo_template/scripts/repo_sync.py:1096 — registry.json 角色过滤分支在测试套件中从未执行：sync_opencode_commands 的 roles[name] 硬下标（f_04）与状态侧 .get 的分岔零覆盖
  - ID: f_template_scripts_ops_14; verification: static
  - Evidence: opencode_commands_status（repo_sync.py:1015-1019）与 sync_opencode_commands（repo_sync.py:1093-1097）都只在 SKILLS_SRC/registry.json 存在时才做 public 角色过滤；后者用 roles[name]['role'] 硬下标（f_04 的 KeyError 位点），前者用 roles.get 安全取值——同一过滤两套容错。; grep .repo_template/tests 全部 *.py：字符串 'registry.json' 零命中；test_repo_sync.py 的 env fixture 只在 consumer .repo_template/skills 下建裸 skill 目录（task-run/nodesc），从不放 registry.json，故两处过滤分支在 repo_sync 测试中从未进入。; skill_registry.py 本体仅有 test_design_regressions.py::test_registry_has_complete_roles_and_real_composition_edges 一条用例：对真实仓库 registry 调 render_registry() 断言含特定名字 + CLI 子进程退出 0；无 fixture 化的缺失/畸形 registry 输入，f_08 的 usage.md 缺标记裸 ValueError 路径同样无用例。
  - Impact: 真实消费仓的 skills 目录恰恰带 registry.json（生产路径恒走过滤分支），而测试恒走无 registry 的旁路：角色过滤失效、registry 与目录不一致时的 KeyError 穿透回滚例外集（f_04）都不会被任何测试拦下，属于『测试环境与生产环境分支不一致』的系统性盲区。
  - Fix: 在 test_repo_sync.py 的 env 中补 registry.json fixture：含 public/internal 两类角色与一条『registry 有名、目录无 skill』的不一致条目，分别断言 opencode_commands_status 与 sync_opencode_commands 的过滤结果一致且不抛 KeyError；skill_registry 侧补 usage.md 缺标记时报出可诊断错误的用例。

- [Low][90] .repo_template/scripts/repo_sync.py:2063 — cmd_link_skills（唯一无事务入口，f_03 的实际暴露面）从未被测试调用，_ensure_symlink 的『入回滚栈』报告真实性亦无断言
  - ID: f_template_scripts_ops_15; verification: static
  - Evidence: cmd_link_skills（repo_sync.py:2063-2072）直接调 repair_symlinks + sync_opencode_commands，全程无 FileTransaction；grep .repo_template/tests 全部 *.py：'link-skills'、'_ensure_symlink'、'cmd_link' 均零命中，该入口从未被任一测试驱动。; _ensure_symlink 的真实目录 rmtree 分支（repo_sync.py:832-840）仅经 test_repair_symlinks_converts_stale_real_dir 间接覆盖：该用例断言软链结果与报告含『旧真实目录已转软链』子串，但不断言报告后半句『原内容入回滚栈』的真实性，也未验证被删 SKILL.md 内容在任一路径下可恢复。; apply 路径下同一分支有事务兜底（test_apply_test_failure_rolls_back_keeps_backup_and_prints_changed 验回滚），link-skills 路径下无兜底这一差异没有任何用例标记或锁定。
  - Impact: f_03 的数据丢失场景恰好只发生在未被测试的入口上：若有人误以为 link-skills 与 apply 等价安全而在其文档/提示中沿用『入回滚栈』措辞，测试层不会给出任何信号；报告措辞与实际可恢复性长期脱节也无网可拦。
  - Fix: 补 cmd_link_skills 级用例：宿主位放带内容的真实目录，调用后断言目录转软链、报告措辞与实际（无备份产生）一致；或在修 f_03 后以该用例锁定『先备份再转链』的新语义。

- [Low][95] .repo_template/scripts/md_format.py:195 — md_format CLI 点名路径的黑名单静默过滤（f_06）无测试：main() 在套件中只被以 --check 全量模式调用过
  - ID: f_template_scripts_ops_16; verification: static
  - Evidence: md_format.py:195 main() 对点名路径做 rels = [p for p in args.paths if not _is_blacklisted(p)] 静默过滤，与 format_paths 在 md_format.py:107 的显式 MdFormatError 拒绝口径相反（f_06）。; test_md_format.py 对 format_paths 的黑名单拒绝有专门用例（test_format_rejects_blacklist），但对 main() 的唯一调用是第 131 行 main(['--check'])（隐含 collect_all 全量模式）；grep 确认全套件无任何以显式路径参数调用 main() 的用例。; test_precommit_hook.py 的 test_blacklisted_md_skipped 覆盖的是 hook 侧 staged 过滤（返回 0 且文件未动），与 CLI 点名路径是不同代码路径，不能替代。
  - Impact: 用户点名格式化归档 .md 时 CLI 静默跳过且报『无改动』，与库函数口径矛盾的行为没有任何测试锁定；将来统一口径（改 CLI 报错或改 format_paths 放行）时无回归网判断哪边是预期。
  - Fix: 在 test_md_format.py 补 main(['docs/archive/keep.md']) 用例，断言其行为与最终裁定的口径一致（报错退出或明确提示跳过），并与 test_format_rejects_blacklist 互相引用注明两层口径。

- [Low][95] .repo_template/tests/test_repo_cleanup.py:148 — repo_cleanup 嵌套未点名目录树（f_01 的确切形状）无测试：防误删承诺的回归网只覆盖仓库根深度 1
  - ID: f_template_scripts_ops_17; verification: static
  - Evidence: _prune 按仓库根相对路径比对排除集（repo_cleanup.py:114-121、158-165）：rel='src/node_modules' 不等于 'node_modules'，深度 ≥2 的同名 bulk 树不被剪枝，主 walk 会进入并按默认类别命中其内文件（f_01）。; test_repo_cleanup.py 两处 bulk 构造都在仓库根一级：fixture tree 的 node_modules/.scratch/artifacts/data（第 40-52 行）与 test_default_categories_do_not_enter_unnamed_dirs（第 148-171 行）的 artifacts/out/__pycache__ 等——后者验的是『根级 bulk 树内部』不被命中，并非『嵌套 bulk 树』。; 全文件 grep 'node_modules' 仅 7 处，全部为根级路径；无 src/node_modules、pkg/.scratch、a/b/artifacts 之类嵌套构造。
  - Impact: docstring『默认扫描不进入未点名目录树』的安全承诺在嵌套 monorepo/子项目布局下已被 f_01 证伪，而测试只钉住根级情形，给出『承诺已测』的假象；修复 f_01（改按名剪枝或逐级剪枝）时也没有现成用例可扩展验证不回归根级行为之外的深度。
  - Fix: 在 test_default_categories_do_not_enter_unnamed_dirs 旁补嵌套变体：src/vendor/node_modules/pkg/.DS_Store、pkg/.scratch/exp/note.log 等构造，断言默认类别零命中、点名类别仍可整树处理。

- [Low][90] .repo_template/scripts/repo_sync.py:819 — sync_dir/sync_skill 目标侧单个文件软链（f_05 的 copy2 跟随位点）无测试：软链覆盖只测了目录根与 cleanup 侧
  - ID: f_template_scripts_ops_18; verification: static
  - Evidence: sync_dir 的文件分支（repo_sync.py:817-820）对目标直接 shutil.copy2(entry, target)，目标为指向树外文件的软链时跟随写入树外（f_05）；sync_skill 复用同一复制路径。; 现有软链用例覆盖的是相邻面：test_sync_dir_rejects_symlink_destination 只验 sync_dir 目标『根目录』本身为软链时拒绝；cleanup 侧 test_cleanup_does_not_follow_directory_symlink_outside_repo 验的是删除不跟随；repair_symlinks 系列验的是宿主 skill 软链管理。; test_repo_sync.py 全文无『同步树内部某目标文件预置为软链』的构造，test_hard_sync_override_and_delete、test_skill_override_preserves_sync_state 的目标都是普通文件。
  - Impact: 消费仓内若有人把 .repo_template 内某文件替换成指向仓外的软链，下一次 apply 会静默改写仓外文件且 changed 清单只记软链路径——这一越界写路径没有任何测试看守，与已钉死的目录根拒绝形成不对称防线。
  - Fix: 在 test_repo_sync.py 补用例：同步目标树内放一个指向仓外哨兵文件的文件软链，断言 sync_dir/sync_skill 拒绝或只替换软链本体、哨兵内容不变，与 test_sync_dir_rejects_symlink_destination 的目录根口径对齐。

- [Low][90] .repo_template/tests/test_repo_hygiene.py:50 — repo_hygiene archive-handoff 对 fenced code block 内伪标题（f_09）无测试：同仓另两个解析器都有围栏用例、独此一切节器没有
  - ID: f_template_scripts_ops_19; verification: static
  - Evidence: f_09 已核：archive-handoff 按任意行首『## 』切节，不识别 fenced code block，handoff 节正文里代码块中的『## 』行会被误当新节标题切走。; test_repo_hygiene.py 的 6 个 archive-handoff 用例（第 50-121 行）构造的 handoff 全是普通文本分节，无一在节正文内放置带『## 』行的 ``` 代码块。; 对照同仓：check_review_status 的 extract_verdicts 与 render_review_prompts 的 extract_section 都有专门围栏用例（test_extract_verdicts_ignores_fenced_and_quoted_examples、test_extract_section_ignores_fenced_heading 等），围栏意识在套件内是既定标准，独 archive-handoff 的切节器未被同标准检验。
  - Impact: 真实 handoff 节常含命令/日志代码块，其中出现『## 』开头行（markdown 示例、脚本注释）即触发误切，把半节内容错迁进 archive 且 handoff 本体静默变短；该解析缺陷在测试层无任何拦截，修复时也无现成用例可依。
  - Fix: 在 test_repo_hygiene.py 补用例：最新节正文含 ``` 块且块内有『## 伪标题』行，断言 cmd_archive_handoff 后该节完整保留在 handoff、archive 只得旧节全文。

## views

```json
{
  "contracts": {
    "reviewer": "d4042ae7-5b4f-4ccd-9b48-8508dbf43d75",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "d4042ae7-5b4f-4ccd-9b48-8508dbf43d75",
    "status": "completed"
  },
  "design": {
    "reviewer": "d4042ae7-5b4f-4ccd-9b48-8508dbf43d75",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "d4042ae7-5b4f-4ccd-9b48-8508dbf43d75",
    "status": "completed"
  },
  "performance": {
    "reviewer": "d4042ae7-5b4f-4ccd-9b48-8508dbf43d75",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "d4042ae7-5b4f-4ccd-9b48-8508dbf43d75",
    "status": "completed"
  },
  "security": {
    "reviewer": "d4042ae7-5b4f-4ccd-9b48-8508dbf43d75",
    "status": "completed"
  },
  "tests": {
    "reviewer": "4b21145b-832c-44ca-a165-cb5f5adf6b4c",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  ".repo_template/scripts/_id_scan.py",
  ".repo_template/scripts/check_review_status.py",
  ".repo_template/scripts/export_template.py",
  ".repo_template/scripts/md_format.py",
  ".repo_template/scripts/package.json",
  ".repo_template/scripts/render_review_prompts.py",
  ".repo_template/scripts/repo_cleanup.py",
  ".repo_template/scripts/repo_hygiene.py",
  ".repo_template/scripts/repo_sync.py",
  ".repo_template/scripts/skill_registry.py"
]
```
