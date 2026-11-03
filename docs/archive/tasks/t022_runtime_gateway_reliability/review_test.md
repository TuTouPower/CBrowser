# t022 测试审阅（full review · test 路）

Verdict: REQUEST CHANGES

审阅基线：`d699e5b`，分支 `t022_runtime_gateway_reliability`。方法：`git diff d699e5b -- tests/` 全量逐文件对照生产改动与 note.md 声称；未重跑全量套件（门禁数字由实施侧提供，本报告抽查其构成，见 F010）。所有被整体替换/删除的旧测试均已与基线原文逐条比对。

## Findings

### t022_test_f001 · important · AC-011「未认证声称身份不能扩大无限状态」与超时释放路径无测试；「多个真实 Agent」表述与测试实物不符
- 定位：`tests/integration/test_gateway_signaling.py` 新增 4 用例；`tests/unit/test_gateway_registry.py::test_registration_throttle_is_bounded_per_source`。
- 证据：生产 `RegistrationThrottle` 以 transport peer 为键并有 `max_sources=1024` 淘汰（`gateway/registry.py:106-155`），实现方向正确；但全部测试只用单一来源（集成均为同一 loopback peer、单测只用 `10.0.0.1/10.0.0.2`），没有任何用例验证「声称不同 profile/instance 字符串不产生新桶」或来源数上限淘汰。AC-011 列举的「超时」结束路径亦无用例：在途预留只测了正常 close 释放（`test_inflight_handshake_reservations_bound_and_release`）与成功/失败释放，未测握手超时强制断开后的释放。
- 另：4 条集成用例走的是真实 Gateway WS 协议（aiohttp 真实监听 + `_register_agent` 真实注册握手，这一点达标、非桩），但对端是测试内的 WS 客户端而非真实 StreamAgent 实例，note.md「真实 Gateway + 多个真实 Agent」高估了实物（同一时刻只有一个注册连接，其余为并发未完成握手）。
- 建议：补一条单测以声称身份轮换断言桶数有界；补握手超时释放用例；note 表述改为「真实 Gateway + WS 注册客户端」。

### t022_test_f002 · important · AC-012 并发双订阅与缓存根身份/挂载不变性未被测到声称的强度
- 定位：`tests/unit/test_runtime_sse_snapshot_handoff.py`、`tests/unit/test_supervisor_cache_generations.py`。
- 证据：(1) SSE 侧 4 用例均为单订阅者视角：快照私有性靠「第二个订阅者事后回放看不到快照行」证明（有效），发布-快照交接靠单个 generator + provider 阻塞事件证明（有效）；但 AC 的「并发订阅…双订阅不互相挤压」没有两个同时活跃的 `subscribe()` 并发用例。(2) 交接用例用 `await asyncio.sleep(0.05)` 后断言 `publish_task` 未完成（`test_runtime_sse_snapshot_handoff.py:125`）——负时序断言，调度抖动下有 flake 隐患，应改为以锁占用事件同步。(3) 缓存代次 3 用例是白盒：直接调私有 `_validate_cache_paths()`、读 `_cache_generations`、靠 monkeypatch 计数 `validate_safe_path` 调用区分全量/快速路径——能证明代次逻辑，但 AC 声称的「根身份（realpath/dev/ino）绑定」未测（只测了 sidecar 指纹篡改与手动置 stale 标志），「新增代次不修改运行中旧挂载」无任何用例（note.md 已自认 gen-N 物理挂载未做、靠 ready 早退推论），该子句目前只有推论、无测试证据。
- 建议：补双订阅并发交接用例与根身份变更（替换目录）触发全量校验用例；挂载不变性若确由 ready 早退保证，补一条 ensure 后二次调用不写缓存的断言，否则在 AC 旁注明未验证。

