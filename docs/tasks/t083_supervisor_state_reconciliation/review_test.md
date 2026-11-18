# Task review t083（reviewer_focus: 测试）

- task：`t083_supervisor_state_reconciliation`
- spec：`docs/tasks/t083_supervisor_state_reconciliation/task.md`
- diff_anchor：`12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`
- target：`git diff 12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`
- round：1
- reviewed_at：2026-11-18T18:30:01+08:00

reviewed_scope: d97be31400b1f373

## Round 1 (2026-11-18T18:30:01+08:00)

reviewed_scope: d97be31400b1f373

### 评审范围说明

本轮以 `git diff 12e3ac2c3066fb732c98ba9cc0bde5fd3abef133`（工作区完整内容，含未跟踪的新交付文件）为准，其中 t083 自身改动是相对 HEAD（d2d4847）的未提交内容；锚点之后合入的 t076–t082 部分已有各自的 review 报告，本轮只在它与 t083 测试证据交叉处核对（t027 deploy harness、t082 收敛 fake API），不重审 t076–t082 的 AC。独立复跑：门禁 venv + `PYTHONPATH=src/backend`，三批串行实跑 280 个测试全部通过（新 t083 三文件 + t054/t056：35 passed；recovery/coordinator/control_auth/integration 九文件：56 passed；t026/t027/a3/docker_offload/t035/t041/t049/t055/t082/infra/fences/selkies/unprotected 十三文件：189 passed）。危险模式全量扫描：新/改测试中无恒真断言、无删/反转/注释断言、无 `.skip`/`.only`/xfail、无 `type: ignore`；无删除的测试（仅 `test_head_is_0012_and_single` 按新单头 0013 改名，`test_head_is_0013_and_single`）。

## Findings

### t083_test_f001 - service_readiness_probe verdict 逻辑零行为测试

- 严重度：important
- 锚点：AC-006（部署/回退不因进程已启动就宣布成功；未就绪、假活、挂起、不可达在声明截止时间内变为未就绪）
- 位置：`scripts/service_readiness_probe.py:63`（`_check_all`）、`:92`（`run`）、`:113`（`main`）
- 问题：新交付的部署门禁探针（`deploy.sh` 的 `wait_services_ready` 直接以其退出码决定部署成败，`scripts/deploy.sh:634-641`）没有任何行为测试。全仓对它的断言只有两处字符串存在性检查：`tests/unit/test_t083_steady_state_probe.py:115-119` 断言 `deploy.sh` 文本含 `service_readiness_probe.py`，以及 `tests/unit/test_t027_release_controller.py:451-452,956,969` 断言 fake docker 日志含 `exec -T supervisor python3 - wait 600`。grep 确认没有任何测试 import 或执行该脚本；t027 的 fake docker 只记录 exec 命令字符串，从不运行真实探针。因此探针即使改成恒返回 ready（或在合法输入上崩溃），全部测试仍全绿：未就绪/假活（status 非 ok）、挂起（HTTP 超时）、不可达（连接失败）在截止时间内返回 exit 1 + `services_not_ready:<...>` 的核心判定逻辑从未被执行过。
- 建议：给探针加直接单测，用本地 stub HTTP 服务覆盖四种情形（全 ready→exit 0；API 返回非 ok→exit 1 且列出 api；服务挂起→在截止时间内失败而非一直等；服务不可达→exit 1），并断言 `run()` 不超截止时间过多。不需要 Docker。

### t083_test_f002 - t026 隔离测试的诊断断言被弱化，且不再含失败/慢输入

- 严重度：important
- 锚点：AC-005（单 Profile 慢响应或不可达不阻断其他 Profile 健康推进）、AC-006（readiness 未就绪须显式）
- 位置：`tests/unit/test_t026_supervisor_convergence.py:818-855`（`test_readiness_one_profile_runtime_failure_isolated`）
- 问题：改写把旧断言 `diagnostics[0].startswith("runtime_unavailable")` 换成了裸真值断言 `assert by_id["prof_bad"].diagnostics`（第 852 行）。生产代码对该场景会给出明确诊断：`src/backend/cbrowser/supervisor/core.py` 的 `_profile_readiness` 在会话实例不匹配时追加 `"session_instance_mismatch"`，测试本可直接断言该值，却退化为“诊断非空”，未来返回错误但非空的诊断也会通过。同时失败输入本身也被换掉：旧测试让 `prof_bad` 的逐 Profile 读取抛 `httpx.ConnectError`，新测试只给它一个绑定了不存在实例（`inst_missing`）的正常条目——即“未就绪”而非“失败/慢”。批量协议确实取消了逐 Profile 读取，但 `_profile_readiness` 仍对每个 Profile 做 Docker/网关调用，AC-005 要求的“慢/不可达不阻断他人”在该测试里已无任何慢或不可达输入。主隔离性质（好 Profile ready、坏 Profile 不 ready、整体不 ready）仍被断言，未丢；丢的是诊断内容与失败输入。
- 建议：把第 852 行改为断言 `"session_instance_mismatch" in by_id["prof_bad"].diagnostics`；另加一个慢/失败输入（例如某 Profile 的 Docker 调用抛错或挂起），证明其他 Profile 的 readiness 仍正常产出。

### t083_test_f003 - StateChangeNotice 接收端与 runner 脏唤醒无测试

- 严重度：minor
- 锚点：AC-003（正常变更通知下 5 秒内进入协调）、AC-001（鉴权严格校验）
- 位置：`src/backend/cbrowser/supervisor/control_server.py:204-212`（`POST /supervisor/v1/state-changes`）、`src/backend/cbrowser/supervisor/runner.py:526`（`drain_dirty()`）
- 问题：通知的发送端有测试（`tests/unit/test_t083_state_protocol_api.py:181-195` 用 MockTransport 捕获 API 发出的 notice），缓存层的围栏/标脏也有测试（`tests/unit/test_t083_state_cache.py:172-208`），但接收端整条线无测试：没有测试向真实 control app POST 一个 notice（无 token 应 401、有 token 应 200 且缓存标脏），也没有测试验证 runner 循环里 `drain_dirty()` 非空会唤醒扫描。AC-003 的“5 秒内进入协调”因此只有缓存标脏这一半证据，端到端时序无人验证。
- 建议：补一个 TestClient 测试覆盖 notice 端点的 401/200 与缓存标脏；runner 侧至少补一个循环步进测试，证明脏集合触发一次扫描（或在结论中明确该时序留待 p135 本地故障矩阵验证）。

