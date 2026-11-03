---
tid: "t022"
slug: "runtime_gateway_reliability"
title: "修正运行时恢复、隔离与信令状态"
status: "done"
branch: "t022_runtime_gateway_reliability"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "d699e5bd8cce70e175dafedd90d48fd8bc22b207"
depends_on: "t021"
conflicts_with: "t019,t020"
note: "review_20261103_185924：A3/A8/A9/A10/A11/A13/A14/A15/A16/A34/A39/A44/A45/A47/A48/A55（D1=B）；不含模板整改与备份切换"
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

2026-11-03：用户授权按职责合并立项，本 task 为 53 项采纳结论中 16 项的唯一主承接；完整范围与 AC 对应见 task.md。现有 t019/t020 保留，原 A36/A37 拒绝；本轮未 start、未实现、未跑业务测试。

创建验证：`task.py preflight t022 --creation` 为 PASS；工作区未提交提示属于本批新建文档。另有 A47 的 SDK ABI/keymap 运行契约标为 `UNVERIFIED-SPIKE`，须先完成隔离实验再回填。

2026-11-04 执行（attempt 1，base=t021 d699e5b）：A47 spike 已核实并回填 task.md（Selkies 2.1.0 官方 wheel sha256 8bde6207… 源码逐行核对：`_spare_keycodes` None 可达、SDK 原规则为惰性初始化同一键池、text_room 先于 prebind）；preflight --require-verified PASS。本机无 Docker/Chrome：真实镜像与真实拓扑类验证按用户 2026-11-04 豁免口径跳过按 pass 计，真实环境义务收尾时立 pending 追踪（p021/p022/p023 先例）。
- A3/AC-001 已实现：cdp_proxy 重连 rearm 记录命令 ID、仅匹配成功 ACK 置健康，error/无 ACK/断线保持不健康；新增 error ACK 与无 ACK 两条红→绿测试，test_runtime_agent_faults 12 passed。
- A13/AC-006 已实现：agent 启动 `_validated_runner_info` 校验必需字段与类型，脱敏 StorageError 拒绝；新增 6 测试，faults 文件 18 passed。
- A14/AC-007 已实现：runner X11 锁不可读/损坏时明确报错并保留锁与 socket，仅死 PID 清理；新增 4 测试，faults 文件 22 passed。
- A55/AC-016 核心层已实现：profile_defaults 有界非阻断包装（超时/异常记录独立状态、失败不写 marker、disabled 不执行）+ run_dir 状态文件；Agent /health 类型化 `search_defaults` 字段；/control `retry_search_defaults` 身份围栏 + 幂等请求文件；runner 监视器在活 context 上消费重试（不重启、重复 request_id 不重跑、过期实例拒绝）。新增 8 测试全绿。API/Supervisor/前端接线在本 task 后段完成。
- A8/AC-002 已实现：EventForwarder 暴露 `emit_event_with_outcome` 三态（bool `emit_event` 为同一路径委托）；401/403/408/429/5xx 统一 UNAVAILABLE（与 artifact_forwarder 共用 `RETRYABLE_4XX`/`classify_delivery_status`），确定语义拒绝才 REJECTED；consume_disk_events 对 REJECTED 隔离原文件一次并推进持久化游标、对 UNAVAILABLE 保持待投递；`_native_exit_instances` 标记移入 DELIVERED 分支（诊断投递不推进业务状态）。新增分类/死信/待投递测试，相关 23 测试全绿；test_supervisor_event_cursor 的桩按新接口迁移（计数与断言不变）。
- A9/AC-003 已实现：X11 权限 helper 收紧为 cap_drop ALL + 仅 FOWNER、read_only、no-new-privileges、受管标签（container_spec.x11_helper_labels），detach+wait 校验退出码、finally 恒 remove。新增 3 测试。
- A10/AC-004 已实现：scan_active_containers 在扫描边界校验 profile/instance 身份与 config-version（`_parse_config_version`），异常资源逐个拒绝并记录脱敏诊断、其余继续；stream 启动 inspect 读取同样校验。新增混合扫描测试。
- A11/AC-005 已实现：core 新增类型化 `LifecycleConflictError`（清理未完/缺 running 意图/重试阻断三处），control_server 按类型映射 409（端口耗尽 503、意外 500 不变），响应不含内部文案。新增真实 HTTP 三态测试。
- A34/AC-010 已实现：network_policy 新增 `NetworkPolicyError`（family/tool/exit_code + ≤512 字符脱敏 stderr）；任一 family restore 失败时对双 family 安装 DROP 兜底规则后再报错，main 记录结构化诊断。新增 IPv4/IPv6 失败测试。
- A45/AC-013 已实现：StopProfileResponse 结果词汇改为 stopped/already_absent/superseded_noop（导出 schema 已同步）；core.stop_profile 对过期目标返回 superseded_noop 并保护新实例、无目标返回 already_absent、重放返回同一结果；API coordinator 显式消费结果且仅按权威观测记录收敛（200 无有效结果视为协议失败 RETRYABLE）。两条旧契约 coordinator 测试整体按新时序改写（mock 先回放观测上报再返回结果，断言不变），新增 superseded/absent/重放与 coordinator 不收敛测试全绿。
- A15/AC-008 已实现：stream_agent/protocol 定义三层预算单一权威（数据 1MiB / envelope 2MiB+64KiB / WS 帧 6MiB+64KiB，含关系断言与 `serialize_tunnel_envelope`）；Agent 入站 envelope 预算对齐、超限 1009 关闭；Gateway 查看器→Agent 路径 data 超预算或 envelope 构造失败仅以 1009 关闭该 viewer。新增 5 单测 + 1 集成用例（另有既有用例覆盖帧级上限路径）全绿。
- A16/AC-009 已实现：registry.update_heartbeat 同步 runtime_state（仅已注册会话）；配额向 Agent 发送失败明确 503；supervisor disconnect 逐目标清理抽为模块级 `close_profile_viewers_and_notify`（单 viewer 失败不跳过其余、Agent 通知失败在全部处理后报 503），假 ws 单测锁定两条失败路径。
- A39/AC-011 已实现：RegistrationThrottle 改双预算（reserve/release：在途上限 4、失败窗口 20/60s；成功不消耗不清失败史；全部退出路径 finally 释放；旧 allow 契约测试整体替换并注明取代）；注册处理器改 reserve/try/finally；Agent ReconnectBackoff 可注入 jitter（生产 random.random，缩放 [50%,100%] 不超上限），既有精确退避测试经 StreamAgent 新参数钉满量程、断言不变。集成新增失败预算 429、成功不消耗、在途上限与取消释放、网关重启恢复四条证据（harness start 改为每次重建 app，语义不变）。
- A44/AC-012 已实现：SSE 快照改私有（不写全局历史、不消耗 live 序号），全部快照帧携带 live 基点 id，一次 DB 读在 publish 同锁下完成、注册同序，无缺口无倒退（并发测试锁定）；窗口不足走快照显式重建、无 provider 时发 `: resync-required` 标记；t007 的 unique-ids 旧测试整体删除并注明被 A44 取代。引擎/GeoIP 缓存改代次复用：全量校验后以树指纹封存 sidecar（原子替换）+ 根身份（realpath/dev/ino）绑定，后续启动仅验根与封存记录，未知/被篡改/刷新后 stale 均全量重验并封存新代次；新增 sidecar 篡改与刷新重封测试。取舍：代次目录物理迁移挂载（gen-N 子目录）未做，挂载路径仍为缓存根（属 t009/t010 已交付的 container_spec 契约），运行中容器挂载不被新代次改动这一点由 ensure_runtime_cache 的 ready 早退保证（进程内二进制就绪后不再写缓存）。
- A47/AC-014 已实现：x11_keymap 适配层新增 `_verify_selkies_keyboard_abi`，安装期校验全部私有面（prebind/text_room/_find_spare_keycodes/_layout_keycode 签名、_BIND_SETTLE_S、__init__ 六个实例属性），不符明确 RuntimeError unsupported ABI；text_room 在 `_spare_keycodes` 为 None 时按 SDK 原规则惰性初始化同一键池（f_backend_stream_gateway_05）。新增 5 条 ABI 契约测试。真实调用顺序证据（owner-loss/正常退出）本机无 Docker/Chrome，按豁免口径立 pending p024（AC-014 的本机验收仅为 ABI 静态契约，真实运行证据以 p024 为准，与 task.md 可测试性声明一致）。
- A48/AC-015 已实现：policy.set_supervisor_quota 与协议同规（有限且 ∈[min_fps,max_fps]，越界 ValueError 严格拒绝且不改现值，None 仅解除）；Agent 侧调用点捕获 ValueError 不断开控制通道；旧 quota 测试整体按新规改写并注明 f_04 取代。StreamAgent 删除无消费者 close()，stop() 成为唯一关闭入口（取消并 await 心跳、排空 viewers/detached、幂等），新增 stop 契约测试。去重：iso_now 单一定义（messaging 改转发 policy_rules）、verb 拦截统一 should_block_client_verb、协议身份校验抽共享函数（三模型九处委托、行为不变）、Gateway 注册解码冗余 `(ValidationError, Exception)` 改单一 Exception 并注明隔离意图、supervisor 三路由 fence 抽模块级 `supervisor_fence_failure`。删除死代码 calculate_cpu_percent 及其专属 2 测试（实际 quota 算法 calculate_quota_normalized_percent 的行为覆盖保留在 ResourcePolicyService 测试中）。
- A55/AC-016 接线已完成：Supervisor 新增 GET search-defaults 与 POST search-defaults/retry 路由（Bearer 鉴权；core 经 UDS /control 转发，session 围栏 409、不可达 503，协议 schema 已重新导出）；API 侧 ProfileRuntimeResponse/SSE 事件新增类型化 `search_defaults`（coordinator 内存映射 + GET 时向 Supervisor 刷新、实例不一致丢弃；publish 与 SSE 快照均携带），新增 POST /profiles/{id}/runtime/search-defaults/retry（CSRF 保护、409/503 映射）；前端生成类型已更新，Profile 详情页在 state=failed 时显示独立提示与重试按钮（新 hook + client 方法 + 中英文案 + 组件测试）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

