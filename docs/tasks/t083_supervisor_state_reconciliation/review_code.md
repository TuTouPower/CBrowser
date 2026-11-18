# Task review t083（reviewer_focus: 代码）

- task：`t083_supervisor_state_reconciliation`
- spec：`docs/tasks/t083_supervisor_state_reconciliation/task.md`
- diff_anchor：`12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`
- target：`git diff 12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`
- round：1
- reviewed_at：2026-11-18T18:30:50+08:00

reviewed_scope: d97be31400b1f373

评审范围说明：相对 anchor 的 `git diff` 除 t083 自身改动外，还包含已合入的 t076–t082 合并提交（那些工作已在其各自 task 下审过，本轮不重复评审）。本轮实际评审对象是 t083 自身的增量：48 个已暂存修改文件 + 14 个新增未跟踪文件（新协议/缓存/探针/迁移/ADR/pending/测试）。新增文件未做 `git add -N`，因而不在 `git diff` 输出中出现；本轮已逐个从 worktree 直接读过，全部纳入评审。

## Findings

### t083_code_f001 - 稳态探针采样窗口整体错位：naive UTC 时间串被 Docker 按客户端本地时区解析

- 严重度：important
- 锚点：AC-009、AC-010（计数与测量器开销可复核；保存 CPU/rchar/宿主日志前后样本，缺日志不冒充零错误）
- 位置：`scripts/steady_state_probe.py:213`（`run_probe` 的 `since`），`scripts/steady_state_probe.py:215-228`（`--since`/`--until` 取值）
- 问题：`run_probe` 用 `time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())` 生成不带时区后缀的 UTC 时间串，传给 `docker events --since/--until`。Docker 的 `docker-system-events` 手册明确写明：支持的日期格式包含 `2006-01-02T15:04:05`，且“不提供 `Z` 或 `+-00:00` 时区偏移时，使用客户端本地时区”。探针在用户 Mac 宿主机（Asia/Shanghai，UTC+8）上运行 Docker 客户端，于是 `since`/`until` 都被当作 UTC+8 解析——600 秒采样窗口整体平移为真实窗口的 8 小时之前。后果：计数反映的是 8 小时前那个 10 分钟窗口（大概率落在暖机/部署期，或因 Docker 事件仅保留滚动 1000 条而取到空窗口），而不是稳态窗口；AC-009 的“零 exec/零 churn”与 AC-010 的故障前后样本都建立在错误的窗口上，可误报失败也可误报通过。复现路径：在 UTC+8 宿主机上跑 `steady_state_probe.py --duration 600`，核对 `docker events --since <输出值>` 实际覆盖的绝对时间，比对探针报告的窗口。
- 建议：改用无歧义的时间表达，例如 Unix 纪元秒（`int(time.time())`）或带 `Z` 的 RFC3339（`time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())`），并补一个单测锁定 `--since`/`--until` 入参含时区信息。

### t083_code_f002 - 探针 exec-id 排除分支取错字段：`measurement_exec_ids` 永远匹配不上真实 exec id

- 严重度：minor
- 锚点：行为缺陷（测量器自身 exec 排除机制半失效）+ ADR 040“测量器自身 exec 打标排除”
- 位置：`scripts/steady_state_probe.py:88-96`（`aggregate_events` 的 `exec_create` 分支）
- 问题：真实 Docker 事件的 Action 形如 `exec_create: <exec-id>`，代码取 `action.split(":", 1)[0].strip()` 得到的是字面量 `"exec_create"`，而不是 exec id，于是 `exec_id in measurement_exec_ids` 对任何真实 exec id 都恒为假。唯一实际生效的排除路径是容器标签 `com.cbrowser.measurement=steady-state-probe`，但没有任何容器带该标签，且 `run_probe` 从不传 `measurement_exec_ids`。当前生产路径未因此误计数（`run_probe` 自身的 rchar 读取发生在 `--since` 窗口之外：before 读在 `since` 计算前，after 读在事件拉取后），所以是潜伏缺陷而非现网误计数；但参数对外承诺的按 exec id 排除能力是坏的，后续调用方一旦传真实 id 会被静默忽略。
- 建议：取 `action.split(":", 1)[1].strip()`（无冒号时为空串），并补一个传入真实 exec id 集合的单测；或删除该参数，只保留标签路径。

### t083_code_f003 - 探针收集失败时静默返回空事件，零计数 + 退出 0 冒充干净窗口

- 严重度：minor
- 锚点：AC-009、AC-010（计数可复核；缺日志不冒充零错误）
- 位置：`scripts/steady_state_probe.py:135-148`（`_docker_json_lines`），`scripts/steady_state_probe.py:239-258`（`run_probe`/`main`）
- 问题：`_docker_json_lines` 以 `check=False` 调 `docker` 且忽略返回码与 stderr，出错时返回 `[]`；`run_probe` 据此算出全零计数，`main` 打印报告并返回 0。Daemon 不可达、`--since` 解析失败、`docker` 不在 PATH 时，探针都会输出一份“零 exec/零 churn”的干净报告——与 AC-010“缺日志不冒充零错误”的要求同构的误报方向。需外部故障触发才显现，故定 minor。
- 建议：`docker` 非零退出时让探针以非零退出并输出错误（至少在报告里加 `collection_error` 字段且不把该次采样计为有效零值）。

### t083_code_f004 - 观测刷新循环每 15 秒做 N 次非批量 runtime 读取

- 严重度：minor
- 锚点：AC-002（DB 往返按批次增长，无 N 个独立 runtime GET）
- 位置：`src/backend/cbrowser/api/runtime_coordinator.py:817-849`（`_observation_refresh_loop`），`src/backend/cbrowser/api/runtime_coordinator.py:831`
- 问题：每轮 sweep 先 `list_profiles()`，再对每个 Profile `await self.profile_service.get_runtime(p.id)`（仓库层每次 2 条 SELECT：runtime 行 + profile 行），只为筛出 `desired=running` 且已绑定实例的目标。1000 Profile 规模下每 15 秒就是 2000 条 SELECT，而本 task 新增的 `list_runtimes_batch`（一批一 SELECT，200/批）5 批即可拿到同样的 `desired_state`/`runtime_instance_id`。有界（15 秒节律、本地 SQLite、仅筛选读）且不影响正确性，故定 minor，不 void AC-002（AC-002 的对齐轮次本身已按批次实现）。
- 建议：sweep 改用 `list_runtime_batch` 按页遍历筛选目标。

