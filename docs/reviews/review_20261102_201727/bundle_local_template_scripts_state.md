# bundle_local_template_scripts_state

## responsibilities

- task.py + repo_task/ 是 task 状态机唯一实现：note.md front matter 为状态权威（与 CBrowser AGENTS.md 写权表一致），提供 add/edit/start/preflight/finish/drop/rewind/purge、attempt 精确身份生命周期（reserve/claim/terminal/report）、调度图（depends_on 硬边、conflicts_with 无向提示）、plan/view 看板、integrate/integrate-chain 原生 Git 合并门禁、goal 队列冻结与终态判定、recovery 只读诊断。
- 派生索引 docs/tasks_index.json 与 docs/archive/tasks_index.json 由 store.rebuild_index 从 note.md 扫描重建（原子写），与 AGENTS.md『派生 index 在集成时进入同一 merge commit』约定一致。
- pending.py / findings.py / spikes.py 管理 pNNN/dNNN/sNNN 一条目一文件总账：编号分配委托 _id_scan（跨单元）在 git 公共目录锁内完成，状态由所在目录表达，迁移用 git mv + 失败回滚。
- repo_state.py 提供完整工作树 vs baseline 的只读取数（deliverable / changed-files / added-lines），供收尾清洁度与交付核对；track_worktree.py 是状态行 hook 的 worktree 标记/写入器。
- file_transaction.py 为图合并与模板同步提供 before-image 持久事务（快照→应用→accept/rollback）；locks.py 提供跨平台同线程可重入文件锁与 git 公共目录控制面锁。

## interfaces

- CLI: task.py 子命令面（cli.py 路由）；pending.py/findings.py/spikes.py 子命令（new/list/archive/park/revive/rename）；repo_state.py 三子命令；track_worktree.py --tid/--write hook 协议（stdin JSON payload）。
- 文件契约：note.md front matter 固定键集（context.FRONT_MATTER_KEYS）；dispatch_ledger.jsonl 事件（attempt_reserved/execution_claimed/attempt_terminal/report/integrated/start）；handoff.json 必填字段类型表（monitoring._HANDOFF_TYPES）；goal_queue.json 快照结构；tasks_index.json 派生结构（generated_by/authority/tasks）。
- HTTP: view_server 只读看板（/、/static/{board.css,board.js,chain_plan.js}、/task-doc?tid&doc&token），默认 loopback 绑定，非 loopback 须 --allow-non-loopback。

## dependencies

- 跨单元：_id_scan.py（template_scripts_ops 单元）被 findings/pending/spikes 导入做锁内取号，且 _id_scan 反向导入 repo_task.locks；md_format.py 被三者导入做新文件格式化。
- 仓内权威输入：docs/blueprint/testing.md（validation.load_policy 解析门禁命令并以 bash 执行——属项目已配置策略的既定信任边界）、.repo_template/docs/task_template（add 复制与规范块校验）、docs/specs_index.md（finalization 收尾校验）。
- 运行时依赖：Git >= 2.38（merge-tree --write-tree 内容门禁，执行前有能力预检）、Python stdlib 为主、无第三方包；view_static 为零依赖 vanilla JS/CSS。

## flows

- start：主仓控制锁内校验策略/账本可读→解析 base（默认主干或链式前置分支 tip，含实现 SHA 祖先校验）→建 worktree→worktree 副本 note.md 写 active/branch/diff_anchor→软链主仓 .env；失败走 rollback_start 按归属补偿。
- attempt 生命周期：ledger 锁内分配 attempt 号并 append attempt_reserved→claim CAS 换 owner→terminal→report（done 须先过 verify_integrate_ready 的 handoff/AC/review 指纹门禁）→cleanup-worktree→integrate（merge --no-ff --no-commit→重建并暂存派生 index→--continue 时重算自动合并 tree 校验 staged 范围→merge commit→append integrated→删分支）。
- finish/drop：_close_task 单次写 front matter 终态后移动目录到 archive，移动失败回滚 front matter；main 上 drop 同步重建派生索引，worktree 内 finish/drop 的索引由后续 commit/integrate 收尾。
- merge-backlog：FileTransaction 快照受影响目录/文件→write_front_matter_many 两阶段批量改图→_close_task 归档来源→rebuild_index→applied+accept；异常自动 rollback。

