---
tid: "t083"
slug: "supervisor_state_reconciliation"
title: "Supervisor 批量状态协调与稳态资源开销闭环"
status: "done"
branch: "t083_supervisor_state_reconciliation"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "12e3ac2c3066fb732c98ba9cc0bde5fd3abef133"
spec_source_sha: "ab3bd3c6e9ae8d0a1de2ba72b1880d9d62f6438a"
depends_on: "t081,t082"
conflicts_with: "t075,t076,t078"
note: "2026-11-18 用户授权详细立项；仅创建 backlog，不实施、不发布。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 创建记录：2026-11-18T00:31:35+08:00，用户要求按已核实资源问题与架构方案详细立项；仅创建 backlog，尚未实施、验证业务 AC 或获得本批 commit/push 授权。
- 跨 task 契约与脱敏现场基线：docs/tasks/t080_linux_native_runtime_storage/architecture_scope.md。长期 specs/blueprint/ADR 在对应实施 finalization 同步，本批不预写生效结论。
- 2026-11-18 云端实施启动（owner cloud-muse-20261117）：run-begin 以 t082 分支为 base；t083 硬依赖 t081+t082 两条兄弟分支，run-begin 的 --base 只接受单个已完成 task 分支，故先把 t081 分支合并进 t082 分支作为集成基底（merge 12e3ac2，仅 docs/blueprint/testing.md 一处叠加冲突、双节并存解决；t082 finish 记录 4c43d34 不变、仍为祖先），diff_anchor=12e3ac2。
- 现状核查（实施前）：内部 supervisor 表面把 UI 聚合 handler 直接复用为 GET /profiles（富列表）与 GET /profiles/{id}/runtime（富 DTO，handler 内同步 refresh_search_defaults/refresh_transport 下游 RPC）；Supervisor 每秒 recovery tick 先列表再逐 Profile GET runtime（现场 60 秒 107 次），readiness 与 \_reconcile_profile、start_profile 意图校验同样逐个 GET；Compose 三服务各有 5 秒 Docker healthcheck（python3 -c 进程内 exec，约 34 次/分钟），gateway/supervisor 以 service_healthy 依赖，deploy 用 up --wait 判健康。
- 设计（ADR 040）：①profile_runtimes 加 state_revision 列（迁移 0013，ORM before_update 事件统一自增），API 进程 epoch 于启动生成；②最小批量状态协议（cbrowser/shared/state_protocol.py）：SupervisorProfileState 仅含意愿/绑定实例/配置/终态事件/重试封锁字段 + state_revision 围栏，GET /state/snapshot 按 profile_id 键集分批（声明上限 200/批，一批一 SELECT）；③API 在 publish_profile_change 汇聚点经既有控制通道（supervisor_url + 服务 bearer）推送 StateChangeNotice（全量最小状态 + 移除名单），Supervisor 状态缓存按 epoch+revision 围栏应用、标脏；④Supervisor SupervisorStateCache：单飞快照（同一时刻至多一个在途）、失败有界退避、30 秒完整兜底对齐、权威窗口（完整快照且最近成功接触 ≤40 秒）外消费者暂停（与旧 API 不可达语义一致）；recovery/readiness/reconcile/start 意图校验全部改读缓存，稳态 tick 零 HTTP；⑤删除旧内部 GET /profiles 与 GET /profiles/{id}/runtime 路由；⑥runtime GET/列表/SSE 只读已维护观测，transport/search-defaults 改由 coordinator 有界后台循环刷新；⑦Compose 删除三处 healthcheck、depends_on 改 service_started，deploy 改为 up 后以 scripts/service_readiness_probe.py（容器内执行、单一截止时间）在截止时间内确认 API/Gateway/Supervisor 真实 readiness，未就绪/未知显式失败，不再以进程已启动判成功；Supervisor readiness 改读状态缓存（未知即未就绪）；⑧稳态探针 scripts/steady_state_probe.py 纳入交付（Docker 事件 exec 口径、rchar/CPU、策略修订计数逻辑单测），真实 4 Profile/10 分钟与故障矩阵属 [deploy]，已登记 p134/p135 并在 task.md AC-009/AC-010 契约区加处置注记。
- 实施完成（云端可做部分）：迁移 0013 + state_revision 映射；shared/state_protocol.py + schema 导出（export_state_protocol.py，纳入门禁 protocol_drift_check）+ 内部 OpenAPI 再生；API snapshot 端点（repository.list_runtimes_batch 一批一 SELECT）与旧路由删除；coordinator publish 汇聚点推送（含删除 removed 名单）+ 有界后台观测刷新循环（15 秒/并发 4）+ runtime GET 删同步 refresh；Supervisor state_cache.py（围栏/单飞/退避/权威窗口/本地写失效 note_local_write）+ core/recovery/control_server/runner 全部消费方迁移（bind/observed/desired-state 写成功后标失效）；Compose 删三处 healthcheck + service_started；deploy.sh 改 up + service_probe_exec 真实 readiness 等待（保留 Profile 收敛 verify）；steady_state_probe.py（聚合口径纯函数）；ADR 040 + blueprint（architecture/supervisor/domain/testing）+ specs（runtime_lifecycle tasks、release_deployment 验收口径）同步。
- 存量测试处置（harness 迁移，断言语义不变）：t026 的 fake API 改供 snapshot 端点、readiness 未知 reason 改 api_state_unknown（新契约口径）；t026 readiness 逐 Profile 读取失败隔离测试改写为新机制下的逐 Profile 评估隔离（批量协议无逐个读取可失败，隔离点移至 \_profile_readiness 评估，理由见测试内注释）；recovery_coordinator/startup_recovery/recovery_authority 三文件的 mock core 改经 \_state_entries/\_state_entry 供数（side_effect 队列语义等价迁移）；test_supervisor_recovery 的 fake API 加 snapshot 分支；coordinator 请求计数断言改为按 RPC 路径过滤（state-changes 通知为新增设计内流量，不计入 reconcile 次数/重试上限）；control_auth 的 malformed 测试改经真实 StateCache 验证畸形快照→503。
- 新测试：test_t083_state_cache.py（9 测）、test_t083_state_protocol_api.py（4 测）、test_t083_steady_state_probe.py（6 测）。
- 审阅第 1 轮（2026-11-18 18:30，双路 FAIL，指纹 d97be31400b1f373）：代码审阅 7 finding（important 1：f001 稳态探针 naive UTC 时间串致 Docker 按客户端本地时区解析、采样窗口整体错位 8 小时；minor 6：f002 exec-id 排除取错字段、f003 探针吞 docker 失败静默出全零报告、f004 观测刷新每 15 秒 N 次非批量读取、f005 domain 蓝图迁移号误写 0012、f006 release_deployment 仍称三服务有 compose 健康检查、f007 core \_state_entries/\_state_entry 十余行逐字重复）；测试审阅 7 finding（important 2：f001 service_readiness_probe 判定逻辑零行为测试、f002 t026 隔离测试诊断断言弱化且无失败输入；minor 5：f003 notice 接收端与 runner 脏唤醒无测试、f004 缓存精度缺口、f005 control_auth 畸形测试复写生产驱动逻辑、f006 offline 恢复测试以 sync_now 绕过退避门、f007 recovery_authority fake 仍走已删旧路由且条目语义与生产不一致）。按流程先撤回 task.md 全部 10 条 AC 打勾再修。
- 第 1 轮 finding 修复（全部已修，见 Review 处置表）：探针改 Unix 纪元秒窗口并入报告 window_epoch、exec-id 取冒号后段、docker 非零退出抛 DockerCommandError 且 main 返回 2；观测刷新改 list_runtime_batch 分页取目标；domain.md 改迁移 0013、release_deployment 改写健康检查口径；core 抽 \_ensure_authoritative()；readiness 探针补 5 个 stub HTTP 行为测试（全 ready/非 ok/挂起/不可达/用法错误）；t026 诊断断言改为 session_instance_mismatch 并加 Docker 抛错 Profile 隔离用例；新增 test_t083_runner_state_wakeup.py（notice 端点 401/200+标脏、\_scan_due 判定函数）；缓存测试补批次上限断言、100/1000 规模、等修订重放、退避边界（+1 秒无重试/+3 秒重试）；control_auth 改绑真实 SupervisorCore.\_state_entry；offline 恢复测试改可推进时钟 + maintain() 自行发起对齐；recovery_authority fake 改走真实快照校验与 \_entry_dict 投影、不可用返回 None；另补观测 sweep 批量选择测试（250 Profile 两批取数、仅 running+已绑定实例被刷新）。定向复跑：探针/缓存/唤醒/authority/control_auth 36 passed；t026/recovery/coordinator 49 passed；协议 API/迁移/recovery 协调/runner 周边 66 passed；sweep 测试 3 passed。
- 第 2 轮全量门禁（t083-gates-r2.log，证据 .scratch/gate-t083/junit 齐全）：protocol/requirements/contract（389 条 0 失败）/design_lint/design_check/frontend_build/integration（228 条 0 失败）全 exit 0；unit 仅 15 条老基线（t063 ×12、t068 ×2、a16 ×1），零新增；frontend_test 696/697——唯一失败是 t073 的 ProfileCreateDialog 宽容器用例 5 秒超时（整套 265 秒、并行负载下超时），本 task 零前端改动，串行单跑该文件 8/8 通过（6.1 秒），定性为负载抖动。
- finish 阻塞（2026-11-18 晚间，review 已 PASS 但 finish 未能提交）：`task.py finish` 第 3 步核心资产所有权校验 FAIL——工作区相对 diff_anchor（12e3ac2）有 15 处非 owner 核心资产差异；其中 14 处是合 main 提交 d2d4847 带入的 A 线 finish 产物（t076/t078/t079 各 task 的 handoff.json、progress.md、review\_\*.md、task.md），另 1 处是我自己的 t081 review_test.md:213 hygiene 改动（已还原至 HEAD，损失为零——该行绝对路径问题仍在，属 t081 已完结记录，宜由主仓另行处理）。校验逻辑（lifecycle.py:765-770）取 before=diff_anchor 整树、after=完整工作区，无“与 main 一致即放行”的例外；且 finish 第 5 步还要求 HEAD == diff_anchor（lifecycle.py:803-805，禁止中间 commit），而本分支 HEAD 已是 merge 提交 d2d4847，两处同源阻塞。工具链内无合规出路：finish 无绕行旗标，diff_anchor 只在 start 时写入（integration.py:377），无中途改锚命令，front matter 只经 task.py 修改。待主会话裁决：改锚点至 d2d4847（需手改 front matter + 重渲染 + 第 4 轮确认审阅）或重排分支历史（在 12e3ac2 上重做实现 commit 并把 35f3e07 改链并入本 commit，另需确认轮）或其它路径。实现内容本身不受影响：review-status overall=PASS（round 3，指纹 09bf8dd004b53625），commit message 已备好（/tmp/t083_commit_msg.txt），67 个文件已暂存待提交。
- 主会话收尾处置（2026-11-18 晚间）：裁决走重排路径——分支 HEAD 以 reset --soft 回到 diff_anchor（12e3ac2），合 main 带入的 14 处非 owner 核心资产回退为锚点内容（t076/t078/t079 的 progress.md 与 task.md 还原为锚点版本；handoff.json 与 review\_\*.md 在锚点时尚未产生，自工作区移除；这些文件主仓已有更新版本，合入时以主仓为准），实现内容与代码文件未作任何改动。处置后实测：HEAD 与 diff_anchor 一致、非 owner 核心资产差异 0、未暂存 0、未跟踪 0。因工作区相对第 3 轮审阅指纹仅有上述流程性变化，另开第 4 轮确认审阅，核对实现内容与第 3 轮一致。
- 全量 unit 分组跑（第 1–4 组可信，第 5 组污染作废）：a–g 组 5 坏/656 过、l–r 组 1 坏/306 过、s 组 5 坏/309 过、t0xx 组 26 坏/997 过/10 error；减老基线 15（t063 ×12、t068 ×2、a16 ×1）后新破损 22 条，已逐簇修复：t062 边界（shared 层不得引 domain，投影函数移至 api/state_projection.py）、t027/t080 deploy harness（fake repo 补拷 service_readiness_probe.py；--wait/--wait-timeout 断言按 t083 新机制改写；compose 契约改断言无 healthcheck/service_healthy）、t082 收敛（fake API 补 snapshot 分支）、t049/t055/t035/t041/a3/docker_offload/unprotected/infra/selkies/fences（同上，逐文件 fake API 补 snapshot 分支；bare core 补 state_cache）、api_search_defaults（真 bug：publish 的通知投影在失败隔离之外，投影异常会吞掉 SSE 主发布——投影已移进 \_notify_supervisor_state 内部全程尽力而为）、t054/t056（见下）、repo_hygiene（见下）。第 5 组跑因分组 glob 写错（test_t4\* 匹配不到 test_t041 等 test_t0NN 文件名，空文件列表使 pytest 回落到 testpaths 整棵树，含 .repo_template/tests 与 integration）结果污染（2908 过/59 坏含重复计数），作废不采信。
- t054/t056 双头根因（主会话核实）：t078 与 t081 各建一个 0011 迁移形成双头；主仓 35f3e07 已改链（c81f0a11b001 接到 t078 的 c41d9a02e6b7 之后）恢复单头。本线合入主仓最新 main（c8563e2，merge 提交 d2d4847；testing.md 仅 t081 节顺序冲突，已按 main 顺序去重解决），并把 t083 迁移按 main 的序列口径改号 0012→0013（文件、REVISION_0013、test_head_is_0013_and_single、t056 增量断言、ADR 040 与 progress.md 引用一并改）；重跑 t054/t056/hygiene 22 passed。
- repo_hygiene 泄漏定位：`docs/tasks/t081_immutable_font_resource_lifecycle/review_test.md:213` 的审阅者复跑证据里含字面量 `TMPDIR=~/workspace/cloud-task-logs/tmp-t081`（原文为绝对家目录路径），已改为相对路径；该文件是 t081 分支带入（t081 门禁时尚未写入故当时未触发）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