### t022_test_f003 · important · AC-016 三层测试互为孤岛，且 API HTTP 路由层与「用户后续手动选择保留」零覆盖
- 定位：`tests/unit/test_api_search_defaults.py`、`tests/unit/test_supervisor_search_defaults_routes.py`、`src/frontend/.../ProfileDetailPage.searchDefaults.test.tsx`、`tests/unit/test_runtime_agent_faults.py`（Agent 段）。
- 证据：四层各自达标（coordinator 用 MockTransport、Supervisor 路由用 ASGITransport + 桩 core、前端 mock 全部 hooks、Agent 用 ASGITransport 真实 app），但没有任何一层真连接下一层：Supervisor `core.get_search_defaults/retry_search_defaults` 的真实 UDS 转发实现（`supervisor/core.py:897,918` 围栏与拒绝分支）无用例；API 侧新增的 `POST /profiles/{id}/runtime/search-defaults/retry` 路由本身（CSRF、权限、409/503 映射）无 HTTP 层用例，只有 coordinator 类方法级测试。AC-016 的「正常启动不覆盖用户后续手动选择」在全部新增测试中 grep 无对应断言；「失败后原标签页继续运行」仅由 runner retry 用例的 fake context 页数间接涉及，初始化失败路径下浏览器可用性无 runner 级用例（profile_defaults 层只证明不抛异常、记状态）。
- 缓解事实：真实端到端已如实记入 p024 第 (4) 项，未冒充已验。
- 建议：至少补一条 API 路由层用例（真 router + 桩 coordinator，断言 CSRF/409/503）与一条手动选择保留用例（marker 已存在时正常启动不重写）；core UDS 转发补桩 UDS 对端用例。

### t022_test_f004 · important · AC-005 只测了 HTTP 映射层，core 三处真实冲突产生点未被触达
- 定位：`tests/unit/test_supervisor_control_conflicts.py`。
- 证据：用例用 `SimpleNamespace` 桩 core 直接抛 `LifecycleConflictError`/`PortPoolExhaustedError`/`RuntimeError`，证明 control_server 按类型映射 409/503/500 且不泄漏文案——映射层达标。但生产中三处 `raise LifecycleConflictError`（`supervisor/core.py:967,982,987`：清理未完、缺 running 意图、重试阻断）没有任何用例真实触发；若某处日后退回普通 RuntimeError，现有测试全绿而 AC-005 实际回归。
- 建议：对三处产生点各补一条 core 级用例（可沿用 stop_teardown 的假 Docker 构造方式），或至少一条覆盖最易回归的「清理未完」路径。

### t022_test_f005 · important · AC-009「配额向 Agent 发送失败明确返回 503」无测试
- 定位：`tests/unit/test_gateway_disconnect_targets.py`；note.md A16 段声称已实现该行为。
- 证据：新文件 2 用例只覆盖 disconnect 逐目标清理（第一 viewer close 失败不跳过其余、Agent send 失败在全部清理后报 `send_failed`，均为真函数 `close_profile_viewers_and_notify` + 假 ws，强度合格）；但 note 声称的配额发送失败 503 路径在 tests/ 全量 grep 无对应新用例（命中的 503 均为既有无关用例）。心跳同步 runtime_state 用例（registry 单测）合格。
- 建议：补配额发送失败用例，或修正 note 声称范围。

### t022_test_f006 · minor · AC-003 helper「取消」路径未测；AC-001 rearm「超时」分支未测
- 证据：A9 的 3 用例覆盖成功（最小权限断言完整：cap_drop ALL/仅 FOWNER/read_only/no-new-privileges/标签/remove）、非零退出、启动失败，均断言清理；AC 文案中的「取消」（wait 被取消/超时时 finally remove）无用例。AC-001 新增 error ACK 与无 ACK 两用例为真实 loopback WS 对端、强度高（另有既有成功 rearm 用例），但无 ACK 用例是「沉默后即断言不健康」，未覆盖 rearm 超时计时器到期路径；再次断线于 pending rearm 期间亦未测。
- 建议：各补一条即可关闭；不补则 AC 旁注明子路径未验证。