## constraints

- 状态读取优先级（AGENTS.md 与 usage.md）：登记 worktree → 未合并 task 分支 ref → 主干；discover_effective_* 按此实现，且对 worktree note.md 损坏降级为脏状态记录而非整体失败。
- 权威/派生文件写入走 atomic_write_text（同目录唯一 tmp + fsync + os.replace，拒绝软链目标）；ledger 为 append-only JSONL，单写者锁内读改写。
- 控制面变更经 git 公共目录 CONTROL 锁串行化；验证子进程（validation_environment 标记）禁止再抢 CONTROL 锁，防父子死锁。
- 审计日志 docs/archive/tasks_audit.log 仅 rewind/purge append（与 usage.md 写权表一致，代码中 append_audit 调用点仅这两处及 rewind 失败标记）。
- task 状态仅 backlog/active/done/dropped；rewind 只在 STATUS_ORDER 内后退；review_level 只允许 single→full 单调升级。

## decisions

- exact identity (tid, attempt, execution_id) 为执行权威，owner_id 只是会话执行权且无自动过期，接管须 --replace-owner + --confirm-stopped（architecture.md Attempt 节一致）。
- ledger 损坏行 fail-closed 拒绝继续（防 attempt 号复用）；与之相对，拓扑/集成事件走 _ledger_append_safely best-effort + WARNING，不阻断主流程——该不对称是显式取舍（见 finding 01 的反面：读路径 OSError 吞噬破坏了 fail-closed 一侧）。
- review scope 指纹绑定交付内容（mode/软链/新文件，排除 review 过程文件），不随暂存/提交/归档迁移变化；指纹算不出时返回空串 fail-closed 为 missing。
- merge 内容门禁不信任人工解决结果：--continue 时用 merge-tree 重算自动合并 tree，仅原始冲突路径与派生 index 允许偏离。
- 看板 token 为进程级随机值且嵌入注入页面的 model JSON（见 finding 02：该设计使 token 校验不构成访问控制，真实边界只有绑定地址）。

## evidence

- .repo_template/scripts/repo_task/documents.py:118-143 atomic_write_text 实现（tmp+fsync+replace+软链拒绝）
- .repo_template/scripts/repo_task/ledger.py:22-49 _read_unlocked 对损坏行 fail-closed 抛 TaskDataError、但 except OSError 返回 []（finding 01）
- .repo_template/scripts/repo_task/store.py:273-344 _discover_effective_entries 按 worktree→branch→main 优先级发现有效状态
- .repo_template/scripts/repo_task/integration.py:545-590 _validate_merge_staged_scope 以 merge-tree 自动结果校验 staged 内容
- .repo_template/scripts/repo_task/view_server.py:110-135 _resolve_task_doc_in 解析后校验路径位于允许根内（路径穿越防护到位）
- .repo_template/scripts/repo_task/view_static/board.js 全文：标题/文档内容均经 createTextNode/textContent 渲染，无 innerHTML 注入面
- .repo_template/docs/usage.md:54 与 .repo_template/docs/architecture.md 调度/attempt/合并契约，与实现逐项对照未见静默改写
- .repo_template/scripts/repo_task/locks.py:1-139 (coordinator coverage patch: file read in full after unit reviewer omitted it from files_reviewed)

## uncertainties