### t083_code_f005 - domain 蓝图把 state_revision 的迁移号写错为 0012，实际是 0013

- 严重度：minor
- 锚点：文档与实现不一致
- 位置：`docs/blueprint/domain.md:114`
- 问题：该行写“ORM `before_update` 事件……统一自增（迁移 0012）”，但实际迁移是 `src/backend/migrations/versions/0013_runtime_state_revision.py`（revision `d83a2c12b083`，down_revision 为 0012 的 `c81f0a11b001`），`test_head_is_0013_and_single` 亦锁定 0013 为单头。按错误号去查迁移会找到 t081 的字体资产目录迁移。
- 建议：改为“迁移 0013”。

### t083_code_f006 - release_deployment spec 仍称三服务“均有与能力匹配的 compose 健康检查”，与实现矛盾

- 严重度：minor
- 锚点：文档与实现不一致
- 位置：`docs/specs/release_deployment.md:20`
- 问题：该行写“API、Gateway、Supervisor 均有与能力匹配的 compose 健康检查：API `/api/v1/health`、Gateway `/gateway/v1/health`……Supervisor `/supervisor/v1/health`……”。t083 已删除 `compose.yaml` 中的三处 healthcheck（grep 确认无 `healthcheck:`/`service_healthy`；`tests/unit/test_t083_steady_state_probe.py` 的 compose 契约测试亦锁定），健康观察已迁入各服务控制组件 + deploy 时的 `service_readiness_probe.py`。spec 第一处（第 18 行）已同步新口径，第二处漏改。
- 建议：改写该句为“Compose 不再声明 Docker healthcheck；三服务健康由各自控制组件观察，deploy 以 service_readiness_probe 在单一截止时间内确认”。

### t083_code_f007 - core 的 `_state_entries` 与 `_state_entry` 十余行逐字重复

- 严重度：minor
- 锚点：DRY（单纯 verbatim 重复）
- 位置：`src/backend/cbrowser/supervisor/core.py:353-370`（`_state_entries`）与 `src/backend/cbrowser/supervisor/core.py:373-390`（`_state_entry`）
- 问题：两方法共享同一段 maintain → 有在途快照时 `sync_now()` → 权威性检查序列，仅最后一行取全部条目还是单条不同。重复尚未造成行为分叉（两处逻辑当前一致），按规则定 minor。
- 建议：抽一个私有 helper（如 `_ensure_authoritative()` 返回 bool），两方法只保留各自的取值行。

## 结论

- 本轮新发现：7 条（1 important，6 minor）
- 未进表的提示：
    - 文件过大：`src/backend/cbrowser/supervisor/core.py` 3608 行、`src/backend/cbrowser/api/runtime_coordinator.py` 1435 行，均已远超 800 行阈值，但为既有规模，t083 本轮仅净增少量行数；按降级规则不进 finding 表。
    - 圈复杂度：新增函数（`SupervisorStateCache._sync`/`apply_notice`/`maintain`、`aggregate_events`、`run_probe`、`_check_all`、`get_state_snapshot`、`_notify_supervisor_state`）手算 CC 均 < 10，无 ≥15 项；不进表。
    - 观察（未成 finding）：`src/backend/cbrowser/supervisor/core.py` 扫描恢复分支在 `if rt is None: ... return` 之后又写了一次冗余的 `if rt is not None:`；快照分页在总数恰为 200 倍数时会多发一次空批请求取 `next_cursor`；`publish_profile_change` 在 SSE 发布前先 await 最长 10 秒的 notice POST（HTTP 路径走 `publish_profile_change_later` 后台任务，不阻塞响应）；`docs/tasks/t081_immutable_font_resource_lifecycle/review_test.md` 有一行 TMPDIR 路径措辞改动（属 t081 的 repo_hygiene 修复，progress.md 有记录，非 t083 范围）。
    - 独立复跑证据（门禁 venv，串行）：新增 3 个 t083 测试文件 19/19 通过；受影响套件 `test_supervisor_recovery.py`、`test_supervisor_recovery_coordinator.py`、`test_supervisor_startup_recovery.py`、`test_t026_supervisor_convergence.py`、`test_supervisor_control_auth.py`、`test_api_runtime_coordinator.py`、`test_t054_migration.py`、`test_t056_migrations.py` 共 88/88 通过；`test_t027_release_controller.py` 54/54 通过；`scripts/export_state_protocol.py --check` 通过，`schemas/runtime/state_protocol.json` 与模型一致。
    - 已核对无问题的要点：旧内部 `GET /profiles` 与 `GET /profiles/{id}/runtime` 已删除（新测试断言 404；OpenAPI 内省文件对应段已删）；快照端点挂在路由器级 `require_supervisor` 服务鉴权之下，无 token 返回 401（已复跑）；`state_revision` 在 desired/bind/observed 三条写路径上各 +1（已复跑；无旁路批量更新，`profile_runtimes` 无 Core `update()` 语句）；`list_runtimes_batch` 一批一 SELECT、键集分页；通知按 revision 围栏、跨 epoch 整轮作废、未读完快照不当权威（缓存单测已复跑）；`service_readiness_probe.py` 所需的 `CBROWSER_API_URL`、`CBROWSER_GATEWAY_CONTROL_URL`、`CBROWSER_SUPERVISOR_TOKEN_FILE` 在 supervisor 容器环境中均已具备；`_execute_retry` 用的 `config_version`/`display_number` 在最小 DTO 中均有字段，无回归。
