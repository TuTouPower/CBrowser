# bundle_local_tests_unit_fixtures

## responsibilities

- 覆盖后端各模块逻辑的单元测试（API、Auth、Domain、Services、Supervisor、Gateway、Stream Agent 等）
- 前端 Vitest 单元测试与设计系统 Token 自动化检查测试
- 维护测试夹具（fixtures），包括 FakeDockerAdapter、DockerDoubles、测试证书与模拟数据

## interfaces

- pytest tests/unit
- npm test --prefix src/frontend

## dependencies

- pytest
- pytest-asyncio
- pytest-xdist
- vitest
- @testing-library/react
- jsonschema

## flows

- 后端单元测试流：轻量内存 SQLite 隔离 -> 模拟 Docker 适配器 -> 验证边界行为与异常分支
- 前端单元测试流：挂载测试上下文 -> 验证组件交互与状态机迁移

## constraints

- 禁止在单元测试中调用真实 Docker 守护进程
- 依赖版本与 Schema 必须实施自动化比对锁定

## decisions

- 单测全面使用 Fake 双重实体隔离宿主环境
- 协议 Schema 导出作为单测断言对象

## evidence

- tests/fixtures/docker_doubles.py:29-43
- tests/unit/test_supervisor_schema.py:32-50
- tests/unit/test_stream_protocol_schema.py:40-46
- tests/unit/test_baseline_runtime_regressions.py:70

## uncertainties

## Findings

- [High][95] tests/fixtures/docker_doubles.py:29-43 — 共享 Docker 测试双重实体 FakeContainers.get 忽略容器名参数，易造成假绿测试

    - ID: f_tests_fake_containers_ignore_name; verification: static
    - Evidence: FakeContainers.get(self, \_name: str) -> FakeContainer 完全忽略 \_name 参数，只要 self.container 存在即恒定返回该容器对象
    - Impact: 生产代码因拼写错误传入错误或不存在的容器名时，测试依然返回有效容器而不抛出 NotFound，掩盖容器定位缺陷
    - Fix: 将 FakeContainers 改造为基于容器名称字典映射 dict[str, FakeContainer]，未命中时抛出 NotFound 异常

- [High][95] tests/unit/test_supervisor_schema.py:32-50; test_stream_protocol_schema.py:40-46 — 协议 Schema 一致性测试采用硬编码白名单比对，形成契约漏检盲区

    - ID: f_tests_schema_assert_hardcoded; verification: static
    - Evidence: test_supervisor_schema.py:32 硬编码比对 14 个消息名，未对比生产代码 protocol.py 中声明的完整 BaseModel 集合; 生产代码新增消息而导出脚本遗漏时，单测依然 100% 通过
    - Impact: 形成契约一致性虚假安全感，无法守卫协议导出脚本的完整性
    - Fix: 在单测中引入反射或内省机制，动态遍历协议源码文件中所有顶级消息类，断言其必须 100% 存在于 Schema messages 中

- [Medium][90] src/frontend/package.json:21; scripts/run_gates.sh:212-217 — 前端 OpenAPI 生成类型缺乏自动化漂移守卫

    - ID: f_tests_frontend_api_codegen_ungated; verification: static
    - Evidence: package.json 中的 test 命令以及 run_gates.sh 均未执行 npm run generate:api 并检查 git diff
    - Impact: 后端接口调整后若开发者遗漏手动执行 generate:api，前端签入的类型定义与后端 OpenAPI 契约发生静默漂移
    - Fix: 在前端测试或门禁脚本中增加 npm run generate:api && git diff --exit-code 检查步

