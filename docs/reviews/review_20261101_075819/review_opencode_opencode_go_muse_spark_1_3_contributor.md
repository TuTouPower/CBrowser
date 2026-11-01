# 累计审阅报告（t001–t007）——独立第四路（全量）

- 本路真实模型：`opencode-go/muse-spark-1.3-contributor`（provider：`opencode-go`），effort=high
- 基线：`3c8bdbc55570e85aaeb6365a3d512da9c0ce180c`（t001 实施前 diff_anchor）
- 目标：`78c95638c8ceb5d84c286994eee82146d7ddddd6`（t007 已合入 main）
- 范围：t001–t007 全部累计改动（507 条）及跨组件交互，一份报告覆盖，不逐 task 拆分。累计差异与清单只作索引，结论全部来自本路静态核验。
- 方法：只读静态审阅。未运行构建/测试/浏览器/Docker/网络请求；未读 `.env`、`data/`、凭据。引用测试只称“已有测试覆盖/证据记载”，不声称本路运行通过。关键改动用 `git diff base..target -- <file>` 核对基线增量。
- 实际覆盖：507 条变化全部过了一遍。生产代码逐文件读（行范围见 Appendix）；`tests/unit|integration|e2e|fixtures` 逐文件核对（大 E2E 文件核关键用例与断言形状）；`docs/archive/tasks/t001–t007` 的 task.md 全读、note.md 读 t007 头（过程日志不作保证）；`docs/findings/d001–d024` 全读结论/影响/现状；`docs/specs/*`、`docs/blueprint/*`、`docs/pending/todo/*` 全读；`docs/v2_architecture_plan.md` 核豁免与修订节；`docs/handoff.md`、`docs/tasks_index.json`、`docs/guides/*`、`docs/reviews/review_v2_scope*`、`review_local_benchmark*` 已读；归档 spikes 以历史追溯口径审查（10 份 report.md 读，`code/*` 探针列历史未逐行审）；`docs/archive/specs/chrome_external_tabs.md`、`docs/archive/pending/*`、`docs/archive/handoff.md`、`docs/archive/tasks_index.json` 已读。
- 覆盖缺口（未谎称已验证）：`docs/archive/spikes/*/code/*` 约 90 个探针脚本只列历史未逐行审；`docs/archive/tasks/*/note.md`（除 t007 头外）未逐行读；`tests/e2e` 单文件超千行者只核关键用例与断言形状；`schemas/openapi/cbrowser_v1.json`（2465 行）只核生成头与一致性单测；`src/frontend/src/i18n.tsx`（659 行）只核 git diff 新增段。除此之外无未读文件。

## 一、安全视角

**S1 · Medium · `src/backend/cbrowser/api/v1/auth_router.py:65` + `src/backend/cbrowser/auth/service.py:97-134` + `src/backend/cbrowser/auth/rate_limiter.py:9-39`**

- 证据：登录限速键为 `request.client.host`；内存滑动窗口，无 XFF 处理；`TestClient` 集成测试证实 5 次后 429（`test_auth_api.py:88-99`）。
- 触发：经 Caddy 反向代理后所有来源共享同一 `client.host`，任一来源 5 次失败即全局 429；多副本/重启计数丢失。
- 影响：单用户试错锁死全员登录（可用性）；分布式猜解仍各 IP 5 次/分钟。
- 修复：Caddy 透传受信 `X-Forwarded-For` 且 API 仅信任配置代理段取值，或改账户级限速；文档注明重启丢失。
- 置信度：80。

**S2 · Medium · `src/backend/cbrowser/supervisor/docker_adapter.py:354-379`（`prepare_profile_directories` `os.chmod(d, 0o777)`；`engine_cache`/`geoip_cache` 258–259 行同）**

- 证据：profile/runtime/events/exchange/x11/pulse 宿主目录统一 `0o777`；x11 事后经 helper 容器 `chmod 1777` 补 sticky（390–404 行），但 profile/runtime/events 保持 `0777` 非 sticky。
- 触发：宿主多用户或目录被挂进其他容器时任意 UID 可读写他 Profile 目录。
- 影响：与“严格 Profile 隔离”叙事冲突；单机单用户基线实际风险低，属纵深缺陷。
- 修复：profile/runtime/events/exchange 收紧为 `0700/0750`，仅 x11 保 `1777`；engine-cache `0o777` 同理复核（只读挂载不需要宿主可写）。
- 置信度：70。

**S3 · Low · `src/backend/cbrowser/api/internal_supervisor.py:21-30`、`internal_gateway.py:20-29`、`src/backend/cbrowser/supervisor/control_server.py:46-48`、`src/backend/cbrowser/gateway/config.py:11-19`**