第 1 轮（指纹 d97be31400b1f373，代码审阅 FAIL、测试审阅 FAIL，2026-11-18 18:30）：

|finding_id|status|处置|
|---|---|---|
|t083_code_f001|已修|探针窗口改 Unix 纪元秒并入报告 window_epoch，补单测锁定 --since/--until 为纯数字纪元|
|t083_code_f002|已修|exec-id 取冒号后段，补真实 exec id 集合单测|
|t083_code_f003|已修|docker 非零退出抛 DockerCommandError，main 返回 2 不出全零报告，补单测|
|t083_code_f004|已修|观测刷新改 list_runtime_batch 分页取目标，补 250 Profile 两批取数测试|
|t083_code_f005|已修|domain.md 迁移号改 0013|
|t083_code_f006|已修|release_deployment 改写为 Compose 无 healthcheck、健康由控制组件观察 + service_readiness_probe 确认|
|t083_code_f007|已修|core 抽 \_ensure_authoritative()，两方法只留取值行|
|t083_test_f001|已修|新建 test_t083_service_readiness_probe.py：stub HTTP 覆盖全 ready/非 ok/挂起/不可达/用法错误 5 测|
|t083_test_f002|已修|t026 诊断断言改为 session_instance_mismatch，并加 Docker 抛错 Profile 隔离用例|
|t083_test_f003|已修|新建 test_t083_runner_state_wakeup.py：notice 端点 401/200+标脏、runner 抽 \_scan_due 判定函数并测脏唤醒与 30 秒兜底|
|t083_test_f004|已修|缓存测试补批次上限断言、100/1000 规模分批计数、等修订重放、退避边界 +1/+3 秒|
|t083_test_f005|已修|control_auth 改绑真实 SupervisorCore.\_state_entry（裸实例 + 真实 state_cache）|
|t083_test_f006|已修|offline 恢复测试改可推进时钟，退避到期后 maintain() 自行发起对齐|
|t083_test_f007|已修|recovery_authority fake 改走真实快照校验与 \_entry_dict 投影，不可用返回 None|

