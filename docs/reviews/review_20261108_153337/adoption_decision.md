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
- 合并说明：原始 73 条具名 finding → 原审阅 55 个决策项；外部方案补充新增 4 项，全文共 59 项（采纳 42、不采纳 17、待决定 0）。聚合报告逐条核对，无仅聚合新增项；bundle_repository_summary 的同题总结并入对应条目，不另计 finding。intensive 属单源多视角，不能作为多模型独立互证。
- 下方映射穷尽 73 条具名 finding；相同行为的跨模块族条目已注明具体覆盖范围。cross_validation 共 24 条 agree 已全部吸收，但 agree 不替代现状核验；无 CHALLENGED/PARTIAL 标记。直接代码反证导致的拒绝/限定范围已逐项说明。
- followup：q_arch_01 → A35；q_strategy_01 → R9（不接受其跨平台战略推断）；q_system_properties_01 → A3（恢复占用不等于只看 running session）。
- 证据基线：HEAD `80e34b58b3dea4572c9e3364dcedb902b36b6f71`，与聚合审阅一致。该 review 目录已由现有提交 53a3ec6 纳入跟踪；本次以其为文档修订基线，源代码与 80e34b58b3dea4572c9e3364dcedb902b36b6f71 相比无变更。工作区另有用户未跟踪 config/deploy，保持不动。本次只写决策文档，未跑完整产品门禁或真实故障注入，不将静态核验写成运行通过。

## 外部方案补充评估来源

用户本轮明确要求核对 Weblink 并把适用方向写入 adoption。本节为原始审阅之后的独立补充证据，不伪装成 bundle finding，也不修改原始报告。

- Weblink 基线：默认分支 `public` 的提交 `6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed`；以下源码均按此提交读取。
- CBrowser 基线：仍为本轮审阅 HEAD；本次只读源码与锁定依赖，未运行 Weblink、未启动真实录制或输入改造，不以静态分析宣称端到端 PASS。