- 本单元不含测试文件：file_transaction/ledger/locks 等核心不变量的实际测试覆盖在 template_tests 单元，本次未核对；finding 01/03 涉及的错误路径是否有回归测试待该单元结论。
- documents.py docstring 称 render_review_prompts.py / check_review_status.py 委托本模块 parse_front_matter——两文件属 template_scripts_ops 单元，本次未跨单元验证该单一真相源声明。
- Windows msvcrt 锁分支与 Git Bash/WSL 软链行为仅静态阅读，未实测（静态审阅约束）；usage.md 亦标注原生 Windows 全流程未认证。
- repository_fingerprint 的消费者 check_review_status.py 在其他单元，其指纹降级（finding 17）的实际影响面未在本单元内确认。

## Findings

- [High][85] .repo_template/scripts/repo_task/ledger.py:22-49 — ledger 读取遇 OSError 静默返回空事件列表，破坏 attempt 号 fail-closed 不变量
  - ID: f_template_scripts_state_01; verification: static
  - Evidence: _read_unlocked 对 JSON 损坏行明确 fail-closed 抛 TaskDataError（注释：跳过会让 attempt 号复用），但同一 try 块的 except OSError 直接 return []，文件存在但不可读（权限/瞬时 I/O 错误）时与『账本不存在』不可区分; ledger_allocate_attempt 在锁内以 _read_unlocked 结果算 ledger_next_attempt=max+1；读到空列表会从 1 重新分配，与仍在运行的旧 attempt 撞号; cmd_start 前置的 ledger_read() 可读性校验（integration.py 注释称防留下副作用）在 OSError 时同样被吞成空列表而通过
  - Impact: 账本短暂不可读即可让 reserve 分配出重复 attempt 号、current identity 误判，后续 claim/terminal/report 基于错误投影继续，exact identity 权威被静默腐蚀且无任何报错。
  - Fix: 区分『文件不存在』（返回 []）与『存在但读取失败』（抛 TaskDataError）：先 is_file() 判定，再让 open/迭代中的 OSError 向上抛；_ledger_append_safely 的 best-effort 语义只保留在写路径。

- [Medium][90] .repo_template/scripts/repo_task/view_server.py:49-56 — 看板会话 token 嵌入未鉴权的首页 HTML，/task-doc 的 token 校验不构成访问控制
  - ID: f_template_scripts_state_02; verification: static
  - Evidence: _build_model 把 _SESSION_TOKEN 写入 model，_render_html 将其 JSON 注入 board.html 经 / 与 /index.html 无条件返回（_route_get 对首页无任何校验）; /task-doc 在 view_server.py:335-342 校验 query token，但攻击者先 GET / 即可从页面 JSON 取得同一 token; serve() 允许 --allow-non-loopback 绑定并仅打印 WARNING；此时 task.md/note.md 正文对同网段任何人实际无鉴权可读
  - Impact: 使用者容易误以为 token 提供了鉴权；非 loopback 暴露时 task spec/过程正文（含设计与处置细节）可被未授权读取。loopback 默认下风险限于本机其他进程。
  - Fix: 二选一并写清语义：要么首页也要求 token（token 只经启动日志/URL 交给用户，页面内不再下发裸 token，改为同源会话 cookie），要么删除 token 校验与相关文案、明确声明唯一边界是绑定地址。

- [Medium][85] .repo_template/scripts/track_worktree.py:62-105 — resolve_worktree 逆序扫描遇到 execution_claimed 等事件直接返回空，claim 后整个执行期跟踪失效
  - ID: f_template_scripts_state_03; verification: static
  - Evidence: 逆序扫描首个命中事件的处理：TERMINAL_EVENTS 返回 ''、start 取 worktree、attempt_reserved(state=running) 继续向前找 start，其余事件一律走 else 返回 ''; 工具链在 reserve 后会写 execution_claimed（attempts.claim_execution），且 claim 后到 terminal 前不再有新事件——这段时间账本最新事件恒为 execution_claimed，resolve_worktree 恒返回 ''; usage.md 声明该 hook 用于多会话场景跟踪各会话 worktree，而 claim 正是多会话必经步骤
  - Impact: 状态行在 task 被 claim 后的整个实施期丢失 worktree 映射（hook 写入与 marker 模式都受影响），多会话场景下状态行指向错误/缺失，与工具声明用途不符。
  - Fix: 逆序扫描时 execution_claimed（及 start/topology 类非终态事件）应像 attempt_reserved 一样继续向前找 start，仅 TERMINAL_EVENTS 与 integrated 关闭窗口；补对 claim 后事件序列的回归用例。