- 证据：四处服务间 token 只校验长度 ≥32 字节，无文件权限（0600）校验；仅 Selkies token 挂载在 `docker_adapter.py:812-816` 强制 0600（且有单测 `test_start_stream_container_enforces_0600_permissions`）。
- 触发：部署者把 token 文件放 `0644` 不告警，宿主其他用户可读。
- 修复：读取时 `stat` 检查 `(mode & 0o077) == 0`，否则拒绝启动。
- 置信度：85。

**S4 · Low · `src/backend/cbrowser/api/v1/auth_router.py:80-95`（`secure=True` 硬编码）**

- 证据：两个 Cookie 均 `Secure`；直连 API `http://` 时浏览器不发送，E2E 经 Caddy `https://127.0.0.1`（`gateway_probe/caddyfile.py:13-15` + `tls internal`）故不受影响。
- 修复：文档注明必须经 Caddy，或以环境开关显式允许本地 http（默认保持 Secure）。
- 置信度：90。

**S5 · Low · `src/backend/cbrowser/gateway/server.py:421-422`（Agent→Viewer 隧道原文转发）+ `src/frontend/.../adapter.ts:345-423`**

- 证据：Agent `tunnel msg` 原样 `send_str` 给页面；页面对 `rtc_config`/`ice_restart` 直接 `setRemoteDescription`/`createAnswer`。
- 触发：同 Profile Stream 容器被攻破可向页面下发恶意 `iceServers`/offer。
- 影响：Stream 本就持有该 Profile 媒体面，属同信任域；服务端已对 `conn_id` 归属校验（server.py:407-418），页面侧保持现状并记录信任假设即可。
- 置信度：65。

**S6 · 已登记 p006（首稿误报为新发现，现纠正）· Medium · `src/backend/cbrowser/supervisor/core.py:492-497`（`agent_secret.txt` mode `0o644` 写在挂进 Browser 的 `runtime/<profile>/`）**

- 证据：`atomic_write_text(agent_secret, token, mode=0o644)`；Browser 容器以 rw 挂载整个 `runtime` 目录（`docker_adapter.py:681`）；`docs/pending/todo/p006` 原文已登记此问题（t007 范围外观察，归属 t005/t006 既有）。
- 触发：Browser 内不可信网页沙箱可读 Stream 的 Gateway 注册凭证，冒充该实例向 Gateway 注册（仍需 API 绑定一致，过期实例会被 1008 拒绝，但同实例窗口内可劫持/干扰）。
- 现状：仍存在，未修复；handoff §四亦点名 t012 处理。首稿 S-新增判级不变（Medium），归因改为“已登记 p006 确认仍存在”，置信度 75。

**S7 · Info · `config/docker/stream_runtime/entrypoint.sh:95-99` 独立启动回退把 controller token 导出进环境变量**

- 仅无挂载凭证的独立/测试路径；受管路径不走此分支；Stream 独立 PID namespace。记录即可。置信度：80。

**通过项**：Argon2id+随机盐、会话仅存 SHA-256（`service.py:139-157`）、自动化 token `cbat_` 单次明文+库内哈希+审计脱敏、Gateway 三级校验（Origin→会话→running，`server.py:475-512`）、Agent HMAC 实例绑定且过期实例 1008 拒绝不覆盖（`server.py:316-329`，另有 `test_supervisor_selkies_token_isolation.py` 负例）、Selkies 双 token tmpfs 0600 + 每实例新文件名（`selkies_tokens.py:40-57`，单测覆盖）、SDP/TURN 全文不进日志（`_sanitize_packet`/`_sanitize_url`，单测 `test_stream_ice_security.py` canary 断言）、`PathValidator` 固定目录防 symlink 别名（单测 `test_supervisor_profile_path_ownership.py`）、CDP 仅 loopback（`runner.py` + `agent.py:248`）、SDK 异常脱敏（`runner.py:748-750`）、launch_args 白名单过滤（`security.py:52-94`，单测覆盖）、拨号 DNS 在受管容器内解析且只放行明确 IP:port（`docker_adapter.py:109-147`）。与 `security.md` 一致，未发现绕过。

## 二、正确性视角

**C1 · Medium · `src/backend/cbrowser/gateway/rotation.py:86-116,207-244`（offer/answer/commit 三 future 只按 `conn_id` 匹配，不校验 generation）**