### t022_test_f007 · minor · AC-014 勾选与证据等级矛盾（已如实入 p024，但 task.md 可测试性声明口径冲突）
- 证据：`test_stream_keymap_abi.py` 5 用例是对测试内自造假类的结构/签名校验，能证明适配层会拒绝残缺 ABI；但 AC-014 文案要求 owner-loss、正常退出、keymap 初始化顺序的「真实调用证据」与 text_room 在 `_spare_keycodes=None` 时按 SDK 原规则惰性初始化的行为，均无用例（惰性初始化逻辑只有 probe 脚本 `tests/fixtures/stream_probe/`，非门禁测试）。task.md 已勾选 AC-014，同时其可测试性声明写「不将静态检查或 skip 作为真实运行证据」——两者冲突。p024 第 (2) 项如实记录了该缺口，按用户豁免口径跳过计 pass，这一点不算隐瞒，但勾选状态应与 p024 互引注明。
- 建议：勾选旁注明「真实调用证据见 p024 未执行」，或将 AC-014 拆分勾选。

### t022_test_f008 · minor · 时序 flake 隐患两处（除 F002 的 sleep 外）
- 证据：(1) `test_inflight_handshake_reservations_bound_and_release` 关闭 held 连接后固定 `asyncio.sleep(0.2)` 再断言可注册——应轮询等待预留释放。(2) `test_agents_recover_after_gateway_restart` 用 20×`sleep(0.25)` + 裸 `except Exception` 重试注册：会吞掉本应失败的断言性异常（如 429 回归会被重试掩盖成慢速通过），且隐藏真实失败原因。建议收窄捕获类型并以条件轮询替代固定 sleep。其余新用例的等待多为 Event/wait_for 同步（如 faults 的 `_wait_until`、ManualClock 注入），做法正确；新用例未发现固定端口竞争（均 port 0 或 unique_port fixture；stop 幂等用例用 `ws://127.0.0.1:1` 作必失败上游，可接受）。
- skip/xfail：diff 内未新增任何 skip/xfail（grep 仅命中用例名中的 skip 一词），无滥用。

### t022_test_f009 · minor · AC-008 的 Agent 入站方向与 AC-015 的 stop 释放深度只到浅层
- 证据：AC-008 集成用例只覆盖 viewer→Gateway 方向超限 1009 且他人不受影响（真实、达标）；Agent 入站 envelope 超限 1009 只有 protocol 层序列化单测，无 WS 层用例（JSON 转义膨胀亦只在序列化层验证）。AC-015 的 stop 用例（`test_stream_agent_lifecycle.py`）只断言无 `close` 属性、重复 stop 不抛、`policy.is_running is False`，未断言后台任务确已取消/await、viewer 与 detached upstream 确已释放（既有 resume 测试覆盖 detached 过期，但非 stop 路径）；CPU 配额方面删除 `calculate_cpu_percent` 后，其替代算法 `calculate_quota_normalized_percent` 的行为覆盖在既有 ResourcePolicyService 用例中保留（已核对基线该文件其余用例未动），此项合格。
- 建议：stop 用例补 viewers/detached 清空与任务取消断言。

### t022_test_f010 · info · 指纹/证据抽查结果（3 处）
- (1) note「A55 新增 8 测试」：`test_runtime_profile_defaults.py` 新增 6（失败/超时/disabled/验证成功/runner 围栏重试/runner 过期拒绝）+ `test_runtime_agent_faults.py` 新增 2（/control 围栏幂等、/health 状态暴露）= 8，对得上。(2) note faults 计数链 12→18→22：与 A3 +2、A13 +6（含参数化函数按函数计）、A14 +4 的增量自洽；当前文件 18 个 test 函数（参数化展开后用例数更多），无矛盾。(3) note「A15 新增 5 单测 + 2 集成」：单测 5 条在 `test_stream_tunnel_budgets.py` 属实；集成只有 1 条新增（viewer 1009），另一条应为既有 `test_oversized_viewer_frame_is_rejected_at_transport`，表述易误读为 2 条新增，建议改字。note「A8 相关 23 测试」无法从 event_delivery（9 函数）+ event_cursor（5 函数）精确复算到 23（计入参数化展开与 artifact 共用分类测试后量级相符），非实锤矛盾，记录备查。
- 黑盒跳过记录：p024 已立项，四类未执行项（全套黑盒、A47 真实调用、A39 真实多 Agent 拓扑、A55 真实重试链）与本报告的证据缺口一致，记录如实。

