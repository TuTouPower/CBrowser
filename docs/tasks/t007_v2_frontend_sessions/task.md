# Task spec

## 背景

完整落实 docs/v2_architecture_plan.md 对应正式实施阶段。实现页面独立 Profile 选择与 WebRTC 浏览界面；t001全项技术验证通过前不实施。

## 契约区

### 范围

- src/frontend/src/app、features/profiles、features/browser_session、features/settings、shared/api、shared/components/i18n；Router/Provider、生成 API 类型、TanStack Query、SSE 与官方 Selkies 薄适配；API 运行意愿变更触发 Supervisor 启停的内部协调（p003）；每 Profile Selkies master/controller token（计划 8.1，p004）及 Stream 显式 Selkies 会话设置。文件与自动化业务由t008完成，复制/重置由t013、剪贴板桥接与完整输入场景由t014交付；本task保留基本多页面媒体/键盘输入。

### 非范围

- 不越过前置验证门禁，不静默缩减计划或改写验收标准；不处理与本阶段无关重构，不覆盖未获具体授权的用户数据或外部环境。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：计划13.1全部页面可导航，/?profileId= 恢复当前目标；两个真实 Chrome 标签页各自切换 Profile，不改另一页目标或连接，不使用共享 localStorage.currentProfileId。

- [ ] AC-002：同 Profile 两页面使用不同官方 client_tab_id，刷新和重连保留 resume_key/身份，复制页冲突重新连接且不踢原页；新标签页 noopener，不重写官方 HELLO。

- [ ] AC-003：页面切换或关闭仅关闭自身 PeerConnection/信令，不调用 Profile stop；页面恢复查询真实运行状态并恢复 Viewer；只有明确停止 Profile 才关闭真实浏览器。

- [ ] AC-004：真实后台可见性经 Selkies 官方 STOP_VIDEO/START_VIDEO 只暂停该连接视频，全部后台时捕获暂停，前台持续视频保持目标帧率；页面不向 Gateway 上报可见性或活动；显示尺寸/DPR由 Profile 配置控制，外部窗口 resize 不改变远端，设置变更须明确应用。

- [ ] AC-005：两个页面都能真实输入且独立静音，无租约/唯一控制者状态；内部浏览器标签页变化同步显示，运行/媒体/音频故障分别给出可理解状态，初次画面和操作延迟可测。

- [ ] AC-006：Profile 列表/创建/编辑/标签/设置通过 /api/v1 生成类型客户端完成；后端状态经 SSE 更新，断线恢复无陈旧控制状态；旧 UI 测试语义失效时整项删除并说明，新增真实新语义测试。

- [ ] AC-007：页面冻结/恢复（Page Lifecycle freeze/resume、bfcache pageshow）后检测失效连接并以原 client_tab_id/resume_key 重建；运行时未就绪、信令失败、ICE 失败、媒体无帧分别显示阶段与可执行操作，诊断取自 RTCPeerConnection 状态与 getStats，不出现无解释黑屏、不新增媒体回退通道。

- [ ] AC-008：Stream Runtime 显式关闭 Selkies 模式切换（enable_dual_mode=false），客户端无法切换到 WebSocket 模式。

- [ ] AC-009：用户经 /api/v1 设置 Profile 运行意愿为 running/stopped 后，API 经内部认证 RPC 驱动 Supervisor 真实启动/停止该 Profile 的 Browser/Stream，前端只经 API 操作；Supervisor 不可达时运行意愿保留并显式报告，恢复后收敛，不由测试直调 Supervisor 代替。

- [ ] AC-010：每个 Profile 的 Selkies master token 与 controller token 由服务端随机生成，master token 不出现在任何前端可见响应、页面或日志；外部页面无需持有 token 即可经认证 Gateway 隧道以 controller 身份连接，绕过隧道直连 Selkies 或使用错误 token 被拒。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部AC具备可自动验证路径；需真实部署/用户数据/原生平台的行为必须具备对应环境和授权，缺失时保持未通过，不用模拟替代。

## 上下文区

- 来源：docs/v2_architecture_plan.md（2026-10-27逐项核对）；t001 已完成并归档（docs/archive/tasks/t001_v2_runtime_validation），技术门禁已通过
- 2026-10-30 计划修订同步：9.3 可见性只走 Selkies 原生、8.1 显式 Selkies 设置、13.4 冻结恢复与连接诊断；AC-004 改写，新增 AC-007/008。

### 有意不测

- 无已豁免计划行为；范围外阶段由其独立task执行，不据此取消完整目标验收

### 测试策略

- Google Chrome Stable + Playwright 真实双标签页/后台最小化/刷新复制/切换 Profile 与实际 Runtime E2E，DOM/候选/媒体统计交叉校验；组件单测覆盖错误状态，不 mock 媒体证明功能。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 前置契约已核实（t006 merge ceb7f34）：Gateway 信令 `/stream/{profileId}/signal`、首帧 `rtc_config`、`ice_restart`/`ice_restart_answer` 控制帧、可见性只走官方 STOP_VIDEO/START_VIDEO（9.3，页面不得上报活动）、登录/CSRF/Origin 与会话 Cookie 见 docs/blueprint/gateway.md、security.md、schemas/openapi/cbrowser_v1.json；Selkies 2.1.0 RTC 配置与 relay-only 行为见 d021/d022；无头 Chrome 可见性限制见 d023；可复用真实栈拓扑夹具 tests/fixtures/gateway_probe/。
- UNVERIFIED-SPIKE：Selkies 2.1.0 master/controller token 的配置入口（`master_token`、`tokens_file`、HELLO/URL 携带方式）与官方 Web 客户端在 token 模式下的连接行为，开工时以固定源码与真实 Stream 镜像实验核实后改写为结论。

### 风险与回退

- 风险：跨服务权限、并发恢复、凭证或数据一致性可能失败；任何未验证行为不得凭配置字段或模拟通过。
- 回退：隔离worktree、测试数据根和容器资源；保留失败日志，回退本阶段产物。生产数据和外部变更按具体验证备份/回滚方案执行。

### 依赖与约束

- 必须先取得t006完成产物；所有正式实施继承t001全项通过硬门禁。保持计划20实施顺序；公共文档/索引由主控串行收尾。

### Finalization 时更新的 blueprint

- docs/blueprint/frontend.md：页面独立状态与官方适配；docs/specs/profile_management.md、docs/specs/webrtc_remote_display.md：交互行为。
