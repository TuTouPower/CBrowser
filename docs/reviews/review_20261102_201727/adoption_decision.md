# 审阅结果决策

## 目录

docs/reviews/review_20261102_201727

## 报告来源

- 已读：根目录全部 41 份 bundle 逐份通读——bundle_repository_summary.md、bundle_cross_validation.md、bundle_global_strategy.md、bundle_global_architecture.md、bundle_global_system_properties.md、bundle_global_evolution.md、bundle_followup_q_architecture_01..04.md、bundle_followup_q_evolution_01..03.md、bundle_followup_q_strategy_01..03.md、bundle_followup_q_system_properties_01..03.md、bundle_local_archive_spikes.md、bundle_local_archive_tasks.md、bundle_local_backend_api_auth.md、bundle_local_backend_core.md、bundle_local_backend_runtime_adapters.md、bundle_local_backend_stream_gateway.md、bundle_local_backend_supervisor.md、bundle_local_backend_tests.md、bundle_local_contracts_deploy.md、bundle_local_docs_current.md、bundle_local_frontend_features.md、bundle_local_frontend_shell.md、bundle_local_repo_ops.md、bundle_local_template_scripts_ops.md、bundle_local_template_scripts_state.md、bundle_local_template_support.md、bundle_local_template_tests.md、bundle_local_tests_e2e_stream_frontend.md、bundle_local_tests_e2e_supervisor.md、bundle_local_tests_integration_fixtures.md、bundle_local_tests_unit_stream_api.md、bundle_local_tests_unit_supervisor_runtime.md；review_intensive.md 作索引与计数交叉核对（362 条与 bundle 逐条提取一致）。
- 缺失：无（intensive 路聚合与 bundle 齐全；本目录无多模型路报告）。
- 合并说明：见文末「附：finding → 决策映射」。原始 finding 362 条（Critical 1 / High 32 / Medium 112 / Low 173 / Info 44）→ 54 个决策项（A 48 / R 6；D1–D8 经用户决策转为 A41–A48）。归并规则：同一缺陷在生产代码与其测试缺口两侧各有一条时合并为一项；全局组合型结论（global\_\*）映射到其构成项；同一区域、同一修复方向的项按族归并。交叉证伪（bundle_cross_validation）抽查 30 条全部 agree，无 CHALLENGED/PARTIAL 需降级。
- 决策标准（用户 2026-11-02 指定）：追求最好的架构与设计、最少的技术债，不考虑开发时间与改动大小。据此，“改动成本高、收益低”不再作为不采纳理由；不采纳只保留三类：项目规则禁止（归档只准新增）、代码将被整体删除（legacy 随 t011）、设计上不应改（附具体设计理由）。部署包络仍为单机单人（已记录的用户决定），它决定需求范围，不降低质量标准。
- 基线与现场：审阅基线 HEAD 5136766。此后 main 新增 8ccb9ae（Browser Runtime 镜像加 GTK、文件对话框书签、`--disable-gtk-ime`），与本文各项无冲突。2026-11-02 实测：在跑的旧版容器 `cbrowser`（compose 启动，数据卷 `~/.cbrowser`）端口发布在 `0.0.0.0:56661`、`AUTH_TOKEN` 已设置；未带凭据请求 `/%2e%2e/%2e%2e/%2e%2e/etc/hostname` 返回 200，路径穿越在现网可利用。

## 统计

- 采纳：48 项
- 不采纳：6 项
- 待决定：0 项

## 待决定项（请先决策）

无。D1–D8 均已由用户决策并转为采纳项 A41–A48。

## 采纳项

### A1. Supervisor 上报端点从用户会话面摘除

- 来源：bundle_global_architecture, bundle_local_backend_api_auth, bundle_followup_q_architecture_04, bundle_global_system_properties, bundle_cross_validation
- 位置：src/backend/cbrowser/api/v1/router.py:56,706-835；src/backend/cbrowser/api/internal_supervisor.py:48-99；tests/integration/test_v2_api_subprocess.py:485-698
- 优先级：HIGH
- 详细判断理由：bind/observed/events 三个 Supervisor 上报 handler 同时挂在管理员会话面，浏览器会话可伪造实例绑定与退出事件，直接驱动对账与重试；授权取决于挂载位置而不是操作本身。精查确认生产 Supervisor 只走内部面、前端零调用，唯一使用者是一个扮演 Supervisor 的验收测试。
- 修复说明：把三个 handler 从 profile_router 移出，只注册在 internal_supervisor 的 supervisor_router（require_supervisor 守卫），handler 自身声明服务身份依赖，使授权随操作而非随挂载；先把 test_v2_api_subprocess.py 中 `/api/v1/runtimes/bind|observed|events` 调用改走 `/api/v1/internal/supervisor/*` 并为其 harness 配置 Supervisor token；重新导出 OpenAPI 并 `npm run generate:api`；补架构测试：枚举全部路由，断言上报类路径只出现在服务面。

### A2. Runtime Agent `/health` 探活移出事件循环

- 来源：bundle_local_backend_runtime_adapters, bundle_global_system_properties, bundle_cross_validation
- 位置：src/backend/cbrowser/runtime_agent/agent.py:100,197-231；src/backend/cbrowser/runtime_agent/subsystems.py:15-146
- 优先级：HIGH
- 详细判断理由：async handler 内同步执行 xdpyinfo/pactl/urlopen，最坏阻塞约 4.5 秒，期间 /cdp 隧道与下载事件处理被冻结；同文件 /cdp/version 已用 to_thread，属遗漏。
- 修复说明：subsystems 的探活改为 async 实现（asyncio.create_subprocess_exec 与异步 HTTP，或 to_thread 包装），get_health 用 asyncio.gather 并发执行并收紧单项超时；补单元测试：用可控慢探活让单次探活约 1 秒，同时请求 /config_version，断言其延迟显著小于探活时长。

### A3. CDP 事件监听单帧异常隔离与自愈

- 来源：bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/runtime_agent/cdp_proxy.py:146-175
- 优先级：MEDIUM
- 详细判断理由：一条非法 JSON 或字段类型异常的 CDP 帧会结束整个监听任务，此后下载捕获、Browser.close 与所有 CDP 命令响应全部失效直至进程重启，且无自愈。
- 修复说明：\_listen_events 对每帧解析与分发包 try/except（记录 warning 后 continue）；连接异常退出时带退避重连并重新 rearm 下载行为，重连失败上报为需 Supervisor 重建实例的硬故障；补用例：非法帧后正常帧仍被处理、连接断开后自动重连。

### A4. 下载产物转发链路：越界拒绝与失败留痕

- 来源：bundle_local_backend_supervisor, bundle_followup_q_architecture_03, bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/supervisor/artifact_forwarder.py:20-27,115-143；src/backend/cbrowser/supervisor/event_forwarder.py:117-133,168-178；src/backend/cbrowser/services/artifact_service.py:152-166
- 优先级：MEDIUM
- 详细判断理由：translate_download_path 只做前缀剥离后拼接，事件文件（位于 Browser 容器可写的挂载目录）里的 `../` 或 `..` 型 profile_id 可让 Supervisor 登记沙箱外的宿主路径；DownloadArtifactForwarder 对解析失败的事件静默标记为已处理并持久化；磁盘信封无版本字段；ingest_download 三种失败都无声返回 None。
- 修复说明：translate_download_path 对拼接结果 resolve 后 `relative_to(<data_root>/artifacts/<profile_id>/downloads)`，越界即拒绝并隔离；profile_id 以事件文件所在目录为准并与事件内容比对；forward_pending 解析失败时记 warning 并移入 dead-letter 目录，不写入 processed 集合；两类磁盘信封加显式 `version` 字段，读取侧按版本兼容或隔离；ingest_download 改为返回带原因的结果并记结构化日志；补负例测试与 EventForwarder quarantine 分支测试。

### A5. Supervisor 对账按 Profile 隔离异常

- 来源：bundle_local_backend_supervisor, bundle_global_system_properties
- 位置：src/backend/cbrowser/supervisor/core.py:345-381；src/backend/cbrowser/supervisor/runner.py（serve_supervisor）
- 优先级：MEDIUM
- 详细判断理由：scan_and_reconcile_existing 的单 Profile 异常（缺 UDP 映射的遗留容器、端口恢复冲突）会中断整轮对账，且启动阶段直接让 Supervisor 退出、形成崩溃循环。
- 修复说明：per-profile 循环体包 try/except，记录该 Profile 的对账失败后 continue，只对 Docker 不可达等全局错误继续抛出；serve_supervisor 在初次对账失败时仍先拉起控制面、后台重试；补双 Profile 单元测试：一个 Profile 的 Stream 容器缺 UDP PortBindings，断言不抛错且另一个 Profile 的会话被恢复、端口正确还原。

### A6. Supervisor 小缺陷四项

- 来源：bundle_local_backend_supervisor
- 位置：src/backend/cbrowser/supervisor/resource_monitor.py:64-80；container_spec.py:44-82；control_server.py:172-210；runner.py:82-87
- 优先级：LOW
- 详细判断理由：资源采集漏捕 ValueError/TypeError，一个畸形 HostConfig 会拖垮全部 Profile 的配额下发；stream_labels 未把 config_version 转 str；status 端点在 try 外下标访问 API 响应，畸形 200 变成 500；runner 用裸 read_text 读 API token，绕过统一的权限/长度校验。
- 修复说明：\_collect 的 per-target except 补 (ValueError, TypeError, KeyError)；stream_labels 改 `str(config_version)` 并把返回类型标为 dict[str, str]；get_status 先用 pydantic 模型校验 API 响应，失败映射 503；runner 改用 `read_secret_file(token_file, label=..., minimum_bytes=32)`。

### A7. 启动恢复守卫测试改为断言真实上报通道

- 来源：bundle_local_backend_supervisor
- 位置：tests/unit/test_supervisor_startup_recovery.py:122-271
- 优先级：MEDIUM
- 详细判断理由：四个防误报退出守卫测试只断言 emit_event 未被调用，而生产 RecoveryCoordinator 根本不用该通道（合成退出走 report_terminal_observation），守卫回归时测试仍全绿。
- 修复说明：四个测试各补 `mock_core.report_terminal_observation.assert_not_awaited()`，与现有 emit_event 断言并列。

