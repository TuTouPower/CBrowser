# Task spec

## 背景

Caddy 当前仅反代，Origin/CSRF/session 鉴权分散在 API 与 Gateway。将会话入口鉴权与自动化 CDP 边界合并交付，避免引入第二条可绕过的入口。现有鉴权与 loopback CDP 已成立，需求属于边界收敛与负向验证，不把已有功能写成缺失。

## 契约区

### 范围

- 部署期生成会话路径 forward_auth 与内部解析端点；管理凭证、路径会话凭证和容器凭证分离，一次性授权交换路径作用域安全 cookie。
- 内部端点在外部 listener 拒绝；剥离转发到运行容器的管理 cookie，约束容器响应运行 origin、CSP、COOP、CORS、Origin/Sec-Fetch-Site 与 Service-Worker-Allowed。
- viewer 不获取 CDP；保留经认证的自动化 API/UDS 通道，核实 Host/origin 与 DNS rebinding 防护。系统 DOM 读取使用隔离执行上下文，不放宽目标页面 CSP。

### 非范围

- 不把 DTLS-SRTP/UDP 经 forward_auth，不删除本机 WebRTC UDP mux。
- 不复活 parked p053 的 LAN、证书分发或跨设备范围；不改 CDP 自动化产品入口。
- 不把宿主 sleep 与页面等待方式的厂商检测宣称写成保证，不为认证收口取消必要的应用内权限检查。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：缺少或伪造会话凭证访问会话 HTTP/WSS 路径均被拒绝；合法一次性授权只能交换一次，得到 HttpOnly/Secure 且作用域限定的 cookie，长期凭据不进入 URL/Referer/访问日志。
- [ ] AC-002：外部 listener 访问内部解析端点被拒；伪造内部鉴权头、跨 Profile cookie、跨站 Origin 与不允许的 Fetch 来源不能越权。
- [ ] AC-003：反代运行容器时不传管理 cookie，容器可控响应不能在持管理凭证 origin 执行脚本或扩大 Service Worker 作用域；安全头与资源加载行为相容。
- [ ] AC-004：普通 viewer 响应、页面配置、WS 消息及错误不暴露 CDP endpoint；认证自动化通道仍可连接，未认证直连与 DNS rebinding/非法 Host-origin 组合被拒。
- [ ] AC-005：系统 DOM 读取不在页面主世界注入探测全局变量、不放宽 CSP；主页面与 iframe 能取得授权范围内的结果。
- [ ] AC-006：真实 Chrome 登录、自动化、WebRTC 首帧及 viewer 重连通过新鉴权链，媒体仍走现行本机 UDP。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；涉及真实 Chrome、引擎、Docker 或网络行为的 AC 使用隔离真实环境探针，不以 mock 结果替代。界面视觉补人工核验，第三方公网检查仅显式 opt-in。

## 上下文区

- 来源：`p075`、`p084`。2026-11-13 核实 network_config.py 生成路由无 forward_auth；auth/dependencies.py 与 gateway/server.py 已有 Origin/session 校验；architecture.md 5.3/5.5 明确 CDP loopback、UDS 和唯一 automation API。agent_executor 中未发现 createIsolatedWorld 调用，需逐 DOM 读取点核实上下文。

### 有意不测

- 不把 DTLS-SRTP/UDP 经 forward_auth，不删除本机 WebRTC UDP mux。：超出本 task 范围；其余已声明 AC 不豁免。

### 测试策略

- 真实 Caddy 容器集成验证认证路由、安全头与请求头剥离；覆盖 cookie path、重放、跨站、跨 Profile 与内部头伪造。
- CDP 主世界/隔离世界与 Host/origin 负向探针，复用 automation CDP 链；Chrome E2E 检查首帧和恢复。
- 项目门禁：按 docs/blueprint/testing.md 的 doctor_cmd / test_cmd / blackbox_verify 执行；本批创建仅验证文档结构，不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- Caddy forward_auth 对 WSS Upgrade、cookie 路径及请求头的实际行为：UNVERIFIED-SPIKE，按仓库固定 Caddy 制品搭建最小验证。
- 容器可控响应与管理 cookie 的 origin 隔离方案：UNVERIFIED-SPIKE，先枚举实际会话响应与 iframe 资源来源，验证 origin/CSP 方案后替换路由，不能只靠一条 CSP 宣称隔离。
- 锁定 Chromium 的 isolated world、Host/origin 支持边界：UNVERIFIED-SPIKE，使用实际引擎验证，不套用上游最新文档。

### 风险与回退

- 风险：鉴权收口可能中断 WS、iframe 或自动化；安全头组合可能使官方客户端无法初始化。
- 回退：回退完整匹配 release 与 Caddy 配置，撤销新路径授权；禁止回退时开放内部端点。

### 依赖与约束

- 保持本机 Docker/OrbStack 与唯一外部 Chrome 客户端边界；不复活 parked 条目。依赖建议见 progress.md；产品 BLOCKING 未确认前不可 start，SPIKE 先验证后回填。

### Finalization 时更新的 blueprint

- docs/blueprint/architecture.md、docs/blueprint/gateway.md：会话授权与 CDP 数据流。
- docs/blueprint/security.md：cookie/origin、内部 listener、隔离 DOM 与负向边界。
- docs/blueprint/decisions.md：鉴权收口 ADR；同步 access_control 与 automation_compatibility spec。
