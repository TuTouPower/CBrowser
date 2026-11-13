# Task review t062（reviewer_focus: 测试）

- task：`t062_control_plane_boundaries`
- spec：`docs/tasks/t062_control_plane_boundaries/task.md`
- diff_anchor：`c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- target：`git -C '/home/hatch/workspace/CBrowser_t062' diff c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- round：1
- reviewed_at：2026-11-13T22:58:53+08:00

reviewed_scope: ec0027fced40d5c9

## Findings

### t062_test_f001 - 四条 AC 全部未打勾，与 progress 收尾报告「全部满足」自相矛盾

- 严重度：important
- 锚点：AC-005、AC-006、AC-007、AC-008；spec 规范「实施验证通过后由实施 Agent 就地打勾」
- 位置：`docs/tasks/t062_control_plane_boundaries/task.md:30-33`（四条均为 `- [ ]`）；`docs/tasks/t062_control_plane_boundaries/progress.md` 收尾报告「结果：全部满足」「AC 判定：见 task.md 行内打勾」
- 问题：实施侧声称全部满足并把 AC 判定指向 task.md 行内打勾，但 task.md 中没有任何一条 AC 被打勾。按 AC 复验规则，未打勾的 AC 一律 TICK-VOID，本轮四条 AC 全部作废，verdict 必为 FAIL，与测试本身是否通过无关。
- 建议：实施方在复验后就地打勾四条 AC（AC-005 的 [deploy] 部分按 p092 顺延口径处理并在打勾时注明），或修正 progress 收尾报告的结论口径；二者不得继续互相矛盾。

### t062_test_f002 - AC-008 端口单一权威守护存在盲区：runner 默认端口与 compose healthcheck 均未被断言

- 严重度：important
- 锚点：AC-008「Supervisor CLI、runner、compose 对默认控制端口使用同一权威值」「覆盖非默认配置时行为一致」；上下文区测试策略「固定端口和非默认端口贯穿 CLI/runner/compose 验证」
- 位置：`tests/unit/test_t062_boundaries.py:172-195`（`test_supervisor_port_single_authority`）；对照 `src/backend/cbrowser/supervisor/runner.py:63` 与 `src/backend/cbrowser/supervisor/runner.py:612`、`compose.yaml:153`
- 问题：该守护只断言 shared 常量自洽、`control_client.DEFAULT_SUPERVISOR_URL` 等于权威值、后端源码无 `8091`/`8005` 字面量、compose 中正则 `supervisor:(\d+)|--port (\d+)` 抓到的端口集合等于权威值。它从不 import 或断言 runner 的 `run_supervisor` 默认参数与 `--port` argparse 默认值——把 runner 默认改成 9999（不含被禁字面量）时全部 t062 测试仍绿，AC-008 点名的 runner 表面实际无守护。同一正则也抓不到 compose healthcheck 里的 `http://127.0.0.1:8005/supervisor/v1/health`（`supervisor:` 后跟的是 `/` 不是数字），healthcheck 端口改成 9999 同样不被发现。此外非默认配置贯穿只在 CLI 侧有既有覆盖（`tests/unit/test_t026_control_client.py` 的 env URL 覆盖用例），runner/compose 侧无任何非默认贯穿测试，与测试策略的明确要求不符。
- 建议：在同一守护测试中断言 runner 两个默认点（函数签名默认值与 argparse 默认值，可用 inspect/解析源码 AST 触达）等于 `DEFAULT_SUPERVISOR_PORT`；compose 检查改为提取全部 `:(\d+)/supervisor` 与 `--port (\d+)` 出现处（含 healthcheck）逐一比对；补一条 runner 非默认端口贯穿用例（至少断言解析后的 args.port 透传到 run_supervisor 调用点）。

### t062_test_f003 - 投递分类在 artifact 消费方的 REJECTED 分支无行为测试

- 严重度：minor
- 锚点：AC-006「投递分类在各消费方结果一致」
- 位置：`src/backend/cbrowser/supervisor/artifact_forwarder.py:293`（`classify_delivery_status(...) == REJECTED` 后标记 processed 继续）；`tests/unit/test_download_reconciler.py:385`（`test_forwarder_retries_after_retryable_4xx`）
- 问题：event 消费方有 400/422 永久拒绝 dead-letter 的真实行为覆盖（`tests/unit/test_supervisor_event_delivery.py`），但 artifact 消费方只测了 200 与 401 可重试两类；其新改的 REJECTED 分支（400/422 时标记已处理并继续后续事件）没有任何用例触达。共享函数本身已被 event 侧验证，故仅标 minor，但「各消费方一致」在 artifact 侧仍缺一半证据。
- 建议：给 `test_download_reconciler.py` 补一条 422（或 400）用例：断言该事件被标记 processed、不再重投，且同一批后续事件仍被转发。

