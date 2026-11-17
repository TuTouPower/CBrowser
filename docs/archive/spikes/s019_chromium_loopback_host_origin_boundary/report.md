# Spike report

## 问题

锁定引擎（CloakBrowser/Chromium）的 CDP loopback 端点在恶意页面可触达的各条路径上，到底是「不可达」还是「可达但被拒」，须分别记录：

- 路径 1：用户外部 Chrome 中的恶意页面 → 宿主机/网络直达 CDP；
- 路径 2：沙箱 Profile 浏览器内的恶意页面 → 同浏览器自身 CDP（127.0.0.1）；
- 路径 3：DNS rebinding 形态——把外部域名解析到目标地址后访问 CDP HTTP 端点或经认证自动化入口；
- 对照：合法认证自动化通道（API 自动化入口 → Supervisor → Agent UDS → CDP）不得受影响。

## 成功判据

- 每条路径给出不可达/被拒的判定与代码或配置级证据；
- 引擎进程内的拒绝行为（Host/Origin 校验）由 real_engine 负向测试在真实引擎上复验，云端无 Docker 时该项明确顺延并登记，不冒充已验。

## 尝试

- 代码/配置走读（云端可验部分）：
    - 浏览器启动参数：`src/backend/cbrowser/runtime_agent/runner.py` 固定 `--remote-debugging-port=0`（内核随机临时端口）与 `--remote-debugging-address=127.0.0.1`；全仓 `src/` 无 `--remote-allow-origins`（grep 零命中），即引擎保持默认 Origin 允许名单为空。
    - 端口发布面：Browser 容器对外仅发布媒体 UDP mux 端口（`docs/blueprint/architecture.md` §6 端口矩阵：CDP 仅监听回环、禁止外部网络直达）；CDP 端口不出现在任何 compose/容器 PortBindings 发布中，调试端口号只存在于容器内 runner 元数据，不进入任何页面可读状态或 API 响应。
    - 唯一外部 CDP 入口：`src/backend/cbrowser/api/v1/automation_router.py` 的 `/api/v1/automation/profiles/{profile_id}/cdp`，须 automation token 鉴权（`AuthService.authorize_automation`）＋ t031 控制权 claim/代次围栏；再经 Supervisor `cdp_proxy`（`src/backend/cbrowser/supervisor/control_server.py`）的 supervisor token 与 `X-CBrowser-Control-Generation` 围栏校验后才代理到 Agent UDS。
    - viewer 侧泄漏面：普通 viewer 可见的 Profile/runtime 响应不含 cdp 字段；`cdp_ws_path` 仅由要求管理会话的 `GET /api/v1/profiles/{profile_id}/automation` 返回（task.md 非范围确认的管理 UI 现行功能）。
- 引擎内建防线（待真实引擎复验）：Chromium DevTools 默认拒绝带非允许 Origin 的页面发起的 WebSocket 连接（无 `--remote-allow-origins` 即全部页面 Origin 被拒）；DevTools HTTP 端点对非 loopback Host 头有 DNS rebinding 校验。此二项为本 spike 的引擎级复验对象，本轮云端无 Docker/引擎，不冒充已实测。

## 证据

- 路径 1 判定为**不可达**：CDP 监听在 Browser 容器网络命名空间的回环上，端口未发布到宿主机或任何外部网络；外部页面连 TCP 都建不起来，与 Host/Origin 校验无关。
- 路径 2 判定为**端口不可知＋引擎默认拒绝（待复验）**：同容器内的页面理论上与 CDP 同回环，但调试端口为内核随机分配且不经任何页面可达通道披露；即便猜中端口，页面发起的 CDP WebSocket 携 Origin 头，引擎默认允许名单为空将拒绝；HTTP 发现端点另有 Host 校验。此项的「拒绝」证据须由 real_engine 负向测试在锁定引擎上产生（见结论的顺延安排）。
- 路径 3 判定为**不可达/被拒分开记录**：对 CDP 本体同路径 1（名字解析到宿主机也无监听）；对经认证自动化入口，rebinding 只改变名字解析，入口要求 automation token 与控制权 claim，无凭据恒拒（API 集成测试覆盖），名字不构成凭据。
- 合法通道不受影响：本 task 不改 automation token 鉴权、控制权围栏与 UDS 代理链；既有 `tests/integration/test_automation_cdp_flow.py` 等套件回归为准。

## 结论

CDP 负向边界的部署层结论已坐实：外部网络对 CDP 本体不可达（未发布＋回环监听＋临时端口不披露），唯一入口为双重凭据把守的认证自动化通道；普通 viewer 配置/响应不泄漏可用 CDP 凭据或 endpoint。引擎进程内的 Host/Origin 拒绝行为按 Chromium 默认语义预期成立，但按本 spike 判据必须在锁定引擎上实测留证：本 task 新增真实引擎负向测试（恶意 Origin 的 WS 连接、伪造 Host 的 HTTP 发现请求、合法回环 Host/Origin 对照），合法认证自动化通道继续由既有 automation E2E 对照；云端无 Docker 按门禁口径跳过，合入后本地实跑，登记为 p094（与 AC-001/AC-002/AC-004/AC-006 的真实拓扑补验同条）。

## 是否采纳

- 决定：是
- 理由：分层结论成立——部署层不可达已由配置坐实，引擎层拒绝以专项负向测试留证，不以文档推断代替实测。
- 后续 task：t064
- 无需后续理由：不适用

## 关联 findings

- findings.py 在本基线被既存编号重复阻断（`docs/findings/` 内 d037、d038 各存在两条不同条目，`findings.py new` 扫描时拒绝分配新号；该重复非本 task 引入，与 t062 执行时所遇为同一基线缺陷）。结论以本报告与 task.md 未知契约清单回填为准，编号修复后可补抽 dNNN。