- 证据：`handle_agent_restart_offer/committed` 只查 `conn_id` 即 `set_result`；generation 一致性只在 commit 等待后检查（285 行）。
- 触发：同一连接 answer 等待 10s 超时→退避重发第二轮 `ICE_RESTART`，迟到第一轮 offer 被第二轮 future 误收（SDP 代错）。
- 影响：该轮 answer 构造失败→再退避；自愈但拖长轮换，最坏拖过旧代过期（tick 已有过期 ERROR 通道，163–168 行）。
- 修复：三个 handler 校验 `payload.generation == in_progress.generation`，错代丢弃 warning。
- 置信度：60。

**C2 · Low · `src/backend/cbrowser/gateway/server.py:254-276`（disconnect 只关 Viewer，不取消该连接 rotation 任务/pending future）**

- 证据：`handle_supervisor_disconnect` 关闭 viewers 并通知 agent；`rotation.active_restarts` 与 `_pending_*` 保留至 10s/30s 超时；answer future 在 agent error 时也不被 `handle_agent_error` 处理（`rotation.py:100-108` 只处理 offer/commit）。
- 触发：Supervisor stop 并发 TURN 轮换时 disconnect。
- 影响：多余 WARNING/backoff 日志 + answer future 泄漏至超时；`_restart_connection` finally 按空连接集可提前 commit，无状态腐败。
- 修复：disconnect 调 rotation 取消该 Profile `active_restarts` 并清理三类 pending；`handle_agent_error` 一并处理 `_pending_answers`。
- 置信度：75。

**C3 · Low · `src/frontend/src/features/browser-session/useBrowserSession.ts:149-153`（runtime 查询失败 fail-open 进 `connecting_signaling`）**

- 证据：catch 直接 `setStage("connecting_signaling")`，注释称为兼容本地 mock。
- 触发：生产 API 宕机/401 时跳过 `runtime_not_ready` 解释，直接信令失败。
- 修复：区分显式 mock URL 与真实 fetch 失败，后者进 `runtime_not_ready`。
- 置信度：80。

**C4 · Low · `src/frontend/src/features/browser-session/adapter.ts:156-158`（`win.__pcs` 无界追加；`__restartOffers` 同，358–369 行）**

- 证据：每次 `new RTCPeerConnection` 都 push 且从不清理；ICE restart 频繁的长会话缓慢增长。
- 修复：只保留 `activePC`，`__restartOffers` 封顶（如 10）。
- 置信度：85。

**C5 · Info · `server.py:449` 心跳更新不校验 `agent_session_id`；`runtime_coordinator.py:105-111` 快照事件共享同一 snap_id；`BrowserSessionPage` 对 `stopping/error` 未特殊处理；`types.ts:10,17` 的 `idle`/`connecting_ice` 阶段从未被设置**

- 前三者皆小（旧 WS 心跳最多延长一次存活随即被 close；SSE 快照 ID 重复仅影响断点续传精度；`stopping` 时 Launch 可点但 Coordinator 幂等收敛）；死阶段建议后续清理类型。记录，不要求本阶段修（p011 已跟踪测试 minors）。

**C6 · 已登记 p005-f001（确认仍存在）· Low · `src/backend/cbrowser/gateway/config.py:68-71` 解析 `CBROWSER_ALLOWED_ORIGINS` 未像 `api/app.py:61-72` 那样去尾部 `/`**

- 证据：gateway `allowed_origins = [o.strip() ...]` 无 `rstrip("/")`；`server.py:480` 精确匹配。配置带尾斜杠时合法 Origin 被 403。
- 现状：p005 已登记“t007 内按需处理”，当前代码仍未改。置信度：90。

**C7 · 已登记 p005-f002（确认语义成立）· Low · `rotation.py:173-176` 轮换窗口期新建连接不在 `migrated_connections` 内**

- 新连接已拿新代配置，到期仍被做一次多余 ICE restart（功能正确，多一次协商）。p005 已登记。置信度：80。

**C8 · 已登记 p005-f003（确认仍存在）· Low · `stream_agent/agent.py:207,624-628,1043-1046` `_restart_tasks` 只在 `stop()` 取消**

- `connect_and_run` finally（373–378 行）只取消心跳任务；Gateway 断开时等待提交的 restart 任务（最长 20s `ICE_RESTART_COMMIT_TIMEOUT`）残留至超时或 stop。p005 已登记。置信度：85。