### t083_test_f004 - 缓存测试的精度缺口：批次上限、规模、等修订重放、退避边界

- 严重度：minor
- 锚点：AC-002（每轮 HTTP/SELECT 按声明批次增长；0/1/100/1000 状态）、AC-007（重复/重放通知不造成额外生命周期动作）
- 位置：`tests/unit/test_t083_state_cache.py:65-86`、`tests/unit/test_t083_state_cache.py:156-170`、`tests/unit/test_t083_state_cache.py:172-208`
- 问题：四处可加精度的缺口，均不影响已验证的主性质：① `test_snapshot_batches_under_one_epoch_become_authoritative` 的 fake fetcher 把 `(cursor, limit)` 都记下来了，但断言只验 cursor（`[c[0] for c in calls]`），从未断言传给 fetcher 的批次上限就是声明的 `MAX_STATE_BATCH`（200）；② AC-002 明确写了 0/1/100/1000 四档规模，全仓没有任何测试以 100 或 1000 个 Profile 跑快照分批或计数 SELECT（最大只做到 3 个 Profile、2 批）；③ `apply_notice` 按 `existing["state_revision"] >= state.state_revision` 丢弃重放（`src/backend/cbrowser/supervisor/state_cache.py:124-141`），但测试只覆盖了旧修订（2 < 3）被丢，未覆盖等修订重放（同修订、不同 desired_state）是否也被丢且不重新标脏——而这正是 AC-007“重复/重放”的字面情形；④ `test_failed_snapshot_backs_off_and_never_authoritative` 在失败后直接推进 31 秒，而首次失败的退避只有 2 秒（`2 ** failures`，上限 30 秒），退避边界值本身未被钉住。
- 建议：断言 fetcher 收到的 limit；补 100/1000 档的分批计数测试（可用内存 fake fetcher + 计数 SELECT 的 repository 替身）；补等修订重放用例；把退避测试改为在 +1 秒无重试、+3 秒有重试的边界断言。

### t083_test_f005 - control_auth 畸形测试在测试内复制了生产 `_state_entry` 驱动逻辑

- 严重度：minor
- 锚点：AC-001（错误严格校验）、AC-006（未就绪显式）
- 位置：`tests/unit/test_supervisor_control_auth.py:46-82`（`test_status_maps_malformed_api_payload_to_503`），对照 `src/backend/cbrowser/supervisor/core.py:353-385`
- 问题：测试为 SimpleNamespace core 手写了一个 `_state_entry`（第 70–76 行：`maintain()` → 未权威且有在途则 `sync_now()` → 未权威返回 None），与生产 `SupervisorCore._state_entry` 的驱动顺序逐行相同。真实 StateCache（畸形快照进 `_sync` 失败→不权威）与真实 status handler（None→503）确实被测到了，但“未权威时是否等待在途快照”这一生产逻辑本身只在测试的平行复制里跑，生产方法改了此处语义测试仍会通过。这是测试基础设施缺口，不应冒充覆盖。
- 建议：让该测试改用真实 `SupervisorCore` 实例（或把 `_state_entry` 的驱动逻辑抽为可直接调用的 seam），删掉测试内的平行实现。

### t083_test_f006 - offline 恢复测试用 `sync_now()` 绕过了退避门

- 严重度：minor
- 锚点：AC-005（API 断线保留既有 Browser，恢复后正常重建）
- 位置：`tests/unit/test_supervisor_recovery.py:324-433`（`test_offline_reconciliation_preserves_containers_on_api_error`），关键行第 433 行
- 问题：第一阶段 503 让缓存进入退避（`_next_attempt_at` 被抬高，`maintain()` 在此期间不会发起新同步）；第二阶段测试直接 `await core.state_cache.sync_now()` 强制同步——而 `sync_now()` 不检查 `_next_attempt_at`，直接绕过了生产 `maintain()` 会强制执行的退避门。测试注释称这是在“模拟退避到期后的调度”，但实际并未推进时间、也未走 `maintain()` 的到期判断；第二阶段的重建结论因此只在“手动绕过退避”的前提下成立。退避本身的时序由缓存单测覆盖，本测试的意图（503 不 teardown、恢复后重建会话）仍真实成立，故为 minor。
- 建议：给 core 注入可推进的时钟（缓存单测已有 `_Clock` 模式），推进到退避到期后让 `maintain()` 自行发起对齐；或在注释中明确这是时间捷径而非生产路径。

### t083_test_f007 - recovery_authority 的 fake 仍走已删除的旧路由，且条目语义与生产不一致

- 严重度：minor
- 锚点：AC-005（API 不可用时不合成退出、不 teardown）
- 位置：`tests/unit/test_recovery_authority.py:18-35`（`core_for` 的 `_entries`/`_entry`）
- 问题：该文件的 fake core 把 `_state_entries` 实现为调 fake API 的 `GET /api/v1/internal/supervisor/profiles`、把 `_state_entry` 实现为调 `GET /profiles/{pid}/runtime`——两条路由在 t083 已删除，生产 fake API 不再提供它们；且 `_entries` 在不可用时返回 `[]`，而生产 `core._state_entries` 在不权威时返回 `None`（暂停语义）。三处测试仍通过（`test_unavailable_runtime_authority_prevents_synthetic_exit` 的 503 经 `_state_entry` 返回 None 而阻止合成退出，路径真实），但该文件的“API 不可用即暂停”分支走的不是生产语义：若 `_observe_profiles` 对 `None` 的处理回归，此文件测不出来（`None` 暂停路径另由 `test_supervisor_recovery_coordinator.py` 的 `test_api_unreachable_or_error_safely_ignored` 覆盖）。
- 建议：把该文件的 fake API 改供 `/state/snapshot`（与其他迁移文件一致），或直接把 `_state_entries` stub 为返回 `None` 以覆盖暂停语义。

