Verdict: REQUEST CHANGES

# t022 code review（full review，code 路）

- 基线：`d699e5b`（t021），分支 `t022_runtime_gateway_reliability`，审阅方式：逐条对照 `task.md` 契约区 16 条 AC 与 `note.md` 实施笔记，通读全部 backend/frontend diff 与新增/改写测试。
- 验证限制：本审阅环境无 `uv`/项目依赖，未能复跑 pytest（实施侧门禁数字见 `note.md` 与 p024）；全部改动文件经 `python3 -m py_compile` 通过。以下 finding 均为静态代码证据，不依赖测试复跑。

## Findings

### t022_code_f001 — important — 缓存代次快速路径从不复验树本身，被改变的代次仍被复用（AC-012 不成立）
- 文件：`src/backend/cbrowser/supervisor/docker_adapter.py:246-279`（`_validate_cache_root`）、`:280-292`（`_cache_sidecar_matches`）
- 证据：快速路径的信任条件只有三项——内存中的 `_cache_generations` 记录、根身份（realpath/dev/ino）、以及 sidecar 与内存记录一致。`_cache_sidecar_matches` 只比对 sidecar 文件内容与内存记录，**从不重算 `_cache_tree_fingerprint(root)` 与记录比对**。封存之后对缓存树的任何改动（文件被替换为指向外部的 symlink、新增/删除条目、内容变更）只要不动 sidecar、不触发 stale 标记，就对校验完全不可见。而 `_validate_cache_paths()` 在每次 Browser 启动路径上都会被调用（`docker_adapter.py` `start_browser_container` 内，基线行附近），因此同一 Supervisor 进程生命周期内所有后续启动都会跳过逐条 `validate_safe_path` ——这正是原全量校验提供的后代 symlink/路径安全检查。sidecar 本身位于同一可写缓存根内，不构成独立信任锚。契约原文「未知或被改变的代次仍完整校验」不满足；`note.md` 中「后续启动仅验根与封存记录」的取舍与 AC-012 原文冲突，测试 `test_supervisor_cache_generations.py` 只覆盖了篡改 sidecar 与显式 stale 两条路径，未覆盖「只改树、不动 sidecar」。
- 建议：快速路径至少重算树指纹（条目集合 + symlink 目标 + 大小/内容摘要）并与封存记录比对，不一致即全量校验并重封；或明确把信任根移到缓存根之外。在此之前 AC-012 不应打勾为完全满足。

### t022_code_f002 — important — RegistrationThrottle 逐出逻辑破坏在途计数并可绕过在途上限（AC-011）
- 文件：`src/backend/cbrowser/gateway/registry.py:131-143`（`_evict_sources`）、`:145-176`（`reserve`/`release`）
- 证据：两处不一致。（1）`_evict_sources` 的 stale 循环判定为 `not values or values[-1] < cutoff`：一个刚 `reserve()` 成功的新来源，其 `_failures` 条目是 `_prune_failures` 用 `setdefault` 建的空列表，满足 `not values`，当来源总数超过 `max_sources` 时，它会在同一次 `reserve()` 调用内被逐出，刚自增的 `_inflight[key]` 一并被 pop——该握手从此不受在途计数约束，后续同源并发 `reserve()` 每次都重演此过程，`max_inflight` 对该来源失效。（2）末尾的 `while len > max_sources` 循环直接 pop 最旧的 `_failures` 条目（可能是窗口内仍有失败记录、甚至仍有在途握手的来源），且不清理对应的 `_inflight` 条目，造成失败历史被洪泛流量冲刷重置与 `_inflight` 残留计数不一致。
- 建议：逐出时排除当前正在 reserve/release 的 key 与仍有在途预留的 key；`while` 循环与 stale 循环使用同一套清理（同步 pop `_inflight`）；补一条「>max_sources 来源洪泛下在途上限仍生效、他人失败历史不被冲刷」的单测。