## 被替换/删除旧测试的强度核查（逐个结论）

| 旧测试 | 处置 | 结论 |
|---|---|---|
| A39 throttle 旧 `allow` 契约（`test_gateway_registry.py`） | 整体替换为 reserve/release 双预算，文件头注明取代 | **增强**：旧断言（同源上限、异源隔离、窗口过期）在新语义下全部保留对应物，另加成功不消耗/不清失败史、在途释放。理由成立（旧语义正是 finding 本身）。 |
| A45 coordinator 两条（`test_api_runtime_coordinator.py` stop 成功、`test_runtime_coordinator_stop_paths.py` 实例 stop） | 改写 mock 时序：先回放观测上报再返回 stop 结果，注明 contract replacement | **保留**：断言未动，改动是新语义（200≠观测收敛）的必然；另新增 superseded 不收敛、无结果不收敛 2 条反面用例，整体增强。 |
| A45 `test_supervisor_stop_fence.py` 参数化 | `completed=False` 分支期望由 stopped 改为 superseded_noop，文件头注明 | **保留且更准**：completed=True 分支仍断言逐字重放；未完成分支的新期望正是 A45 的修复目标，非迁就实现——core 级另有 teardown 文件的 superseded/absent/重放 2 条独立用例佐证。 |
| A48 quota 旧用例（`test_stream_capture_policy.py`） | 整体改写并注明取代 f_04 | **增强**：旧用例接受 5 FPS（低于下限）且无效值静默，正是被报的漂移；新用例断言下限值有效、5/越界/NaN/Inf 抛 ValueError 且现值不变、None 解除。 |
| t007 unique-ids（`test_runtime_event_broadcaster_epoch.py`） | 整体删除，原位留取代说明指向新文件 | **合理取代**：旧断言（快照帧 id 唯一）与 A44 新语义（快照帧共带 live 基点 id）直接冲突，属「旧 contract 被新语义取代」；新文件以更强断言覆盖（基点一致、私有不入历史、无缺口交接、窗口重建、resync 标记）。唯 F002 的并发深度问题另计。 |
| `calculate_cpu_percent` 两条 | 随死代码删除，文件内无注释但 note.md 记录删除理由 | **可接受**：函数确无消费者（note 声称且与 A48 范围一致）；实际配额算法的独立行为覆盖仍在同文件其余用例。建议在删除处留一行注释与 note 互引（现仅 note 有记录）。 |
| supervisor schema 枚举（`test_supervisor_schema.py`） | 追加 A55 两消息 + A45 未动枚举 | **增强**：只增不删，既有消息样本全保留；StopProfileResponse 样本仍为 stopped（合法值之一），superseded_noop/absent 由 core/coordinator 用例覆盖，schema 层未单独断言新枚举值——minor 缺口，归入 F009 同类。 |

未发现借替换削弱覆盖、把旧预期就地改成实现输出（AGENTS.md 红线）的情况：每处替换均有原位或 note 的取代说明，且新断言普遍严于旧断言。

## AC 覆盖矩阵