- [Medium][75] .repo_template/scripts/repo_task/store.py:273-344 — discover_effective_* 对每个未合并分支全量扫描其全部 task，git 子进程数随分支×task 数乘积增长
  - ID: f_template_scripts_state_04; verification: static
  - Evidence: _discover_effective_entries 对每条未合并 task 分支调用 scan_tasks_at_ref，后者先 ls-tree 再对每个 task 目录逐个 git show note.md（store.py:117-160），且每条分支先经 has_unmerged_commits 的多次 git 调用判定; 该发现函数被 view/plan/ps/preflight/start/effective-status 等几乎所有只读命令共用，看板 /task-doc 每次请求亦重新 compute_schedule + discover_effective_sources（view_server.py:346-348），无缓存; plan.classify_node（plan.py:92-109）对每个节点重建 waiting/blocked 列表，叠加一层 O(n²)
  - Impact: 仓内 task 与残留分支增多后，plan/view/ps 等高频只读命令延迟线性恶化到秒级以上，看板文档请求可对本机造成明显的 git 进程风暴；容易被误判为工具链卡死。
  - Fix: scan_tasks_at_ref 只读所有者 tid 的 note.md（其余 task 在分支内与 main 副本的差异仅影响该分支所有者）；或对同一 ref 的 ls-tree/show 结果做进程内缓存；看板侧对 schedule 计算加与渲染缓存同级 TTL。

- [Medium][80] .repo_template/scripts/repo_task/documents.py:60-80 — front matter 解析静默丢弃无冒号行与重复键，格式错误可无声抹掉 depends_on 等权威字段
  - ID: f_template_scripts_state_05; verification: static
  - Evidence: parse_front_matter_text 对不含 ':' 的行直接 continue，对重复 key 后者静默覆盖，均不报错也不警告; 手误把 `depends_on: t002` 写成 `depends_on t002` 时，该硬依赖边静默消失；scan/scheduling/start 都会把该 task 当作无依赖，可能绕过 architecture.md 的硬前置门禁; 结束围栏用 text.find("\n---", 3) 定位，`--- `（尾随空格）或 `----` 会使正文切分错位（正文混入残余字符），而非明确报格式错误
  - Impact: 状态权威文件 note.md 的解析对格式漂移零反馈，与同仓其他解析器（ledger 损坏行、处置表结构错误）的 fail-closed 风格不一致；依赖边静默丢失是最危险的失效模式。
  - Fix: front matter 区内出现非空、非注释且无冒号的行或重复 key 时抛 TaskDataError 并指出行号；结束围栏按行精确匹配 `---`（允许尾随空白）后再切分正文。

- [Low][85] .repo_template/scripts/pending.py:226-245 — pending 批量迁移回滚吞掉单条失败且无条件宣称全部回滚成功，正文恢复为非原子直写
  - ID: f_template_scripts_state_06; verification: static
  - Evidence: 回滚循环内层 except Exception: pass 吞掉 git mv/rename/write 的全部失败，随后 stderr 仍打印『已回滚 {len(migrated)} 条已迁移条目（含正文）』; 正文恢复用 src.write_bytes(orig_bytes) 直写，与 set_field 的 atomic_write_text 路径不一致，中途崩溃可留下截断条目; actions 的 find_entry 在 _apply 取 id_lock 之前完成，--write 落盘时条目可能已被其他进程迁移，move 失败后进入上述不可靠回滚
  - Impact: 迁移失败时用户被告知已完整回滚，实际可能处于部分迁移+正文未恢复状态，后续按错误前提继续操作总账。
  - Fix: 回滚逐条记录成败，任一失败时明确报告未恢复条目与现场路径；正文恢复改走 atomic_write_text；find_entry 结果在锁内复核后再执行迁移。