### A8. Gateway 接入与注册拒绝的顺序修正

- 来源：bundle_local_backend_stream_gateway
- 位置：src/backend/cbrowser/gateway/server.py:357-395,538-558；tests/integration/test_gateway_signaling.py
- 优先级：MEDIUM
- 详细判断理由：Viewer 接入在 ws.prepare 之后才检查 TURN 代次，失败时返回普通 503 Response（aiohttp 抛错）且 viewers 字典残留死条目；Agent 注册在驱逐旧 Agent 之后才检查代次，代次短暂不可用时会先断开健康会话再拒绝新注册。若 A42 的 spike 通过，代次检查随 TURN 机制删除，本项改为确认新流程中所有拒绝都发生在 prepare 与注册之前。
- 修复说明：所有拒绝检查（含代次）前移到 ws.prepare 与 registry.register 之前；在 test_gateway_signaling.py 增加用例：拒绝发生时客户端收到可识别的 503，Gateway 内无残留 viewer/agent 条目。

### A9. Stream Agent 心跳循环与捕获仲裁循环逐次隔离异常

- 来源：bundle_local_backend_stream_gateway, bundle_global_architecture, bundle_global_system_properties
- 位置：src/backend/cbrowser/stream_agent/agent.py:378-407；src/backend/cbrowser/stream_agent/policy.py:356-364；tests/unit/test_stream_agent_lifecycle.py
- 优先级：MEDIUM
- 详细判断理由：心跳循环的 try 包住整个 while，一次瞬时异常即永久停跳，约 30 秒后 Gateway 驱逐仍在推流的 Agent 并断开全部 Viewer；捕获仲裁循环同样一次异常即停，帧率可能卡在 30 FPS。
- 修复说明：两个循环改为循环体内 try/except Exception（记录后等待下一周期），只在连接关闭或停止时退出；循环任务挂 done 回调，意外退出时告警并按退避重启；补故障注入用例：selkies_video_state 首次抛错后恢复，断言心跳继续按节奏到达。

### A10. ICE restart 失败后复位 restart_pending

- 来源：bundle_local_backend_stream_gateway, bundle_global_architecture
- 位置：src/backend/cbrowser/stream_agent/ice_transport.py:340-512
- 优先级：MEDIUM
- 详细判断理由：start() 阶段失败或 commit 等待超时时 restart_pending 不复位，此后所有 prepare_restart 都被拒绝，轮换永久楔死，凭证过期后流中断。若 A42 的 spike 通过，本项随 ICE 代次机制删除而失效。
- 修复说明：在 start() 的失败出口与 wait_restart_commit 超时路径复位 restart_pending，清理 provisional gatherer 与凭证围栏状态并回到旧连接；补单元用例或 probe 变体：prepare_restart 成功后令 start() 失败，断言可再次 prepare_restart 并完成提交。

### A11. RTC 轮换时序参数启动期校验

- 来源：bundle_local_backend_stream_gateway
- 位置：src/backend/cbrowser/gateway/config.py:96-118；src/backend/cbrowser/rtc_config/models.py:14-28；tests/unit/test_gateway_config.py；tests/unit/test_rtc_config.py
- 优先级：MEDIUM
- 详细判断理由：lifetime/interval/lead/heartbeat 只做 float()，NaN、负数、interval≥lifetime 都能通过，后果是网关拒绝一切接入或轮换被静默关闭。heartbeat 校验与 A42 无关，其余在 A42 的 spike 通过时随轮换删除。
- 修复说明：RtcScheduleParams 加 model_validator：三参数均为有限正数，且 interval < lifetime、lead < lifetime；GatewayConfig.from_env 校验 heartbeat 超时为有限正数；补正例（非默认合法值被正确解析）与参数化负例。

### A12. Gateway 小缺陷五项

- 来源：bundle_local_backend_stream_gateway
- 位置：src/backend/cbrowser/gateway/rotation.py:160-176；server.py:210-220,704；registry.py:30；rtc_config/credential.py:1；stream_agent/ice_transport.py:85-140
- 优先级：LOW
- 详细判断理由：handle_agent_error 漏处理 \_pending_answers；quota 路由不校验即回 ok；ABI 守卫每次接入都实例化样例 PeerConnection；日志与 docstring 写死 30s、credential 模块自称有验证函数。rotation、ABI 守卫、credential 三处在 A42 的 spike 通过时随删除失效。
- 修复说明：handle_agent_error 遍历集合加入 \_pending_answers 并补用例；handle_supervisor_quota 用 SupervisorQuotaPayload.model_validate 校验，失败返回 400；ABI 守卫结果按进程缓存；超时文案引用配置值；credential.py docstring 改为“generation（验证由 coturn 完成）”；补 RotationCoordinator.tick 与完整握手提交的单元用例。

### A13. API 认证小缺陷三项

- 来源：bundle_local_backend_api_auth, bundle_global_system_properties
- 位置：src/backend/cbrowser/auth/service.py:307-371；auth/rate_limiter.py:65-77；api/internal_supervisor.py:30-36；auth/dependencies.py:12-16
- 优先级：MEDIUM
- 详细判断理由：每次被拒的自动化授权都写一条审计 DB 行，伪造 `cbat_` 令牌即可放大为无界 SQLite 写入；retry_after 未修剪全局队列导致 Retry-After 偏大；app.state 未初始化时内部守卫抛 AttributeError 变 500。
- 修复说明：authorize_automation 对 invalid_token_format 与 token_not_found 只记日志不落库，其余拒绝保持审计并加按来源限流；retry_after_seconds 先 \_trim 全局队列；require_supervisor 改 getattr，为 None 时走 503；get_auth_service 缺失时抛 HTTPException(503)；各补单元测试。

### A14. 生效 spec 与 blueprint 对齐代码和已落地决策

- 来源：bundle_local_docs_current, bundle_global_system_properties, bundle_global_evolution, bundle_global_architecture, bundle_cross_validation
- 位置：docs/specs/storage_and_artifacts.md:15-29,47；docs/blueprint/persistence.md:42,73；docs/blueprint/conventions.md:18-22；docs/blueprint/domain.md:12；docs/specs/v2_runtime_validation.md:133
- 优先级：HIGH
- 详细判断理由：生效 spec 把 t010 才交付的迁移工具写成已交付且 AC-002 已勾；blueprint 写 failure_count≥3 阻断（ADR 008/代码为第 4 次）、写 runtime_events 不随 Profile 级联（D1=A 已落地为级联）；conventions 的 schema 落点表引用四个不存在的路径；domain.md 的 ObservedState 与代码不一致；t001 spec 以现在时称 v2 代码未合入。
- 修复说明：storage_and_artifacts.md §2.2 改为“旧库迁移工具归 t010，当前未实施”，AC-002 取消勾选并注明 t010；§2.1 补 settings 表；persistence.md:73 改为“第 4 次异常阻断，见 ADR 008”；persistence.md:42 改为“runtime_events 随 Profile 级联删除，audit_events 独立保留”；conventions.md 落点表按磁盘真实结构重写；domain.md:12 改为 stopped/starting/running/stopping/error；v2_runtime_validation.md:133 加“截至 t001 验收时点”；blueprint 文首声明“与代码冲突时以代码与生效 spec 为准，并须同步修正”。

### A15. 入口文档写明现状（legacy 在跑、v2 未发布）

- 来源：bundle_local_docs_current, bundle_local_contracts_deploy, bundle_global_strategy, bundle_local_archive_spikes
- 位置：README.md（快速上手）；DOCKER_DEPLOYMENT.md:9-30,64-90；CHANGELOG.md:3-8；AGENTS.md:3
- 优先级：MEDIUM
- 详细判断理由：README/部署文档把 legacy 单容器表述为当前架构且无状态区分，快速上手在干净克隆上走不通（缺前端构建、基础镜像无来源、引用不存在的 healthcheck）；CHANGELOG 停在 0.1.9；AGENTS.md 仍写“控制租约管理”，与 ADR 007 矛盾。
- 修复说明：README 增“当前状态”小节（Docker 快速上手启动的是 legacy 单容器，v2 为预发布，正式部署见 t012）；DOCKER_DEPLOYMENT.md 文首加状态段并补前置步骤，删除 healthcheck 表述；CHANGELOG 增 Unreleased 节概述 v2 阶段；AGENTS.md:3 的“控制租约管理”改为“多页面连接管理（ADR 007 已废弃排他控制租约）”。

### A16. 文档小修五项

- 来源：bundle_local_docs_current
- 位置：docs/guides/browser_isolation_analysis.md:3,66-72；docs/blueprint/testing.md:34,45,58；docs/reviews/review_20261101_075819/adoption_decision.md:17,70,84；docs/v2_architecture_plan.md §8.4、§19.3；docs/blueprint/architecture.md:141-147
- 优先级：MEDIUM
- 详细判断理由：标为 Active 的隔离分析指南仍把已否决的 KasmVNC 升级列为待办；权威门禁命令硬编码个人目录；上一轮 adoption 的 D1 已决策仍挂在待决定标题下且行尾多一个 A；计划 §8.4/§19.3 正文无“已被修订块替代”标记；architecture.md 5.5 排在 5.4 前。
- 修复说明：guides 状态改 Superseded 并链接 blueprint/architecture.md 与 ADR 007，删除 KasmVNC TODO；testing.md 门禁命令去掉个人路径（按 A41 统一迁入 scripts/run_gates.sh）；上轮 adoption_decision 把 D1 标为“已决策：A（2026-11-01）”并删除重复的 A；计划 §8.4、§19.3 节首各加替代标记；architecture.md 两节编号对调并同步引用。

### A17. t009 过程总账补记 2026-11-02 决定