| AC | 覆盖测试（主要） | 是否触达生产逻辑 | 结论 |
|---|---|---|---|
| AC-001 A3 | faults：reconnect 成功（既有）+ error ACK + 无 ACK | 真实 loopback WS 对端驱动真 CdpProxyManager | 充分（超时分支见 F006） |
| AC-002 A8 | event_delivery 参数化分类（401/403/408/429/5xx→unavailable、400/422→rejected）+ event_cursor 死信一次/推进持久游标/重启不重放/暂不可用保留待投递 | MockTransport 真 forwarder + 真 consume_disk_events | 充分 |
| AC-003 A9 | docker_boundaries helper 3 用例 | 假 Docker client 调真 adapter，断言完整 kwargs + 清理 | 基本充分（取消未测，F006） |
| AC-004 A10 | docker_boundaries 混合扫描（合法/缺失/畸形/无 instance/双角色） | 真 scan 逻辑 | 充分 |
| AC-005 A11 | control_conflicts 真 control app（ASGI）三态 + 不泄漏 | 映射层真、core 产生点为桩 | 部分（F004） |
| AC-006 A13 | faults 元数据：缺字段真启动拒绝 + 参数化类型错误 + 完整接受 | 真 `_validated_runner_info` 与 `run_uds_agent` | 充分 |
| AC-007 A14 | faults X11 锁 4 用例（活/死/损坏/不可读，均断言 socket 保留） | 真文件 + 真 runner 静态方法 | 充分 |
| AC-008 A15 | tunnel_budgets 5 单测 + signaling viewer 超限 1009 集成 | 单测真 protocol；集成真 Gateway WS | 基本充分（Agent 入站 WS 层未测，F009） |
| AC-009 A16 | disconnect_targets 2 用例 + registry 心跳同步 | 真抽取函数 + 假 ws；心跳真 registry | 部分（配额 503 无测，F005） |
| AC-010 A34 | network_policy_failure 双 family 失败 | monkeypatch subprocess 调真 apply_policy，断言 DROP 兜底调用序列 + 脱敏有界 stderr | 充分（teardown 清理为既有覆盖） |
| AC-011 A39 | registry 双预算单测 + signaling 4 集成（429/成功不消耗/在途释放/重启恢复） | 集成真 Gateway WS 协议；对端非真 Agent | 部分（F001） |
| AC-012 A44 | sse_snapshot_handoff 4 用例 + cache_generations 3 用例 | 真 broadcaster 并发交接（单订阅）；缓存为白盒私有方法 | 部分（F002） |
| AC-013 A45 | stop_teardown superseded/absent/重放 + stop_fence 参数化 + coordinator 不收敛 2 用例 + 旧两条改写 | 真 core + 真 coordinator（MockTransport） | 充分 |
| AC-014 A47 | keymap_abi 5 用例（假类结构/签名/属性/常量） | 只触达适配层校验函数 | 不充分（真实调用证据在 p024 未执行，F007） |
| AC-015 A48 | capture_policy quota 改写 + lifecycle stop 幂等/jitter 边界 + 既有 verb/身份/时间等价用例 | 真 policy/agent | 基本充分（stop 释放深度浅，F009） |
| AC-016 A55 | profile_defaults 6 + Agent 2 + coordinator 4 + Supervisor 路由 3 + 前端 2 | 每层真触达本层逻辑，层间全 mock | 部分（孤岛 + 路由层/手动选择缺口，F003） |

## 总评

替换纪律与多数核心路径（AC-001/002/004/006/007/010/013）的测试质量明显高于基线，真实对端（loopback WS、真 control app、真 broadcaster）使用得当，无 skip/xfail 滥用、无恒真断言。REQUEST CHANGES 的理由集中在四条 important 的覆盖缺口（F001 身份桶/超时、F003 孤岛与 API 路由层、F004 冲突产生点、F005 配额 503）——这些都是补少量针对性用例即可关闭的缺口，不涉及推翻现有测试。F002/F007 的证据等级问题已由 p024 如实兜底，补测或改勾选注记二选一即可。

## Round 2

双路复审在新指纹上进行（本轮结论见 review_test_r2.md）：F001–F010 全部关闭；唯一 REQUEST CHANGES 理由 N1 为抽跑窗口与执行侧修复落盘重叠的中间快照，非最终状态结论。

## Round 3

定向复审在最终内容上复核（全文见 review_code_r3.md）：第 1 轮 10 条 finding 处置全部属实，N1 已消解（test_gateway_registry 全文件实跑 7 passed），必查 8 文件实跑 83 passed / 0 failed，无新问题。最终结论绑定下方 reviewed_scope 指纹对应的交付内容。

verdict: PASS
reviewed_scope: 901134129b56cc06
