---
tid: "t026"
slug: "runtime_infrastructure_reconciliation"
title: "实现基础设施替换后的运行时自愈与信令状态收敛"
status: "done"
branch: "t026_runtime_infrastructure_reconciliation"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "c2bd696bf7b2ca869642abb3cf0ea2dc4f6382b3"
depends_on: ""
conflicts_with: "t025"
note: "来源 p034（运行时部分）；云端 Muse，真实环境执行交 t032"
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-04：从 p034（运行时部分） 聚合立项，核实基线 main@c6a9322；只创建 backlog，不 start。
- 云端范围与本地最终 t032 分离；真实环境未执行不能按通过回填。
- 2026-11-04：按三方审阅修订并实测 d029：并入 search-defaults 门禁测试修复（用户决定）；固定端点改为显式 subnet+ip_range；旧规格网络经 Stream-only 替换收敛；策略按实际规则校验，Browser 漂移 fail-closed；readiness 归 Supervisor 经容器内命令调用；传输观测不落库。
- 2026-11-04 执行（attempt 1 / exec-main-20261104-t026，base=t025 分支 c2bd696）：preflight --require-verified PASS。基线门禁（base 原样）：contract 169 passed；unit 748 passed / 1 failed / 1 skipped，唯一失败为 test_repo_hygiene 对 t025 归档 review 报告（review_code/review_test.md 含开发者本机路径且指纹未登记 allowlist——与 t024 同型自指涉，本 task AC-001 要求全绿，按双绑定登记其最终字节指纹）；integration 114 passed / 2 failed（search-defaults 必败即 AC-001 修复对象；test_ac009 协调类为已知全量负载旋转失败，t024 已记单独可复绿）；前端基线另测。
- 实施设计：新增 supervisor/address_pool.py 从可配置地址池（env CBROWSER_MEDIA_SUBNET_POOL，默认 10.251.0.0/16 按 /24 切分）分配显式 subnet，ip_range 取低半段、Gateway 固定端点取 subnet 末地址（range 外），分配/冲突/占用写入网络标签（media-subnet/media-ip-range/gateway-endpoint/media-spec）；network_policy 增加 verify（iptables-save 与渲染规格规范化比对）与 fail-closed 模式；core 在同实例分支与 API 离线分支做附着/策略/注册收敛，Stream-only 替换保留 Browser，Browser 策略漂移 fail-closed+error 上报；注册协议加 build_id 与结构化拒绝（Gateway 记录最近拒绝，Supervisor 经控制面查询）；Supervisor 新增 reconcile_all/readiness 内部端点 + 容器内 CLI（cbrowser.supervisor.control_client）；分层观测 TransportObservation 经 Supervisor 协议暴露、API 内存缓存（仿 search-defaults fence 模式）进 REST/SSE，不落库。
- 2026-11-04 实施完成并自测：AC-001 夹具按原断言修复（fixture 绑定 inst_1 使 stub 与绑定一致 + 异实例负例）；allowlist 登记 t025 两份 review 报告最终字节指纹（tasks/archive 双路径，与 t024 同模式）。实施中纠正三处设计-代码偏差：docker-py `IPAMPool` 参数为 `iprange`（原 `ip_range` 在真实 daemon 上必炸，已改）；`attach_profile_infrastructure` 为同步方法，收敛路径统一经 `asyncio.to_thread` 调用；Stream 策略规格按启动安装的真实形状构造（allowed_tcp=固定端点、udp_mux_port=会话端口），Browser 规格按快照 `config.proxy` 在容器内解析。Gateway 每轮按标签重新解析（resolve_gateway_container_id），runner 新增 network 事件订阅唤醒扫描（媒体网络名 `{prefix}-net-{profile}`）。注册拒绝码分可修复/不可修复：unsupported_version、unauthorized、identity_mismatch、invalid_payload、instance_not_bound 不替换；Stream-only 替换预算同实例窗口内 3 次。
- 新增测试：unit test_t026_address_pool / test_t026_network_policy_verify / test_t026_supervisor_convergence / test_t026_media_network_adapter / test_t026_control_endpoints / test_t026_runner_network_events / test_t026_control_client；integration test_t026_gateway_registration（真实 Gateway：结构化拒绝/build 标识/registration 端点/Gateway 不可达区分）/ test_t026_transport_api（REST 围栏 + coordinator 刷新围栏 + 重启后 unknown）；前端 useBrowserSession.transportRecovery（AC-011 四态）/ sse.transport（事件校验）；e2e tests/e2e/test_supervisor_reconciliation_e2e.py（真实 Docker，daemon+镜像门控，本机无 Docker 按用户豁免口径跳过并在文件头写明 t032 运行说明，真实环境义务归 t032 AC-009，不另立 pending）。
- 2026-11-04 Review Round 1 双路 FAIL 后修复：code 路 critical 属实——生产 DockerAdapter 缺 get_profile_containers（收敛三处调用全靠泛 catch 吞掉、readiness 对 running Profile 500），已在生产 adapter 实现（按确定名取容器 + 前缀/Profile/role 标签核验，外国容器不采纳）并补生产契约测试；连带修复：_replace_stream_only 改为先解析 Gateway 再拆 Stream（缺失只报 gateway_missing 不动现状）；Stream 容器缺失且有跟踪 session 时 _reconcile_profile 路由到 Stream-only 替换（无 session 仍保留）；Browser fail-close 失败不再预标记、观测报 browser_policy_drift_unmitigated 并下轮重试；API 离线恢复不再依赖内存 session（用扫描已核验的实例一致性，Supervisor 重启后存量沙箱可恢复附着）；readiness 策略分支守 None 容器、注册未知诊断改 registration_unverifiable；收敛 inspect/attach 失败落 degraded 观测（media_inspect_failed/media_attach_failed）；runner 网络事件流停机关闭、匹配/泵逻辑抽为可测 helper。修复中另发现 AC-004 生产缺口：cleanup_network_by_name 在 Browser 附着时拒绝删网，rebuild_network 路径在生产同样走不通——已实现 adapter.rebuild_media_network（核验端点→逐个断开→删网→按规格重建→重连 Browser/Stream、Gateway 由调用方按固定端点重附，未知端点先行拒绝），fake 同步同语义。test 路 5 条均为覆盖缺口，已补：runner 事件泵测试、readiness 逐 Profile 三态 + control_client 退出码契约、attach 回滚只撤本轮连接、未知 endpoint 拒绝清理、双 Profile 并发不串网、替换中途 recovering 采样、coordinator 新实例 unknown；删除 2 个填充测试（convergence 的 agent key 断言、e2e 的 httpx 恒真断言）。
- 2026-11-04 证据修复（finish 归档后 review_scope 变 stale，按 recovery=evidence_repair 在原 worktree 收尾）：对最终执行 commit 内容重跑双路 full review，Evidence Repair 小节追加于两份 review 报告末尾（reviewed_scope 绑定归档后指纹 cf4c2cbdec3d4182，双路 PASS、零新 finding；证据修复不计回归轮次，round 仍为 5）。两份报告 Round 1 头部 target 行的开发者本机绝对路径改为相对写法 `CBrowser_t026`：hygiene 豁免按（路径, 字节指纹）双绑定，报告追加后旧豁免失效，而 allowlist 文件本身位于 review scope 指纹之内、登记新指纹必使 scope 再次 stale，故以去除泄漏本身保持 hygiene 绿；finding 与 verdict 正文未动。新证据经 amend 并入同一执行 commit（first parent 仍为 c2bd696、commit message 不变）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-04T10:08:41+08:00 code / test 同批）

