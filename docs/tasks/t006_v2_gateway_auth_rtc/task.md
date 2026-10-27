# Task spec

## 背景

完整落实 docs/v2_architecture_plan.md 对应正式实施阶段。实现认证信令 Gateway 与独立 RTC 凭证轮换；t001全项技术验证通过前不实施。

## 契约区

### 范围

- src/backend/cbrowser/gateway、auth、rtc_config 与对应 API/内部 RPC；Agent 注册表、每 Viewer 独立隧道、登录/CSRF/Origin/Profile 授权、独立自动化凭证基础和客户端/Stream RTC 配置。

### 非范围

- 不越过前置验证门禁，不静默缩减计划或改写验收标准；不处理与本阶段无关重构，不覆盖未获具体授权的用户数据或外部环境。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：首次启动使用用户提供管理员密码，Argon2id 保存；真实 HTTPS 登录 Cookie 含 HttpOnly/Secure/SameSite=Strict，写请求缺 CSRF 拒绝；未登录、错误 Origin、跨 Profile 未授权 Viewer 无法建立信令，master token 不返回前端。
- [ ] AC-002：Agent 专属凭证注册包含计划7.2字段，健康消息每10秒，连接丢失按1/2/4/8/16/30秒退避；过期实例不覆盖当前注册，未就绪 Profile 明确拒绝连接。
- [ ] AC-003：两个真实 Chrome 页面各经独立 Agent/Gateway 隧道协商并解码音视频，关闭一条不影响另一条；Gateway SIGKILL 后浏览器进程不变，Agent 重注册，页面恢复连接；媒体不经 Gateway。
- [ ] AC-004：客户端与 Stream 分别取得可达 TURN URL 和各自凭证；新连接总取当前有效配置，24小时凭证每12小时更新并在旧凭证到期前6小时执行已验证 ICE restart；失败显式记录并重试，不静默用过期凭证。
- [ ] AC-005：真实 relay-only 双端选中 relay candidate，并以新代接管、旧代退役后的新音视频增量证明两次凭证切换，同一 PeerConnection/媒体对象保持；无效凭证负例不能由旧媒体判成功。
- [ ] AC-006：CDP 自动化独立 Bearer Token 或 mTLS，合法非浏览器客户端可无 Origin；登录 Cookie 不能代替自动化凭证；认证失败、撤销与权限越界可观察且审计不泄漏秘密。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部AC具备可自动验证路径；需真实部署/用户数据/原生平台的行为必须具备对应环境和授权，缺失时保持未通过，不用模拟替代。

## 上下文区

- 来源：docs/v2_architecture_plan.md（2026-10-27逐项核对）；t001在登记worktree仍active，尚未通过全部技术门禁

### 有意不测

- 无已豁免计划行为；范围外阶段由其独立task执行，不据此取消完整目标验收

### 测试策略

- 真实 TLS/HTTP/WebSocket、真实 Chrome/正式 Runtime、Gateway 进程故障、实际 coturn relay；凭证调度单测可用受控时钟覆盖边界，另用短周期集成验证真实轮换，不能仅 mock ICE。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- UNVERIFIED-SPIKE：以前置task最终已验证协议/模型/镜像为准；现有原型不得直接视为正式契约。涉及原生Linux/公网/实际数据/外部发布时必须核实入口与授权。

### 风险与回退

- 风险：跨服务权限、并发恢复、凭证或数据一致性可能失败；任何未验证行为不得凭配置字段或模拟通过。
- 回退：隔离worktree、测试数据根和容器资源；保留失败日志，回退本阶段产物。生产数据和外部变更按具体验证备份/回滚方案执行。

### 依赖与约束

- 必须先取得t005完成产物；所有正式实施继承t001全项通过硬门禁。保持计划20实施顺序；公共文档/索引由主控串行收尾。

### Finalization 时更新的 blueprint

- docs/blueprint/gateway.md、docs/blueprint/security.md：注册/鉴权/凭证边界；docs/specs/webrtc_remote_display.md：隧道与 RTC 行为。
