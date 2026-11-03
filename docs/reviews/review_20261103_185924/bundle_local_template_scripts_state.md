# bundle_local_template_scripts_state

## responsibilities

- repo_task 包是 task.py CLI 的状态机实现：note.md front matter 为 task 状态权威（store/documents/lifecycle），docs/runtime/dispatch_ledger.jsonl 为执行权威（ledger/attempts），派生 tasks_index.json 由 scan 重建（store.rebuild_index）。
- 生命周期与集成：lifecycle.py 管 add/edit/preflight/finish/drop/rewind/purge/list/show；integration.py 管 start（建 branch/worktree）、cleanup-worktree、integrate 与 integrate-chain（原生 git merge + merge-tree 内容门禁）；graph.py 管 backlog 原子合并（FileTransaction 保护）。
- 调度与展示：scheduling.compute_schedule 算可跑集，plan.compute_batch_plan 算本波并发链（算法权威），control.py 提供 view/ps/attempt 命令面，view_server.py + view_static/ 提供只读本地看板（服务端注入 model.plan，JS 只渲染）。
- 监控与恢复：monitoring.py 做 handoff/review 门禁核验（verify_integrate_ready）与 review scope 指纹；recovery.py 只读分类中断阶段；goal.py 冻结 goal 队列快照并只读判定终态。
- 条目脚本：pending.py / findings.py / spikes.py 管 p/d/s 编号条目的分配、列举、迁移与改名（编号分配委托 _id_scan，本单元外）；repo_state.py 只读评估完整工作树相对 baseline 的变更；track_worktree.py 是状态栏 worktree 追踪的 hook 写入器与标记入口。

## interfaces

- CLI：task.py 子命令 add/edit/start/preflight/limits/finish/drop/rewind/purge/list/show/effective-status/view/plan/attempt{reserve,claim,terminal,report}/cleanup-worktree/integrate/integrate-chain/ps/goal/goal-check/ledger{tail,import}/recovery/merge-backlog/graph-transaction/review-upgrade。
- 数据契约：note.md front matter 固定键 FRONT_MATTER_KEYS（context.py）；ledger 事件 attempt_reserved/execution_claimed/attempt_terminal/report/integrated/start；handoff.json 必填字段与类型（monitoring._HANDOFF_TYPES）；review 报告 verdict/reviewed_scope/处置表格式（review.py）。
- HTTP：view_server 仅 GET /、/static/{board.css,board.js,chain_plan.js}、/task-doc?tid&doc&token；默认绑 loopback，非 loopback 须 --allow-non-loopback。
- 跨脚本：pending.py 复用 repo_task.documents.atomic_write_text 与 _id_scan.id_lock；validation.run_checks 被 task 与 sync 共用（模块 docstring 声明）。

## dependencies

- 仅 Python 标准库（argparse/subprocess/hashlib/http.server 等）+ git CLI；无第三方包、无网络调用（view_server 主动打开本机浏览器除外）。
- _id_scan.py（allocate/allocate_dir/id_lock）与 md_format.py 被 pending/findings/spikes 引用，但不在本单元文件清单内，其校验与锁语义未核对。
- 运行环境假设：主工作区/主干分支判定（git_ops.require_primary_worktree）、git >= 2.38（merge-tree --write-tree 内容门禁）、docs/blueprint/testing.md 的项目验证策略（validation.load_policy）。

## flows

- 执行主线：add（锁内取号建目录）→ start（校验 spec/依赖/验证策略 → 建 worktree 并写 active+diff_anchor → best-effort 记 ledger start）→ attempt reserve（领域门禁 + 锁内分配 attempt/execution_id + 写 execution_context.json）→ claim/terminal/report（exact identity 校验）→ finish（AC/finalization 门禁 → 归档目录）→ cleanup-worktree（exact 门禁后移除 worktree）→ integrate（merge 准备 → 验证 → --continue 提交 + append integrated + 删分支）。
- 失败恢复：recovery 只读分类（evidence_repair/committed_unreported/reported_uncleaned 等）→ 证据修复走 amend 同一执行 commit；ledger 丢失且有 done 分支持 handoff 时 ledger import 重建三事件。
- 看板：view --serve → 每请求重算 compute_schedule + compute_batch_plan（500ms 渲染缓存）→ HTML 注入转义后的 model JSON → board.js 渲染 DAG/链面板，/task-doc 按 token 与有效状态来源（worktree 文件/branch git show/main）读文档。

## constraints

- 静态审阅：未运行任何代码/测试/构建；所有结论为静态证据或疑点（verification=static/suspected）。
- fail-closed 是全仓一致的设计基调：ledger 损坏行拒绝继续、git status 失败抛错而非当作干净、review 指纹算不出返回空串、审计写失败中止状态迁移；findings 已按此基调校准严重度。
- 凭据面：本单元未发现硬编码 secret/真实邮箱/本机绝对路径；.env 仅以文件名被 worktrees.link_local_env 软链进 task worktree（内容不经本代码读取/打印）。

## decisions

