# bundle_followup_q_evolution_03

## Summary

精查证实并收窄分布：私有内部耦合横跨 6 个测试单元中的 5 个、涉事文件 ≥17 个，质心在 supervisor coordinator，v2 runtime_agent 与 API 本体基本干净；『每一步都触发』应收窄为 supervisor/gateway/stream 步骤。

## Findings

No findings.

## evidence

```json
[
  "结论：耦合不是集中在 coordinator 一个模块，而是横跨 5/6 个测试单元、3 个测试层（unit/e2e/integration）、至少 4 个生产面；但分布不均——supervisor/coordinator 与 stream 最密，v2 runtime_agent 与 v2 API 本体基本干净。故问题中『遍布』一角成立、『仅 coordinator』的反证条件不成立；但『切换链每一步都会触发』需收窄为『凡触碰 supervisor/gateway/stream 的切换步都会触发，runtime/api 步基本不会』。",
  "按测试单元分布（严格口径：断言/读写 _ 前缀成员、私有方法、name-mangled 属性）：tests_unit_supervisor_runtime 1 条（f_04, Medium）；tests_unit_stream_api 1 条（f_06, Low）；backend_tests 1 条（f_07, Low）；tests_e2e_supervisor 2 条（f_06, Medium；f_11, Low）；tests_e2e_stream_frontend 0 条（该单元的问题是 dist 新鲜度与 web_lock_shim 分叉，属不同缺陷类）；tests_integration_fixtures 2 条（f_05, Medium；f_13, Low）。严格集共 7 条 finding，分布在 5 个单元。",
  "按生产模块分布——Supervisor/RecoveryCoordinator/DockerAdapter（最密，4 条 finding 触及）：f_tests_unit_supervisor_runtime_04（coordinator._running、_reconcile_profile_loop、_active_tasks、_publish_tasks、_in_flight_tasks、_cleanup_failures、_cleanup_cooldown_until、_reported_dead_instances；core._sessions、_query_agent_health；另含按 tick() 内部调用顺序编排 api.get side_effect）；f_tests_e2e_supervisor_06（DockerAdapter._prepare_policy_gate、_install_network_policy）；f_tests_e2e_supervisor_11（core._get_profile_lock、coordinator._in_flight_tasks、_reported_dead_instances）；f_tests_integration_fixtures_05 的 supervisor 部分（core.ports._allocated、core._sessions 注入、recovery._in_flight_tasks、coordinator._load_profile_config、SimpleNamespace 假 core）。",
  "按生产模块分布——Stream Agent/Gateway 轮换（2 条）：f_tests_unit_stream_api_06（agent._is_paused、_supervisor_fps_cap、_loop_task/_motion_task、policy._supervisor_fps_cap、conn_id_to_sdk_peer_id；test_gateway_rotation_guards 直接播种 coordinator._pending_offers/_pending_answers）。即 gateway 侧确有耦合，不止 supervisor。",
  "按生产模块分布——第三方 Selkies 内部（integration 探针，2 条）：f_tests_integration_fixtures_05 与 f_13——transport._RTCIceTransport__monitor_task、pc._RTCPeerConnection__iceTransports 等 name-mangled 属性，及 selkies.input_handler._X11ClipboardMonitor、_XTestKeyboard 等下划线类；这是对钉版库私有 API 的耦合，Selkies 升级即触发，与生产重构无关但同属爆炸半径。",
  "按生产模块分布——legacy 后端（1 条 + 1 邻接）：f_backend_tests_07（vnc._allocated 直接增删与断言、browser_mgr._held/_launching 成员断言）；邻接项 f_backend_tests_01（High）以普通赋值替换单例 browser_mgr.launch/stop 公开方法且不还原——属『替换 SUT 自身方法』一族（与 f_tests_unit_supervisor_runtime_04 中替换 coordinator 方法同型），但作用于公开方法、后果是跨测试污染，未计入严格集。",
  "v2 runtime_agent 与 v2 API 本体基本干净：无任何 finding 指认 runtime_agent 私有成员耦合；与 runtime/adapters 最接近的只有 f_tests_unit_stream_api_06 中 test_profile_copy_reset 反复取用 repo._session_maker 建 ArtifactRepository（一处）。API 侧仅 integration 层有 app.state 状态注入（f_tests_integration_fixtures_05：改 artifact_service.max_artifact_bytes、经 coordinator.broadcaster 注入事件、读 site._server.sockets），属绕过公开面的状态操纵，与下划线成员耦合邻接但不同型。",
  "抽查核实（4 处，与 local finding 逐字吻合）：tests/unit/test_runtime_coordinator_stop_paths.py:260,304,346 `coordinator._running = True` 并直调 `_reconcile_profile_loop`；tests/unit/test_stream_capture_policy.py:116,132 断言 `agent._is_paused`、:222-224 断言 `agent._supervisor_fps_cap == 5.0`；tests/e2e/test_supervisor_infrastructure_network_e2e.py:161,176 调用 `secured_adapter._prepare_policy_gate`/`_install_network_policy`；tests/fixtures/stream_probe/ice_restart_failure.py:68,90 读 `transport._RTCIceTransport__monitor_task`。",
  "涉及文件数（据各 finding 证据列举）：仅 coordinator/supervisor 相关即 ≥8 个测试文件（test_runtime_coordinator_stop_paths、test_api_runtime_coordinator、test_runtime_coordinator_background_tasks、test_supervisor_recovery_coordinator、test_recovery_authority、test_supervisor_startup_recovery、test_supervisor_startup_recovery_e2e、test_supervisor_infrastructure_network_e2e 等），加 stream 侧 ≥3 个、integration 探针 ≥6 个——远超反证条件所述『2–3 个文件』。"
]
```

## result

```json
"confirmed"
```

## limitations

```json
[
  "分布统计基于六个测试单元的 local finding 全文（标题+证据+影响）做关键词初筛后逐条人工分类；初筛另命中 8 条同词 finding（dist 新鲜度、finally 断言、端口 TOCTOU、sys.path 污染、CWD 路径、docstring 虚假覆盖、fixture 再实现、fixture 生命周期绕行），经读全文判定为不同缺陷类而剔除——其中 fixture 再实现（f_tests_integration_fixtures_01）是 f_global_evolution_03 的另一独立证据腿，不在本题口径内。",
  "未对全仓测试文件做穷举 grep 统计私有成员访问总数；文件数与分布以 local finding 的证据列举为准，另抽查 4 处源文件核实无误。个别未被任何 local finding 点名的零星私有访问可能存在，但不改变分布结论。",
  "本精查为静态阅读，未运行测试套件验证重构敏感性（如改名一个私有字段实际变红的用例数）。"
]
```