### t062_test_f004 - AST 边界守护忽略相对 import，跨包相对导入可绕过

- 严重度：minor
- 锚点：AC-005、AC-007 的依赖方向守护可信度
- 位置：`tests/unit/test_t062_boundaries.py:42-56`（`_cbrowser_refs` 只处理 `node.level == 0` 的绝对 import）
- 问题：gateway/supervisor/shared 若改用 `from ..supervisor import ...` 这类相对 import，`test_gateway_and_supervisor_do_not_import_each_other` 与 `test_shared_imports_no_service_package` 都不会命中。当前代码经 grep 核实只有包内相对 import（如 gateway 的 `from .config import ...`），且 `test_t062_image_closure.py` 在组装树中实际 import 全部模块能兜住已交付镜像内的真实断裂，故仅为守护鲁棒性缺口，标 minor。
- 建议：`_cbrowser_refs` 增加 level≥1 相对 import 的解析（按文件所在包名拼接），或在测试 docstring 中明确声明该守护只覆盖绝对 import、跨包相对 import 由镜像闭包测试兜底。

### t062_test_f005 - 新增交付文件未做 git add -N，规定的 diff 命令看不到核心交付

- 严重度：minor
- 锚点：review scope 完整性（派审前须对新交付文件执行 `git add -N`）
- 位置：`git status --short` 的 `??` 项：`src/backend/cbrowser/shared/{agent_credentials,atomic_write,delivery,egress,endpoints,fencing,profile_locks}.py`、`tests/unit/{test_shared_atomic_write,test_t062_boundaries,test_t062_image_closure,test_t062_shared_rules}.py`、`docs/pending/todo/p092_t062_local_image_verification.md`
- 问题：本轮全部新增实现与测试文件仍是未跟踪状态，prompt 规定的 `git diff c5f8329...` 单独执行时不包含它们；本次审阅是靠文件系统直读才看到完整交付。指纹（reviewed_scope）覆盖未跟踪内容、文件本身可读，故不构成 INCOMPLETE，但任何只跑 diff 的复核者都会漏审核心文件。
- 建议：实施方对上述新交付文件执行 `git add -N` 后再派下一轮审阅。

## 结论

- 改测方向复核：逐项核对了 diff 中全部既有测试修改，无「迁就实现」的改测。具体判定：① `test_a31_unified_api_image.py` 与 `test_baseline_runtime_regressions.py` 的打包断言反转（API 全量 COPY、Supervisor 借 Gateway 包由必备改为禁止）是本 task 规格本身重定义打包契约，且新断言同时含正向（shared 整包 COPY 必须在）与负向（旧形态禁止）检查，不是弱化；② `test_a26_browser_image_modules.py` 新增 `TERMINAL_PACKAGES={shared}` 并把 `secret_files.py` 移出 UNRELATED，收窄了其闭包展开，但替代覆盖成立——`test_t062_image_closure.py` 在按 Dockerfile 组装的树中实际 import 每个镜像的全部模块、且 browser Dockerfile 确已整包 COPY shared 与单行 COPY secret_files，属合法的以更高层验证替代；③ preview 两处注入点改测（`os.chmod`→`os.fchmod`、`os.chown`→`os.fchown`，暂存 glob `.*.tmp`→`*.tmp`、碰撞文件名与 uuid patch 点改指 `cbrowser.shared.atomic_write`）是机制搬家的注入点跟随，断言语义保留（失败清暂存、碰撞不删他人文件、chown 的 uid/gid 与「最终路径尚不可见」无窗口断言）；④ `test_preview_router.py` 的 stub service 新增 `profile_lock()` 公开方法、`test_supervisor_recovery_coordinator.py`/`test_supervisor_manual_retry.py`/`test_recovery_authority.py` 的 stub 改用 `is_profile_locked`，均是跟随生产公开接口变更；⑤ `test_auth_service.py` 是加强（领域会话对象字段与 DB 中 SessionModel 行 id/hash 逐项对账）；⑥ 其余均为被测模块搬家的 import 路径替换（endpoints、agent_credentials、egress、ProfileLockRegistry、delivery 常量）与 t027 注释更新，断言未动。
- 危险模式扫描：新增与改动的测试中未命中恒真断言、删/反转 expect（规格重定义的两处打包断言除外，见上）、注释掉断言、`.skip`/`.only`、`type: ignore` 新增、mock 被测逻辑、阈值掩盖或条件跳过弱化断言；删除的 `tests/unit/test_supervisor_file_storage.py` 唯一用例已在改名后的 `tests/unit/test_shared_atomic_write.py` 中原样保留并新增失败保旧、碰撞不删他人两条用例，覆盖未丢。
- 本轮新发现：5 条（2 important、3 minor）。
- 未进表的提示：① 基线失败定性已独立核实——用 `git archive c5f8329` 导出 pristine 树复跑 `test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip`，与当前 worktree 同为 `tests/fixtures/gateway_probe/topology.py:655` 的 `AttributeError: 'GatewayTopologyHarness' object has no attribute 'data_dir'`，确为既存基线失败、与本 task 无关。② 门禁证据数字与日志一致（unit 2012 passed/1 基线 failed、frontend 618 passed/5 failed 均为超时型）；integration 的 2 条 setup error「串行复跑通过」与 frontend 5 条「单跑通过」本轮未独立复跑（负载高、属证据模式定性），依赖 `.scratch/gate_evidence_20261113/` 日志与实施侧复跑记录，属 trust_prior。③ progress 实施笔记称 browser 镜像「加 adapters 两行（__init__ + egress_probe.py）」，但最终 Dockerfile diff 中无 adapters COPY（egress 已落 shared，adapters 不再需要）——笔记与最终交付不符，属 code 轴/实施侧订正事项，不影响测试结论。
- 总体判断：测试本身可信且核心行为覆盖成立（本轮独立复跑 44+128 条相关用例全绿，含五镜像闭包），但四条 AC 全部未打勾使打勾复验全数作废，且 AC-008 守护有真实盲区，未解决 important 存在，FAIL。
- 系统性 follow-up：无（AC-005 的真实 Docker 构建/readiness 顺延已登记 p092）。

