# bundle_local_tests_integration_e2e

## responsibilities

- 验证跨服务、跨进程协作逻辑（API 与 Supervisor/Gateway 通信、SSE 广播、网络模式动态切换）
- 运行基于真实 Docker 拓扑与 Playwright 驱动的端到端系统测试（E2E）
- 自动化探针套件执行与验证

## interfaces

- pytest tests/integration
- CBROWSER_RUN_E2E=1 pytest tests/e2e
- scripts/run_automation_probe.sh

## dependencies

- Docker Daemon
- Playwright
- Google Chrome
- Xvfb / PulseAudio
- pytest-xdist

## flows

- 集成测试流：拉起轻量 SQLite 与 Mock 服务端点 -> 验证完整 HTTP/WS 协议交互
- E2E 测试流：GatewayTopologyHarness 拉起隔离容器组 -> Playwright 驱动 Chrome 访问 HTTPS -> 验证 WebRTC 画面像素与状态收敛 -> 按前缀标签强制清理容器

## constraints

- E2E 模式在 CBROWSER_E2E_REQUIRED=1 下强制 fail-closed，严禁隐式 skip
- 并发测试需通过 worker_resource_offsets 隔离端口与媒体子网

## decisions

- 容器清理强制校验 com.cbrowser.prefix 标签，防误伤宿主其他容器
- 画面验证采用 wait_iframe_pixel 像素采样比对验证真实远程画布

## evidence

- tests/integration/test_agent_executor_chain.py:343-695
- tests/fixtures/gateway_probe/topology.py:36-56
- tests/e2e/conftest.py:27,91
- tests/e2e/test_frontend_media_e2e.py:695-830
- tests/integration/test_network_apply_operations.py:39-60
- tests/e2e/test_frontend_build_wiring.py:1-164

## uncertainties

## Findings

- [High][95] tests/integration/test_agent_executor_chain.py:343; test_automation_probe_chain.py:320 — 集成测试套件中包含 18 个无条件 bare pytest.skip 的 GUI 强依赖测试，导致常规 CI 静默假绿

    - ID: f_tests_integration_bare_skips; verification: static
    - Evidence: test_agent_executor_chain.py 等文件在缺失 Chromium 或 Xvfb 时直接执行 pytest.skip，共 18 处; 常规 CI 环境运行 pytest tests/integration 时静默跳过但这部分核心执行器未能真正受到保护
    - Impact: 执行器核心链路在常规门禁中完全未运行，破坏逻辑时门禁依然全绿放行
    - Fix: 将强依赖真实 Chromium/Xvfb 的测试用例移至 tests/e2e/，并在 CBROWSER_E2E_REQUIRED=1 时实行严格 fail-closed

- [Medium][90] tests/fixtures/gateway_probe/topology.py:36-56 — find_free_port() 存在跨进程 TOCTOU 竞争与无效线程锁

    - ID: f_tests_find_free_port_toctou; verification: static
    - Evidence: find_free_port 绑定端口获取 port 后立即 close socket，到 Docker 实际 run 绑定端口之间存在时间差; \_host_port_lock 为进程内线程锁，在 pytest-xdist 多进程并发下完全失效
    - Impact: 高并发测试时偶发端口分配冲突，导致 Harness 容器拉起失败并引发测试 Flaky
    - Fix: 按 worker id 预分配独立的静态端口范围基地址，或让 Docker 自行分配随机端口（绑定宿主 0 端口）后回读

- [Medium][90] tests/e2e/conftest.py:27; test_stream_runtime_e2e.py:39 — E2E 测试强行硬编码 macOS 专属 Google Chrome 路径，导致 Linux CI 无法运行

    - ID: f_tests_e2e_hardcoded_macos_chrome; verification: static
    - Evidence: conftest.py:27 HOST_CHROME_PATH = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'); 在 Linux 机器上开启 E2E 验证时，即使安装了 google-chrome，预检门禁也必然因找不到 /Applications 路径而 fail-closed
    - Impact: 直接阻断 Linux 持续集成流水线与非 macOS 开发者运行 E2E 测试
    - Fix: 引入跨平台路径探测逻辑：优先读取 CBROWSER_CHROME_PATH，其次探测 shutil.which('google-chrome') 与 Linux 常见路径