- 状态双权威分离：文档状态以 note.md front matter 为准、执行状态以 ledger exact identity (tid, attempt, execution_id) 为准，派生索引可随时重建——多处代码注释与校验与此一致。
- 一个 task 恰一个执行 commit：handoff.base_sha、front matter diff_anchor 与分支 tip first parent 三方等值校验（monitoring.verify_integrate_ready）。
- 合并内容门禁：用 git merge-tree 重算自动合并结果，staged 内容只许偏离于冲突文件与派生索引（integration._validate_merge_staged_scope）。
- 所有权接管不靠时间过期：claim 须 --replace-owner + --confirm-stopped 显式确认原会话停止（attempts.claim_execution）。

## evidence

- .repo_template/scripts/repo_task/attempts.py:34-96 project_attempts 投影与 OPEN_STATES
- .repo_template/scripts/repo_task/monitoring.py:331-470 verify_integrate_ready 三方等值与 review 门禁
- .repo_template/scripts/repo_task/integration.py:560-615 _validate_merge_staged_scope merge-tree 门禁
- .repo_template/scripts/repo_task/locks.py:76-139 file_lock 线程可重入 + git_common_lock 验证隔离
- .repo_template/scripts/repo_task/ledger.py:29-66 损坏行 fail-closed 与 tid 预筛
- .repo_template/scripts/repo_task/view_server.py:53-110 模型注入转义与 500ms 渲染缓存

## uncertainties

- _id_scan.py 不在本单元：allocate/allocate_dir 是否校验 slug、id_lock 与 locks.TASK_ID_LOCK_NAME 是否同一把锁无法核对（影响 f_template_scripts_state_07 的定级）。
- 本单元无测试文件，脚本的实际测试覆盖与质量在 template_tests 单元，未核对；tests 视角因此标 partial。
- repo_state.py 的路径基准问题（f_template_scripts_state_01）依赖 git 在子目录下 ls-files/diff 的路径输出基准，未实测 git 行为，仅按 git 文档语义静态推断。
- /task-doc 的会话 token 定位（真鉴权还是防误触）代码与注释未声明，f_template_scripts_state_03 按其实际可达性定级。
- tests 视角由独立 viewfix 补审完成（原审阅者因本单元 34 个文件不含测试文件标 partial）：补审通读了 template_tests 单元中实际测试本单元代码的测试文件——test_repo_state.py、test_pending.py、test_goal.py、test_plan.py、test_task_scheduling.py、test_task_start_flow.py、test_dispatch_integration.py、test_evidence_repair.py、test_workflow_contracts.py、test_design_regressions.py、test_review_report_regressions.py、test_check_review_status.py、test_review_scope_fingerprint.py、test_task_document_validation.py、test_task_save.py、test_task_archive_dir.py、test_task_unverified.py、test_task_modularization.py、test_view_server.py、test_chain_plan.py/test_chain_plan_cases.js、test_contract_suite.py 与 review_support.py——并以 grep 核对本单元各模块的测试引用分布。结论：CLI/账本/集成层为真实 git 端到端覆盖、断言为行为级，空白集中在 repo_state 子目录调用、board.js、账本损坏输入与 view_server 真实 HTTP 四处（见 f_template_scripts_state_17..20）。另注：真实 E2E 夹具经 review_support 合成 PASS 证据并关闭项目门禁命令这一覆盖 caveat 已由 template_tests 单元自有 finding 记录，本视角不重复立项，仅标注其同样适用于本单元的 finish/cleanup/integrate 覆盖。

## Findings

- [Medium][75] .repo_template/scripts/repo_state.py:44-57,86-101,156-186 — repo_state.py 混用 CWD 相对与仓库根相对的路径基准，在子目录运行时静默给出错误结果
  - ID: f_template_scripts_state_01; verification: static
  - Evidence: _git() 不指定 cwd，全部 git 调用继承进程 CWD；_untracked_files 用 `git ls-files --others`（默认输出相对 CWD 的路径），_diff_name_only 用 `git diff --name-only`（默认输出相对仓库根的路径），两者在 cmd_changed_files 中直接拼接去重并用同一组 fnmatch --exclude 匹配——CWD 非仓库根时同一文件以两种相对形式出现、exclude 匹配口径不一致。; cmd_added_lines 对 _untracked_files 返回的路径执行 Path(path).is_file()/read_text（相对 CWD 解析），与 ls-files 的路径基准叠加后，未跟踪文件全文可能被静默跳过（is_file 为假即 continue，无警告）。; cmd_deliverable 的 path.exists() 相对 CWD，而其 git diff --stat 以仓库根语义解释同一参数；本仓其他脚本一律以 context.REPO_ROOT 锚定路径，repo_state.py 是唯一例外，其 docstring 也未声明必须在仓库根运行。; 该脚本输出喂给 task 收尾的 deliverable 核对与清洁度 grep 计数（文件头 docstring 明示），路径基准错位会造成 deliverable 误报 missing 或新增行漏计，且无任何报错。
  - Impact: 在仓库子目录（或被其他工具以任意 CWD 调用）时，changed-files/added-lines/deliverable 结果不可靠且静默降级，可能让收尾清洁度检查漏过未提交改动或误判交付物缺失。
  - Fix: 在 repo_state.py 启动时解析仓库根（git rev-parse --show-toplevel）并 chdir 或对所有路径做根锚定；ls-files 加 --full-name 统一为根相对路径，Path 解析一律以仓库根为基准。

