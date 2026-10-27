# Task spec

## 背景

完整落实 docs/v2_architecture_plan.md 对应正式实施阶段。实现页面独立 Profile 选择与 WebRTC 浏览界面；t001全项技术验证通过前不实施。

## 契约区

### 范围

- src/frontend/src/app、features/profiles、features/browser_session、features/settings、shared/api、shared/components/i18n；Router/Provider、生成 API 类型、TanStack Query、SSE 与官方 Selkies 薄适配。文件与自动化业务由 t008 完成。

### 非范围

- 不越过前置验证门禁，不静默缩减计划或改写验收标准；不处理与本阶段无关重构，不覆盖未获具体授权的用户数据或外部环境。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：计划13.1全部页面可导航，/?profileId= 恢复当前目标；两个真实 Chrome 标签页各自切换 Profile，不改另一页目标或连接，不使用共享 localStorage.currentProfileId。
- [ ] AC-002：同 Profile 两页面使用不同官方 client_tab_id，刷新和重连保留 resume_key/身份，复制页冲突重新连接且不踢原页；新标签页 noopener，不重写官方 HELLO。
- [ ] AC-003：页面切换或关闭仅关闭自身 PeerConnection/信令，不调用 Profile stop；页面恢复查询真实运行状态并恢复 Viewer；只有明确停止 Profile 才关闭真实浏览器。
- [ ] AC-004：真实后台可见性驱动每连接解码暂停及 Profile 聚合捕获，前台持续视频保持目标帧率；显示尺寸/DPR由 Profile 配置控制，外部窗口 resize 不改变远端，设置变更须明确应用。
- [ ] AC-005：两个页面都能真实输入且独立静音，无租约/唯一控制者状态；内部浏览器标签页变化同步显示，运行/媒体/音频故障分别给出可理解状态，初次画面和操作延迟可测。
- [ ] AC-006：Profile 列表/创建/编辑/标签/设置通过 /api/v1 生成类型客户端完成；后端状态经 SSE 更新，断线恢复无陈旧控制状态；旧 UI 测试语义失效时整项删除并说明，新增真实新语义测试。

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

- Google Chrome Stable + Playwright 真实双标签页/后台最小化/刷新复制/切换 Profile 与实际 Runtime E2E，DOM/候选/媒体统计交叉校验；组件单测覆盖错误状态，不 mock 媒体证明功能。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- UNVERIFIED-SPIKE：以前置task最终已验证协议/模型/镜像为准；现有原型不得直接视为正式契约。涉及原生Linux/公网/实际数据/外部发布时必须核实入口与授权。

### 风险与回退

- 风险：跨服务权限、并发恢复、凭证或数据一致性可能失败；任何未验证行为不得凭配置字段或模拟通过。
- 回退：隔离worktree、测试数据根和容器资源；保留失败日志，回退本阶段产物。生产数据和外部变更按具体验证备份/回滚方案执行。

### 依赖与约束

- 必须先取得t006完成产物；所有正式实施继承t001全项通过硬门禁。保持计划20实施顺序；公共文档/索引由主控串行收尾。

### Finalization 时更新的 blueprint

- docs/blueprint/frontend.md：页面独立状态与官方适配；docs/specs/profile_management.md、docs/specs/webrtc_remote_display.md：交互行为。