code 路 FAIL（critical 1 / important 5 / minor 2），test 路 FAIL（important 3 / minor 2）；逐条核实全部属实，已修并补测，待 Round 2 复审重签。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t026_code_f001|critical|已修|生产 DockerAdapter 无 get_profile_containers，收敛/readiness 三处调用在生产必 AttributeError（被泛 catch 吞成 warning / readiness 500），单测替身自创该方法掩盖分叉|docker_adapter.py 新增生产实现（确定名+标签核验）；test_t026_media_network_adapter 生产契约测试 2 条|
|t026_code_f002|important|已修|_replace_stream_only 先拆 Stream/网络后查 Gateway，Gateway 缺失时 Stream 已拆且不重建，违反 AC-008|core.py 改为先解析 Gateway、缺失即中止（gateway_missing、零拆动）；回归测试 test_gateway_missing_aborts_replacement_before_teardown|
|t026_code_f003|important|已修|Stream 容器缺失/停止时 _reconcile_profile 在完整性检查提前返回，永不走 Stream-only 替换；Round 2 复核发现「已停止/退出」一半未覆盖（同实例分支只报 container_exit），Round 2 补齐|core.py：缺失——Browser 在场+API 确认 desired running+围栏通过+跟踪 session 同实例时路由替换（按媒体合规决定 rebuild_network），无 session 保留；已停止/退出——同实例分支在 Browser running 且仅 Stream 非 running 时于替换预算内直接 Stream-only 替换，预算耗尽才回落 container_exit；路由测试 3 条|
|t026_code_f004|important|已修|Browser fail-close 先标记已处理再执行，失败被吞、永不重试且观测谎报已封堵|core.py：成功后才标记，失败报 browser_policy_drift_unmitigated（recovering）并下轮重试；两轮收敛测试|
|t026_code_f005|important|已修|API 离线附着恢复以内存 session 存在为前提，Supervisor 重启+API 离线时存量沙箱完全不恢复|core.py：_recover_attachment_offline 接受扫描已核验实例（标签/实例一致性在调用前已校验）；无 session 恢复测试|
|t026_code_f006|important|已修|readiness 策略分支未守 None 容器，Stream 缺失时 AttributeError 逃逸成端点 500|core.py：策略分支要求双容器非 None，否则 policy=None+policy_unverifiable 诊断（后随 test f002 补逐 Profile readiness 测试）|
|t026_code_f007|minor|已修|收敛中 inspect/attach 失败（含端点被占）不落 degraded 观测，只剩扫描层泛化 warning|core.py：inspect 失败落 media_inspect_failed、attach 失败落 media_attach_failed（failed+last_error）|
|t026_code_f008|minor|已修|网络事件 watcher 的事件流停机时从不关闭，阻塞线程无法被 cancel 打断|runner.py：网络流登记到 _close_stream_sync 一并关闭；匹配/泵抽为 media_network_event_matches/_pump_network_events 并补测|
|t026_test_f001|important|已修|网络事件触发路径（runner watcher）零测试，收敛测试全是直调 _converge_session|tests/unit/test_t026_runner_network_events.py（匹配/畸形事件/泵唤醒/停止语义 4 条）|
|t026_test_f002|important|已修|readiness 逐 Profile 校验逻辑无测试（仅 API 失败早退），control_client 在 tests 中零引用|convergence 文件补 readiness 三态（全绿 ready/注册未知 not ready/单 Profile runtime 失败隔离）；新增 test_t026_control_client.py（退出码 0/1/2 与 JSON 契约 4 条）|
|t026_test_f003|important|已修|AC-007 三个子条款无 case：attach 失败回滚保留旧连接、未知 endpoint 拒绝清理、多 Profile 并发不串网|adapter 测试补回滚（只撤本轮新连接、既有 Browser 端点保留）与未知 endpoint 拒绝；convergence 补双 Profile 并发隔离|
|t026_test_f004|minor|已修|两个填充测试不触达生产逻辑（agent key 文件 size 断言、e2e httpx 恒真断言）|已删除两条；e2e 文件随之移除无用 httpx import|
|t026_test_f005|minor|已修|AC-010「API 重启后 unknown」与 AC-004「替换期间 Viewer 恢复中」无直接断言|integration 补新 coordinator 缓存为空→fenced_transport 为 None；convergence 补替换进行中采样 transport_state==recovering|