### AC 复验方式

- AC-005：TICK-VOID，re_verified。task.md 未打勾；云端侧证据经独立复跑成立（test_t062_image_closure 五镜像组装树实际 import 与 test_t062_boundaries 依赖方向守护包含在复跑的 128 条全绿集合内），但真实 Docker 构建与 readiness 未验、按 [deploy] 顺延 p092，不足以支撑打勾。
- AC-006：TICK-VOID，re_verified。task.md 未打勾；原子写失败保旧/碰撞/symlink、锁串行与并行、fence、origin 白名单一致、event 侧投递分类行为测试经独立复跑全绿（44+128 条集合），但未打勾按规则作废（artifact 侧 REJECTED 覆盖缺口见 f003）。
- AC-007：TICK-VOID，re_verified。task.md 未打勾；test_auth_service 领域会话对象与 ORM 存储逐项对账、路由/认证依赖不导入 SessionModel 的 AST 守护、egress 移出 domain 后的 t052 行为回归经独立复跑全绿，但未打勾按规则作废。
- AC-008：TICK-VOID，re_verified。task.md 未打勾，且守护测试对 runner 默认端口与 compose healthcheck 存在盲区、非默认贯穿在 runner/compose 侧缺失（见 f002），测试证据不足以支撑该 AC。

coverage = 4 / 4

verdict: FAIL

## Round 2 (2026-11-13T23:10:55+08:00)