- 总体判断：实现主体扎实、AC 逐条有真实代码与测试支撑，但 f001 使 [deploy] 验收唯一的计数仪器采样了错误的 10 分钟窗口，在修复前 AC-009/AC-010 的本地补验无法产出可信证据；有一条未解决 important，故 FAIL。
- 系统性 follow-up：无（[deploy] 真实验证已登记 p134/p135，不重复建项）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。旧内部路由返回 404、快照端点无 token 401、state_revision 三写路径各 +1、通知推送含移除名单，四项均已复跑通过。
- AC-002：TICK-VALID，re_verified。limit=2 时 3 个 Profile 分两批读完、每批一 SELECT、稳态 maintain 零 fetch、并发 maintain 单飞，缓存单测已复跑通过。
- AC-003：TICK-VALID，re_verified。通知按 revision 丢弃迟到/重放、移除删条目、异 epoch 使完整性失效、30 秒兜底对齐、runner 以 drain_dirty 唤醒扫描，缓存单测与 runner 改动均已核对。
- AC-004：TICK-VALID，re_verified。runtime GET 纯度单测（spy coordinator 遇同步刷新即抛错）已复跑通过；`make_runtime_response` 只读已维护的 in-memory 观测。
- AC-005：TICK-VALID，re_verified。离线保留容器、Native 退出优先、重试重读缓存权威、单 Profile 失败隔离改写为逐 Profile 就绪评估，相关恢复套件 88/88 已复跑通过。
- AC-006：TICK-VALID，re_verified。Compose 无 healthcheck/service_healthy、deploy 以 service_readiness_probe 在单一截止时间确认三服务 readiness、未知即未就绪，t027 套件 54/54 已复跑通过。
- AC-007：TICK-VALID，re_verified。单飞快照、有界退避、重放通知不产生额外动作，缓存单测已复跑通过。
- AC-008：TICK-VALID，re_verified。观测刷新是与 UI 无关的 15 秒/并发 4 后台循环，runtime GET 纯度单测通过；无 Viewer 时循环继续运行，不新增控制循环开销。
- AC-009：TICK-VALID，re_verified。按修订契约（用户 2026-11-18 裁定）打勾含义为云端可做部分完成：稳态探针及其计数逻辑单测已复跑通过，Compose 无 healthcheck、deploy 走真实 readiness 探针已核对；真实 4 Profile/10 分钟验证延期至 p134，不在本轮复验内。注意 f001 须先修复，否则 p134 采样窗口错误。
- AC-010：TICK-VALID，re_verified。按修订契约打勾含义为云端可做部分完成：恢复语义由状态缓存围栏/兜底对齐的单元与集成验证覆盖（已复跑），故障矩阵与采样口径由探针交付定义；真实故障注入延期至 p135，不在本轮复验内。注意 f001 同样影响 p135 的采样窗口。

coverage = 10/10

verdict: FAIL

## Round 2 (2026-11-18T19:10:52+08:00)

- task：`t083_supervisor_state_reconciliation`
- spec：`docs/tasks/t083_supervisor_state_reconciliation/task.md`
- diff_anchor：`12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`
- target：`git diff 12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`
- round：2
- reviewed_at：2026-11-18T19:10:52+08:00

reviewed_scope: 60ba63b53a5a49b6

评审范围说明：与第 1 轮相同，相对 anchor 的 `git diff` 除 t083 自身增量外还包含已合入的 t076–t082 合并提交（已在其各自 task 下审过，本轮不重复评审）。本轮实际评审对象是 t083 自身增量，重点是第 1 轮 7 条代码 finding 的修复核实，以及修复过程引入的新问题扫描。落点仓库校验：`git -C` 方式的 `rev-parse --show-toplevel` 输出为工作目录本身（不带 `-C` 的首次调用因 exec 默认 cwd 不在仓库内而失败，属调用位置问题，已改用带 `-C` 的校验确认）。

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核（逐条以 diff/代码为准，不采信处置表自称）：
    - t083_code_f001（important，探针 naive UTC 时间串致采样窗口错位 8 小时）：已消除。`scripts/steady_state_probe.py` 的 `run_probe` 现以 `int(time.time())` 取 Unix 纪元秒作 `--since`/`--until`（文件内注释说明了 naive UTC 串被 Docker 按客户端本地时区解析的根因），报告含 `window_epoch: {since, until}` 纪元秒；`tests/unit/test_t083_steady_state_probe.py:163` 锁定 `window_epoch` 为纪元秒，已复跑通过。
    - t083_code_f002（minor，exec-id 排除取错字段）：已消除。`scripts/steady_state_probe.py` 的 `aggregate_events` 现取 `action.split(":", 1)[1].strip()`（无冒号时为空串），并保留容器标签路径作第二排除通道；`tests/unit/test_t083_steady_state_probe.py:124` 用真实 exec id `abc123deadbeef` 锁定匹配，已复跑通过。
    - t083_code_f003（minor，探针收集失败静默出全零报告）：已消除。`_docker_json_lines` 在 docker 非零退出时抛 `DockerCommandError`（含退出码与前 500 字符 stderr），`main` 捕获后打印错误并返回 2，不再输出报告；`tests/unit/test_t083_steady_state_probe.py:182` 锁定该行为，已复跑通过。`_inspect_stack` 同样走 `_docker_json_lines`，故其失败路径亦不再静默。
    - t083_code_f004（minor，观测刷新每 15 秒 N 次非批量读取）：已消除。`src/backend/cbrowser/api/runtime_coordinator.py:821-849` 的 `_observation_refresh_loop` 现以 `list_runtime_batch(after_profile_id=..., limit=MAX_STATE_BATCH)`（200/批）分页取目标，仅对 `desired_state == "running"` 且已绑定实例者做后台刷新；`tests/unit/test_runtime_coordinator_background_tasks.py:85-142` 以 250 个 runtime 锁定恰好两次取数，已复跑通过。
    - t083_code_f005（minor，domain 蓝图迁移号误写 0012）：已消除。`docs/blueprint/domain.md:114` 现写“迁移 0013”，与 `src/backend/migrations/versions/0013_runtime_state_revision.py` 及 `test_head_is_0013_and_single` 一致。
    - t083_code_f006（minor，release_deployment 仍称三服务有 compose 健康检查）：已消除。`docs/specs/release_deployment.md:20` 现写“Compose 不再声明 Docker healthcheck（t083 已删除三处 healthcheck）；三服务健康由各自控制组件观察……deploy 以 `service_readiness_probe.py` 在单一截止时间内确认”；`compose.yaml` 内 `healthcheck` 仅剩两行注释性说明，无实际 healthcheck 配置。
    - t083_code_f007（minor，core `_state_entries`/`_state_entry` 逐字重复）：已消除。`src/backend/cbrowser/supervisor/core.py` 现抽出 `_ensure_authoritative()`（maintain → 在途快照时 `sync_now()` → 权威性检查），两方法只留各自取值行；`_state_entries`/`_state_entry` 的所有调用点（readiness、恢复、start 意图校验）均经该 helper，已复跑相关套件通过。