### Round 2 (2026-11-04T10:31~10:33+08:00）

test 路 PASS（新 minor 3 条：f006 readiness 缺 Stream 守卫分支无回归测试、f007 degraded 观测两码无测试、f008 control_client 路径与 _client 构造未验——均为 Round 1 修复的覆盖缺口，已补测）。code 路 FAIL：f001/f002/f004/f005/f007 已消除，f006/f008 主体消除（残余另立 f009/f012），f003 修不彻底（容器「已停止/退出」未覆盖），新 important 3 条（f009/f010/f011）+ minor 2 条（f012/f013）——逐条核实全部属实，已修并补回归测试，待 Round 3 复审。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t026_code_f009|important|已修|_profile_readiness 的 inspect/get_profile_containers 无 catch，单个 Docker 异常使 readiness() 整体 RAISE、端点 500、诊断全失|core.py：readiness 逐 Profile 评估加隔离兜底，异常落 readiness_check_failed:<type> 的 not-ready 条目；回归测试 test_readiness_docker_failure_isolated_per_profile|
|t026_code_f010|important|已修|install_fail_closed 复用 best-effort 的 _install_fail_closed（不查 returncode），restore 失败时 helper 仍 exit 0、core 误记已封堵且永不重试|network_policy.py：显式 fail-closed 入口改严格实现（任一 family restore 失败/不可执行即 NetworkPolicyError，CLI 随之 exit 3，adapter 随之抛错触发重试）；apply 回滚路径保持 best-effort 不变；严格性测试 2 条|
|t026_code_f011|important|已修|Stream 缺失路由绕过 _stream_replacement_allowed 预算，无退避、可被自身网络事件自加速重试|core.py：缺失路由先过预算，耗尽落 stream_missing_budget_exhausted（failed）不替换；回归测试 test_missing_stream_budget_exhausted_never_replaces|
|t026_code_f012|minor|已修|watcher 登记网络流时未查 stop_event，停机竞态下新流无人关闭|runner.py：登记后若 stop 已置位立即 _close_stream_sync 并返回|
|t026_code_f013|minor|已修|rebuild_media_network 端点核验只查 prefix+managed-by，弱于 cleanup 的 role 白名单|docker_adapter.py：加 role ∈ {browser,stream,gateway} 白名单，未知 role 先行拒绝；回归测试 test_rebuild_refuses_managed_container_with_unknown_role|
|t026_test_f006|minor|已修|readiness 的 policy_unverifiable 守卫分支（Stream 缺失）无回归测试|test_readiness_missing_stream_policy_unverifiable|
|t026_test_f007|minor|已修|media_inspect_failed/media_attach_failed 两 degraded 码全仓测试零命中|test_converge_inspect_failure_records_degraded_observation / test_converge_attach_failure_records_degraded_observation|
|t026_test_f008|minor|已修|control_client 测试 handler 不查路径、_client 的 token/env/Authorization 构造未验|test_handlers_hit_the_contract_paths（路径精确断言）+ test_client_construction_uses_env_url_and_token_file（env URL+token 文件→base_url/Bearer 头）|

