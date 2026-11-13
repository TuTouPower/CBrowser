# bundle_local_template_scripts_ops

## responsibilities

- export_template.py：只从已提交的 git 树（git archive）导出模板产物到空目标目录，解包前校验全部 tar 成员路径/类型/软链不越界，并拒绝 .env（非 .env.example）、.git、.commandcode、缓存目录、docs/runtime/、.claude/state/、sync_state.json 等不可分发内容混入提交
- repo_sync.py：repo-template-sync 的机械执行器——init/status/plan/apply/prompt/link-skills/install-hooks/transaction；硬同步 .repo_template 树与 .md_kx.toml、skill 整目录覆盖与宿主软链建修、.gitignore/.prettierignore/MCP 机械合并、AGENTS.md 分区协议（开发原则强制、目录规则交 agent、项目介绍保护）、workflow schema 强制迁移、sync_state.json 字段级原子更新；apply 走 FileTransaction 事务、失败回滚，干净源先经 export_template 快照再写盘，禁止自动 commit
- repo_cleanup.py：repo-cleanup 的机械执行器——按类别（默认 pycache/pytest/logs/os/editor；node/scratch/artifacts/data 须点名）扫描仓库垃圾，HARD_PROTECTED 与 docs/ 类别限制、--keep 保护、dry-run 预览与 apply 删除（含 --expected-count 候选数核对）
- repo_hygiene.py：repo-hygiene 的机械迁移动作——archive-handoff（handoff.md 最新节外整段 append 迁入 archive，含中断幂等处理）、archive-spike / archive-review（git mv 整目录 + 未跟踪残留合并）
- check_review_status.py：薄 CLI，把 note.md front matter 与 review 报告的 verdict/回归轮次/指纹新鲜度判定委托 repo_task.review.evaluate_review，输出一行一键值；--max-review-round 只能降不能升已持久化上限
- render_review_prompts.py：从 note.md front matter 把契约区/上下文区正文注入 code/test/general reviewer prompt 模板，校验 diff_anchor、spec 路径不出仓，契约区相对 anchor 漂移时附 diff 警告；--out-dir 限定仓内并原子写
- md_format.py：md_kx 的仓库内包装——点名/--changed/--all/--check 选文件，黑名单（docs/archive/、.scratch/）与越界路径拒绝，写模式失败时按内存快照回滚本次已格式化文件；库函数 format_new_file 供 pending/findings/spikes 建条目时调用，缺二进制只警告
- \_id_scan.py：pending/findings 共用的编号扫描与互斥分配——扫全部本地分支 git 树（含 legacy 单文件正文小节编号）与全部登记 worktree 工作区，同一来源内同号多状态目录报错，分配在 git 公共目录锁内「扫描取号→临时文件 os.replace 落盘」
- skill_registry.py：校验 .repo_template/skills/registry.json 与 canonical SKILL.md 清单/角色/显式调用门禁/调用边一致性，并把注册表渲染进 docs/usage.md 的 skill_registry 标记区（--write 写回，否则不一致 exit 1）；标记区经核对确实存在于 usage.md:60-90
- package.json：仅声明 {"type":"commonjs"}，使 scripts/ 下的 .js 被 Node 按 CommonJS 解析

## interfaces

- CLI：repo_sync.py 子命令 init/status/plan/apply/transaction/prompt/link-skills/install-hooks（--consumer/--source/--checkout 全局覆盖）；repo_cleanup.py scan|apply [CATEGORIES...] [--keep REL] [--expected-count N]；repo_hygiene.py archive-handoff|archive-spike sNNN|archive-review NAME [--write]；check_review_status.py --task-dir（输出 key=value 行）；render_review_prompts.py --task-dir|--note [--out-dir]；md_format.py PATH...|--changed|--all|--check；skill_registry.py [--write]
- 库接口：\_id_scan.allocate/allocate_dir/scan_max_id（供 pending.py/findings.py/spikes.py）；md_format.format_paths/format_new_file（供条目创建脚本）；repo_sync.export 的 export_template（供 cmd_apply 干净源快照）；check_review_status/render_review_prompts 依赖 repo_task.review/monitoring/documents 的判定与指纹（单一真相源在 repo_task 包）
- 状态文件契约：.repo_template/sync_state.json（本机）、sync_manifest.json（可移植来源证明，仅 resolved_commit+脱敏 source_url）、sync_policy.json（shared user_prompts）；user_prompts 的 tags 同时充当 .gitignore 合并的拦截子串来源