- [Low][90] .repo_template/scripts/repo_task/documents.py:118-143 — atomic_write_text 只 fsync 文件不 fsync 父目录，掉电时 rename 本身不保证持久
  - ID: f_template_scripts_state_07; verification: static
  - Evidence: 实现为同目录 tmp 写入 + os.fsync(文件) + os.replace，全程未对 path.parent 目录做 fsync; docstring 宣称『防掉电/中断产生半写状态』——内容半写确已防住，但目录项持久性在 ext4 等文件系统上不经目录 fsync 不保证，崩溃后可出现文件回退到旧版本或消失; 该 helper 是 note.md、派生 index、goal 快照、FileTransaction journal 的共同写路径
  - Impact: 极端掉电场景下状态权威文件可能丢失最后一次已报告成功的写入，与工具链的崩溃一致性定位有落差（普通进程崩溃不受影响）。
  - Fix: os.replace 后打开父目录 fd 并 fsync（POSIX）；Windows 下跳过或降级，并在 docstring 中区分『防半写』与『防掉电丢失』两个保证级别。

- [Low][95] .repo_template/scripts/repo_task/lifecycle.py:830-850 — task.py show 输出的 task_md 字段实际指向 note.md 路径
  - ID: f_template_scripts_state_08; verification: static
  - Evidence: cmd_show 非 ref 分支：fields["note_md"] 与 fields["task_md"] 都赋值为 ctx._rel(path)，而 path 是 load_task 返回的 note.md 路径; ref 分支同样把 task_md 拼为 {ref}:{dir}/note.md; task.md 是同目录另一文件，show 的消费者（含 skill 脚本化读取）会据此读错文件
  - Impact: show 输出的 task_md 定位错误，按图索骥的 agent/脚本会把 note.md 当 spec 读取，掩盖 task.md 缺失等问题。
  - Fix: task_md 改为同目录 task.md 的相对路径（ref 分支为 {ref}:{dir}/task.md），并在文件不存在时显式标注缺失而非回退 note.md。

- [Low][80] .repo_template/scripts/repo_task/view_static/board.js:481-494 — 看板每次 hover/拖动都全量重建 SVG 与三个面板，节点多时交互明显卡顿
  - ID: f_template_scripts_state_09; verification: static
  - Evidence: 节点 mouseenter/mouseleave 处理器每次调用 renderDag() + renderArchive() + renderChainPanel()，renderDag 内部重跑 layoutDag 并重建全部 SVG 节点与事件监听; pointermove 拖动期间同样逐事件 renderDag() 全量重绘（board.js:1065-1075）; layoutDag 含 6 轮 barycenter 扫描且 reindex 用 l.indexOf（O(n²) 量级），与全量重绘叠加
  - Impact: task 数达到数百量级时，悬停高亮与拖动画布从即时反馈退化为逐帧卡顿；属可用性问题，不影响数据正确性。
  - Fix: hover 只更新受影响节点/边的属性（role 变化集合）而非整树重建；拖动时仅更新 <g> 的 transform 属性，松手后才做完整渲染；布局层 indexOf 改为 Map 位置索引。