- [Low][85] tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile:1-19 — 存在废弃且版本冲突的历史测试镜像 Dockerfile 夹具

    - ID: f_tests_abandoned_api_dockerfile; verification: static
    - Evidence: tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile 残留在仓库中，硬编码旧版依赖且以 root 运行，仅有一处单测做文本断言
    - Impact: 混淆代码审计，且维持了死代码夹具的维护成本
    - Fix: 清理该历史 Dockerfile 夹具并同步移除单测中的对应文本断言

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "agent_tests_unit_fixtures"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "agent_tests_unit_fixtures"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "agent_tests_unit_fixtures"
  },
  "performance": {
    "status": "completed",
    "reviewer": "agent_tests_unit_fixtures"
  },
  "design": {
    "status": "completed",
    "reviewer": "agent_tests_unit_fixtures"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "agent_tests_unit_fixtures"
  },
  "tests": {
    "status": "completed",
    "reviewer": "agent_tests_unit_fixtures"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "agent_tests_unit_fixtures"
  }
}
```

## files_reviewed

```json
[
  "tests/fixtures/api_auth.py",
  "tests/fixtures/automation_probe/__init__.py",
  "tests/fixtures/automation_probe/harness.py",
  "tests/fixtures/automation_probe/probe_client.py",
  "tests/fixtures/automation_probe/run_levels.py",
  "tests/fixtures/docker_doubles.py",
  "tests/fixtures/e2e_env.py",
  "tests/fixtures/frontend_app_probe/harness.py",
  "tests/fixtures/frontend_probe/__init__.py",
  "tests/fixtures/frontend_probe/adapter_probe.py",
  "tests/fixtures/frontend_probe/harness.py",
  "tests/fixtures/frontend_probe/host_builder.py",
  "tests/fixtures/frontend_probe/host_entry.tsx",
  "tests/fixtures/gateway_probe/__init__.py",
  "tests/fixtures/gateway_probe/browser_oracle.py",
  "tests/fixtures/gateway_probe/evidence.py",
  "tests/fixtures/gateway_probe/selkies_assets.py",
  "tests/fixtures/gateway_probe/topology.py",
  "tests/fixtures/runtime_probe/audio_analyzer.py",
  "tests/fixtures/runtime_probe/test_mitshm.c",
  "tests/fixtures/stream_probe/clipboard_oracle.py",
  "tests/fixtures/stream_probe/media_page.html",
  "tests/fixtures/stream_probe/web_lock_shim.js",
  "tests/fixtures/stream_probe/x11_keymap_probe.py",
  "tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile",
  "tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile.dockerignore",
  "tests/fixtures/supervisor_recovery_probe/gateway_service.py",
  "tests/fixtures/supervisor_recovery_probe/offline_fixture.py",
  "tests/fixtures/supervisor_resource_probe/cpu_burner.py",
  "tests/fixtures/supervisor_resource_probe/stream_monitor.py",
  "tests/fixtures/wait.py",
  "tests/unit/__init__.py",
  "tests/unit/conftest.py",
  "tests/unit/review_privacy_allowlist.txt",
  "tests/unit/test_agent_executor_cli.py",
  "tests/unit/test_agent_executor_control.py",
  "tests/unit/test_agent_executor_dialogs.py",
  "tests/unit/test_agent_executor_ledger.py",
  "tests/unit/test_agent_executor_refs.py",
  "tests/unit/test_agent_executor_state.py",
  "tests/unit/test_api_models_and_sse.py",
  "tests/unit/test_api_runtime_coordinator.py",
  "tests/unit/test_api_search_defaults.py",
  "tests/unit/test_artifact_service.py",
  "tests/unit/test_auth_client_ip.py",
  "tests/unit/test_auth_models.py",
  "tests/unit/test_auth_service.py",
  "tests/unit/test_automation_cdp.py",
  "tests/unit/test_automation_probe_harness.py",
  "tests/unit/test_baseline_fixture_regressions.py",
  "tests/unit/test_baseline_runtime_regressions.py",
  "tests/unit/test_browser_entrypoint.py",
  "tests/unit/test_browser_readiness_fence.py",
  "tests/unit/test_control_error_redaction.py",
  "tests/unit/test_control_migration.py",
  "tests/unit/test_control_service.py",
  "tests/unit/test_coordinator_close_flag.py",
  "tests/unit/test_dialog_attendant.py",
  "tests/unit/test_docker_build_contexts.py",
  "tests/unit/test_docker_doubles_contract.py",
  "tests/unit/test_docker_offload.py",
  "tests/unit/test_domain_and_repository.py",
  "tests/unit/test_download_reconciler.py",
  "tests/unit/test_evidence_redaction.py",
  "tests/unit/test_exit_reason_allowlist.py",
  "tests/unit/test_font_sets.py",
  "tests/unit/test_font_sets_api.py",
  "tests/unit/test_fontconfig.py",
  "tests/unit/test_frontend_build_freshness.py",
  "tests/unit/test_gateway_config.py",
  "tests/unit/test_gateway_disconnect_targets.py",
  "tests/unit/test_gateway_endpoint.py",
  "tests/unit/test_gateway_registry.py",
  "tests/unit/test_gateway_takeover_pump.py",
  "tests/unit/test_launch_args.py",
  "tests/unit/test_network_config.py",
  "tests/unit/test_network_policy.py",
  "tests/unit/test_network_policy_failure.py",
  "tests/unit/test_network_policy_input_safety.py",
  "tests/unit/test_network_repository.py",
  "tests/unit/test_network_router.py",
  "tests/unit/test_network_service.py",
  "tests/unit/test_preview.py",
  "tests/unit/test_preview_repository.py",
  "tests/unit/test_preview_router.py",
  "tests/unit/test_profile_copy_reset.py",
  "tests/unit/test_profile_query_loading.py",
  "tests/unit/test_recovery_authority.py",
  "tests/unit/test_recovery_shutdown_safety.py",
  "tests/unit/test_refactor_behavior_equivalence.py",
  "tests/unit/test_repo_hygiene.py",
  "tests/unit/test_repository_idempotency.py",
  "tests/unit/test_resource_fault_isolation.py",
  "tests/unit/test_runtime_agent.py",
  "tests/unit/test_runtime_agent_faults.py",
  "tests/unit/test_runtime_agent_preview.py",
  "tests/unit/test_runtime_agent_protocol_export.py",
  "tests/unit/test_runtime_coordinator_background_tasks.py",
  "tests/unit/test_runtime_coordinator_error_responses.py",
  "tests/unit/test_runtime_coordinator_error_settle.py",
  "tests/unit/test_runtime_coordinator_stop_paths.py",
  "tests/unit/test_runtime_event_broadcaster_epoch.py",
  "tests/unit/test_runtime_event_policy.py",
  "tests/unit/test_runtime_image_hygiene.py",
  "tests/unit/test_runtime_instance_storage.py",
  "tests/unit/test_runtime_persistence_guards.py",
  "tests/unit/test_runtime_profile_defaults.py",
  "tests/unit/test_runtime_protocol.py",
  "tests/unit/test_runtime_sse_snapshot_handoff.py",
  "tests/unit/test_secret_file_permissions.py",
  "tests/unit/test_selkies_file_transfers.py",
  "tests/unit/test_stream_agent_lifecycle.py",
  "tests/unit/test_stream_agent_protocol_v2.py",
  "tests/unit/test_stream_binding_guards.py",
  "tests/unit/test_stream_capture_policy.py",
  "tests/unit/test_stream_clipboard_policy.py",
  "tests/unit/test_stream_display_config.py",
  "tests/unit/test_stream_ice_config.py",
  "tests/unit/test_stream_keymap_abi.py",
  "tests/unit/test_stream_protocol_schema.py",
  "tests/unit/test_stream_resume.py",
  "tests/unit/test_stream_runtime.py",
  "tests/unit/test_stream_selkies_tokens.py",
  "tests/unit/test_stream_takeover_chain.py",
  "tests/unit/test_stream_takeover_classifier.py",
  "tests/unit/test_stream_takeover_report.py",
  "tests/unit/test_stream_transport_hardening.py",
  "tests/unit/test_stream_tunnel_budgets.py",
  "tests/unit/test_supervisor_adapter_paths.py",
  "tests/unit/test_supervisor_agent_credentials.py",
  "tests/unit/test_supervisor_cache_generations.py",
  "tests/unit/test_supervisor_control_auth.py",
  "tests/unit/test_supervisor_control_conflicts.py",
  "tests/unit/test_supervisor_coordinator_lock.py",
  "tests/unit/test_supervisor_core.py",
  "tests/unit/test_supervisor_core_network.py",
  "tests/unit/test_supervisor_display_config.py",
  "tests/unit/test_supervisor_docker_boundaries.py",
  "tests/unit/test_supervisor_event_cursor.py",
  "tests/unit/test_supervisor_event_delivery.py",
  "tests/unit/test_supervisor_file_permissions.py",
  "tests/unit/test_supervisor_file_storage.py",
  "tests/unit/test_supervisor_infrastructure_config.py",
  "tests/unit/test_supervisor_metrics.py",
  "tests/unit/test_supervisor_network_endpoints.py",
  "tests/unit/test_supervisor_normal_exit_observation.py",
  "tests/unit/test_supervisor_operation_journal.py",
  "tests/unit/test_supervisor_port_recovery.py",
  "tests/unit/test_supervisor_preview_policy.py",
  "tests/unit/test_supervisor_profile_path_ownership.py",
  "tests/unit/test_supervisor_reconcile_fences.py",
  "tests/unit/test_supervisor_recovery.py",
  "tests/unit/test_supervisor_recovery_coordinator.py",
  "tests/unit/test_supervisor_resource_aggregation.py",
  "tests/unit/test_supervisor_resource_policy.py",
  "tests/unit/test_supervisor_schema.py",
  "tests/unit/test_supervisor_search_defaults_core.py",
  "tests/unit/test_supervisor_search_defaults_routes.py",
  "tests/unit/test_supervisor_selkies_token_instances.py",
  "tests/unit/test_supervisor_selkies_token_isolation.py",
  "tests/unit/test_supervisor_selkies_tokens.py",
  "tests/unit/test_supervisor_start_conflicts.py",
  "tests/unit/test_supervisor_startup_recovery.py",
  "tests/unit/test_supervisor_stop_fence.py",
  "tests/unit/test_supervisor_stop_teardown.py",
  "tests/unit/test_supervisor_unprotected_sandbox.py",
  "tests/unit/test_t026_address_pool.py",
  "tests/unit/test_t026_control_client.py",
  "tests/unit/test_t026_control_endpoints.py",
  "tests/unit/test_t026_media_network_adapter.py",
  "tests/unit/test_t026_network_policy_verify.py",
  "tests/unit/test_t026_runner_network_events.py",
  "tests/unit/test_t026_supervisor_convergence.py",
  "tests/unit/test_t027_release_controller.py",
  "tests/unit/test_t028_image_identity.py",
  "tests/unit/test_t028_run_gates_evidence.py",
  "tests/unit/test_t034_dependency_lock.py",
  "tests/unit/test_t034_runtime_paths.py",
  "tests/unit/test_t035_openapi_contract.py",
  "tests/unit/test_t035_profile_domain.py",
  "tests/unit/test_t035_proxy_runtime.py",
  "tests/unit/test_t041_font_hygiene.py",
  "tests/unit/test_t041_font_runtime.py",
  "tests/unit/test_t043_selkies_pin.py",
  "tests/unit/test_t044_e2e_prerequisites.py",
  "tests/unit/test_t044_gate_contract.py",
  "tests/unit/test_t044_merge_junit.py",
  "tests/unit/test_t044_selkies_asset_probe.py",
  "tests/unit/test_t044_status_constants.py",
  "tests/unit/test_t044_verify_image_packages.py",
  "tests/unit/test_t045_e2e_host_port_allocation.py",
  "tests/unit/test_t045_e2e_shared_stack.py",
  "tests/unit/test_t045_gate_container_cleanup.py",
  "tests/unit/test_t045_run_gate_suite_exit5.py",
  "tests/unit/test_t045_selkies_wheel_cache.py",
  "tests/unit/test_tunnel_agent_wiring.py",
  "tests/unit/test_tunnel_filter.py",
  "tests/unit/test_tunnel_filter_autoattach.py",
  "tests/unit/test_tunnel_registry.py",
  "tests/unit/test_udp_mux_bounds.py",
  "tests/unit/test_vendor_selkies_security.py"
]
```