### t022_code_f003 — minor — 树指纹不含内容、代次号跨进程不单调（AC-012）
- 文件：`src/backend/cbrowser/supervisor/docker_adapter.py:268-273`、`:309-327`
- 证据：`_cache_tree_fingerprint` 对普通文件只取 `st_size`，同尺寸的内容替换在任何一次重封/重验中都不可见（指纹变化为空）；另外 `generation` 取自纯内存字典，进程重启后记录丢失、代次号从 1 重新封存并覆盖磁盘 sidecar，磁盘上的旧 sidecar 在新进程中从未被校验或承接（新进程首轮恰好走全量校验，掩盖了这一点）。代次号因此不具备跨重启的可比性。
- 建议：文件指纹至少纳入 mtime_ns+size（或内容 hash 抽样/全量）；新进程首轮全量校验后应与磁盘 sidecar 的代次号衔接（取 max 后递增），而非无条件重置为 1。

### t022_code_f004 — minor — Gateway 注册在 registry 落册后失败无回滚，留下无 pump 的孤儿注册
- 文件：`src/backend/cbrowser/gateway/server.py:406-437`
- 证据：节流预留本身在各路径释放无误（`try/finally` + `handshake_complete` 已逐路核查：400/401/403 返回、`ws.prepare` 异常/取消、receive 超时、报文非法、身份不符均走 `release(success=False)`，成功路径显式 `release(success=True)` 且不重复释放——此点已核查无 finding）。但 `registry.register(agent)` 之后的代码没有隔离：`close_viewers_for_session(old_agent…)` 未包异常（旧 ws 的 close 在内层有保护，viewer close 路径没有），`await ws.send_str(ack…)` 也未包异常；任一失败都会在 finally 记一次失败后把异常抛给 aiohttp，此时新 agent 已在 registry 中、ACK 未送达、消息 pump 从未启动，只能等 30s 心跳超时驱逐，期间该 profile 的 viewer/quota 路由会把这个死注册当作在线 agent。
- 建议：register 之后的收尾段失败时先 `registry.remove(pid, ws=ws)` 再关闭 ws（或将 register 推迟到 ACK 发送成功之后），并补一条注入 ACK 发送失败的集成用例。

### t022_code_f005 — minor — fail-closed 兜底用 `--noflush` 安装，已生效的 ACCEPT 规则不被清除（AC-010）
- 文件：`src/backend/cbrowser/supervisor/network_policy.py:252-264`（`_install_fail_closed`）、`:297-306`
- 证据：兜底规则集只声明链默认策略 DROP 并追加 loopback ACCEPT，却以 `--noflush` 恢复：若失败发生在第二 family，第一 family 已成功安装的目标策略 ACCEPT 规则（DNS/网关等放行项）仍留在链上先于默认 DROP 命中，受管环境并非「保持 DROP 且不放行」，只是默认策略为 DROP。新增测试 `test_network_policy_failure.py` 只断言兜底调用发生，未断言既有放行规则被清除。
- 建议：兜底改为先 flush 再装最小 DROP 集（或不用 `--noflush` 做整表替换），并在测试中断言兜底后链上无目标策略的 ACCEPT 条目。

### t022_code_f006 — minor — X11 helper 的受管标签未接入孤儿回收，进程被杀后 helper 容器永不清理（AC-003）
- 文件：`src/backend/cbrowser/supervisor/docker_adapter.py:549-577`（`setup_x11_permissions`）对照 `:337-365`（`_cleanup_orphan_helpers`）
- 证据：X11 helper 新增了 `x11_helper_labels`（role=`x11-permissions`、managed-by=supervisor），但启动期孤儿回收 `_cleanup_orphan_helpers` 只接纳 role ∈ {`cache-init`, `network-policy`} 且要求确定性名称模式；X11 helper 没有 `name=`、role 也不在回收集合内。进程内 success/失败路径靠 `finally` 的 `remove` 没问题，但 Supervisor 被 SIGKILL/宿主异常终止时留下的（已退出）helper 容器带「受管」标签却永远不会被回收，与另外两类 helper 的处理不一致。
- 建议：给 X11 helper 加确定性名称并把 `x11-permissions` 纳入 `_cleanup_orphan_helpers` 的角色与名称校验。