## dependencies

- repo_task 包（另一审阅单元）：locks.git_common_lock、file_transaction.FileTransaction/fingerprint、documents.atomic_write_text/parse_front_matter、context.TaskDataError、review.evaluate_review/review_limits、monitoring.review_scope_fingerprint、validation.run_checks/validation_environment、finalization.validate_spike（repo_hygiene 延迟导入）
- 外部工具：git（全部脚本）、md_kx 二进制（md_format 硬依赖，PATH 查找）、pytest 契约测试（repo_sync apply 门禁，CONSUMER_TEST_COMMAND 写死 .repo_template/tests/ -m contract，60s 超时）
- 同级脚本：repo_sync 顶层 import export_template.export_template 与 repo_task.\*；check_review_status/render_review_prompts 以脚本目录在 sys.path 为前提导入 repo_task

## flows

- apply（干净源）：read_state → resolve_src → src_dirty/expected-commit 校验 → FileTransaction.begin（覆盖 .repo_template、skills 宿主位、.claude/settings.json、.opencode/commands、docs/tasks、docs/archive/tasks、conventions、MCP 候选等路径）→ export_template 快照源 commit → \_apply_sync_write（硬同步→workflow 强制迁移→conventions 迁移→软链修复→opencode 薄层→.gitignore/.prettierignore 合并→MCP 合并→共享单元裁定）→ 契约测试+run_checks → 推进 last_synced_commit 并写 sync_manifest → transaction.applied；任一步抛 OSError/ValueError/SyncError/SubprocessError 则自动 rollback 并报告
- repo_cleanup apply：collect（bulk 点名树整树收集 + 主 walk 分类收集，keep/保护过滤）→ 可选 expected-count 核对 → apply_delete（删除前独立重查 keep 与保护名单，文件先行、目录按深度逆序）
- archive-handoff --write：先 append 归档（原子替换写）后重写 handoff.md 只留最新节；中断重跑以「归档尾部已含待迁文本」判定跳过 append 实现幂等
- \_id_scan.allocate：git_common_lock 内 scan_max_id（全分支 ls-tree + legacy 正文 + 全 worktree 工作区）→ +1 → 同目录临时文件写后 os.replace 原子落盘

## constraints

- 全部脚本假定在 git 仓库内运行；REPO_ROOT/CONSUMER 由脚本文件位置（.repo_template/scripts 的上两级）推导，repo_sync 可用 --consumer 改绑
- 删除/覆盖类动作的既定防线：repo_cleanup 的 HARD_PROTECTED、docs/ 仅 os/editor、未点名类别整树不进主 walk；repo_sync 的 FileTransaction 回滚与 AGENTS.md 项目介绍保护；export_template 的不可分发文件拒绝
- repo_sync 硬同步语义是破坏性的：dst 中 src 没有的非噪声条目直接删除（\_is_noise 仅豁免 __pycache__/.pytest_cache/.DS_Store/\*.pyc 与 sync_state/sync_manifest/sync_policy 三个文件名，任意深度同名均豁免）
- check_review_status 与 render_review_prompts 的路径参数一律 resolve 后校验仍在仓内（relative_to REPO_ROOT），越界即报错

## decisions

- 模板分发只认已提交树不认工作区（export_template），且 apply 干净源先快照后写盘，避免把源仓未提交状态同步进消费仓
- sync 失败回滚而非续跑：事务状态机 applied/accept 把「提交门禁」与「接受备份」分开，accept 前要求本轮路径已提交且指纹一致或复验通过
- MCP 合并只增不改：已有 server 键保留消费值防冲密钥，新建文件时模板 env 明文值替换为 \<KEY_PLACEHOLDER>（Issue #54）
- 编号分配宁可报错不重号：跨来源重复容忍（合并前暂时重复），同来源重复立即 IdScanError 暴露迁移残留

## evidence