- 来源：bundle_followup_q_strategy_03
- 位置：docs/tasks/t009_v2_full_acceptance/note.md
- 优先级：LOW
- 详细判断理由：t009 front matter 已改依赖，但实施笔记仍是空白模板，依赖变更与 AC-003 降级只记在 handoff。task 总账是状态权威，应能独立复述。
- 修复说明：在 t009 note.md 实施笔记补一条：2026-11-02 用户决定依赖改为 t013、AC-003 改为真实 Chrome 手动清单、p015 以 transferred 转入本 task，出处 docs/archive/handoff.md 对应节与 commit 856757d。

### A18. 前端 v2 界面缺陷六项

- 来源：bundle_local_frontend_shell, bundle_local_frontend_features
- 位置：src/frontend/tailwind.config.ts:8-26（AppLayout.tsx:235-265 及 features 下 7 个文件）；features/profiles/BrowserSessionPage.tsx:69-71；features/profiles/ProfileDetailPage.tsx:38-50；features/profiles/useProfilesQuery.ts:168-183；shared/api/sse.ts:113-160；features/browser-session/adapter.ts:398-418
- 优先级：MEDIUM
- 详细判断理由：未定义的 primary 色板使新建按钮几乎不可见、选中态无高亮；会话页启动失败被吞掉无提示；详情页后台刷新覆盖未保存的编辑；“应用并重启”轮询对单次瞬时错误零容忍；SSE 流结束时丢弃最后一帧；ICE 收集超时路径不移除监听器。
- 修复说明：tailwind.config.ts colors 增加 primary 与 primary-foreground（对齐 accent 体系），并加构建后校验关键工具类存在；BrowserSessionPage 渲染启动错误条；ProfileDetailPage 改为脏字段跟踪，只回填未被修改的字段；waitForRuntimeState 容忍连续 3 次失败并区分轮询失败与超时；sse.ts done 后 flush decoder 并 dispatch 残留帧；adapter.ts 在统一 settle 中移除监听；补相应 vitest 用例。

### A19. 前端生成物与依赖清理

- 来源：bundle_local_frontend_shell, bundle_local_repo_ops
- 位置：src/frontend/tsconfig.tsbuildinfo；src/frontend/tsconfig.json；.gitignore；src/frontend/package.json:26-28；docs/blueprint/testing.md:168
- 优先级：MEDIUM
- 详细判断理由：tsconfig.tsbuildinfo 是生成产物却入库，内容停在重组前布局，每次构建都弄脏工作区；react-router 与 react-router-dom 双直依赖且版本错位，实际只用后者。
- 修复说明：.gitignore 增加 `*.tsbuildinfo`，`git rm --cached src/frontend/tsconfig.tsbuildinfo`，tsconfig.json 设 `tsBuildInfoFile` 指向 node_modules/.tmp，删除 testing.md 中还原该文件的步骤；package.json 删除 react-router 直依赖，`npm install` 更新 lock，`npm ls react-router` 确认单实例。

### A20. E2E 门禁：必需模式与构建新鲜度

- 来源：bundle_local_tests_e2e_supervisor, bundle_local_tests_e2e_stream_frontend, bundle_local_tests_integration_fixtures, bundle_global_system_properties, bundle_global_evolution, bundle_cross_validation
- 位置：tests/e2e/（各文件开头的 pytest.skip 门控）；tests/fixtures/frontend_app_probe/harness.py:19-39；tests/fixtures/frontend_probe/host_builder.py:17-31；scripts/verify_frontend_dist.py
- 优先级：HIGH
- 详细判断理由：supervisor 与 stream 两组 E2E 缺镜像环境变量时整层 skip，门禁可全绿零覆盖；前端 E2E 只拷贝磁盘上既有 dist，不构建也不校验新鲜度，改源码后会对着旧构建出结果。
- 修复说明：新增 tests/e2e/conftest.py：`CBROWSER_E2E_REQUIRED=1` 时会话开始即校验各 lane 所需环境变量，缺失 `pytest.exit` 并列出缺项；构建时把前端源文件（src/frontend/src、index.html、vite 配置、package-lock）的内容哈希写入 dist 内的构建戳文件，两个 harness 比对当前源哈希与构建戳，不一致即报错提示重新构建（不依赖 mtime）；host_builder docstring 与实际保证一致；本地门禁入口（A41）默认开启必需模式。

### A21. E2E 断言小修四项

- 来源：bundle_local_tests_e2e_supervisor, bundle_local_tests_e2e_stream_frontend
- 位置：tests/e2e/test_supervisor_namespace_policy_e2e.py:541-557；test_supervisor_retry_e2e.py:355-530；test_supervisor_startup_recovery_e2e.py:14-22；test_stream_selkies_tokens_e2e.py:94-105
- 优先级：MEDIUM
- 详细判断理由：IPv6 fail-closed 断言被 `if v6_b/if v6_c` 包裹，无 IPv6 地址时静默跳过；退避断言只有下限；startup_recovery docstring 描述已被取代的旧语义；Selkies token 测试服务发布到 0.0.0.0。
- 修复说明：namespace_policy 先 `assert v6_b and v6_c` 再无条件执行阻断探针；retry 退避断言加宽松上限 `target + max(5, target*0.5)`；docstring Case 3 改为当前诊断事件语义；`-p {port}:{port}` 改为 `-p 127.0.0.1:{port}:{port}`。

### A22. Supervisor 测试改用真实 Gateway，删除重写的 Gateway 夹具

- 来源：bundle_local_tests_integration_fixtures, bundle_cross_validation
- 位置：tests/fixtures/supervisor_recovery_probe/gateway_fixture.py；gateway_contract.md；tests/fixtures/supervisor_container_probe/gateway_container.py；tests/fixtures/supervisor_recovery_probe/offline_fixture.py:691
- 优先级：HIGH
- 详细判断理由：SupervisorGatewayFixture 从头重写了 Gateway，用自己跟踪的 viewer 连接计算可见性，而生产 Gateway 只返回 Agent 最近的健康报告；supervisor 离线/恢复套件因此验证的是分叉语义。夹具的容器入口还绕过自身生命周期，start() 忽略就绪结果。重写的替身就是持续漂移的技术债。
- 修复说明：supervisor 的集成与离线/恢复套件改用生产 `create_gateway_app` 加 FakeApiService（test_gateway_fixtures.py 的 GatewayHarness 已有范式），容器黑盒用真实 gateway 镜像；需要的观测能力（如可见性快照）在生产 Gateway 以正式接口提供；删除 gateway_fixture.py、gateway_contract.md 与 gateway_container.py；跑全部 supervisor 集成与 E2E 验证。

### A23. 仓储测试改用真实迁移建表

- 来源：bundle_local_tests_unit_supervisor_runtime, bundle_global_evolution
- 位置：tests/unit/test_domain_and_repository.py:33-82
- 优先级：HIGH
- 详细判断理由：domain/repository 测试用 Base.metadata.create_all 建表，模型与 Alembic 迁移的漂移结构性不可检——这正是 t010 的核心风险。
- 修复说明：db_context fixture 改为 `run_database_migrations(temp_db_path)` 后再建 engine；另加一条测试：迁移后的 schema 与 Base.metadata 逐表逐列一致（Alembic autogenerate compare 无差异）。

### A24. 单元测试卫生小修

- 来源：bundle_local_tests_unit_stream_api, bundle_local_tests_unit_supervisor_runtime
- 位置：tests/unit/test_stream_ice_transport.py:1-16,155-161；test_secret_file_permissions.py:36；test_selkies_file_transfers.py:31；test_stream_selkies_tokens.py:257；test_control_error_redaction.py:33-40；test_refactor_behavior_equivalence.py:99-108；test_supervisor_core.py:1-9；test_supervisor_startup_recovery.py:63-64；test_runtime_protocol.py:19-33
- 优先级：MEDIUM
- 详细判断理由：进程全局 relay-only 标志不还原；两处 docstring 声称不存在的覆盖；token 读取只断言非 None；入口脚本读取依赖 CWD；脱敏测试只捕获 WARNING 以上；墙钟容差只有 100ms；schema 测试用 CWD 相对路径且弱于导出比对测试。
- 修复说明：relay-only 标志用 autouse fixture 快照还原；docstring 只描述实际覆盖并指向承担覆盖的文件，删去未验证的“2s backoff”；token 断言等于写入值；路径锚定 `Path(__file__).resolve().parents[2]`；脱敏测试改 DEBUG 级并钉死各动作的状态码；墙钟断言改为注入时钟；删除被字节比对测试完全覆盖的 test_runtime_protocol 弱测试。

### A25. 归档 spike 只读说明与 secret 写出路径忽略

- 来源：bundle_local_archive_spikes, bundle_followup_q_system_properties_01
- 位置：docs/archive/spikes/（新增 README.md）；.gitignore
- 优先级：MEDIUM
- 详细判断理由：归档 spike 代码含关闭 X11/PulseAudio/Selkies 鉴权的入口与无认证控制面，早期报告的复现路径指向已不存在的 docs/spikes/，report_same_url.md 无替代标记；harness 会把 TURN secret/agent token 写进自身目录且未被 gitignore（精查确认从未入库）。归档区只准新增，新增目录级说明与忽略规则符合规则。
- 修复说明：新增 docs/archive/spikes/README.md：全部 spike 为历史证据、勿在仓内运行（先复制到 .scratch）、列出含关闭鉴权入口与无认证控制面的文件、docs/spikes/ 路径对应 docs/archive/spikes/、s008 report_same_url.md 已被 report.md 替代、列出跨 spike 的重复文件；.gitignore 增加三个写出文件名的规则。

### A26. 接口契约完整化

