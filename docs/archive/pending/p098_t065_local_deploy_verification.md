# p098 t065 真实部署链本地补验：代理凭据隔离与认证转发

- 来源：t065 遗留（[deploy] AC-001～004 真实链，云端无 Docker/真实引擎，按口径顺延本地补验）
- 内容：在 Mac 真实部署拓扑（隔离真实 Docker/Chrome/引擎）下验收以下四项，云端实现已完成、云端可验部分已实证，真实链未冒充已验：
    1. AC-001 凭据全路径不可读：在运行中的 Browser 容器内（argv、/proc、环境、日志、全部可读挂载）确认代理凭据无处可读；凭据只存在于 secret 目录与转发器容器内。
    2. AC-002 三协议上游认证：同一代理分别以 HTTP、HTTPS（CONNECT）、SOCKS5 上游真实出站，转发器注入凭据后认证成功；上游认证失败（错密码/407）时失败封闭。
    3. AC-003 故障封闭：上游不可达、407、SOCKS5 认证失败、转发器容器退出时，Browser 无响应体、无直连源站尝试；转发器缺失/退出时 reconcile 只重建转发器（`_replace_proxy_forwarder_only`），Browser 不动。
    4. AC-004 性能：相同拓扑/目标/样本下，认证成功率不低于基线，报告首包延迟、407 往返与可观测协议差异；默认不接受超出测量噪声的退化，若无法满足须带证据请求用户批准后修订 AC。云端 smoke 测试（`test_first_byte_smoke_reports_latency_samples`）只做存活验证（5 次 loopback 取回成功并报告首包样本），不作基线对比证据；基线对比的测量与判定均在本项完成。
- 处理：c1df58a；resolution=obsolete；reason=用户裁决删除外置认证转发器（容器/镜像/编排/文档全删），Browser 直连上游代理且凭据由 Browser 直接使用；AC-001~004 的验收对象整体消失，四条 AC 全部失去对象，不再补验

## 裁决（2026-11-15）：转发器删除，本项 obsolete

用户裁决拆掉外置认证转发器：删除转发器容器、镜像及其创建/分组/标签/网络白名单/readiness/reconcile/stop/孤儿清理/资源计数全部代码与文档；Browser 改为直连上游代理，凭据由 Browser 直接使用（`--proxy-server=scheme://user:pass@host:port`，见 `docs/findings/d031_authenticated_socks5_supported.md` 与 ADR 037）。

本项 AC-001～004 的验收对象（外置转发器、「Browser 永不见凭据」、「转发器退出时 reconcile 只重建转发器」）在新架构下**整体不存在**，四条 AC 全部失去对象：
- AC-001「凭据只存在于 secret 目录与转发器容器内」→ 凭据本就由 Browser 使用，断言反转。
- AC-002「转发器注入凭据后认证成功」→ 无转发器，凭据由 Chromium 原生处理。
- AC-003「转发器缺失/退出时只重建转发器」→ 无转发器，`_replace_proxy_forwarder_only` 已删除。
- AC-004 性能基线已于上一轮按铁律砍除。

`credential_revision` 失败封闭、`proxy_credentials.json` 权限与 loopback→host-gateway 映射保留，由 `docs/specs/proxy_management.md` 与 `tests/unit/test_t035_proxy_runtime.py` 承载。本项按 `resolution=obsolete` 归档，不再补验；转发器设计待定状态解除。

## 开发铁律重判（2026-11-15，历史记录，已被上方裁决取代）

- AC-004「认证成功率不低于基线、首包延迟/407 往返对比」**无可比基线对象**（云端 smoke 只是 5 次 loopback 存活样本），且 spec 原文规定「若无法满足须带证据请求用户批准后修订 AC」—— 属过度设计，砍除，不再补验。
- AC-001（Browser 容器内凭据全路径不可读）、AC-002（HTTP / HTTPS CONNECT / SOCKS5 三协议上游认证 + 407 失败封闭）、AC-003（上游不可达/转发器退出时无响应体、无直连、reconcile 仅重建转发器）是**真实安全边界**，会产生新信息，值得做。
- 设施已具备：`<home>/kar/code/temp123/mihomo_proxy` 是 94 个 `mixed` 监听（21000–21093，同时兼容 HTTP 与 SOCKS5、支持 CONNECT）+ 88 个真实海外节点，容器 `mihomo-proxy` 常驻、`host.docker.internal` 可达。此前「需额外上游代理设施」的卡点不成立。
- 跑通条件：通过 API 建三类 proxy 指向该 mixed 端口 → 建 Profile 引用 → 启动真实 Browser → 验证 egress 与容器内无凭据；故障封闭用错端口/停转发器注入。407 认证失败需另起带认证的上游（mihomo 本身无认证）。
- 时间：2026-11-14T22:36:00+08:00