### Round 3 (2026-11-04T10:41~10:44+08:00）

test 路 PASS（新 minor 3 条 f009–f011）；code 路 FAIL：Round 2 六条（f003 残余/f009/f010/f011/f012/f013）经 13 条独立探针复核全部消除，但新立 important 1 条 f014——f003 回落路径的 error 锁存自锁。逐条处置如下，待 Round 4 复审。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t026_code_f014|important|已修|container_exit 回落把 session.observed_state 置 error 后，同实例块回 running 与 converge 的唯二入口都以 observed==running 为门，自锁无出口（窗口滑动修复成功后连扫两轮零收敛、transport 永停 recovering）|core.py：_reconcile_instance_observation 返回 "running"（Browser running+Agent 健康且身份匹配的权威观测）时释放同实例 session 的 error 锁存；不改变「Docker running 不得覆盖 Agent 错误观测」的保护语义（释放条件本身就是 Agent 健康）；三段回归测试 test_latched_container_exit_error_releases_on_authoritative_running|
|t026_test_f009|minor|遗留|f012 watcher 停机竞态修复无回归测试（serve_supervisor 嵌套闭包，确定性复现需先抽可测单元）；生产修复已经两轮 code review 静态核对成立|p035|
|t026_test_f010|minor|已修|f010 严格化测试只有全败/全胜桩，单 family 失败与 CLI exit 3 未断言|补 test_install_fail_closed_raises_on_single_family_failure（仅 ip6tables 失败亦抛）与 test_fail_closed_cli_exits_3_on_restore_failure|
|t026_test_f011|minor|已修|f009 readiness 隔离测试只有单个 Profile，未验同轮健康 Profile 仍被评估|补 test_readiness_failure_in_one_profile_still_evaluates_others（坏 Profile 落 readiness_check_failed、健康 Profile ready=True）|