第 2 轮（指纹 60ba63b53a5a49b6，代码审阅 PASS、测试审阅 PASS，2026-11-18）：代码侧 0 新 finding，第 1 轮 7 条代码 finding 全部核实消除，AC 10/10 TICK-VALID，独立复跑 179/179；测试侧 1 条新 minor finding，第 1 轮 7 条测试 finding 全部核实消除，AC 10/10 TICK-VALID（含 AC-006 由 TICK-VOID 翻为 TICK-VALID），独立复跑 194 passed。

|finding_id|status|处置|
|---|---|---|
|t083_test_f008|已修|补 Supervisor 未就绪行为测试：stub 的 supervisor_not_ready 模式已有定义未被使用，现加 test_supervisor_not_ready_is_listed_and_fails（readiness 返回 ready False → reason 为 services_not_ready:supervisor、main 返回 1）；复跑 test_t083_service_readiness_probe.py 6 passed|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：10 条 AC 全部打勾（AC-009/AC-010 为 [deploy]，按用户 2026-11-18 裁定：打勾表示云端可做部分完成，真实验证延期至本地统一补验，跟踪 p134/p135）
- 测试：第 2 轮全量门禁（t083-gates-r2.log）：protocol/requirements/contract（389 条 0 失败）/design_lint/design_check/frontend_build/integration（228 条 0 失败）全 exit 0；unit 仅 15 条老基线（t063 ×12、t068 ×2、a16 ×1）；frontend_test 696/697，唯一失败为 t073 对话框用例 5 秒超时，串行单跑 8/8 通过，定性负载抖动
- 黑盒：无（云端无 Docker/真实运行环境；真实 4 Profile 稳态与故障矩阵属 [deploy]，见 p134/p135）
- review：第 1 轮双路 FAIL（代码 7 finding、测试 7 finding，全部已修）；第 2 轮双路 PASS（代码 0 新 finding、测试 1 条 minor 新 finding f008，已修）；第 3 轮确认轮双路 PASS（0 新 finding）；review-status overall=PASS（round 3，指纹 09bf8dd004b53625）
- AC 判定：见 `task.md` 行内打勾，10/10