**通过项**：`browser_runtime_ready` 四文件+runner_info 身份核对（`core.py:41-58`，单测 `test_browser_readiness_fence.py`）；实例 fence（bind CAS + stale 拒绝 + 同实例幂等不倒退，`repository.py:469-508`）；退出状态机（正常清意愿/异常保留+计数+`BLOCK_AFTER=4`，`repository.py:665-681`；与 `runtime_policy.py:3-4` 一致）；幂等重放不重置 failure（`repository.py:570-571`）；Native 事件优先于合成事件（`recovery_coordinator.py:178-188,280-287`）；退出合成 137 默认、0 强制转 1（191–211 行）；`wait_restart_commit` 只认真实接管（`ice_transport.py:630-652`，与 d021 一致）；offer 要求信令 stable 且 ICE connected（`agent.py:941-949`，与 d021 一致）；`_execute_retry` 五重意图重读（455–487 行）；`scan_and_reconcile_existing` 锁/完整性/实例 fence/503 保留容器（126–296 行）；`consume_disk_events` 目录/Profile/实例三重核对（298–369 行）；`start_profile` 先 bind 后建容器、就绪轮询 30s、15s 等待 Gateway 注册（407–557 行）；`stop_profile` operation journal + 旧实例 fence + 混合实例拒绝（580–664 行）；Stream policy 单一串行锁 + 8/30 规则 + quota 取 min（`policy.py:420-559`）；HELLO 代注入不改 tab/resume（`agent.py:746-770`，与 d024 一致）；upstream 世代隔离（generation 检查 723–728/819–829/881/906 行）；`x11_keymap` argv 数组 + ABI pin（`x11_keymap.py:22-26,100-109`）；`verify_selkies_abi_guard` 三版本 + 私有字段 fail-closed（`ice_transport.py:87-144`）；`config.py` 网址/端口/几何/fps 全 fail-closed；`event_storage` 坏文件显错不猜（`get_instance_state` 三重身份核对 180–234 行）；`load_config_snapshot` 先验后建目录（`runner.py:32-57`）；退出观察区分 SDK 失联（`runner.py:591-601`，与 d016 一致）；下载捕获路径收敛进默认目录（`cdp_proxy.py:203-211`）；前端 SSE 断线指数退避（`sse.ts:179-191`）；`require_csrf_and_origin` 对写方法强制 CSRF+Origin（`dependencies.py:49-74`）。

## 三、契约·类型·Breaking 视角

**K1 · Medium · `pyproject.toml:7-18` 依赖声明缺 `argon2-cffi` 与 `aiohttp`**

- 证据：`auth/service.py:13` 用 argon2，两包均不在 dependencies；Gateway 镜像自带 aiohttp（`gateway_runtime/Dockerfile:12-15`）故网关不受影响；API 镜像走 `config/docker/Dockerfile`（基座 `cbrowser:latest` 内容不明），干净环境 `pip install -e .` 后登录即 `ImportError`。
- 修复：补 `argon2-cffi`、`aiohttp`（测试门禁 `test_cmd` 实际带了 `--with argon2-cffi --with aiohttp`，旁证声明缺失）。
- 置信度：70。

**K2 · Low · Stream UDP 端口仅绑定宿主回环（`docker_adapter.py:896`）+ `browser_isolation.md:15-20` 标签清单过期**

- 回环绑定与本地基线一致，公网属 USER_WAIVED；但 `architecture.md` 端口矩阵未注明“仅回环”，t012 切公网时须改映射并同步文档。
- spec 漂移：`browser_isolation.md:15-20` 仍写 `com.cbrowser.managed=true` / `com.cbrowser.runtime-image`，实现为 `managed-by=supervisor` + `prefix`/`role`/`instance-id`/`network-policy`（`docker_adapter.py:733-741,916-926`）。specs_index 该行止于 t003，t005 改标签未同步 spec。修 spec 一行即可。
- 置信度：90。

**通过项**：`schemas/openapi/cbrowser_v1.json`（export 脚本直调 `create_app().openapi()`，前端 `generate:api` 管道 + `types.ts` 禁手写类型）、`schemas/stream/agent_protocol.json` 与 `export_stream_protocol.py` 一致（单测 `test_stream_protocol_schema.py:13-22` 逐字节断言）、`schemas/runtime/supervisor_protocol.json` 与 `export_supervisor_protocol.py` 一致（单测 `test_supervisor_schema.py:13-24` 断言 stop fences 必填）、`schemas/runtime/agent_protocol.json`（单测 `test_runtime_protocol.py:21-30`）。`NetworkPolicySpec` extra=forbid + stream 必带 mux（`network_policy.py:80-109`）；`ProtocolEnvelope` v2 字面量；操作日志请求指纹 409（`repository.py:562-571`，单测 `test_supervisor_stop_fence.py:36-38`）；SSE `<epoch>:<seq>`（首稿 C5 备注）；JWT 无（会话方案）；Breaking（旧入口移除/旧 CDP 切换）划归 t008/t011/t012，本阶段保留旧链路正确（`config/docker/Dockerfile` 与 `*_runtime/Dockerfile` 共存、`package.json` 残留 `@novnc/novnc`+`@dnd-kit` 未打包引用——t011 移除，属计划内）。