- 来源：bundle_local_backend_api_auth, bundle_local_contracts_deploy, bundle_global_architecture, bundle_local_backend_stream_gateway
- 位置：schemas/openapi/cbrowser_v1.json；schemas/stream/agent_protocol.json；scripts/export_openapi.py；scripts/export_stream_protocol.py；src/backend/cbrowser/api/v1/\*；src/backend/cbrowser/stream_agent/protocol.py:154-330；src/backend/cbrowser/stream_agent/config.py:151-162
- 优先级：MEDIUM
- 详细判断理由：OpenAPI 未声明任何 securityScheme 与 CSRF 头，系统性漏报 401/403/404/413/429/507；内部面与 CDP WebSocket 不在任何契约内；stream 协议只导出信封，payload 是 dict[str, Any]，承载 TURN 凭证的类型不受契约约束；ICERestartOffer/AnswerPayload 是与线上形态矛盾的死模型；FPS 在配置与注册载荷两层口径不一。契约只覆盖读路径的 happy path。
- 修复说明：FastAPI 以 Security 依赖声明 cookie 会话、CSRF 头与内部 Bearer 三个 securityScheme，各路由用 `responses=` 声明实际可达错误码（引用 ErrorResponse），加守卫测试“契约响应码 ⊇ 实现可达响应码”；新增 schemas/openapi/cbrowser_internal.json 导出内部面并纳入漂移测试；stream payload 改为按 action 判别的联合类型并全部导出，Gateway/Agent 收发两侧用模型校验，删除或修正死模型；FPS 只保留一个权威（配置层），注册载荷按同一规则校验；契约变更后重新生成前端类型。在 A1 之后执行。

### A27. 正式拓扑与镜像要求写入 t012 契约

