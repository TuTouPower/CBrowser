# t022 测试审阅 · 第 2 轮（full review · test 路复审）

Verdict: REQUEST CHANGES

复审基线：第 1 轮报告 `review_test.md`（REQUEST CHANGES，F001–F010）+ 执行侧处置清单。方法：逐项到文件/测试原文核实（不采信 note 处置行自述），并抽跑 3 组新增测试（unit 两组、integration 一组）。除新发现 N1 外，F001–F010 的处置均真实落地；N1 为抽跑中发现的、同文件同主题的确定性失败用例，使执行侧门禁数字（unit 694 passed / 2 基线 failed）在当前工作树下不成立，故本轮不能 PASS。

## 抽跑记录（本轮实测）

| 组 | 命令范围 | 结果 |
|---|---|---|
| unit 组 1 | `test_supervisor_start_conflicts.py` + `test_supervisor_search_defaults_core.py` + `test_gateway_registry.py` + `test_gateway_disconnect_targets.py` | 15 passed，**1 failed**（即 N1） |
| unit 组 2 | `test_runtime_sse_snapshot_handoff.py` + `test_supervisor_cache_generations.py` + `test_stream_agent_lifecycle.py::test_agent_stop_releases_viewers_detached_and_tasks` + `test_runtime_profile_defaults.py::test_existing_success_marker_preserves_later_manual_choice` + `test_supervisor_docker_boundaries.py::test_x11_helper_wait_failure_still_cleans_up` + `test_runtime_agent_faults.py::test_rearm_timeout_keeps_capture_unhealthy` | 14 passed |
| integration | `test_api_search_defaults_routes.py`（2）+ `test_gateway_signaling.py` 的 handshake_timeout / oversized_envelope / inflight / gateway_restart 4 用例 | 6 passed（14.16s，含真实 10s 握手超时等待） |

## 第 2 轮逐项复核表