- .repo_template/scripts/export_template.py:20-65 解包三阶段（校验→写文件→建软链→验软链不越界）；:88-96 不可分发文件扫描
- .repo_template/scripts/repo_sync.py:739-778 sync_dir 树对树覆盖/删除；:823-845 \_ensure_symlink 真实目录转软链；:1843-1935 cmd_apply 事务与回滚；:253-285 resolve_src 的 clone/pull
- .repo_template/scripts/repo_cleanup.py:131-211 collect 双通道收集与 keep 过滤；:214-241 apply_delete 二次防线；:158-165 主 walk 剪枝集合
- .repo_template/scripts/repo_hygiene.py:96-135 archive-handoff 幂等 append 与重写；:155-172 git mv + 残留合并
- .repo_template/scripts/\_id_scan.py:212-273 锁内编号分配与原子落盘；:84-122 分支树文件名+目录身份扫描
- .repo_template/docs/usage.md:60-90 skill_registry 标记区实际存在，与 skill_registry.py 的 START/END 常量一致
- unit_plan.json 中 template_tests 单元文件清单：本单元 10 个文件中 6 个有同名测试文件（test_repo_cleanup/test_repo_hygiene/test_repo_sync/test_check_review_status/test_render_review_prompts/test_md_format），export_template.py、skill_registry.py、\_id_scan.py 无专属测试文件

## uncertainties

- repo_task 包（locks/file_transaction/review/monitoring 等）属 template_scripts_state 单元，本单元只核对了调用契约面，未审其实现：FileTransaction 是否完整快照目录型路径、git_common_lock 的重入与跨进程语义、evaluate_review 的判定细节均以该单元审阅为准
- 各脚本的测试内容质量（断言强度、是否触达生产逻辑）属 template_tests 单元范围，本单元仅核对了覆盖存在性映射，未逐个阅读测试文件
- 本轮为静态审阅，未运行任何脚本：md_kx 的实际退出码语义、git archive 成员顺序、Path.rglob 对软链目录的行为等运行时细节以代码与文档契约推断，相关 finding 已标 suspected

## Findings