### t022_code_f007 — minor — X11/helper 清理与错误映射不完整：finally 中 remove 可掩盖结果，非 DockerException 不被映射
- 文件：`src/backend/cbrowser/supervisor/docker_adapter.py:562-577`
- 证据：`finally: helper.remove(force=True)` 未做任何异常隔离：remove 本身失败（daemon 抖动/NotFound 竞态）会替换掉原本的成功返回或已构造的 `DockerSandboxError`，使「权限设置成功」被报告为失败、上层收到裸 docker 异常。另外 `helper.wait(timeout=30)` 若抛非 `DockerException`（如 requests 读超时），不走 `except DockerException` 的脱敏映射，以原始异常类型上抛，与 AC-003「成功、失败和取消均有明确结果」不符。（同文件 `_install_network_policy` 是同一既有模式，X11 路径系本 task 新增/改写，故在此登记。）
- 建议：finally 中 remove 包一层 `try/except (DockerException, OSError)` 只记日志；`wait` 的异常捕获放宽到能统一映射为 `DockerSandboxError` 的集合。

### t022_code_f008 — minor — CDP rearm 无 ACK 超时，且重连路径的命令 ID 分配绕过锁（AC-001）
- 文件：`src/backend/cbrowser/runtime_agent/cdp_proxy.py:217-238`、`:145-170`、对照 `:96-107`（`send_command`）
- 证据：（1）`_rearm_pending_id` 只在断线/close 时清除，没有超时：ACK 在任意晚的时刻到达都会把 `_last_rearm_ok` 置 True，AC-001 中「超时保持不健康」实际靠「连接一直不断就一直不健康」被动成立，没有与 `rearm_download_capture(timeout=5s)` 对齐的主动超时语义。（2）重连段直接 `self._next_cmd_id += 1` 而不走 `send_command` 使用的 `self._lock`，若重连期间有并发 `send_command`，两者可能分配到同一 ID：该响应会先被 reader 的 rearm 分支消费为「匹配成功 ACK」置健康，同时又命中 `pending_cmd_futures`——未真正收到 rearm ACK 也可能报告健康。
- 建议：rearm 待 ACK 加与初始路径一致的超时清除；ID 分配统一走同一把锁/单一分配函数。

### t022_code_f009 — minor — Selkies ABI 校验依赖 getsource 子串匹配，且 signature 异常未归一为 unsupported ABI（AC-014）
- 文件：`src/backend/cbrowser/stream_agent/x11_keymap.py:53-82`
- 证据：实例属性检查用 `inspect.getsource(keyboard_cls.__init__)` 后做 `f"self.{attr}" in source` 子串匹配：若 SDK 的 `__init__` 把属性初始化委托给 helper 方法或父类，该检查会对功能兼容的 ABI 误报 unsupported 而拒启动；反之注释/字符串中出现同名文本会误放行。`inspect.signature(method)` 对无签名的可调用对象会抛 `ValueError/TypeError`，此处未捕获，会以非 RuntimeError 形式逃逸，与「不支持的结构或签名明确报告 unsupported ABI」的契约表述不一致。现有 5 条 ABI 测试用的都是源码内联定义的假类，恰好掩盖了 getsource 脆弱性。
- 建议：属性存在性改为构造后实例检查或对 `__init__` 及其调用链做 AST 级检查；signature 获取包 try 并统一转 RuntimeError。