| # | 执行侧声称处置 | 核实证据 | 结论 |
|---|---|---|---|
| F001 | registry 新增来源键有界/淘汰单测；signaling 新增握手超时释放集成用例；note A39 表述不再高估 | `test_throttle_buckets_by_source_not_claimed_identity` 属实：throttle API 只收 source 键、声称身份轮换不产生新桶，`max_sources=3` 下 5 个新来源后断言 `len(_failures) <= 3`，抽跑通过。`test_handshake_timeout_releases_reservations` 属实：4 个静默握手被网关 10s 超时以 1008 关闭后合法注册成功，抽跑通过（真实等待）。note A39 段（note.md:44）本身只述「集成新增四条证据」，未再声称真实 Agent；Review 处置 F001 行（note.md:57）明确写明 harness 为「真实 Gateway + WS 注册客户端」。task.md AC-011 的「多个 Agent」为契约原文，真实多 Agent 拓扑已由 p024 第 (3) 项如实 deferred，不属 note 高估 | **已修**（但同文件淘汰安全性另见 N1） |
| F002 | 双订阅并发用例；负断言改事件阻塞 provider + 多次 sleep(0)；缓存根整体替换触发全量 + ready 早退不改 sidecar 两用例 | `test_concurrent_subscribers_do_not_share_snapshot_state` 存在且通过：快照订阅者与回放订阅者互不可见快照帧、其后收敛到同一 live 帧 id（并发深度注记见 N2）。交接用例已改 `provider_started`/`release_provider` 事件阻塞 + 10×`sleep(0)` 让行后再断言 publish 未完成，无固定时长负断言残留。`test_replaced_cache_root_is_a_new_identity_and_fully_validated`（整目录 move+重建→后代校验计数 >0 且 sidecar 字节变化）与 `test_ready_cache_is_not_rewritten_by_ensure`（`_binary_ready/_geoip_ready` 置真后 sidecar 字节不变）均存在且抽跑通过 | **已修** |
| F003 | API 路由层真实 uvicorn+登录+CSRF 集成用例；Supervisor core UDS 映射单测（含 get 的 status 自带 instance 二次围栏）；marker 已存在不重跑 UI 用例 | `test_api_search_defaults_routes.py` 属实且抽跑通过：真实 `create_app`+uvicorn+登录拿 cookie/CSRF，无 CSRF→403、带 `Idempotency-Key: sd-key-42`→200 且断言 coordinator 原样收到该 key、conflict→409、unavailable→503、无 coordinator→503。`test_supervisor_search_defaults_core.py` 三用例属实且通过：get 对 status 自带 instance 不符返回 None（f009 二次围栏）、retry 的 UDS 200/403→`LifecycleConflictError`/503→`RuntimeUnavailableError` 映射、调用前围栏（实例过期/无 session 时不发 UDS）。`test_existing_success_marker_preserves_later_manual_choice` 属实且通过：marker 已存在时以「任何 new_page 即断言失败」的 context 验证 UI 流程不再执行 | **已修** |
| F004 | `test_supervisor_start_conflicts.py` 三条，core 层真实抛 `LifecycleConflictError` | 三用例分别命中 `core.start_profile` 三个不同产生点并抽跑通过：session `observed_state="stopping"`→清理未完（core.py:972）、`desired_state="stopped"`→缺 running 意图（core.py:987）、`restart_blocked=True`→重试阻断（core.py:992）；经 MockTransport 真实进入 core 逻辑，非桩抛错。第 1 轮「只测 HTTP 映射」的缺口已关闭 | **已修** |
| F005 | 配额发送抽为模块级 `deliver_supervisor_quota` + 失败/成功单测 | `gateway/server.py:67` 模块级函数属实：构造 `SUPERVISOR_QUOTA` envelope、send 异常捕获后返回 False、成功 True；路由层（server.py:295）以其 False 返回 503。用例 `test_quota_delivery_failure_is_reported_not_raised` 属实且通过：坏 socket→False 不抛、健康 socket→True 且断言真实发出 1 条 | **已修** |
| F006 | docker_boundaries 新增 wait 失败仍清理；faults 新增 rearm 超时分支 | `test_x11_helper_wait_failure_still_cleans_up`：wait 抛 `DockerException`→表面化为 `DockerSandboxError` 且 `helper.removed is True`，对应 helper 的 finally remove 路径，通过。`test_rearm_timeout_keeps_capture_unhealthy`：对端静默时 `rearm_download_capture(timeout=0.3)` 抛 `TimeoutError`、`rearm_count` 不变（1）、其后恢复应答可再次成功 rearm（count=2），通过。两条子路径均已补齐 | **已修** |
| F007 | note A47/AC-014 行互引 p024 并声明本机验收仅为 ABI 静态契约 | note.md:46 A47 行已写明「AC-014 的本机验收仅为 ABI 静态契约，真实运行证据以 p024 为准」；p024 第 (2) 项明确真实 owner-loss/正常退出/keymap 顺序未执行、本机仅 wheel 源码级 ABI 核对与适配层契约测试。第 1 轮「勾选 [x] 与可测试性声明口径冲突」已由该互引消解（task.md AC-014 勾选应结合 note/p024 读，不再构成冒充已验） | **已修** |
| F008 | inflight 改条件轮询；重启重试异常收窄 | `test_inflight_handshake_reservations_bound_and_release` 已改 5s 上界条件轮询：仅 429 可重试、超时或非 429 即抛，抽跑通过。`test_agents_recover_after_gateway_restart` 重试捕获已收窄为 `aiohttp.ClientResponseError` 且状态 ∈{403,503} 才重试、其余（含 429 回归）立即抛，无裸 `except Exception` 残留，抽跑通过 | **已修** |
| F009 | stop 深度用例；Agent 入站超限 WS 层用例；Gateway pump 新增入站 envelope 预算→1009 实现 | `test_agent_stop_releases_viewers_detached_and_tasks` 属实且通过：断言 heartbeat/worker/reader/timer 任务均 done、viewer_workers 与 _detached_upstreams 清空、upstream 真被 close、重复 stop 幂等。`test_agent_oversized_envelope_closes_1009` 属实且抽跑通过。实现对应已核：`gateway/server.py:461` pump 在 JSON 解析前以同一常量 `MAX_TUNNEL_ENVELOPE_SIZE`（stream_agent/protocol.py:29，与 Agent 侧 agent.py:632 对称）对 Agent 入站帧做长度检查，超限 log 后 `ws.close(code=1009)` 并 break、仅断该连接。该实现属 AC-008「Gateway 与 Agent 对原始数据、envelope 及 WS 帧使用一致有界预算，超限按 1009 受控关闭」应有之义（第 1 轮时 Gateway 侧仅有 viewer→Agent 方向，入站方向为真实缺口，非范围外扩增） | **已修** |
| F010 | note A15 改为 1 集成用例表述；resource_policy 删除处留互引注释 | note.md:42 A15 行已改为「新增 5 单测 + 1 集成用例（另有既有用例覆盖帧级上限路径）」，与实物一致。`resource_policy.py:35-36` 删除处已留注释：「t022 A48: the unused calculate_cpu_percent helper was removed (its only callers were its own tests); the CPU-to-quota mapping below is the live one.」，与 note A48 记录互引 | **已修** |