## 终局补验证据（gate5 / 真实部署栈，最终结论；取代下方 gate4 阶段性记录）

- gate5 `GATE_EXIT=0`：e2e 105/0、unit 2278/0、integration 209/0、image_packages 0。`ee94faf` 同步 t065 契约后 `test_browser_runtime_e2e.py::test_t035_proxy_outbound_and_cdp_browser_version`（夹具改写 `proxy_forwarder.json`：`scheme=http`、bare host、`port=18080`、`credential_revision` 等于 snapshot、权限 0644）与 `test_proxy_library_e2e.py::test_ac008_proxy_library_outbound_via_ui`（根因是 Supervisor 容器 env 缺 `CBROWSER_PROXY_FORWARDER_IMAGE`，`docker_adapter.py:2293` fail-closed → `restart_blocked`；`frontend_app_probe/harness.py` 补注入后 browser/proxy-forwarder/stream 容器均起、PROXY_GET 命中）单跑通过。
- 真实部署栈 `scripts/deploy.sh deploy` 成功，proxy-forwarder 镜像 `2ed32840` 纳入 release env；4 容器 healthy。
- 卡点：AC-001（运行中 Browser 容器内 argv/proc/env/日志/全部可读挂载确认凭据无处可读）、AC-002（HTTP / HTTPS CONNECT / SOCKS5 三协议上游认证成功 + 407/错密码失败封闭）、AC-003（上游不可达/转发器退出时 Browser 无响应体、无直连源站、reconcile 仅 `_replace_proxy_forwarder_only`）、AC-004（首包延迟/407 往返/认证成功率基线对比与噪声判定）需隔离部署栈 + 三种真实上游代理 + 性能基线测量，本批未构造；不冒充已验。

## 本地补验证据（gate4）

- 已验：`ee94faf` 同步 t065 契约后 `test_browser_runtime_e2e.py::test_t035_proxy_outbound_and_cdp_browser_version` 单跑通过（夹具改写 `proxy_forwarder.json`：`scheme=http`、bare host、`port=18080`、`credential_revision` 等于 snapshot、权限 0644；旧 `proxy_credentials.json` 已无人读）；`test_proxy_library_e2e.py::test_ac008_proxy_library_outbound_via_ui` 单跑通过（根因是 Supervisor 容器 env 缺 `CBROWSER_PROXY_FORWARDER_IMAGE`，`docker_adapter.py:2293` fail-closed → 4 次重试 `restart_blocked`；`frontend_app_probe/harness.py` 补注入后 browser/proxy-forwarder/stream 容器均起、PROXY_GET 命中）。gate4 `unit 2243/0`、`integration 208/0`、`image_packages=0` 含 t065 相关用例全绿。
- 卡点：AC-001（运行中 Browser 容器内 argv/proc/env/日志/全部可读挂载确认凭据无处可读）、AC-002（HTTP/HTTPS CONNECT/SOCKS5 三协议上游认证成功 + 407/错密码失败封闭）、AC-003（上游不可达/转发器退出时 Browser 无响应体、无直连源站、reconcile 仅 `_replace_proxy_forwarder_only`）、AC-004（首包延迟/407 往返/认证成功率基线对比与噪声判定）均需隔离部署栈与真实上游代理；本批未启动生产栈，未验。

## 主线 ae02d42 本地复核（2026-11-16）

- 口径：按「按现状做本地复核」；`resolution=obsolete` 用户裁决（删除外置认证转发器）属终局结论，本轮只核裁决是否仍成立，不重建已消失的验收对象、不跑上游代理链；基线 `main` @ `ae02d42`。
- 静态核对：全仓 `src/` / `scripts/` / `config/` 扫描 `_replace_proxy_forwarder_only`、`CBROWSER_PROXY_FORWARDER_IMAGE`、`proxy_forwarder` **零命中**（转发器容器 / 镜像 / 编排 / reconcile 分支确已删除）；`credential_revision` 失败封闭仍在（`supervisor/core.py:2439`、`shared/egress_plan.py:144-157` 等）；`tests/unit/test_t035_proxy_runtime.py` 存在。
- 定向实测：`p098_t035` → `33 passed / EXIT=0`；日志 `.scratch/p090_p098_reverify_20261116/logs/p098_t035.log`。
- 结论：AC-001~004 的验收对象在当前主线未复现，`obsolete` 裁定仍成立；不补验。
- 证据留存：gate5 / gate4 原始目录已缺失；汇总见 `docs/archive/verification/p090_p098_local_reverify_20261116.md`。