- [Low][95] .repo_template/scripts/repo_task/lifecycle.py:838-854 (cmd_show) — cmd_show 输出的 task_md 字段实际指向 note.md
  - ID: f_template_scripts_state_02; verification: static
  - Evidence: ref 分支：fields["note_md"] 与 fields["task_md"] 都赋值为 f"{ref_name}:{task['dir']}/note.md"（lifecycle.py:846-847）。; 本地分支：path 来自 load_task（即 note.md 路径），fields["note_md"] 与 fields["task_md"] 都赋值为 ctx._rel(path)（lifecycle.py:852-853）。; task.md 是同目录另一文件，show 输出中没有任何字段指向它；view_server 的 _DOC_NAMES 映射（task→task.md）是正确的同名概念实现，可对照。
  - Impact: show 的消费者（含按字段取 task.md 路径的 agent/脚本）会打开 note.md 当作 spec，误读契约区内容；仅展示元数据错误，不影响状态机本身。
  - Fix: cmd_show 两分支把 task_md 改为 task['dir'] + '/task.md'（ref 形式加 ref 前缀），并补一条 show 输出字段的回归测试。

- [Low][90] .repo_template/scripts/repo_task/view_server.py:61-67,285-303 — /task-doc 的会话 token 随看板首页下发给任何可达客户端，不构成访问控制
  - ID: f_template_scripts_state_03; verification: static
  - Evidence: _build_model() 把 _SESSION_TOKEN 写入 model['token']，_render_html 将整个 model JSON 注入首页 HTML；任何能 GET / 的客户端同时拿到 token。; /task-doc 唯一的校验是 token == _SESSION_TOKEN；首页与 /static/* 无任何校验。绑定非 loopback 时（--allow-non-loopback，代码以 WARNING 放行），网络内任意主机取首页即得 token，进而读取全部 task spec/正文。; loopback 默认下风险有限，但 token 给出的『有令牌保护』表象与实际可达性不符；同源策略可挡普通跨站读取，却挡不住能直连端口的网络对端与 DNS-rebinding 场景。
  - Impact: 使用者可能误以为 /task-doc 受令牌保护而在非 loopback 绑定时暴露 task 文档；实际保密性等同于首页本身的可达性。
  - Fix: 若 token 意在防本机其他进程/页面误触，在 serve 的非 loopback 警告与模块 docstring 中明确其非鉴权定位；若需真鉴权，应改为启动时打印的一次性 URL 且不随首页 JSON 下发，或要求请求头携带而非查询参数。

- [Low][90] .repo_template/scripts/repo_task/view_static/chain_plan.js:36-94 与 .repo_template/scripts/repo_task/plan.py:1-7 — chain_plan.js 仍复刻了 Python 的链停止原因算法，与『看板 JS 不复刻算法』的声明矛盾
  - ID: f_template_scripts_state_04; verification: static
  - Evidence: plan.py 模块 docstring 明示：『算法权威在本模块 compute_batch_plan……看板 JS 只做展示，不复刻本算法』；chain_plan.js 文件头亦自称『本文件不再实现批计划算法，避免与 Python 双实现漂移』。; 但 chain_plan.js 的 chainStopInfo 完整重写了 Python chain_stop_info 的判定（后继枚举、暂缓/他链/汇合点分支与文案），board.js 在 chain.stop_reason 缺失时以它兜底（buildChainCard），与 Python 版存在细节差异（如 Python 对 upstream 父节点的 unfinished 判定走 cat_of 类别、JS 走 blocksDownstream 类别集合，措辞与分支顺序亦非逐字一致）。; 同一文件内 CHAIN_COLORS/chainName/chainLetter/chainText 也与 plan.py 同名常量/函数双份定义，靠人工同步。
  - Impact: 服务端未写 stop_reason 的数据形态下，看板展示的停因可能与 task.py plan 的输出不一致，形成双实现漂移——正是文件头声称要避免的情形。
  - Fix: 删除 chainStopInfo 兜底或将其降为纯展示（stop_reason 缺失时显示空），常量/命名函数改为由服务端 model 注入；至少修正 chain_plan.js 文件头与 plan.py docstring 的声明与现状一致。

- [Low][85] .repo_template/scripts/repo_task/integration.py:157-158 (cmd_start) — cmd_start 手工拆分 depends_on/conflicts_with，不 strip 空格也不校验 tid 格式
  - ID: f_template_scripts_state_05; verification: static
  - Evidence: cmd_start 用 [t for t in str(ref_fm.get('depends_on','')).split(',') if t.strip()] 解析依赖——元素本身不 strip，' t002'（逗号后空格）会原样进入依赖判定，随后 effective.get(' t002') 落空并被报告为『依赖未满足：t002(缺失)』类误导信息。; 全仓其余路径统一用 documents.parse_tid_list（strip + TID_RE.fullmatch 校验 + 去重排序），front matter 由 dump_tid_list 写出时无空格，但 AGENTS.md 允许人工维护 note.md，手写带空格的列表是现实输入。; 同函数对 conflicts_with 同样手工拆分，running_conflicts 判定会静默漏掉带空格的冲突项（放行本应警告的并行）。
  - Impact: 手改 front matter 后 start 可能误报依赖缺失，或漏报正在运行的冲突 task；错误信息指向不存在的『缺失』依赖，排障成本高。
  - Fix: cmd_start 改用 parse_tid_list 解析两字段（与 scheduling/lifecycle 一致），非法格式直接以字段名报错。

- [Low][85] .repo_template/scripts/repo_task/attempts.py:74-75 (project_attempts) — project_attempts 对 execution_claimed 事件直接下标取 owner_id，结构不合法的账本行会以 KeyError 崩溃而非 fail-closed
  - ID: f_template_scripts_state_06; verification: static
  - Evidence: ledger._read_unlocked 只校验每行是 JSON 对象，不校验事件字段结构；project_attempts 对 attempt_reserved 等事件用 event.get 宽容读取，唯独 execution_claimed 分支写 record['owner_id'] = event['owner_id'] 直接下标。; 账本的既定基调是 fail-closed：损坏 JSON 行直接 TaskDataError 拒绝继续（ledger.py:44-52），但一条 JSON 合法、缺 owner_id 的 execution_claimed 行（手改、旧版本或外部工具写入）会让 ps/recovery/integrate 等所有投影消费者抛裸 KeyError，绕过 cli.py 的 TaskDataError 统一出口变成 traceback。; 同文件 _require_identity_values 等校验只作用于命令入参，不作用于账本回放。
  - Impact: 账本出现单条结构异常事件时，全部依赖投影的只读命令（ps/recovery/goal-check）不可用且错误信息不指向账本行号，恢复成本高于设计预期。
  - Fix: project_attempts 对 execution_claimed 用 event.get('owner_id') 并在缺失时抛带 tid/attempt 上下文的 TaskDataError，或在 _read_unlocked 增加事件级结构校验。

- [Low][60] .repo_template/scripts/pending.py:141-153、findings.py:51-62、spikes.py:38-48 — 三个条目脚本的 new 子命令对 --slug 无本地校验，与 rename 的严格校验不一致
  - ID: f_template_scripts_state_07; verification: suspected
  - Evidence: pending.cmd_new / findings.cmd_new / spikes.cmd_new 直接把 args.slug 传给 _id_scan.allocate/allocate_dir，本单元文件内无任何 slug 格式校验。; 同文件的 rename 子命令却都先以 re.fullmatch(r'[a-z0-9]+(_[a-z0-9]+)*', slug) 严格校验（pending.py:290、findings.py:71），说明 slug 格式是既定契约，new 路径只是把校验完全外包。; _id_scan.py 不在本单元文件清单内，其 allocate 是否校验 slug 无法核对；若未校验，'../x'、'Foo Bar' 等 slug 可生成越界路径或不合规条目名，且 ENTRY_FILE_RE 后续 list 时会静默漏掉这些条目。
  - Impact: 取决于 _id_scan 的实现：最坏情况下 new 可创建目录外文件或永远列不出的条目；最好情况下只是校验权威分散、rename 与 new 口径不一致。
  - Fix: 在三个 cmd_new 入口复用 rename 的同一 slug 正则先行校验（或在 _id_scan.allocate 内校验并由本单元注明该契约），使两条路径口径一致。

- [Low][65] .repo_template/scripts/repo_state.py:93-101,120-121,166-172 — repo_state.py 把 baseline 作为裸位置参数传给 git，未防以短横线开头的选项注入
  - ID: f_template_scripts_state_08; verification: suspected
  - Evidence: _diff_name_only 执行 git diff --name-only -z <baseline>、cmd_added_lines 执行 git diff <baseline>、cmd_deliverable 执行 git diff --stat <baseline> -- <path>，均未在 baseline 前加 '--' 分隔（deliverable 仅对 path 加了 --）且未拒绝以 '-' 开头的值。; baseline 语义上应是 commit sha（调用方常取自 front matter diff_anchor 这类仓内数据），以 '-' 开头时会被 git 解析为选项（如 diff 的 --output=<file> 可写文件），git_ops.resolve_local_branch 对分支名有同类防护（拒绝 '-' 开头），repo_state.py 没有。; _baseline_ok 的 rev-parse --verify 校验只在部分路径先行：cmd_changed_files/cmd_added_lines 在 baseline 不可解析时是降级继续而非拒绝，注入参数仍会到达后续 git 调用。
  - Impact: 仓内数据（diff_anchor）被污染或调用方误传时，git 选项注入可改变命令行为，最坏以 --output 写任意文件；本地工具威胁模型下概率低，但与同仓其他模块的防护基线不一致。
  - Fix: repo_state.py 对 baseline 先做 rev-parse --verify 强制校验或拒绝 '-' 开头，并在 diff 调用中把 baseline 放在 '--' 之前按 rev 语义固定（git diff <rev> -- 路径）。

- [Low][80] .repo_template/scripts/repo_task/lifecycle.py:614-615,806-822 — cmd_finish 与 list --rebuild 未持控制面锁，与同类变更命令不一致
  - ID: f_template_scripts_state_09; verification: static
  - Evidence: lifecycle.py 中 cmd_add/cmd_edit/cmd_drop/cmd_rewind/cmd_purge 均有 @control_locked，唯独 cmd_finish（lifecycle.py:614）无装饰器，而它与 cmd_drop 共用 _close_task：写 front matter、移动 task 目录、（dropped 路径外）影响派生索引。; cmd_list 的 --rebuild 分支调用 rebuild_index 写两个派生 JSON，同样无锁；并发的 finish/rebuild 或两个 rebuild 交错时，索引内容取决于最后写入者，atomic_write 只防截断不防语义交错。; control.py 的 attempt 命令与 integration 的 start/cleanup/integrate 均持锁，说明控制面串行化是既定纪律，finish 是缺口而非有意例外（其 worktree 侧操作有 require_own_task_worktree 约束，但归档移动与索引重建发生在主仓共享面）。
  - Impact: 多会话并发（一个 finish、一个 rebuild/其他变更命令）时可能出现索引与目录状态短暂不一致，需要再跑一次 rebuild 修复；不会损坏状态权威（note.md/目录），故定级 Low。
  - Fix: 给 cmd_finish 与 cmd_list 的 rebuild 分支加 @control_locked（或在 _close_task 内部持锁），与 cmd_drop 对齐。

- [Low][80] .repo_template/scripts/repo_task/documents.py:55-75 (parse_front_matter_text) — front matter 结束分隔符用子串查找，会把以 --- 开头的任意行误判为结束
  - ID: f_template_scripts_state_10; verification: static
  - Evidence: parse_front_matter_text 用 text.find('\n---', 3) 定位结束分隔符，'\n----'、'\n--- foo' 等行都会命中前缀，front matter 值中若出现以 --- 开头的行（分隔线、YAML 文档标记风格内容）会提前截断，后续键被当作正文。; 解析循环还对重复键静默覆盖（fm[key] = ...），与 dump_front_matter 全键重写的往返组合下，手写 note.md 的重复键/伪分隔符不会得到任何报错，状态字段以截断后的值为准参与全部门禁。; store._task_record 对 tid/status 等关键字段有合法性校验，可挡住部分后果，但 title/note/depends_on 等字段的静默截断无校验覆盖。
  - Impact: 手写或外部工具生成的 note.md 在边界格式下被静默误解析，表现为依赖丢失、标题截断等难定位问题；工具自身 dump 的文件格式规整，触发条件主要是人工编辑。
  - Fix: 按行解析并要求结束行恰为 '---'（允许尾随空白），重复键时抛 TaskDataError，与 fail-closed 基调一致。

- [Low][90] .repo_template/scripts/pending.py:262-272 (cmd_park) 对比 237-259 (cmd_archive) — pending park 接受空 --reason，与 archive 的非空校验口径不一致
  - ID: f_template_scripts_state_11; verification: static
  - Evidence: cmd_archive 显式 strip 并拒绝空 reason（『归档必须提供非空 --reason』），且对 fix_ref/reason/resolution 逐项查换行。; cmd_park 只查 reason 是否含换行，空字符串（--reason '' 或全空白）直接通过，最终写入『- 暂搁：』空理由并把处理字段置为『不办』，条目进入 parked 后原因永久缺失。; parked 语义是『用户确认暂搁』，理由是后续 revive/审计的唯一依据，空理由与 archive 的闭环依据要求形成明显落差。
  - Impact: 暂搁条目可无理由落盘，日后无法判断暂搁依据；属数据质量问题，不影响状态机正确性。
  - Fix: cmd_park 复用 cmd_archive 的非空校验（strip 后为空即 IdScanError）。

- [Low][85] .repo_template/scripts/repo_task/view_static/board.js:renderDag 与 pointermove 处理（bindEvents） — board.js 在每次 pointermove/mouseenter 时整表重建 SVG，规模大时拖拽与悬停明显卡顿
  - ID: f_template_scripts_state_12; verification: static
  - Evidence: canvasEl 的 pointermove 处理每事件调用 renderDag()，renderDag 每次 computeLayout()（含 6 轮 barycenter 扫描）并把 canvasEl.innerHTML 清空后重建全部边/节点 DOM 与事件监听。; 节点 mouseenter/mouseleave 同样触发 renderDag + renderArchive + renderChainPanel 三个全量渲染。; 无节流/防抖，也未把平移限定为只更新 <g> 的 transform 属性（view 变换本可只改一个属性完成）。
  - Impact: task 数量达到数百量级时，拖拽平移与悬停高亮会掉帧；看板是只读展示工具，不影响数据正确性，故定级 Low。
  - Fix: 拖拽期间只更新 svg <g> 的 transform，pointerup 后再全量渲染；悬停渲染加 requestAnimationFrame 节流或仅切换受影响节点属性。

- [Low][85] .repo_template/scripts/repo_task/store.py:244-308 (scan_tasks_at_ref / _discover_effective_entries) — 有效状态发现对每个未合并分支/每个 worktree 做全量扫描，git 子进程数量随 task 数线性放大
  - ID: f_template_scripts_state_13; verification: static
  - Evidence: _discover_effective_entries 对每个未合并 task 分支调 scan_tasks_at_ref：一次 ls-tree 加每个 task 目录一次 git show；对每个登记 worktree 调 scan_tasks_in_worktree 读取全部 note.md。; compute_schedule 每次调用都走 discover_effective_tasks + scan_tasks 两遍全量扫描；view_server 每请求重算（仅 500ms 渲染缓存），cmd_ps/cmd_view/recovery/goal-check 等只读命令也都触发。; monitoring.compute_ps_rows 还对每个 terminal 记录调 verify_integrate_ready（多次 git 调用 + 临时目录写 review 文件），ps 类命令总开销叠加放大。
  - Impact: task 与分支数量增长后，只读命令与看板刷新延迟线性上升；功能正确性不受影响。
  - Fix: scan_tasks_at_ref 改为单次 git cat-file --batch 批量取 note.md；发现结果按 ledger/HEAD 指纹做进程内或文件级缓存（monitoring.repository_fingerprint 已有可复用机制）。

- [Low][85] .repo_template/scripts/track_worktree.py:16-19,139-152,186-196 — track_worktree 的 tid 提取与校验弱于其 docstring 声明
  - ID: f_template_scripts_state_14; verification: static
  - Evidence: 文件头 docstring 称 marker 模式『Validates the tid』，但 main 只校验 --tid 非空，无 TID_RE 格式校验（repo_task.context.TID_RE 存在且全仓通用，本脚本未用）。; hook 模式的 extract_tid 用正则 \bstart\s+(t\d+) 扫描任意 Bash 命令文本：任何含『start tNNN』字样的无关命令（如脚本参数、注释、echo 字符串）都会被当作 task start 触发 worktree 解析与状态栏记录写入。; --tid[= ](\S+) 取首个匹配的任意非空串，命令中出现的路径/参数可抢占真实 tid（fallback 顺序使然）。
  - Impact: 状态栏 worktree 标记可能误记/漏记，仅影响展示与 agent 提示，不触及 task 状态权威；但 docstring 与实现不一致会误导维护者高估其可靠性。
  - Fix: marker 与 hook 两路都用 ^t[0-9]+$ 校验 tid；hook 提取限定命令以 task.py/task 路径开头或含 track_worktree 调用时才采用位置参数形式，并修正 docstring 措辞。

- [Low][80] .repo_template/scripts/repo_task/cli.py:246-253 与 documents.py:97-124 — CLI 统一异常出口漏掉 ValueError，个别路径会裸 traceback
  - ID: f_template_scripts_state_15; verification: static
  - Evidence: cli.main 只捕获 ctx.TaskDataError 与 OSError 两类；documents.atomic_write_text 对软链目标抛 ValueError（『does not support writing to symlink』），write_front_matter/write_front_matter_many 是 edit/limits/图合并等命令的公共写路径，note.md 被软链（模板仓软链部署形态下并不罕见）时命令以 traceback 结束。; file_transaction.FileTransaction 的方法以 ValueError 表达事务状态错误，graph.cmd_merge_backlog/cmd_graph_transaction 已做转换，但这是逐调用点纪律而非入口兜底，后续新增调用点易遗漏。; 同仓其他入口（pending.py/findings.py）以 sys.exit(str(e)) 收口，对照之下 task.py 的出口覆盖面最窄。
  - Impact: 异常形态不一致：用户看到 Python traceback 而非可行动的错误信息；不影响数据安全（写入在抛错前未发生）。
  - Fix: cli.main 增加对 ValueError 的捕获并转统一错误输出，或把 atomic_write_text 的软链错误改为 TaskDataError 家族。

- [Info][90] .repo_template/scripts/repo_task/ledger.py:44-56 (_read_unlocked) — 账本损坏错误信息恒指默认账本路径，与实际读取的自定义路径不符
  - ID: f_template_scripts_state_16; verification: static
  - Evidence: _read_unlocked(path, ...) 接受调用方传入 path（ledger_read(path=...) 被 preflight 等以主仓账本路径调用），但损坏行/非对象行的报错文案写死 ctx._rel(ctx.LEDGER_PATH)，未用实际 path。; 在 worktree/测试等以非默认路径读账本时，报错会把维护者指向错误文件。
  - Impact: 仅排障指引错误，无功能影响。
  - Fix: 报错文案改用实际读取的 path 参数。

- [Medium][90] .repo_template/tests/test_repo_state.py:22-30 — repo_state.py 的测试从未在子目录 CWD 下运行，恰好绕开本单元 f_01 的缺陷面
  - ID: f_template_scripts_state_17; verification: static
  - Evidence: test_repo_state.py 的 _run() 恒以 cwd=repo（仓库根）启动脚本，全部 8 个测试无一从子目录调用；deliverable/changed-files/added-lines 的断言都建立在 CWD=仓库根的前提上。; 本单元 correctness 视角的 f_template_scripts_state_01 已静态确认：CWD 非仓库根时 ls-files（CWD 相对）与 diff --name-only（根相对）路径基准混杂、未跟踪文件可能被静默跳过——该行为在现有测试下不可见，修与不修测试结果相同。; 同文件已有对调用环境差异的回归意识（test_added_lines_exclude_robust_to_diff_prefix_config 覆盖用户 git config 改变 diff 前缀、test_non_ascii_paths_raw_and_exclude_consistent 覆盖非 ASCII 路径），说明调用环境维度本在该文件的测试设计范围内，子目录 CWD 只是未覆盖。
  - Impact: repo_state.py 是 task 收尾 deliverable 核对与清洁度计数的取数脚本；其唯一已知缺陷面（子目录调用）没有任何测试信号，既无法印证 f_01，也无法防止按 f_01 修复后同类路径基准问题无声回归。
  - Fix: 在 test_repo_state.py 增加从 repo 子目录（如 docs/）调用三个子命令的用例，断言输出与仓库根运行时一致（含 --exclude 命中与未跟踪文件全文计入 added-lines）。

- [Medium][95] .repo_template/scripts/repo_task/view_static/board.js:1-1135；.repo_template/tests/test_view_server.py:55 — board.js 1135 行前端逻辑零行为测试，仅有路径字符串存在性断言
  - ID: f_template_scripts_state_18; verification: static
  - Evidence: 全部测试中对 board.js 的唯一引用是 test_view_server.py:55 的 assert "/static/board.js" in html——只证明看板 HTML 引用了该路径，不加载、不解析、不执行 board.js 任何一行；board.css（701 行）同样无任何校验。; 同目录的 chain_plan.js（展示辅助子集）有专门的 node 用例集 test_chain_plan_cases.js 并由 test_chain_plan.py 驱动；board.js 的渲染、拖拽、SVG 连线与分类展示逻辑没有任何等价测试物。; 本单元 f_template_scripts_state_12（board.js 每次 pointermove 整表重建 SVG 的性能缺陷）正位于这片无测试区，其存废与修复均无测试信号。
  - Impact: board.js 是本单元行数最大的文件；它出现语法错误或逻辑回归时，模板契约套件与全部 Python 测试仍全绿，看板前端会静默损坏而无人察觉。
  - Fix: 仿 test_chain_plan_cases.js 为 board.js 的纯函数部分（分类映射、边/SVG 几何、文本拼装）建 node 用例集并由 pytest 驱动；至少加一条 node --check 语法冒烟纳入契约套件。

- [Low][85] .repo_template/scripts/repo_task/ledger.py:29-66；.repo_template/scripts/repo_task/attempts.py:34-96 — 账本内容损坏（非 JSON 行/结构非法事件）无任何测试，f_06 的 KeyError 路径正落在该空白区
  - ID: f_template_scripts_state_19; verification: static
  - Evidence: 现有账本失败测试覆盖的是「文件缺失/回滚」一侧：test_design_regressions.py 的 lost-ledger import 与 runtime_missing 相位、各处 ledger.unlink() 场景、test_review_report_regressions.py 把账本回滚为旧字节；没有任何测试向 dispatch_ledger.jsonl 写入非 JSON 行或结构非法的事件行。; grep 全测试目录：project_attempts 仅出现在 test_task_modularization.py 的门面缺席名单中，无直接行为测试；ledger_read 的直接测试（test_dispatch_integration.py:757）只喂格式完好的行验证 tid 预过滤与 attempt 分配。; 本单元 summary 把 ledger.py:29-66「损坏行 fail-closed」列为正面证据，但该行为无测试钉住；attempts.project_attempts 对 execution_claimed 行直接下标取 owner_id（f_template_scripts_state_06）在结构非法输入下抛 KeyError 而非 fail-closed，同样无测试暴露。
  - Impact: 账本是执行身份与恢复相位的事实来源；损坏行处理若回归（静默跳过、误投影、裸异常），recovery/cleanup 门禁可能在真实账本损坏时给出错误相位或崩溃，而测试层无任何信号。
  - Fix: 为 ledger_read 与 project_attempts/recovery 增加损坏输入用例：非 JSON 行、缺 event 字段行、execution_claimed 缺 owner_id 行各一，断言统一 fail-closed（TaskDataError 或明确的 needs_attention 相位）且不改写账本。

- [Low][90] .repo_template/scripts/repo_task/view_server.py（serve/_Handler）；.repo_template/tests/test_view_server.py；.repo_template/tests/pytest.ini:3 — view_server 无任何真实 HTTP 端到端测试，首页与静态资源路由连 handler 级测试也没有
  - ID: f_template_scripts_state_20; verification: static
  - Evidence: pytest.ini 对 contract 标记的声明即「不起真实 HTTP 服务」；test_view_server.py 中 serve() 的测试全部以 FakeServer 替换 ThreadingHTTPServer，_Handler 的测试以 FakeHandler/DummyHandler 手工驱动 do_GET/_send_bytes，socket 监听→请求解析→响应写回的完整链路从未跑通一次。; _route_get 的直接测试只有 /task-doc 一条路由（test_task_doc_endpoint_requires_valid_session_token）；首页 "/" 渲染路由与 /static/board.js、board.css 的静态文件路由没有任何 handler 级用例——_render_html 的纯函数测试不经过路由、Content-Type 与缓存头路径。; test_find_free_port_and_serve_ipv6_loopback 真实调用了 _find_free_port，但 serve 本体仍走 FakeServer，未验证真实绑定与并发请求下的渲染缓存去抖（test_rendered_html_cache_debounce 亦为 monkeypatch _build_model 的纯函数级验证）。
  - Impact: 路由表、静态目录解析或响应头在真实服务路径上的回归（如静态文件 404、MIME 错误）不会被任何测试发现；看板是 task 状态的只读权威视图，静默损坏会误导执行决策。
  - Fix: 在非 contract 层补一条真实回环 HTTP 冒烟：随机端口起 serve（或直接 ThreadingHTTPServer+_Handler），断言 GET / 返回 200 且含 window.__BOARD__、GET /static/board.js 返回 200 且字节与源文件一致、未知路径返回 404。

## views

```json
{
  "security": {
    "reviewer": "f229ba0b-01f9-4d5d-ad32-97b21fee6bae",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "f229ba0b-01f9-4d5d-ad32-97b21fee6bae",
    "status": "completed"
  },
  "contracts": {
    "reviewer": "f229ba0b-01f9-4d5d-ad32-97b21fee6bae",
    "status": "completed"
  },
  "performance": {
    "reviewer": "f229ba0b-01f9-4d5d-ad32-97b21fee6bae",
    "status": "completed"
  },
  "design": {
    "reviewer": "f229ba0b-01f9-4d5d-ad32-97b21fee6bae",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "f229ba0b-01f9-4d5d-ad32-97b21fee6bae",
    "status": "completed"
  },
  "tests": {
    "reviewer": "c9728a76-4372-4866-9499-a834848de156",
    "status": "completed",
    "reason": "原审阅者因本单元不含测试文件标 partial；由独立 viewfix 补审通读 template_tests 单元中实际测试本单元代码的测试文件后完成判定（依据见 summary.uncertainties 末条与 f_template_scripts_state_17..20）。"
  },
  "documentation": {
    "reviewer": "f229ba0b-01f9-4d5d-ad32-97b21fee6bae",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  ".repo_template/scripts/findings.py",
  ".repo_template/scripts/pending.py",
  ".repo_template/scripts/repo_state.py",
  ".repo_template/scripts/repo_task/__init__.py",
  ".repo_template/scripts/repo_task/attempts.py",
  ".repo_template/scripts/repo_task/cli.py",
  ".repo_template/scripts/repo_task/context.py",
  ".repo_template/scripts/repo_task/control.py",
  ".repo_template/scripts/repo_task/documents.py",
  ".repo_template/scripts/repo_task/file_transaction.py",
  ".repo_template/scripts/repo_task/finalization.py",
  ".repo_template/scripts/repo_task/git_ops.py",
  ".repo_template/scripts/repo_task/goal.py",
  ".repo_template/scripts/repo_task/graph.py",
  ".repo_template/scripts/repo_task/integration.py",
  ".repo_template/scripts/repo_task/ledger.py",
  ".repo_template/scripts/repo_task/lifecycle.py",
  ".repo_template/scripts/repo_task/locks.py",
  ".repo_template/scripts/repo_task/monitoring.py",
  ".repo_template/scripts/repo_task/plan.py",
  ".repo_template/scripts/repo_task/recovery.py",
  ".repo_template/scripts/repo_task/review.py",
  ".repo_template/scripts/repo_task/scheduling.py",
  ".repo_template/scripts/repo_task/store.py",
  ".repo_template/scripts/repo_task/validation.py",
  ".repo_template/scripts/repo_task/view_server.py",
  ".repo_template/scripts/repo_task/view_static/board.css",
  ".repo_template/scripts/repo_task/view_static/board.html",
  ".repo_template/scripts/repo_task/view_static/board.js",
  ".repo_template/scripts/repo_task/view_static/chain_plan.js",
  ".repo_template/scripts/repo_task/worktrees.py",
  ".repo_template/scripts/spikes.py",
  ".repo_template/scripts/task.py",
  ".repo_template/scripts/track_worktree.py"
]
```