## 结论

- 改测方向复核：有两处“迁就实现”的改测已分别立案，不再重复计为改测问题：① `tests/unit/test_t026_supervisor_convergence.py:852` 把诊断断言弱化为裸真值（见 f002，important）；② `tests/unit/test_t027_release_controller.py` 的 compose 契约测试把“每服务有 healthcheck”反转为“无 healthcheck、无 service_healthy”（`test_compose_yaml_release_contract`），以及 deploy 断言从 `up --wait` 改为 service probe exec——这两处是契约区/ADR 040 明确要求的机制变更（删除 Compose healthcheck、改走真实 readiness 探针），有 spec 依据，不属迁就实现。其余改测均为 harness 迁移且断言语义不变：各 fake API 补 `/state/snapshot` 分支（t026/t035/t041/t049/t055/a3/docker_offload/unprotected/infra/selkies/fences/t082）、coordinator 计数断言按 RPC 路径过滤新增的 `/state-changes` 通知（`tests/unit/test_api_runtime_coordinator.py`、`tests/unit/test_runtime_coordinator_stop_paths.py`——过滤的是设计内新增流量，单条 start/stop RPC 仍精确断言为 1；重试上限计数同样排除通知，`publish_profile_change` 本身吞掉通知异常，见 `src/backend/cbrowser/api/runtime_coordinator.py:1011-1050`，不影响重试语义）、recovery 三文件的 mock core 改经 `_state_entries`/`_state_entry` 供数（side_effect 队列语义等价）、t054/t056 按 0013 单头改断言（迁移 0013 真实存在，`src/backend/migrations/versions/0013_runtime_state_revision.py`）。`tests/unit/test_t026_supervisor_convergence.py:470` 的 `api_unavailable`→`api_state_unknown` 是精确值改精确值，与生产 `readiness()` 的新口径一致，不属弱化。
- 本轮新发现：7 条（important 2 条，minor 5 条）
- 未进表的提示：① 快照端点边界（错误 token、limit 越界 422、未知 cursor）无测试，属可补 case，未立案；② `apply_notice` 会把被丢弃的旧通知也算作一次成功接触而重设权威窗口（`src/backend/cbrowser/supervisor/state_cache.py:124-141` 末尾无条件写 `_last_contact`），属代码层观察、非测试 finding，交 code reviewer 判断；③ `docs/tasks/t081_immutable_font_resource_lifecycle/review_test.md` 的 1 行改动只是 repo_hygiene 的 TMPDIR 相对路径修正，与 t083 无关；④ AC-004 的 SSE/列表纯度：t083 未改 SSE/列表组装代码（`router.py` 无相关 diff），其覆盖沿用既有测试，本轮不另立案。
- 总体判断：新 t083 测试本身可信且实跑全绿，迁移后的存量测试也全部通过，但部署门禁探针的判定逻辑零行为测试（f001）与 t026 隔离测试的诊断弱化（f002）是两处 blocking 缺口，AC-006 的打勾因此证据不足；其余 5 条为 minor。
- 系统性 follow-up：无（f001/f002 均属本 task 内补测试可解，不建议新建跨 task 项）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。快照 401、旧路由 404、最小 DTO 精确键集、state_revision 三写路径递增、notice 发布与删除名单、runtime GET 纯度（refresh 调即抛错的 spy）均实跑通过。
- AC-002：TICK-VALID，re_verified。两批 3 Profile 快照、30 秒内 maintain 零 HTTP、单飞、失败退避均实跑通过；规模/上限精度缺口见 f004（minor）。
- AC-003：TICK-VALID，re_verified。快照中途 epoch 变更不权威、旧修订丢弃、删除生效、异 epoch 通知失效、40 秒权威窗口与 30 秒兜底均实跑通过；端点与 runner 的 5 秒接线缺口见 f003（minor）。
- AC-004：TICK-VALID，re_verified。runtime GET 纯度测试实跑通过；生产 `get_font_runtime` 为 t081 的元数据只读路径，不读字体正文。
- AC-005：TICK-VALID，re_verified。API 503 不 teardown 且恢复后重建、Native 退出优先、重启封锁、单 Profile 隔离（好 Profile ready / 坏 Profile 不 ready）均实跑通过；诊断断言弱化见 f002（important，但隔离主性质仍被断言）。
- AC-006：TICK-VOID，re_verified。Supervisor readiness 端点部分已复验（API 不可用→`api_state_unknown` 未就绪、逐 Profile 隔离实跑通过），但部署门禁探针 `service_readiness_probe.py` 的判定逻辑零行为测试，仅有文件名与日志字符串断言，见 f001；打勾的部署一半无行为证据支撑。
- AC-007：TICK-VALID，re_verified。单飞快照、有界退避、旧修订丢弃、移除名单、本地写强制重同步均实跑通过；等修订重放缺口见 f004（minor）。
- AC-008：TICK-VALID，re_verified。runtime GET 纯度、compose 无 healthcheck、无 service_healthy、t082 策略收敛迁移测试均实跑通过。
- AC-009：TICK-VALID，re_verified。云端可做部分已复验：探针计数逻辑 6 个单测实跑通过，`docs/pending/p134_verify_t083_steady_state_locally.md` 已登记；真实 4 Profile/10 分钟实测按处置注记延期至本地 p134。
- AC-010：TICK-VALID，re_verified。云端可做部分已复验：缓存围栏/兜底对齐与恢复语义单测实跑通过，故障矩阵与采样口径由探针交付定义，`docs/pending/p135_verify_t083_fault_matrix_locally.md` 已登记；真实故障注入按处置注记延期至本地 p135。