- [Medium][85] tests/e2e/test_frontend_media_e2e.py:695-830 — E2E 核心媒体测试用例缺乏断言语句，存在假测试风险

    - ID: f_tests_frontend_media_vacuous_test; verification: static
    - Evidence: test_ac005_remote_tab_switch_is_visible_on_both_pages 全程执行像素等待和落盘，但函数内无任何一条 assert 语句
    - Impact: 测试用例未能对双页面间像素一致性与切换结果做显式断言校验，存在静默假通过隐患
    - Fix: 在测试末尾显式补充对 red_a, red_b, green_a, green_b 匹配结果的 assert 断言

- [Medium][85] tests/integration/test_network_apply_operations.py:39-60 — 集成测试全量 Mock 核心依赖服务，退化为假集成测试

    - ID: f_tests_network_apply_all_mocked; verification: static
    - Evidence: test_network_apply_operations.py 将核心通信对象 supervisor 整体 MagicMock 掉，仅验证 NetworkService 自身内部流转
    - Impact: 未验证真实的 HTTP RPC 调用、鉴权头透传与协议兼容性，将纯单元测试伪装为集成测试导致覆盖率虚高
    - Fix: 将该用例移至 tests/unit/，或在集成测试中拉起真实 MockSupervisorServer 验证完整网络栈