## 四、性能·资源视角

- 无新发现。静态扫描无循环内查库/串行可并行/缺分页强信号。RTC 轮换（24h/12h/6h）、心跳 10s/超时 30s、退避上限 60s、重连 1/2/4/8/16/30s 量级合理。`tick` 每秒 O(P) 轻量遍历本地 10 流无压力。
- x11_keymap 同步 subprocess、`ResourceMonitor` 线程阻塞采样、8 小时/1000 次/P95 容量均声明递延 t009/t012（`stream_runtime.md`/`architecture.md §7`），不作承诺，不报 bug。
- E2E 固定 sleep 见已登记 p009（`test_stream_runtime_e2e.py:797` multi_viewer）、p013（`test_frontend_app_e2e.py:366-377` 静止帧断言）；`useApplyDisplaySettingsMutation` 500ms 轮询最长 120s/180s（`useProfilesQuery.ts:126-181`）为受控收敛等待，可接受。

## 五、架构·可维护性视角

**A1 · Info**：`stream_agent/agent.py`（1153）、`docker_adapter.py`（1098）、`gateway/server.py`（664）、`ice_transport.py`（667）、`policy.py`（773）、`runner.py`（750）、`recovery_coordinator.py`（606）、`router.py`（696）超规模；`HEARTBEAT_INTERVAL=30.0`（aiohttp WS 保活）与 `heartbeat_interval=10.0`（应用心跳）同名异义（`agent.py:44,204`）。p001 已登记 recovery tick 拆分（圈复杂度约 68，冻结期不动）。不阻塞。
**A2 · Info**：`runtime_events`/`audit_events` 无保留/轮转策略（bind lifecycle + heartbeat applied 均落库，`repository.py:510-523,650-663`）；单机规模可接受，建议 t010/t012 加 retention。`tick` 内 `_states` 按 profile 常驻不驱逐（含已删除 profile）；`viewers` 无 idle 超时（仅靠 Agent 30s 心跳超时清注册连带清 viewer）。三处均为有界缓增，不阻塞。
**A3 · 通过**：`file_storage.atomic_write_text` 替换链接本身（单测 `test_supervisor_file_storage.py`）；`OperationJournal` 目录 hash 文件拒绝 SQLite 化；`CoordinatorLock` flock + `O_NOFOLLOW`（单测真进程 SIGKILL 验证）；`startup_gate` 标记三元组校验后 `os.execv`；`scan_active_containers` 只认 prefix label；`cleanup_*` 归属 mismatch 即抛不强删；helper 回收仅启动锁内一次（`runner.py:121` + `docker_adapter.py:205-211`）；网络复用/删除验名称+三标签（`_require_network_ownership`）；infra 容器验 role/status/prefix（454–487 行）；`_runtime_policy_ready` 验 gate 只读挂载+ready.json 三元组（1039–1069 行）。

## 六、健壮性·可观测性视角

**R1 · Low · `src/backend/cbrowser/gateway/server.py:140-154`（tick 内 RTC_CONFIG 下发无 per-profile 容错）**

- `await self._send_agent_control(env)` 裸奔；半开 WS 抛错跳出当轮剩余 Profile 检查。外层 `monitor_heartbeats` 捕获记 ERROR（649–655 行），影响为推迟一周期（约 1s）。
- 修复：发送处 try/except 或 `send_agent_control` 内吞错记 warning。置信度：75。

**R2 · Low · `src/backend/cbrowser/stream_agent/agent.py:768-770` HELLO 解析 `except: pass` 静默吞错**

- `parts[2]` JSON 解析失败即按原样转发上游；畸形 HELLO 由 Selkies 侧拒绝（`Invalid hello message type`，见 p009），功能自洽但丢了一次可观测点。
- 修复：warning 记一笔（不含载荷）。置信度：70。