coverage = re_verified / 10

verdict: FAIL

## Round 2 (2026-11-18T19:12:17+08:00)

reviewed_scope: 60ba63b53a5a49b6

### 评审范围说明

本轮以工作区完整内容为准（`git diff 12e3ac2c3066fb732c98ba9cc0bde5fd3abef133` + 磁盘上的未跟踪新交付文件）。注意：新交付文件（`tests/unit/test_t083_service_readiness_probe.py`、`tests/unit/test_t083_runner_state_wakeup.py`、`scripts/service_readiness_probe.py` 等）至今仍为未跟踪状态（`git status --short` 显示 `??`），未执行 `git add -N`，故不出现在 `git diff` 输出里；本轮对它们的核查以磁盘文件原文 + 独立复跑为准，不以 diff 有无为准。落点校验：`git rev-parse --show-toplevel` 输出精确等于工作仓库。独立复跑：门禁 venv + `PYTHONPATH=src/backend` + `TMPDIR=/home/hatch/workspace/cloud-task-logs/tmp-t083`，三批串行实跑 194 个测试全部通过（新 t083 五文件：31 passed；f002/f005/f006/f007 相关九文件：88 passed；t054/t056/t027/集成 supervisor 两文件：75 passed）。危险模式全量扫描：新/改测试中无恒真断言、无删/反转/注释断言、无 `.skip`/`.only`/xfail、无 `type: ignore`；无删除的测试（删除的断言行均为第 1 轮已裁决的旧路由/旧契约断言，见改测方向复核）。

## Findings

### t083_test_f008 - service_readiness_probe 的 Supervisor 未就绪分支零行为测试

- 严重度：minor
- 锚点：AC-006（未就绪、假活、挂起、不可达在声明截止时间内变为未就绪）
- 位置：`tests/unit/test_t083_service_readiness_probe.py:46-49`（`supervisor_not_ready` 模式分支）、对照 `scripts/service_readiness_probe.py:97-100`（`payload.get("ready") is True`）
- 问题：stub handler 已定义 `supervisor_not_ready` 模式（返回 `{"ready": False}`），但五个探针测试无一使用它，全部用 `supervisor_ready`。因此三路服务里只有 Supervisor 的 False 判定分支从未被执行过：若探针把 Supervisor 误判为恒就绪（例如改成只看 HTTP 200），全部测试仍全绿。API 的非 ok 分支已被 `test_non_ok_api_is_listed_and_fails` 覆盖，Gateway 与 API 共用 `status == "ok"` 同形判定；缺的恰是 Supervisor 特有的 `ready is True` 判定——而这正是 AC-006“假活”在 Supervisor 一侧的字面情形。探针其余四种情形（全 ready / API 非 ok / 挂起 / 不可达 / 用法错误）均已真实覆盖，故定 minor，不阻断。
- 建议：加一个用例，把 `/supervisor/v1/readiness` 设为 `supervisor_not_ready`，断言 `run()` 返回 `ready is False` 且 `services["supervisor"] is False`、reason 列出 supervisor。

## 结论

- 前轮 finding 复核（逐条以代码/测试原文 + 独立复跑核实，不采信处置表自述）：
    - t083_test_f001（important）：已消除。新建 `tests/unit/test_t083_service_readiness_probe.py`，5 个测试用本地 stub HTTP 真跑探针 `run()`/`main()`：全 ready→exit 0 且精确字典相等；API 非 ok→exit 1 且 reason 精确为 `services_not_ready:api`；挂起→3 秒截止内失败（实测 elapsed < 5.5 断言，handler 挂 10 秒）；不可达（127.0.0.1:1）→快速失败；用法错误→exit 2。独立复跑 5/5 通过。
    - t083_test_f002（important）：已消除。`tests/unit/test_t026_supervisor_convergence.py:871` 改为精确断言 `"session_instance_mismatch" in by_id["prof_bad"].diagnostics`，与生产 `src/backend/cbrowser/supervisor/core.py:1308` 的诊断值逐字一致；新增 `prof_slow`：`_FakeAdapter.inspect_media_network` 对其抛 `RuntimeError`，断言其 diagnostics 精确等于 `["readiness_check_failed:RuntimeError"]`（生产 `core.py:1288` 兜底分支），同时好 Profile 仍 ready、整体不 ready。独立复跑 t026 全文件通过。
    - t083_test_f003（minor）：已消除。新建 `tests/unit/test_t083_runner_state_wakeup.py`：notice 端点用真实 `create_control_app` + 真实 `SupervisorStateCache`，无 token→401 且缓存不脏、有 token→200 且 `drain_dirty() == {"p1"}`，`_never_fetch` 保证不走快照；runner 侧抽出 `_scan_due`（`src/backend/cbrowser/supervisor/runner.py:54-65`，真实循环已调用）并测脏唤醒立即扫描、无脏时 29 秒不扫、30 秒兜底扫。5 秒端到端时序本身仍无测试（只测了扫描决策函数），按第 1 轮建议的“至少补一个循环步进测试”已满足，剩余时序留待 p135 本地故障矩阵验证。
    - t083_test_f004（minor）：已消除。缓存测试四项补齐：`tests/unit/test_t083_state_cache.py:78` 断言每批 limit 均为 `MAX_STATE_BATCH`；新增 `test_snapshot_scales_by_declared_batch`（100/1000 参数化，fetch 次数精确等于 `ceil(total/200)` 且每批 limit 均为 200）；等修订重放用例（同修订 4、desired 改回 running，状态不变且 `drain_dirty() == set()`）；退避边界改为 +1 秒无重试、+3 秒（首次失败退避 2 秒）`has_inflight`。独立复跑缓存文件 11/11 通过。
    - t083_test_f005（minor）：已消除。`tests/unit/test_supervisor_control_auth.py:46-82` 改用真实 `SupervisorCore.__new__(SupervisorCore)` + 真实 `SupervisorStateCache` + 真实 `_fetch`（经 `StateSnapshot.model_validate`），畸形快照→缓存不权威→status 503；测试内手写 `_state_entry` 平行实现已删除。独立复跑 control_auth 全文件通过。
    - t083_test_f006（minor）：已消除。`tests/unit/test_supervisor_recovery.py` 给 `core.state_cache` 注入可推进时钟，503 失败后推进 3 秒（超过首次失败 2 秒退避），由生产 `maintain()` 自行发起对齐（断言 `has_inflight`），`sync_now()` 仅等待在途对齐完成；之后 `scan_and_reconcile_existing()` 重建会话。独立复跑 recovery 全文件通过。
    - t083_test_f007（minor）：已消除。`tests/unit/test_recovery_authority.py` 的 fake 改走真实快照校验：`_entries` 调 `/api/v1/internal/supervisor/state/snapshot`、非 200 返回 `None`（暂停语义）、200 则经 `StateSnapshot.model_validate` + 真实 `_entry_dict` 投影；旧路由 `/profiles` 与 `/profiles/{id}/runtime` 已无引用。独立复跑 recovery_authority 全文件通过。
    - 另核：观测 sweep 批量选择测试（`tests/unit/test_runtime_coordinator_background_tasks.py:80-152`，250 Profile）真实跑 `_observation_refresh_loop`：fake service 只提供 `list_runtime_batch`（无逐 Profile 读取可走），断言精确两次 fetch `[(None, 200), ("p199", 200)]`，且刷新集合精确等于 running + 已绑定实例的 Profile。独立复跑通过。