- 来源：bundle_global_architecture, bundle_followup_q_architecture_02, bundle_local_contracts_deploy, bundle_local_tests_integration_fixtures, bundle_cross_validation
- 位置：docs/tasks/t012_v2_docker_release/task.md；config/docker/Dockerfile:1-2；compose.yaml；tests/fixtures/gateway_probe/topology.py；tests/fixtures/frontend_probe/harness.py；tests/fixtures/supervisor_container_probe/*.Dockerfile*
- 优先级：HIGH
- 详细判断理由：出厂镜像跨代拼接（v2 前端装进 legacy 后端镜像）、FROM cbrowser:latest 自引用未钉版、五服务拓扑只存在于互相分叉的测试夹具、API 无生产 Dockerfile、turnserver.conf 三处生成、缺 .dockerignore、依赖未锁哈希、stream 镜像保留编译链、supervisor 以 root 运行无说明、.env.example 双份。它们属于 t012 的交付物，现在单独改会被重写；但必须写进 t012 契约，否则会在 t012 中被遗漏。
- 修复说明：在 t012 task.md 契约区补充范围与 AC：拓扑由单一权威工件（正式 compose 或拓扑清单）定义，测试夹具消费该工件而不各自重写，turnserver.conf/Caddyfile 由同一生成器产出；五个常驻服务（含 API）的生产 Dockerfile 同处 config/docker/ 且基础镜像 digest 钉版、产物 tag 与基础 tag 分离；夹具镜像 FROM 生产镜像；每个镜像有白名单 .dockerignore；Python 依赖 `--require-hashes`；stream 镜像多阶段构建；supervisor 的特权需求写明（最小 capability）；单一 .env.example 覆盖全部 v2 变量；构建期断言前端与后端 API 代际一致；部署文档演练纳入验收。并注明：t012 之前不要从当前源码重建 legacy 镜像。

### A28. 删除单值死字段 runtime_mode/viewer_mode

- 来源：bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/domain/models.py:79-80,375-376,412-413；src/backend/cbrowser/adapters/database/{models,repository}.py；schemas/openapi/cbrowser_v1.json；src/frontend/src/shared/api/generated/cbrowser_v1.d.ts
- 优先级：MEDIUM
- 详细判断理由：v2 中 runtime_mode 只能是 `docker`、viewer_mode 只能是 `webrtc`（Literal 单值），却在 DB 列、领域模型、API 响应和快照中全程携带；repository 读回硬编码、update 不回写，测试数据恰好等于唯一值。审阅指出的读写分叉不可达，但字段本身是不承载信息的死配置（native 与 VNC 模式已被 v2 计划删除）。
- 修复说明：新增 Alembic 迁移删除两列；领域模型、ORM、repository、API 响应与快照去掉两字段；重新导出 OpenAPI 与前端类型；t010 的旧库迁移映射忽略这两个旧字段（在 t010 task.md 注明）；补迁移升级测试。

### A29. API 认证与事件流加固

- 来源：bundle_local_backend_api_auth
- 位置：src/backend/cbrowser/auth/service.py:143-244；src/backend/cbrowser/api/app.py:161-170；src/backend/cbrowser/api/runtime_coordinator.py:82-165
- 优先级：LOW
- 详细判断理由：自动化令牌无过期只能手动吊销；过期会话行从不清理；/docs 与 /openapi.json 默认无认证开放；协调器把 SecretStr 令牌摊平为 str；SSE 订阅的初始快照与实时队列存在乱序窗口，快照占用序号却不入历史，续传语义含糊。
- 修复说明：自动化令牌增加可选 expires_at（创建时可设，界面显示），授权按过期拒绝；登录时与启动时清理过期会话；docs/redoc/openapi 默认关闭，仅 `CBROWSER_API_DOCS=1` 时开启；协调器内部保留 SecretStr，仅构造请求头时取值；SSE 订阅先生成快照再注册队列并补发间隙事件，快照事件写入历史并明确 Last-Event-ID 语义，补时序测试。

### A30. Gateway 与 Stream 加固

- 来源：bundle_local_backend_stream_gateway
- 位置：src/backend/cbrowser/gateway/server.py:291,496-538；src/backend/cbrowser/gateway/api_client.py:19-27；src/backend/cbrowser/rtc_config/service.py:28-97；docs/blueprint/security.md
- 优先级：LOW
- 详细判断理由：Viewer 信令入口无限流，每次尝试都放大为内部 API 调用；两处密钥文件读取绕过统一的权限校验读取器；服务端 WebSocket 未显式设置消息上限；client TURN 凭证按 Profile 共享且有效期 24 小时，这一设计取舍未记录。
- 修复说明：viewer-authorize 失败按来源与 Profile 节流，超限 429；GatewayApiClient 与 RtcConfigService 改用 read_secret_file；两处 WebSocketResponse 显式设置 max_msg_size（与 Agent 侧 MAX_FRAME_SIZE 对齐）；TURN 凭证取舍写入 security.md（若 A42 的 spike 通过，TURN 相关部分随删除失效）。

### A31. Supervisor 加固

- 来源：bundle_local_backend_supervisor
- 位置：src/backend/cbrowser/supervisor/control_server.py:88-92,238-247；core.py:842；docker_adapter.py:646；operation_journal.py:23-31；metrics.py:30-44
- 优先级：LOW
- 详细判断理由：内部 URL 拼接未转义 profile_id；含完整 ProfileConfig（可能含代理凭证）的 snapshot.json 以 0644 写入；控制面 CDP WebSocket 先 accept 后鉴权；操作日志损坏时停止路径被永久阻断；阶段指标只输出累计值却被当作区间值阅读。
- 修复说明：所有拼入 URL 的 id 统一 `quote(..., safe="")`；snapshot.json 以 0600 写入并 chown 给运行时 uid（Supervisor 有该权限）；CDP WebSocket 在 accept 前校验 token，失败直接关闭；journal 损坏文件改名隔离并按无记录处理；指标同时输出累计与区间值并在字段名区分。

### A32. Runtime 与存储加固

- 来源：bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/runtime_agent/{runner,event_storage,agent}.py；src/backend/cbrowser/services/{artifact_service,profile_service}.py；src/backend/cbrowser/adapters/filesystem/artifact_store.py:205-209；src/backend/cbrowser/adapters/database/{repository,migrations}.py；tests/unit/test_artifact_service.py
- 优先级：MEDIUM
- 详细判断理由：下载事件文件无保留策略且每次全量读取；Artifact 配额检查与写入非原子；Pulse/X11/Openbox 配置用共享固定 /tmp 路径并无条件删 X 锁；Pulse cookie 与 Xauthority 为 0644；artifact_id 不做路径组件校验；Runner 改写进程级 os.environ；Profile 锁字典只增不减；幂等回放逻辑四处复制；迁移入口的 PRAGMA 注释与实际不符。均为结构性小债。
- 修复说明：下载事件按实例保留最近 N 条，去重改用增量维护的索引文件，/events/downloads 分页；ArtifactService 增加 per-profile 锁并在写事务内断言配额，补并发上传用例；Runner 的 pulse/openbox/cookie 路径收进 run_dir，删 X 锁前校验锁内 PID；Pulse cookie 与 Xauthority 改 0600（Browser 与 Stream 容器同为 uid 1000，以 E2E 验证）；artifact_id 施加与 profile_id 同级的单组件校验并补穿越用例；Runner 以显式 env 字典传给子进程；删除 Profile 时清理锁条目；抽出单一 `_replay_if_committed` 供四处复用；迁移入口删除无效 PRAGMA 并修正注释。

### A33. 统一文件所有权模型，删除全局可写回退

- 来源：bundle_local_backend_runtime_adapters, bundle_local_tests_unit_stream_api, bundle_local_backend_supervisor
- 位置：src/backend/cbrowser/services/profile_service.py:96-118；src/backend/cbrowser/supervisor/docker_adapter.py:263-286,378-390；tests/unit/test_profile_copy_reset.py:264-271；tests/unit/test_artifact_service.py
- 优先级：MEDIUM
- 详细判断理由：Profile 复制在 chown 失败时把整个浏览器数据目录置为 0777/0666（含 Cookie 与登录数据）；Supervisor 的引擎缓存与“legacy world mode”回退同样 0777；测试还把世界可写断言为预期，锁死了这种权限。这是为兼容 macOS 非 1000 uid 开发路径留下的兼容层，按“不留兼容层”的原则应移除。
- 修复说明：新增 ADR：API、Supervisor 写入的运行时数据与 Browser/Stream 容器统一归属 uid 1000（Supervisor 以特权完成 chown，API 在容器内以 uid 1000 运行）；删除 0o777/0o666 与 legacy world mode 回退，chown 失败直接报错；目录 0700/0750、文件 0600/0640；测试改为断言精确权限；开发与测试路径改为在容器内或匹配 uid 下运行 API。与 t012 的部署用户设计一致。

### A34. 前端客户端与会话加固

- 来源：bundle_local_frontend_shell, bundle_local_frontend_features
- 位置：src/frontend/src/shared/api/{client,sse}.ts；src/frontend/src/features/browser-session/{useBrowserSession,adapter,BrowserSessionView.test}.ts(x)；src/frontend/src/features/profiles/useProfilesQuery.ts；src/frontend/src/app/providers.tsx；src/frontend/src/i18n.tsx；src/frontend/index.html
- 优先级：MEDIUM
- 详细判断理由：ApiClient 无超时与取消；Idempotency-Key 只在两处发送且每次现生成，重试无法去重；SSE 遇 401 无限重连；ApiClient 接受绝对 URL 仍附凭据与 CSRF 头；ApiError 丢弃错误码与 retryable；Web Locks 不可用时只表现为一般信令失败；会话页运行时检查绕过 ApiClient 并把网络失败当作就绪（测试便利路径泄漏进生产）；视图测试用真实计时器；useProfileEventsSync 的启停不对称；切换语言不更新 document.lang，存储键沿用上游前缀。
- 修复说明：ApiClient 按请求类型设超时（普通请求默认值，上传与长操作单独配置），合并外部 signal；所有写操作由 mutation 层生成并在重试时复用幂等键；SSE 增加 onUnauthorized，401 时停止重连并触发登出；request 入口强制同源；ApiError 携带 errorCode、retryable、detail，react-query 重试按其决策；Web Locks 缺失时进入专门诊断阶段并给出文案；useBrowserSession 改走 ApiClient，网络失败进入 runtime_not_ready 并显示原因，删除测试便利分支；宽限期与健康检查定时器可注入，测试改 fake timers；useProfileEventsSync 清理时调用 stop；I18nProvider 同步 document.documentElement.lang，存储键迁移为 cbrowser.locale（读旧写新）；补相应测试。

### A35. 两个被静默放弃的测试缺口补齐

- 来源：bundle_local_archive_tasks
- 位置：tests/e2e/test_frontend_session_e2e.py（关闭页面后容器状态断言）；src/backend/cbrowser/supervisor/artifact_forwarder.py 与 runtime_agent 的下载文件名截断路径
- 优先级：MEDIUM
- 详细判断理由：p011 的 f012（会话 E2E 关闭页面后接受 created 状态，无法区分未停止与被重建）被标为 resolved 但未做；t008_test_f009（255 字符文件名截断无测试，截断被移除时 422 会使下载被永久标记已处理）以流程便利为由撤回且无承接。归档文件不改，直接在现行测试中补齐。
- 修复说明：test_frontend_session_e2e 的状态断言收紧为 running 且实例 id 不变；新增单元测试：超长文件名的下载事件经转发与 ingest 后被正确截断并登记，不被标记为已处理而丢失。

### A36. E2E 与集成测试：夹具与前置条件统一

- 来源：bundle_local_tests_e2e_supervisor, bundle_local_tests_e2e_stream_frontend, bundle_local_tests_integration_fixtures
- 位置：tests/e2e/*；tests/integration/*；tests/fixtures/{gateway_probe,frontend_probe,stream_probe,supervisor_recovery_probe}/\*
- 优先级：MEDIUM
- 详细判断理由：前置条件校验在各文件重复且语义漂移（skip/fail/KeyError 并存），TURN 镜像摘要硬编码 6 处；测试互相用 importlib 盗用对方 fixture、sys.path 注入；两份分叉的标签身份 shim，身份仲裁测的是测试专用 shim 而非生产 adapter；多观看者主用例用文件内重写的 GatewayMockServer；Selkies token 注入由测试仿真；browser_oracle、probe 启动样板多处复制；单个 E2E 函数约 1190 行；Selkies 私有 API 访问分散。
- 修复说明：抽出共享 prerequisites 模块（统一“缺失=skip、格式错=fail、必需模式=硬失败”，镜像摘要集中一处并注明来源）；fixture 迁入 tests/e2e/conftest.py 与 tests/integration/conftest.py，删除 importlib 盗用与 sys.path 注入；身份与信令测试改为驱动构建产物中的生产 adapter，删除测试 shim（按 A47 探针统一由测试注入）；stream 多观看者用例迁到真实 Gateway 拓扑，token 注入经真实 Stream Agent 验证并断言 viewer 被降级；browser_oracle 与 probe 启动统一为单一实现；巨型用例按 AC 阶段拆分并共享 module 级拓扑；Selkies 私有 API 访问收敛到每类探针一个适配模块。

### A37. E2E 与集成测试：时序与断言可信度

- 来源：bundle_local_tests_e2e_supervisor, bundle_local_tests_e2e_stream_frontend, bundle_local_tests_integration_fixtures
- 位置：tests/e2e/test_supervisor\_{resource_policy,namespace_policy,startup_recovery,offline_recovery,recovery,event_shutdown}_e2e.py；tests/e2e/test_{gateway_ac001_auth,gateway_ac007_visibility,frontend_media,frontend_session,frontend_app,frontend_app_auth,browser_runtime,stream_runtime,runtime_coordinator,runtime_profile_defaults,frontend_build_wiring,frontend_adapter_build,frontend_session_vendor}\*.py；tests/integration/test_gateway\_{rotation,signaling}.py；tests/fixtures/stream_probe/chrome_relay.py
- 优先级：MEDIUM
- 详细判断理由：大量固定 sleep 后单次断言（资源策略、startup gate、健康传播、Cookie 落盘、rearm、可见性）；精确零增量与绝对 FPS 阈值；状态三选一、日志全文子串、状态码三选一等宽口径断言；代次提交以日志文案为判据；finally 中断言掩盖原始失败；就绪等待超时后静默穿透；冻结恢复不验证帧增长；独立静音未验证；构建接线以文本与写死的 hash 文件名断言；延迟只记录不设上限；profile defaults 宿主层只做回声校验；集成与 E2E 用例断言或注入 SupervisorCore/RecoveryCoordinator 私有状态、用 SimpleNamespace 手工拼假 core、直接改 app.state 内部对象制造场景。
- 修复说明：固定 sleep 全部改为带超时的条件轮询或事件；私有状态断言改为 API 运行时状态、WS 帧、/proc 计数等可观察结果，场景经公开接口触发，假 core 改为构造真实 SupervisorCore；零增量与 FPS 改为相对基线并允许在途帧；状态与状态码收敛为契约规定的唯一值；日志断言改为结构化字段与本次请求时间窗；提交判据改为可观察协议结果（rtc_config 代次或 Agent 确认状态）；零泄漏校验移出 finally 作为独立步骤；统一 wait_ready 辅助（超时抛错并附日志）；冻结恢复轮询 framesDecoded 增长；静音期间逐页断言音频增量；hash 文件名从 vendor 产物动态解析，verify 脚本的合成用例移入 tests/unit；首帧与输入延迟设宽松上限；profile defaults 容器脚本输出分阶段结构化结果供宿主逐项断言，设置页交互改为条件等待。

### A38. E2E 与集成测试：资源隔离与卫生

- 来源：bundle_local_tests_e2e_supervisor, bundle_local_tests_e2e_stream_frontend, bundle_local_tests_integration_fixtures
- 位置：tests/e2e/*；tests/integration/test\_{v2_api_subprocess,automation_cdp_flow,normal_exit_replay}.py；tests/fixtures/{gateway_probe/topology.py,gateway_probe/evidence.py,stream_probe/*,runtime_probe/test_mitshm.c,supervisor_recovery_probe/offline_fixture.py}
- 优先级：MEDIUM
- 详细判断理由：UDP 端口、X 显示号、TURN relay 区间、固定名探针容器与固定主机端口在用例间重叠，只能单机串行独占运行；空闲端口获取有 TOCTOU；集成测试把状态写入仓内 .scratch；evidence 落盘 resume_key 与全部 WS 帧；夹具 secret 目录 0777、turnserver.conf 0644、共享内存 0777；Supervisor 容器依赖 host.docker.internal 而未配 host-gateway；公网出口探针写死 1.1.1.1；破坏性用例修改 module 级共享 Profile 不恢复；负向探针调用 DockerAdapter 私有方法并自建沙箱；namespace 用例清理失败无痕。
- 修复说明：端口、显示号、容器名与网络由 run 前缀派生或由 Docker 分配后回读，删除固定主机端口；集成测试全部改用 tmp_path；evidence 对 resume_key 只存指纹、WS 帧只存类型与长度；夹具 secret 目录 0700、配置 0600、shm 0600；RealSupervisorContainer 设 `extra_hosts={"host.docker.internal": "host-gateway"}`；出口探针目标可配置，不可达时区分环境无出口；破坏性用例改用独立 Profile；隔离探针经生产容器创建路径或真实 Profile 容器内 exec；所有 teardown 按前缀复查残留并以独立步骤报告。

### A39. 单元测试架构整改

- 来源：bundle_local_tests_unit_stream_api, bundle_local_tests_unit_supervisor_runtime
- 位置：tests/unit/*（重点：test_stream_agent_lifecycle.py、test_stream_transport_hardening.py、test_api_runtime_coordinator.py、test_runtime_coordinator\_*.py、test_supervisor\_*recovery*.py、test_docker_offload.py、test_baseline_fixture_regressions.py、test_automation_cdp.py、test_supervisor_normal_exit_observation.py、test_supervisor_event_cursor.py）
- 优先级：MEDIUM
- 详细判断理由：安全相关的负断言依赖固定 0.05–0.1 秒 sleep，可在未处理报文时真空通过；大量测试读写私有成员、替换被测类自身方法、按内部调用顺序编排 side_effect；卸载与协调器测试依赖墙钟阈值与 sleep 轮询；共享 .scratch 目录与后缀碰撞的 rmtree；返回已关闭 httpx 客户端的 helper；导入期 sys.path 污染与跨测试模块 fixture；root 下失效的 chmod 故障注入；样板复制；SSE 只做子串断言；硬编码端口；版本测试条件分支；重复断言与命名漂移。
- 修复说明：负断言改为“发送哨兵有效报文、等其生效后再断言无效报文未生效”或等待处理计数；在生产类上补必要的可观测公开接口（任务状态、处理计数、注入时钟），测试只走公开面；以 asyncio.Event 或 task done 回调替代 sleep 计数，卸载测试改为线程内阻塞期间的事件 rendezvous；新增 tests/unit/conftest.py 承载共享 fixture，删除 sys.path 注入与跨模块导入；全部改用 tmp_path，UDS 用短路径的 mkdtemp；故障注入改为 monkeypatch 写函数；端口统一绑定 0；SSE 解析 data 为 JSON 后逐字段断言；版本测试 stub importlib.metadata；删除重复断言与重复行，名称与覆盖范围一致。

### A40. 仓库卫生

- 来源：bundle_local_repo_ops, bundle_local_contracts_deploy, bundle_local_docs_current
- 位置：.gitattributes:1-3；scripts/vendor_selkies_web.py:37-152；docs/specs/runtime_persistence.md:90
- 优先级：LOW
- 详细判断理由：.gitattributes 的 beads merge 属性悬空（.beads 整目录被忽略）；没有 text/eol 规则，容器入口脚本行尾靠约定；vendor 脚本解包不防路径穿越、清单校验不拒绝清单外文件，`--image` 路径无哈希校验；spec 中写入形似真实凭据的合成 canary，会反复触发 secret 扫描。
- 修复说明：删除悬空的 beads 属性；补 `* text=auto`、`*.sh text eol=lf`、Dockerfile 与 \*.c eol=lf，`git add --renormalize`；vendor 解包拒绝含 `..` 或绝对路径的条目并断言最终路径在目标目录内，verify_manifest 增加“目录文件集合 = 清单集合”（明确的补丁白名单除外）；spec 中 canary 改为抽象描述，真实夹具值只留在测试代码。

### A41. 交付流水线（CI、本地门禁入口与 release）

- 来源：bundle_local_repo_ops, bundle_local_frontend_shell, bundle_global_strategy, bundle_global_system_properties, bundle_cross_validation
- 位置：.github/workflows/ci.yml:8-39；.github/workflows/release.yml:3-6,50-207,563-595；docs/blueprint/testing.md
- 优先级：HIGH
- 详细判断理由：ci.yml 两个 job 引用重组前的 `backend/`、`frontend/` 路径，每次 push 都在第一步失败，仓库实际没有 CI；release.yml 依赖已删除的 `packaging/` 脚本、Docker 构建默认找根目录 Dockerfile、安装包校验文件未签名，整条发布链不可用且产物形态已被 v2 计划废弃。Docker 与真实 Chrome E2E 依赖本机 macOS/OrbStack（Linux x86 验证已由用户豁免），无法放进 GitHub 托管 runner；公开仓也不宜挂自托管 runner。
- 修复说明：（用户决策 A）三层门禁：ci.yml 改为现行布局，在 ubuntu-latest 上跑全部可移植层（契约、legacy 与 v2 单元、tests/integration、前端 vitest 与 `npm run build`），action 钉完整 SHA；新增 `scripts/run_gates.sh` 作为本地全量门禁唯一入口（含 E2E 必需模式，见 A20），testing.md 只引用该脚本；release.yml 删除，由 t012 重新定义发布。
- 用户决策：A（原 D2，2026-11-02 用户在本文档填写）

### A42. 按“单机单人”重定架构：多主机媒体机制的去留

- 来源：bundle_global_strategy, bundle_global_evolution, bundle_global_architecture, bundle_followup_q_strategy_01, bundle_followup_q_strategy_03, bundle_followup_q_evolution_01
- 位置：docs/v2_architecture_plan.md；docs/blueprint/decisions.md；src/backend/cbrowser/gateway/rotation.py；src/backend/cbrowser/rtc_config/；src/backend/cbrowser/stream_agent/ice_transport.py；coturn 相关配置与夹具
- 优先级：HIGH
- 详细判断理由：精查确认全仓没有任何远程/多用户/多主机目标，记录一致为“仅本人单机使用”。但架构仍按多主机流媒体服务维护：coturn、TURN 凭证 24h/12h 轮换、同 PeerConnection 的 ICE 代次接管——后者靠给 Selkies 2.1.0 私有 ABI 打补丁实现（升级 Selkies 即失效），并且是本轮多条缺陷的来源（restart_pending 楔死、时序参数无校验、等待清理遗漏）。项目已有 `local` 直连模式（UDP mux 端口发布到 127.0.0.1），但“同机 Chrome 不经 TURN 直连”在多页面、重连、可见性暂停等场景下没有完整 E2E 证据。收尾链 t009→t012 全部 backlog，审阅判定为排序问题。去留属于长期架构取舍。
- 修复说明：（用户决策 B）证据门控的简化：先做一个 spike，用 local 直连模式在真实 Chrome + OrbStack 上验证多页面、刷新/复制标签、断线 resume、可见性暂停、媒体与输入全链路；通过则删除 coturn、TURN 凭证与轮换、ICE 代次接管及 Selkies 私有 ABI 补丁（含对应测试、夹具与文档），Gateway 只保留信令路由，t012 拓扑相应收缩，并以 ADR 记录；不通过则保留现有机制但冻结、不再扩展，并把失败事实写入 findings。无论结论如何，decisions.md 都新增 ADR 记录单机单人为长期部署包络，计划修订块同步；新功能暂停，按 t009→t010→t011→t012 收尾。A8、A10、A11、A12、A30 中与 TURN/轮换相关的部分等本项 spike 结论后再做（spike 通过则随删除失效）。
- 用户决策：B（原 D3，2026-11-02 用户在本文档填写）

### A43. .repo_template 工具链缺陷的处理

- 来源：bundle_local_template_scripts_state, bundle_local_template_scripts_ops, bundle_local_template_tests, bundle_local_template_support, bundle_global_architecture, bundle_global_evolution, bundle_global_strategy, bundle_followup_q_evolution_02, bundle_followup_q_strategy_02, bundle_local_repo_ops, bundle_cross_validation
- 位置：.repo_template/scripts/repo_task/ledger.py:22-49 等（共 59 条，见映射）
- 优先级：HIGH
- 详细判断理由：模板工具链共 59 条 finding，最高为 ledger 读取遇 OSError 返回空列表、可导致 attempt 号重复分配（High，交叉证伪 agree）；另有 repo_cleanup 嵌套 node_modules 不剪枝、link-skills 无事务 rmtree、purge 拒绝护栏在测试中被 stub 掉、门禁命令在 task 流程中从不执行、本仓未入库 sync_manifest.json 等。AGENTS.md 规定消费仓不得自行修改 .repo_template，缺陷须在模板仓解决。
- 修复说明：（用户决策 A）用 template-issue-report skill 向模板仓提交一份脱敏汇总 issue。
- 用户决策：A（原 D4，2026-11-02 用户在本文档填写）

### A44. 公开仓中的本机路径与会话标识

- 来源：bundle_global_system_properties, bundle_local_archive_tasks, bundle_local_archive_spikes, bundle_local_docs_current
- 位置：docs/archive/handoff.md（32 处本机绝对路径、session id、PID）；docs/archive/spikes/*/independent_review*.md；docs/reviews/review_20261101_075819/review_opencode_cpa_gemini_3_8_flash.md:348
- 优先级：MEDIUM
- 详细判断理由：归档与历史审阅含开发者用户名、目录布局与 agent 会话/PID，随公开 fork 暴露；精查确认没有真实凭据入库。归档区规则只准新增，且 git 历史仍保留，就地脱敏无法真正收回。
- 修复说明：（用户决策 A）历史不改；conventions.md 增加约定（今后 handoff、归档、审阅文档不写本机绝对路径与 session/PID），并新增一条仓库卫生测试：扫描已跟踪的非归档文本文件，出现家目录绝对路径即失败。
- 用户决策：A（原 D5，2026-11-02 用户在本文档填写）