### t022_code_f010 — minor — SSE 实时 publish 路径漏掉 search-defaults 的实例围栏（AC-016）
- 文件：`src/backend/cbrowser/api/runtime_coordinator.py:422-443`（`publish_profile_change`，关键行 `:434`）
- 证据：`runtime_views.make_runtime_response` 与 router 的快照组装都对缓存的 `search_defaults` 做了「与当前 `runtime_instance_id` 不符则丢弃」的围栏，唯独 coordinator 的实时 publish 直接 `search_defaults=self.get_search_defaults(profile_id)` 不做任何实例比对即随事件广播：实例切换后、刷新前，SSE 订阅者会收到「新实例 id + 旧实例 search-defaults 状态」的自相矛盾事件，前端据此可能对新实例显示旧实例的失败提示/重试入口。
- 建议：在 `publish_profile_change` 内复用同一围栏判断（三处抽一个小 helper，避免再次漂移）。

### t022_code_f011 — minor — search-defaults 重试是异步消费，但 API 同步刷新并返回旧状态，重试结果不可观察（AC-016）
- 文件：`src/backend/cbrowser/runtime_agent/agent.py`（`retry_search_defaults` 控制动作，写请求文件即返回 ok）、`src/backend/cbrowser/runtime_agent/runner.py:640-690`（监视器 0.5s 轮询消费）、`src/backend/cbrowser/api/runtime_coordinator.py:313-330`（`retry_search_defaults` 在 POST 返回后立即 `refresh_search_defaults` 并 publish）
- 证据：全链没有任何一环等待 runner 真正执行初始化：Supervisor 转发拿到的是「请求文件已落盘」，coordinator 随即刷新状态——此时 runner 尚未消费（轮询间隔 + 初始化最长 20s），返回前端的必然是旧的 failed 状态，前端 mutation 又把这份旧状态 `setQueryData` 回 runtime 查询缓存；runner 之后写下的新状态没有任何推送触发（状态只在下一次 GET /runtime 时被动刷新）。用户点完重试，页面持续显示失败，看不到成功，与「显示独立失败状态并允许重试、只有验证成功才记录成功」的可观察性目标有落差（没有虚报成功，故不升 important）。
- 建议：coordinator 在重试后做有界轮询刷新直到状态文件的 `request_id` 与本次请求匹配（或监视器消费后由 agent 主动上报），至少让响应/publish 反映本次重试的终态。

### t022_code_f012 — minor — 无锁文件时 X11 socket 被无条件删除，属于「无法证明过期」却未保留（AC-007）
- 文件：`src/backend/cbrowser/runtime_agent/runner.py:231-254`（`_clear_stale_x11_state`）
- 证据：活 PID/损坏/不可读锁的保留逻辑已正确实现（解析失败即抛错保留、PermissionError 保留、仅 ProcessLookupError 才继续）。但函数尾部在 `lock_path` 根本不存在时仍无条件执行 `lock_path.unlink(missing_ok=True); sock_path.unlink(missing_ok=True)`：没有锁文件就没有任何证据证明 socket 已过期，若锁被外部移除而 X server 仍活着，其 socket 会被删。AC-007 原文要求「无法证明过期的 X11 锁及 socket 保留」。
- 建议：仅在「锁可解析且进程确认不存在」这一条已证明路径上删除 socket；无锁文件时保留 socket 或另以连接探活证明过期后再删。