### Round 4 (2026-11-04T10:49~10:50+08:00）

test 路 PASS（新 minor 1 条 f012，已即时修复）；code 路 FAIL：f014 本体经探针 A/B 复核已消除且保护语义未误伤，但新立 important 1 条 f015——释放锁存未同步清除终态去重集。已修，待 Round 5（末轮）复审。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t026_test_f012|minor|已修|f011 双 Profile 隔离测试中坏 Profile 排在 API 列表末位，「首个异常即短路」的退化实现会产出相同结果，判别力不足|夹具顺序改为坏 Profile 在前（test_readiness_failure_in_one_profile_still_evaluates_others），其余断言不变，复跑通过|
|t026_code_f015|important|已修|f014 释放 session 锁存时未同步清除 _terminal_observations 去重 key：同代次恢复后 Agent 再报终态会被去重吞掉、API 永远停在恢复时的 running|core.py：释放点同步 discard (pid, instance, config_version) 去重 key——该代次已证明未终结，后续终态事实必须可再上报；f014 回归测试改用生产 report_terminal_observation + 记录型 API 重写为三段（锁存+首报一次 → 释放+key 清除+收敛恢复 → 再退出必须再报，断言 container_exit 共 2 次）|

### Round 5 (2026-11-04T10:55~10:57+08:00，末轮）

双路 PASS：code 路复核 f015 已真修复（探针 A 五段全过、key 全路径一致性核查通过），test 路零新 finding。code 路新立 minor 1 条 f016（防御性硬化、当前契约下不可达），遗留登记。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t026_code_f016|minor|遗留|终态去重 key 的写入版本（fallback session 版本）与释放 discard 版本（fallback 标签版本）来源不对称；当前 API 契约下恒等、漏清不可达，改前缀清除属防御性硬化，不在本轮已审范围内变更|p036|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-012 真实 Docker 实跑按用户豁免口径跳过，义务归 t032 AC-009）
- 测试（Round 3 修复后最终复跑）：contract 169 passed；unit 816 passed / 1 skipped（基线 748/1 failed/1 skipped，t025 hygiene 经 allowlist 登记转绿；Round 1 后 +23 净新测、Round 2 后 +11、Round 3 后 +4，删 1 填充测试）；integration 125 passed / 0 failed（基线 114 passed / 2 failed：search-defaults 必败已修；test_ac009_api_supervisor_start_and_stop_coordination 为已知全量负载旋转——曾一轮 run_gates 123/1 命中、其余全量复跑均为全过，干净 base c2bd696 单独运行同 ID 亦失败，属本机基线存量、非回归）；前端 38 文件 204 passed + test:types + 生产 build 通过（基线 196，+8 新测）；e2e 文件 2 条真实 Docker 用例本机 skipped（原第 3 条为恒真填充测试，已按 test f004 删除）。
- 黑盒：testing.md 的 blackbox_verify 为真实 Docker/部署类条款；本机无 Docker daemon，按用户既定豁免口径跳过并按 pass 计，真实环境义务已按规格归 t032 AC-009（e2e 用例与运行说明已交付），不另立 pending。
- review：见下方 Review 处置（full 双路）。
- AC 判定：见 `task.md` 行内打勾（12/12）。

### 结果摘要

- 固定端点媒体网络（显式 subnet/ip_range + 标签规格 + 池分配/冲突/占用显式失败）、Gateway 标签重解析与同端点重附、稳态收敛器（附着/实际策略/注册三检，Stream-only 有界替换，Browser 漂移 fail-closed，协议级拒绝不替换，Gateway 不可达不重建）、API 离线只恢复附着、reconcile_all/readiness + 容器内 CLI、注册结构化拒绝与 build 标识、分层观测全链（Supervisor→API 内存围栏→REST/SSE→前端校验/同步）、信令首连恢复窗口（AC-011）全部落地；blueprint（supervisor/gateway/frontend/testing）与 specs（runtime_lifecycle、webrtc_remote_display）已同步，specs_index 已登记 t026。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