- 本轮新发现：0 条。
- 修复过程新问题扫描：复核了修复触及的新/改路径——`_notify_supervisor_state`（投影已移进函数内部全程 try，投影异常只记日志不吞 SSE 主发布）、`SupervisorStateCache._sync`（中途失败丢弃已收集批次、保留旧条目与旧 `_complete`，退避有界 30 秒封顶）、`_ensure_authoritative`（退避期内未权威时返回 False 暂停协调，不绕过退避）、快照端点 `next_cursor`（总数恰为 200 倍数时多发一次空批，仅一次额外 SELECT，无正确性影响）——均未发现可观测缺陷。`_read_rchar` 失败仍静默返回 None，但 rchar 增量缺失时直接省略该项、不谎报零值，与 f003 的误报方向不同，不成 finding。
- 未进表的提示：
    - 文件过大：`src/backend/cbrowser/supervisor/core.py` 3608 行、`src/backend/cbrowser/api/runtime_coordinator.py` 1435 行，均已远超 800 行阈值，但为既有规模，t083 本轮仅净增少量行数；新增文件均远低于阈值（`state_cache.py` 216 行、`state_protocol.py` 86 行、`steady_state_probe.py` 309 行、`service_readiness_probe.py` 144 行、`state_projection.py` 32 行、迁移 42 行）；按降级规则不进 finding 表。
    - 圈复杂度：新增/改动函数（`SupervisorStateCache._sync`/`apply_notice`/`maintain`、`aggregate_events`、`run_probe`、`_check_all`、`get_state_snapshot`、`_notify_supervisor_state`、`_observation_refresh_loop`）手算 CC 均 < 10，无 ≥15 项；不进表。
    - 观察（未成 finding）：`src/backend/cbrowser/supervisor/core.py` 扫描恢复分支在 `if rt is None: ... return` 之后仍有一次冗余的 `if rt is not None:`（第 1 轮已观察到，修复轮未动，无行为影响）；快照分页在总数恰为 200 倍数时多发一次空批请求（见上）。
    - 独立复跑证据（门禁 venv `/home/hatch/workspace/CBrowser/.scratch/gate_venv/bin/python`，`PYTHONPATH=src/backend`，`TMPDIR=/home/hatch/workspace/cloud-task-logs/tmp-t083`，串行）：5 个 t083 新测试文件 31/31 通过；受影响套件 `test_supervisor_recovery.py`、`test_supervisor_recovery_coordinator.py`、`test_supervisor_startup_recovery.py`、`test_t026_supervisor_convergence.py`、`test_supervisor_control_auth.py`、`test_recovery_authority.py`、`test_api_runtime_coordinator.py` 共 75/75 通过；`test_runtime_coordinator_background_tasks.py`、`test_t027_release_controller.py`、`test_t054_migration.py`、`test_t056_migrations.py` 共 73/73 通过；合计 179/179 通过。本轮未跑全量门禁（任务要求只复跑受影响的关键测试）。
    - 已核对无问题的要点：旧内部 `GET /profiles` 与 `GET /profiles/{id}/runtime` 已删除（新测试断言 404；OpenAPI 内省文件对应段已删）；快照端点挂在路由器级 `require_supervisor` 服务鉴权之下，无 token 返回 401；`state_revision` 在 desired/bind/observed 三条写路径上各 +1；`list_runtimes_batch` 一批一 SELECT、键集分页；通知按 revision 围栏、跨 epoch 整轮作废、未读完快照不当权威；`service_readiness_probe.py` 所需的 `CBROWSER_API_URL`、`CBROWSER_GATEWAY_CONTROL_URL`、`CBROWSER_SUPERVISOR_TOKEN_FILE` 在 supervisor 容器环境中均已具备；`_execute_retry` 用的 `config_version`/`display_number` 在最小 DTO 中均有字段。
- 总体判断：第 1 轮 7 条 finding（含 1 条 important）均已真实消除，修复未引入新问题，AC 逐条有真实代码与测试支撑；无未解决的 critical / important，可以 PASS。
- 系统性 follow-up：无（[deploy] 真实验证已登记 p134/p135，不重复建项）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。旧内部路由返回 404、快照端点无 token 401、state_revision 三写路径各 +1、通知推送含移除名单，四项均已复跑通过。
- AC-002：TICK-VALID，re_verified。limit=2 时 3 个 Profile 分两批读完、每批一 SELECT、稳态 maintain 零 fetch、并发 maintain 单飞，缓存单测已复跑通过；观测刷新改批量取数后 250 Profile 恰好两次取数亦已复跑通过。
- AC-003：TICK-VALID，re_verified。通知按 revision 丢弃迟到/重放、移除删条目、异 epoch 使完整性失效、30 秒兜底对齐、runner 以 drain_dirty 唤醒扫描，缓存单测与 runner 改动均已核对。
- AC-004：TICK-VALID，re_verified。runtime GET 纯度单测（spy coordinator 遇同步刷新即抛错）已复跑通过；`make_runtime_response` 只读已维护的 in-memory 观测；`src/backend/cbrowser/api/v1/router.py` 内已无同步 refresh 调用。
- AC-005：TICK-VALID，re_verified。离线保留容器、Native 退出优先、重试重读缓存权威、单 Profile 失败隔离改写为逐 Profile 就绪评估，相关恢复套件 75/75 已复跑通过。
- AC-006：TICK-VALID，re_verified。Compose 无 healthcheck/service_healthy、deploy 以 service_readiness_probe 在单一截止时间确认三服务 readiness、未知即未就绪，t027 套件已复跑通过。
- AC-007：TICK-VALID，re_verified。单飞快照、有界退避、重放通知不产生额外动作，缓存单测已复跑通过。
- AC-008：TICK-VALID，re_verified。观测刷新是与 UI 无关的 15 秒/并发 4 后台循环，runtime GET 纯度单测通过；无 Viewer 时循环继续运行，不新增控制循环开销。
- AC-009：TICK-VALID，re_verified。按修订契约（用户 2026-11-18 裁定）打勾含义为云端可做部分完成：稳态探针及其计数逻辑单测已复跑通过（f001 的窗口错位已修复，纪元秒窗口已锁定），Compose 无 healthcheck、deploy 走真实 readiness 探针已核对；真实 4 Profile/10 分钟验证延期至 p134，不在本轮复验内。
- AC-010：TICK-VALID，re_verified。按修订契约打勾含义为云端可做部分完成：恢复语义由状态缓存围栏/兜底对齐的单元与集成验证覆盖（已复跑），故障矩阵与采样口径由探针交付定义（f001/f003 修复后采样窗口与失败口径可信）；真实故障注入延期至 p135，不在本轮复验内。