- task：`t062_control_plane_boundaries`
- spec：`docs/tasks/t062_control_plane_boundaries/task.md`
- diff_anchor：`c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- target：`git -C '/home/hatch/workspace/CBrowser_t062' diff c5f83296ece80a9a0ed9f1e48d957ce332f858c4`（交付已全部暂存，`git diff --cached` 可见完整交付，105 文件）
- round：2
- reviewed_at：2026-11-13T23:10:55+08:00

## Findings

本轮无新发现（无 t062_test_f006 及后续编号）。

### 前轮 finding 复核

- t062_test_f001（important）：处置成立。`task.md:30-33` 四条 AC 现均为 `- [x]`（直读核实）；`progress.md` 收尾报告口径已对齐——「结果：全部满足（AC-005 的真实 Docker 构建/readiness 部分按 [deploy] 口径顺延本地，p092 登记）」「AC 判定：见 task.md 行内打勾」，Round 1 的自相矛盾已消除。`docs/pending/todo/p092_t062_local_image_verification.md` 实存（本轮直读全文），内容覆盖两项顺延：第 1 项 AC-005 [deploy] 五镜像（api/gateway/supervisor/browser/stream）真实构建、独立启动与 readiness，含 Gateway 删 domain/Supervisor 文件、Supervisor 删 Gateway 整包、Browser 新增 shared 整包后 runtime_agent 全功能三个重点；第 2 项 AC-008 默认与非默认控制端口各跑一次部署的真实贯穿；第 3 项合入顺序说明。云端可验部分的测试证据经本轮独立复跑成立（见结论复验摘要），四条打勾改判 TICK-VALID（AC-005 的 [deploy] 部分、AC-008 的真实贯穿部分以 p092 为顺延凭据，非云端已验，与 Round 1 建议口径一致）。
- t062_test_f002（important）：处置成立。直读 `tests/unit/test_t062_boundaries.py:186-251` 的 `test_supervisor_port_single_authority`，Round 1 的三处盲区均已真实补上：① runner 运行期默认值——实际 import 后 `inspect.signature(run_supervisor).parameters["port"].default == DEFAULT_SUPERVISOR_PORT`，是运行期断言而非源码文本比对；② CLI 默认值——AST 遍历 runner.py 的 `add_argument("--port", ...)` 调用，断言 default 恰一处且必须是 `ast.Name`、名为 `DEFAULT_SUPERVISOR_PORT`（改成任何字面量即失败，改成其他常量名亦失败）；③ compose 三类端口面全量提取比对——supervisor 服务块内 `--port", "(\d+)"`（command）、`127\.0\.0\.1:(\d+)`（块内 healthcheck URL）、全文件 `supervisor:(\d+)`（跨服务 URL）三者并集须恰等于 `{str(DEFAULT_SUPERVISOR_PORT)}`，另断言就绪探针含权威值、后端源码（shared/endpoints.py 除外）无 `8091`/`8005` 字面量。按 Round 1 的变异设想逐一推演：runner 默认改 9999 触签名断言、CLI 改字面量触 AST Name 断言、healthcheck 改 9999 触 compose 并集断言，盲区已闭。该测试在本轮复跑集合内通过（boundaries 9 passed）。非默认端口在真实部署中的行为贯穿属部署级验证，已登记 p092 第 2 项顺延，不在本守护的静态覆盖内，与 AC-008 的 TICK-VALID 顺延口径一致。
- t062_test_f003（minor）：处置成立。直读 `tests/unit/test_download_reconciler.py:147-202` 的 `test_forwarder_delivery_classification_outcomes`：参数化两例，驱动真实 `DownloadArtifactForwarder`（httpx MockTransport 为 HTTP 边界替身，被测分类逻辑为生产代码），连续两轮 `forward_pending()`——422 例断言两轮后总投递次数恰为 1（只投递一次；第二轮不再投递即「已标记处理」的行为证据），503 例断言总投递次数为 2（保留待重试、下一轮再投）；两例首轮/次轮转发成功数均为 0，断言无虚设。该测试在本轮复跑集合内通过（download_reconciler 25 passed）。artifact 消费方 REJECTED 分支自此有行为覆盖，AC-006「各消费方一致」两侧证据齐备。
- t062_test_f004（minor）：处置成立。两处助手均已解析相对 import（直读核实，逻辑同构）：`tests/unit/test_t062_boundaries.py:42-71` 的 `_cbrowser_refs` 与 `tests/unit/test_a26_browser_image_modules.py:35-55` 的 `_top_level_cbrowser_refs` 都按文件相对后端根的路径构造所在包名，对 `ast.ImportFrom` 的 `level≥1` 节点按 level 回退包层级后拼接 module 归一为绝对 cbrowser 顶层名——如 gateway 内文件写 `from ..supervisor import ...` 会得到 `supervisor` 并触犯跨服务守护，包内相对引用只记本包名、不误报。两文件均在本轮复跑集合内通过（boundaries 9 passed、a26 5 passed）。
- t062_test_f005（minor）：处置成立（本轮亲验，状态取自本报告追加之前）。`git status --short` 共 105 条，全部为第一列暂存状态（M/A/R/D），无未跟踪项（`??` 为零）、无未暂存的已跟踪修改（`git diff --name-only` 为空）；`git diff --cached --stat` 为 105 文件、+1595/-594，含 shared 新模块（atomic_write/delivery/egress/fencing/profile_locks 为 A、agent_credentials/endpoints 为 R）、四个新测试文件（test_t062_boundaries/test_t062_image_closure/test_t062_shared_rules/test_shared_atomic_write，均为 A）、p092（A）与两份 review 报告（A）——规定的 diff 命令现已可见完整交付。本报告的 Round 2 追加本身会使 review_test.md 出现未暂存改动，属 reviewer 报告文件、按规程不由 reviewer 暂存，不属本 finding 的交付暂存范围。