- [Medium][85] .repo_template/scripts/repo_cleanup.py:158-165 — cleanup 主 walk 的剪枝只按仓库根相对路径匹配，嵌套 node_modules / 嵌套 bulk 树 / 嵌套 .git 不被剪枝，未点名类别的垃圾会在这些树内被默认类别命中删除

    - ID: f_template_scripts_ops_01; verification: static
    - Evidence: collect() 中 prune = {".git", *bulk_roots}（bulk_roots 为根相对的 .scratch/artifacts/data），\_prune 用完整相对路径 rel 与集合比对：根级 node_modules 的 rel 为 "node_modules" 可命中，但 "src/frontend/node_modules" 的 rel 不在集合中，os.walk 继续下钻; 模块 docstring（:13-15）明确承诺「默认扫描不进入未点名的 node_modules 与这三棵目录树（防误删未点名内容）」，实现只兑现了根级情形; 本仓布局即含嵌套场景：前端在 src/frontend/，其 node_modules 及仓库内任何嵌套 data/、artifacts/ 目录都会被主 walk 遍历，内部 *.pyc/*.log/.DS_Store/*~ 等会被 pycache/logs/os/editor 默认类别命中并在 apply 时删除，尽管用户从未点名 node/artifacts/data 类别
    - Impact: 在含嵌套 node_modules 或嵌套同名目录的仓库运行 repo_cleanup.py apply（默认类别），会删除未点名类别树内的文件，违反脚本自身声明的防误删契约；同时对大型嵌套 node_modules 全量遍历带来明显扫描开销
    - Fix: 剪枝改按路径分量/基名判定：任一路径段为 .git、node_modules（node 未点名时）或与根 bulk 目录同名的受控名时整段剪枝；或在 \_prune 中同时比对基名集合，并为嵌套情形补测试

- [Medium][70] .repo_template/scripts/repo_sync.py:739-778 — sync_dir/sync_file 向目标写文件时不防目标侧文件软链：dst 是指向仓外文件的软链（或断链）时 shutil.copy2 跟随链接把模板内容写到仓外目标

    - ID: f_template_scripts_ops_02; verification: suspected
    - Evidence: sync_dir 对 dst_dir 本身是软链、以及「src 是目录而 dst 是目录软链」两种情形有显式拒绝（:741、:756），但 src 是普通文件时只调 \_reject_dir_target（仅拒绝 dst 为真实目录），随后 shutil.copy2(entry, target)（:768）；copy2 对 dst 软链默认跟随，写入链接指向的文件; 断链情形更隐蔽：`if not target.exists() or _file_differs(...)` 中断链 exists() 为 False，直接进入 copy2，copyfile 打开 dst 路径即在链接目标处创建/覆盖文件; sync_file（:782-798）同一模式：copy2(src, dst) 前未检查 dst.is_symlink()；sync_skill 的文件分支同样经 \_reject_dir_target + copy2; 同仓其他脚本对同类风险均有专门防线（repo_cleanup 对 bulk 根软链越界的 Issue #16 处理、sync_dir 自身的目录软链拒绝），说明文件级 dst 软链属遗漏而非有意设计
    - Impact: 消费仓 .repo_template/.agents/skills 等同步目标树内若存在被植入或误建的指向仓外的文件软链（例如指向 ~/.claude/settings.json 或其他仓库文件），apply 会把模板文件内容覆盖写到仓外目标，造成越界写与目标文件损坏；FileTransaction 的备份范围是仓内路径，仓外被写文件不在回滚范围内
    - Fix: 在 sync_dir/sync_file/sync_skill 的文件写入前统一检查：dst 存在且 is_symlink() 时先 unlink 再写（与 \_ensure_symlink 的处理一致），或显式拒绝并报错要求人工处理；同时对 \_file_differs 的断链分支补 is_symlink 判断

- [Medium][80] .repo_template/scripts/repo_sync.py:2063-2074 — link-skills 子命令在无事务保护下调用 repair_symlinks，可 rmtree 宿主位真实目录且报告谎称「原内容入回滚栈」

    - ID: f_template_scripts_ops_03; verification: static
    - Evidence: \_ensure_symlink（:823-845）：宿主位是真实目录时直接 shutil.rmtree(link) 后建软链，report 文案为「旧真实目录已转软链（原内容入回滚栈）」; cmd_apply 路径下 FileTransaction 覆盖 .agents/skills/.claude/skills，rmtree 内容确可经事务回滚；但 cmd_link_skills（:2063-2074）直接调用 repair_symlinks，全程没有 FileTransaction.begin，目录内容被永久删除且无任何备份; usage.md:18 把 link-skills 描述为改 SKILL.md 后日常重跑的轻量命令，使用频率高、使用者预期其低风险
    - Impact: 用户在 .claude/skills/<name> 或 .agents/skills/<name> 放了真实目录（无论是旧模板副本还是误放的自有内容）时，日常执行 link-skills 即不可恢复地删除整个目录，且输出文案误导其以为可回滚
    - Fix: link-skills 路径也纳入 FileTransaction（或独立备份目录）；或 \_ensure_symlink 增加 require_backup 参数，无事务时对真实目录改为报错要求人工处理/显式 --force，并修正文案使其只在确有回滚栈时声称已备份

- [Medium][75] .repo_template/scripts/repo_sync.py:1081-1097 — sync_opencode_commands 对 registry 缺失条目用 roles[name] 硬下标，KeyError 会穿透 cmd_apply 的回滚异常集导致半同步现场无回滚

    - ID: f_template_scripts_ops_04; verification: static
    - Evidence: opencode_commands_status（:1019）用 roles.get(name, {}).get("role") 容忍 skill 目录未登记 registry；sync_opencode_commands（:1097）却用 roles[name]["role"]，模板源出现未登记 skill 目录时抛 KeyError; sync_opencode_commands 在 \_apply_sync_write 内被调用，此时硬同步与 workflow 迁移可能已写盘；cmd_apply 的回滚 handler（:1919）只捕获 (OSError, ValueError, SyncError, subprocess.SubprocessError)，KeyError 不在其列; main() 的兜底也只捕获 (SyncError, TaskDataError, OSError)，KeyError 最终以裸 traceback 终止，事务既未 rollback 也未 applied，留下混合版本工具文件
    - Impact: 模板源 registry.json 与 skills 目录不一致（新增 skill 忘登记）时，一次 apply 在中途崩溃且不回滚，消费仓工具链处于新旧混合状态，后续 status/plan 的结论也随之不可信
    - Fix: sync_opencode_commands 与 status 统一用 .get 容忍并对未登记 skill 抛 SyncError（使其进入回滚路径）；或把 cmd_apply 回滚 handler 扩为捕获 Exception 后回滚再抛

- [Low][80] .repo_template/scripts/repo_sync.py:253-285 — resolve_src 对 URL 源在每次调用时执行 clone/pull，status/plan 等只读命令实际会写盘缓存并在离线时整体失败

    - ID: f_template_scripts_ops_05; verification: static
    - Evidence: resolve_src（:253-285）：URL 源时若 .scratch/repo_template_sync_src/.git 不存在则 git clone（:270），存在则校验 origin 后无条件 git pull --ff-only（:277），pull 失败即 SyncError; cmd_status、cmd_plan 均先调用 resolve_src；plan 子命令在 build_parser 中自述「计算差异预览（零写盘）」，但 URL 源下 plan 会 clone/pull 修改缓存 checkout，并非零写盘; 已有可用缓存时若网络不可达，status/plan 也无法降级使用缓存给出差异结论
    - Impact: URL 源消费仓在离线/网络受限环境连只读的 status/plan 都不可用；plan 的「零写盘」契约对 URL 源不成立，审计/自动化若按只读假设调用会意外触发网络与写盘
    - Fix: 为 resolve_src 增加 read_only 模式：status/plan 默认不 pull，仅当缓存缺失时才 clone 并在输出中标注缓存新旧；或 pull 失败时回退缓存并打 WARNING（与 src_dirty 的 F36 处理口径一致）

- [Low][85] .repo_template/scripts/repo_sync.py:155-190 — read_state 对手改 JSON 的防御不一致：manifest 缺 resolved_commit 抛 KeyError、policy 顶层非对象抛 AttributeError，均以裸 traceback 终止而非 SyncError 指引

    - ID: f_template_scripts_ops_06; verification: static
    - Evidence: read_state 对 sync_state.json 与 manifest/policy 的 JSON 解析错误都包装为 SyncError 并给出恢复指引（:162-174、:186-189），但 manifest 回退分支直接 portable["resolved_commit"]（:177），键缺失时 KeyError 无包装; policy 分支 json.loads(...).get("user_prompts", [])：policy 顶层若为 JSON 数组/标量则 AttributeError，同样未包装; 同文件 write_state/cmd_prompt 等入口都以 SyncError 为统一错误面，main() 不捕获 KeyError/AttributeError
    - Impact: sync_manifest.json/sync_policy.json 被手改或由旧版本写出异形内容时，所有 repo_sync 子命令以无指引的 traceback 失败，与该脚本其余状态损坏场景的友好报错口径不一致，排障成本上升
    - Fix: manifest 回退分支校验 isinstance(portable, dict) 且含 resolved_commit，policy 分支校验顶层为 dict，异常统一转 SyncError 并给出与现有文案一致的恢复路径

- [Low][65] .repo_template/scripts/repo_hygiene.py:110-135 — archive-handoff 的幂等判定用「归档文件尾部恰好以待迁文本结尾」推断已追加，同文重现时可误判跳过 append 却仍执行 handoff 重写，造成段落永久丢失

    - ID: f_template_scripts_ops_07; verification: suspected
    - Evidence: cmd_archive_handoff（:116）：existing.rstrip("\\n").endswith(stale_text.rstrip("\\n")) 为真时跳过 append，随后无条件把 HANDOFF 重写为仅保留最新节（:132-133）; 误判条件：待迁段落文本此前已因别的原因出现在归档文件尾部（如相同模板段落被重复迁移、或上一轮迁移的正是同文段落而本轮 handoff 又生成了同文新段落），endswith 为真但本轮段落从未归档; handoff 节标题通常含日期使同文概率低，但脚本未利用标题/时间做更强同一性判定，纯文本尾缀匹配是唯一依据
    - Impact: 极端但可构造的情形下，过时段落从 handoff.md 被移除且未写入 docs/archive/handoff.md，归档内容静默丢失，违反 archive 只增不丢的定位
    - Fix: 幂等标记改为显式证据：append 时在归档段落前写入含本轮段落首标题与长度/哈希的标记行，重跑时按标记判定；或跳过 append 时同时校验 handoff 当前内容与「上一轮已重写」形态一致，否则报错停手

- [Low][70] .repo_template/scripts/repo_hygiene.py:69-80 — \_split_handoff 按行首 "## " 切节且不感知 fenced code block，handoff 正文代码块内的 ## 行会被当作节边界切断段落

    - ID: f_template_scripts_ops_08; verification: static
    - Evidence: \_split_handoff（:69-80）仅以 line.startswith("## ") 收集节边界，无围栏状态跟踪; 同工具链的 render_review_prompts.extract_section（:60-90）对同一问题有专门的 fence 感知实现，说明该风险在本项目已被识别并处理，repo_hygiene 未对齐; handoff.md 内容为自由文本交接记录，粘贴含 markdown 示例/日志的围栏块是现实用法
    - Impact: handoff.md 某节的代码块内含 "## " 开头行时，archive-handoff 会把一节切成两节：「最新节」判定与迁移清单随之错位，可能把本应保留的最新节内容误迁入归档（内容不丢但现行 handoff 被截断）
    - Fix: \_split_handoff 复用与 extract_section 相同的围栏跟踪逻辑（\`\`\` / ~~~ 开闭与宽度匹配）后再判定 H2 边界，并补含围栏的回归测试

- [Low][65] .repo_template/scripts/repo_sync.py:1351-1365 — MCP 合并的占位化只处理 env 字典，模板 server 的 command/args/url 中携带的明文凭据会原样写入新建的消费仓 MCP 配置

    - ID: f_template_scripts_ops_09; verification: suspected
    - Evidence: \_sanitize_mcp_servers（:1351-1365）只遍历 v_copy["env"] 的字符串值做占位替换，command、args、url、headers 等字段不检查; merge_mcp（:1368-1400）在消费侧文件不存在时以 sanitized 结果整文件新建，并仅在报告中标注「已占位化环境参数，需审阅」；args 数组里如 --api-key=xxx 形式的令牌、url 中的 userinfo 都会原样落盘; 该机制的存在目的正是防模板侧真实值随同步扩散（Issue #54），当前实现只覆盖了 env 一条通道
    - Impact: 模板仓 MCP 配置若在 args/url 中放了真实令牌，首次同步到任一消费仓时即被复制进消费仓配置文件，存在随消费仓提交扩散的风险，与占位化机制的声明目标不完全一致
    - Fix: 扩展 sanitize 到 args 列表元素与 url 的 userinfo/query、对 headers 同 env 处理；或在新建报告中明确列出「env 之外字段未检查，需人工审阅全部字段」而非只称环境参数已占位化

- [Low][95] .repo_template/scripts/render_review_prompts.py:4 — 模块 docstring 称 prompt 模板为三个 txt，实际加载四个（含 general_prompt.txt），文档与实现漂移

    - ID: f_template_scripts_ops_10; verification: static
    - Evidence: render_review_prompts.py:4 docstring：「提示词正文存于 .repo_template/docs/review_prompts/ 下三个 txt（code_prompt.txt / test_prompt.txt / share_prompt.txt）」; render_review_prompts()（:197-202）实际加载 code/test/general/share 四个模板，general 用于 review_level=single 时渲染 general_review_prompt.md（:256-263）; 用法段（:12-16）也未提 single 级渲染产物与 full 的区别
    - Impact: 维护者按 docstring 盘点模板文件会漏掉 general_prompt.txt，排查 single 级 prompt 问题时入口信息错误；属低风险文档漂移，但该脚本是 review 流程唯一入口，入口文档应准确
    - Fix: 更新 docstring 列全四个模板并注明 full→code+test、single→general 的对应关系，用法段补 single 的输出文件

- [Low][70] .repo_template/scripts/export_template.py:1-116 — 本单元三个脚本无专属测试：安全敏感的 export_template（tar 解包防线）、skill_registry、\_id_scan 在 .repo_template/tests 无对应测试文件

    - ID: f_template_scripts_ops_11; verification: static
    - Evidence: unit_plan.json 的 template_tests 单元清单中存在 test_repo_cleanup.py、test_repo_hygiene.py、test_repo_sync.py、test_check_review_status.py、test_render_review_prompts.py、test_md_format.py，覆盖本单元 10 个文件中的 6 个脚本; 清单中无 test_export_template.py、test_skill_registry.py、test_id_scan.py（\_id_scan 仅可能经 test_pending/test_findings 间接覆盖分配路径）; export_template 的软链越界/重复路径/.env 拒绝等防线全为手写校验逻辑，无专属回归测试时重构易静默削弱分发安全边界
    - Impact: 模板分发这一安全边界（防 .env/仓外软链随产物扩散）缺乏直接回归保护，后续改动若破坏校验顺序（如先建软链后写文件）不会被现有测试拦下
    - Fix: 为 export_template 补专属测试：含 ../ 路径、绝对软链、链式越界软链、重复成员、.env 与 sync_state.json 混入、目标非空拒绝等用例；skill_registry 补标记缺失/registry 与目录不一致用例

- [Low][85] .repo_template/scripts/md_format.py:193-197 — md_format CLI 对点名的黑名单路径静默丢弃，与 format_paths「拒绝格式化」的库语义不一致，点名归档文件得到 exit 0 的「无改动」假象

    - ID: f_template_scripts_ops_12; verification: static
    - Evidence: main（:196-197）：args.paths 先以 [p for p in args.paths if not \_is_blacklisted(p)] 过滤，黑名单路径在进入 format_paths 前已被丢弃; format_paths（:118-121）则对黑名单路径抛 MdFormatError，其注释明确写道「黑名单先于缺二进制：拒绝归档路径不依赖本机是否安装 md_kx」，即库层设计意图是显式拒绝; 结果：md_format.py docs/archive/x.md 输出「无改动」且 exit 0，使用者无法区分「文件已格式化且无变化」与「路径被拒绝根本没处理」
    - Impact: 显式点名场景下静默吞掉输入，违反最小惊讶；若有自动化按 exit 0 判断归档文件已处理，会得到错误结论（实际格式化从未发生，好在方向是保守的未写入）
    - Fix: CLI 点名路径含黑名单项时报错列出被拒路径（与库语义统一）；--changed/--all 的批量过滤保持静默即可

- [Low][75] .repo_template/scripts/repo_sync.py:1556-1590 — cmd_init 无条件删除 legacy state 文件，新 state 已存在时 legacy 中未合并的 user_prompts 会被静默丢弃

    - ID: f_template_scripts_ops_13; verification: static
    - Evidence: cmd_init（:1556-1590）：仅当 STATE_PATH 不存在时才把 legacy 内容作为 base 写新 state（:1560-1577），但随后只要 LEGACY_STATE_PATH 存在就 unlink（:1580-1587），不区分是否发生过合并; 新旧两处 state 并存的情形（新路径 init 过一次、旧宿主目录又被旧版工具写过）下，legacy 独有的 user_prompts/last_synced\_\* 在删除前从未被读取合并; read_state 的读取优先级也是新路径优先，legacy 被删后其内容无任何其他读取机会
    - Impact: 双 state 并存时运行 init 会永久丢失 legacy 侧的站立指令（user_prompts 影响后续 .gitignore 裁定与同步行为），且无提示
    - Fix: unlink 前若新 state 已独立存在且 legacy 含新 state 没有的 user_prompts，先合并或至少打印警告并保留备份文件，不静默删除

- [Low][70] .repo_template/scripts/export_template.py:88-96 — 导出不可分发检查是名字黑名单制且 dirty 直写路径完全绕过：非名单内的敏感文件（如 \*.pem、credentials.json）可随产物导出，--allow-dirty-source 同步则连 .env 检查都不经过

    - ID: f_template_scripts_ops_14; verification: suspected
    - Evidence: export_template 的分发前扫描（:88-96）只拒绝固定名字/前缀：.git、.commandcode、__pycache__、.pytest_cache、.env/.env.\*、docs/runtime/、.claude/state/、sync_state.json；提交进 .repo_template 的私钥/凭据文件在其它名下不被拦截; repo_sync cmd_apply 的 dirty 分支（--allow-dirty-source，:1865-1870）直接以源工作区调 \_apply_sync_write，sync_dir 的 \_is_noise 不含 .env 类规则，源仓工作区里未提交的 .env 也会被树对树复制进消费仓; 干净路径的安全叙事（「提交含不可分发文件」即拒绝导出）容易让使用者误以为同步链整体有凭据防线
    - Impact: 模板仓误提交凭据文件（非 .env 命名）时可随模板产物分发到所有消费仓；开发验证用 dirty 同步时源仓本地 .env 可被带入消费仓。两者均需人为误操作在先，故定 Low
    - Fix: 导出扫描改为黑名单+敏感模式双轨（*.pem/*.key/credentials\*/id_rsa\* 等一并拒绝）；dirty 直写前对源树跑同一份不可分发扫描，命中即拒绝并要求改走干净源