- [Low][85] .repo_template/scripts/repo_state.py:164-173 — added-lines 对不可读的未跟踪文件静默跳过，清洁度取数可无声缺内容
  - ID: f_template_scripts_state_10; verification: static
  - Evidence: cmd_added_lines 读取未跟踪文件全文时 except OSError: continue，无 stderr 提示; 本脚本 docstring 定位是收尾清洁度/deliverable 核对的取数层，added-lines 喂给 grep 计数；文件被跳过意味着其内容从未被检查却不留痕迹; 对照同文件 deliverable/changed-files 的降级路径都有 _warn_degraded 声明，此处静默不一致
  - Impact: 权限异常或竞态消失的 deliverable 文件会从清洁度扫描中无声消失，可能让含违规内容的文件绕过收尾 grep 门禁。
  - Fix: 跳过时向 stderr 打印 WARNING 并计入退出状态或单独的 skipped 清单，与既有降级声明风格一致。

- [Low][70] .repo_template/scripts/repo_task/validation.py:14-33 — validation.sections 的围栏判定只比首字符不比长度，嵌套围栏会误切 testing.md 章节
  - ID: f_template_scripts_state_11; verification: static
  - Evidence: sections() 以 marker[1][0] 记录/清除 fence 状态：开栏为 ```` 的代码块内出现 ``` 行即被当作闭栏，其后内容被按标题重新切分; 同仓 documents.py 的围栏语义为『字符+长度且闭栏须不短于开栏』，两套解析对同一 Markdown 给出不同结果; testing.md 是验证策略唯一权威，doctor/test/blackbox 命令块若含嵌套围栏示例，load_policy 可能提取错位或误报缺章节
  - Impact: 特定格式的 testing.md 会让 start/preflight 的策略解析与文档校验结论分叉，报错指向与真实问题不符，排查成本高。
  - Fix: 复用 documents.py 的围栏状态机（字符+长度）实现 sections()，消除第二套语义。

- [Low][75] .repo_template/scripts/repo_task/graph.py:76-90 — merge-backlog 事务的 accept 校验形同虚设，FileTransaction 状态机对 preparing 亦无恢复出口
  - ID: f_template_scripts_state_12; verification: static
  - Evidence: graph.py 在 transaction.applied() 后立即 accept()；applied() 刚用当前树计算 after 指纹，accept() 随即以同一指纹比对，未经任何外部验证即通过（file_transaction.py:89-97 与 124-136）; FileTransaction.rollback 仅接受 applying/applied/restore_failed/rolled_back；begin 中断留下的 preparing journal 经 graph-transaction status 可见，但 rollback 报『没有可恢复文件事务』，与 usage.md『中断用 graph-transaction 查询/恢复』的指引不完全对应（preparing 期未开始变更，实际无害但语义含糊）
  - Impact: accept 的『apply 后资产发生变化则拒绝』门禁在该调用点永不触发，读者会高估图合并的事务校验强度；preparing 残留时恢复指引与实际报错不一致。
  - Fix: graph 合并在 applied 与 accept 之间加入实际校验（如重跑 compute_schedule 一致性检查）并以 verified 语义调用；或在文档/状态输出中标明 preparing 表示『尚未开始变更，可直接重跑 begin』。

- [Low][55] .repo_template/scripts/repo_state.py:83-88 — repo_state 的 baseline 参数未经 -- 隔离直接进入 git diff 参数位，存在选项注入面
  - ID: f_template_scripts_state_13; verification: suspected
  - Evidence: _diff_name_only 与 cmd_added_lines 把用户传入的 baseline 直接作为 git diff 的第一个位置参数，未用 --end-of-options 或 -- 分隔（repo_state.py:139-147）; 当前可达性受 _baseline_ok 的 rev-parse --verify 前置校验限制，以 '-' 开头的字符串通常过不了校验，故实际利用条件苛刻；git_ops 中同类 revspec 拼接（如 rev-list {base}..{branch}）靠分支名正则约束，约束来源不统一
  - Impact: 若未来校验放宽或出现能同时通过 rev-parse 校验又被 diff 解释为选项的输入，baseline 可改变 diff 行为（如 --output 写文件）；当前主要为纵深防御缺口。
  - Fix: 所有接受外部 revspec 的 git 调用统一加 --end-of-options（Git>=2.24 支持）或先以 rev-parse 规范化为完整 SHA 再使用。

- [Low][80] .repo_template/scripts/repo_task/cli.py:270-276 — CLI 统一异常入口只捕获 TaskDataError/OSError，atomic_write_text 的 ValueError 会裸 traceback
  - ID: f_template_scripts_state_14; verification: static
  - Evidence: cli.main 的 except 只覆盖 ctx.TaskDataError 与 OSError；documents.atomic_write_text 对软链目标抛 ValueError（documents.py:124-127），不在捕获之列; note.md 被意外替换为软链（或 FileTransaction journal 路径被软链占用）时，edit/start/graph 等命令以 Python traceback 退出，而非工具链统一的中文错误出口; 同为 ValueError 子类的 ReviewDataError/ValidationError 在各调用点被单独捕获，说明该缺口只是 atomic_write 路径遗漏
  - Impact: 异常现场的用户可见信息不一致，脚本化调用方按退出输出分类错误时会被 traceback 干扰；状态本身因写前拒绝未受损。
  - Fix: 在 cli.main 增加对 ValueError 的统一捕获并标注命令名，或让 atomic_write_text 的软链拒绝抛 TaskDataError 子类。

- [Low][70] .repo_template/scripts/repo_task/lifecycle.py:690-740 — rewind 审计失败后的提示称『直接重试将正常完成』，但重试实际以『已是 backlog』失败退出
  - ID: f_template_scripts_state_15; verification: static
  - Evidence: cmd_rewind 顺序为：discard worktree/删分支 → append_audit（失败即 sys.exit 并提示重试可正常完成）→ write_front_matter；审计失败发生在状态写入之前，但 worktree 副作用已完成; 重试时 load_task 读到的主仓 front matter 仍是 backlog（start 从不回写主仓），worktree 已不存在，effective=backlog 使 target 为 None，退出信息为『已是 backlog，无可撤回』，与上次提示矛盾; 该次 rewind 的 note 记录与审计行也因此双双缺失，无从追溯已发生的 worktree 丢弃
  - Impact: 用户按提示重试得到看似失败的结果，且一次已执行的 rewind 在审计与 note 中无记录，状态恢复叙事不完整。
  - Fix: 审计失败的退出信息改为与可达状态一致（如『worktree 已清理、状态未写；请直接核对 backlog 状态，勿重复 rewind』），或让重试路径识别『worktree 已清且 main 为 backlog』为幂等成功并补写审计。

- [Info][90] .repo_template/scripts/repo_task/view_server.py:1-7 — 模块 docstring 称『每次请求重新计算 schedule』，与 500ms 渲染缓存实现不符
  - ID: f_template_scripts_state_16; verification: static
  - Evidence: docstring 第 4-6 行声明每次请求重新计算、无后台轮询；_get_rendered_html 实际以 _RENDER_CACHE_TTL=0.5s 缓存整页（view_server.py:66-85，注释自述为平抑并发）; /task-doc 路径则确实每次重算，两条路径新鲜度语义不同但文档未区分
  - Impact: 维护者按 docstring 预期排查『看板数据不刷新』时会先入为主排除缓存因素。
  - Fix: docstring 补一句首页渲染有 500ms TTL 缓存、/task-doc 每次重算。

- [Info][95] .repo_template/scripts/repo_task/monitoring.py:211-231 — repository_fingerprint 对 >1MB 未跟踪文件只哈希 (size, mtime_ns, 前 8KB)，同尺寸同 mtime 的中段改动不可见
  - ID: f_template_scripts_state_17; verification: static
  - Evidence: repository_fingerprint 的 large 分支以 size+mtime_ns+8KB 前缀代替全量内容，docstring 已明确声明该精度降级（monitoring.py:190-198）; 该指纹供静默变化检测类消费者使用（本单元外），若大文件被等长原地改写且 mtime 被保留/回拨，变化检测会漏报
  - Impact: 属已声明的性能取舍而非隐藏缺陷；记录在此供全局汇总评估消费者是否接受该漏检面。
  - Fix: 无需改代码；若消费者用于安全相关判定，应改用全量哈希或纳入 inode change time 并在消费者文档标注。

- [Info][90] .repo_template/scripts/repo_task/git_ops.py:108-148 — porcelain_entries 与 tracked_dirty_entries 近乎逐行重复，仅差一个 --untracked-files=no 参数
  - ID: f_template_scripts_state_18; verification: static
  - Evidence: 两函数共享同一套 -z 解析循环（重命名跳下一字段等细节各写一份），任一解析修复需改两处，易漂移; 同类小重复：_ledger_tid_sort_key 与 documents.tid_sort_key_or_zero 语义相近但实现不同源（monitoring.py:22-24）
  - Impact: 维护性风险：porcelain 解析若需适配新 git 输出格式，双份实现可能只改一处，造成 merge 前脏检查与 rewind 脏检查口径不一致。
  - Fix: 抽出单一 _porcelain_paths(root, untracked: bool) 供两函数共用。

- [Info][85] .repo_template/scripts/repo_task/view_static/board.js:151-175 — board.js 注释引用不存在的 TS 源文件（dagLayout.ts / boardUtils），为已消失实现的历史残留
  - ID: f_template_scripts_state_19; verification: static
  - Evidence: 注释多处称『dagLayout.ts 的翻译』『boardUtils.collectRelated / highlightRoleOf 的翻译』，仓内无对应 TS 文件，读者无法回查所指原文; chain_plan.js 头注释已正确声明算法权威在后端 plan.py，形成对照：board.js 的来源注释未随单实现收敛更新
  - Impact: 文档可追溯性受损，维护者可能误以为仓外还有一份 TS 实现需要同步。
  - Fix: 将来源注释改为指向当前权威（repo_task/plan.py 与本文件内函数），或删除失效的翻译出处说明。

- [Info][70] .repo_template/scripts/repo_task/locks.py:22-24 — Per-path RLock registry grows without eviction for the process lifetime
  - ID: f_template_scripts_state_20; verification: static
  - Evidence: _thread_locks.setdefault(str(lock_path), threading.RLock()) at locks.py:84-85 inserts one entry per distinct lock path and no code path ever removes entries; In this codebase the distinct paths are few (id/control/ledger locks per repo), so growth is bounded in practice; noted for long-lived processes such as view_server that touch many repos
  - Impact: Negligible memory growth in current usage patterns; only matters if a long-lived process locks unbounded distinct paths.
  - Fix: No action needed at current scale; if path diversity grows, evict registry entries when no thread holds or waits on the path.

## views

```json
{
  "contracts": {
    "reviewer": "82e5a8a3-5ebb-4bd0-b71d-58fa5596f976",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "82e5a8a3-5ebb-4bd0-b71d-58fa5596f976",
    "status": "completed"
  },
  "design": {
    "reviewer": "82e5a8a3-5ebb-4bd0-b71d-58fa5596f976",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "82e5a8a3-5ebb-4bd0-b71d-58fa5596f976",
    "status": "completed"
  },
  "performance": {
    "reviewer": "82e5a8a3-5ebb-4bd0-b71d-58fa5596f976",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "82e5a8a3-5ebb-4bd0-b71d-58fa5596f976",
    "status": "completed"
  },
  "security": {
    "reviewer": "82e5a8a3-5ebb-4bd0-b71d-58fa5596f976",
    "status": "completed"
  },
  "tests": {
    "reviewer": "82e5a8a3-5ebb-4bd0-b71d-58fa5596f976",
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
  ".repo_template/scripts/track_worktree.py",
  ".repo_template/scripts/repo_task/locks.py"
]
```