第 1 轮（双路独立审阅，review_code.md / review_test.md，均 REQUEST CHANGES）处置：

test 路：
- F001 已修：新增来源键有界/淘汰单测（test_gateway_registry）+ 握手超时释放集成用例（test_gateway_signaling）；note A39 表述经复核未高估（harness 为真实 Gateway + WS 注册客户端）。
- F002 已修：新增双订阅并发用例；交接负断言改事件阻塞 + 让行（去 sleep 固定时长）；新增缓存根整体替换触发全量 + ensure ready 早退不改 sidecar 两用例。
- F003 已修：新增 API 路由层集成用例（真实 uvicorn+CSRF：403/200/409/503 + Idempotency-Key 透传）、Supervisor core UDS 映射单测（get 围栏/retry 200·403·503/调用前围栏）、marker 已存在不重跑 UI 用例（手动选择保留）。
- F004 已修：新增 test_supervisor_start_conflicts 三条，core 三处冲突产生点真实触发。
- F005 已修：配额发送抽为模块级 deliver_supervisor_quota 并新增失败/成功单测（路由 503 映射不变）。
- F006 已修：新增 X11 helper wait 失败仍清理用例、rearm 超时分支用例（抛错/计数不变/可恢复）。
- F007 已修：AC-014 行互引 p024 并声明本机验收边界（见上 A47 条）。
- F008 已修：inflight 改条件轮询；重启重试异常收窄为 ClientResponseError 且状态 ∈{403,503}。
- F009 已修：stop 深度用例（心跳取消/viewers 与 detached 释放断言）；Agent 入站超限补 WS 层用例——并由此发现 Gateway pump 缺入站 envelope 预算关闭，已补实现（超 MAX_TUNNEL_ENVELOPE_SIZE 以 1009 关闭该 Agent 连接，与 Agent 侧对称，属 AC-008 应有之义）。
- F010 已修：note A15 计数表述更正；resource_policy 删除处留互引注释。

