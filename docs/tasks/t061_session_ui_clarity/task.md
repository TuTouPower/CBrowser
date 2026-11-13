# Task spec

## 背景

会话页面视觉问题与断线后的 UI 阶段收敛共用组件/hook/页面测试。合并 t061 与收缩后的 t067，交付会话展示和断线重连修复；不引入生命周期或产品新功能。

## 契约区

### 范围

- 顶部详情按钮作为唯一开关，关闭面板释放宽度；保留开关持久化。
- 正常等待使用轻量指示，故障、未启动和停止状态按下列真实 SessionStage 矩阵分别展示；沿用现有阶段枚举，仅修复断线重连所需的阶段收敛。
- 顶栏与详情的传输状态统一国际化；环境触发器只显示名称，列表保留各环境状态。
- 修复信令异常后媒体健康但 UI 停留 reconnecting；媒体不健康时复用现有恢复路径；迟到结果受 generation/runtime fence 保护。
- 保留官方 resume_key/client_tab_id 与当前连接恢复行为；重连不改变内部 Browser、已有网页和浏览器数据。
- 无 viewer 时继续保留环境；不增加 idle/绝对期限/viewer TTL 等自动停止或销毁规则，现有采集编码暂停行为不变。

### 非范围

- 不新增自动回收、三时限、无人连接停止/销毁、Webhook、reserveTab、bridge 协议协商、启动治理、Persona、预热、自检或配额。
- 不改变内部 Browser 进程、已有网页/数据及多 viewer 输入契约；保留官方 resume_key/client_tab_id。
- 覆盖 364d191 在正常等待态新增按钮的视觉契约，保留故障态适用重连动作；不更改 DESIGN.md token。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：顶部按钮关闭后详情面板不占宽度，再次点击恢复；刷新保持开关状态，面板内部无标题/第二开关，页面唯一详情开关的定位无歧义。
- [ ] AC-002：checking_runtime、connecting_signaling、media_waiting、reconnecting 四种等待态仅显示轻量指示，不渲染居中诊断表或操作按钮；connected 不显示等待层。connecting_ice 不属于 SessionStage，不新增该运行态。
- [ ] AC-003：signaling_failed、ice_failed、media_no_frames、web_locks_unavailable、error 保留诊断及适用重连动作；runtime_not_ready 保留启动与状态提示；stopping 显示停止提示及现有查看状态入口，不提供启动/重连。
- [ ] AC-004：中/英文界面中 ready/recovering/failed/unknown 在顶栏与详情均显示对应翻译；未知或缺失值有本地化兜底，不展示原始机器码。
- [ ] AC-005：环境触发器不含状态徽标，顶栏运行状态只显示一次；下拉项仍显示各环境状态，移除触发器当前状态后不保留仅服务该徽标的查询。
- [ ] [deploy] AC-006：已连接后异常 WS 关闭，现有 5 秒恢复检查确认媒体仍健康时，即使 ConnectionSnapshot 未变也退出 reconnecting 到 connected；不重建内部 Browser/现有网页/环境数据。媒体不健康时沿现有重连路径恢复，旧 generation 迟到结果不覆盖当前状态。
- [ ] AC-007：诊断与界面可区分正在恢复和已经恢复；健康媒体恢复后不残留无限等待提示，失败原因不含凭据。
- [ ] [deploy] AC-008：全部 viewer 断开后 Browser 环境及已有网页/数据继续保留，不因无人连接或时间经过被新增逻辑停止、重置或删除；再次连接可恢复，既有按活跃 consumer 暂停/恢复采集行为保持。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001..005：组件/页面和真实 Chrome 布局断言可自动化；人工视觉仅补充。
- AC-006、AC-008：需真实 Chrome/Stream/Browser 断线恢复及无 viewer 保留验收，不用 mock 替代；[deploy] 不授权生产发布。
- AC-007：hook/页面诊断可自动测试。

## 上下文区

- 合并来源：t067（p079/p083 中仅保留断线重连范围）。来源 AC-001→本 task AC-006，来源 AC-006→AC-007，来源 AC-008→AC-008；原 t061 AC-001..005 保留。取消的启动治理/自动回收等不并入。
- 来源：2026-11-13 审阅复核：p061、p064、p065；复核 types.ts、session_stage.ts 与 stageActions，stopping 是终止态；connecting_ice 仅为组件遗留 StageKey 扩展。SessionDetailsPanel.tsx 固定宽度/内部开关/transport_state 原值均存在。

### 有意不测

- 非范围中的新增产品功能不作为本 task 验收；已声明 AC 不豁免。

### 测试策略

- 组件与页面测试覆盖全部真实阶段、开关占位、本地化、缺失值及持久化；SessionDetailsPanel.test.tsx 的关闭仍保留容器断言、SessionPage.test.tsx 的内部开关定位与 SessionStagePanel.test.tsx 的全阶段重连断言需整体替换失效用例并写明理由，禁止仅改旧预期追随输出。
- 真实 Chrome 自动化验证布局宽度和首帧就绪；人工只做补充视觉 QA，不替代 AC 自动断言。
- 按 docs/blueprint/testing.md 的 doctor_cmd/test_cmd/blackbox_verify 执行；本次仅改 backlog，创建校验不代表实现验收。
- 先用可控 timer 与真实 hook 复现异常 WS + stats 始终健康 + snapshot 不变，覆盖不健康媒体、迟到 generation 与后端停止的负向分支。
- 真 Chrome 验证断线/重新连接、已有网页和 Cookie/存储保留、全部 viewer 关闭后环境仍存在；不写等待任意长 TTL 的假证明，检查没有新增回收计时器及对应生命周期调用。
- 项目门禁按 docs/blueprint/testing.md 执行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 媒体健康但阶段卡住及恢复回调顺序：UNVERIFIED-SPIKE，用真实 hook 最小复现现行 timeout/generation fence 后修复并真链验证；产品边界已明确，无产品 BLOCKING。

### 风险与回退

- 风险：按上述负向测试及技术 spike 验证恢复/数据原子性；产品边界已确认，不再以已取消功能阻塞实施。
- 回退：回退本 task 的完整实现 release；涉及数据先停写者并从已验证成套备份恢复，禁止仅降级数据库或以旧兼容分支兜底。

### 依赖与约束

- 硬依赖和冲突以 progress.md 的 task.py 调度字段为准；不把文件重叠当硬依赖。plan 仅输出图上候选，不能替代 preflight；技术 SPIKE 先验证并回填，不新增产品功能。

### Finalization 时更新的 blueprint

- docs/blueprint/testing.md：会话阶段/布局、本地化、健康媒体断线及无人连接保留。
- docs/blueprint/architecture.md：既有长驻 Browser、连接恢复与采集暂停的职责边界。