- 改测方向复核：无新的“迁就实现”改测。本轮涉及的改测均有契约依据或语义等价：t027 的 `--wait`/`--wait-timeout`/healthcheck 断言改写是 ADR 040 明确要求的机制变更（删 Compose healthcheck、改走真实 readiness 探针），第 1 轮已裁决；t026 的 `api_unavailable`→`api_state_unknown` 是精确值改精确值，与生产 readiness 新口径一致；其余为 fake API 补 snapshot 分支、计数断言过滤设计内新增通知流量，单条 start/stop 仍精确断言。
- 本轮新发现：1 条（minor 1 条，important/critical 0 条）
- 未进表的提示：① 0 Profile 空快照未测试（AC-002 列出 0/1/100/1000 四档；100/1000 已补，1 档由各单 Profile 用例覆盖，0 档空快照无用例——生产 `_sync` 对空列表无特殊分支，属可补 case，不立案）；② 第 1 轮结论提示的 `apply_notice` 行为仍在：`src/backend/cbrowser/supervisor/state_cache.py:149` 对被丢弃的旧/重放通知也无条件重设 `_last_contact`（延长权威窗口），属代码层观察、非测试 finding，交 code 轴判断，本轮不重复立案；③ `test_t083_service_readiness_probe.py:46-49` 的 `supervisor_not_ready` 模式除 f008 外无其他死分支；④ 新交付文件仍为未跟踪状态，`git diff` 看不到它们——下轮派审前实施方应对新文件执行 `git add -N`。
- 总体判断：第 1 轮 2 条 important 与 5 条 minor 均已真实修复并独立复跑通过；本轮仅 1 条 minor（Supervisor 未就绪分支缺一个用例），AC 逐条均有真实测试支撑。PASS。
- 系统性 follow-up：无（f008 属本 task 内补一个用例可解，不建议新建跨 task 项）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。快照 401、旧路由 404、最小 DTO 精确键集、state_revision 三写路径递增、notice 端点 401/200 与缓存标脏、runtime GET 纯度均独立复跑通过。
- AC-002：TICK-VALID，re_verified。两批 3 Profile 快照且每批 limit 均为 MAX_STATE_BATCH、100/1000 档 fetch 次数精确等于 ceil(total/200)、30 秒内 maintain 零 HTTP、单飞、退避边界 +1/+3 秒均独立复跑通过；250 Profile 观测 sweep 两批取数已复跑通过。
- AC-003：TICK-VALID，re_verified。快照中途 epoch 变更不权威、旧/等修订重放丢弃且不重标脏、删除生效、异 epoch 通知失效、40 秒权威窗口与 30 秒兜底、notice 端点与 \_scan_due 脏唤醒均独立复跑通过。
- AC-004：TICK-VALID，re_verified。runtime GET 纯度测试独立复跑通过；生产 get_font_runtime 为 t081 的元数据只读路径，不读字体正文。
- AC-005：TICK-VALID，re_verified。API 503 不 teardown 且退避到期后 maintain() 自行对齐重建、Native 退出优先、重启封锁、单 Profile 隔离（精确诊断 session_instance_mismatch 与 readiness_check_failed:RuntimeError，好 Profile 仍 ready）均独立复跑通过。
- AC-006：TICK-VALID，re_verified。第 1 轮 blocker 已消除：service_readiness_probe 全 ready/非 ok/挂起/不可达/用法错误 5 个 stub HTTP 行为测试独立复跑通过；Supervisor readiness 端点与逐 Profile 隔离亦复跑通过；Supervisor 未就绪分支缺用例见 f008（minor）。
- AC-007：TICK-VALID，re_verified。单飞快照、有界退避、旧修订与等修订重放丢弃、移除名单、本地写强制重同步均独立复跑通过。
- AC-008：TICK-VALID，re_verified。runtime GET 纯度、compose 无 healthcheck、无 service_healthy、t082 策略收敛迁移测试均独立复跑通过。
- AC-009：TICK-VALID，re_verified。云端可做部分已复验：稳态探针计数逻辑单测独立复跑通过，p134 已登记；真实 4 Profile/10 分钟实测按处置注记延期至本地 p134。
- AC-010：TICK-VALID，re_verified。云端可做部分已复验：缓存围栏/兜底对齐与恢复语义单测独立复跑通过，故障矩阵与采样口径由探针交付定义，p135 已登记；真实故障注入按处置注记延期至本地 p135。

coverage = 10/10

verdict: PASS