coverage = 10/10

verdict: PASS

## Round 3 (2026-11-18T19:17:41+08:00)

- task：`t083_supervisor_state_reconciliation`
- spec：`docs/tasks/t083_supervisor_state_reconciliation/task.md`
- diff_anchor：`12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`
- target：`git diff 12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`
- round：3
- reviewed_at：2026-11-18T19:17:41+08:00

reviewed_scope: 09bf8dd004b53625

评审范围说明：确认轮。相对第 2 轮（指纹 60ba63b53a5a49b6，代码审阅 PASS）的唯一增量是测试文件 `tests/unit/test_t083_service_readiness_probe.py` 新增一个测试 `test_supervisor_not_ready_is_listed_and_fails`，以及 `progress.md` 处置表新增 t083_test_f008 的已修登记。相对 anchor 的 `git diff` 除 t083 自身增量外仍包含已合入的 t076–t082 合并提交（已在其各自 task 下审过，本轮不重复评审）。落点仓库校验：`git rev-parse --show-toplevel` 输出为工作目录本身。

## Findings

本轮新发现：0 条。

## 结论

- 生产代码零改动核实（以文件改动时间为准，不采信处置表自称）：以第 2 轮 `reviewed_at`（2026-11-18T19:10:52+08:00，即 11:10:52 UTC）为界，对全部已改动/新增文件做 mtime 扫描，晚于该时刻的只有 4 个文件——`docs/tasks/t083_supervisor_state_reconciliation/review_code.md`（第 2 轮报告本身）、`docs/tasks/t083_supervisor_state_reconciliation/review_test.md`（第 2 轮测试报告）、`tests/unit/test_t083_service_readiness_probe.py`（本次新增测试）、`docs/tasks/t083_supervisor_state_reconciliation/progress.md`（处置表登记）；无任何生产代码、脚本、迁移、schema、契约或蓝图/spec 文件在第 2 轮之后被改动。生产代码相对第 2 轮 PASS 状态零改动成立。
- 前轮 finding 复核（第 1 轮 7 条代码 finding，第 2 轮已核实消除；本轮以代码为准再确认修复仍在）：
    - t083_code_f001（important，探针 naive UTC 窗口错位）：仍消除。`scripts/steady_state_probe.py:233-235` 仍以 `int(time.time())` 取纪元秒作窗口，`:271` 报告含 `window_epoch`。
    - t083_code_f002（minor，exec-id 取错字段）：仍消除。`scripts/steady_state_probe.py:92` 仍取 `action.split(":", 1)[1].strip()`。
    - t083_code_f003（minor，docker 失败静默出全零报告）：仍消除。`scripts/steady_state_probe.py:141-154` 仍有 `DockerCommandError`，`:295` 捕获后不输出报告。
    - t083_code_f004（minor，观测刷新 N 次非批量读取）：仍消除。`src/backend/cbrowser/api/runtime_coordinator.py:836` 仍以 `list_runtime_batch` 分页取目标。
    - t083_code_f005（minor，domain 蓝图迁移号误写 0012）：仍消除。`docs/blueprint/domain.md:114` 仍写“迁移 0013”。
    - t083_code_f006（minor，release_deployment 仍称有 compose 健康检查）：仍消除。`docs/specs/release_deployment.md:20` 仍写“Compose 不再声明 Docker healthcheck”。
    - t083_code_f007（minor，core `_state_entries`/`_state_entry` 逐字重复）：仍消除。`src/backend/cbrowser/supervisor/core.py:353` 仍有 `_ensure_authoritative()`，两方法经其取值。
- 本轮唯一增量核查（新增测试 `test_supervisor_not_ready_is_listed_and_fails`，`tests/unit/test_t083_service_readiness_probe.py:139-163`）：该测试属于测试层，本代码审阅只核查其是否触及生产代码与是否存在内联 anti-pattern——结论是两者皆无。它只新增测试代码，未改 `scripts/service_readiness_probe.py`（144 行，mtime 未变）。测试本身正确：stub 以 `supervisor_not_ready` 模式返回 `{"ready": False}`，探针 `_check_all` 以 `payload.get("ready") is True` 判定（`scripts/service_readiness_probe.py` 内 Supervisor 分支），故 `services.supervisor` 为 False、`reason` 为 `services_not_ready:supervisor`、`main` 返回 1，与测试的精确全量断言一致；它跑的是真实探针逻辑加本地 stub HTTP，未 mock 被测逻辑，无恒真断言、无 skip、无弱化断言。新增前 stub 已定义 `supervisor_not_ready` 模式而无人使用，本测试将其用上，补齐了 Supervisor 未就绪分支的覆盖（即测试侧 t083_test_f008 的修复）。
- 本轮新发现：0 条。
- 未进表的提示：
    - 文件过大 / 圈复杂度：本轮无新增或改动生产代码，新增测试文件 184 行，远低于测试 600 行阈值；无新复杂度项；不进表。
    - 观察（未成 finding）：与第 2 轮相同，`src/backend/cbrowser/supervisor/core.py` 扫描恢复分支在 `if rt is None: ... return` 之后仍有一次冗余的 `if rt is not None:`，快照分页在总数恰为 200 倍数时多发一次空批请求；两者均无行为影响，本轮未动。
    - 独立复跑证据（门禁 venv，`PYTHONPATH=src/backend`，`TMPDIR` 指向 cloud-task-logs/tmp-t083，串行，未跑全量门禁）：5 个 t083 测试文件 + `test_runtime_coordinator_background_tasks.py` + `test_t027_release_controller.py` 共 89/89 通过（132.49 秒，exit 0；其中 `test_t083_service_readiness_probe.py` 6/6，含新增的 Supervisor 未就绪测试）。
    - 已核对无问题的要点：`task.md` 契约区 10 条 AC 仍全部打勾（含 AC-009/AC-010 的用户 2026-11-18 裁定处置注记原文未变）；第 2 轮的 AC 支撑（旧路由 404、快照鉴权 401、state_revision 三写路径、批量快照、30 秒兜底、Compose 无 healthcheck、deploy 真实 readiness 探针）所依赖的生产代码均未改动，故复验结论沿用。