- [Info][85] .repo_template/scripts/repo_sync.py:137-142 — repo_sync.\_git 不翻译 subprocess.TimeoutExpired，与同工具链其他脚本的包装口径不一致，慢 git 调用以裸 traceback 终止

    - ID: f_template_scripts_ops_15; verification: static
    - Evidence: \_git（:137-142）subprocess.run(timeout=30) 无 try/except，TimeoutExpired（SubprocessError 子类）在 cmd_status/cmd_plan/cmd_init 等事务外路径不被 main() 的 (SyncError, TaskDataError, OSError) 捕获; 对照同单元 repo_cleanup.repo_root 与 repo_hygiene.\_git 都专门捕获 TimeoutExpired 并转领域错误（repo_cleanup.py:56-57、repo_hygiene.py:47-52）
    - Impact: git 因锁等待/网络文件系统变慢超过 30s 时，只读命令以 traceback 失败，无超时语义提示；cmd_apply 内因 except 含 SubprocessError 可回滚，影响限于事务外命令的观感与排障
    - Fix: \_git 内捕获 TimeoutExpired 转 SyncError 并注明命令与超时阈值，与同工具链口径统一

- [Info][80] .repo_template/scripts/\_id_scan.py:256-270 — allocate_dir 对 files 字典的相对文件名不做越界校验，绝对路径或 .. 键可写出临时目录之外（当前调用方均为内部固定文件名，属潜伏契约缺口）

    - ID: f_template_scripts_ops_16; verification: static
    - Evidence: allocate_dir（:262-270）：dest_file = tmp_dir / name 后直接 write_bytes；name 为绝对路径时 Path 拼接丢弃 tmp_dir 前缀，含 .. 时可上溯到 target_dir 之外，且写入发生在锁内、os.replace 之前，异常清理只 rmtree tmp_dir，不回收已写出的越界文件; 同文件 allocate 的 slug 有 SLUG_RE 严格校验（:226-227、:255-256），说明入口校验是既定风格，files 键未做同等处理; 现有调用方（spikes/task 流程）传入的是固定文件名集合，未发现可达的用户输入路径
    - Impact: 当前无实际触发路径；作为被 pending/findings/spikes 共用的库函数，未来调用方若把外部数据拼进 files 键，会在编号锁内向任意可写路径落文件且不留清理
    - Fix: 写入前校验每个 name：非绝对、不含 .. 分量、resolve 后仍在 tmp_dir 内，不合规抛 IdScanError

## views

```json
{
  "contracts": {
    "reviewer": "f64cda77-d088-4c3c-849e-47ec6a6c1ecc",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "f64cda77-d088-4c3c-849e-47ec6a6c1ecc",
    "status": "completed"
  },
  "design": {
    "reviewer": "f64cda77-d088-4c3c-849e-47ec6a6c1ecc",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "f64cda77-d088-4c3c-849e-47ec6a6c1ecc",
    "status": "completed"
  },
  "performance": {
    "reviewer": "f64cda77-d088-4c3c-849e-47ec6a6c1ecc",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "f64cda77-d088-4c3c-849e-47ec6a6c1ecc",
    "status": "completed"
  },
  "security": {
    "reviewer": "f64cda77-d088-4c3c-849e-47ec6a6c1ecc",
    "status": "completed"
  },
  "tests": {
    "reviewer": "f64cda77-d088-4c3c-849e-47ec6a6c1ecc",
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