|证据|已核对来源|用途与限制|
|---|---|---|
|W1|[Weblink 本地 IME 状态机](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/libs/domain/remote-control/text-input.ts)|以 DOM 编辑器为输入权威，组合期间不提交，compositionend 延后收尾；reset 丢弃未提交组合。|
|W2|[Weblink 有界文字提交](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/libs/domain/remote-control/text.ts)|每包 64、每提交 1024 均按 UTF-16 code unit 计数；按 Unicode code point 遍历避免切断代理对；Enter/Tab 分离，传输复位不排队重放。|
|W3|[Weblink 隐形输入控件](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/routes/home/components/remote-keyboard-input.tsx)|实际路径为 routes/home/components；可聚焦透明 1px textarea、两端零宽守卫、焦点/失焦与独立剪贴板处理。|
|W4|[Weblink Windows 原生文字投递](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/crates/desktop-input/src/windows/text.rs)|无可用 Focus/非适用控件等前置条件返回 Ok(false)；已进入校验/replace 的错误返回 Err。不能把“不适用”与“投递失败”统称一种失败。|
|W5|[Weblink Windows Unicode 键注入](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/crates/desktop-input/src/windows/device.rs)|text::insert 返回 Ok(true) 时结束，Ok(false) 时转 KEYEVENTF_UNICODE；Err 经 ? 直接传播，包括 native 投递超时或其它 Err，不泛化为所有非超时失败都会回退。|
|W6|[Weblink 按视图启用的诊断采样](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/libs/hooks/session-diagnostics.ts)|Solid signal 保存在局部 hook；视图 enabled/visible 才采样，等待请求后 setTimeout 续跑，retired 防迟到写回。|
|W7|[Weblink 有界编码包录制旁路](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/crates/desktop-capture/src/media/recording.rs)|32 包/8 MiB 双重上限，try_send 不等待录制消费者；从关键帧开始，溢出终止录制订阅并给出错误。数值是上游策略，不直接成为本项目默认。|
|W8|[Weblink 录制订阅生命周期](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/crates/desktop-capture/src/media/recording/source.rs)|录制订阅与 Viewer transport 分离；恢复请求关键帧，支持 encoded audio，不能复用时另有 PCM 路径。|
|W9|[Weblink 编码包封装](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/libs/application/recording-encoded.ts)|视频 EncodedVideoPacketSource 与 encodedAudio 可复用原编码；PCM/MediaStream 音频分支执行 Opus 编码，区别于对已有编码音轨的重新编码。|
|W10|[Weblink NAL 格式与参数集归一](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/libs/application/recording-video-config.ts)|本文件证明参数集归一与 NAL 长度前缀转换；编码样本封装链还需结合 W7–W9 核对，不单凭此文件推断全系统如何处理 RTP。|
|W11|[Weblink 原生录制 codec 选择](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/libs/application/native-codec-selection.ts)|该原生录制选择入口限定 H.264/H.265，不能据此推断任意 VP8 管线都有同样录制能力。|
|W12|[Weblink app.tsx](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/src/app.tsx) 与 [apps/web/package.json](https://github.com/99percentpeople/weblink/blob/6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed/apps/web/package.json)|应用入口使用 Solid，包声明 solid-js/@solidjs/router、vite-plugin-solid 等；本次核对的 web 应用入口及构建依赖为 Solid，不据单文件推断仓库所有应用都没有 React。|
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
|bundle_local_backend_core.md:L70|`f_backend_core_attr_error`|A1|
|bundle_local_backend_core.md:L77|`f_backend_core_network_prefix`|A2|
|bundle_local_backend_core.md:L84|`f_backend_core_control_client_ip`|A4|
|bundle_local_backend_core.md:L91|`f_backend_core_network_active_leak`|A35|
|bundle_local_backend_core.md:L98|`f_backend_core_font_sets_block`|A5|
|bundle_local_backend_core.md:L105|`f_backend_core_http_exc_dict`|A6|
|bundle_local_backend_core.md:L112|`f_backend_core_automation_tunnel_agent_id`|A42|
|bundle_local_backend_core.md:L119|`f_backend_core_legacy_cdp_router`|A7|
|bundle_local_backend_runtime_supervisor.md:L64|`f_supervisor_teardown_port_leak`|A3|
|bundle_local_backend_runtime_supervisor.md:L71|`f_supervisor_normal_exit_override`|A8|
|bundle_local_backend_runtime_supervisor.md:L78|`f_supervisor_replace_stream_leak`|A9|
|bundle_local_backend_runtime_supervisor.md:L85|`f_supervisor_stream_output_accept`|A10|
|bundle_local_backend_runtime_supervisor.md:L92|`f_supervisor_caddy_rebuild_no_rollback`|A35|
|bundle_local_backend_runtime_supervisor.md:L99|`f_supervisor_helper_read_timeout`|A11|
|bundle_local_backend_runtime_supervisor.md:L106|`f_supervisor_transport_pending_futures`|A12|
|bundle_local_backend_runtime_supervisor.md:L113|`f_supervisor_preview_session_leak`|A13|
|bundle_local_backend_runtime_supervisor.md:L120|`f_supervisor_secret_file_toctou`|A14|
|bundle_local_backend_runtime_supervisor.md:L127|`f_supervisor_dialog_attendant_waiters`|A12|
|bundle_local_backend_runtime_supervisor.md:L134|`f_supervisor_start_profile_journal`|R2|
|bundle_local_backend_runtime_supervisor.md:L141|`f_supervisor_orphan_helper_regex`|A15|
|bundle_local_backend_runtime_supervisor.md:L148|`f_supervisor_stop_global_lock`|R3|
|bundle_local_backend_runtime_supervisor.md:L155|`f_supervisor_sun_path_proc_fd_hack`|A36|
|bundle_local_backend_stream_gateway.md:L58|`f_gateway_viewer_throttle_proxy_ip`|A4|
|bundle_local_backend_stream_gateway.md:L65|`f_stream_agent_tunnel_close_empty_session`|R4|
|bundle_local_backend_stream_gateway.md:L72|`f_gateway_missing_applied_network_403`|R5|
|bundle_local_backend_stream_gateway.md:L79|`f_stream_agent_x11_keymap_monkeypatch`|A39|
|bundle_local_contracts_deploy_infra.md:L54|`f_contracts_supervisor_protocol_drift`|A16|
|bundle_local_contracts_deploy_infra.md:L61|`f_contracts_stream_protocol_drift`|A16|
|bundle_local_contracts_deploy_infra.md:L68|`f_deploy_script_bind_port_drop`|A24|
|bundle_local_contracts_deploy_infra.md:L75|`f_deploy_script_inline_caddyfile`|A24|
|bundle_local_contracts_deploy_infra.md:L82|`f_docker_supervisor_root_cap`|A37|
|bundle_local_contracts_deploy_infra.md:L89|`f_docker_browser_copy_all_backend`|A26|
|bundle_local_contracts_deploy_infra.md:L96|`f_compose_secrets_dir_overexpose`|A25|
|bundle_local_contracts_deploy_infra.md:L103|`f_docker_automation_probe_arm64_deb`|R10|
|bundle_local_frontend_core_shared.md:L57|`f_frontend_missing_error_boundary`|A17|
|bundle_local_frontend_core_shared.md:L64|`f_frontend_router_no_code_split`|R6|
|bundle_local_frontend_core_shared.md:L71|`f_frontend_runtime_snapshot_thundering_herd`|R7|
|bundle_local_frontend_core_shared.md:L78|`f_frontend_cn_class_collision`|R8|
|bundle_local_frontend_core_shared.md:L85|`f_frontend_legacy_cbm_locale_key`|A18|
|bundle_local_frontend_features.md:L54|`f_frontend_settings_poll_timer_leak`|A19|
|bundle_local_frontend_features.md:L61|`f_frontend_session_recovery_timer_leak`|A20|
|bundle_local_frontend_features.md:L68|`f_frontend_mounted_ref_lifecycle`|A20|
|bundle_local_frontend_features.md:L75|`f_frontend_session_stage_split_brain`|A20|
|bundle_local_frontend_features.md:L82|`f_frontend_settings_contract_violation`|A21|
|bundle_local_frontend_features.md:L89|`f_frontend_profile_detail_nav_link`|R14|
|bundle_local_frontend_features.md:L96|`f_frontend_maintenance_missing_redirect`|A22|
|bundle_local_frontend_features.md:L103|`f_frontend_adapter_any_casting`|A23|
|bundle_local_historical_archives_reviews.md:L46|`f_arch_unarchived_spikes_lingering`|R16|
|bundle_local_historical_archives_reviews.md:L53|`f_arch_unarchived_reviews_lingering`|R16|
|bundle_local_historical_archives_reviews.md:L60|`f_arch_adoption_decision_dead_links`|R16|
|bundle_local_repo_template_toolchain.md:L47|`f_tool_track_worktree_regex_greedy`|R15|
|bundle_local_repo_template_toolchain.md:L54|`f_tool_repo_cleanup_symlink_traversal`|R12|
|bundle_local_repo_template_toolchain.md:L61|`f_tool_sync_state_json_type_check`|R13|
|bundle_local_specs_blueprint_docs.md:L53|`f_docs_selkies_version_drift`|A32|
|bundle_local_specs_blueprint_docs.md:L60|`f_docs_frontend_router_contradiction`|A33|
|bundle_local_specs_blueprint_docs.md:L67|`f_docs_guides_python_version_drift`|A32|
|bundle_local_specs_blueprint_docs.md:L74|`f_docs_findings_metadata_drift`|A34|
|bundle_local_specs_blueprint_docs.md:L81|`f_docs_parked_p031_dead_link`|A33|
|bundle_local_specs_blueprint_docs.md:L88|`f_docs_skill_task_id_leak`|A33|
|bundle_local_tests_integration_e2e.md:L51|`f_tests_integration_bare_skips`|A38|
|bundle_local_tests_integration_e2e.md:L58|`f_tests_find_free_port_toctou`|A28|
|bundle_local_tests_integration_e2e.md:L65|`f_tests_e2e_hardcoded_macos_chrome`|R9|
|bundle_local_tests_integration_e2e.md:L72|`f_tests_frontend_media_vacuous_test`|R11|
|bundle_local_tests_integration_e2e.md:L79|`f_tests_network_apply_all_mocked`|A29|
|bundle_local_tests_integration_e2e.md:L86|`f_tests_build_wiring_wrong_directory`|A30|
|bundle_local_tests_unit_fixtures.md:L49|`f_tests_fake_containers_ignore_name`|A27|
|bundle_local_tests_unit_fixtures.md:L56|`f_tests_schema_assert_hardcoded`|A16|
|bundle_local_tests_unit_fixtures.md:L63|`f_tests_frontend_api_codegen_ungated`|A16|
|bundle_local_tests_unit_fixtures.md:L70|`f_tests_abandoned_api_dockerfile`|A31|

## 统计

- 采纳：42 项
- 不采纳：17 项
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

R15/R16 为用户明确暂缓，不是误报或问题闭环。原 A1–A34、R2–R14 编号保持不变；原 R1 已撤回并转 A42；后续沟通使用当前编号，旧 D 编号只用于追溯。

## 待决定项

无。原 D1–D7 已完成选择，去向见“用户决策回填”。

## 采纳项

### A1. 修复网络 RPC 客户端与认证接入

- 来源：bundle_cross_validation, bundle_local_backend_core, bundle_repository_summary
- 位置：src/backend/cbrowser/api/app.py:153-158,198-202；api/runtime_coordinator.py:255,262-263,1144-1191；services/network_service.py:154-161,196-202
- 优先级：CRITICAL
- 结论：采纳
- 覆盖：`f_backend_core_attr_error`
- 详细判断理由：生产装配中 `app.py:153-158,198-202` 将 RuntimeCoordinator 实例注入 NetworkService.supervisor_client；当 URL/token 齐备、`is_enabled()` 为真，网络后台操作第一次调用 `rebuild_edge` 就访问不存在的 `self.client`，在发出 HTTP 请求前抛 AttributeError，后续 `_auth_headers` 也未定义。NetworkService 捕获后保存 FAILED。这是当前受管调用链的首个失败点；从正式 UI 进入还另受 A2 路由错误阻断，不能把下游容器修改描述为这次操作已发生的事实。
- 修复说明：复用既有 `_client` 的创建/生命周期、Supervisor 凭据及错误契约，修复两个网络 RPC；不另建认证权威。测试必须通过正式装配的 NetworkService→真实 RuntimeCoordinator→受控 HTTP 服务，不能替换被验证的 Coordinator 方法。
- 验收标准：修复前证明受管 `is_enabled=True` 时进入第一次 RPC 即失败且下游零请求；修复后两种 RPC 的路径、认证、载荷、401/超时/5xx 和失败状态均正确。A35 的下游故障注入必须以本项与 A2 已解决或明确隔离入口为前提。

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
- 位置：api/v1/control_router.py:74；auth/service.py:43-45,389-396；auth/rate_limiter.py:55-68；gateway/server.py:421-426,731-760；gateway/registry.py:96-247
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_backend_core_control_client_ip`, `f_gateway_viewer_throttle_proxy_ip`, `f_global_sys_proxy_ip_cascade_dos`
- 详细判断理由：三类限流应分别分析，不能用一个模块的桶键反证另一个模块。控制 API 的 require_automation_token 使用 request.client.host 调用 AuthService.authorize_automation；后者的 source bucket 仅按 client_ip，另有独立 global budget。同一 Caddy 地址达到 source 阈值会影响经该入口访问不同 Profile 的自动化客户端，跨 Profile 连带风险成立。Gateway Viewer 的 AuthorizationThrottle 则按 `(source, profile_id)`，影响范围限于共享来源的该 Profile；Agent RegistrationThrottle 的并发和凭据失败预算又只按 source IP。三者不能混称同一种封禁。
- 修复说明：API 控制路由复用 resolve_client_ip 与受信代理配置；Gateway 的 Viewer 及 Agent 注册入口分别核对真实网络路径并采用明确受信来源解析。内部 Stream Agent 直接注册时应保留可验证的传输对端 IP；经已配置可信反代时才解析转发链，不能因入口是内部接口就忽略其 source-only 桶。保留有意设计的全局抗猜测预算，不把它误删为代理缺陷。
- 桶与影响范围：
    - 控制面：`auth/service.py:389` + `auth/rate_limiter.py:55-68`，source-only；代理来源合并会跨 Profile 连带限流。全局预算是额外机制，修复来源识别不承诺攻击请求永远不影响全局预算。
    - Viewer：`gateway/server.py:731` + `gateway/registry.py:209-247`，source/profile；负例应验证同 Profile 不同来源隔离，而非据此缩小控制面影响。
    - Agent 注册：`gateway/server.py:421-426` + `gateway/registry.py:96-205`，source-only；实际直连/反代拓扑需分别验证，注册 reservation 在成功、拒绝、超时和取消时仍正确释放。
- 验收标准：两来源、两 Profile、可信与非可信代理、伪造 X-Forwarded-For 分别测试；错误 Token 不把整台反代当成控制面单一来源。注册与 Viewer 的桶键、阈值与释放语义各自断言，不能只测 Viewer 即宣布全链修复。

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
- 位置：supervisor/core.py:1514-1556,1562-1655；supervisor/recovery_coordinator.py:145-235
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_supervisor_normal_exit_override`
- 详细判断理由：报告描述的“正常原生退出 journal 已送达，随后按 exited/dead/not_found 对账”路径确实存在：consume_disk_events 调用 `_reconcile_instance_observation`，后者在 `core.py:1598-1606` 直接上报 error/container_exit。normal-exit health 判定位于 container_status==running 的分支，无法反证已退出容器的缺陷。终态 ACK 去重会影响某次错误是否被接受，但不能替代本路径正确分类。初稿把报告归约为“所有正常关闭必复活”再反驳，撤回该表述。
- 修复说明：统一原生 journal、容器事实及 health 的优先级，在已退出容器路径校验 Profile/实例/配置版本后利用可信原生退出原因作终态分类；不能只在 running health 分支补判断。保留 owner-loss 等异常语义，Docker ExitCode==0 本身不足以替代正常原生退出证据。
- 验收标准：覆盖正常 journal 送达后容器已退出、API 暂不可用后重放、终态 ACK 前后去重、错实例/错版本和 owner-loss；验证 API 实际最终观测及自动恢复行为，正常关闭不被合成 error 覆盖。不能用运行中 Agent health 正例替代 exited 分支验证。

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
- 位置：src/frontend/src/features/browser-session/adapter.ts:26,50,98,108-109,133,152,183,211,251,272-274,365
- 优先级：LOW
- 结论：采纳
- 覆盖：`f_frontend_adapter_any_casting`
- 详细判断理由：报告列出的四处是示例，不是全部改动范围。当前 adapter.ts 对 `any` 的检索共有 14 处：26、50、98、108、109、133、152、183、211、251、272、273、274、365，覆盖扩展 Window、原生构造器与发送参数、Web Locks 回调、WebSocket 事件、RTCStats 及生命周期事件。此前按四处描述会低估接口梳理和回归面。
- 修复说明：按整个 adapter 的实际边界清单定义类型，关联 A40 的统计样本契约和 A20 的会话代次；复用 DOM/WebRTC/WebSocket/Web Locks 标准类型。外部未知对象使用 unknown 加运行时校验，不以粗泛断言代替检查；不据此扩成全仓 any 清理。
- 验收标准：逐项核对上述 14 处及其直接消费者，类型检查与信令、构造器原型/静态行为、Web Locks、统计、焦点、pageshow 测试通过；需要保留的极小例外逐项解释，不用忽略规则把未建模接口隐藏。

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
- 详细判断理由：生产 Browser Dockerfile 全量复制 cbrowser 后端包，报告指出可在受损 Browser 内读取无关服务源码，这一事实成立。初稿额外引入“凭据泄漏”作为反证对象，与报告原论点无关，撤回。采纳依据是运行交付应与 Browser 职责和实际 import 闭包匹配；删源码本身不阻止获得其它能力，也不能当作凭据隔离或漏洞消除的证明。
- 修复说明：从 Browser 入口与 runtime_agent 实际依赖确定最小模块交付，移除与运行无关的 API/Gateway/Supervisor 代码；保留字体、预览、CDP、下载、协议模型等真实依赖，按镜像构建验证缺项。不机械复制报告中的示例目录清单。
- 验收标准：镜像中实际模块清单与 import/入口冒烟、健康、字体、预览、CDP、下载和停止链路一致；无关服务入口未交付，必要功能完整。权限和凭据安全分别由对应条目验收，不借源码裁剪宣称额外安全收益。

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

### A31. 统一 API 测试镜像交付入口并同步现行指南

- 来源：bundle_local_tests_unit_fixtures
- 位置：tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile；tests/unit/test_baseline_runtime_regressions.py:68-104；docs/guides/supervisor_validation.md:16,19；tests/fixtures/e2e_env.py:17；tests/fixtures/gateway_probe/topology.py:101；tests/e2e/test_supervisor_container_graph_e2e.py:71,153
- 优先级：LOW
- 结论：采纳
- 覆盖：`f_tests_abandoned_api_dockerfile`
- 详细判断理由：测试代码与脚本中未发现现行构建调用，但该 Dockerfile 仍被 test_baseline_runtime_regressions.py 的文本测试引用，且现行 supervisor_validation.md:16,19 明确指导将它构建为 CBROWSER_API_TEST_IMAGE。该镜像变量又被 e2e_env、GatewayTopologyHarness 和容器拓扑用例实际消费。因此不能写成“仅一处文本引用”“无运行消费者”；失去的是可验证的统一构建/交付关系，指南仍保留旧入口。
- 修复说明：先验证现行正式 API 镜像及统一 harness 能满足这些 E2E 所需 API 角色，明确 CBROWSER_API_TEST_IMAGE 的生产方式与含义，再合并私有 fixture 构建入口。同步修改 supervisor_validation.md 的环境变量、构建入口与相关说明，移除被替代 Dockerfile/专属 dockerignore 及仅验证它的文本测试；不能先删文件再留下失效指南或任意删除仍被消费的镜像变量。
- 验收标准：全仓核对脚本、测试与现行文档中的 Dockerfile 和 CBROWSER_API_TEST_IMAGE 引用，构建指令真实可执行且注入统一镜像；容器图与 API 相关 E2E 使用该入口通过。若发现不可替代运行行为，先报告差异，不以“死文件”假设强行删除。

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
- 位置：api/app.py:153-158,198-202；services/network_service.py:135-202；api/runtime_coordinator.py:255,262-263,1144-1191；supervisor/core.py:2695-2755；supervisor/docker_adapter.py:1830-1898；adapters/database/repository.py:1278-1322；gateway/config.py:44-45,57-77；supervisor/operation_journal.py
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_global_arch_network_switch_atomicity`, `f_backend_core_network_active_leak`, `f_supervisor_caddy_rebuild_no_rollback`
- 决策记录：原 D1；用户在文档选择 A，采用持久化、可恢复的网络配置事务。
- 用户决策：A（持久化配置事务）。
- 详细判断理由：必须区分三层证据。第一层为当前正式可达链路：app 注入 RuntimeCoordinator，受管 is_enabled 为真时，NetworkService 在 Phase 1 首次 RPC 因 A1 的未定义属性失败并记录 FAILED，尚未执行 Caddy 删除或 Stream 重建；从 UI 进入还受 A2 阻断。第二层为下游静态缺陷：Supervisor/DockerAdapter 的重建方法本身先删 Caddy 再 run，失败无恢复，NetworkService 后续步骤无跨组件补偿；它们可通过独立调用/故障注入验证，但不能作为本次正式链路已执行的事实。第三层是本文选定的未来恢复设计。A1/A2 是正式链路验证前置；修复它们不能掩盖第二层缺口，本项也不能靠当前不可达证明端到端故障已复现。
- 修复说明：由 API/SQLite 作为网络配置、操作阶段和最终提交/放弃的唯一裁决者，在原有配置/操作记录内补足恢复字段；磁盘导出、Gateway 缓存和 Supervisor journal 均不得独立提升配置版本。各状态的权威关系与提交边界先写入契约，再实施。
- 现状与拟定状态权威：

|状态面|当前事实|本项拟定职责|
|---|---|---|
|API/SQLite|repository.py:1298 已规定 DB applied version 优先；同库有 pending/active operation|已提交配置与操作终局的唯一权威；配置意图、阶段、恢复方向仍存同一操作权威，不另建平行总账|
|磁盘 applied 文件/Caddyfile|导出副本；当前 NetworkService 先写文件后记 DB，有崩溃间隙；空 DB 可从磁盘启动|由 API 决定导出的版本化快照，含 operation/generation/hash；DB 非空时不能覆盖 DB；首次空库导入只作为显式初始化事务，不在日常恢复时争夺权威|
|Gateway Origin 缓存|gateway/config.py:44-45,63-75 按 mtime 惰性加载并保留缓存|消费 API 授权的发布快照并回执实际 generation/hash；mtime 只作重读提示，不能充当已切换证明，也不能无限保留无法核实的旧 Origin|
|Supervisor operation_journal|本地持久命令请求/结果，用于生命周期幂等；当前网络 RPC 未接入它|执行回执及资源补偿证据，不裁决全局配置；子命令 ID 从 API 操作/阶段/资源派生，不能因旧缓存结果而跳过 Docker 实况核验|
|Docker/运行进程|Caddy 绑定、Stream 标签/参数、注册等实际状态|用于核验和恢复的物理事实，既不替代 API 的意图，也不凭日志中 status=ok 宣布全局提交|

- 执行协议（全部为拟实施要求，不是现状）：
    1. API 在同一数据库事务中排他登记操作，冻结旧已提交配置、目标配置、operation_id 和执行代次；并发新操作被拒绝。密码不进入持久化操作或错误日志。
    2. prepare 生成候选快照并验证配置、端口、Caddy、归属与旧入口恢复材料。候选配置有 operation 标识，不能冒充已提交 applied version；各组件准备完成后回执实际内容 hash。
    3. API 持久推进操作后命令参与组件安装候选代次，逐资源记录结果；API/Gateway 的暂态 Origin 接纳也必须由同一活动操作明确授权，记录有效代次与清理条件。没有隐含的独立配置开关或靠 mtime 恰好变化推进流程。
    4. 重建 Caddy 前保留足够旧镜像/配置/卷/网络/端口身份以恢复；同端口冲突可有界中断，但新建失败必须能恢复旧入口。Stream 按实例围栏逐项执行，与 A3/A9 共用清理和占用语义。
    5. readiness 收集 Caddy 实际绑定、API/Gateway 当前激活 generation/hash、Origin 判定、Stream 实例与注册/媒体配置回执。Gateway 未 ACK、仍消费旧缓存或接口不可验证时，不允许最终提交；一次普通 health 200 不足以证明版本一致。
    6. 满足 readiness 后，仅 API 数据库事务可提升 network.applied_version 并记录 COMMIT 决定；之后按该决定完成/核对派生导出与回执。此时崩溃只续做提交收尾，不能因客户端丢响应退回旧版本。
    7. COMMIT 前失败由 API 持久记录 ABORT/补偿方向，命令所有已改变组件恢复旧配置，Gateway/API 同步撤销候选 Origin，并以新的执行代次确认旧内容；配置版本可回到旧值，执行代次仍递增，防止旧回执或 mtime 缓存误判。补偿失败保持恢复未完成状态，不释放仍占用端口，不让下一操作覆盖现场。
    8. 重启恢复先读 DB 终局与活动阶段，再对照各组件回执和实况：已有 COMMIT 续完目标，有 ABORT 恢复旧配置，无终局则在排他恢复中作出并持久裁决后再执行。Supervisor/API 短暂失联不能自行猜测成功或切换恢复方向。
- 验收标准：先复现 A1 处下游零请求；修复 A1/A2 后再执行真实链路并在 Caddy、部分 Stream、Gateway 缓存未更新、Origin 生效、DB COMMIT 前后与磁盘导出间隙注入故障/重启。验证 DB 决定唯一、Gateway ACK 可验证、旧/目标快照无永久分裂、幂等重放不碰新实例、原有端口不提前释放。
- 依赖与回退：A1/A2/A16/A24/A29 为真实调用及契约基础，A19/A21 呈现实际阶段；DB schema 变化按项目迁移/备份规则，配置补偿不等于二进制回滚或数据库降级。该选择不承诺多容器瞬时原子，也不重新引入旧客户端兼容层。

### A36. 将 UDS 地址与可变数据根解耦

- 来源：bundle_local_backend_runtime_supervisor, bundle_repository_summary
- 位置：supervisor/path_validator.py:20-44；supervisor/core.py:1670-1685；supervisor/control_server.py:467-490；Agent socket 创建与对应卷映射
- 优先级：MEDIUM
- 结论：采纳
- 覆盖：`f_supervisor_sun_path_proc_fd_hack`
- 决策记录：原 D3；用户在文档选择 A，建立独立且长度有界的 UDS 运行根。
- 用户决策：A（独立短路径运行根）。
- 详细判断理由：当前 short_unix_socket_path 不是死代码：SupervisorCore.\_agent_uds_client 在 core.py:1677 使用它，control_server.py:482 的自动化 WebSocket 也使用它。采纳的是将 UDS 地址从可变数据根解耦，同时完整迁移这些活跃消费者；“删除无消费者代码”只能是所有调用方迁完后的收尾条件。
- 修复说明：定义生产者与 HTTP/WS 消费者共同使用的有界 socket 运行根、标识规则、挂载和归属校验。全部现行消费者迁移后再移除 proc/相对路径适配；实际依赖目录 FD 提供的防替换能力须以新拓扑下等价机制保留。
- 切换与回退语义：
    - 不保留长期运行的新旧地址探测、双读或静默 fallback，这是零兼容约束。
    - 升级事务仍须 prepare：验证新挂载/路径/权限，保存旧完整镜像与拓扑，停止受影响运行实例后切换生产者和全部消费者，完成真实 UDS readiness。前置失败保留旧拓扑，切换中失败恢复旧完整部署。
    - 部署级回滚启动上一套匹配的二进制、挂载与路径规则，不要求新代码同时识别旧地址；必要时重新创建运行实例并验证。禁止兼容分支不等于禁止恢复旧部署，与 A35 的事务恢复要求一致。
    - 不改动持久 Profile 数据；旧实例停止与 socket 清理由受管身份限定，不能删其它实例目录。迁移有中断或数据/schema影响时须提前列清备份与恢复路径。
- 实施步骤：限定编码后路径字节上界及标识唯一性；明确宿主根到容器短路径映射；更新 Agent 创建、Core HTTP、control_server WS、Compose/动态卷与 harness；保留实例/归属/软链接防护；迁完再删除旧适配及仅服务该适配的测试。
- 验收标准：真实 HTTP health/control 与 WS CDP 均走新根；最长合法标识、深持久数据根、两个 Profile/实例、软链接及目录替换负例覆盖；在切换各阶段故障时恢复旧完整拓扑后旧客户端仍能连接，正常新部署没有运行期双地址 fallback。

### A37. 显式收敛 Supervisor 进程权限，不宣称削弱 Docker 控制权

- 来源：bundle_cross_validation, bundle_local_contracts_deploy_infra
- 位置：compose.yaml:71-76；config/docker/supervisor_runtime/Dockerfile；supervisor 的直接文件归属/缓存操作与 helper 启动路径
- 优先级：HIGH
- 结论：采纳
- 覆盖：`f_docker_supervisor_root_cap`
- 决策记录：原 D4；用户在文档选择 A，保留 Supervisor 为唯一高信任 Docker 控制者并落实最小权限。
- 用户决策：A（保留现行控制信任模型，审计并收敛权限）。
- 详细判断理由：现有 Compose 已有 read_only:true 与 cap_add:[FOWNER,DAC_OVERRIDE]，不能描述为“没有显式权限约束”。但 cap_add 本身只添加能力，不等于 cap_drop:[ALL] 后逐项授予；实际进程 capability 集仍须 inspect/运行测量确认。root/Docker socket 是当前高信任控制者的能力，非 root 或 cap_drop 不会限制经 Docker API 创建高权限容器的权能。
- 采纳目的：仅审计并收敛 Supervisor 常驻进程直接持有的 Linux 权限，防止非必要直接文件/进程操作；明确它不改善“完整 Docker socket 等同宿主控制权”的信任边界，不以此声称阻止 Supervisor 受损后经 Docker 越权。初稿以 Docker 信任边界改善为题立项、用 A25 凭据成果验收，撤回。
- 修复说明：保持用户选定的唯一高信任 Docker 控制者架构，先测现有 User/CapEff/CapBnd 与直接 chown/chmod/缓存操作需求；只有可证明存在非必要默认能力，才改为显式剥离后授予实际所需集合。helper 的 NET_ADMIN/FOWNER 按各自容器验证，不加到常驻进程；root 是否可移除由实际文件归属需求决定，不预先承诺。
- 验收标准：提供变更前后同镜像/编排下实际 capability 差异及被删除能力的具体负例，必要归属处理、缓存初始化、helper 调度、启动/停止和恢复全链通过；不能仅检查 YAML 文本或 A25 的凭据不可读就记本项完成。若没有可安全收敛的能力，交付该结论和需求证据，不为保持“修复成果”另建服务或偷偷放回默认能力。
- 范围与残余：只读根策略保持，新增安全选项需在当前平台验证；A25 单独负责 secret 挂载，本项不重复计功。若目标变为真正限制 Docker 控制权，必须另选可校验资源/挂载/HostConfig 的执行边界或隔离 daemon；这不在用户已选 A 的范围内。

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

### A39. 中立验证中文文字提交方案与依赖交付边界

- 来源：bundle_cross_validation, bundle_local_backend_stream_gateway, bundle_repository_summary

- 位置：src/backend/cbrowser/stream_agent/x11_keymap.py:35-194

- 优先级：HIGH

- 结论：采纳

- 覆盖：`f_stream_agent_x11_keymap_monkeypatch`

- 决策记录：原 D2；用户在聊天明确确认选 A，先做隔离验证，按证据确定中文提交正式路径，不默认二开 Selkies。

- 用户决策：A（先验证输入方案）。

- 详细判断理由：静态核对确认现行客户端与服务端已有通过 co,end 提交 composition 最终文字的调用链；固定 Selkies X11 输入实现随后执行 XTest/xdotool，历史 d014/d017 记录了特定环境下的 XKB 问题。本轮未运行真实中文输入，不能据调用链宣称端到端输入已通过。Weblink 提供了另一组前端输入、传输与 Windows 注入样例。它们都不能单独证明本项目必须二开、必须新建文本协议，或必须采用零宽守卫。用户选择 A 是授权先比较方案，并未选定最后实现。

- 修复说明：建立中立的隔离对照，先列现行功能/安全/平台要求和可变更的旧设计约束，再按同一矩阵评价候选。每个候选都记录权限、焦点、文本语义、事件可观测性、维护/升级和工程交付要求；不因是否二开、是否使用剪贴板或是否涉及私有 ABI 预先判输，按证据和同一正式验收标准作结论。

- 候选范围（均未定案）：

    - 未修改的固定 Selkies 与当前补丁分别作为基线，真实复核历史故障；不能以历史短测代替当前版本完整输入行为。
    - 现有/新本地 IME 暂存方案、现有 co,end 或显式文本协议，分别测试；Weblink 的 DOM 取值、延后收尾、两端守卫是候选技术，不是本项目已经采用的设计。
    - Linux 可用的成熟文字提交机制、浏览器专用接口、上游源码修复或派生包均可进入对照；记录它们对网页、富文本、地址栏、权限和输入事件的不同边界。
    - 剪贴板方案也可在隔离测试作为对照，但当前“不用剪贴板提交”仍是生效规约；列出改规约所需的副作用与用户策略决策，不把尚未批准的正式变更当成已允许，也不在技术比较开始前把它排除。

- 当前工程落点：本仓 vendor_selkies_web.py 只从锁定 wheel 提取前端资源，现有 uv.lock/requirements/Stream Dockerfile 消费上游包，没有 Selkies 服务端源码构建与派生 wheel 发布流水线。若派生包胜出，方案必须补全源码固定提交、可重现构建、包分发/哈希、依赖锁、服务端安装与前端资源同源、许可证、升级和回滚；不能说“改 wheel”已有现成工程入口。本轮不执行该构建或外部发布。

- Weblink 证据如何使用：

    - W1/W3 的 composing/finishing、DOM editor、setTimeout 收尾与零宽守卫仅列对照维度；先比较官方 Selkies 已有捕获器，不默认加第二套。验收要求是正确提交与焦点隔离，而不是必须通过某种零宽守卫实现。
    - W2 的 64/1024 按 UTF-16 code unit 计，不是 WebRTC 标准上限；对比按不同语义长度/字节预算分包的正确性。Enter/Tab 是物理动作还是文本内容要按控件行为评测，不能机械翻译。
    - 本地一次提交去重与跨断连交付语义分开；任何候选都验证中断、焦点变化与重复风险，不从可靠 DataChannel 推导跨重连恰好一次。
    - W4/W5 展示 Windows 特定注入：native path 返回 Ok(false) 才进入 Unicode 路径，已返回 Err 的投递通过 `?` 传播，不重放。Linux 后端不能直接移植这些 API；这不否定派生依赖或其它成熟 Linux 输入实现作为候选。

- 验证矩阵：普通/密码/多行输入框、contenteditable/富文本、地址栏及浏览器搜索；中英切换、长中文、生僻字、Emoji/组合字符、用户真实零宽字符、换行/Tab、选择区/光标、撤销、快捷键、取消组合、compositionend/input 顺序交换、失焦/切 Profile/连接代次变化、分包中断、双 Viewer 与跨 Profile 隔离。必须区分本地捕获、消息传输、远端最终编辑三层结果。

- 验收标准：交付每个可行候选的环境、代码/接口来源、同矩阵结果、权限与事件差异、未覆盖场景和可实施入口；比较前不得把任何候选技术写成“采用”。能说明不适用原因也属于有效研究结论，不强行承诺一定替换现有路径。正式方案变更另行更新 specs/blueprint/ADR 和实施范围。

- 安全与实施边界：研究只用隔离 Profile、测试字符串和测试剪贴板，不触碰用户实际数据；记录的是当前规范与候选方案冲突、以及需用户决定的变更，不据“中立验证”授权上线任何路径。真人接管、Profile 隔离及不记录真实文本为共同要求；不默认移植 Weblink 的 grant/lease 架构，不把研究完成记成生产输入重构完成。

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
- 详细判断理由：静态证据支持“编码帧可复用”这一研究方向，但固定依赖中尚无已验证稳定的独立录制订阅接口。produce_data 是 Selkies 模块内回调，不等于对外录制 API；本仓也没有把录制注册为捕获消费者。policy.py:554-573 在无活跃 Viewer 时暂停捕获，届时没有视频预编码样本。因此必须先证明接入点和捕获存续条件，不能先画一条已成立的独立录制拓扑。
- 采纳范围：技术可行性研究与证据，不是已选定录制架构或完整会话录像功能。评估有流时的复用、无流时的边界，并提出需变更的依赖/捕获/Artifact 契约；没有稳定落点也可形成“不宜按当前条件实施”的有效结论。
- 修复说明：按以下前置门逐项验证。前一门未通过时，后续拓扑只能列为条件方案，不能登记成当前能力或绕过失败继续写生产实现。
- 门 1——稳定接入：定位固定版本实际编码帧与 Opus 回调，验证 codec/参数集/pts/dts/time_base、原生 buffer 所有权和可用接入机制。已有受支持接口、明确组件扩展或依赖源码扩展分别记录；produce_data 内部可见只证明数据存在，不能作为已稳定订阅。需要扩展依赖时给出维护/构建/锁定/回滚方案，是否采用由结果决定，不假设本仓已有派生流水线。
- 门 2——捕获存续：第一组实验严格保持现行 Viewer 策略，只在已有活跃流时证明旁路封装；无 Viewer/全后台时样本停止是预期观察，不得报录制完整。若目标是无 Viewer 连续录制，必须先提出并确认“录制是否计作独立消费者”、帧率/音频/CPU 配额和生命周期新契约，再开展第二组验证。录制生命周期不由某 Viewer 对象拥有，不等于捕获可脱离所有 Viewer 持续。
- 门 3——隔离旁路：只有门 1/2 条件满足后，才验证预编码样本→独立有界队列→封装写入 worker 的候选；采用包数/字节数上限、不可阻塞捕获/发送、溢出或慢盘只失败录制。RTP 前样本可避免去包；若仅有 RTP，须验证重排/去包/时钟及完整样本恢复。队列或 worker 不被当作已有代码落点。
- 门 4——容器与音频：用实际 codec 决定 MKV/MP4 等候选，验证关键帧起始、参数集/NAL framing、音视频同步、8/30 变帧率、静止和静音间隙及代次切换。复用已编码 Opus 才是音频免重编码；PCM→Opus 是对该 PCM 的首次编码，若为录像另开则是新增编码开销，不称“把编码音轨重新编码”。encodedAudio 分支复用本身不编码；混音、重采样或转换原有压缩音轨需另列成本。
- 门 5——受管存储：当前 Stream 无 /exchange，Artifact 补登不扫描 recordings 子目录。候选输出须由 Supervisor 分配最小必要 staging 挂载/写入者，完成并封装校验后经受限事件/RPC 交 API 单写者登记，保留路径/实例/配额围栏；不能直接把子目录当作现有自动登记入口。
- 条件目标拓扑：在已验证接入机制及捕获消费者契约的前提下，单 Profile 编码样本可同时服务 RTP 与一个受管录制旁路；这是研究待证设计，不是固定依赖现有功能。无消费者捕获暂停、低权限 Stream、媒体不经 API 转发等现行契约在正式变更前保持。
- 技术验收：
    - 明确接入机制是否稳定、是否需改依赖，以及有/无 Viewer 两类实验的差异；只完成回调探针不能报完整独立录制可用。
    - 用编码器/采集调用证据判断是否增加新视频编码或音频编码，产物独立解复用/解码及时间戳正确；不依赖“免重编码”口号推断性能。
    - 同场景测 CPU、内存、队列、磁盘与 Viewer 媒体指标；测慢/满盘、溢出、writer 崩溃、Stream 替换、codec/分辨率变化和退出收尾。失败片段标 partial/failed，不能宣称完整审计。
    - 验证 Profile 授权隔离、最小挂载、完成事件幂等与 Artifact 读取/删除；不能因研究需要修改真实 Profile、真实剪贴板或生产数据。
- 交付与未决产品条件：报告固定版本接入缺口、候选实现、实验结果、依赖/捕获契约变更清单及结论。谁可录制、持续或仅观看、是否录音、保留/配额策略仍待正式立项；本项不把这些条件预选为可上线功能。

### A42. 自动化隧道登记沿用现行 token_id 主体语义

- 来源：bundle_local_backend_core
- 位置：api/v1/control_router.py:148-179；api/v1/automation_router.py:118-125,158-166；services/control_service.py:218-278；services/tunnel_registry.py:29-58
- 优先级：LOW
- 结论：采纳
- 覆盖：`f_backend_core_automation_tunnel_agent_id`
- 修订记录：撤回原 R1。原拒绝依据只按字段名推断身份定义，未核对现行控制面实现，判定错误。
- 详细判断理由：control_router 的 claim/handoff 已把 token_id 当作 agent_instance_id 使用，automation_cdp 也用 token_id 进行隐式 claim；但相同隧道 registry.register 却写 agent_instance_id=None，丢失既有主体标识。报告建议与当前领域语义一致，不能用另行设想的“执行器实例 ID”概念拒绝它。
- 修复说明：复用成功鉴权/claim 得到的有效 token_id，传入 API 层隧道登记的 agent_instance_id；不把原始 token、哈希或未知字符串写入记录。若存在未启用控制服务的测试/显式配置路径，同样明确取得经鉴权的 token_id，不能依赖仅在某 if 分支定义的局部变量。
- 验收标准：从真实鉴权与控制 claim 进入隧道，registry 的 token 身份与当前 control 主体一致；两 Token、多 Profile、撤销/接管/关闭和 agent_session_id=None 语义均验证。身份缺失/鉴权失败不登记，日志与对外响应不暴露凭据值，不因本修复更改现行领域身份模型。

## 不采纳项

### R2. 未证实 start 命令重放缺口的完整语义，不机械复制 stop 账本

- 来源：bundle_local_backend_runtime_supervisor
- 位置：src/backend/cbrowser/supervisor/core.py:2114-2235
- 优先级：LOW
- 结论：不采纳
- 覆盖：`f_supervisor_start_profile_journal`
- 详细判断理由：报告论点是 start_profile 未接入持久操作账本，不能简化成“所有正常重复 start 都返回 409”。未调用 begin/complete 是事实；running session 的直接返回只证明同一活跃生命周期内的幂等，不能证明跨重启或部分启动失败的 operation_id 结果重放已经实现。409 出现在已有非 running session，是否由同 operation_id 重试触发及应否重放原结果，还需要具体时序/契约证据。
- 当前处置：不直接采纳“在 start 入口照搬 stop 的 begin/complete”修法；先区分当前状态幂等、命令结果幂等和跨生命周期重放。如果报告要求的持久命令语义属于现行契约，应据此另行修正分类，不能以 running 分支当成永久反证。本项保留这一限制，不宣称缺口不存在或已被 reset_blocked 覆盖。
- 不采纳理由：当前可核事实不足以定义启动中断、旧 operation_id 与新实例之间的结果保留边界，机械复制账本可能返回过时实例；不把未跑出的竞态写成已证实，也不凭方法名推定完整合同。

### R3. 不直接删除停止流程全局锁

- 来源：bundle_local_backend_runtime_supervisor
- 位置：src/backend/cbrowser/supervisor/core.py:2404
- 优先级：LOW
- 结论：不采纳
- 覆盖：`f_supervisor_stop_global_lock`
- 详细判断理由：锁存在属实，但报告没有锁竞争测量与共享状态互斥分析；“不同 Profile 独立”不能证明共享端口、扫描和会话账本无需协调。仅删除锁不是根因级并发设计，也无法从当前证据确认这是实际性能缺陷。

### R4. 不以占位身份或放宽协议修复关闭通知，竞态结论保留

- 来源：bundle_local_backend_stream_gateway
- 位置：src/backend/cbrowser/stream_agent/agent.py:957; protocol.py:89; messaging.py:86-105
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：`f_stream_agent_tunnel_close_empty_session`
- 详细判断理由：`session_id=self.agent_session_id or ""` 与非空模型约束确实存在；报告担忧的是失败时关闭通知不能正确发出。该构造异常位于内部 try/except，不能把未通知与未捕获崩溃混为一谈。注册后才创建 worker、通知前检查 generation/ws.closed、断连 finally 清空 session 的事实支持检查时序，但单靠这些静态守卫不能穷尽取消/清理竞争，也不能证明缺陷绝不触发。
- 当前处置：不采纳占位 session_id 或放宽信封约束。若复现有效 worker 仍需通知却丢失注册身份，应绑定 worker 创建时的真实注册代次，并验证关闭通知或明确清理结果；不能造一个能通过 Pydantic 却无领域身份的字符串。
- 证据限制：本轮未跑出此竞态，故不把关闭通知完整性标已验证，也不以“不会崩溃”否定通知失败的价值。后续测试须覆盖 Gateway close、worker 异常与取消并发、None session 及新代次替换。

### R5. 不采用固定 Origin 回退，启动配置缺失由初始化链路解决

- 来源：bundle_local_backend_stream_gateway, bundle_repository_summary
- 位置：src/backend/cbrowser/gateway/config.py:57-75
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：`f_gateway_missing_applied_network_403`
- 详细判断理由：报告准确指出首次冷启动没有 applied 文件时 Origin 列表为空，合法 Viewer 会被拒绝；其建议是固定本机白名单回退。当前 Gateway 明确要求从已应用配置派生 Origin，部署负责提供初始版本，因此不采纳常量白名单作为第二套配置来源。不能因该安全取舍抹去冷启动可用性问题。
- 正确去向：A24 保证初始化产物可验证且真实可供 Gateway 消费；A35 规定运行切换与缓存确认。文件缺失/损坏时应有可诊断的未就绪状态与恢复路径，不能“健康但永远 403”就称验收通过。
- 不采纳边界：拒绝固定 Origin 回退，不是拒绝修启动流程；不推测报告意图绕过鉴权。实际端口/网络模式随配置变化，回退常量不能满足该契约。

### R6. 同步路由导入不足以证明首屏性能缺陷

- 来源：bundle_local_frontend_core_shared
- 位置：src/frontend/src/app/router.tsx:4-10
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：`f_frontend_router_no_code_split`
- 详细判断理由：同步导入属实，但报告未给构建分块、压缩体积或首屏指标，Selkies 大型官方客户端又在独立 iframe。按路由切块并非必然更优；当前没有冷启动性能缺陷或需求证据，不因抽象最佳实践新增 Suspense/加载状态。

### R7. 区分 SSE 单 Profile 失效与窗口回焦全体 stale 查询重取

- 来源：bundle_local_frontend_core_shared
- 位置：features/profiles/useProfilesQuery.ts:444；app/useRuntimeSnapshot.ts:16-21；app/providers.tsx:55-61
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：`f_frontend_runtime_snapshot_thundering_herd`
- 详细判断理由：SSE 的 runtime 失效键限定为 event.profile_id，因此原报告“每条 SSE 必触发全部 runtime 重取”没有由此调用点得到支持；但初稿由此延伸成没有全量重取路径也错误。AppProviders 配置 staleTime=5000 与 refetchOnWindowFocus=true，useRuntimeSnapshot 为全体 Profile 挂载活跃查询；页面恢复焦点时，已 stale 的这些查询可能集中重取，初次装载也有 N 个 runtime 请求。
- 当前处置：不采纳以错误 SSE 因果为依据的聚合接口或仅读缓存修法；保留焦点重取和初次 N 查询这一实际成本，不宣称“没有惊群/无定时轮询”即可排除它。仅消费已有缓存还可能遗漏未加载 Profile 的统计与错误，不能无证据删取数职责。
- 验证边界：后续量化普通 SSE、SSE 初始快照、失焦超过 staleTime 后回焦、Profile 数变化时的实际请求数和状态完整性；若确认焦点重取造成问题，基于该真实触发器确定查询策略/聚合方案，不凭当前错误论证直接改全局 refetchOnWindowFocus。

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
- 位置：.repo_template/scripts/template_sync/state.py:14-16；.repo_template/scripts/template_sync/common.py:34-49
- 优先级：LOW
- 结论：不采纳
- 覆盖：`f_tool_sync_state_json_type_check`
- 详细判断理由：read_state 在 state.py:14-16 调用 common.\_load_json_object，后者 common.py:34-49 检查顶层是否 dict，非对象则抛带恢复指引的 SyncError。结论为误报，但初稿仅列 state.py:27-38 不能指向该证据，现补齐真实调用与实现位置，不重复添加类型断言。

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
- 详细判断理由：提案的编码复用原则值得研究，但字面实现依赖未经证明的接口与存储前提。当前锁定 WebRTC 路径为 pixelflux/pcmflux 产出编码样本后打包 RTP，produce_data 是内部回调，Stream 无 /exchange；Artifact 也不自动扫描 recordings 子目录。容器还需要参数集、样本边界、时间戳和正确收尾，不能把已有 RTP bytes 直接当文件内容。
- 音频术语更正：W9 的 encodedAudio 分支复用压缩包，不做编码；PCM/MediaStreamAudioTrackSource 分支生成 Opus，属于对应原始音频的编码，不能笼统叫“音轨重新编码”。若从已存在的压缩音轨解码再编码才属于重编码；为录像另开 PCM 编码路径虽非重编码，仍是新增 CPU 编码成本。
- 不采纳内容：不承诺零 CPU/零复制/零延迟，不按未验证的 GStreamer appsink 或固定下载子目录直接接线，也不把 48 kHz 采样率当已编码证明；默认再抓屏解码再编码不能被包装成免重编码方案。
- 正确去向：A41 先过稳定接入与捕获存续两道前置验证门。R18 拒绝不成立的具体前提，不否定未来采用已验证封装组件或其它可满足需求的实现。

## 实施组织与验证要求

本节为后续实施边界，不创建 task、不登记依赖状态、不授权发布或代码执行。若进入实施，依项目流程形成可独立验证的工作项，每项保持根因范围，禁止顺手扩展功能。

|工作面|关联决策|先决事实与联合验收|
|---|---|---|
|网络应用完整链路|A1、A2、A16、A19、A21、A24、A29、A35|先统一接口与配置权威，再做实际切换、故障补偿、重启恢复；前端仅反映真实操作结果|
|容器生命周期与占用|A3、A8、A9、A11、A15|统一实例围栏及清理语义；与网络补偿共享资源占用事实，不能靠删除 session 假装清理完成|
|安全边界|A4、A10、A14、A25、A37、A42|限流桶按模块验证；进程能力收敛不宣称削弱 Docker 权能；凭据挂载和隧道身份分别验收|
|运行控制与 UDS|A12、A13、A36|先明确唯一运行地址和会话生命周期；验证真实健康/CDP/控制/预览消费者|
|前端契约与生命周期|A6、A17、A18、A20、A22、A23|保留现行导航与多页面语义；错误、终态和旧异步回调均可观测且可恢复|
|测试与交付真实性|A5、A26、A27、A28、A30、A31、A38|分别保持实际产品覆盖、镜像依赖闭包、资源隔离及必跑证据，不用文本断言代替真实行为|
|中文输入方案验证|A39、R17|Weblink 技术列入同矩阵候选，不预设暂存/零宽守卫胜出；依赖二开、剪贴板等按相同标准比较，当前规约变更需另行定案|
|诊断采样与渲染|A40|与 A20/A23 统一会话代次和类型；采样共享、叶子订阅，保持首帧/恢复判定|
|免重编码录制验证|A41、R18|先验证真实编码样本旁路和 Artifact 边界；不默认实现完整录像、不承诺零 CPU|
|现行文档修正|A32、A33、A34|随对应实现同步核对 blueprint/specs/ADR 传播，保留历史事实，遵守 R15/R16 暂缓边界|

- 每项先以触达生产逻辑的失败用例证明缺口，再修复；旧测试语义失效时整体替换/删除并记录理由，禁止就地改预期迎合实现。
- 定向验证通过后运行与改动范围相符的项目门禁，真实 Docker/Chrome/引擎验证按要求执行；本机基准仍为 Mac+OrbStack，未执行的环境或长期压力检查明确记 NOT_RUN，不记 PASS。
- schema、TypeScript、设计 token 等派生产物均从权威源生成；检查型门禁不得改写受跟踪文件。所有调试与一次性材料只写已忽略目录或正式登记 spike 工作区。
- 数据/运行拓扑改变前准备可恢复备份、受影响实例清单与回退方式；生产数据不因“零兼容”直接删除。发布、外部 issue、push 均需已有明确授权，本文未提供这些授权。
- A 项“采纳”表示方案进入后续实施范围，不表示已经完成。R 项“暂缓”保留问题状态；A39 已选择先验证输入方案，验收对象首先是可信的方案结论，不能以探针完成冒充输入重构已交付。

## 本轮复核修订记录

本次按用户逐条复核意见修订，不将文档修订视为代码修复。事实、当前可达路径、潜在下游缺陷和拟定设计分别标明。

|复核点|修订与证据|去向|
|---|---|---|
|A35 与 A1 现状冲突|正式注入链在首次受管 RPC 抛 AttributeError；删除 Caddy/重建 Stream 只作下游静态缺陷，正式故障验证依赖 A1/A2|A1、A35|
|R1 错误身份假设|control_router 及隐式 claim 已用 token_id；撤回 R1，沿用现行主体语义|A42|
|A4 混用反证对象|控制面 source-only、Viewer source/profile、注册 source-only 分开，补注册路径与全局预算区别|A4|
|录制订阅/无 Viewer 前提|produce_data 无稳定外部订阅证明，现行无活跃 Viewer 即暂停；先验证接入与捕获条件，独立拓扑标为条件方案|A41|
|输入验证预设胜负|把 Weblink 暂存/守卫改为候选；二开、剪贴板、私有接口与其它方案按共同标准比较，区分当前规范与可提议变更|A39|
|UDS 双读与回滚混淆|禁止长期运行兼容，不禁止部署事务恢复旧完整镜像/挂载；列明 Core HTTP 与 control_server WS 是活跃消费者|A36|
|权限手段/收益错位|已有只读根和 cap_add 如实保留；只测直接进程 capability 收敛，不声称约束 Docker socket；A25 不重复计功|A37|
|网络多份状态无裁决|API/DB 为唯一终局决定者；文件派生、Gateway 缓存/ACK、Supervisor 回执各有职责，COMMIT 前后恢复方向明确|A35|
|私有 API 镜像引用漏指南|指南与 CBROWSER_API_TEST_IMAGE 实际消费者纳入替换范围，先打通统一镜像交付再删除旧入口|A31|
|R13 行号不支持结论|补 state.py:14-16 调用与 common.py:34-49 对象校验证据|R13|
|any 范围低估|当前 adapter 14 处 any 列清并按整个实际接口边界验收|A23|
|全局回焦重取遗漏|补 staleTime/refetchOnWindowFocus 与全 Profile 活跃查询组合；不再从 SSE 单键失效推断无全局重取|R7|
|退出 health 反证错位|running health 无法覆盖 exited/dead/not_found；撤回“所有正常退出”归约，针对报告原路径修复|A8|
|稻草人措辞|R2 分清命令/状态幂等；R4 分清通知与崩溃；R5 保留冷启动可用性问题；A26 删除自设的凭据泄漏靶子|R2、R4、R5、A26|
|PCM 编码/重编码术语|encodedAudio 复用不编码，PCM→Opus 是对应原始音频编码；另开编码仍有新增成本|W9、A41、R18|
|Windows fallback 摘要过宽|Ok(false) 才转 Unicode；进入投递后返回 Err 的超时和其它错误都经 ? 传播，不能统称非超时失败均回退|W4/W5、A39|
|W10 证据越界|仅归因参数集/NAL 转换，全链封装结合 W7–W9|W10|
|框架证据单薄|追加固定提交 apps/web/package.json，结论限定所核对 web 应用入口/构建，不覆盖整个 monorepo|W12|

未新增生产代码、未跑故障注入/录制/输入性能实验，不将这些条件方案写成已验证能力。原 73 条 finding 重新按当前根层报告定位行号，finding ID 和源文件保持不变；R1→A42 的改判不改变原 finding 总量。

## 本轮校验

- 原审阅 73 条具名 finding 仍穷尽映射且不重复计数；新增 4 项属于外部补充，来源见 W/C/P 证据目录，各决策编号唯一。
- Markdown 格式检查、合并优先级取最高校验通过；七项选择已全部回填，无待决定项；原 D1–D7 与当前编号映射完整。
- 纯函数探针复现 R15：`--tid t042; next_command` 被解析为 `t042;`；本地 SDK 类层级验证确认 `ReadTimeout` 不属于 `DockerException`。
- 已核对关键调用、路由装配、协议模型/导出入口、容器清理与端口恢复、网络规则、前端状态与测试辅助函数。未核验的历史链接数量与外部上游修复版本已明确保留为未知。
- 原报告及用户提供的外部方案摘要均按已核对源码限定结论；关键更正包括 Windows 注入不可直接移植、当前实际管线非 GStreamer、Stream 无下载挂载、免重编码不等于零 CPU、现状没有顶层 Context 高频统计。未做真实输入/录制/性能实验，不标 PASS。

## 审批状态

- 当前：原选择已全部回填；用户要求的 Weblink 补充评估已写入 A39/A40/A41、R17/R18，全文 42 项采纳、17 项不采纳、0 项待决定；本轮复核已修订，等待用户审阅更新后的整份文档。选择确认不等于审批，不提交 review 目录，不实施采纳项。
- 审批归档与采纳项实施分开确认。