## Round 3 (2026-11-18T19:15:46+08:00)

reviewed_scope: 09bf8dd004b53625

### 评审范围说明

确认轮：相对第 2 轮的唯一增量是 `tests/unit/test_t083_service_readiness_probe.py` 新增 `test_supervisor_not_ready_is_listed_and_fails`、`progress.md` 处置表新增 t083_test_f008 已修登记，以及新文件已 `git add -N`（`git status --short` 现显示 `A tests/unit/test_t083_service_readiness_probe.py`，`git diff 12e3ac2c3066fb732c98ba9cc0bde5fd3abef133` 已能看到该文件完整内容，不再依赖磁盘未跟踪文件核查）。落点校验：`git rev-parse --show-toplevel`（在工作仓库内执行）输出精确等于工作仓库。独立复跑：门禁 venv + `PYTHONPATH=src/backend` + `TMPDIR` 指向云端任务日志临时目录，串行实跑探针文件 6/6 通过，另复跑相邻 t083 四文件（state_cache / runner_state_wakeup / steady_state_probe / state_protocol_api）26/26 通过。危险模式扫描（仅本轮增量）：新测试无恒真断言、无删/反转/注释断言、无 `.skip`/`.only`、无 `type: ignore`、无 mock 被测逻辑（真实探针脚本经 importlib 加载、真实 stub HTTP 服务在系统边界供数）。

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核（以代码/测试原文 + 独立复跑核实，不采信处置表自述）：
    - t083_test_f008（minor）：已消除。新测试 `test_supervisor_not_ready_is_listed_and_fails`（`tests/unit/test_t083_service_readiness_probe.py:133-153`）真实驱动了 stub 的 `supervisor_not_ready` 分支（第 46-49 行，`/supervisor/v1/readiness` 返回 `{"ready": False}`），探针生产判定 `payload.get("ready") is True`（`scripts/service_readiness_probe.py:97-100`）据此判 Supervisor 未就绪；测试精确断言 `result["ready"] is False`、`result["reason"] == "services_not_ready:supervisor"`、services 字典精确等于 `{"api": True, "gateway": True, "supervisor": False}`，且 `probe.main([... "wait", "2"]) == 1`。断言为精确值而非真值/存在性：若探针把 Supervisor 误判为恒就绪，该测试必失败（`ready` 为 True、`reason` 为 None）。独立复跑该文件 6/6 通过，其中新测试单项通过；相邻四文件 26/26 通过，无回归。
- 改测方向复核：无。本轮唯一测试改动是新增一个用例，未修改任何既有测试或断言。
- 本轮新发现：0 条
- 未进表的提示：无（第 2 轮提示的 0 Profile 空快照与 `apply_notice` 重设 `_last_contact` 两项仍属既往观察，本轮增量未触及，不重复立案）。
- 总体判断：第 2 轮唯一的 minor finding f008 已真实修复并独立复跑通过；其余 AC 证据沿用第 2 轮复验结论，本轮无新问题。PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。沿用第 2 轮复验：快照 401、旧路由 404、最小 DTO 精确键集、notice 端点 401/200 与缓存标脏、runtime GET 纯度均独立复跑通过；本轮增量未触及该 AC。
- AC-002：TICK-VALID，re_verified。沿用第 2 轮复验：分批 limit 均为 MAX_STATE_BATCH、100/1000 档 fetch 次数精确、30 秒内 maintain 零 HTTP、退避边界均独立复跑通过；本轮增量未触及该 AC。
- AC-003：TICK-VALID，re_verified。沿用第 2 轮复验：旧/等修订重放丢弃、删除生效、异 epoch 通知失效、notice 端点与 \_scan_due 脏唤醒均独立复跑通过；本轮增量未触及该 AC。
- AC-004：TICK-VALID，re_verified。沿用第 2 轮复验：runtime GET 纯度测试独立复跑通过；本轮增量未触及该 AC。
- AC-005：TICK-VALID，re_verified。沿用第 2 轮复验：API 503 不 teardown 且退避到期后 maintain() 自行对齐重建、单 Profile 隔离精确诊断均独立复跑通过；本轮增量未触及该 AC。
- AC-006：TICK-VALID，re_verified。本轮独立复跑：service_readiness_probe 6/6 通过，其中新增的 Supervisor 未就绪测试真实驱动 stub 的 supervisor_not_ready 分支，精确断言 reason 为 services_not_ready:supervisor 且 main 返回 1；f008 已消除。
- AC-007：TICK-VALID，re_verified。沿用第 2 轮复验：单飞快照、有界退避、旧/等修订重放丢弃、移除名单均独立复跑通过；本轮增量未触及该 AC。
- AC-008：TICK-VALID，re_verified。沿用第 2 轮复验：runtime GET 纯度、compose 无 healthcheck、t082 策略收敛迁移测试均独立复跑通过；本轮增量未触及该 AC。
- AC-009：TICK-VALID，re_verified。沿用第 2 轮复验：云端可做部分（稳态探针计数逻辑单测）独立复跑通过，p134 已登记；真实 4 Profile/10 分钟实测按处置注记延期至本地 p134。
- AC-010：TICK-VALID，re_verified。沿用第 2 轮复验：云端可做部分（缓存围栏/兜底对齐与恢复语义单测）独立复跑通过，p135 已登记；真实故障注入按处置注记延期至本地 p135。

coverage = 10/10

verdict: PASS

## Round 4 (2026-11-18T19:28:47+08:00)

reviewed_scope: ae1172614ee9adf5

### 评审范围说明

