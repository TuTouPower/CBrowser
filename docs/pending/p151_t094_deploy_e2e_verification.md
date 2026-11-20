---
pid: "p151"
slug: "t094_deploy_e2e_verification"
status: "todo"
---
# p151 t094 AC-008/009 真实 Docker/Chrome 拓扑验证（轻量探测 + Browser 防泄露两链）

- 来源：t094 实施期 `[deploy]` AC-008/AC-009 本机无法实测（镜像 ID 缺失），按项目既定 USER_WAIVED 口径登记。
- 内容：
    1. AC-008 探针链：在本机隔离真实 Docker/Chrome 拓扑执行 `tests/e2e/test_supervisor_namespace_policy_e2e.py` 与三协议轻量探测用例，验证 http/https/socks5 出口展示、失败无直连回退、零 helper/网络/策略 Docker 资源事件与冻结后的延迟口径；须设置全部 `REQUIRED_E2E_ENV` 不可变镜像 ID（`CBROWSER_RUNTIME_TEST_IMAGE`/`CBROWSER_STREAM_TEST_IMAGE`/`CBROWSER_GATEWAY_IMAGE`/`CBROWSER_SUPERVISOR_TEST_IMAGE`/`CBROWSER_API_TEST_IMAGE`/`CBROWSER_CADDY_TEST_IMAGE`/`CBROWSER_NETWORK_POLICY_IMAGE`/`CBROWSER_INVALID_POLICY_TEST_IMAGE` 等）及 GeoIP/引擎缓存后运行 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`，留 Junit/网络/Docker 事件证据。
    2. AC-009 Browser 防泄露链：真实 Chrome 经监听代理出口（`tests/e2e/test_proxy_library_e2e.py`），覆盖 IPv4/IPv6/DNS、私有地址阻断、失败封闭与公网出口对照，断言零直连/STUN/外部 DNS 旁路流量；确认配置代理的 Browser Profile 仍受 ADR 038 双栈 `OUTPUT DROP` 约束。
    3. 云端已完成的验证：契约 388、单元 2400、集成 210、前端 726 全绿；轻量探测与作业编排由单元/集成测试覆盖，但真实镜像与 Chrome 端到端未执行，不得以 mock/skip/历史结果代替。
- 处理：未开
