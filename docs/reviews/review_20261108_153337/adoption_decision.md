# 审阅结果决策

## 目录

docs/reviews/review_20261108_153337

## 报告来源

- 已读（仅本目录根层，逐份通读，未读取任何子目录或其它评审目录）：
    - bundle_cross_validation.md
    - bundle_followup_q_arch_01.md
    - bundle_followup_q_strategy_01.md
    - bundle_followup_q_system_properties_01.md
    - bundle_global_architecture.md
    - bundle_global_evolution.md
    - bundle_global_strategy.md
    - bundle_global_system_properties.md
    - bundle_local_backend_core.md
    - bundle_local_backend_runtime_supervisor.md
    - bundle_local_backend_stream_gateway.md
    - bundle_local_contracts_deploy_infra.md
    - bundle_local_frontend_core_shared.md
    - bundle_local_frontend_features.md
    - bundle_local_historical_archives_reviews.md
    - bundle_local_repo_template_toolchain.md
    - bundle_local_specs_blueprint_docs.md
    - bundle_local_tests_integration_e2e.md
    - bundle_local_tests_unit_fixtures.md
    - bundle_repository_summary.md
    - review_intensive.md
- 缺失：无（按根层实际文件判断；不推测未提供的模型路线）。
- 合并说明：原始 73 条具名 finding → 原审阅 55 个决策项；外部方案补充新增 4 项，全文共 59 项（采纳 41、不采纳 18、待决定 0）。聚合报告逐条核对，无仅聚合新增项；bundle_repository_summary 的同题总结并入对应条目，不另计 finding。intensive 属单源多视角，不能作为多模型独立互证。
- 下方映射穷尽 73 条具名 finding；相同行为的跨模块族条目已注明具体覆盖范围。cross_validation 共 24 条 agree 已全部吸收，但 agree 不替代现状核验；无 CHALLENGED/PARTIAL 标记。直接代码反证导致的拒绝/限定范围已逐项说明。
- followup：q_arch_01 → A35；q_strategy_01 → R9（不接受其跨平台战略推断）；q_system_properties_01 → A3（恢复占用不等于只看 running session）。
- 证据基线：HEAD `80e34b58b3dea4572c9e3364dcedb902b36b6f71`，与聚合审阅一致。当前工作区仅本轮 review 目录未跟踪。本次只写决策文档，未跑完整产品门禁或真实故障注入，不将静态核验写成运行通过。

## 外部方案补充评估来源

用户本轮明确要求核对 Weblink 并把适用方向写入 adoption。本节为原始审阅之后的独立补充证据，不伪装成 bundle finding，也不修改原始报告。

- Weblink 基线：默认分支 `public` 的提交 `6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed`；以下源码均按此提交读取。
- CBrowser 基线：仍为本轮审阅 HEAD；本次只读源码与锁定依赖，未运行 Weblink、未启动真实录制或输入改造，不以静态分析宣称端到端 PASS。

