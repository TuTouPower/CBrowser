# Task spec

## 背景

完整落实v2架构计划第19.3节，从过载的文件/自动化task拆成可独立验收的执行commit。t001全项技术验证通过前不实施。

## 契约区

### 范围

- 从t008原AC-003/004拆出ClipboardBridge（只处理本机剪贴板权限、页面焦点和拒绝提示，传输沿用 Selkies 官方剪贴板消息，不自建同步协议或 Agent clipboard RPC）、Profile clipboard_sync 到 Selkies 剪贴板策略的映射与服务端锁定、浏览器会话权限/状态提示与OpenAPI生成类型；保留官方IME键盘提交路径，不改变Profile复制重置与文件/CDP服务。

### 非范围

- 不迁移现有用户数据、不删除旧链路、不外部发布，不扩大到相邻模块重构；完整压力、安全与性能门禁不因本task少量用例通过而取消。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：纯文本剪贴板传输遵从权限和明确用户操作，权限拒绝提供可执行提示；保护用户原剪贴板内容，后台页面不自动覆盖本机剪贴板，剪贴板内容不进入日志。
- [ ] AC-002：真实中文组合输入经键盘消息而非剪贴板粘贴；地址栏、普通输入框、受控输入框、富文本中提交/预编辑取消/标点均精确到达目标浏览器，失败明确提示。
- [ ] AC-003：两个页面同时向同Profile输入均能到达，切换或关闭一个页面不丢另一页输入；纯文本粘贴无静默截断/重复，容器与宿主剪贴板各自仅发生获授权变更。
- [ ] AC-004：真实Chrome页面在获得权限、权限拒绝、后台/恢复与切换Profile场景保持各自输入和剪贴板状态，其他Profile不读到对应剪贴板数据；所有测试使用独立已知fixture，不读取用户实际私人剪贴板。
- [x] AC-005：Profile clipboard_sync 开启时 Selkies enable_clipboard=true、关闭时为 false，enable_binary_clipboard=false，均服务端锁定；客户端改写设置不生效，关闭后双向均无剪贴板传输，图片等二进制剪贴板不传输。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部AC可自动测试；需要真实Docker/Chrome和隔离测试数据，缺失时保持未通过。

## 上下文区

- 来源：docs/v2_architecture_plan.md、t008原AC-003/004/005（2026-10-27拆分，保持原需求，不复用t008被移出编号）
- 2026-10-30 计划修订同步：8.4 剪贴板策略（Selkies 2.1.0 enable_clipboard 为 true/in/out/false，enable_binary_clipboard 默认 true，`|locked` 禁止客户端修改；main 当前均未设置）；范围收窄 ClipboardBridge，新增 AC-005。

### 有意不测

- 第19章1000次输入/剪贴板与8小时基准由t009验收，不豁免这些行为；不访问真实用户私密数据

### 测试策略

- 真实Chrome原生composition/clipboard权限与独立fixture、官方DataChannel、真实CloakBrowser四类输入目标；结合消息/DOM/容器clipboard精确判定，不能以JS合成事件或写远端DOM代替提交。1000次IME和1000次clipboard由t009完整验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。Selkies 2.1.0 `enable_clipboard`/`enable_binary_clipboard` 与 `|locked` 语义已由固定 wheel 源码核实；输入/剪贴板传输沿用 t004 已验证的官方 composition/Native X11 与 DataChannel 路径，不新增协议。

### 风险与回退

- 风险：跨Profile数据污染、并发写者或权限状态失配；日志不得包含私密输入/剪贴板。
- 回退：隔离worktree、测试数据根及专属容器，失败保留证据；涉及删除/覆盖必须先验证备份与可回退步骤，不操作真实用户目录。

### 依赖与约束

- 必须取得t008前置产物，继承t001全项通过硬门禁。t013/t014同改OpenAPI及前端生成类型，不并发写同一批生成资产；调度冲突由task.py登记。

### Finalization 时更新的 blueprint

- docs/specs/webrtc_remote_display.md：输入与剪贴板；docs/blueprint/frontend.md、automation.md：权限和页面边界。
