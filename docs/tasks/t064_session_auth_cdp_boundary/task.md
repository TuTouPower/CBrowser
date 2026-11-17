# Task spec

## 背景

Caddy 当前只反代 API、Gateway 信令并托管本地静态前端，运行容器无 HTML/HTTP 反代。收缩为 viewer 握手去管理 Cookie 与 CDP loopback 负向边界；保留同源官方客户端及自动化页面表达式语义。

## 契约区

### 范围

- 仅对 /stream/{profileId}/signal 的 viewer 握手进行控制面授权，Gateway 不接收 cbrowser_session；Caddy/API 建立可信授权上下文，Gateway 验证可信来源、Profile 绑定、Origin、授权时效/撤销与 runtime/Agent 就绪。
- 内部解析端点在外部 listener 显式拒绝；伪造转发头在边缘删除，Gateway 内网绕过也不能伪造授权；/stream/agent/register 继续走独立 Agent 凭据，不套 viewer cookie 授权。
- CDP 保留唯一认证自动化入口，验证 Browser loopback 的 Host/Origin/DNS rebinding 防护；普通 viewer 配置不泄漏可用 CDP 凭据/endpoint。

### 非范围

- 删除原“容器 HTTP 响应 origin/CSP/Service Worker 隔离”假前提；不改变 /selkies/ 同源 iframe、统计函数跨 frame 访问或 audio postMessage origin。
- 不强制 wait_for/extract 切 isolated world；snapshot 保持 DOM/AX 协议读取，用户表达式保留页面主世界访问。
- 管理 UI Automation 页面经权限校验展示 cdp_ws_path 属现行功能，不按普通 viewer 泄漏处理；不将所有 /stream/\* 套 forward_auth。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] [deploy] AC-001：未授权/过期/撤销/跨 Profile viewer 握手被拒；合法握手可用且 Gateway 收到的请求不含 cbrowser_session，管理登录 cookie 保持现有 Path=/ 语义，不把管理 cookie 改成路径 cookie。
- [x] [deploy] AC-002：外部 listener 不能访问新授权解析端点；伪造授权头、直连 Gateway 绕边缘、非法 Origin 均不能越权；Agent register 使用其独立认证仍正常。
- [x] [deploy] AC-004：普通 viewer 页面/信令/错误不提供可用 CDP 连接凭据；认证 Automation 页与自动化通道保留，非法 Host/Origin 和实际可触达的 DNS rebinding 请求被拒，合法 UDS/自动化连接不受影响。
- [x] AC-005：snapshot 的 DOM/AX 读取与 wait_for/extract 主世界表达式行为保持，目标页面 CSP 不被放宽；同源 iframe 统计与音频控制正常。
- [x] [deploy] AC-006：真实 Caddy/Chrome 链中登录、viewer 首帧、重连、退出撤销和认证自动化均通过，WebRTC 媒体仍走现有本机 UDP。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-002：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-004：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-005：可自动测试，触达生产函数或实际工具入口。
- AC-006：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。

## 上下文区

- 来源：2026-11-13 审阅复核：p075、p084；network_config.py 仅 /api/*、/stream/* 反代及本地 file_server；gateway 当前直接读 cbrowser_session 并回 API authorize_viewer；/stream/agent/register 为独立路由。session.py 的 snapshot 用 DOM/AX，wait_for/extract 用 Runtime.evaluate。

### 有意不测

- 非范围中的新增产品功能不作为本 task 验收；已声明 AC 不豁免。

### 测试策略

- 真实 Caddy/Gateway/API 验证授权头伪造、绕过边缘、cookie 剥离、Profile 绑定、退出撤销与 Agent register 回归。
- CDP 真实引擎负向测试覆盖 Host、Origin、DNS rebinding 可触达性及合法认证通道；主世界表达式、iframe stats/audio 和首帧/重连回归。
- 按 docs/blueprint/testing.md 的 doctor_cmd/test_cmd/blackbox_verify 执行；本次仅改 backlog，创建校验不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 边缘与 Gateway 授权证明：已由 spike s018 定稿（docs/spikes/s018_edge_viewer_authorization_proof/report.md）。结论：采纳 Caddy forward_auth 可信内部证明＋API 签发短期 HMAC viewer grant（TTL 60 秒、绑定 Profile、claims 不含会话标识），否决短期授权交换（与官方客户端表达式语义冲突且令牌落日志面更大）。来源认证分两跳且秘密不共用（edge_proof_key 供 Caddy→API、viewer_grant_key 供 API→Gateway）；重放窗口 60 秒且权力小于会话 Cookie；退出/撤销在每次握手的 forward_auth 重验时生效；forward_auth 子请求先于代理与 Upgrade 完成，WebSocket 握手适用。验证方式：shared grant 单元测试、API 边缘端点集成测试、Gateway 集成测试、Caddyfile 渲染契约测试，真实 Caddy/Chrome 链归 AC-006 [deploy] 补验。
- 实际 Chromium loopback Host/Origin 拒绝边界：已由 spike s019 定稿（docs/spikes/s019_chromium_loopback_host_origin_boundary/report.md）。结论（不可达与被拒分开记录）：外部网络对 CDP 本体不可达（容器回环监听、端口未发布、临时端口不披露）；唯一外部入口为 automation token＋控制权围栏的认证自动化通道，DNS rebinding 不构成凭据；沙箱内页面到自身 CDP 的引擎内 Host/Origin 拒绝按 Chromium 默认语义预期成立，须由本 task 新增的 real_engine 负向测试在锁定引擎上留证（云端无 Docker 跳过，归 AC-004 [deploy] 补验）。

### 风险与回退

- 风险：跨模块/制品或状态变更需按上述负向测试与 spike 验证；产品 BLOCKING 未消除不得实施。
- 回退：回退本 task 的完整实现 release；涉及数据先停写者并从已验证成套备份恢复，禁止仅降级数据库或以旧兼容分支兜底。

### 依赖与约束

- 硬依赖和冲突以 progress.md 的 task.py 调度字段为准；不把文件重叠当硬依赖。plan 仅输出图上候选，不能替代 preflight；产品 BLOCKING 必须先确认，SPIKE 先验证并回填。

### Finalization 时更新的 blueprint

- docs/blueprint/architecture.md、docs/blueprint/gateway.md、docs/blueprint/security.md：边缘/API/Gateway 授权职责和 Agent register 例外。
- docs/blueprint/testing.md：Cookie 剥离、CDP 负向与同源回归。