### 结果摘要

- Supervisor 批量状态协调落地：最小批量状态协议（GET /state/snapshot，200/批，一批一 SELECT）+ 推送通知（StateChangeNotice，epoch/revision 围栏）+ SupervisorStateCache（单飞/退避/30 秒兜底/40 秒权威窗口），recovery/readiness/reconcile/start 意图校验全部改读缓存；旧内部 GET /profiles 与 GET /profiles/{id}/runtime 已删；runtime GET 纯读已维护观测，transport/search-defaults 由 15 秒有界后台循环刷新（本轮改走 list_runtime_batch 分页取目标）。
- 健康责任迁入控制组件：Compose 删三处 healthcheck、depends_on 改 service_started；deploy 改 up 后以 service_readiness_probe.py 在单一截止时间内确认三服务真实 readiness；稳态探针 scripts/steady_state_probe.py 纳入交付（Docker 事件 exec 口径、纪元秒采样窗口、失败 loud fail）。
- 本地统一补验：p134（AC-009 真实 4 Profile/10 分钟稳态）、p135（AC-010 故障矩阵）；t082 分支指针因集成基底前进至 12e3ac2（finish 记录 4c43d34 不变）；迁移改号 0012→0013（合 main d2d4847）。

### 长期文档闭环

执行 finalization 时更新关联 active spec 的 tasks 清单及 task.md 指定 blueprint/ADR。正式 spike 通过工具创建，结论入 findings 并回填；创建期不提前声明实施或闭环。