### A45. 启动参数治理

- 来源：bundle_local_backend_runtime_adapters, bundle_global_system_properties, bundle_cross_validation
- 位置：src/backend/cbrowser/runtime_agent/security.py:12-94；src/backend/cbrowser/runtime_agent/runner.py:380-441；src/backend/cbrowser/domain/models.py:69,260,307,364；tests/unit/test_runtime_agent.py:29-77
- 优先级：HIGH
- 详细判断理由：清洗器是前缀黑名单，`--load-extension`、`--js-flags`、位置参数（如 `file:///`）、`--fingerprint-*` 均可穿透，且用户参数拼在内置参数之后会覆盖屏幕指纹；API 层对 launch_args 不做任何校验；测试只枚举黑名单自身条目，还把 `--enable-features=...` 钉为应放行。黑名单天然漏项，属于结构性缺陷。
- 修复说明：（用户决策 A）白名单：定义允许的参数及其值格式，API 层（ProfileConfig）校验并返回 422，runner 作为第二道校验；用户参数不得覆盖内置参数；测试按白名单契约逐项声明并覆盖绕过类。
- 用户决策：A（原 D6，2026-11-02 用户在本文档填写）

### A46. v1 前端死代码提前删除

- 来源：bundle_local_frontend_shell, bundle_local_frontend_features, bundle_global_evolution, bundle_cross_validation
- 位置：src/frontend/src/App.tsx；src/frontend/src/components/*；src/frontend/src/lib/api.ts；src/frontend/src/hooks/useProfiles*.ts；src/frontend/src/novnc.d.ts；src/frontend/src/assets/\*.svg；src/frontend/src/i18n.tsx；src/frontend/package.json:19-22
- 优先级：HIGH
- 详细判断理由：main.tsx 只挂 v2 路由，v1 树（约 2900 行含测试）从入口不可达，却仍参与 tsc/vitest，两套登录页/设置页/API 客户端并存；@dnd-kit 与 @novnc 只被死树引用；ProfileViewer 有剪贴板明文 console.log；仅 v1 使用的 i18n 键使字典无法瘦身。按计划归 t011，提前删除会改变 t011 范围。
- 修复说明：（用户决策 A）现在独立 commit 删除：App.tsx、components/\* 及测试、lib/api.ts 及测试、hooks/useProfiles\* 及测试、novnc.d.ts、src/assets 下两份重复 svg、仅 v1 使用的 i18n 键、package.json 的 @dnd-kit/\* 与 @novnc/novnc（重新 lock）；删除前 grep 确认零引用，删除后跑 tsc -b、vitest、npm run build；t011 task.md 相应去掉这部分。
- 用户决策：A（原 D7，2026-11-02 用户在本文档填写）

### A47. 浏览器会话 adapter 中的测试钩子

- 来源：bundle_local_frontend_features, bundle_global_system_properties, bundle_cross_validation
- 位置：src/frontend/src/features/browser-session/adapter.ts:31-37,75-106,170-178,258；src/frontend/src/features/browser-session/useBrowserSession.ts:232,284,376
- 优先级：HIGH
- 详细判断理由：生产 adapter 把全部 DataChannel 发送报文原文（含键入与 seamless 剪贴板内容）存入 `window.__sentDataChannelMessages`（最多 500 条），并暴露 `__pcs`、`__inputChannel`、`__last_ws`、`__latestRtcConfig` 等仅供测试读取的全局。宿主页与 iframe 之间真正的生产契约只有 `__getWebRTCStats`（useBrowserSession 在用）。测试钩子留在生产代码里既是隐私留存面，也是设计污染；4 个 E2E、fixtures/selkies_assets.py 与 2 个 vitest 依赖这些钩子。
- 修复说明：（用户决策 A）生产代码移除全部测试钩子：测试改用 Playwright `add_init_script` 注入自己的探针包装 RTCDataChannel/WebSocket（fixtures/gateway_probe/selkies_assets.py 已有同类模式）；宿主与 iframe 的统计契约改为显式的 postMessage 请求/响应（或保留唯一有文档的 `__getWebRTCStats`）。
- 用户决策：A（原 D8，2026-11-02 用户在本文档填写）

### A48. 在跑旧版容器与 legacy 默认部署的安全暴露

- 来源：bundle_global_system_properties, bundle_followup_q_system_properties_02, bundle_local_contracts_deploy, bundle_local_backend_core, bundle_global_strategy, bundle_cross_validation
- 位置：compose.yaml:10-17；src/backend/main.py:116-165,1835-1843,1301,1399,1221-1236；README.md:40；.env.example:15-16
- 优先级：CRITICAL
- 详细判断理由：唯一部署形态是 legacy 单容器，端口发布到 0.0.0.0；`AUTH_TOKEN` 留空时全部 API 无认证。你的现网容器已设置 token，所以“无认证控制面”这一半对你不成立；但 SPA 兜底路由的路径穿越绕过 token（非 `/api/` 路径不鉴权），已实测可从本机读取容器内文件，局域网同样可达，可读 `/data` 下各 Profile 的 Cookie、`profiles.db`、`settings.json`。另有剪贴板正文前 60 字符写入 manager.log、只有 shutdown 做同源校验等问题。legacy 代码将由 t011 整体删除；若现在从源码重建 legacy 镜像，会把 v2 前端打进只跑旧后端的镜像，界面不可用（A27），所以 legacy 代码修复实际无法部署。涉及在跑服务与访问方式，需你决定。
- 修复说明：（用户决策 A）运维缓解：compose.yaml 端口改为 `127.0.0.1:${CBROWSER_PORT:-56661}:8080`，用 `docker compose up -d --no-build` 以现有镜像重建容器（数据卷不变）；README 与 .env.example 把 AUTH_TOKEN 标为必填。legacy 代码不改，由 t011 删除。
- 用户决策：A（原 D1，2026-11-02 用户在对话中确认）

## 不采纳项

### R1. legacy 后端与其测试的问题随 t011 整体删除

- 来源：bundle_local_backend_core, bundle_local_backend_tests, bundle_local_backend_api_auth, bundle_global_evolution
- 位置：src/backend/{main,database,browser_manager,vnc_manager,settings_store,env_file,models}.py；src/backend/requirements.txt；src/backend/tests/\*
- 优先级：HIGH
- 详细判断理由：双栈分叉、自动重建表丢列、依赖清单分叉与浮动、代理 URL 拼接、VNC 日志、settings 静默回退、测试单例污染与弱断言等，全部位于 legacy 栈，t011 将整体删除；修改即将删除且无法部署（见 A48）的代码不减少任何技术债。最小债务的路径是推进 t010/t011。在跑容器的安全暴露由 A48 单独处理。

### R2. 归档文件的就地修订

- 来源：bundle_local_archive_tasks, bundle_local_archive_spikes, bundle_global_evolution
- 位置：docs/archive/pending/p001,p005,p011；docs/archive/specs/chrome_external_tabs.md；docs/archive/tasks/{t013,t014}/note.md；docs/archive/handoff.md；docs/archive/spikes/\*
- 优先级：MEDIUM
- 详细判断理由：AGENTS.md 规定归档区内部文件只准新增，不得就地修改。复制粘贴的闭环理由、缺废弃头注、旧评审指纹、t014 收尾模板未填、历史快照标题、缺失的历史评审文件、乱码与夸大措辞都是历史记录本身。需要提示读者的部分由 A25 以新增 README 补充；被放弃的两个测试缺口由 A35 在现行测试中补齐；pending 闭环理由的机械校验属模板工具链，归 A43。

### R3. 已修复或前提不成立

- 来源：bundle_local_docs_current, bundle_local_template_support, bundle_local_backend_tests
- 位置：docs/handoff.md:5-10；docs/specs/storage_and_artifacts.md:48；.repo_template/docs/usage.md:51；src/backend/tests/test_api.py:748-774
- 优先级：LOW
- 详细判断理由：handoff 的 head_commit 指交接提交之前的提交，是已写明的口径；storage spec AC-003 的“p014 待确认”已由 8ccb9ae 修复；“pre-commit 未启用”是审阅所用 clone 的状态，主 clone 已设置 `core.hooksPath=.repo_template/hooks`（本会话提交时核实）；测试中的 license key 字面量随 524e34e 重组从上游测试带入，现网容器 `CBROWSER_LICENSE_KEY` 为空，并非你的密钥，legacy 测试随 t011 删除。

### R4. 正面属性记录

- 来源：bundle_global_system_properties
- 位置：src/backend/cbrowser/；schemas/；config/docker/\*\_runtime/
- 优先级：LOW
- 详细判断理由：Info 级正面结论（v2 组件工程质量足以支撑目标姿态，缺口在接线与完成度），无修复项，作为其余处置的前提引用。

### R5. Stream Agent 实例令牌保持确定性 HMAC

- 来源：bundle_local_backend_stream_gateway
- 位置：src/backend/cbrowser/supervisor/agent_credentials.py:21-33；src/backend/cbrowser/gateway/server.py（handle_agent_register）
- 优先级：LOW
- 详细判断理由：令牌对 (profile, runtime_instance_id) 唯一，实例 id 每次启动都新生成，Gateway 还会用 API 的当前绑定复核，令牌的有效窗口与实例生命周期严格一致——这正是期望的语义。加时间戳或随机数会让长会话中的 Agent 重连在令牌过期后失败，或需要额外的续签协议，增加复杂度而不缩小实际攻击面（能读到令牌的进程本就在该实例的 Stream 容器内）。Agent 侧最小长度口径与 32 字节对齐的建议并入 A30 的密钥读取统一。

### R6. Runtime Agent 的 UDS 不加应用层令牌

- 来源：bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/runtime_agent/agent.py:316-321,470-484
- 优先级：LOW
- 详细判断理由：UDS 由 socket 0660、父目录 0750、umask 077 保护，边界是容器与 uid。浏览器按 ADR 011 以 `--no-sandbox` 与 Agent 同 uid 运行，渲染进程一旦逃逸即拥有该 uid，可同样读取任何令牌文件，应用层令牌不提供额外隔离，只增加密钥分发与轮换的复杂度。真正的边界在 ADR 011 的容器加固与 Supervisor 网络策略。

## 附：finding → 决策映射

逐条格式：`L行号 编号尾号[严重度首字母]→决策`。严重度：C=Critical H=High M=Medium L=Low I=Info。组合型全局结论在括号内列出其构成决策。

- bundle_followup_q_architecture_02.md：L9 02_01[M]→A27
- bundle_followup_q_architecture_03.md：L9 03_01[M]→A4；L15 03_02[L]→A4
- bundle_followup_q_architecture_04.md：L9 04_01[L]→A1
- bundle_followup_q_evolution_02.md：L9 02_01[M]→A43
- bundle_followup_q_strategy_02.md：L9 02_01[L]→A43
- bundle_followup_q_strategy_03.md：L9 03_01[L]→A17
- bundle_global_architecture.md：L9 01[H]→A27（另见 A48）；L15 02[H]→A1；L21 03[M]→A27；L27 04[M]→A14（legacy 部分 R1）；L33 05[M]→A26；L39 06[M]→A10（组合：A9/A10/A11；另见 A42）；L45 07[M]→A43
- bundle_global_evolution.md：L9 01[H]→A42；L15 02[H]→A14（组合：A14/A15）；L21 03[H]→A23（组合：A20/A22/A23/A36/A37/A39）；L27 04[M]→A43；L33 05[M]→R1；L39 06[M]→A42；L45 07[L]→R2；L51 08[L]→A46
- bundle_global_strategy.md：L9 01[H]→A42；L15 02[H]→A42；L21 03[L]→A43；L27 04[M]→A48（文档部分见 A15）；L33 05[M]→A41；L39 06[L]→A42
- bundle_global_system_properties.md：L9 01[C]→A48；L15 02[H]→A41（基础镜像部分 A27）；L21 03[H]→A20（组合：A41/A16/A20/A24/A37/A39）；L27 04[H]→A14（组合：A14/A15）；L33 05[H]→A47（legacy 剪贴板日志见 A48）；L39 06[M]→A5（组合：A2/A5/A9/A10/A11/A48）；L45 07[M]→A13（组合：A1/A13/A26/A48/A43）；L51 08[M]→A44；L57 09[I]→R4
- bundle_local_archive_spikes.md：L60 01[M]→A25；L66 02[M]→A25；L72 03[M]→A25；L78 04[L]→A44；L84 05[L]→A25；L90 06[L]→R2；L96 07[L]→A25；L102 08[L]→R2；L108 09[L]→R2；L114 10[I]→R2；L120 11[I]→R2；L126 12[I]→A15
- bundle_local_archive_tasks.md：L63 01[M]→A35；L69 02[L]→R2；L75 03[L]→R2；L81 04[L]→A44；L87 05[L]→R2；L93 06[L]→R2；L99 07[L]→A35；L105 08[I]→R2
- bundle_local_backend_api_auth.md：L67 01[M]→A13；L73 02[M]→A1；L79 03[M]→A26；L85 04[M]→A26；L91 05[L]→A29；L97 06[L]→A29；L103 07[L]→A13；L109 08[L]→A29；L115 09[L]→A13；L121 10[I]→A29；L127 11[I]→A26；L133 12[L]→A29；L139 13[I]→R1
- bundle_local_backend_core.md：L66 01[H]→A48；L72 02[H]→A48；L78 03[H]→R1；L84 04[M]→A48；L90 05[M]→A48；L96 06[M]→R1；L102 07[M]→R1；L108 08[M]→R1；L114 09[L]→R1；L120 10[L]→R1；L126 11[L]→R1；L132 12[L]→R1；L138 13[L]→R1；L144 14[L]→R1；L150 15[L]→R1；L156 16[I]→R1；L162 17[M]→A48；L168 18[H]→A48；L174 19[M]→R1
- bundle_local_backend_runtime_adapters.md：L67 01[H]→A45；L73 02[H]→A2；L79 03[M]→A28；L85 04[M]→A28；L91 05[M]→A3；L97 06[M]→A32；L103 07[M]→A33；L109 08[M]→A32；L115 09[L]→A32；L121 10[L]→A32；L127 11[L]→A32；L133 12[L]→A32；L139 13[L]→A4；L145 14[L]→A32；L151 15[L]→A32；L157 16[I]→A32；L163 17[I]→R6；L169 18[H]→A45；L175 19[M]→A2；L181 20[M]→A28；L187 21[L]→A32；L193 22[L]→A32
- bundle_local_backend_stream_gateway.md：L73 01[M]→A8；L79 02[M]→A9；L85 03[M]→A10；L91 04[M]→A11；L97 05[L]→A8；L103 06[L]→A30；L109 07[L]→R5；L115 08[I]→A30；L121 09[L]→A12；L127 10[L]→A12；L133 11[L]→A12；L139 12[L]→A26；L145 13[L]→A26；L151 14[L]→A9；L157 15[L]→A12；L163 16[I]→A30；L169 17[L]→A30；L175 18[M]→A8；L181 19[M]→A9；L187 20[L]→A10；L193 21[L]→A11；L199 22[L]→A12
- bundle_local_backend_supervisor.md：L72 01[M]→A5；L78 02[M]→A4；L84 03[L]→A31；L90 04[L]→A6；L96 05[L]→A31；L102 06[L]→A33；L108 07[L]→A31；L114 08[L]→A6；L120 09[L]→A6；L126 10[L]→A6；L132 11[I]→A31；L138 12[I]→A31；L144 13[M]→A7；L150 14[M]→A5；L156 15[L]→A4
- bundle_local_backend_tests.md：L60 01[H]→R1；L66 02[M]→R1；L72 03[M]→R1；L78 04[M]→R1；L84 05[L]→R1；L90 06[L]→R3；L96 07[L]→R1；L102 08[L]→R1；L108 09[I]→R1；L114 10[I]→R1
- bundle_local_contracts_deploy.md：L64 01[H]→A27；L70 02[H]→A48；L76 03[M]→A26；L82 04[M]→A26；L88 05[M]→A15；L94 06[M]→A15；L100 07[L]→A27；L106 08[L]→A26；L112 09[L]→A27；L118 10[L]→A27；L124 11[L]→A40；L130 12[I]→A27；L136 13[I]→A27
- bundle_local_docs_current.md：L62 01[H]→A14；L68 02[M]→A14；L74 03[M]→A14；L80 04[M]→A14；L86 05[M]→A15；L92 06[M]→A16；L98 07[M]→A16；L104 08[L]→A14；L110 09[L]→A14；L116 10[L]→R3；L122 11[L]→A16；L128 12[L]→R3；L134 13[I]→A16；L140 14[I]→A40；L146 15[I]→A44；L152 16[I]→A16；L158 17[L]→A14
- bundle_local_frontend_features.md：L58 01[M]→A47；L64 02[M]→A34；L70 03[M]→A18；L76 04[L]→A34；L82 05[L]→A46；L88 06[L]→A18；L94 07[L]→A34；L100 08[L]→A46；L106 09[L]→A18；L112 10[L]→A18；L118 11[L]→A46；L124 12[I]→A34
- bundle_local_frontend_shell.md：L67 01[H]→A46；L73 02[H]→A41；L79 03[M]→A18；L85 04[M]→A19；L91 05[M]→A34；L97 06[M]→A34；L103 07[L]→A18；L109 08[L]→A34；L115 09[L]→A19；L121 10[L]→A46；L127 11[L]→A46；L133 12[L]→A34；L139 13[L]→A34；L145 14[I]→A46；L151 15[I]→A46；L157 16[I]→A34
- bundle_local_repo_ops.md：L54 01[H]→A41；L60 02[H]→A41；L66 03[H]→A41；L72 04[L]→A41；L78 05[L]→A41；L84 06[L]→A40；L90 07[L]→A40；L96 08[L]→A19；L102 09[I]→A43；L108 10[I]→A41
- bundle_local_template_scripts_ops.md：L67 01[M]→A43；L73 02[M]→A43；L79 03[M]→A43；L85 04[M]→A43；L91 05[L]→A43；L97 06[L]→A43；L103 07[L]→A43；L109 08[L]→A43；L115 09[L]→A43；L121 10[L]→A43；L127 11[L]→A43；L133 12[L]→A43；L139 13[L]→A43；L145 14[L]→A43；L151 15[I]→A43；L157 16[I]→A43
- bundle_local_template_scripts_state.md：L66 01[H]→A43；L72 02[M]→A43；L78 03[M]→A43；L84 04[M]→A43；L90 05[M]→A43；L96 06[L]→A43；L102 07[L]→A43；L108 08[L]→A43；L114 09[L]→A43；L120 10[L]→A43；L126 11[L]→A43；L132 12[L]→A43；L138 13[L]→A43；L144 14[L]→A43；L150 15[L]→A43；L156 16[I]→A43；L162 17[I]→A43；L168 18[I]→A43；L174 19[I]→A43；L180 20[I]→A43
- bundle_local_template_support.md：L61 01[M]→A43；L67 02[L]→R3；L73 03[L]→A43；L79 04[L]→A43；L85 05[I]→A43；L91 06[L]→A43
- bundle_local_template_tests.md：L56 01[M]→A43；L62 02[M]→A43；L68 03[L]→A43；L74 04[L]→A43；L80 05[L]→A43；L86 06[L]→A43；L92 07[L]→A43；L98 08[L]→A43；L104 09[L]→A43；L110 10[L]→A43；L116 11[L]→A43；L122 12[I]→A43；L128 13[I]→A43
- bundle_local_tests_e2e_stream_frontend.md：L59 01[H]→A20；L65 02[H]→A20；L71 03[M]→A36；L77 04[M]→A36；L83 05[M]→A36；L89 06[M]→A37；L95 07[M]→A38；L101 08[M]→A38；L107 09[M]→A37；L113 10[L]→A37；L119 11[L]→A37；L125 12[L]→A37；L131 13[L]→A37；L137 14[L]→A37；L143 15[L]→A38；L149 16[L]→A21；L155 17[L]→A36；L161 18[L]→A37；L167 19[I]→A37
- bundle_local_tests_e2e_supervisor.md：L55 01[H]→A20；L61 02[M]→A37；L67 03[M]→A37；L73 04[M]→A21；L79 05[M]→A38；L85 06[M]→A38；L91 07[M]→A36；L97 08[M]→A37；L103 09[M]→A38；L109 10[M]→A38；L115 11[L]→A37；L121 12[L]→A21；L127 13[L]→A37；L133 14[L]→A37；L139 15[L]→A36；L145 16[L]→A38；L151 17[L]→A38；L157 18[L]→A36；L163 19[L]→A21；L169 20[I]→A37
- bundle_local_tests_integration_fixtures.md：L62 01[H]→A22；L68 02[M]→A36；L74 03[M]→A27；L80 04[M]→A37；L86 05[M]→A37；L92 06[M]→A38；L98 07[M]→A38；L104 08[M]→A27；L110 09[M]→A22；L116 10[L]→A36；L122 11[L]→A37；L128 12[L]→A38；L134 13[L]→A36；L140 14[L]→A20
- bundle_local_tests_unit_stream_api.md：L55 01[M]→A24；L61 02[M]→A24；L67 03[M]→A39；L73 04[M]→A39；L79 05[L]→A39；L85 06[L]→A39；L91 07[L]→A33；L97 08[L]→A24；L103 09[L]→A39；L109 10[L]→A24；L115 11[L]→A24；L121 12[L]→A39；L127 13[L]→A24；L133 14[I]→A39；L139 15[I]→A39；L145 16[I]→A39
- bundle_local_tests_unit_supervisor_runtime.md：L55 01[M]→A23；L61 02[M]→A39；L67 03[M]→A39；L73 04[M]→A39；L79 05[L]→A24；L85 06[L]→A39；L91 07[L]→A39；L97 08[L]→A39；L103 09[L]→A24；L109 10[L]→A39；L115 11[L]→A24；L121 12[L]→A39
