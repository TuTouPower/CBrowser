# Task spec

## 背景

完整落实 docs/v2_architecture_plan.md 对应正式实施阶段。打通 Artifact 文件管理与受控 CDP 自动化；t001全项技术验证通过前不实施。

## 契约区

### 范围

- Artifact Service/Repository/API、Supervisor Browser Agent UDS 转发、下载事件入库、frontend artifacts/automation 与对应测试；浏览器用户数据和 Artifact 存储分离。原AC-003/004转t014，原AC-005转t013；本task保留文件/CDP闭环，不重复承载剪贴板输入与复制重置。

### 非范围

- 不越过前置验证门禁，不静默缩减计划或改写验收标准；不处理与本阶段无关重构，不覆盖未获具体授权的用户数据或外部环境。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：真实上传校验文件名/MIME/配额/磁盘空间并写对应 Profile Artifact，失败不留下半文件；下载经 Agent 事件可见且内容/大小正确，UI 可列出/下载/删除获授权文件，路径穿越与跨 Profile 请求拒绝；上传返回Artifact ID和容器内container_path（/exchange/uploads/...），不泄露宿主路径；/profiles/:profileId/files页面可实际上传/管理文件。
- [ ] AC-002：外部自动化经独立认证入口到 Supervisor/UDS/loopback CDP，完整双向协议可用；无公网 CDP TCP 映射，旧 CDP 入口仅薄转发新代理；自动化断开后下载捕获恢复，随后真实下载完整入库；/automation/:profileId页面展示获授权端点和状态，独立路由加载/刷新保持正常会话。

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

- 真实本地HTTP上传/下载、容器CDP/UDS、授权正负例、真实Chrome文件/自动化页面及受控fixture；文件hash与数据库事件校验，禁止以临时fake文件替代实际下载。剪贴板/IME由t014、复制重置由t013独立交付，1000次专项由t009验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- UNVERIFIED-SPIKE：以前置task最终已验证协议/模型/镜像为准；现有原型不得直接视为正式契约。涉及原生Linux/公网/实际数据/外部发布时必须核实入口与授权。

### 风险与回退

- 风险：跨服务权限、并发恢复、凭证或数据一致性可能失败；任何未验证行为不得凭配置字段或模拟通过。
- 回退：隔离worktree、测试数据根和容器资源；保留失败日志，回退本阶段产物。生产数据和外部变更按具体验证备份/回滚方案执行。

### 依赖与约束

- 必须先取得t007完成产物；所有正式实施继承t001全项通过硬门禁。保持计划20实施顺序；公共文档/索引由主控串行收尾。

### Finalization 时更新的 blueprint

- docs/blueprint/artifacts.md、docs/blueprint/automation.md：文件/CDP/剪贴板；docs/specs/profile_management.md：复制重置行为。