**通过项**：异常一律记 `type(e).__name__` 不泄载荷（`control_server.py:99-101` canary 单测、`test_network_policy_input_safety.py:24-29` canary 单测、`test_stream_ice_security.py` 私钥单测、`test_runtime_agent_faults.py:37-53` canary 单测）；`api/app.py:230-251` 422 脱敏 + `constraint/integrity/dbapi` 分级 409/500/503+Retry-After；`diagnostics.emit_runtime_event_log` allowlist 脱敏（git diff 已核，`_sanitize_id`/`_sanitize_reason`）；前端 SSE `console.error` 仅监听器异常；`EventForwarder` spool 哈希文件名 + ack 日志 fsync（单测 `test_supervisor_event_delivery.py` 真 HTTP 重启恢复）；`stop()` 确定性排空（`agent.py:1037-1053`）；`RecoveryCoordinator.close` 不杀健康容器（单测 `test_recovery_shutdown_safety.py`）；`run_supervisor` finally 关 forwarder/api/gateway/docker（`runner.py:120-128`）；`serve_supervisor` 任务异常退出即升 RuntimeError（202–209 行）。

## 七、测试·规格视角

- 已有测试（证据记载，未本路运行；门禁见 handoff §四：契约 168/1 skipped、旧后端 384、unit 307、integration 55、Vitest 105、E2E Gateway 5/前端 22/Runtime 13/Stream 19/Supervisor 生命周期 6/启动恢复 2/拓扑 8/网络策略 5/资源 5）：unit 61 文件逐文件核对（真实 SQLite/HTTP/WS，Mock 仅限 Docker/SDK 外部边界与 transport；恒真/弱化/跳过断言未见，`grep "assert True|pytest.skip|time.sleep" tests/unit` 仅 coordinator_lock 一处 0.02s 进程同步）；integration 16 文件逐文件核对（真实 uvicorn/aiohttp/SQLite + FakeApiService 最小内部 API）；e2e 34 文件按 AC 映射核对（Docker/Chrome 门禁，`NOT_RUN` skip 均带环境变量门 + USER_WAIVED 单列，固定 sleep 见 p009/p013 已登记）；fixtures 30+ 文件抽查（`api_auth` 登录头、`gateway_probe` Caddy/TLS 拓扑、`stream_probe` ICE 失败/提交探针、`runtime_probe` MIT-SHM C 探针、`supervisor_container_probe` 隔离镜像 Dockerfile）。
- 规格对齐：task.md 的 AC（t001 六项、t002 六项、t003 六项、t004 六项、t005 七项、t006 七项、t007 十项）与 `specs/*`、`specs_index.md` 一致；`chrome_external_tabs.md`（租约模型）已正确归档，`profile_management.md` 明确取代。
- pending 全对应“已登记”：p001 tick 复杂度、p005（f001–f004，本轮 C6/C7/C8/R-注逐项复核确认仍存在）、p006（本轮 S6 确认仍存在）、p007（本轮确认 SettingsPage:25、新建页、详情页三处硬编码）、p008（resume 未触发 RESUMED，与 `agent.py:695-718` 每隧道新建 upstream 对应）、p009（`test_stream_runtime_e2e.py:797`）、p010（vendor 未进 `npm run build`，`test_frontend_adapter_build.py` 只验单源性不验生产接线）、p011（f011 SSE 重取无回归测试/f012 容器状态收紧/f013 `audio_status.test.ts` 辅助丢能量字段——本轮复核 `samples()` 确无 `totalAudioEnergy` 透传，判定逻辑确不读该字段，结论不受影响）、p012（`test_stream_selkies_tokens_e2e.py` 首跑 1006，同 `agent.py:814-829` 世代关闭竞态）、p013（`test_frontend_app_e2e.py:366-377`）。
- 阶段边界：t008/t013/t014/t009/t010/t011/t012 未实施不判 bug；公网/x86 USER_WAIVED 单列合规（`v2_architecture_plan.md §执行调整`、`testing.md §6`、`guides/*` 均单列 NOT_RUN）。

## 八、文档规范视角

**D1 · Low · `docs/blueprint/architecture.md:9`**

- “现有生产代码库仍维持旧单容器实现…在 t001 阶段…保持完全不变”无时间锚点，易误读；同节 t005/t006/t007 bullets 对冲。修复：一句加注“（t001 时点陈述）”。置信度：70。

其余：`security/gateway/stream/supervisor/browser/frontend/persistence` 三态分节清晰；`specs_index.md` 在表即生效；`pending` 脚本编号；`archive` 镜像原路径（spikes 10 份 report 均带“范围更新”头，`chrome_external_tabs` 归档正确）；`handoff.md` 仅最新一节；`guides/*` 为阶段验证未冒充交付；`review_v2_scope*`/`review_local_benchmark` 明确“文档评审 PASS≠性能验收通过”；`i18n.tsx` diff 新增键与实现同步；`generated/cbrowser_v1.d.ts` 头声明禁手改；`vendor` 清单位置问题 p010 已登记（`tests/fixtures/.../selkies_web_sha256.txt` 被生产脚本引用）。

