# Task spec

## 背景

v2.3 同一 Profile 可有多个 ViewerConnection，共享捕获和编码管线。媒体运行时必须与浏览器数据隔离，任何页面不能独立改变远程显示尺寸或压低其他前台页面帧率。

## 契约区

### 范围

- config/docker/stream_runtime/ 独立镜像、src/backend/cbrowser/stream_agent/ 及 schemas/stream/ 协议和本 task 新测试。采用 t001 已确认接口对接 t003 Browser Runtime 的 IPC/X11/音频；Stream Agent 主动连接 Gateway 并接受认证后的 Profile 级媒体需求。主写域不含 API、Browser Agent、共享 pyproject.toml、正式 compose 或前端应用。

### 非范围

- Gateway 注册表/用户鉴权的正式服务、Supervisor 端口和网络编排、前端自定义管理界面、数据库迁移和旧 VNC 删除。不得恢复业务控制租约或为各 Viewer 创建独立全局编码器。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：两个真实 Google Chrome 页面同时连接同一 Profile，视频实际解码且音频实际接收；关闭或刷新一个页面后另一个继续播放和输入，真实浏览器不中断。
- [ ] AC-002：多个页面身份独立且同页面重连保持身份；复制标签页产生身份冲突时不会误踢其他活动页面，远端显示尺寸不随任一页面窗口或连接顺序变化。
- [ ] AC-003：根据认证后的 Profile 聚合需求及资源限制调整共享编码：活动前台达到30 FPS、静止前台回到8 FPS，持续变化视频不因无键鼠降帧；全部隐藏/断开暂停捕获，恢复可见先恢复画面再按活动提帧，后台页面不能降低其他前台需求；接收 Supervisor 提供的过载限制后按 Profile 降低 FPS，资源恢复后回归正常活动目标，过载规则和实测限额不能由页面任意修改。
- [ ] AC-004：真实多个媒体 Peer 使用该 Profile 分配的同一 UDP mux 发布端口；候选地址/端口与实际映射一致，客户端和服务端 RTC 配置各自使用可达 TURN 地址，并按 t001 确认路径完成原计划凭证切换与 relay-to-relay 验收。
- [ ] AC-005：真实中文组合输入不经剪贴板模拟，两个页面输入均到达同一真实浏览器；各页独立静音，关闭首页面不影响其余页面音频。
- [ ] AC-006：Stream Runtime 不挂载浏览器用户数据或 Docker Socket，只能访问对应 Profile 的 X11/音频与媒体网络；Agent 失联重连和媒体暂停不停止浏览器。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；需要真实 Docker、Chrome 和相应已验证网络环境，缺失时不得勾选部署行为。

## 上下文区

- 来源：docs/v2_architecture_plan.md（2026-10-27 核对）；t001 为技术验证硬门禁，尚未完成

### 有意不测

- 迁移现有用户数据与正式环境发布：由后续独立迁移/发布 task 验收，本 task 只在全新隔离测试目录运行

### 测试策略

- 以 t003 正式 Browser Runtime 镜像为真实上游，Google Chrome Stable + Playwright 双页面 E2E，观察 candidate pair、framesDecoded、bytesReceived、音频样本/能量、真实浏览器输入和显示几何。单测覆盖媒体需求处理及非法命令拒绝，不 mock 编码器或 PeerConnection 来证明媒体通过。至少覆盖首页面关闭、隐藏/恢复、持续动画与音频不中断。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- UNVERIFIED-SPIKE：t001 尚未验证完的官方多页面、共享编码器控制、IME、TURN、ICE restart 契约；必须先取得全部验证证据，不将自动重建连接等替代行为静默当作 ICE restart。

### 风险与回退

- 风险：客户端默认 SETTINGS、display_owner 与共享编码器可能覆盖 Profile 全局策略；TURN 过期或后台消息可能影响其他连接。
- 回退：实验和新模块通过独立 worktree、数据目录及容器前缀验证；不覆盖现有用户数据、不切换旧正式运行入口。失败保留证据和当前分支，不迁移或删除旧链路。

### 依赖与约束

- t001 全部通过并冻结技术结论后才能 start。协议/依赖约束：Selkies2.1.0固定官方commit 6ee68a7a815956e6745e916741f13335e0b3ff53；MODE=webrtc、ENABLE_DUAL_MODE=false、ENABLE_SHARING=true、ENABLE_COLLAB=false、FRAMERATE=8,8-30，不设置mk_control=true；不能将版本或配置值充当行为AC。公共索引与跨模块总览由主控在各 task 收尾阶段串行更新，实现 agent 只写本模块，不并发改公共控制面。

### Finalization 时更新的 blueprint

- docs/blueprint/stream_runtime.md：媒体需求、固定分辨率与 RTC/输入边界；docs/specs/webrtc_remote_display.md：更新共享8–30 FPS、多连接、端口池与 TURN 行为，删除旧租约/60 FPS 失效约定。公共 specs_index 由主控在 task worktree 收尾时串行更新。