code 路（以落盘 review_code.md 的 15 条为准；另有一份经上下文转述的 12 条摘要与之编号不一致，其中 Idempotency-Key 跨层透传、前端 SSE 消费 search_defaults、配额拒绝后仍 reconcile、get_search_defaults 二次围栏、sidecar 改 atomic_write_text 五项改进已一并落地，见各 AC 实施行）：
- t022_code_f001 已修（important）：缓存快速路径改为重算树指纹并与封存记录比对，不一致即全量校验重封；新增「只改树不动 sidecar（文件换逃逸 symlink）触发全量并拒绝」用例。
- t022_code_f002 已修（important）：节流淘汰重写——在途/受保护来源永不淘汰、两映射同步清理、优先淘汰无历史与最近最不活跃来源；新增洪泛下在途上限与活跃来源历史保留用例。
- t022_code_f003 已修：指纹已含 size+mtime_ns（内容哈希不做，信任边界已成文于 docstring 与 blueprint）；代次号跨进程衔接（新进程首封从磁盘 sidecar 代次 +1），新增用例。
- t022_code_f004 已修：register 后旧会话 viewer 清理与 ACK 发送均加异常隔离（失败只记日志，pump 负责收尸），不再留下无 pump 孤儿注册；ACK 注入失败的集成注入用例受 harness 构造所限未做，隔离逻辑由代码审查与既有 supersede 集成覆盖兜底。
- t022_code_f005 已修：fail-closed 兜底去掉 --noflush 做整表替换，新增断言正常路径保留 --noflush、兜底两族均替换的用例。
- t022_code_f006 已修：X11 helper 加确定性名称 `{prefix}-x11-{12hex}` 并纳入 _cleanup_orphan_helpers 角色集，新增孤儿回收用例。
- t022_code_f007 已修：helper finally 的 remove 包异常隔离（只记日志）；wait 的非 DockerException 统一映射 DockerSandboxError（DockerSandboxError 本身透传）；新增 remove 失败不掩盖成功用例。
- t022_code_f008 已修：rearm 待 ACK 加 5s 截止（晚到 ACK 忽略，新增晚到 ACK 用例）；命令 ID 统一单一同步分配器（新增共享分配用例）。
- t022_code_f009 已修：ABI 属性检查改 AST 解析（注释/字符串不算数，新增用例）；signature 异常归一为 unsupported RuntimeError。
- t022_code_f010 已修：publish 路径与 REST/SSE 快照统一实例围栏（coordinator.fenced_search_defaults + runtime_views.fence_search_defaults 单一实现），新增 publish 围栏用例。
- t022_code_f011 已修：retry 成功后有界轮询（≤5s）等状态文件出现本次 request_id 的终态再 publish/返回，新增「前两次轮询旧状态、第三次终态」用例。
- t022_code_f012 已修：无锁文件时改探活 socket（拒连才删、活着报错保留、探活不明报错保留），新增死/活 socket 两用例。
- t022_code_f013 已修：core 隔离失败返回 False 且不推进游标（事件保持待投递，新增用例）；死信单一归属——core 传 dead_letter_spool=False，forwarder  spool 副本直接丢弃，新增「死信总数恰为 1」用例。
- t022_code_f014 已修：删除 messaging 的残缺 __all__ 并留说明注释。
- t022_code_f015 已修：runner 已处理 request_id 改 OrderedDict 有界 64。