## Spec 合规结论

t001–t007 已交付链路与现行 spec/blueprint 一致。本轮 S1–S5（S6 为已登记 p006）、C1–C4（C6–C8 为已登记 p005）、K1–K2、R1–R2、D1 均为已交付路径的真实缺陷或声明缺口，建议修但不推翻阶段验收；其余 pending 均为已登记。t008–t014 缺失不计 bug。

## Strengths

1. 凭证纵深：HMAC 派生 + Selkies 双 token + TURN 短期凭证三轨；过期实例拒绝不覆盖；Selkies token 0600 + 新文件名防旧挂载残留（`selkies_tokens.py:40-57`）。
2. 路径安全：secret 目录与 Browser 挂载平级隔离 + 0600 挂载校验 + 别名拒绝（单测三件套）。
3. 失败语义诚实：`last_coordinator_error` 显式报告；commit 只认真实接管（`COMMIT_TIMEOUT_SEC` + committed 事件）；answer 转发≠成功（d021 落地）。
4. 前端：关页不杀 Browser、多 tab controller、Web Locks 防踢原页、静音/音频状态独立、阶段可执行操作。
5. 测试资产：unit/integration/e2e/fixtures 与生产逻辑直连，脱敏 canary 负例成体系（auth/config/policy/ice/agent/registry 六处）。

## Appendix · 覆盖清单（507 条逐文件；已审=全文读，抽查=关键段+断言形状，历史=归档追溯口径）