### t022_code_f013 — minor — A8 死信路径：隔离失败仍推进游标，且同一事件落两份死信（AC-002）
- 文件：`src/backend/cbrowser/supervisor/core.py`（`consume_disk_events` 的 REJECTED 分支与 `_quarantine_event_file`）、`src/backend/cbrowser/supervisor/event_forwarder.py`（`emit_event_with_outcome` 的 REJECTED 分支）
- 证据：（1）core 的 `_quarantine_event_file` 吞掉 OSError/PathSecurityError 只记日志，REJECTED 分支随后无条件 `_advance_event_cursor` 并在结尾持久化——隔离实际失败时，事件既未送达也未进死信，却被游标永久越过，丢失且无痕。（2）同一次 REJECTED，EventForwarder 已把自己的 spool 副本隔离进 spool/quarantine，core 又把磁盘 journal 原件隔离进 data_root/quarantine——一个事件产生两份死信副本，与「只入死信一次」的表述不符，后续人工处置时容易双份处理。
- 建议：隔离失败时不推进游标（保持待投递并告警）；明确单一死信归属（建议只保留 core 对原件的隔离，forwarder 在被 consume 路径调用时不再自隔离，或反之），并在测试中断言死信总数为 1。

### t022_code_f014 — info — messaging 的 iso_now 转发声明不完整
- 文件：`src/backend/cbrowser/stream_agent/messaging.py:8-17`
- 证据：`iso_now` 改为从 `policy_rules` 转发本身无误（单一定义已达成，`agent.py` 经 messaging 的命名导入可正常工作）；但新增的 `__all__ = ["iso_now"]` 把 messaging 真正的公开 API（`build_register_payload`、`build_heartbeat_envelope`、`tunnel_*_envelope` 等）全部排除在外，任何 `from .messaging import *` 的消费者将只拿到 `iso_now`，且该声明误导后续维护者对模块 API 的判断。
- 建议：删除 `__all__`（靠命名导入的重导出在 lint 层面可用注释/`py.typed` 惯例处理），或把 `__all__` 补全为模块的真实公开面。

### t022_code_f015 — info — runner 的已处理 request_id 集合无界增长
- 文件：`src/backend/cbrowser/runtime_agent/runner.py:122`、`:658-660`
- 证据：`_search_defaults_processed_requests` 只增不减，实例生命周期内每次合法重试（每次都是新 uuid）永久驻留。量级受人工点击限制，实际风险低，但与本 task 多处「有界状态」的口径不一致。
- 建议：改为只保留最近 N 个（如 64）或仅保留最后一个 request_id + 其结果状态。

## 已核查、无 finding 的维度

