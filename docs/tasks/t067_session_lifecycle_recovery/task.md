# Task spec

## 背景

只修断线重连：已连接会话信令异常后，媒体仍健康却一直显示 reconnecting；恢复不能重启内部 Browser、改变环境状态或删除数据。用户明确无人连接也保留环境，不新增任何自动回收。

## 契约区

### 范围

- 修复信令异常后媒体健康但 UI 停留 reconnecting；媒体不健康时复用现有恢复路径；迟到结果受 generation/runtime fence 保护。
- 保留官方 resume_key/client_tab_id 与当前连接恢复行为；重连不改变内部 Browser、已有网页和浏览器数据。
- 无 viewer 时继续保留环境；不增加 idle/绝对期限/viewer TTL 等自动停止或销毁规则，现有采集编码暂停行为不变。

### 非范围

- 不做自动回收、无人连接停止/销毁、Webhook、reserveTab、bridge 版本协商、配额或新的生命周期治理。
- 不扩展启动幂等/OperationJournal、启动进度、取消清理或控制面重启对账；原 AC-003/004/005 不在本轮实施。
- 不新增 Persona、预热或用户自检，不修改既有多 viewer 输入和身份语义。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] [deploy] AC-001：已连接后异常 WS 关闭，现有 5 秒恢复检查确认媒体仍健康时，即使 ConnectionSnapshot 未变也退出 reconnecting 到 connected；不重建内部 Browser/现有网页/环境数据。媒体不健康时沿现有重连路径恢复，旧 generation 迟到结果不覆盖当前状态。
- [ ] [deploy] AC-006：诊断与界面可区分正在恢复和已经恢复；健康媒体恢复后不残留无限等待提示，失败原因不含凭据。
- [ ] [deploy] AC-008：全部 viewer 断开后 Browser 环境及已有网页/数据继续保留，不因无人连接或时间经过被新增逻辑停止、重置或删除；再次连接可恢复，既有按活跃 consumer 暂停/恢复采集行为保持。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001、AC-008：真实 Chrome/Stream/Browser 链自动化验收，模拟信令断开、媒体健康/损坏及无 viewer；不可用 mock 替代真实保留与恢复检查。
- AC-006：可自动测试，hook/页面诊断断言；[deploy] 不授权生产发布。

## 上下文区

- 来源：2026-11-13 审阅复核：p079、p083；useBrowserSession 的 WS_CLOSE 分支只在 !healthy 时 reconnect，healthy 分支未恢复 stage；diagnostics_source 仅 ConnectionSnapshot 变化时回调，机制缺口成立但运行复现留给针对性测试。API 已有幂等，Supervisor start/journal 与 Coordinator 随机 ID 仍须验证重试窗口；architecture 5.1 明确关 viewer 不关 Browser，5.3/5.4 不能替代该条证据。

### 有意不测

- 非范围中的新增产品功能不作为本 task 验收；已声明 AC 不豁免。

### 测试策略

- 先用可控 timer 与真实 hook 复现异常 WS + stats 始终健康 + snapshot 不变，覆盖不健康媒体、迟到 generation 与后端停止的负向分支。
- 真 Chrome 验证断线/重新连接、已有网页和 Cookie/存储保留、全部 viewer 关闭后环境仍存在；不写等待任意长 TTL 的假证明，检查没有新增回收计时器及对应生命周期调用。
- 项目门禁按 docs/blueprint/testing.md 执行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 媒体健康但阶段卡住及恢复回调顺序：UNVERIFIED-SPIKE，最小复现并核实现行 timeout/generation fence，随后真链回归。
- 用户明确不新增自动回收，环境无人连接时保留；无产品 BLOCKING。

### 风险与回退

- 风险：跨模块/制品或状态变更需按上述负向测试与 spike 验证；产品 BLOCKING 未消除不得实施。
- 回退：回退本 task 的完整实现 release；涉及数据先停写者并从已验证成套备份恢复，禁止仅降级数据库或以旧兼容分支兜底。

### 依赖与约束

- 硬依赖和冲突以 progress.md 的 task.py 调度字段为准；不把文件重叠当硬依赖。plan 仅输出图上候选，不能替代 preflight；产品 BLOCKING 必须先确认，SPIKE 先验证并回填。

### Finalization 时更新的 blueprint

- docs/blueprint/testing.md：健康媒体信令断线回归、全部 viewer 断开后的环境保留。
- docs/blueprint/architecture.md：只修连接恢复，保持长驻 Browser/状态与既有采集暂停语义。