- `.gitignore`（M,55 行）：已审（diff 仅加 selkies/ 忽略）。
- `config/docker/browser_runtime/Dockerfile`（A,102）：已审；`entrypoint.sh`（A,115）：已审。`gateway_runtime/Dockerfile`（A,31）：已审；`.dockerignore`（A,15）：抽查。`stream_runtime/Dockerfile`（A,57）：已审；`entrypoint.sh`（A,207）：已审。`supervisor_runtime/Dockerfile`（A,24）：已审；`.dockerignore`（A,8）：抽查。`config/docker/Dockerfile`（旧基座）：已审（t011/t012 范围，现状记录）。
- `docs/archive/handoff.md`（M,524）：抽查（追加旧节合规）。`docs/archive/pending/p002,p003,p004`：已审（均为 resolved 历史）。`docs/archive/specs/chrome_external_tabs.md`（R,35 行）：已审（正确归档，租约废弃）。
- `docs/archive/spikes/s001–s010 report.md/first_review/blackbox_review/independent_review*/container_download_*/recovery_review`（约 30）：已审（报告头+范围更新+结论，均为历史快照口径）。`code/*` 约 90 探针脚本：历史（未逐行审，追溯口径）。
- `docs/archive/tasks/t001–t007 task.md`（7）：已审（AC 全对）；`note.md`（7）：抽查（t007 头 30 行，余为过程日志）；`review_code.md/review_test.md`（14）：抽查（t007 review_code 头 30 行，余证据记载）；`handoff.json/scope_adjustment/validation_matrix`：抽查。
- `docs/archive/tasks_index.json`（M）：抽查（t001–t007 done 行）。
- `docs/blueprint/` architecture/security/supervisor/gateway/stream_runtime/browser_runtime/persistence/frontend/testing/decisions（11）：已审（testing 60–174 行抽查命令节，decisions 头 60 行，余全文）。
- `docs/findings/d001–d024`（24）：已审（结论/影响/现状逐条；d001/d024 全文）。
- `docs/guides/browser|stream|supervisor_validation.md`（3）：已审（头+分层节）。
- `docs/handoff.md`（M）：已审（§一–五全文 73 行内）。
- `docs/pending/todo/p001,p005,p006,p007,p008,p009,p010,p011,p012,p013`（10）：已审（全文短条）。
- `docs/reviews/review_local_benchmark_20261027/review_benchmark.md`：已审（头 20 行，PASS 限定文档层）。`docs/reviews/review_v2_scope_20261027/` 4 文件：已审（disposition 全文+余清单级）。
- `docs/specs/access_control.md,browser_isolation.md,profile_management.md,runtime_lifecycle.md,runtime_persistence.md,v2_runtime_validation.md,webrtc_remote_display.md`（7）+`specs_index.md`：已审。
- `docs/tasks/t008–t014 task.md/note.md`（14）：已审（task 全文短契约，note 头；均为 backlog 未来，不判 bug）。`docs/tasks_index.json`：已审（头 40 行）。
- `docs/v2_architecture_plan.md`：已审（豁免/修订/1.1 节 + grep 余节标题）。
- `pyproject.toml`（M）：已审（K1）。
- `schemas/openapi/cbrowser_v1.json`：抽查（生成头+一致性单测）。`schemas/runtime/agent_protocol.json,supervisor_protocol.json` + `schemas/stream/agent_protocol.json`：已审（经导出脚本+单测逐字节断言）。`scripts/export_openapi.py,export_supervisor_protocol.py,export_stream_protocol.py`：已审。`scripts/vendor_selkies_web.py`（262）：已审（1–180 行全读，余抽查；zip-slip 宽容记 Info）。
- `src/backend/cbrowser/auth/__init__.py,service.py,dependencies.py,rate_limiter.py`：已审。`api/app.py,main.py,v1/router.py(696 全),v1/auth_router.py,internal_gateway.py,internal_supervisor.py,runtime_coordinator.py(481 全)`：已审。`adapters/database/models.py(283 全),session.py,migrations.py,repository.py(440–709 全+余 grep)`：已审。`domain/models.py(418 全),runtime_policy.py`：已审。`services/profile_service.py(243 全)`：已审。`gateway/__init__.py,__main__.py,api_client.py,config.py,registry.py,rotation.py(337 全),server.py(664 全)`：已审。`rtc_config/__init__.py,credential.py,models.py,service.py`：已审。`runtime_agent/__main__.py,agent.py(479 全),cdp_proxy.py(240 全),event_storage.py(235 全),profile_defaults.py(318 全),protocol.py,runner.py(1–100,551–750 全+余 grep),security.py,subsystems.py`：已审。`stream_agent/__init__.py（薄）/__main__（经 run_standalone 全读 1061–1153）,agent.py(1153 全分段),boundary.py,client_shim.py,config.py(317 全),ice_transport.py(667 全分段),policy.py(1–120,420–564,667–773 全+余 grep),protocol.py(350 全),x11_keymap.py(118 全)`：已审。`supervisor/__init__.py,__main__.py,agent_credentials.py,control_server.py,coordinator_lock.py,core.py(773 全分段),docker_adapter.py(1098 全分段),event_forwarder.py,file_storage.py,gateway_client.py,network_policy.py(261 全),operation_journal.py,path_validator.py,port_allocator.py,protocol.py,recovery_coordinator.py(606 全分段),resource_monitor.py(162 全),resource_policy.py（grep 决策链+单测）,runner.py(306 全),selkies_tokens.py,startup_gate.py(151 全)`：已审。`src/backend/diagnostics.py`（M）：已审（diff 68 行全）。`src/backend/migrations/alembic.ini,env.py（头 25）,script.py.mako,versions/0001（表结构 grep）,0002`：已审。
- `src/frontend`：AppLayout(292 全)/providers/router(57)/RequireAuth/auth_guard 测试(头)/LoginPage/redirect/useAuth/useProfilesQuery(221 全)/ProfileNewPage/ProfileDetailPage(头 100)/BrowserSessionPage/BrowserSessionView/adapter(555 全)/adapter_restart 测试(头)/audio_control/audio_status(+测试)/host_entry/index/media_controls 测试(头)/selkies_adapter_entry/SessionDiagnostics(头)/sse(+测试)/client(+测试)/types/generated d.ts(头)/BrowserSessionMount/vite-env（薄）/vite.selkies.config/tsconfig/package.json(diff 核)/settings(头+残留确认)/placeholders×2/i18n(diff 段)/main/router 测试(头)/useProfilesQuery 测试(头)/BrowserSessionView 测试（经 review 引文核） ：已审（JSX 余部抽查）。
- `tests/unit` 61 文件：已审（逐文件头+关键断言；fence/脱敏/隔离/轮换/恢复类多文件深读）。
- `tests/integration` 16 文件：已审（逐文件头+关键路径；gateway_control/signaling/rotation/auth_api/sse/rpc/status_truth/coordinator/recovery 按段深读）。
- `tests/e2e` 34 文件：抽查（AC 映射全核：browser 6 AC、stream multi_viewer+tokens+ice/commit/relay/keymap/identity/rtc_config、gateway ac001/003/005/007、supervisor 12 文件名+关键用例、frontend 8 文件名+关键断言、coordinator；sleep/skip 模式 grep 全扫）。
- `tests/fixtures` 30+ 文件：抽查（api_auth、gateway_probe caddyfile/topology 头、stream_probe ice_restart_failure 头、runtime_probe C 探针存在性、supervisor_container/recovery/resource_probe Dockerfile、frontend_probe harness 存在性）。
- 跨 task 交互合并：S5/C1–C2/R1/K2/p005/p006/d003-d024 同条说明，不分散。