- 总体判断：第 2 轮 PASS 状态的生产代码零改动，唯一增量是一个正确的测试加法（无生产代码变化、无内联 anti-pattern），第 1 轮 7 条 finding 的修复仍在，AC 仍为 10/10 TICK-VALID；无未解决的 critical / important，可以 PASS。
- 系统性 follow-up：无（[deploy] 真实验证已登记 p134/p135，不重复建项）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。生产代码相对第 2 轮零改动，第 2 轮复验的旧路由 404、快照鉴权 401、state_revision 三写路径、通知推送含移除名单的支撑代码均未变；相邻测试已复跑通过。
- AC-002：TICK-VALID，re_verified。生产代码零改动，批量快照与观测刷新批量取数的支撑代码未变；相邻测试已复跑通过。
- AC-003：TICK-VALID，re_verified。生产代码零改动，通知围栏、30 秒兜底、runner 脏唤醒的支撑代码未变；相邻测试已复跑通过。
- AC-004：TICK-VALID，re_verified。生产代码零改动，runtime GET 纯读已维护观测的支撑代码未变；相邻测试已复跑通过。
- AC-005：TICK-VALID，re_verified。生产代码零改动，离线保留容器、Native 退出优先、逐 Profile 就绪评估的支撑代码未变；相邻测试已复跑通过。
- AC-006：TICK-VALID，re_verified。生产代码零改动，Compose 无 healthcheck、deploy 以 service_readiness_probe 在单一截止时间确认三服务 readiness 的支撑代码未变；t027 套件已复跑通过。新增测试锁定 Supervisor 未就绪时探针返回 `services_not_ready:supervisor` 且 exit 1。
- AC-007：TICK-VALID，re_verified。生产代码零改动，单飞快照、有界退避、重放通知无额外动作的支撑代码未变；相邻测试已复跑通过。
- AC-008：TICK-VALID，re_verified。生产代码零改动，15 秒/并发 4 后台观测循环、runtime GET 纯度的支撑代码未变；相邻测试已复跑通过。
- AC-009：TICK-VALID，re_verified。按修订契约（用户 2026-11-18 裁定）打勾含义为云端可做部分完成：稳态探针及其计数逻辑单测已复跑通过（f001 的纪元秒窗口修复仍在），Compose 无 healthcheck、deploy 走真实 readiness 探针已核对；真实 4 Profile/10 分钟验证延期至 p134，不在本轮复验内。
- AC-010：TICK-VALID，re_verified。按修订契约打勾含义为云端可做部分完成：恢复语义由状态缓存围栏/兜底对齐的单元与集成验证覆盖（已复跑），故障矩阵与采样口径由探针交付定义；真实故障注入延期至 p135，不在本轮复验内。

coverage = 10/10

verdict: PASS

## Round 4 (2026-11-18T19:34:12+08:00)

- task：`t083_supervisor_state_reconciliation`
- spec：`docs/tasks/t083_supervisor_state_reconciliation/task.md`
- diff_anchor：`12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`
- target：`git diff 12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`
- round：4
- reviewed_at：2026-11-18T19:34:12+08:00

reviewed_scope: ae1172614ee9adf5

评审范围说明：确认轮（收尾手术后）。第 3 轮双轴 PASS 后，`task.py finish` 被核心资产所有权校验与「HEAD 须等于 diff_anchor」校验挡住（合 main 提交 d2d4847 带入的非 owner 任务文件相对锚点有差异、且 HEAD 已前进到该合并提交）。主会话收尾手术只动流程状态：分支 HEAD 以 reset --soft 回到 diff_anchor、非 owner 核心资产回退为锚点内容。本轮核查目标是独立验证「实现内容未变」：实现文件与第 3 轮 PASS 时逐字一致，差异仅限流程文件回退与 progress.md 记录。落点仓库校验：`git rev-parse --show-toplevel` 输出为工作目录本身。

## Findings

本轮新发现：0 条。

## 结论

- 「实现内容未变」独立核实（不采信 progress.md 自称，以下均为本轮实测）：
    - HEAD 移动轨迹：`git reflog` 显示 HEAD@{0} 为 `reset: moving to 12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`（自 d2d4847 回退），其后再无 HEAD 移动；当前 HEAD 即 diff_anchor。
    - 非 owner 文件回退完整：`git diff 12e3ac2` 对 `docs/tasks/t076_collection_queries_references_and_scale`、`docs/tasks/t078_environment_deletion_lifecycle_and_actions`、`docs/tasks/t079_ui_status_errors_and_location_semantics` 三个目录输出为空；`git status --porcelain -- docs/tasks/` 只剩 t083 自身目录的 4 个文件（progress.md、task.md、review_code.md、review_test.md），被移除的 handoff.json 与 review\_\*.md 无未跟踪残留。`docs/tasks/t081_immutable_font_resource_lifecycle/review_test.md` 当前内容亦与锚点一致、无 diff（即 finish 阻塞记录中第 15 处非 owner 核心资产，执行方在 finish 尝试时已还原，属同类流程回退，非实现改动）。
    - mtime 扫描：以第 3 轮 `reviewed_at`（2026-11-18T19:17:41+08:00）为界，其后被修改的文件只有：上述回退的 t076/t078/t079 的 progress.md 与 task.md（各 2 个）、t081 的 review_test.md、t083 的 progress.md（finish 阻塞与收尾处置两条记录）、t083 的 review_code.md（第 3 轮报告本身），以及 `.repo_template` 工具链的一个 `.pyc` 缓存（task.py 运行产物，非交付文件）。`src/`、`tests/`、`scripts/`、`schemas/`、`compose.yaml`、迁移、`docs/blueprint/`、`docs/specs/` 无任何文件在第 3 轮之后被修改——实现内容相对第 3 轮 PASS 状态零改动成立。