另：摘要版提及的两处存量问题（AuthorizationThrottle 来源上限、pump tunnel 逐消息身份复检）非落盘报告条目，已立 p025 跟踪，不在 t022 范围内改。

第 2 轮复审（双路新审阅者，review_code_r2.md / review_test_r2.md）：code 路 PASS（简报编号 12 项逐项属实；第 1 轮摘要版 f011/f012 经其独立核查为误读撤回——FORBIDDEN_PEER_PREFIXES 已删除、_query_agent_health 已走 _agent_uds_client；其指出的三条残余观察均为审阅窗口内第二批修复落盘前的快照，已被随后落盘的 f004/f010 修复与 X11 孤儿用例转绿覆盖）；test 路 F001–F010 全部关闭，仅以 N1 给 REQUEST CHANGES——N1 为其抽跑窗口与第二批修复落盘重叠的中间快照（当时节流淘汰实现/测试尚在改写中），最终状态下 test_gateway_registry 全文件 7 passed、unit 全量 710 passed，code 路复审者亦独立复验该实现与探针通过。针对落盘 code 报告 15 条 + N1 最终状态另派第 3 轮定向复审（review_code_r3.md）。

第 3 轮定向复审：**PASS**——15 条 code finding 逐项属实已修、N1 已消解（最终实现 + 全文件实跑 7 passed），必查 8 文件实跑 83 passed / 0 failed，无新问题。full review 三轮闭环，最终指纹与复审范围一致。