- [Low][80] tests/e2e/test_frontend_build_wiring.py:1-164 — 纯 Python 单元测试被错误放置于 tests/e2e/ 目录中

    - ID: f_tests_build_wiring_wrong_directory; verification: static
    - Evidence: test_frontend_build_wiring.py 全文仅测试 verify_frontend_dist.py 文件匹配逻辑，无需 Docker 与 Chrome，耗时小于 0.2s; 位于 tests/e2e/ 导致在常规门禁阶段完全被跳过
    - Impact: 构建验证逻辑单测未能在常规门禁阶段执行，且污染 E2E 目录结构
    - Fix: 将该文件移动至 tests/unit/ 目录下使其每次随单测自动执行

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "agent_tests_integration_e2e"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "agent_tests_integration_e2e"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "agent_tests_integration_e2e"
  },
  "performance": {
    "status": "completed",
    "reviewer": "agent_tests_integration_e2e"
  },
  "design": {
    "status": "completed",
    "reviewer": "agent_tests_integration_e2e"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "agent_tests_integration_e2e"
  },
  "tests": {
    "status": "completed",
    "reviewer": "agent_tests_integration_e2e"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "agent_tests_integration_e2e"
  }
}
```

## files_reviewed

```json
[
  "tests/e2e/conftest.py",
  "tests/e2e/test_artifact_delete_resume_e2e.py",
  "tests/e2e/test_artifact_download_chain_e2e.py",
  "tests/e2e/test_automation_compatibility_probe_e2e.py",
  "tests/e2e/test_browser_runtime_e2e.py",
  "tests/e2e/test_control_handoff_e2e.py",
  "tests/e2e/test_fingerprint_platform_e2e.py",
  "tests/e2e/test_frontend_adapter_build.py",
  "tests/e2e/test_frontend_app_auth_e2e.py",
  "tests/e2e/test_frontend_app_e2e.py",
  "tests/e2e/test_frontend_build_wiring.py",
  "tests/e2e/test_frontend_display_apply_e2e.py",
  "tests/e2e/test_frontend_media_e2e.py",
  "tests/e2e/test_frontend_session_e2e.py",
  "tests/e2e/test_frontend_session_vendor.py",
  "tests/e2e/test_gateway_ac001_auth_e2e.py",
  "tests/e2e/test_gateway_ac003_media_e2e.py",
  "tests/e2e/test_gateway_ac007_visibility_e2e.py",
  "tests/e2e/test_gateway_registration_budget_e2e.py",
  "tests/e2e/test_network_access_lan_e2e.py",
  "tests/e2e/test_profile_preview_e2e.py",
  "tests/e2e/test_proxy_library_e2e.py",
  "tests/e2e/test_runtime_coordinator_e2e.py",
  "tests/e2e/test_runtime_profile_defaults_e2e.py",
  "tests/e2e/test_search_defaults_retry_live_e2e.py",
  "tests/e2e/test_stream_runtime_e2e.py",
  "tests/e2e/test_stream_selkies_tokens_e2e.py",
  "tests/e2e/test_stream_x11_keymap_e2e.py",
  "tests/e2e/test_supervisor_browser_network_e2e.py",
  "tests/e2e/test_supervisor_cache_initialization_e2e.py",
  "tests/e2e/test_supervisor_container_graph_e2e.py",
  "tests/e2e/test_supervisor_core_e2e.py",
  "tests/e2e/test_supervisor_event_shutdown_e2e.py",
  "tests/e2e/test_supervisor_ipv6_policy_e2e.py",
  "tests/e2e/test_supervisor_namespace_policy_e2e.py",
  "tests/e2e/test_supervisor_network_ownership_e2e.py",
  "tests/e2e/test_supervisor_offline_recovery_e2e.py",
  "tests/e2e/test_supervisor_orphan_helpers_e2e.py",
  "tests/e2e/test_supervisor_policy_failure_e2e.py",
  "tests/e2e/test_supervisor_quota_chain_e2e.py",
  "tests/e2e/test_supervisor_reconciliation_e2e.py",
  "tests/e2e/test_supervisor_recovery_e2e.py",
  "tests/e2e/test_supervisor_resource_capacity_e2e.py",
  "tests/e2e/test_supervisor_resource_monitor_e2e.py",
  "tests/e2e/test_supervisor_resource_policy_e2e.py",
  "tests/e2e/test_supervisor_retry_e2e.py",
  "tests/e2e/test_supervisor_startup_recovery_e2e.py",
  "tests/e2e/test_x11_helper_permissions_e2e.py",
  "tests/integration/conftest.py",
  "tests/integration/test_ac007_origin_whitelist_sync.py",
  "tests/integration/test_agent_executor_chain.py",
  "tests/integration/test_api_search_defaults_routes.py",
  "tests/integration/test_api_sse_events.py",
  "tests/integration/test_artifacts_api.py",
  "tests/integration/test_auth_api.py",
  "tests/integration/test_automation_api.py",
  "tests/integration/test_automation_cdp_flow.py",
  "tests/integration/test_automation_probe_chain.py",
  "tests/integration/test_control_api.py",
  "tests/integration/test_control_attendant_chain.py",
  "tests/integration/test_control_http_clients.py",
  "tests/integration/test_control_supervisor_close.py",
  "tests/integration/test_font_sets_api.py",
  "tests/integration/test_gateway_control.py",
  "tests/integration/test_gateway_fixtures.py",
  "tests/integration/test_gateway_signaling.py",
  "tests/integration/test_internal_service_config.py",
  "tests/integration/test_network_apply_operations.py",
  "tests/integration/test_normal_exit_replay.py",
  "tests/integration/test_preview_clear_on_lifecycle.py",
  "tests/integration/test_preview_late_writes.py",
  "tests/integration/test_profile_copy_reset_api.py",
  "tests/integration/test_profile_launch_args_api.py",
  "tests/integration/test_profile_patch_semantics.py",
  "tests/integration/test_recovery_snapshot_failure.py",
  "tests/integration/test_runtime_coordinator_integration.py",
  "tests/integration/test_sse_epoch_integration.py",
  "tests/integration/test_supervisor_gateway_client.py",
  "tests/integration/test_supervisor_gateway_control_auth.py",
  "tests/integration/test_supervisor_manual_retry.py",
  "tests/integration/test_supervisor_observation_authority.py",
  "tests/integration/test_supervisor_rpc.py",
  "tests/integration/test_supervisor_start_capacity.py",
  "tests/integration/test_supervisor_status_truth.py",
  "tests/integration/test_t026_gateway_registration.py",
  "tests/integration/test_t026_transport_api.py",
  "tests/integration/test_t027_gateway_health.py",
  "tests/integration/test_t027_readiness_probe.py",
  "tests/integration/test_v2_api_subprocess.py"
]
```