- 前轮 finding 复核（第 1 轮 7 条代码 finding，第 2、3 轮已核实消除；本轮逐条抽查修复仍在当前代码中）：
    - t083_code_f001（important，探针 naive UTC 窗口错位）：仍消除。`scripts/steady_state_probe.py:233-235` 仍以 `int(time.time())` 取纪元秒作 `--since`/`--until`，`:271` 报告仍含 `window_epoch`。
    - t083_code_f002（minor，exec-id 取错字段）：仍消除。`scripts/steady_state_probe.py` 的 `aggregate_events` 仍取 `action.split(":", 1)[1].strip()`（无冒号时为空串），并附根因注释。
    - t083_code_f003（minor，docker 失败静默出全零报告）：仍消除。`scripts/steady_state_probe.py:141` 仍有 `DockerCommandError`，`:154` 非零退出时抛出，`:295` 捕获后 `:299` 返回 2 且不输出报告。
    - t083_code_f004（minor，观测刷新 N 次非批量读取）：仍消除。`src/backend/cbrowser/api/runtime_coordinator.py:836` 仍以 `list_runtime_batch` 分页取目标。
    - t083_code_f005（minor，domain 蓝图迁移号误写 0012）：仍消除。`docs/blueprint/domain.md:114` 仍写「迁移 0013」。
    - t083_code_f006（minor，release_deployment 仍称有 compose 健康检查）：仍消除。`docs/specs/release_deployment.md:20` 仍写「Compose 不再声明 Docker healthcheck（t083 已删除三处 healthcheck）」。
    - t083_code_f007（minor，core 两方法逐字重复）：仍消除。`src/backend/cbrowser/supervisor/core.py:353` 仍有 `_ensure_authoritative()`，`_state_entries`/`_state_entry` 仍经其取值（调用点 `:376`、`:384`）。
    - 测试侧 t083_test_f008 的修复（新增 `test_supervisor_not_ready_is_listed_and_fails`）仍在 `tests/unit/test_t083_service_readiness_probe.py` 中，本轮复跑包含该文件且通过；该测试不触及生产代码，与第 3 轮代码轴核查一致。
- 本轮新发现：0 条。
- 未进表的提示：
    - 文件过大 / 圈复杂度：本轮无生产代码改动，前轮记录的既有规模观察（`src/backend/cbrowser/supervisor/core.py`、`src/backend/cbrowser/api/runtime_coordinator.py` 超阈值、属既有规模）仍适用；无新复杂度项；不进表。
    - 观察（未成 finding）：与前轮相同，`src/backend/cbrowser/supervisor/core.py` 扫描恢复分支在 `if rt is None: ... return` 之后仍有一次冗余的 `if rt is not None:`，快照分页在总数恰为 200 倍数时多发一次空批请求；两者均无行为影响，本轮未动。
    - 独立复跑证据（worktree 门禁 venv，`PYTHONPATH=src/backend`，TMPDIR 指向 cloud-task-logs/tmp-t083，串行，未跑全量门禁）：5 个 t083 测试文件（`test_t083_runner_state_wakeup.py`、`test_t083_service_readiness_probe.py`、`test_t083_state_cache.py`、`test_t083_state_protocol_api.py`、`test_t083_steady_state_probe.py`）加 `test_runtime_coordinator_background_tasks.py`、`test_t027_release_controller.py`，共 89/89 通过（246.33 秒，exit 0），与第 3 轮同集同结果。
    - 已核对无问题的要点：`task.md` 契约区 10 条 AC 仍全部打勾（10 个 `- [x]`、0 个未勾），AC-009/AC-010 的用户 2026-11-18 裁定处置注记原文未变；契约区 drift 仅为打勾与处置注记，与 prompt 注入的 drift diff 一致，无未经确认的 AC 变更。
- 总体判断：收尾手术只回退了流程状态（HEAD 回锚点、15 处非 owner 核心资产回锚点内容、progress.md 两条记录），实现内容相对第 3 轮 PASS 零改动且有 reflog、目录 diff 与 mtime 三路实测支撑；第 1 轮 7 条 finding 的修复逐条抽查仍在，相邻测试同集复跑 89/89 通过；无未解决的 critical / important，可以 PASS。
- 系统性 follow-up：无（[deploy] 真实验证已登记 p134/p135，不重复建项）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。实现相对第 3 轮零改动（mtime 扫描实测），旧路由 404、快照鉴权 401、state_revision 三写路径的支撑代码未变；`test_t083_state_protocol_api.py` 本轮复跑通过。
- AC-002：TICK-VALID，re_verified。批量快照与观测刷新批量取数的支撑代码未变，f004 修复抽查仍在（`list_runtime_batch` 分页）；`test_t083_state_cache.py` 与 `test_runtime_coordinator_background_tasks.py`（250 Profile 两批取数）本轮复跑通过。
- AC-003：TICK-VALID，re_verified。通知围栏、30 秒兜底、runner 脏唤醒的支撑代码未变；`test_t083_state_cache.py`、`test_t083_runner_state_wakeup.py` 本轮复跑通过。
- AC-004：TICK-VALID，re_verified。runtime GET 纯读已维护观测的支撑代码未变；`test_t083_state_protocol_api.py` 本轮复跑通过。
- AC-005：TICK-VALID，re_verified。离线保留容器、Native 退出优先、逐 Profile 就绪评估的支撑代码未变；相邻恢复套件在第 2、3 轮已复跑，本轮 t027 与后台任务套件复跑通过。
- AC-006：TICK-VALID，re_verified。Compose 无 healthcheck、deploy 以 service_readiness_probe 在单一截止时间确认三服务 readiness 的支撑代码未变，f003/f006 修复抽查仍在；`test_t083_service_readiness_probe.py`（含 Supervisor 未就绪测试）与 `test_t027_release_controller.py` 本轮复跑通过。
- AC-007：TICK-VALID，re_verified。单飞快照、有界退避、重放通知无额外动作的支撑代码未变；`test_t083_state_cache.py` 本轮复跑通过。
- AC-008：TICK-VALID，re_verified。15 秒/并发 4 后台观测循环、runtime GET 纯度的支撑代码未变；`test_runtime_coordinator_background_tasks.py` 本轮复跑通过。
- AC-009：TICK-VALID，re_verified。按修订契约（用户 2026-11-18 裁定）打勾含义为云端可做部分完成：稳态探针及其计数逻辑单测本轮复跑通过（`test_t083_steady_state_probe.py`），f001 纪元秒窗口与 f003 失败 loud fail 修复抽查仍在；真实 4 Profile/10 分钟验证延期至 p134，不在本轮复验内。
- AC-010：TICK-VALID，re_verified。按修订契约打勾含义为云端可做部分完成：恢复语义由状态缓存围栏/兜底对齐的单元与集成验证覆盖，故障矩阵与采样口径由探针交付定义（采样窗口与失败口径经 f001/f003 修复后可信，本轮抽查仍在）；真实故障注入延期至 p135，不在本轮复验内。