确认轮。第 3 轮（指纹 09bf8dd004b53625）之后工作区仅有流程性变更：分支 HEAD 以 reset --soft 回到 diff_anchor（当前 HEAD 即锚点提交 12e3ac2）；合 main 带入的 14 个非本 task 任务文件回退为锚点内容；progress.md 增加 finish 阻塞与主会话收尾处置两条记录（`docs/tasks/t083_supervisor_state_reconciliation/progress.md:39-40`）。本轮独立核实：`git diff 12e3ac2c3066fb732c98ba9cc0bde5fd3abef133 -- docs/tasks/` 仅剩本 task 自身四文件（progress.md、review_code.md、review_test.md、task.md），t076/t078/t079 三个目录相对锚点 diff 为 0 行，与回退声明一致；reset --soft 不改工作区、回退仅作用于上述 14 个文件，实现与测试文件未被手术触及，本轮抽查的关键行内容与第 1–3 轮引用逐字一致（见前轮 finding 复核）。落点校验：`git rev-parse --show-toplevel` 输出精确等于工作仓库；`git status` 无未跟踪文件，全部交付内容均在 diff 内。独立复跑：门禁 venv + `PYTHONPATH=src/backend`，串行实跑六个文件 66 个测试全部通过（t083 五文件：service_readiness_probe / runner_state_wakeup / state_cache / steady_state_probe / state_protocol_api；加 t026 收敛文件）。危险模式扫描（t083 五文件 + t026）：无 `.skip`/`.only`/xfail、无恒真断言、无 `type: ignore`。

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核（以代码/测试原文 + 独立复跑核实，不采信处置表自述）：
    - t083_test_f001（important）：保持消除。`tests/unit/test_t083_service_readiness_probe.py` 6 个行为测试本轮复跑全过（全 ready / API 非 ok / Supervisor 未就绪 / 挂起 / 不可达 / 用法错误），探针判定逻辑被真实执行。
    - t083_test_f002（important）：保持消除。`tests/unit/test_t026_supervisor_convergence.py:871` 精确断言 `"session_instance_mismatch" in by_id["prof_bad"].diagnostics`，与生产 `src/backend/cbrowser/supervisor/core.py` 中 `diagnostics.append("session_instance_mismatch")` 逐字一致；prof_slow 的 diagnostics 精确等于 `["readiness_check_failed:RuntimeError"]`；t026 全文件本轮复跑通过。
    - t083_test_f003（minor）：保持消除。`tests/unit/test_t083_runner_state_wakeup.py` 两测试（notice 端点 401/200 且缓存标脏、脏集合唤醒扫描）本轮复跑通过。
    - t083_test_f004–f007（minor）：保持消除。所涉 state_cache 测试（批次 limit、100/1000 规模、等修订重放、退避边界）本轮随 state_cache 文件复跑通过；control_auth / recovery / recovery_authority 三文件的修复内容未被手术触及，沿用第 2 轮复跑结论。
    - t083_test_f008（minor）：保持消除。`test_supervisor_not_ready_is_listed_and_fails`（`tests/unit/test_t083_service_readiness_probe.py:121`）本轮复跑通过，stub 的 supervisor_not_ready 分支被真实驱动。
- 改测方向复核：无。本轮无任何测试改动（手术未触及测试文件）。
- 本轮新发现：0 条
- 未进表的提示：无。第 1–2 轮留下的两项既往观察（0 Profile 空快照未测、`apply_notice` 对被丢弃通知重设 `_last_contact`）本轮内容未变，不重复立案。
- 总体判断：第 3 轮后仅有流程性回退与记录增补，实现与测试内容经独立核实未变，关键修复抽查复跑全绿；无未解决 critical / important。PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。本轮复跑：notice 端点 401/200 与缓存标脏（runner_state_wakeup）、快照协议与最小 DTO（state_protocol_api）均通过；内容较第 3 轮未变。
- AC-002：TICK-VALID，re_verified。本轮复跑 state_cache 全文件通过：分批 limit 均为 MAX_STATE_BATCH、100/1000 档 fetch 次数精确、30 秒内 maintain 零 HTTP、退避边界均成立。
- AC-003：TICK-VALID，re_verified。本轮复跑：旧/等修订重放丢弃、notice 端点标脏与脏唤醒（runner_state_wakeup + state_cache）均通过。
- AC-004：TICK-VALID，re_verified。沿用第 2 轮复验的 runtime GET 纯度证据；本轮 state_protocol_api 复跑通过且相关内容未变。
- AC-005：TICK-VALID，re_verified。本轮复跑 t026 全文件通过：单 Profile 隔离精确诊断（session_instance_mismatch / readiness_check_failed:RuntimeError）、好 Profile 仍 ready；API 503 不 teardown 与恢复重建沿用第 2 轮复跑结论，内容未变。
- AC-006：TICK-VALID，re_verified。本轮复跑 service_readiness_probe 6/6 通过（含 Supervisor 未就绪分支），第 1 轮 blocker 的证据基础（探针行为测试）在当前内容下仍成立。
- AC-007：TICK-VALID，re_verified。本轮复跑 state_cache 通过：单飞、有界退避、旧/等修订重放丢弃、移除名单均成立。
- AC-008：TICK-VALID，re_verified。本轮核实 compose.yaml 无 healthcheck 定义（仅注释说明移除原因）；runtime GET 纯度与 t082 策略收敛证据沿用第 2 轮复跑结论，内容未变。
- AC-009：TICK-VALID，re_verified。本轮复跑 steady_state_probe 计数逻辑单测通过，p134 已登记；真实 4 Profile/10 分钟实测按处置注记延期至本地 p134。
- AC-010：TICK-VALID，re_verified。云端可做部分（缓存围栏/兜底对齐）本轮随 state_cache 复跑通过，故障矩阵与采样口径由探针交付定义，p135 已登记；真实故障注入按处置注记延期至本地 p135。

coverage = 10/10

verdict: PASS

## Round 5 (2026-11-18T19:36:29+08:00)

reviewed_scope: dbbb76ad2624fe91

### 评审范围说明