- **AC-001 主路径**：rearm 命令 ID 记录、唯一 reader 内匹配 result 才置健康、error ACK/断线保持不健康、发送侧不自等待——实现与测试（error ACK、无 ACK 两条红→绿）属实（残余问题见 f008）。
- **AC-002 分类主路径**：`classify_delivery_status`/`RETRYABLE_4XX` 与 artifact_forwarder 共用同一定义；401/403/408/429/5xx 为 UNAVAILABLE、确定性 4xx 为 REJECTED；REJECTED 推进并持久化游标、UNAVAILABLE 保持待投递、`_native_exit_instances` 标记已移入 DELIVERED 分支（诊断投递不再推进业务状态）——属实（残余问题见 f013）。
- **AC-003 权限面**：helper 的 `cap_drop=["ALL"]` + 仅 `FOWNER`、`read_only=True`、`no-new-privileges:true`、受管标签均属实，未照抄多余 CHOWN（残余问题见 f006/f007）。
- **AC-004**：扫描边界 `_parse_config_version`（bool 单独排除、非数值/缺失/小于 1 均拒）逐资源隔离、身份缺失不接纳不批量删、stream 启动 inspect 同样校验——属实，混合扫描测试断言充分。
- **AC-005**：`LifecycleConflictError` 类型映射 409（不靠文案匹配、响应体不含内部 detail）、PortPoolExhausted 503、意外 500，真实 ASGI HTTP 三态测试齐全——属实。
- **AC-006**：`_validated_runner_info` 在构造 CDP manager 前校验必需字段与类型（bool 不算 int、ws_url 前缀、值不回显、统一 StorageError）——属实；缺 `browser_ws_url` 的元数据经轮询超时后同样以脱敏错误拒启动。
- **AC-008 主路径**：三层预算单一权威（data 1MiB / envelope 2MiB+64KiB / frame 6MiB+64KiB，含关系 assert 与 `serialize_tunnel_envelope`）；Gateway viewer 路径 data 超限或 envelope 构造失败仅 1009 关闭该 viewer、集成测试证明其余 viewer 不受影响；Agent 入站 envelope 超限 1009。注：Gateway 的 agent→viewer 入站方向未做 envelope 字节数复验，仅有 frame 上限兜底——因发送侧 agent 已用同一 `serialize_tunnel_envelope` 自限，实际风险低，记录备查、不立 finding。
- **AC-009**：`close_profile_viewers_and_notify` 逐目标隔离、全部处理后才报 send_failed→503；quota 发送失败明确 503；心跳同步 `runtime_state` 且仅限已注册 session（陈旧 session 不能改写）——属实，假 ws 单测锁定两条失败路径。
- **AC-010 诊断面**：`NetworkPolicyError` 携带 family/tool/exit_code 与 ≤512 字符脱敏 stderr（控制字符清洗、超长截断），main 结构化记录——属实（兜底彻底性见 f005）。
- **AC-011 节流主路径**：双预算建模正确——成功只释放预留不清失败史、失败才记账、key 只用传输源地址不用未认证声称身份；server 侧 reserve/release 全结束路径已逐路核查无泄漏（见 f004 证据段）；Agent jitter 缩放 [50%,100%] 不超上限——属实（逐出逻辑见 f002）。集成四条证据（失败预算 429、成功不消耗、在途上限与取消释放、网关重启）真实存在且断言未削弱。
- **AC-012 SSE 交接**：快照私有化属实——快照帧不写全局历史、不消耗 live 序号、统一携带 base 点 id；回放窗口 `min-1 <= target` 边界正确（target=min-1 时回放恰好无缺口、更旧则走显式快照重建、无 provider 时发 `: resync-required`）；快照构建、base 点与订阅注册在同一把锁内与 publish 同序，并发测试锁定「publish 在快照构建期间被同序阻塞、随后紧接 base+1 送达」——无缺口、无倒退、无重复，此维度无 finding（缓存代次问题见 f001/f003）。
- **AC-013 stop 契约**：结果词汇 stopped/already_absent/superseded_noop 与 schema 同步；过期目标返回 superseded 且 complete 进 journal、重放逐字返回同一结果、新实例不受触碰；无 session 时以精确 Profile+instance 归属证据分流 already_absent/实际停止；coordinator 显式消费结果词汇、200 无合法结果视为协议失败、仅按权威观测收敛——属实。注：`stop_profile` 在 target 为 None（无 session 且无 expected）时直接返回 already_absent 而不写 journal，同 operation_id 的该类结果不具备重放记录——因结果幂等且无副作用，记录备查、不立 finding。
- **AC-015**：`set_supervisor_quota` 与协议同规（有限且 ∈[min_fps,max_fps]、越界 ValueError 且不改现值、None 仅解除），Agent 调用点捕获 ValueError 不断链；StreamAgent 删除无消费者 `close()` 后全仓无调用方残留，`stop()` 取消并 await 心跳任务、排空 viewers/detached、重复调用安全；verb 判定统一 `should_block_client_verb`、身份校验抽共享函数后三模型行为不变、messaging 的 `iso_now` 已单一定义（声明面见 f014）；`calculate_cpu_percent` 删除后全仓无引用，实际 quota 算法 `calculate_quota_normalized_percent` 的行为覆盖仍在 ResourcePolicyService 测试中——属实。
- **AC-016 围栏主链**：API（CSRF 由 profile_router 路由级依赖覆盖、coordinator 以 runtime 记录实例为围栏）→ Supervisor（session 围栏 409、不可达 503）→ Agent（runner_info 围栏 403、request_id 幂等文件）→ Runner（活 context 消费、profile/instance 再围栏、重复 request_id no-op、不重启浏览器）四级围栏齐全；关闭开关不执行（disabled 状态）、失败不写 marker、marker 首次语义与用户手动选择保留逻辑未被改动；Supervisor `get_search_defaults` 校验 health 实例与 session 一致、coordinator 刷新再校验 status 实例与 supervisor 围栏一致——属实（残余问题见 f010/f011）。
- **Gateway fence helper**：`supervisor_fence_failure` 的 `RegisteredAgent` 类型已正确从 `.registry` 导入（文件头 `from __future__ import annotations` 下亦无前向引用问题），三条 supervisor 路由改用 helper 后 503/409 语义与原内联逻辑逐项一致——无 finding。
- **TDD 纪律 / 测试替换核查**：逐项核查了任务点名的六处替换，理由均成立且断言未被削弱——(1) A39 throttle：旧单预算 `allow` 测试整体替换，文件内注明取代关系，新断言覆盖在途/成功不消耗/失败不被清除/窗口过期四面，强于旧版；(2) A45 stop fence：completed 分支仍逐字断言原 journal 结果，incomplete 分支才改断 superseded_noop，文件头注明契约更新，新实例保留断言两分支都在；coordinator 两条旧测试是 mock 改为「先回放观测上报再返回结果」、原断言不变，另新增 superseded 不收敛与无结果不收敛两条；(3) A48 quota：整体改写并注明 f_04 取代理由，新增 5 个非法值逐一断言 raises 且现值不变，地板值/恢复路径断言保留；(4) t007 unique-ids：整体删除并在原文件留取代说明，新语义由 `test_runtime_sse_snapshot_handoff.py` 4 条测试覆盖（含 base 点、隐私、窗口重建、并发交接）；(5) supervisor schema 枚举扩展：仅新增 search-defaults 两条消息的期望条目与样例，未动既有断言；(6) resource_policy 死代码测试：删除的 2 条仅覆盖已删的 `calculate_cpu_percent`，删除理由在 note 中记录。另 A39 精确退避测试靠注入 `jitter_source=lambda: 1.0` 钉满量程、期望序列未改，属合法的确定性注入而非改预期。未发现「就地把旧预期改成实现输出而无取代说明」之处——此维度无 finding。
- **范围外改动**：diff 全部文件均可对应 t022 的 AC 或收尾要求（blueprint/specs/specs_index、两份 OpenAPI 与两份 runtime schema 及导出脚本、前端生成类型、p024 真实环境债务条目）；`.repo_template/` 的 diff 为 0，未被改动；未混入 t019/t020 或其他 task 的变更——无 finding。
- **死代码/未用导入抽查**：改动文件 `py_compile` 全过；删除项（`StreamAgent.close`、`calculate_cpu_percent`、policy 的 `FORBIDDEN_PEER_PREFIXES` 类属性转发）均已核查无残留引用；`artifact_forwarder` 的 `RETRYABLE_4XX` 改为从 event_forwarder 导入后单一定义属实（残余问题仅 f014 一处声明面问题）。

## 汇总

- important：2（f001、f002）——分别直接违反 AC-012「被改变的代次仍完整校验」与 AC-011「未认证/洪泛条件下状态有界、预留可靠」，未解决前不得 PASS。
- minor：11（f003–f013）；info：2（f014、f015）。

## Round 2

双路复审在新指纹上进行（本轮结论见 review_code_r2.md）：简报编号 12 项逐项属实，含两条经独立核查撤回的误读（FORBIDDEN_PEER_PREFIXES 已删除、_query_agent_health 已走 _agent_uds_client）。

verdict: PASS

## Round 3

定向复审本报告 15 条 finding 在最终内容上的处置（全文见 review_code_r3.md）：逐项属实已修，必查测试实跑全绿，无新问题。最终结论绑定下方 reviewed_scope 指纹对应的交付内容。

verdict: PASS
reviewed_scope: 901134129b56cc06