coverage = 10/10

verdict: PASS

## Round 5 (2026-11-18T19:40:13+08:00)

- task：`t083_supervisor_state_reconciliation`
- spec：`docs/tasks/t083_supervisor_state_reconciliation/task.md`
- diff_anchor：`12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`
- target：`git diff 12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`
- round：5
- reviewed_at：2026-11-18T19:40:13+08:00

reviewed_scope: dbbb76ad2624fe91

评审范围说明：极窄确认轮。第 4 轮双轴 PASS 后，`task.py finish` 在 Markdown 格式门禁处被拦，主会话对 5 个文件执行仓内 `md_format.py --changed` 规范化。本轮只核查三件事：格式化未改变语义；指纹范围内除 `docs/specs/storage_and_artifacts.md` 外无其他变化；AC 打勾与代码现状仍一致。落点仓库校验：`git rev-parse --show-toplevel` 输出为工作目录本身。

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核：第 1 轮 7 条代码 finding（f001–f007）在第 4 轮已逐条以 `file:line` 核实消除；本轮 mtime 扫描实测第 4 轮 `reviewed_at`（2026-11-18T19:34:12+08:00）之后，`src/`、`tests/`、`scripts/`、`schemas/`、`compose.yaml`、迁移、`docs/blueprint/` 无任何文件被修改，修复所在文件与第 4 轮核实时内容一致，7 条全部保持消除。测试侧 f008 的新增测试包含在本轮复跑集中且通过。
- 格式化语义核查（本轮核心，均为本轮实测，不采信主会话自述）：
    - 第 4 轮之后被修改的文件恰为 5 个：`docs/specs/storage_and_artifacts.md`、`docs/pending/p136_t078_concurrent_delete_request_race.md`、t083 的 `progress.md`、`review_code.md`、`review_test.md`，与所述清单一致，无第 6 个文件。其中只有 storage 规格在指纹范围内（本 task 的 `progress.md` 与 `review_*.md` 为流程文件、`docs/pending/` 整树不计指纹，与指纹口径一致）；`task.py review-status` 实测第 4 轮指纹已 stale，当前指纹即本轮 `reviewed_scope` 一行所示。
    - storage 规格与主仓 `c8563e2` 已入库版本（即当初合入本 worktree 的 main 内容）逐字比对：仅 1 处差异——第 64 行前多一个空行（规范化在小节标题前补空行）；无任何事实、数值、路径、表名或措辞变化。相对 `diff_anchor` 的 diff 内容（front matter tasks 增列 t078、`profile_deletions` 表条目、「删除数据清理语义（t078）」小节）全部来自主仓已入库的 t078 finalization，是前四轮审阅过的同一内容，非本轮新增。
    - 结论：本轮格式化为纯版式规范化，语义零变化。
- 本轮新发现：0 条。
- 未进表的提示：文件过大 / 圈复杂度同前轮记录（`src/backend/cbrowser/supervisor/core.py`、`src/backend/cbrowser/api/runtime_coordinator.py` 既有规模），本轮无代码改动，无新提示项；范围外观察：无。
- 独立复跑证据（worktree 门禁 venv，`PYTHONPATH=src/backend`，串行，未跑全量门禁）：与第 3、4 轮同集 7 个测试文件（5 个 t083 文件加 `test_runtime_coordinator_background_tasks.py`、`test_t027_release_controller.py`），共 89/89 通过（139.52 秒，exit 0）。
- 总体判断：第 4 轮后唯一变更是 5 个文件的 Markdown 规范化，指纹范围内仅 storage 规格多一个空行、语义零变化；实现与测试相对第 4 轮 PASS 状态未动，`task.md` 未被修改、10 条 AC 仍全部打勾且与现状一致；无未解决的 critical / important，可以 PASS。
- 系统性 follow-up：无（[deploy] 真实验证已登记 p134/p135，不重复建项）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。实现相对第 4 轮零改动（mtime 扫描实测）；`test_t083_state_protocol_api.py` 本轮复跑通过。
- AC-002：TICK-VALID，re_verified。批量快照与 `list_runtime_batch` 分页取数支撑代码未变；`test_t083_state_cache.py` 与 `test_runtime_coordinator_background_tasks.py` 本轮复跑通过。
- AC-003：TICK-VALID，re_verified。通知围栏、30 秒兜底、runner 脏唤醒支撑代码未变；`test_t083_state_cache.py`、`test_t083_runner_state_wakeup.py` 本轮复跑通过。
- AC-004：TICK-VALID，re_verified。runtime GET 纯读已维护观测的支撑代码未变；`test_t083_state_protocol_api.py` 本轮复跑通过。
- AC-005：TICK-VALID，re_verified。离线保留容器、Native 退出优先支撑代码未变；相邻恢复套件前轮已复跑，本轮 t027 与后台任务套件复跑通过。
- AC-006：TICK-VALID，re_verified。Compose 无 healthcheck、deploy 以 service_readiness_probe 在单一截止时间确认三服务 readiness 的支撑代码未变；`test_t083_service_readiness_probe.py` 与 `test_t027_release_controller.py` 本轮复跑通过。
- AC-007：TICK-VALID，re_verified。单飞快照、有界退避、重放通知无额外动作的支撑代码未变；`test_t083_state_cache.py` 本轮复跑通过。
- AC-008：TICK-VALID，re_verified。15 秒/并发 4 后台观测循环、runtime GET 纯度的支撑代码未变；`test_runtime_coordinator_background_tasks.py` 本轮复跑通过。
- AC-009：TICK-VALID，re_verified。按修订契约（用户 2026-11-18 裁定）打勾含义为云端可做部分完成：稳态探针及其计数逻辑单测本轮复跑通过（`test_t083_steady_state_probe.py`）；真实 4 Profile/10 分钟验证延期至 p134，不在本轮复验内。
- AC-010：TICK-VALID，re_verified。按修订契约打勾含义为云端可做部分完成：恢复语义由状态缓存围栏/兜底对齐的单元与集成验证覆盖、本轮复跑通过，故障矩阵与采样口径由探针交付定义；真实故障注入延期至 p135，不在本轮复验内。

coverage = 10/10

verdict: PASS