|证据|已核对来源|用途与限制|
|---|---|---|
|W1|[Weblink 本地 IME 状态机](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/libs/domain/remote-control/text-input.ts)|以 DOM 编辑器为输入权威，组合期间不提交，compositionend 延后收尾；reset 丢弃未提交组合。|
|W2|[Weblink 有界文字提交](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/libs/domain/remote-control/text.ts)|每包 64、每提交 1024 均按 UTF-16 code unit 计数；按 Unicode code point 遍历避免切断代理对；Enter/Tab 分离，传输复位不排队重放。|
|W3|[Weblink 隐形输入控件](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/routes/home/components/remote-keyboard-input.tsx)|实际路径为 routes/home/components；可聚焦透明 1px textarea、两端零宽守卫、焦点/失焦与独立剪贴板处理。|
|W4|[Weblink Windows 原生文字投递](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/crates/desktop-input/src/windows/text.rs)|仅已知 Edit/RichEdit 类走 EM_REPLACESEL；有前台焦点及进程校验，超时不盲目改走按键重放。|
|W5|[Weblink Windows Unicode 键注入](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/crates/desktop-input/src/windows/device.rs)|submit_text 先尝试原生编辑控件，再经 KEYEVENTF_UNICODE 注入；此为 Windows 实现。|
|W6|[Weblink 按视图启用的诊断采样](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/libs/hooks/session-diagnostics.ts)|Solid signal 保存在局部 hook；视图 enabled/visible 才采样，等待请求后 setTimeout 续跑，retired 防迟到写回。|
|W7|[Weblink 有界编码包录制旁路](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/crates/desktop-capture/src/media/recording.rs)|32 包/8 MiB 双重上限，try_send 不等待录制消费者；从关键帧开始，溢出终止录制订阅并给出错误。数值是上游策略，不直接成为本项目默认。|
|W8|[Weblink 录制订阅生命周期](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/crates/desktop-capture/src/media/recording/source.rs)|录制订阅与 Viewer transport 分离；恢复请求关键帧，支持 encoded audio，不能复用时另有 PCM 路径。|
|W9|[Weblink 编码包封装](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/libs/application/recording-encoded.ts)|使用 EncodedVideoPacketSource/可用时编码音频；PCM 或 MediaStream 音频分支会编码 Opus，不能说所有录制路径完全不编码。|
|W10|[Weblink NAL 格式与参数集归一](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/libs/application/recording-video-config.ts)|在原编码视频上做参数集验证与 NAL 长度前缀转换，不把 RTP 包直接拼成文件。|
|W11|[Weblink 原生录制 codec 选择](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/libs/application/native-codec-selection.ts)|该原生录制选择入口限定 H.264/H.265，不能据此推断任意 VP8 管线都有同样录制能力。|
|W12|[Weblink 前端框架](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/app.tsx)|使用 Solid，并非 React；借鉴响应边界与采样生命周期，不复制其框架状态模型。|
|W13|[Weblink 许可证](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/LICENSE)|MIT；若后续实质复用代码，保留对应版权/许可证；本次只记录设计评估，未复制代码进入生产。|
|C1|`src/frontend/src/features/browser-session/useBrowserSession.ts:386-465`；`SessionPage.tsx:158,194,252-288`；`app/providers.tsx`|每秒把诊断写入会话 hook state，驱动 SessionPage 重渲染；未发现原始 RTCStatsReport 放入顶层 Context。iframe 节点 key 稳定，父组件重渲染不等于媒体被重建。|
|C2|`src/backend/cbrowser/supervisor/volume_spec.py:47-66`；`docs/blueprint/artifacts.md`|Stream 无 `/exchange` 挂载；Artifact 由 API 单写者登记，下载补登只扫描直接子文件，不自动接纳 recordings 子目录。|
|C3|`uv.lock`；`scripts/vendor_selkies_web.py`；锁定 Selkies 2.2.1 wheel|wheel SHA256 `18503b5c1491a04194f0a45fa10c547ffe5b4a24f33496ce5d56e97370a6a3cd` 与仓库锁一致；内部 `selkies/webrtc_media_pipeline.py:22-45,616-670,970-999`、`webrtc/codecs/base.py:39-78`、`webrtc/rtcrtpsender.py:1088-1123` 证明 pixelflux/pcmflux 交付编码帧并再打包 RTP，不是所述 GStreamer appsink 链路。|
|C4|同一 wheel 内 `selkies/selkies_web/selkies-core.js`；`selkies/input_handler.py:9667-9686`|官方客户端已有 composition/输入辅助和 co,end 消息；服务端接收完整文字后进入 XTest/xdotool。前端借鉴不能单独解决 Linux 端注入问题。|
|C5|`src/backend/cbrowser/stream_agent/policy.py`；`docs/blueprint/stream_runtime.md`|全后台/无 Viewer 时暂停捕获，输入提交参与真人接管分类；新录制或文本路径不能绕过这些正式策略。|
|P1|[React useSyncExternalStore](https://react.dev/reference/react/useSyncExternalStore)|外部源与 React 的订阅桥梁；snapshot 与 subscribe 身份必须稳定。不因引入 ref 就能让 UI 自动刷新。|
|P2|[GStreamer tee](https://gstreamer.freedesktop.org/documentation/coreelements/tee.html)|若未来确实采用 GStreamer，分支仍需独立 queue 隔离；不作为当前 Selkies 已有 appsink 的证据。|
|P3|[matroskamux](https://gstreamer.freedesktop.org/documentation/matroska/matroskamux.html)、[mp4mux](https://gstreamer.freedesktop.org/documentation/isomp4/mp4mux.html)|容器输入要求与 codec 支持不同；编码流还需参数、时间戳及正确封装，不是改扩展名。|
|P4|[Windows KEYBDINPUT](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-keybdinput)|KEYEVENTF_UNICODE 经 VK_PACKET/消息翻译进入 Windows 应用，是平台能力，不是 Linux X11 的通用接口。|
|P5|[CDP Input 协议源码](https://github.com/ChromeDevTools/devtools-protocol/blob/master/pdl/domains/Input.pdl)|insertText 为非按键文字提交候选；该链接仅说明接口存在，本轮没有验证目标引擎、浏览器地址栏、富文本或隐私影响。|

### 补充评估结论映射

|用户提出方向|本次处理|当前编号|
|---|---|---|
|本地 IME 暂存、文字/按键分离与有界发送|融入已确认的输入方案验证，不另建重叠项目|A39|
|诊断采样与 UI 叶子订阅|采纳会话级采样源与订阅隔离，保留 React/官方 iframe|A40|
|免重编码录制|采纳编码包旁路的技术可行性验证与未来设计原则，未立项完整录像功能|A41|
|直接搬用 Windows Unicode 注入|不采纳跨平台照搬|R17|
|当前 Selkies 直接 tee/appsink、写 downloads 子目录、零 CPU|不采纳这组未经核对的字面实现与性能承诺|R18|

原始 73 条 finding 仍对应原 55 个决策项；外部补充新增 4 个决策项，A39 内容扩充但不重复计数。新项来源使用本节 W/C/P 证据号，原 bundle 来源字段保持可追溯。

### 原始 finding 覆盖映射

|原始报告位置|Finding ID|决策|
|---|---|---|
|bundle_global_architecture.md:L9|`f_global_arch_network_switch_atomicity`|A35|
|bundle_global_evolution.md:L9|`f_global_evolution_schema_drift_governance`|A16|
|bundle_global_strategy.md:L9|`f_global_strategy_platform_impedance`|R9|
|bundle_global_system_properties.md:L9|`f_global_sys_proxy_ip_cascade_dos`|A4|
|bundle_local_backend_core.md:L71|`f_backend_core_attr_error`|A1|
|bundle_local_backend_core.md:L77|`f_backend_core_network_prefix`|A2|
|bundle_local_backend_core.md:L83|`f_backend_core_control_client_ip`|A4|
|bundle_local_backend_core.md:L89|`f_backend_core_network_active_leak`|A35|
|bundle_local_backend_core.md:L95|`f_backend_core_font_sets_block`|A5|
|bundle_local_backend_core.md:L101|`f_backend_core_http_exc_dict`|A6|
|bundle_local_backend_core.md:L107|`f_backend_core_automation_tunnel_agent_id`|R1|
|bundle_local_backend_core.md:L113|`f_backend_core_legacy_cdp_router`|A7|
|bundle_local_backend_runtime_supervisor.md:L65|`f_supervisor_teardown_port_leak`|A3|
|bundle_local_backend_runtime_supervisor.md:L71|`f_supervisor_normal_exit_override`|A8|
|bundle_local_backend_runtime_supervisor.md:L77|`f_supervisor_replace_stream_leak`|A9|
|bundle_local_backend_runtime_supervisor.md:L83|`f_supervisor_stream_output_accept`|A10|
|bundle_local_backend_runtime_supervisor.md:L89|`f_supervisor_caddy_rebuild_no_rollback`|A35|
|bundle_local_backend_runtime_supervisor.md:L95|`f_supervisor_helper_read_timeout`|A11|
|bundle_local_backend_runtime_supervisor.md:L101|`f_supervisor_transport_pending_futures`|A12|
|bundle_local_backend_runtime_supervisor.md:L107|`f_supervisor_preview_session_leak`|A13|
|bundle_local_backend_runtime_supervisor.md:L113|`f_supervisor_secret_file_toctou`|A14|
|bundle_local_backend_runtime_supervisor.md:L119|`f_supervisor_dialog_attendant_waiters`|A12|
|bundle_local_backend_runtime_supervisor.md:L125|`f_supervisor_start_profile_journal`|R2|
|bundle_local_backend_runtime_supervisor.md:L131|`f_supervisor_orphan_helper_regex`|A15|
|bundle_local_backend_runtime_supervisor.md:L137|`f_supervisor_stop_global_lock`|R3|
|bundle_local_backend_runtime_supervisor.md:L143|`f_supervisor_sun_path_proc_fd_hack`|A36|
|bundle_local_backend_stream_gateway.md:L59|`f_gateway_viewer_throttle_proxy_ip`|A4|
|bundle_local_backend_stream_gateway.md:L65|`f_stream_agent_tunnel_close_empty_session`|R4|
|bundle_local_backend_stream_gateway.md:L71|`f_gateway_missing_applied_network_403`|R5|
|bundle_local_backend_stream_gateway.md:L77|`f_stream_agent_x11_keymap_monkeypatch`|A39|
|bundle_local_contracts_deploy_infra.md:L55|`f_contracts_supervisor_protocol_drift`|A16|
|bundle_local_contracts_deploy_infra.md:L61|`f_contracts_stream_protocol_drift`|A16|
|bundle_local_contracts_deploy_infra.md:L67|`f_deploy_script_bind_port_drop`|A24|
|bundle_local_contracts_deploy_infra.md:L73|`f_deploy_script_inline_caddyfile`|A24|
|bundle_local_contracts_deploy_infra.md:L79|`f_docker_supervisor_root_cap`|A37|
|bundle_local_contracts_deploy_infra.md:L85|`f_docker_browser_copy_all_backend`|A26|
|bundle_local_contracts_deploy_infra.md:L91|`f_compose_secrets_dir_overexpose`|A25|
|bundle_local_contracts_deploy_infra.md:L97|`f_docker_automation_probe_arm64_deb`|R10|
|bundle_local_frontend_core_shared.md:L58|`f_frontend_missing_error_boundary`|A17|
|bundle_local_frontend_core_shared.md:L64|`f_frontend_router_no_code_split`|R6|
|bundle_local_frontend_core_shared.md:L70|`f_frontend_runtime_snapshot_thundering_herd`|R7|
|bundle_local_frontend_core_shared.md:L76|`f_frontend_cn_class_collision`|R8|
|bundle_local_frontend_core_shared.md:L82|`f_frontend_legacy_cbm_locale_key`|A18|
|bundle_local_frontend_features.md:L55|`f_frontend_settings_poll_timer_leak`|A19|
|bundle_local_frontend_features.md:L61|`f_frontend_session_recovery_timer_leak`|A20|
|bundle_local_frontend_features.md:L67|`f_frontend_mounted_ref_lifecycle`|A20|
|bundle_local_frontend_features.md:L73|`f_frontend_session_stage_split_brain`|A20|
|bundle_local_frontend_features.md:L79|`f_frontend_settings_contract_violation`|A21|
|bundle_local_frontend_features.md:L85|`f_frontend_profile_detail_nav_link`|R14|
|bundle_local_frontend_features.md:L91|`f_frontend_maintenance_missing_redirect`|A22|
|bundle_local_frontend_features.md:L97|`f_frontend_adapter_any_casting`|A23|
|bundle_local_historical_archives_reviews.md:L47|`f_arch_unarchived_spikes_lingering`|R16|
|bundle_local_historical_archives_reviews.md:L53|`f_arch_unarchived_reviews_lingering`|R16|
|bundle_local_historical_archives_reviews.md:L59|`f_arch_adoption_decision_dead_links`|R16|
|bundle_local_repo_template_toolchain.md:L48|`f_tool_track_worktree_regex_greedy`|R15|
|bundle_local_repo_template_toolchain.md:L54|`f_tool_repo_cleanup_symlink_traversal`|R12|
|bundle_local_repo_template_toolchain.md:L60|`f_tool_sync_state_json_type_check`|R13|
|bundle_local_specs_blueprint_docs.md:L54|`f_docs_selkies_version_drift`|A32|
|bundle_local_specs_blueprint_docs.md:L60|`f_docs_frontend_router_contradiction`|A33|
|bundle_local_specs_blueprint_docs.md:L66|`f_docs_guides_python_version_drift`|A32|
|bundle_local_specs_blueprint_docs.md:L72|`f_docs_findings_metadata_drift`|A34|
|bundle_local_specs_blueprint_docs.md:L78|`f_docs_parked_p031_dead_link`|A33|
|bundle_local_specs_blueprint_docs.md:L84|`f_docs_skill_task_id_leak`|A33|
|bundle_local_tests_integration_e2e.md:L52|`f_tests_integration_bare_skips`|A38|
|bundle_local_tests_integration_e2e.md:L58|`f_tests_find_free_port_toctou`|A28|
|bundle_local_tests_integration_e2e.md:L64|`f_tests_e2e_hardcoded_macos_chrome`|R9|
|bundle_local_tests_integration_e2e.md:L70|`f_tests_frontend_media_vacuous_test`|R11|
|bundle_local_tests_integration_e2e.md:L76|`f_tests_network_apply_all_mocked`|A29|
|bundle_local_tests_integration_e2e.md:L82|`f_tests_build_wiring_wrong_directory`|A30|
|bundle_local_tests_unit_fixtures.md:L50|`f_tests_fake_containers_ignore_name`|A27|
|bundle_local_tests_unit_fixtures.md:L56|`f_tests_schema_assert_hardcoded`|A16|
|bundle_local_tests_unit_fixtures.md:L62|`f_tests_frontend_api_codegen_ungated`|A16|
|bundle_local_tests_unit_fixtures.md:L68|`f_tests_abandoned_api_dockerfile`|A31|

## 统计

- 采纳：41 项
- 不采纳：18 项
- 待决定：0 项

## 决策原则与执行边界

- 按用户本轮要求坚持架构至上、拒绝临时补丁、零兼容负担；不以开发成本、工作量或旧客户端兼容为拒绝依据。破坏性设计仍须备份、迁移、回退及验证，不能删除未经批准的真实数据。
- A 项修复说明为后续实施范围，不代表已修改代码；全部用户选择已回填。A39 先验证输入方案，不将未经验证的二开或其它输入机制定为既成事实。
- 模板缺陷 R15 已报告，本轮按用户选择暂缓，不改模板、不发送 issue、不自动同步。历史资料 R16 本轮不归档、不运行 repo-hygiene；不修改冻结历史裁决。
- 审批后按 my-adoption 先派子代理只提交本 review 目录，再单独询问是否执行采纳项；审批不等同代码执行授权。涉及项目专属 task/写权要求时须先形成合规实施入口，不把文档审批当作自动绕过项目流程。

## 用户决策回填

六项选择来自用户直接编辑本文件；原 D2 选 A 来自随后聊天明确确认。全部按明确选择回填，不用推荐代替用户选择。

|原编号|用户选择|当前编号|定案范围|
|---|---|---|---|
|D1|A|A35|持久化网络配置事务、失败补偿与重启恢复|
|D2|A（聊天确认）|A39|先验证中文输入方案，不默认二开 Selkies|
|D3|A|A36|独立短路径 UDS 运行根及安全迁移|
|D4|A|A37|保留唯一高信任 Docker 控制者，收敛权限|
|D5|B|R15|本轮不修模板、不上报或同步，保留已验证缺陷|
|D6|C|R16|本轮不归档历史资料，不批量改历史链接|
|D7|A|A38|真实引擎容器化必跑入口与完整证据|

R15/R16 为用户明确暂缓，不是误报或问题闭环。原 A1–A34、R1–R14 编号保持不变；后续沟通使用当前编号，旧 D 编号只用于追溯。

## 待决定项

无。原 D1–D7 已完成选择，去向见“用户决策回填”。

## 采纳项

### A1. 修复网络 RPC 客户端与认证接入

- 来源：bundle_cross_validation, bundle_local_backend_core, bundle_repository_summary
- 位置：src/backend/cbrowser/api/runtime_coordinator.py:1155,1157,1179,1181
- 优先级：CRITICAL
- 结论：采纳
- 覆盖：`f_backend_core_attr_error`
- 详细判断理由：AST 与调用点确认只定义 self.\_client，两个网络 RPC 使用不存在的 self.client 和 \_auth_headers。不是可选重构；受管部署路径会直接失败。
- 修复说明：修改 RuntimeCoordinator.rebuild_edge / converge_network_streams，复用既有 httpx 客户端初始化、supervisor_token 认证与错误处理路径；禁止再建一套认证封装；以真实本地 HTTP stub 校验 URL、Bearer、载荷和错误响应。
- 验收标准：真实 RuntimeCoordinator 对受控 HTTP 服务分别完成两种网络 RPC，验证路径、Bearer 认证与完整载荷；401、超时和 5xx 被正确上报，不再出现 AttributeError；禁用 Supervisor 模式不能作为受管部署通过证据。

### A2. 统一网络 API 的 /api/v1 前缀

- 来源：bundle_cross_validation, bundle_local_backend_core, bundle_repository_summary
- 位置：src/backend/cbrowser/api/v1/network_router.py:36; src/backend/cbrowser/api/app.py:415
- 优先级：CRITICAL
- 结论：采纳
- 覆盖：`f_backend_core_network_prefix`
- 详细判断理由：network_router 的 /network 与直接 include_router 组合不产生 /api/v1；设置页请求与 Caddy /api/\* 代理均无法命中。
- 修复说明：在网络路由权威定义处统一 /api/v1/network，删除旧 /network 对外路径；重新导出 OpenAPI 与前端生成类型，覆盖经正式 app 装配的请求及错误旧路径。
- 验收标准：通过正式 create_app 装配访问全部网络端点，/api/v1/network/\* 命中正确处理器，旧 /network/\* 拒绝；OpenAPI 与生成类型包含真实路径；经 Caddy 的设置/证书链路有独立验证。

### A3. 资源销毁确认后才释放端口，并从 Docker 事实恢复占用

- 来源：bundle_cross_validation, bundle_followup_q_system_properties_01, bundle_global_system_properties, bundle_local_backend_runtime_supervisor, bundle_repository_summary
- 位置：src/backend/cbrowser/supervisor/core.py:2491-2503; 1218-1231
- 优先级：CRITICAL
- 结论：采纳
- 覆盖：`f_supervisor_teardown_port_leak`
- 详细判断理由：stop_profile 与未保护沙箱清理在 teardown 失败时仍释放端口，确实违反蓝图；重启端口恢复还依赖成功接纳 session。端口冲突风险成立，报告所称画面串扰未有运行证据。根因是占用账本跟随业务 session，而非资源实际生命周期。
- 修复说明：统一 core 中 stop、启动失败及异常清理的释放条件：确认受管 Stream 及绑定资源已消失才 release；失败保留占用与待清理状态。启动先扫描受管资源实际 PortBindings 并保守预留，异常/不完整/暂不可验证资源不得因未建立 session 被当成空闲；补失败重试、重启恢复与双 Profile 不复用验证。
- 验收标准：分别注入停止、启动失败、未保护沙箱清理与重启扫描中的 Docker 错误；残留 Stream 的端口一直被预留，重试确认销毁后才释放；另一个 Profile 不会取得该端口；未知身份资源不接管或误删。

### A4. 统一受信反代后的客户端 IP 限流键

- 来源：bundle_cross_validation, bundle_global_system_properties, bundle_local_backend_core, bundle_local_backend_stream_gateway, bundle_repository_summary
- 位置：src/backend/cbrowser/api/v1/control_router.py:74；src/backend/cbrowser/gateway/server.py:731-760；src/backend/cbrowser/api/v1/control_router.py:74; gateway/server.py:731
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_backend_core_control_client_ip`, `f_gateway_viewer_throttle_proxy_ip`, `f_global_sys_proxy_ip_cascade_dos`
- 详细判断理由：控制面直接用 request.client.host，aiohttp Gateway 直接用 request.remote；反代下会共享 Caddy 地址，形成限流连带影响。报告夸大为多租户全局封禁，Gateway 实际还按 profile_id 分桶，但根因成立。FastAPI 还受服务器代理配置影响，修复须统一实际部署边界，不能盲信 X-Forwarded-For。
- 修复说明：control_router 复用现有 resolve_client_ip 与 trusted_proxy_cidrs；Gateway 配置与部署显式接入同一受信代理策略，aiohttp 请求经同一解析逻辑取得限流来源。验证可信/非可信代理、伪造头及不同来源限流隔离，不全信任任意 CIDR。
- 验收标准：用可信代理、多级转发、直连和伪造 X-Forwarded-For 构造端到端鉴权负例；两个来源的失败计数隔离，同来源仍受限；不同框架的来源解析符合统一策略，不能通过任意头绕过限流。

### A5. 将字体完整性扫描移出 API 事件循环

- 来源：bundle_cross_validation, bundle_local_backend_core
- 位置：src/backend/cbrowser/api/v1/font_sets_router.py:51-66; src/backend/cbrowser/font_sets/manifest.py:312-314
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_backend_core_font_sets_block`
- 详细判断理由：async 路由直接调用同步字体枚举与文件哈希，阻塞点明确。仅按 set_id 永久缓存会漏检文件篡改，与完整性检查契约冲突，不采纳该缓存建议。
- 修复说明：font_sets_router 中将完整同步枚举/校验交给有界工作线程，数据库 usage 查询仍留异步路径；每次检查保持内容完整性语义，覆盖篡改可见与并发健康请求不被扫描阻塞。
- 验收标准：在可控慢扫描阻塞点挂起文件校验时，API 健康/事件循环任务仍可推进；修改字体文件后后续请求明确报告哈希异常；并发检查有界，不靠永久缓存使测试通过。

### A6. 恢复结构化业务错误契约

- 来源：bundle_local_backend_core
- 位置：src/backend/cbrowser/api/v1/control_router.py:102,233; src/backend/cbrowser/api/app.py:394
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_backend_core_http_exc_dict`
- 详细判断理由：全局 HTTPException handler 确实 str(detail)，会丢失 control 的 code/message 结构；不同路由还有显式 JSONResponse 特例，不能只对 dict 做任意展开。
- 修复说明：统一 HTTPException 业务错误到明确的 ErrorResponse 映射，保留 code、message、detail 与 retryable；核对控制面、实体路由和前端 ApiError 消费，更新对应 OpenAPI 与链路负例，避免暴露内部异常文本。
- 验收标准：覆盖真实控制冲突、实体引用冲突、普通 HTTPException、422 与 503；前端可稳定读取约定错误码和必要 detail，retryable 正确；响应不出现 Python dict repr、凭据或内部堆栈。

### A7. 彻底删除旧 CDP 路由兼容层

- 来源：bundle_cross_validation, bundle_local_backend_core, bundle_repository_summary
- 位置：src/backend/cbrowser/api/app.py:29,418; src/backend/cbrowser/api/v1/automation_router.py:21,250
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_backend_core_legacy_cdp_router`
- 详细判断理由：legacy_cdp_router 与隐藏挂载属实；按用户本轮明确零兼容要求应删除。include_in_schema=False 对 WebSocket 本身不能证明刻意隐瞒，也没有证据证明该路径绕过鉴权，采纳依据仅为遗留兼容职责。
- 修复说明：删除 automation_router 的 legacy router、旧代理函数及 app 导入/挂载；现行调用方只使用 /api/v1/automation/profiles/{id}/cdp，覆盖旧路径拒绝并更新现行文档中薄兼容声明，不改历史归档裁决。
- 验收标准：扫描现行生产路由与导入确认兼容层删除；旧地址不再可连接，新地址仍执行完整认证与控制权围栏；现行指南和 API 返回端点统一，不保留重定向或旧路由代理。

### A8. 按实例原生退出事实统一终态观测

- 来源：bundle_cross_validation, bundle_local_backend_runtime_supervisor
- 位置：src/backend/cbrowser/supervisor/core.py:1598-1606; core.py:1555
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_supervisor_normal_exit_override`
- 详细判断理由：exited/dead/not_found 分支无条件报 error 属实；但存在终态去重、原生事件围栏与正常 Agent health 分支，不能据此宣称所有正常关闭必复活。缺口是“已有匹配正常原生退出、容器已退出且尚无终态 ACK”路径。仅凭 Docker ExitCode=0 判正常会违背 process_observation_lost 等已定契约。
- 修复说明：统一 \_reconcile_instance_observation、磁盘事件重放与 RecoveryCoordinator 的退出事实优先级；校验 profile/instance/config_version 后依据正常原生事实报告 stopped/normal_exit，未知、owner-loss 与异常退出保持 error；补 API 离线重放与容器先退出时序测试，禁止用 ExitCode==0 一刀切。
- 验收标准：覆盖“匹配正常 journal+容器已退出+API 离线后重放”、未知退出、owner-loss、实例/配置版本不匹配、终态 ACK 去重；正常关闭不复活，异常仍按原退避契约恢复。

### A9. Stream 创建失败由创建者完成回收

- 来源：bundle_cross_validation, bundle_local_backend_runtime_supervisor, bundle_repository_summary
- 位置：src/backend/cbrowser/supervisor/core.py:696-728; docker_adapter.py:1423-1468
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_supervisor_replace_stream_leak`
- 详细判断理由：start_stream_container 在 run 成功后策略安装失败没有回收新容器；上层替换失败也未兜底。生命周期责任缺口明确。
- 修复说明：DockerAdapter 在成功创建后、初始化完成前失败时按已验证身份删除本次容器，回收失败返回类型化待清理结果；Core 保留同实例端口与失败状态，下一次替换前先清理残留；不删 Browser、不误删新代次，覆盖策略失败及删除失败。
- 验收标准：容器创建后分别在地址解析、策略安装、gate/readiness 与回收失败注入异常；本次残留可定位并受控重试，Browser 和新代次资源不受影响，端口不被提前归还。

### A10. 按角色收紧 Stream 双栈默认出站规则

- 来源：bundle_cross_validation, bundle_local_backend_runtime_supervisor
- 位置：src/backend/cbrowser/supervisor/network_policy.py:158,205
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_supervisor_stream_output_accept`
- 详细判断理由：IPv4/IPv6 渲染均无条件最终 OUTPUT ACCEPT，与 Stream 最小出站契约冲突；Browser 公网上网不受该条限制。
- 修复说明：network_policy 仅对 Browser 保留公共目的默认放行；Stream 默认 DROP，明确放行 Gateway、必要 DNS/控制端点及本实例直连媒体；IPv4/IPv6 同步，验证本机/LAN ICE、音视频、邻居发现及公网任意 TCP/UDP 负例，避免只删 ACCEPT 导致媒体回归。
- 验收标准：真实 netns 中分别验证 Stream 的必要控制/媒体通信成功、未授权公网 TCP/UDP 失败，Browser 正常公共网络访问仍可用；IPv4/IPv6 与 Local/LAN 均测，规则安装失败仍保持 gate 封闭。

### A11. 统一网络策略 helper 的超时错误边界

- 来源：bundle_local_backend_runtime_supervisor
- 位置：src/backend/cbrowser/supervisor/docker_adapter.py:296-302,676-680
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_supervisor_helper_read_timeout`
- 详细判断理由：网络策略 helper.wait 仅捕获 DockerException；X11 helper 已有更广异常映射，报告把两个位置都描述为遗漏不准确。采纳网络策略路径及其 finally 清理错误可能掩盖原错误的缺口。
- 修复说明：在 \_install_network_policy 的 SDK 传输边界覆盖实际 requests 传输异常并转为脱敏 DockerSandboxError；确保 helper 回收异常不覆盖主错误，gate 不开放；以超时/回收失败注入验证，不重复修改已覆盖的 X11 分支。
- 验收标准：模拟 requests ReadTimeout、DockerException 与 helper 删除失败，调用方只收到稳定且脱敏的 DockerSandboxError，主异常不被清理覆盖，ready 标记不生成；已覆盖 X11 分支继续通过。

### A12. 连接结束时结清 CDP 与弹窗等待者

- 来源：bundle_local_backend_runtime_supervisor
- 位置：src/backend/cbrowser/agent_executor/transport.py:63-96,161-174；src/backend/cbrowser/runtime_agent/dialog_attendant.py:339-351
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_supervisor_transport_pending_futures`, `f_supervisor_dialog_attendant_waiters`
- 详细判断理由：两处读循环结束未结清 pending/waiters，调用方只能等待超时；均为连接拥有者没有完成请求生命周期。合并为同类责任修复，两个模块分别处理。
- 修复说明：CdpClient 在正常 EOF、异常、主动 close 与发送失败时使未完成 Future 收到稳定断连错误并移除；DialogAttendantService 在 \_run finally 取消或失败结清等待者且清空集合。覆盖连接关闭、并发请求与已完成 Future，不产生未取回异常。
- 验收标准：正常 EOF、异常断连、主动关闭和发送失败时所有等待者及时完成且集合归零；已完成 Future 不重复置位；并发命令及弹窗应答保持可区分错误，不等待完整 30 秒兜底。

### A13. 截图 CDP session 在全部退出路径 detach

- 来源：bundle_local_backend_runtime_supervisor
- 位置：src/backend/cbrowser/runtime_agent/preview_capture.py:108-139
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_supervisor_preview_session_leak`
- 详细判断理由：capture_once attach 后无 detach，metrics 无效、截图/解码失败与成功路径均可能累积会话。
- 修复说明：preview_capture.capture_once 在取得有效 session 后以 try/finally 执行 Target.detachFromTarget；清理失败不得掩盖原截图错误，覆盖成功、无效视口、命令失败及取消路径。
- 验收标准：成功截图、无效视口、metrics 失败、截图失败、解码失败和取消均释放已获得 session；detach 失败保留原错误；连续截图不会线性增加附着 session。

### A14. 通过同一 fd 校验并读取凭据正规文件

- 来源：bundle_local_backend_runtime_supervisor
- 位置：src/backend/cbrowser/secret_files.py:15-27
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_supervisor_secret_file_toctou`
- 详细判断理由：stat 与 read_text 两次路径查找存在竞态，也未拒绝 FIFO。即使是本地部署，配置错误导致无界阻塞也应从文件读取边界消除。
- 修复说明：secret_files 使用 O_NOFOLLOW/O_CLOEXEC/O_NONBLOCK 打开后对 fd 做 fstat，拒绝非正规文件及不安全权限，再从同一 fd 读取并校验长度；全部错误保持脱敏。O_NONBLOCK 防止在 fstat 前打开 FIFO 已阻塞，覆盖软链接、FIFO、权限及替换场景。
- 验收标准：正规私有文件正常读取；group/other 可读、软链接、目录、FIFO 均有界拒绝；路径替换时读取/校验作用于同一个已打开对象；错误与日志不含内容，所有 fd 确认关闭。

### A15. 孤儿 helper 扫描逐资源拒绝异常身份

- 来源：bundle_local_backend_runtime_supervisor
- 位置：src/backend/cbrowser/supervisor/docker_adapter.py:458-463
- 优先级：LOW
- 结论：采纳
- 覆盖：`f_supervisor_orphan_helper_regex`
- 详细判断理由：一个带匹配标签但名字异常的候选会抛异常阻断整轮。应保留严格身份拒绝，调整错误隔离范围；不能为了可用性放宽删除匹配。
- 修复说明：DockerAdapter.\_cleanup_orphan_helpers 对身份/名称不匹配候选记录脱敏 warning 并保留，继续验证其它候选；只删除完全匹配资源；覆盖异常与合法候选混合、外部资源始终不删。
- 验收标准：混合合法遗留 helper、同标签错名资源和无关容器时，只删除严格归属匹配者；异常项被保留并记录，剩余扫描继续；启动不因单个异常候选整体退出。

### A16. 建立协议入口与生成产物完整性门禁

- 来源：bundle_cross_validation, bundle_global_evolution, bundle_local_contracts_deploy_infra, bundle_local_tests_unit_fixtures, bundle_repository_summary
- 位置：scripts/export_supervisor_protocol.py:15-48；scripts/export_stream_protocol.py:24-30；tests/unit/test_supervisor_schema.py:32-50; test_stream_protocol_schema.py:40-46；src/frontend/package.json:21; scripts/run_gates.sh:212-217；scripts/export_supervisor_protocol.py; export_stream_protocol.py; tests/unit/test_supervisor_schema.py
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_contracts_supervisor_protocol_drift`, `f_contracts_stream_protocol_drift`, `f_tests_schema_assert_hardcoded`, `f_tests_frontend_api_codegen_ungated`, `f_global_evolution_schema_drift_governance`
- 详细判断理由：静态枚举确认 Supervisor 漏 8 个模型，Stream 漏人工接管信封，硬编码测试与导出共享同一遗漏；前端生成命令也未纳入漂移校验。不能把 protocol 中所有 BaseModel 无差别导出，payload、基类与真正 wire 入口需区分。直接重生成再 git diff 会弄脏门禁，违背现行只读要求。
- 修复说明：生产协议入口建立唯一显式消息注册/联合类型，导出由其派生；测试独立核对真实 RPC/信封消费入口与 Schema messages。补齐现有遗漏并从源重新生成 schemas；OpenAPI→TypeScript 及所有协议产物在临时目录生成后与入库产物比较，门禁前后受跟踪文件不变；以新增漏导模型负例验证守卫有效。
- 验收标准：引入新增 wire 模型但故意漏注册/漏导出时门禁失败；payload/基类不被误当入口；现有遗漏全部出现在 Schema；改后端契约而不更新 TypeScript 时失败；门禁前后受跟踪产物字节不变。

### A17. 增加应用与路由异常恢复界面

- 来源：bundle_cross_validation, bundle_local_frontend_core_shared
- 位置：src/frontend/src/app/router.tsx:12-71; src/frontend/src/main.tsx:8-14
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_frontend_missing_error_boundary`
- 详细判断理由：缺少自定义异常边界属实；createBrowserRouter 有默认错误界面，不能说任何路由错误都必白屏，但 provider 等路由外渲染异常仍无应用级兜底。明确恢复入口有收益。
- 修复说明：在应用顶层覆盖 providers/RouterProvider 的渲染边界，路由根配置领域错误界面；沿用设计 token 与 i18n，提供安全重载/返回入口，不泄漏异常堆栈；验证路由内外渲染异常与正常会话。
- 验收标准：分别触发 provider 层和路由页面渲染异常，出现可操作且本地化的错误界面，无堆栈/私密数据暴露；恢复动作可用；正常会话不因边界本身重新挂载或停止。

### A18. 删除 cbm.locale 历史迁移逻辑

- 来源：bundle_local_frontend_core_shared, bundle_repository_summary
- 位置：src/frontend/src/i18n.tsx:924,937-941,968; src/frontend/src/i18n.test.tsx:33-42
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_frontend_legacy_cbm_locale_key`
- 详细判断理由：旧键读取、迁移与清理仍存在，用户明确无需旧系统兼容。删除后旧键被忽略，属于已授权架构方向；保留当前 cbrowser.locale 与浏览器语言选择语义。
- 修复说明：i18n 删除 LEGACY_STORAGE_KEY 及相关读取/写回/删除分支，删除仅验证迁移的旧测试并注明语义废止；保留当前键与默认语言测试，同步 frontend blueprint 现行描述。
- 验收标准：当前 cbrowser.locale 的保存、读取与默认语言选择仍通过；仅存在旧 cbm.locale 时按新系统默认规则处理且不迁移；现行源码与有效迁移测试不再依赖旧键。

### A19. 网络操作轮询归属组件生命周期

- 来源：bundle_cross_validation, bundle_local_frontend_features, bundle_repository_summary
- 位置：src/frontend/src/features/settings/SettingsPage.tsx:185-203
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_frontend_settings_poll_timer_leak`
- 详细判断理由：SettingsPage 局部 setInterval 无卸载清理，错误被持续吞掉；请求耗时超过周期还会重叠。切换端口期间断连是正常情形，应按操作状态和截止时间反馈，不是无界轮询。
- 修复说明：用可取消的组件级串行轮询管理单一 operation_id，卸载/替换操作时清 timer 并中止请求；终态与有界失败停止轮询并显示新入口或恢复提示，迟到响应不得更新已失效组件。
- 验收标准：fake timer 与可控请求验证卸载/切换操作后无新请求、迟到响应不更新界面；慢请求不重叠；completed/failed 及时结束；持续断连到截止时间后给出明确状态与入口指引。

### A20. 统一会话状态权威与异步清理

- 来源：bundle_local_frontend_features, bundle_repository_summary
- 位置：src/frontend/src/features/browser-session/useBrowserSession.ts:77-79,192-194,518-528；src/frontend/src/features/browser-session/useBrowserSession.ts:82,202-256；src/frontend/src/features/browser-session/SessionPage.tsx:158,184-193; useBrowserSession.ts:387-465
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_frontend_session_recovery_timer_leak`, `f_frontend_mounted_ref_lifecycle`, `f_frontend_session_stage_split_brain`
- 详细判断理由：transportRecoveryTimerRef 确有卸载遗漏；initialStage 提前 return 跳过 mountedRef cleanup；SessionPage 的 runtime 覆盖未进入 Hook 内部状态，可能继续统计/恢复。三项同属会话生命周期边界，应一次消除分流，而不是各加一个布尔补丁。
- 修复说明：以统一 runtime 查询作为 Hook 的运行态输入，派生唯一会话阶段；终态停止统计与恢复，profile/reload 代次围栏隔离旧异步回调；组件真实 mount/unmount 独立管理，全部 timers/请求清理含 transportRecoveryTimerRef；覆盖 initialStage、停止、切 Profile、重连与卸载，仍不调用 stop API。
- 验收标准：停止、异常、恢复、切 Profile、reloadKey 变化、initialStage 与组件卸载均使用同一阶段来源；旧代次请求不能覆盖新状态；终态没有遗留统计/恢复计时器，且任何清理均不停止 Profile。

### A21. 设置页复用生成类型和统一查询客户端

- 来源：bundle_local_frontend_features
- 位置：src/frontend/src/features/settings/SettingsPage.tsx:16-59,112-238
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_frontend_settings_contract_violation`
- 详细判断理由：SettingsPage 手写网络与字体 DTO 属实；虽通过 client.request 而非裸 fetch，仍绕过领域方法与生成契约，静态检查无法守住字段变化。
- 修复说明：网络接口先具备完整 OpenAPI response/request 模型；重新生成类型，在 shared/api/types 与 ApiClient 增加网络域方法，设置页改用生成类型与查询 hooks，字体复用 useFontSetsQuery；删除重复接口定义，不手改 generated 文件。
- 验收标准：设置页无重复后端 DTO，响应/请求字段变化可触发类型检查；网络域方法实际经过统一认证/CSRF/同源处理；字体查询复用现有缓存与错误呈现，现有表单行为保持契约。

### A22. 删除 Profile 成功后回环境列表

- 来源：bundle_local_frontend_features
- 位置：src/frontend/src/features/profiles/MaintenanceTab.tsx:24-37
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_frontend_maintenance_missing_redirect`
- 详细判断理由：MaintenanceTab 成功删除后没有导航，当前路由已无对应实体；错误路径应留原页。
- 修复说明：handleDelete 成功后 navigate 到现行环境列表 / 并 replace，失败保留当前页与错误；覆盖成功导航、409 禁删和网络错误。
- 验收标准：成功删除后 replace 回 /；409、401及网络失败保留约定错误和路由处理；浏览器后退不重新进入刚删除详情作为当前页。

### A23. 显式声明 Selkies 薄适配层接口

- 来源：bundle_local_frontend_features
- 位置：src/frontend/src/features/browser-session/adapter.ts:26,50,98,108
- 优先级：LOW
- 结论：采纳
- 覆盖：`f_frontend_adapter_any_casting`
- 详细判断理由：adapter 中 any 跨过 window/WebRTC/统计接口检查，已有明确的有限交互面，可用结构类型约束，不需抽象成通用框架。
- 修复说明：在 adapter 及直接消费边界声明实际使用的扩展 Window、统计结果与构造参数类型；外部未知数据先用 unknown 校验，只清理本范围裸 any，跑 typecheck 与原有 adapter 行为测试。
- 验收标准：TypeScript 检查与 adapter 原有身份、信令、Web Locks、统计和焦点测试通过；扩展接口无臆造必需字段，未知消息经过运行时校验，不用宽泛 any/断言消除真实错误。

### A24. 发布网络初始化与端口读取统一事实源

- 来源：bundle_cross_validation, bundle_local_contracts_deploy_infra, bundle_repository_summary
- 位置：scripts/deploy_v2.sh:503-508；scripts/deploy_v2.sh:455-501
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_deploy_script_bind_port_drop`, `f_deploy_script_inline_caddyfile`
- 详细判断理由：deploy_v2.sh 仅读取 bind_host，HTTPS_PORT 仍来自环境/默认；初次配置和 Caddyfile 又由 Bash 模板生成，哈希为空。根因同为部署没有消费 Python 网络配置权威。
- 修复说明：为 network_config 提供部署可调用的确定性初始化/读取入口，复用既有模型、生成器与原子写；deploy 只调用该入口，已应用 bind_host/config.https_port 为发布权威，配置畸形拒绝而不默认覆盖；删除 Bash 双模板与 grep 解析，验证自定义端口二次发布、LAN/本机状态和真实哈希。
- 验收标准：初次部署生成真实哈希；已应用自定义端口与 LAN 地址再次发布仍保持；缺失/损坏配置明确区分且不静默重置；Python 与脚本消费同一生成结果，未执行真实发布前不宣称部署验收通过。

### A25. 按服务挂载实际所需凭据文件

- 来源：bundle_local_contracts_deploy_infra
- 位置：compose.yaml:28,58,100
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_compose_secrets_dir_overexpose`
- 详细判断理由：三个服务均挂载整个 secrets 目录；Gateway 与 API 同 UID，确可读取管理员密码等无关凭据。精确挂载可消除当前不必要暴露，不改变认证协议。
- 修复说明：compose 中 API/Gateway/Supervisor 分别只读挂载其已声明使用的 secret 文件；按实际数据目录嵌套情况检查遮蔽挂载，确保其它数据卷不再次暴露 secrets。验证必要密钥可读、无关凭据容器内不存在、轮换与 readiness 正常。
- 验收标准：按角色从实际容器检查必要凭据可读、无关凭据路径不存在；同时检查数据根等旁路挂载；服务启动、认证、readiness 与凭据轮换都可用，日志及检查证据不输出秘密内容。

### A26. Browser 镜像只交付运行必需模块

- 来源：bundle_local_contracts_deploy_infra
- 位置：config/docker/browser_runtime/Dockerfile:105
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_docker_browser_copy_all_backend`
- 详细判断理由：全量 COPY 后端属实；开源代码可读并不等同凭据泄漏，报告安全影响夸大，但运行组件职责边界与交付最小化问题成立。
- 修复说明：从 Browser entrypoint/runtime_agent 实际 import 闭包确定模块白名单，Dockerfile 改为按必需模块复制；验证所有入口启动、健康、CDP、下载、字体与预览；镜像不含 API/Gateway 等无关服务入口，不仅按报告示例目录机械裁剪。
- 验收标准：检查实际镜像文件与启动 import 闭包；Browser 的 Agent、字体、预览、CDP、下载与停止功能通过；API/Gateway/Supervisor 等无关服务入口未复制，缺模块不靠补回全量 COPY 解决。

### A27. Docker fake 按容器名匹配资源

- 来源：bundle_cross_validation, bundle_local_tests_unit_fixtures
- 位置：tests/fixtures/docker_doubles.py:29-43
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_tests_fake_containers_ignore_name`
- 详细判断理由：共享 FakeContainers.get 忽略参数确实掩盖错名，契约测试也未覆盖此负例。
- 修复说明：docker_doubles 改为明确 name→container 映射，get 未命中抛 NotFound；同步全部消费方的显式注册，删除单容器无条件回退；增加错名、同 Profile 两角色及多实例不串用契约验证。
- 验收标准：不存在/错拼名称抛 NotFound；同一 fake 可同时注册 Browser/Stream 与两个 Profile，查找不串用；所有依赖共享 fake 的生产逻辑测试通过，不用默认任意名称回退补绿。

### A28. Docker 创建时原子分配测试宿主端口

- 来源：bundle_local_tests_integration_e2e
- 位置：tests/fixtures/gateway_probe/topology.py:36-56
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_tests_find_free_port_toctou`
- 详细判断理由：socket bind(0) 后 close 未为 Docker 保留端口；进程内 set/锁不能解决跨 worker 或外部进程抢占。报告未给复现概率，但竞态从实现可确定。
- 修复说明：GatewayTopologyHarness 的 Docker 发布端口交给 daemon 分配，创建后读取实际绑定再生成 URL/Origin/依赖配置；有启动前依赖时分阶段创建，禁止退回先扫空闲端口；测试跨 worker 并发、失败清理和分配结果传递。
- 验收标准：并发 worker 创建隔离拓扑时由 Docker 返回真实端口，URL/Origin/健康检查使用回读值；失败/取消清理本轮资源；不再靠 bind(0) 后关闭或进程内全局 set 预留 Docker 端口。

### A29. 补真实 Coordinator→Supervisor RPC 集成覆盖

- 来源：bundle_local_tests_integration_e2e
- 位置：tests/integration/test_network_apply_operations.py:39-60
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_tests_network_apply_all_mocked`
- 详细判断理由：原用例实际覆盖 NetworkService 与 SQLite 集成，不是完全无价值假测试；但 mock Supervisor 确实无法发现 A1。应增加缺失链路，不为目录名称迁移有效测试。
- 修复说明：保留现有数据库链路测试，在 integration 增加真实 RuntimeCoordinator/httpx 对本地受控 Supervisor HTTP 服务验证 URL、认证、模型及失败传播；与正式 app 网络路由测试联合覆盖 A1/A2，不 mock 被验证 RPC 方法。
- 验收标准：网络集成测试直接执行生产 RPC 方法，能捕获不存在客户端属性、错误 URL、缺认证头与请求模型漂移；SQLite 流程原测试保留，HTTP 错误进入操作失败/恢复路径而非被 mock 成成功。

### A30. 构建校验器单测纳入常规 unit 套件

- 来源：bundle_local_tests_integration_e2e
- 位置：tests/e2e/test_frontend_build_wiring.py:1-164
- 优先级：LOW
- 结论：采纳
- 覆盖：`f_tests_build_wiring_wrong_directory`
- 详细判断理由：该文件只用临时 dist 与纯 Python 校验，无需 Docker/Chrome；常规门禁跳过 E2E 目录会遗漏这些负例。
- 修复说明：将 test_frontend_build_wiring.py 移到 tests/unit 对应位置，保留原测试语义；检查相对路径、collection 与无 E2E 前置运行，避免重复收集。
- 验收标准：常规 unit collection 能收集原有全部构建校验器用例，原负例仍失败/被正确断言；无 Docker/Chrome/真实 dist 前置；旧 E2E 路径不再重复收集。

### A31. 移除失去运行消费者的私有 API 测试镜像

- 来源：bundle_local_tests_unit_fixtures
- 位置：tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile:1-19
- 优先级：LOW
- 结论：采纳
- 覆盖：`f_tests_abandoned_api_dockerfile`
- 详细判断理由：仓库引用检索仅见一处文本门禁，没有构建/运行消费者。报告所称旧版/root 并不等于现行运行漏洞，但废弃交付路径应删除，避免恢复第二套私有拓扑。
- 修复说明：确认现行脚本与 harness 无消费者后，删除该 api_runtime.Dockerfile 及其专属 dockerignore；删除只针对废弃夹具的文本断言，保留正式 API 镜像基线校验。
- 验收标准：再次检索构建、脚本、harness 与文档无运行消费者后删除；常规正式镜像基线测试保留并通过；清理范围仅这套已废弃夹具及专属引用，不顺带删其它历史资产。

### A32. 现行入口文档对齐依赖基线

- 来源：bundle_local_specs_blueprint_docs
- 位置：README.md:3; AGENTS.md:3,8; docs/specs/v2_runtime_validation.md:17,71；docs/guides/supervisor_validation.md:21; browser_runtime_validation.md:40
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_docs_selkies_version_drift`, `f_docs_guides_python_version_drift`
- 详细判断理由：根文档仍声明 Selkies 2.1.0、指南仍指导 Python 3.12+，与现行 2.2.1/3.15+ 冲突。历史实验事实不能全局替换版本。
- 修复说明：修 README/AGENTS 的现状描述与验证指南执行环境；生效 spec 区分历史技术验证基线与现行运行基线，以 ADR 022 标注替代而不重写历史证据；保留 repo_template 来源声明。
- 验收标准：当前根文档与操作命令使用受锁定基线；历史 2.1.0 实验仍有明确原版本语境与替代引用；链接有效，模板来源声明及其它现行架构规则保留。

### A33. 修正现行文档入口、死链和用户可执行指引

- 来源：bundle_local_specs_blueprint_docs
- 位置：docs/blueprint/frontend.md:7,13；docs/pending/parked/p031_domain_learnings_site_skills.md:49；assets/skills/cbrowser-agent/SKILL.md:22
- 优先级：LOW
- 结论：采纳
- 覆盖：`f_docs_frontend_router_contradiction`, `f_docs_parked_p031_dead_link`, `f_docs_skill_task_id_leak`
- 详细判断理由：frontend 同时列旧/新自动化入口；p031 仍指向已归档待办；公开 skill 的“交 t031 handOff”无法指导调用方操作，均有明确现行目标。
- 修复说明：frontend 自动化路径改为 /profiles/:profileId/automation；p031 的 p030/p032/p033 链接指向实际 archive/pending 文件，不改变 parked 状态；cbrowser-agent skill 改为明确真人交接动作并链接 human_agent_control 规约。
- 验收标准：逐个解析修改后的相对链接指向实际目标；自动化页面路径与现行 router 一致；公开 skill 能指示真人交接而非要求理解内部 task 编号；p031 仍保持 parked，不迁移条目。

### A34. 区分历史实验有效性与现行架构适用性

- 来源：bundle_local_specs_blueprint_docs
- 位置：docs/findings/d030_selkies_2_2_1_upgrade_contract.md; d009_turn_hmac_relay_transport.md:11
- 优先级：LOW
- 结论：采纳
- 覆盖：`f_docs_findings_metadata_drift`
- 详细判断理由：d009/d010 已有 ADR 013 后续说明，不能说完全没有替代标注；但“现状：有效”与现行适用范围仍易混淆，d030/d031 缺现状行。报告声称自动化误判未给实际解析器证据，按文档一致性处理。
- 修复说明：d030/d031 补现状元数据；对已由 ADR 013 删除的 TURN/ICE 机制统一标“历史实验事实有效，已不适用于现行实现/验收”，保留实验原结论与后续说明，核对其它同族条目，不将历史实验改成错误事实。
- 验收标准：d030/d031 现状字段齐全；被替代 TURN/ICE 条目明确历史有效性与现行不适用性，原实验结果未被改写；不将缺乏证据的“解析器已修复”写成验收结果。

### A35. 网络切换改为可恢复、可验证的配置事务

- 来源：bundle_cross_validation, bundle_followup_q_arch_01, bundle_global_architecture, bundle_local_backend_core, bundle_local_backend_runtime_supervisor, bundle_repository_summary
- 位置：src/backend/cbrowser/services/network_service.py:135-203; runtime_coordinator.py:1144-1190；src/backend/cbrowser/services/network_service.py:49,71-76,129-133；src/backend/cbrowser/supervisor/docker_adapter.py:1868-1887
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_global_arch_network_switch_atomicity`, `f_backend_core_network_active_leak`, `f_supervisor_caddy_rebuild_no_rollback`
- 决策记录：原 D1；用户在文档选择 A，采用持久化、可恢复的网络配置事务。
- 用户决策：A（持久化配置事务）。
- 详细判断理由：网络应用包含反向代理入口、Gateway Origin、活动 Stream 发布地址和网络策略、磁盘导出及 API 数据库多个参与面。现实现先删 Caddy、再重建 Stream，失败仅把操作标 FAILED，无法证明上一版本仍完整生效；API 重启还会遗留非终态操作。统一配置事务与恢复协议才能修正根因。该事务提供阶段可追溯、最终一致与补偿能力，不承诺多容器瞬时原子切换。
- 修复说明：在 NetworkService、RuntimeCoordinator、Supervisor Core/DockerAdapter 与网络配置导出之间定义同一 operation_id/target_version 的幂等协议。由 API 持久化配置意图和阶段，Supervisor 只持久化自身操作事实，不访问 SQLite；Gateway 消费同一已发布版本。以下阶段和字段是实施契约要求，具体类名及数据库列由实施设计确定，不能另建竞争状态权威。
- 实施步骤：
    1. 接受操作前原子完成并发占用检查及新操作登记，冻结目标配置与上一已验证配置；密码只用于本次验证，不进入操作日志、恢复快照或错误文本。
    2. prepare 阶段校验配置、目标入口占用、Caddy 配置有效性、资源归属及可恢复旧入口所需信息；每项检查记录实际结果，准备失败不破坏现行入口。
    3. 逐资源记录应用前身份与待执行动作，执行后核对实际 Docker/服务状态再推进阶段。Caddy 必须保留可恢复旧配置、镜像与必要网络/卷配置；同端口不能同时绑定时允许有界中断，但失败必须能恢复旧入口，不能先永久删除唯一旧资源。
    4. Stream 更新按 Profile 与运行实例围栏执行；已完成项可重放核验，旧实例、已删除 Profile 与新启动实例分别处理，不能把旧操作覆盖到后来实例。与 A3/A9 共用资源占用和清理语义。
    5. readiness 真实核对目标入口、API/Gateway 可达性、Origin、目标版本及受影响 Stream 注册/媒体配置；没有运行中 Profile 时也必须验证控制入口。只写阶段名或收到 RPC 200 均不等于完成验收。
    6. 用持久提交意图协调数据库已应用版本和磁盘导出；单个文件 os.replace 不等于跨数据库/文件事务。进程在任意间隙退出后，恢复逻辑能依据意图与实际状态补齐提交或执行补偿，不能暴露永久冲突的两套版本。
    7. 任一应用/验收失败按已记录事实补偿到上一已验证版本，补偿同样幂等并执行恢复 readiness；补偿失败保留资源占用、操作事实及明确恢复状态，不能只标 FAILED 后允许下一操作覆盖现场。
    8. API/Supervisor 重启先恢复未终结操作，再开放冲突变更；正常结束及时移除后台任务引用。取消和关闭事件有明确收尾，不把 CancelledError 当正常完成。
- 验收标准：
    - 覆盖 Local→LAN、LAN→Local 与自定义 HTTPS 端口切换，成功后 API/导出文件/Caddy/Gateway/全部受影响 Stream 的版本和入口一致。
    - 在 Caddy 创建、第二个 Stream 更新、readiness、数据库与文件提交间隙、补偿过程中分别注入失败或进程中断；恢复后只能处于完整目标版本、完整旧版本，或明确可诊断的恢复未完成状态。
    - 同 operation_id 重放不重复创建资源；并发不同操作不能同时进入应用；已正常关闭的 Profile 不被恢复动作拉起。
    - 故障资源仍存在或 Docker 状态无法核实时，A3 的端口占用不释放；用户可通过保存的旧入口/恢复说明定位控制面。
- 数据与回退：变更操作持久化结构前确认当前 schema 与数据备份可恢复，提供迁移/回退说明；不删除 Profile、浏览器用户数据或运行证据。不将发布脚本回滚等同数据库降级。
- 关联范围：A1/A2/A16/A19/A21/A24/A29 为同链路接口、前端与证据配套；各条目保留独立职责，不能以其中一项通过宣布整个网络事务已完成。

### A36. 将 UDS 地址与可变数据根解耦

- 来源：bundle_local_backend_runtime_supervisor, bundle_repository_summary
- 位置：src/backend/cbrowser/supervisor/path_validator.py:20-44
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_supervisor_sun_path_proc_fd_hack`
- 决策记录：原 D3；用户在文档选择 A，建立独立且长度有界的 UDS 运行根。
- 用户决策：A（独立短路径运行根）。
- 详细判断理由：可变持久数据根不应决定操作系统 socket 地址能否连接。当前目录 fd 方案有防目录替换作用，不能简单删函数了事；本次重构须同时保留 Profile/实例归属及防路径逃逸。生产仅在 Linux 容器使用 UDS，目标不是新增任意宿主回退路径。
- 修复说明：定义唯一短路径 UDS 拓扑，与长期 Profile 数据及事件目录分离；Browser Agent 创建、Supervisor HTTP/WS 消费者、Compose/动态容器挂载、路径校验和测试 harness 使用同一地址规则，移除 short_unix_socket_path 的 proc 与 cwd-relative 回退及无消费者代码。
- 实施步骤：
    1. 为运行实例选择受限长度标识与唯一位置，完整路径按编码后的字节数校验，计入 socket 文件名与终止符约束；不能仅限制字符数，也不能靠截断 Profile ID 造成碰撞。
    2. 映射 Docker 宿主运行根与容器内固定短路径，启动期一次性验证可写方/只读消费方、UID/GID 与权限；Stream 不获得 Browser 用户数据或不必要控制目录。
    3. 生产者与消费者都校验实例及路径归属，拒绝软链接、越界路径和异常 owner；短路径不替代原有安全校验。可变目录仍须具备等价防替换机制。
    4. socket 属运行时瞬态资源，旧实例停止/替换时按身份清理，启动不会误连同 Profile 的旧实例，也不会删除其它实例 socket。
    5. 直接切换所有现行调用方，不保留新旧双读、探测或静默回退；旧运行实例通过受管停止/重建完成切换，浏览器持久数据不迁移、不删除。
- 验收标准：深数据根不影响真实 UDS HTTP/WS；最长合法标识仍满足实际平台路径限制；两 Profile/两实例地址不冲突；软链接逃逸、目录替换与旧实例误连负例均拒绝；健康、CDP、预览和控制通道完整通过。
- 迁移与回退：在隔离拓扑验证后给出受影响运行实例重建清单和有界中断说明；回退恢复上一完整拓扑，不保留运行期兼容分支。

### A37. 确定 Supervisor 最小权限与 Docker 控制信任边界

- 来源：bundle_cross_validation, bundle_local_contracts_deploy_infra
- 位置：config/docker/supervisor_runtime/Dockerfile:1-32; compose.yaml:71-76
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_docker_supervisor_root_cap`
- 决策记录：原 D4；用户在文档选择 A，保留 Supervisor 为唯一高信任 Docker 控制者并落实最小权限。
- 用户决策：A（保留现行控制信任模型，审计并收敛权限）。
- 详细判断理由：Docker 控制能力是本组件既定职责，完整 socket 可创建高权限容器，非 root 或 cap_drop 本身不能隔离该权能。当前缺少显式剥离与权限职责证明，需落实可验证的最小权限，而不是增加不能约束创建参数的 proxy 并宣称安全边界已经改变。
- 修复说明：审计 Supervisor 常驻进程与短生命周期 helper 的能力需求；Compose 显式先剥离能力，再按必要操作授予最小集合，并约束写路径和提权。保留唯一 socket 持有者、API 唯一数据库写入者，不引入 socket proxy/rootless daemon 或额外常驻控制者。
- 权限审计清单：
    - 逐项区分由 Supervisor 进程执行的 chown/chmod/文件创建，与经 Docker 启动的 NET_ADMIN/FOWNER helper；helper 所需权限不能直接加到常驻进程作为默认能力。
    - 以实际调用证明是否仍需 root 和哪些 capabilities，不能预先承诺全部删除，也不能沿用 Docker 默认完整集合；保留项须说明触发操作与负例验证。
    - 对数据根、字体、引擎缓存、临时目录及 secret 挂载核对读写范围，结合 A25 消除无关凭据可读；日志不输出密钥、代理凭证或用户内容。
    - 明确 read-only docker.sock 挂载只约束文件挂载属性，不限制 Docker API 写操作；不使用该声明作为宿主隔离证明。
    - 审核 no-new-privileges 与明确剥离策略是否兼容入口、helper 调度及当前运行环境；验证失败要按根因调整，不能靠 privileged 或放回默认全部能力通过。
- 验收标准：在正式镜像/编排中检查实际 User、CapDrop/CapAdd、安全选项和挂载；最小能力下新建 Profile、缓存归属、网络策略安装、停止、恢复与 readiness 全部通过；非必要文件和凭据不可读写。
- 残余边界：Supervisor 受损仍可能通过合法 Docker 控制能力影响宿主，此项不能消除该风险。文档须如实说明，不能写成沙箱级隔离或已防逃逸；Browser/Stream 的零特权隔离要求继续独立成立。

### A38. 为真实引擎集成测试建立必跑验证通道

- 来源：bundle_cross_validation, bundle_local_tests_integration_e2e, bundle_repository_summary
- 位置：tests/integration/test_agent_executor_chain.py:343; test_automation_probe_chain.py:320
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_tests_integration_bare_skips`
- 决策记录：原 D7；用户在文档选择 A，真实引擎链路统一容器化执行并纳入必跑证据。
- 用户决策：A（统一容器化入口，正式模式缺失/skip 失败封闭）。
- 详细判断理由：GUI/Xvfb 依赖确会使宿主 integration 跳过，但现有 run_automation_probe.sh 已提供 arm64 容器验证能力，不能说相关功能从未测试。根因是总门禁没有强制关联真实链路完成证据。仅改目录或把任意 pytest.skip 改 fail 都不能证明验证层级和覆盖范围正确。
- 修复说明：复用现有探针与统一 E2E 资源管理，明确一组真实引擎必跑用例及其唯一容器执行入口；将镜像身份、前置检查、选中与实际执行的用例、JUnit 计数和退出码纳入总证据，常规宿主 skip 不再被当作真实链路 PASS。
- 实施步骤：
    1. 列清执行器、自动化探针及真人接管等真实浏览器链路的用例集合、前置环境与现有调用入口；保留跨进程 integration 与完整 Docker/媒体 E2E 的语义区别，不为消除 skip 混并不同层级。
    2. 以当前 linux/arm64 探针镜像与目标引擎缓存运行必跑集合，依赖和 Python 版本遵循仓库锁；仓库/引擎按现有约束只读挂载，不挂生产数据或 Docker socket 给浏览器探针。
    3. 正式模式在 collection/preflight 阶段验证镜像不可变 ID、架构、引擎、Xvfb 和权限；前置缺失一次性列明并失败，不能每 worker 静默 skip。
    4. 执行后核对选中与完成用例，非零退出码、必跑用例缺失、零收集、运行中 skip 或 JUnit 缺失/损坏都不能生成成功证据；xfail 等豁免必须显式区分，不能充当已通过。
    5. 总门禁汇总真实探针 suite，只有对应证据完整通过才允许整体宣称真实链路已验；可选本地模式缺环境时明确 NOT_RUN，不能把宿主 integration 全绿替代容器结果。
    6. 统一清理本轮隔离资源并记录中断状态；失败时保留脱敏诊断与镜像身份，禁止删除生产资源、全局缓存或其它会话容器。
- 验收标准：依次演练缺前置、缺必跑用例、注入 skip、测试失败、中断、证据损坏及完整成功；前六类均不能 all_passed，成功报告含实际用例数、零必跑 skip、镜像身份与可追溯日志。
- 范围边界：不新增 Linux 宿主 Chrome 支持、不交付 amd64 探针、不把容器内链路验证当作 Mac Chrome Viewer/真实 WebRTC 媒体或长期稳定性通过；R9/R10 的拒绝范围保持不变。
- 关联范围：A16 处理生成产物完整性，A27/A28/A29/A30 处理测试真实性与可执行范围；此项只关闭真实引擎链路的必跑与证据缺口。

### A39. 先验证中文文字提交边界，再确定如何删除猴子补丁

- 来源：bundle_cross_validation, bundle_local_backend_stream_gateway, bundle_repository_summary

- 位置：src/backend/cbrowser/stream_agent/x11_keymap.py:35-194

- 优先级：HIGH

- 结论：采纳

- 覆盖：`f_stream_agent_x11_keymap_monkeypatch`

- 决策记录：原 D2；用户在聊天明确确认选 A，先做隔离验证，按证据确定中文提交正式路径，不默认二开 Selkies。

- 用户决策：A（先验证输入方案）。

- 详细判断理由：AST 检查与私有方法动态替换确实存在，但这不能推出必须二开 Selkies。本地固定 2.2.1 wheel 的 co,end 处理先取得完整 text_to_type，再调用 \_type_text_xtest，失败才走 xdotool；文字传输不是已知故障点，历史缺陷位于 X11 键位映射与 Chromium 缓存。现行规约锁定 Native X11 且禁止用剪贴板提交，因此既往修复沿此路径展开。用户质疑复杂度后重新评估：直接派生 wheel 只是收回实现所有权，尚未证明输入架构最优；应先用真实 Chrome 比较未修改上游、当前补丁与候选文字提交方式。候选方案的焦点、地址栏、编辑器、事件语义与隐私影响未验证，不能宣称可直接替换。现有补丁不能未经验证删除。

- 修复说明：先建立隔离、可复现的输入路径比较，以真实 Chrome 行为确定最简单且完全满足需求的唯一正式输入方案。该项第一阶段交付是验证结论、证据与明确实施建议，不授权直接维护 Selkies 派生包、改用剪贴板、修改生产输入规约或删除现有补丁。若现行 Native X11 设计不是最佳方案，应从输入职责边界重定正式路径，不继续叠加私有 ABI 适配或多层回退。

- 验证目标：本机输入法完成选词后，完整 Unicode 文本能按顺序、恰好一次地进入目标 Profile 的正确焦点位置；英文按键、修饰键与快捷键仍遵循各自语义。文字传输、焦点定位与远端提交分别观测，不能把发送成功等同文字已经正确进入 Chrome。

- 实施步骤：

    1. 明确用户实际输入场景：网页普通输入框、密码框与多行文本、contenteditable/富文本、Chrome 地址栏与搜索框；区分网页内容和浏览器自身界面，不把只能操作网页的候选方案当成全部场景已覆盖。
    2. 在隔离的当前固定 Selkies 2.2.1、真实 Browser/Stream/Chrome 拓扑比较未修改上游与当前补丁，复查 d014/d017 的长文本、键位池及 XKB 缓存问题；无法复现时记录环境和差异，不继续把历史现象视作所有环境下的必然故障。
    3. 对完整文字提交消息进行脱敏观测，定位重复、丢字、错序发生在本机 composition、传输、接收还是远端注入；只保存测试样本文本与必要计数，不记录用户真实输入或剪贴板内容。
    4. 核查当前上游公开配置与成熟输入机制，验证能够减少动态键位映射的候选路径；候选接口、所需权限及能力上界必须有源码/协议或真实实验支持。尚未验证的浏览器专用接口只列假设，不写成保证支持地址栏、受控编辑器或全部可信事件的事实。
    5. 所有候选执行同一测试矩阵：中英混输、常用/生僻字、Emoji、组合字符、换行和长文本；选词提交、取消、重复输入、按住修饰键、快捷键、焦点切换、双页面同时连接与不同 Profile 隔离。网络中断后的重放/拒绝语义必须明确，不以盲目重发掩盖丢字。
    6. 比较焦点正确性、内容一致性、重复/丢失/错序、应用输入事件及页面可见差异、剪贴板副作用、权限范围和输入延迟。隐私指纹变化与事件可信性需分别证实，不能仅凭 isTrusted 或检测器总分判安全。
    7. 按“完整满足需求的最简单实现”给出唯一推荐：若未修改上游已满足要求，删除补丁前给出回归证据；若成熟独立文字提交方案更合适，明确其完整覆盖及是否需调整旧 Native X11 约束；仅在证据证明必须保留现行路线且上游存在确定缺陷时，再提出上游修复或源码派生方案，不自动执行二开。
    8. 形成来源、环境/版本、比较结果、失败样本、未覆盖场景和可执行结论；需要长期保留的验证按项目 spike/findings 工具链登记。输入架构、权限或跨服务契约变化须在后续明确方案中同步 specs/blueprint/ADR，历史实验结论保持原语境。

- 验收标准：

    - 每个候选都有明确环境、代码来源、启用方式与同矩阵结果，当前补丁与未修改上游均有基线；不以 mock 输入、仅 DataChannel 收到文本或单一空白网页成功作为完整通过。
    - 推荐方案覆盖目标焦点及 Profile 隔离，中文/Emoji/长文本内容严格一致，无重复、丢字或错序；不支持的控件或地址栏必须明确列为缺口，不能隐去。
    - 本机 composition 取消不向远端残留拼音；中英文切换、已有选择区、光标位置与修饰键行为有真实验证；剪贴板关闭的 Profile 不因文字输入而传输或改写剪贴板。
    - 若候选引入浏览器控制接口，说明连接、权限、焦点/目标选择与页面可观测影响；若候选依赖剪贴板，明确其与现行规约冲突及副作用，未经新决策不得作为正式路径上线。
    - 报告明确区分“方案验证完成”“正式实现完成”和“长期压力验收完成”；当前采纳不预先宣称哪种方案获胜，也不将二开列为既定交付物。

- 实施边界：现阶段保留可用生产输入路径，只在隔离验证中关闭/替换补丁；不向上游自动提交流、不发布派生 wheel、不修改用户 Profile 或真实剪贴板；不为该验证扩展公网、amd64 或其它宿主平台支持。

- Weblink 补充借鉴（W1–W5、C4/C5、P4/P5）：

    - 本地 IME 层：采用“只暂存、只提交最终文字”的职责划分。以实际编辑器值为权威，在 compositionend 的最终 input 序列完成后只提交一次；失焦、切 Profile、控制权变化或连接代次失效时取消未提交组合及延后任务。`setTimeout(0)` 是收尾时序手段，不是已证明覆盖所有浏览器/输入法事件顺序的保证，须用目标 Mac Chrome 真实输入法验证。
    - 零宽守卫仅维持本地编辑上下文。若验证确有收益，种子和光标位置可参考 W1/W3；只能去掉自身注入的边界守卫，不得全局删除用户文本中的合法 U+200B 或其它组合字符。先对照官方 Selkies 已有 composition/keyboard-input-assist 行为，禁止在宿主与 iframe 同时运行两套捕获器导致双发，也不能让隐形 textarea 抢走管理页密码框、宿主快捷键或远端输入焦点。
    - 传输层：保留“文本提交”和“物理按键”两个语义，优先映射现有 Selkies co,end/按键协议，不因 Weblink 使用 JSON 就另建未鉴权信道。若确需新契约，明确定义可靠有序传输、长度单位、字节上限、连接/输入代次及服务端验证，并与 Schema/身份围栏同时更新。
    - 分包层：W2 的 64/1024 是 UTF-16 code unit 数，不是 64 字节、1024 个 Unicode 字符，也不是 WebRTC 协议硬上限；本项目边界依据实际消息预算与接收端能力定案。分包不能切断 surrogate pair；超长、非法孤立 surrogate、控制字符和 channel 背压必须显式处理，不静默截断用户输入。
    - 文本中的换行/Tab 不机械等同 Enter/Tab。后者可能触发表单提交或改变焦点，须按目标控件及现行交互契约验证；多行粘贴、Shift+Enter、富文本和地址栏行为分别判定。
    - “单次 composition 只提交一次”限定在本地事件去重；可靠 DataChannel 不等于跨重连恰好一次执行。已发出但 ACK 不明的文字不得自动重放到新焦点/新 Profile；中断返回明确结果，避免继续排队造成重复或错投。
    - 宿主层：Weblink 的原生 Edit/RichEdit 快路径与 KEYEVENTF_UNICODE 仅作为“文本不是扫描码”的架构证据；不把 Windows API 或 UTF-16 消息投递移植承诺写入 Linux 设计。X11 路径、成熟输入机制及浏览器专用候选分别按 A39 同矩阵验证；CDP insertText 不能先验覆盖 Chrome 地址栏或所有目标控件。
    - 真人优先：若文字绕开现行 co,end，须让真正已提交的前台文本仍进入现有真人接管与活动分类；不复制 Weblink 排他 grant/lease 模型，不复活 CBrowser 已废弃的多 Viewer 排他租约。文本不写日志，不因 clipboard_sync=false 被改成远程粘贴。

- 补充验收：除了 A39 原矩阵，再覆盖 compositionend/input 顺序交换、连续提交、失焦前后收尾、超长 UTF-16、跨包 Emoji、真实零宽字符、分包中途断连、焦点切换及两套捕获器排重。记录“接收字符串正确”与“远端编辑结果正确”两层证据，不把前端借鉴记为 XKB 问题已经解决。

### A40. 会话诊断采样独立于页面渲染，只让展示叶子订阅

- 来源：本轮 Weblink 外部补充评估 W6/W12、CBrowser 现状 C1、React 官方订阅契约 P1。
- 位置：`src/frontend/src/features/browser-session/useBrowserSession.ts:386-465`、`SessionPage.tsx:158,194,280-288`、`types.ts`、`audio_status.ts`；对照 W6。
- 优先级：MEDIUM
- 结论：采纳
- 详细判断理由：当前每秒调用 iframe 的 `__getWebRTCStats()`，再创建新 diagData 写入会话 hook state，使持有该 hook 的 SessionPage 重新执行；这给诊断采样与页面编排引入不必要耦合。现状并没有把原始 RTCStatsReport 放到 AppProviders 顶层 Context，官方视频仍在稳定 iframe 内，不能夸大成每秒重建 PeerConnection/重编码或已证明掉帧。Weblink 用 Solid 局部 signal 加 enabled/visible 门控，借鉴的是职责与生命周期，不是更换 React 框架。
- 修复说明：建立页面会话实例独占的诊断采样源，采样/计算/保留有界窗口位于组件渲染之外；诊断 Overlay、音频状态等需要展示的叶子独立订阅对应快照。沿用当前 React 与 iframe 统计入口，优先现有依赖和 React 原生订阅能力，不引入全局状态库、Web Worker 或新的后端统计服务。
- 实施步骤：
    1. 将连接阶段、控制动作等低频业务状态与帧计数、RTT、字节/丢包计数等诊断样本分开；A20 保持会话状态权威，外部采样源不成为第二套 runtime/控制权状态机。
    2. 每个页面会话/iframe 代次最多一个异步采样在途。采用前次完成后安排下一次或显式 in-flight 合并，避免慢 getStats 与 setInterval 重叠；切 Profile、reload、卸载与终态关闭时清 timer、订阅及历史，旧结果由代次丢弃。
    3. 原始报告与样本保留有界，仅发布格式化且稳定的不可变快照；值未变化不制造新身份或无效通知。使用 useSyncExternalStore 时保证 subscribe/getSnapshot 稳定并正确取消订阅；仅用 ref 保存值不能独立驱动叶子更新。
    4. 诊断面板关闭/页面不可见时停止或降低纯诊断工作，当前默认 1 秒不为“高频”盲目上调。首帧超时、连接恢复、必要音频状态仍独立工作，不能因为面板关闭失去连接判定；多叶子共用采样，不各自建立重复 poller。
    5. 速率/FPS/丢包变化由同一 track/连接代次的计数差与实际采样时间计算；计数回退、track 更换、缺失、0 RTT 与暂停分别处理。客户端解码 FPS 不等于服务端 8/30 目标帧率、编码吞吐或 Supervisor 配额，若没有权威数据就标未知，不倒推出确定状态。
    6. 保留 `deriveAudioStatus` 的独立音频语义、静音和采样窗口；不因视频阶段变化随意重建窗口。主操作栏只订阅实际展示的低频状态变化，不透传整份诊断对象；iframe 的 src/key 和 PeerConnection 生命周期不随样本改变。
- 验收标准：
    - 使用可控延迟统计源验证单次在途、订阅共享、相同快照不重渲染、旧代次结果丢弃，以及无订阅/不可见/终态的清理。
    - 用 React Profiler 或组件渲染计数比较同输入样本：仅 RTT/计数增长时诊断叶子更新，SessionPage 与无关主操作栏不由该样本驱动重渲染；展示值仍正确及时。
    - 真实媒体验证 iframe 不重挂载、src/key 不变、PeerConnection 不重建，音视频与输入不断；面板关闭仍能正确确认首帧/处理恢复，不把渲染次数减少等同帧率提升。
    - 记录优化前后采样调用数、组件渲染次数、统计任务耗时和必要浏览器 CPU 观测，不能预设“高频已拖垮页面”或承诺未测收益。
- 关联范围：与 A20 的单一阶段/清理语义、A23 的统计接口类型统一实施边界；A40 针对采样与展示订阅分离，不修改 Profile 查询、SSE 权威或多人类 Viewer 策略。

### A41. 借鉴有界编码包录制旁路，先验证免重编码能力

- 来源：本轮 Weblink 外部补充评估 W7–W11，CBrowser 固定依赖与存储/策略证据 C2/C3/C5，容器封装参考 P2/P3。
- 位置：固定 Selkies 2.2.1 wheel 的 `webrtc_media_pipeline.py`、`webrtc/codecs/base.py`、`webrtc/rtcrtpsender.py`；本仓 `stream_agent/policy.py`、`supervisor/volume_spec.py`、Artifact 导入与配额链路。
- 优先级：MEDIUM
- 结论：采纳
- 采纳范围：采纳“复用已经编码的音视频、非阻塞有界录制旁路”的架构原则及隔离技术验证；用户提出的是未来录像需求评估，本次没有立项或授权完整会话录像产品，也不默认开启录音/录像。
- 修复说明：先在固定依赖的隔离拓扑验证预编码样本订阅、非阻塞封装、故障隔离和受管 Artifact 交付；以结果确认稳定扩展点与实际预算，再形成正式录制功能方案，不按未经核对的 appsink 或下载子目录描述直接修改生产链路。
- 详细判断理由：CBrowser 受纯 CPU 编码预算约束，重复抓屏/解码后编码不应成为未来录制默认方案。固定依赖已经在 pixelflux/pcmflux 回调产生预编码视频与 Opus，RTP sender 只打包，静态上存在复用编码样本的合理边界；Weblink 对编码包的有界订阅、关键帧起始和独立生命周期是可借鉴实现。尚未证明当前 Selkies 提供正式稳定的录制订阅接口、容器内 muxer 可用或实际性能预算，故必须先验证，不能直接部署私有猴子补丁。
- 目标拓扑：单 Profile 共享捕获/编码 → 同一预编码样本边界 → 原 WebRTC RTP 发送，以及独立有界录制订阅 → 封装写入 worker → 受管临时录像 → 完成校验 → 经 Supervisor/API 登记 Artifact。录制不绑定某个 Viewer，不为每个外部页面重复编码或重复录制；媒体不绕经 API 转发。
- 实施步骤：
    01. 先在隔离固定镜像识别真实 codec、profile、参数集、关键帧标识、pts/dts/time_base 和原生 buffer 生命周期，验证可通过受支持的回调/组件边界订阅一次。优先编码后、RTP 分包前样本，而非从每个 Peer 收集分片；若只能取得 RTP，需完整去包、重排与样本重建，不能直接追加 RTP bytes 成 MP4/MKV。
    02. 接口不存在或只有私有实现时，记录缺口并提出明确扩展方案，不新增运行时 AST/monkey-patch，不因本次评估自动 fork Selkies。不把 `produce_data` 内部实现存在当成已承诺稳定的插件 API。
    03. 录制消费者使用包数和字节数双上限、单一异步封装写入者，采集/发送线程不等待磁盘或 muxer。内存引用可共享则共享；若必须复制就计入成本。队列满、磁盘慢/满或写入失败时，只终止/报错录制订阅并保留可诊断终态，不能阻塞 Viewer、无界缓存或悄悄丢帧仍标完整成功。
    04. 从可独立解码的关键帧开始，保存 H.264/H.265 所需参数及容器 codec metadata，正确处理 NAL framing；VP8/VP9 不套用 H.264 NALU 术语。先验证实际 H.264+Opus 复用，容器候选优先满足原 codec 的 MKV；MP4 是否符合实际 codec、播放器和分段要求单独验证，不为文件扩展名自动转码。
    05. 直接复用已编码 Opus 才能称音频也免重编码；PulseAudio 48000 Hz 只说明采样率，原始 PCM 不是 Opus，不能用采样率推出零编码开销。若需要混音、重采样或 AAC，显式标为新增编码范围并另测预算，本项不自动回退到这些路径；缺音轨与静音必须如实表达。
    06. 使用共同单调时间基准映射音视频，处理 8/30 动态帧率、损伤驱动静止、静音门控与捕获重启；不能假定固定帧间隔或给每帧伪造 30 FPS。codec/分辨率/配置代次变更按可解码边界分段，补充必要参数；编码器重启不能让文件时间戳倒退。
    07. 录制停止先停止接收新样本、有限排空队列、完成容器索引/尾部并校验，再原子发布；崩溃截断、未收尾和溢出录像标 partial/failed，不作为完整证据。分段长度/大小服从 Artifact 配额、磁盘保留与长会话可恢复性，不能把全部录像保存在内存。
    08. 输出由 Supervisor 为当前 Profile/实例分配唯一受管 staging 位置，Stream 或写入 worker 仅获得必要录像目录。禁止为方便挂完整 Browser 用户数据或全量 downloads；确需新增挂载时走卷边界设计和验证，不能假设当前存在 `/exchange`。
    09. 录像不是浏览器 CDP 下载；由显式完成事件/RPC 经 Supervisor 鉴权、路径/实例围栏和配额校验后交 API 单写者登记，复用 Artifact 元数据及下载授权，不另建平行文件总账。现有下载补登只扫直接子文件，不能靠 recordings 子目录自动入库；半文件、未知实例与越界路径拒绝。
    10. 记录现行全后台/无 Viewer 会暂停捕获这一事实。验证阶段只证明已有媒体流的旁路能力；未来若要求无人观看时连续录制，须明确录制是否成为独立捕获消费者、8/30/CPU 配额和停录策略，再更新正式契约，不能偷偷破坏后台节流，也不能把暂停时无画面的录像称完整无人值守审计。
- 技术验收：
    - 观察编码器实例/调用与采集来源，确认新增录制没有开启第二路抓屏、视频解码/编码或重复音频编码；产物可独立解复用/解码，codec 与原始样本一致，音画时钟正确。
    - 同场景分别测“仅流媒体”与“流媒体+录制”的 CPU、内存、队列高水位、磁盘吞吐/空间、编码吞吐和 Viewer RTT/丢包/帧率；免重编码不等于零额外 CPU、零复制或零延迟，不预填性能数值。
    - 测慢盘、满盘、队列溢出、writer 崩溃、Profile 停止、Stream-only 替换、codec/分辨率变化及主进程退出；Viewer 不被录制故障拖停，资源有界回收，完整和残缺文件区分明确。
    - 双 Profile 路径/授权隔离与多 Viewer 共享录制验证通过；未经开启不落盘；完成事件重放幂等，旧实例事件不能覆盖当前录制，已完成录像经 Artifact 正常读取和删除。
- 交付与未定业务项：交付真实管线接入可行性、产物样本、性能/故障矩阵及稳定扩展点建议。正式录像立项另定谁可开始/停止、默认关闭、音轨范围、持续/仅观看模式、保留/删除策略、配额与界面；本项不预选这些用户策略。录像只能证明已捕获画面，不能自动证明操作人身份、无丢帧或防篡改审计链。
- 实施边界：本轮只写 adoption，未来验证按项目 spike 工具链隔离开展；保留 API 唯一 SQLite 写入者、Supervisor 唯一 Docker 控制者、Profile 隔离及官方 Chrome 客户端，不复制 Weblink 的 Tauri/Windows 采集栈或引入第二套流媒体架构。

## 不采纳项

### R1. 不把 token_id 冒充 agent_instance_id

- 来源：bundle_local_backend_core
- 位置：src/backend/cbrowser/api/v1/automation_router.py:158-166
- 优先级：LOW
- 结论：不采纳
- 覆盖：`f_backend_core_automation_tunnel_agent_id`
- 详细判断理由：token_id 是自动化凭证/主体标识，agent_instance_id 是执行器实例标识，两者不同；control_service.claim 已显式使用 token_id。简单赋值会制造错误身份与审计语义，原报告未证明实例 ID 可以从凭证推导。若后续增加 Token 审计字段，应另定义字段而非复用。

### R2. 不采纳“正常重复 start 必返回 409”的断言

- 来源：bundle_local_backend_runtime_supervisor
- 位置：src/backend/cbrowser/supervisor/core.py:2114-2235
- 优先级：LOW
- 结论：不采纳
- 覆盖：`f_supervisor_start_profile_journal`
- 详细判断理由：start_profile 在 Profile 锁内对 observed_state=running 直接返回既有 session，已具有常规重复启动语义；只有尚未完成清理的运行实例才拒绝。operation_id 在 force/reset 中另有用途，不能仅凭未调用 operations.begin 判定 start 合同缺失。跨生命周期命令重放是否需要持久结果须另立契约，当前证据不足。

### R3. 不直接删除停止流程全局锁

- 来源：bundle_local_backend_runtime_supervisor
- 位置：src/backend/cbrowser/supervisor/core.py:2404
- 优先级：LOW
- 结论：不采纳
- 覆盖：`f_supervisor_stop_global_lock`
- 详细判断理由：锁存在属实，但报告没有锁竞争测量与共享状态互斥分析；“不同 Profile 独立”不能证明共享端口、扫描和会话账本无需协调。仅删除锁不是根因级并发设计，也无法从当前证据确认这是实际性能缺陷。

### R4. 不放宽注册会话身份或填占位 session_id

- 来源：bundle_local_backend_stream_gateway
- 位置：src/backend/cbrowser/stream_agent/agent.py:957; protocol.py:89; messaging.py:86-105
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：`f_stream_agent_tunnel_close_empty_session`
- 详细判断理由：worker 只在注册后处理，断连 finally 清空 session 再清理 worker；通知分支还有 ws.closed 与 generation 守卫，信封构造异常也已捕获。报告未证明未注册状态能走到有效通知路径，更不会按所述直接崩溃。伪造占位 ID 或放宽 min_length 会破坏围栏，拒绝该修复建议；若复现竞态，应传递 worker 原注册代次而非假身份。

### R5. 保留缺配置时 Origin 失败封闭

- 来源：bundle_local_backend_stream_gateway, bundle_repository_summary
- 位置：src/backend/cbrowser/gateway/config.py:57-75
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：`f_gateway_missing_applied_network_403`
- 详细判断理由：Gateway.allowed_origins 注释明确要求从已应用版本派生；部署初始化负责预置文件。缺配置返回空列表符合失败封闭，硬编码 localhost 白名单会引入第二套权威并绕过实际端口/网络配置。初始化漂移由 A24 处理，不添加回退。

### R6. 同步路由导入不足以证明首屏性能缺陷

- 来源：bundle_local_frontend_core_shared
- 位置：src/frontend/src/app/router.tsx:4-10
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：`f_frontend_router_no_code_split`
- 详细判断理由：同步导入属实，但报告未给构建分块、压缩体积或首屏指标，Selkies 大型官方客户端又在独立 iframe。按路由切块并非必然更优；当前没有冷启动性能缺陷或需求证据，不因抽象最佳实践新增 Suspense/加载状态。

### R7. 否决“每条 SSE 重取所有 runtime”的结论

- 来源：bundle_local_frontend_core_shared
- 位置：src/frontend/src/app/useRuntimeSnapshot.ts:16-21; AppLayout.tsx:95; useProfilesQuery.ts:444
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：`f_frontend_runtime_snapshot_thundering_herd`
- 详细判断理由：useRuntimeSnapshot 首次确实为各 Profile 建查询，但 SSE 只 invalidate profileKeys.runtime(event.profile_id) 与列表，不使所有 runtime key 失效；无定时 refetchInterval。报告将初始 N 次查询和逐事件全部重取混为一谈。仅读已有缓存还会漏掉未加载 Profile 的统计与错误，不能按原方案删 fetcher。

### R8. 不为未定义的覆盖契约替换 cn

- 来源：bundle_local_frontend_core_shared
- 位置：src/frontend/src/shared/ui/cn.ts:1-5
- 优先级：LOW
- 结论：不采纳
- 覆盖：`f_frontend_cn_class_collision`
- 详细判断理由：cn 的职责目前就是条件拼接，基础组件已有显式 variant/size；报告没有给真实冲突调用或现行“后传 class 必须覆盖默认”契约。引入 tailwind-merge 还需适配自定义 design token 的类组语义，不应为假设性覆盖需求改变全库样式解析。

### R9. 不扩展为 Linux 宿主 Chrome/CI 支持工程

- 来源：bundle_followup_q_strategy_01, bundle_global_strategy, bundle_local_tests_integration_e2e
- 位置：tests/e2e/conftest.py:27; test_stream_runtime_e2e.py:39；tests/e2e/conftest.py:27; tests/integration/test_agent_executor_chain.py:343
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：`f_tests_e2e_hardcoded_macos_chrome`, `f_global_strategy_platform_impedance`
- 详细判断理由：macOS Chrome 固定路径属实，但当前产品验证基准明确是 Mac+OrbStack+官方 Chrome，公网及原生 Linux x86_64 验证不在范围；后续 LAN 访问并未改成任意宿主验证战略。followup 只证明 Linux 容器可运行，没有推翻已声明宿主范围。集成测试 skip 问题拆到 A38；不为报告推定的多平台战略扩展功能。

### R10. 保留明确限定 linux/arm64 的探针构建范围

- 来源：bundle_local_contracts_deploy_infra
- 位置：config/docker/automation_probe/Dockerfile:5-6
- 优先级：LOW
- 结论：不采纳
- 覆盖：`f_docker_automation_probe_arm64_deb`
- 详细判断理由：run_automation_probe.sh 明确校验 linux/arm64，真实引擎缓存、字体与验收证据都按该目标建立；单独替换一个 deb 不能交付 amd64 探针，报告缺少该平台现行需求。此项不属于隐藏兼容层，也无需为未支持平台添加分支。

### R11. 像素等待函数已执行测试判定

- 来源：bundle_local_tests_integration_e2e
- 位置：tests/e2e/test_frontend_media_e2e.py:695-830
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：`f_tests_frontend_media_vacuous_test`
- 详细判断理由：wait_iframe_pixel 只在实际像素满足 predicate 时返回，超时必抛 TimeoutError；测试依次验证两页面红→绿→恢复红。没有字面 assert 不代表没有断言，重复 assert 已被保证的 predicate 不增加覆盖。

### R12. 软链接清理漏洞为误报

- 来源：bundle_local_repo_template_toolchain
- 位置：.repo_template/scripts/repo_cleanup.py:223-225
- 优先级：LOW
- 结论：不采纳
- 覆盖：`f_tool_repo_cleanup_symlink_traversal`
- 详细判断理由：当前 repo_cleanup.apply_delete 明确先 target.is_symlink()→unlink，只有非软链接目录才 rmtree。报告所引位置已包含防护，无需在消费仓改模板。

### R13. 同步状态顶层类型缺失为误报

- 来源：bundle_local_repo_template_toolchain
- 位置：.repo_template/scripts/template_sync/state.py:27-38
- 优先级：LOW
- 结论：不采纳
- 覆盖：`f_tool_sync_state_json_type_check`
- 详细判断理由：state.read_state 经 common.\_load_json_object 读取；该 helper 已验证 isinstance(data, dict)，否则抛带恢复指引的 SyncError。报告忽略公共 helper，不需重复校验。

### R14. 真实锚点导航符合当前明确契约

- 来源：bundle_local_frontend_features
- 位置：src/frontend/src/features/profiles/ProfileDetailPage.tsx:68-74,98-106
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：`f_frontend_profile_detail_nav_link`
- 详细判断理由：frontend blueprint 第 1 节明确规定导航与环境链接为真实 <a href></a>；ProfileDetailPage 按此实现。报告未证明硬刷新损坏业务状态，不能仅按 SPA 惯例把既定产品导航策略判为 bug。若用户希望页面内保留缓存切 Tab，应另行变更导航契约。

### R15. 模板 hook 的 task 标识解析缺陷交由模板源处理

- 来源：bundle_local_repo_template_toolchain
- 位置：.repo_template/scripts/track_worktree.py:140
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：`f_tool_track_worktree_regex_greedy`
- 决策记录：原 D5；用户在文档选择 B，本轮只保留问题记录，等待在模板源安排修复。
- 用户决策：B（暂不处理模板 hook）。
- 详细判断理由：缺陷已经通过纯函数输入复现：`--tid t042; next_command` 的标识被解析为 `t042;`。问题真实；本轮不采纳的是实施/上报动作，不是否认缺陷。用户明确选择暂缓，因此不把自动修复、创建 issue 或模板同步夹入采纳项。
- 本轮边界：不修改 `.repo_template`，不运行模板同步，不创建/发送外部 issue，也不自动登记其它待办文件。本决策作为现有问题证据保留；报告中的简单正则字符集替换未被认定为完整修复方案。
- 恢复条件：用户另行要求处理时，由模板源明确支持的命令语法、参数边界和引号规则并测试；消费仓通过正式同步引入。当前未修复，不能在验收中标“问题已闭环”。

### R16. 确定历史调研、评审归档与链接勘误范围

- 来源：bundle_local_historical_archives_reviews
- 位置：docs/spikes/；docs/reviews/；docs/reviews/review_20261103_185924/adoption_decision.md
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：`f_arch_unarchived_spikes_lingering`, `f_arch_unarchived_reviews_lingering`, `f_arch_adoption_decision_dead_links`
- 决策记录：原 D6；用户在文档选择 C，本轮不做历史归档，仅保留问题记录。
- 用户决策：C（本轮不归档）。
- 详细判断理由：报告指出的历史资料滞留和旧链接失效未在本轮逐份独立核验；已完成 task 也不能证明所有关联评审均已过时。用户选择不做归档，因此本轮不启动 repo-hygiene，不迁移目录、不批量改历史链接，也不默认承认报告声称的 57 条死链数量。
- 本轮边界：保持 `docs/spikes/`、其它 review 目录与冻结历史裁决原位；不重写归档 AC、回执或历史决策。A33 仍只修当前明确点名的现行文档链接，不借其扩大到本项历史资料。
- 恢复条件：用户重新要求整理后，先通过 repo-hygiene dry-run 给出确切过时目录、现行引用、迁移与勘误方案，再按具体清单处理；此前本项为用户明确暂缓，非误报、非已归档。

### R17. 不把 Windows Unicode 注入当成 Linux X11 的现成修复

- 来源：本轮 Weblink 外部补充评估 W4/W5、C4、Windows 文档 P4、CDP 接口 P5。
- 位置：Weblink `crates/desktop-input/src/windows/text.rs`、`windows/device.rs`；CBrowser Linux Xvfb/Chromium 输入边界。
- 优先级：MEDIUM
- 结论：不采纳
- 详细判断理由：EM_REPLACESEL 依赖特定 Win32 Edit/RichEdit 控件，KEYEVENTF_UNICODE 依赖 Windows 的 VK_PACKET/消息翻译；容器内 Chromium 使用 Linux X11，不因宿主是 Mac 而获得这些 API。用户材料准确展示一种 Windows 设计，但没有提供能在本项目直接用的 Linux 后端。也不能把“前端发送整段文字”误当成远端已经能直接插入文字的证明。
- 保留借鉴：文本/按键语义分离、焦点前后校验、超时不盲目回退重放均纳入 A39。Linux 原生输入机制或浏览器文字接口仍须真实验证；若最终方案不能覆盖地址栏或有隐私/事件行为差异，必须显式说明，不能改 DOM 假装原生输入成功。
- 边界：不为借鉴输入功能迁移到 Windows/Tauri、不直接复用 Windows 模块、不默认二开 Selkies。此项拒绝跨平台照搬，不否定 A39 的研究方向。

### R18. 不采纳 appsink 直连、固定下载路径与零 CPU 的字面录制方案

- 来源：本轮用户提案、Weblink W7–W11、CBrowser C2/C3/C5、封装参考 P2/P3。
- 位置：固定 Selkies 2.2.1 WebRTC 编码回调、Stream volume 及 Artifact 管理链路。
- 优先级：MEDIUM
- 结论：不采纳
- 详细判断理由：提案把可借鉴的编码包复用，扩大成了尚不存在的 GStreamer tee/appsink 接口、已挂载下载目录和绝对零开销承诺。源码/锁定 wheel 显示当前 WebRTC 路径是 pixelflux/pcmflux→预编码样本→RTP 打包；Stream 无 /exchange，Artifact 扫描也不遍历 recordings 子目录。MP4/MKV 需要编码参数、样本边界、时钟与收尾；Weblink 自身也有 PCM/音轨重新编码分支。直接按描述落地会跨错组件边界并绕过配额/登记。
- 不采纳内容：不新增第二路无头抓屏/解码再编码作为默认，不将 RTP bytes 直接拼文件，不把 48 kHz PCM 当已编码音频，不承诺零 CPU/零延迟，不为了套 GStreamer 图额外替换当前已可复用的编码管线，不把 /exchange/downloads/recordings 当作当前可写且自动受管的目录。
- 正确去向：A41 单独采纳编码样本旁路与有界生命周期并安排技术验证；可验证的额外成本与存储契约必须写明。本项不是否决未来录像，也不是要求引入一套通用录像平台。

## 实施组织与验证要求

本节为后续实施边界，不创建 task、不登记依赖状态、不授权发布或代码执行。若进入实施，依项目流程形成可独立验证的工作项，每项保持根因范围，禁止顺手扩展功能。

|工作面|关联决策|先决事实与联合验收|
|---|---|---|
|网络应用完整链路|A1、A2、A16、A19、A21、A24、A29、A35|先统一接口与配置权威，再做实际切换、故障补偿、重启恢复；前端仅反映真实操作结果|
|容器生命周期与占用|A3、A8、A9、A11、A15|统一实例围栏及清理语义；与网络补偿共享资源占用事实，不能靠删除 session 假装清理完成|
|安全边界|A4、A10、A14、A25、A37|分别验证来源可信度、双栈最小出站、凭据读取/挂载及高信任控制权限，不互相替代安全证明|
|运行控制与 UDS|A12、A13、A36|先明确唯一运行地址和会话生命周期；验证真实健康/CDP/控制/预览消费者|
|前端契约与生命周期|A6、A17、A18、A20、A22、A23|保留现行导航与多页面语义；错误、终态和旧异步回调均可观测且可恢复|
|测试与交付真实性|A5、A26、A27、A28、A30、A31、A38|分别保持实际产品覆盖、镜像依赖闭包、资源隔离及必跑证据，不用文本断言代替真实行为|
|中文输入方案验证|A39、R17|纳入 Weblink 本地 IME 与有界文本语义；Linux 注入单独验证，不默认派生 Selkies或移植 Windows API|
|诊断采样与渲染|A40|与 A20/A23 统一会话代次和类型；采样共享、叶子订阅，保持首帧/恢复判定|
|免重编码录制验证|A41、R18|先验证真实编码样本旁路和 Artifact 边界；不默认实现完整录像、不承诺零 CPU|
|现行文档修正|A32、A33、A34|随对应实现同步核对 blueprint/specs/ADR 传播，保留历史事实，遵守 R15/R16 暂缓边界|

- 每项先以触达生产逻辑的失败用例证明缺口，再修复；旧测试语义失效时整体替换/删除并记录理由，禁止就地改预期迎合实现。
- 定向验证通过后运行与改动范围相符的项目门禁，真实 Docker/Chrome/引擎验证按要求执行；本机基准仍为 Mac+OrbStack，未执行的环境或长期压力检查明确记 NOT_RUN，不记 PASS。
- schema、TypeScript、设计 token 等派生产物均从权威源生成；检查型门禁不得改写受跟踪文件。所有调试与一次性材料只写已忽略目录或正式登记 spike 工作区。
- 数据/运行拓扑改变前准备可恢复备份、受影响实例清单与回退方式；生产数据不因“零兼容”直接删除。发布、外部 issue、push 均需已有明确授权，本文未提供这些授权。
- A 项“采纳”表示方案进入后续实施范围，不表示已经完成。R 项“暂缓”保留问题状态；A39 已选择先验证输入方案，验收对象首先是可信的方案结论，不能以探针完成冒充输入重构已交付。

## 本轮校验

- 原审阅 73 条具名 finding 仍穷尽映射且不重复计数；新增 4 项属于外部补充，来源见 W/C/P 证据目录，各决策编号唯一。
- Markdown 格式检查、合并优先级取最高校验通过；七项选择已全部回填，无待决定项；原 D1–D7 与当前编号映射完整。
- 纯函数探针复现 R15：`--tid t042; next_command` 被解析为 `t042;`；本地 SDK 类层级验证确认 `ReadTimeout` 不属于 `DockerException`。
- 已核对关键调用、路由装配、协议模型/导出入口、容器清理与端口恢复、网络规则、前端状态与测试辅助函数。未核验的历史链接数量与外部上游修复版本已明确保留为未知。
- 原报告及用户提供的外部方案摘要均按已核对源码限定结论；关键更正包括 Windows 注入不可直接移植、当前实际管线非 GStreamer、Stream 无下载挂载、免重编码不等于零 CPU、现状没有顶层 Context 高频统计。未做真实输入/录制/性能实验，不标 PASS。

## 审批状态

- 当前：原选择已全部回填；用户要求的 Weblink 补充评估已写入 A39/A40/A41、R17/R18，全文 41 项采纳、18 项不采纳、0 项待决定；等待用户审批更新后的整份文档。选择确认不等于审批，不提交 review 目录，不实施采纳项。
- 审批归档与采纳项实施分开确认。