## 结论

- 前轮 finding 复核：5 条全部处置成立（2 important + 3 minor），逐条依据见上，均由直读文件、状态命令与测试自跑支撑，未采信处置表自述。
- 本轮新发现：0 条。
- 复验摘要（本 reviewer 独立执行）：落点校验 `git rev-parse --show-toplevel`（cd 进 worktree 后执行）= `/home/hatch/workspace/CBrowser_t062`、分支 `t062_control_plane_boundaries`、HEAD 为基线 `c5f8329`（交付在 index 中）；以 gate venv（`/home/hatch/workspace/CBrowser/.scratch/gate_venv`，Python 3.15.2）+ `PYTHONPATH=src/backend` + `TMPDIR=.scratch/tmp` 自跑七个文件共 70 passed、0 failed——`test_t062_boundaries.py` 9 passed、`test_t062_image_closure.py` 5 passed（五镜像组装树实际导入）、`test_shared_atomic_write.py` 3 passed、`test_t062_shared_rules.py` 5 passed、`test_a26_browser_image_modules.py` 5 passed、`test_download_reconciler.py` 25 passed、`test_auth_service.py` 18 passed（领域会话对象与 ORM 存储对账）。
- 基线失败定性复核：抽跑 `test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip` 单例，仍为 FAILED，签名与 Round 1 在 pristine 基线树的证据逐字一致——`tests/fixtures/gateway_probe/topology.py:655` 的 `AttributeError: 'GatewayTopologyHarness' object has no attribute 'data_dir'`。定性记录（基线既存、非本 task 引入、留终局处置）与当前状态一致。
- 未进表的提示：① `progress.md` 实施笔记称 browser 镜像「加 shared 整包一行与 adapters 两行（__init__ + egress_probe.py）」，本轮 grep 复核最终 `config/docker/browser_runtime/Dockerfile` 无任何 adapters COPY（egress 已落 shared、adapters 不再需要）——笔记与最终交付仍不符，沿用 Round 1 定性：实施侧订正事项，不影响测试结论、不阻断本轴判定。② integration 2 errors 与 frontend 5 failed 的负载 flaky 定性沿用 Round 1 口径（证据在 `.scratch/gate_evidence_20261113/`），本轮未重跑全量门禁。
- 总体判断：Round 1 的 FAIL 两主因（AC 打勾闭环未完成、AC-008 端口守护盲区）与三条 minor 均已真实修复并经独立复跑验证，四条 AC 打勾与实现、测试证据、progress 口径三者一致，无 critical/important/minor 遗留，test 轴 verdict PASS。AC-005 [deploy] 真实镜像验证与 AC-008 非默认端口真实贯穿仍待本地 p092 补验，属已登记顺延、不阻断本轴判定。
- 系统性 follow-up：无（顺延事项已登记 p092，不重复建议）。

### AC 复验方式

- AC-005：TICK-VALID，re_verified。task.md 已打勾；云端部分（中立包导入、Gateway/Supervisor 零互 import 的 AST 守护、按包 COPY、五镜像闭包组装实际导入）经本轮自跑复验成立（boundaries 9 + image_closure 5 passed），真实 Docker 构建/readiness 按 [deploy] 顺延 p092（pending 实存且内容覆盖五镜像构建/启动/readiness 与重点风险项）。
- AC-006：TICK-VALID，re_verified。task.md 已打勾；原子写失败保旧/碰撞不误删（shared_atomic_write 3 passed）、锁串行并行与 origin/fence/投递分类单一权威（shared_rules 5 passed）、投递分类两侧消费方行为（event 侧 Round 1 已验、artifact 侧本轮 f003 补强用例在 download_reconciler 25 passed 内）均成立。
- AC-007：TICK-VALID，re_verified。task.md 已打勾；`test_auth_service.py` 18 passed（领域会话对象字段与 DB 中 SessionModel 行逐项对账）、路由/认证依赖不导入 SessionModel 与 domain egress 无 I/O 实现的 AST 守护在 boundaries 自跑集合内通过；`ProfileService.profile_lock()` 公开接口由 test_preview_router 等既有用例随门禁覆盖。
- AC-008：TICK-VALID，re_verified。task.md 已打勾；端口权威守护经 f002 复核已覆盖 runner 运行期默认值、CLI 常量名引用、compose 三类端口面与探针，自跑通过；非默认端口真实部署贯穿顺延 p092 第 2 项。

coverage = 4 / 4

reviewed_scope: 6feea54970e59850

verdict: PASS