结构化处置表（与上方逐项说明一致）：

| finding_id | status | fix_ref |
| --- | --- | --- |
| t022_code_f001 | 已修 | t022 |
| t022_code_f002 | 已修 | t022 |
| t022_code_f003 | 已修 | t022 |
| t022_code_f004 | 已修 | t022 |
| t022_code_f005 | 已修 | t022 |
| t022_code_f006 | 已修 | t022 |
| t022_code_f007 | 已修 | t022 |
| t022_code_f008 | 已修 | t022 |
| t022_code_f009 | 已修 | t022 |
| t022_code_f010 | 已修 | t022 |
| t022_code_f011 | 已修 | t022 |
| t022_code_f012 | 已修 | t022 |
| t022_code_f013 | 已修 | t022 |
| t022_code_f014 | 已修 | t022 |
| t022_code_f015 | 已修 | t022 |
| t022_test_f001 | 已修 | t022 |
| t022_test_f002 | 已修 | t022 |
| t022_test_f003 | 已修 | t022 |
| t022_test_f004 | 已修 | t022 |
| t022_test_f005 | 已修 | t022 |
| t022_test_f006 | 已修 | t022 |
| t022_test_f007 | 已修 | t022 |
| t022_test_f008 | 已修 | t022 |
| t022_test_f009 | 已修 | t022 |
| t022_test_f010 | 已修 | t022 |

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：16 条 AC 全部实现并勾选；本机可执行的验收证据齐全，真实环境义务入 p024。
- 测试（最终指纹全量实测）：模板契约 169 passed；unit 710 passed / 2 failed（仅基线存量 repo_hygiene home 路径、runtime_persistence_guards terminal_storage_failure，与干净 base 同 ID、零新增）；前端 105 passed（23 文件）+ 生产构建通过；git diff --check 干净。integration：第一批指纹全量 115 passed / 0 failed；最终指纹两次全量各有 1–2 条协调/子进程类用例偶发失败（test_v2_api_subprocess、test_ac009 协调类，在两次运行间旋转出现），涉事文件单独与合跑均全绿（9/9、14/14），与基线已知的 test_ac009 全量负载偶发类一致，非本次回归。
- 黑盒：按用户 2026-11-04 豁免口径跳过记 pass（本机无 Docker/真实拓扑），未执行义务立 p024（含 A47 真实调用证据、A39 真实多 Agent 拓扑、A55 真实重试链）。
- review：full review 三轮闭环——第 1 轮 code 15 条 + test 10 条（均 REQUEST CHANGES）全部处置；第 2 轮 code PASS、test 仅 N1（中间快照）；第 3 轮定向复审 PASS（review_code_r3.md），最终指纹与复审范围一致。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 运行时恢复/隔离/信令 16 条 AC 全部落地：CDP rearm 严格 ACK、事件投递三态与死信、X11 helper 最小权限、扫描边界校验、类型化 409、元数据脱敏拒启动、X11 锁死 PID 清理、三层信令预算（Gateway pump 入站方向在 review 期间补齐）、NetworkPolicy 双族兜底、stop 结果词汇化、注册双预算节流 + 退避抖动、SSE 快照私有化交接 + 缓存代次封存、Selkies ABI 安装期校验、配额严格化与死代码清理、search-defaults 状态四层贯通（Agent→Supervisor UDS→API→前端，含 Idempotency-Key 跨层幂等）。
- 遗留：p024（真实环境执行义务）、p025（Gateway 两处存量加固，非本 task 引入）。

### 长期文档闭环

- specs_index：runtime_lifecycle 与 webrtc_remote_display 两行已加 t022 关联。
- blueprint 已更新 7 处（browser_runtime / supervisor / gateway / stream_runtime / frontend / decisions 新增 016 / testing 故障矩阵）；A47 spike 结论已回填 task.md 并以 ABI 契约测试固化，无独立 spike 目录（探针在 .scratch，不入库）。