极窄确认轮。第 4 轮双轴 PASS（指纹 ae1172614ee9adf5）之后，工作区唯一变更是主会话跑 finish 时被 Markdown 格式门禁拦下、对 5 个文件执行仓内 `md_format.py --changed` 规范化格式化。本轮独立核实该声明：以格式化批次时刻（2026-11-18 19:35:53+08:00）为界全仓扫描（排除 .git/.scratch），mtime 落在批次内的文件恰为声明的 5 个——`docs/specs/storage_and_artifacts.md`、`docs/pending/p136_t078_concurrent_delete_request_race.md`、本 task 的 `progress.md`、`review_code.md`、`review_test.md`，无第六个文件。其中仅 `docs/specs/storage_and_artifacts.md` 在审阅指纹范围内（本 task 的 progress.md 与 review\_\*.md 为流程文件不计指纹，docs/pending/ 整树不计指纹），与新指纹 dbbb76ad2624fe91 的成因一致。落点校验：`git rev-parse --show-toplevel` 输出精确等于工作仓库。关键测试文件未被触及：t083 五个测试文件 mtime 均不晚于 2026-11-18T19:13:15+08:00（早于第 4 轮审阅时刻），本轮抽查的 `tests/unit/test_t083_service_readiness_probe.py` 与 `tests/unit/test_t083_state_cache.py` 以门禁 venv + `PYTHONPATH=src/backend` 串行复跑 17/17 通过（探针 6/6、缓存 11/11，与第 2–4 轮计数一致）。危险模式扫描：本轮增量为纯文档格式化，无任何测试文件改动，无可扫描的新测试内容。

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核：第 1–3 轮 finding（t083_test_f001–f008）已在第 2–4 轮逐条核实消除；本轮增量未触及任何实现或测试文件，全部保持消除，无需重复抽查代码行。第 4 轮的「实现与测试内容未变」结论在本轮继续成立，且范围更窄：本轮连流程性回退都没有，只有格式化。
- 改测方向复核：无。本轮无任何测试改动。
- 本轮新发现：0 条
- 未进表的提示：无。格式化后逐项核对：① `docs/specs/storage_and_artifacts.md` 全文已读——与测试、门禁、验收有关的表述（§2.6 逐文件 SHA-256 校验、§3 验收清单含真实容器 E2E 测试名 `test_p014_file_input_opens_chooser_with_uploads_bookmark`、AC-002 仍诚实未勾）与前四轮审阅过的语义一致，事实、数值与路径未被格式化改动；文件内引用均可达（`scripts/storage_migration.py` 存在、上述 E2E 测试名在 `tests/e2e/test_browser_runtime_e2e.py` 中存在）；该文件相对锚点的增量仍只是 t078 回填三处（front matter tasks 增 t078、`profile_deletions` 表行、删除数据清理语义一节），无内容增删。② `docs/pending/p136_t078_concurrent_delete_request_race.md` 格式化后 front matter 与正文完好（pid p136、status todo、现象描述在位）。③ `docs/tasks/t083_supervisor_state_reconciliation/task.md` 未被格式化批次触及（mtime 2026-11-18T19:05:21+08:00），AC 打勾复数实测 10/10、无未勾 AC；AC-009 处置注记（task.md:45，跟踪项 p134）与 AC-010 处置注记（task.md:47，跟踪项 p135）原文与契约区注入文本逐字一致。④ progress.md:39-40 的 finish 阻塞与收尾处置记录仍在位。
- 总体判断：第 4 轮 PASS 后唯一变更为 5 个 Markdown 文件的规范化格式化，其中仅 spec 一件在指纹范围内且语义经逐项核对未变；测试证据基础（关键文件内容与复跑结果）与第 4 轮一致。无未解决 critical / important。PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。支撑文件（state_protocol_api、runner_state_wakeup 等）经全仓 mtime 扫描证明自第 4 轮独立复跑后未变，第 4 轮复验结论在当前内容下继续成立。
- AC-002：TICK-VALID，re_verified。本轮独立复跑 `tests/unit/test_t083_state_cache.py` 11/11 通过：分批 limit 均为 MAX_STATE_BATCH、100/1000 档 fetch 次数精确、30 秒内 maintain 零 HTTP、退避边界均成立；文件 mtime 2026-11-18T18:39:57+08:00，未被格式化触及。
- AC-003：TICK-VALID，re_verified。支撑文件（state_cache、runner_state_wakeup）内容未变（mtime 均早于第 4 轮），本轮随 state_cache 复跑再次确认重放丢弃与兜底对齐；第 4 轮 notice 端点与脏唤醒复跑结论继续成立。
- AC-004：TICK-VALID，re_verified。runtime GET 纯度相关测试与生产文件未被本轮增量触及，第 2–4 轮复验结论继续成立。
- AC-005：TICK-VALID，re_verified。t026 等支撑文件内容未变（第 4 轮全文件复跑通过），本轮增量未触及该 AC 的任何证据。
- AC-006：TICK-VALID，re_verified。本轮独立复跑 `tests/unit/test_t083_service_readiness_probe.py` 6/6 通过（含 Supervisor 未就绪分支精确断言 reason 为 services_not_ready:supervisor）；文件 mtime 2026-11-18T19:13:15+08:00，为第 3 轮 f008 修复后的版本，未被格式化触及。
- AC-007：TICK-VALID，re_verified。本轮随 state_cache 复跑再次确认单飞、有界退避、旧/等修订重放丢弃、移除名单；其余证据文件未变。
- AC-008：TICK-VALID，re_verified。compose.yaml 未被格式化批次触及（不在批次文件清单内），无 healthcheck 定义的第 4 轮核实结论继续成立；runtime GET 纯度证据未变。
- AC-009：TICK-VALID，re_verified。云端可做部分（steady_state_probe 计数逻辑单测）文件未变、第 4 轮复跑结论继续成立，p134 已登记；task.md:45 处置注记原文未变，真实 4 Profile/10 分钟实测仍按裁定延期至本地 p134。
- AC-010：TICK-VALID，re_verified。云端可做部分（缓存围栏/兜底对齐）本轮随 state_cache 复跑通过，p135 已登记；task.md:47 处置注记原文未变，真实故障注入仍按裁定延期至本地 p135。

coverage = 10/10

verdict: PASS