## 新发现

### t022_test_r2_n1 · important · `test_gateway_registry.py` 内淘汰策略用例确定性失败：来源洪泛会冲掉在窗失败史，执行侧门禁数字在当前工作树不成立
- 定位：`tests/unit/test_gateway_registry.py::test_throttle_eviction_never_drops_live_reservations_or_history`（同文件、与 F001 同主题，在 F001 声称用例之后）；生产侧 `src/backend/cbrowser/gateway/registry.py` `RegistrationThrottle._evict_sources`。
- 证据（本轮两次实测，单跑与组跑结果一致）：该文件 7 用例 6 passed / 1 failed，失败点 line 243 `assert not throttle.reserve("victim", now=32.0)`——victim 先积累 2 次失败（上限 3），经 12 个不同来源洪泛触发淘汰后，再补 1 次失败本应达上限被拒，实际 reserve 返回 True，即 victim 的在窗失败史已被淘汰冲掉（`_evict_sources` 超额时按插入序 pop 最旧条目）。holder 在途计数断言通过，失败仅在失败史保留一点。
- 影响：(1) 与执行侧声称门禁「unit 694 passed / 2 基线 failed」矛盾——本用例为非基线新增失败，抽样组 1 因此为 15 passed / 1 failed。(2) F001 的「有界」一半成立（桶数有界用例通过），但淘汰策略的安全性不成立：洪泛可冲掉他源在窗失败史，与 A39「失败预算不可被绕过」的语义相冲突；note 中 code 路 f006 处置所称「活状态条目保留属设计」与本用例断言直接矛盾，两边必居其一须裁决。
- 建议：按测试编码的设计修正 `_evict_sources`（如仅淘汰过期/空条目、达上限时不接纳新来源的失败记录），或由用户裁决修改设计并同步改测试——但不得按 AGENTS.md 红线就地把测试预期改成当前实现输出而不写明理由。修复后重跑该文件及 unit 全量并更新门禁数字。

### t022_test_r2_n2 · minor（注记，不单独构成 REQUEST CHANGES） · F002 双订阅用例的并发深度为交错而非双注册同时活跃
- 证据：`RuntimeEventBroadcaster.subscribe` 为 async generator，注册（`self._subscribers.add(q)`）发生在首次 `__anext__` 执行函数体时；新用例中 replay 订阅者在 publish 之后才首次 `__anext__`，其 live 帧实为历史回放而非队列实时投递。用例对「快照不入共享历史、双订阅互不可见、收敛同一 live id」的断言有效且通过，故 F002 判已修；但「两个同时活跃订阅者并发投递」的最强语义仍只有快照订阅者一侧被实时验证。若后续收紧 AC-012 口径，可把 replay 订阅者的首次 `__anext__` 提前到 publish 之前（先取回放帧、再 publish、再断言其实时收到下一帧）即可补足，成本一条用例内调整。

## 最终 Verdict

**REQUEST CHANGES**

理由：F001–F010 十项处置逐项核实全部属实且抽跑有效（F007 以 note 互引 p024 消解口径冲突，F009 的 Gateway 入站 envelope→1009 实现与测试对应且属 AC-008 应有之义），第 1 轮 findings 本身已关闭。但抽跑发现新问题 N1：与 F001 同文件同主题的淘汰策略用例在当前工作树确定性失败，执行侧门禁数字不成立，且其断言与现实现/处置口径存在未裁决的设计冲突。N1 关闭（实现修正或经裁决的设计+测试同步修订，并重跑 unit 全量更新数字）后，test 路可转 PASS；N2 为可选补强注记，不阻塞。
