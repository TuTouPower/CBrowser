# Task spec

## 背景

2026-11-10 intensive review 在前端状态管理方面列出一组一致性缺陷，adoption_decision 采纳为 A24、A25、A27、A39：

- Profile 编辑提交整份表单快照，会把其它客户端的修改以旧值写回，并产生内容倒退的配置版本；前端字段分类比后端少一类（`capture_preview`）；保存后先 setQueryData 再立即 invalidate，在途旧 GET 可回填旧值。
- 会话页 stage 已由 runtimeQuery 派生，但错误文案与 hook 内部 timer 仍由 hook 自行读取 runtime 决定，可与展示态分岔；后端 stopped 时迟到的帧信号仍可把 hook 推到 connected 并启动音频管线。
- 根 ErrorBoundary 丢弃错误、无日志、在 Router 之外，任一渲染异常即全应用错误页且只能整页重载。
- runtime 首检完成前收到的延迟 WS_CLOSE 会启动恢复轮询，随后覆盖已定版的诊断态。

## 契约区

### 范围

- A24：Profile 编辑只提交与初始值不同的字段；字段分类直接使用后端导出的分类（经生成类型或接口），与后端 instant / metadata / runtime 三分一致；保存成功时取消在途 detail 查询后写入缓存，不再 invalidate detail。
- A25：会话错误文案与 stage 一并由 runtimeQuery 派生，hook 不再自行读取 runtime 写错误；帧信号仅在后端状态非 stopped / error 时推进连接态。
- A27：ErrorBoundary 记录错误到前端日志通道；Router 内为路由内容增加 boundary，路由切换即复位；根部保留兜底。
- A39：runtime 首检完成前收到的 WS_CLOSE 只记录、不启动恢复；首检定版为非 running 时取消同 generation 的恢复轮询。

### 非范围

- 不改会话页视觉与布局（p061、p064、p065 前端界面改造不在本 task）。
- 不改后端配置三分规则。
- 不改 Profile 创建防重（t056 A23）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：编辑表单只修改时区时，请求体只含时区字段；另一客户端在此期间对其它字段的修改不被覆盖。
- [ ] AC-002：仅切换 `capture_preview` 时不产生新配置版本，前端走即时字段路径。
- [ ] AC-003：保存成功后，即使保存前已有在途的旧 detail 请求，再次打开配置页显示的是保存后的值。
- [ ] AC-004：会话页错误文案与展示 stage 始终来自同一份 runtime 数据；runtime 单次读取失败不会在 stage 健康时显示错误文案。
- [ ] AC-005：后端状态为 stopped 时，迟到的帧信号不会使会话进入 connected，也不会启动音频管线。
- [ ] AC-006：路由内容渲染异常时，只有该路由显示错误页，导航到其它路由后恢复正常；错误被记录到前端日志通道。
- [ ] AC-007：Profile 未运行时打开会话页，首检完成前收到的 WS 1006 关闭不会把最终状态覆盖为信令失败。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试（React 组件与 hook 测试、mock API 时序）。

## 上下文区

- 来源：`docs/reviews/review_20261110_200842/adoption_decision.md` A24、A25、A27、A39（审阅原文第 79–83、85、101 项）。实施前按审阅位置核实：`ProfileForm.tsx:53-58`、`ConfigTab.tsx:44-62`、`useProfilesQuery.ts:87-90`、`repository.py:116-120`、`useBrowserSession.ts:150-168,419-499`、`SessionPage.tsx`、`ErrorBoundary.tsx`、`main.tsx`。

### 有意不测

- React Query 在途请求晚到的精确时序：以「保存后 cancel + 不 invalidate detail」的行为测试替代。

### 测试策略

- 组件 / hook 测试：请求体内容、缓存值、stage 与错误文案同源、帧信号守卫、boundary 复位、首检前 WS 关闭。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。

### 风险与回退

- 风险：增量提交漏掉联动字段（如时区与语言联动）；以 t053 联动测试与本 task AC-001 共同覆盖。
- 回退：revert 实现 commit。

### 依赖与约束

- 与 t053（ProfileForm）、t056（ProfileForm / 创建弹窗、错误契约）、t059（组件样式）存在文件重叠，按 `conflicts_with` 串行。

### Finalization 时更新的 blueprint

- `docs/blueprint/frontend.md`：增量提交、会话状态单一权威、错误边界层级。
- `docs/specs/profile_management.md`、`docs/specs/webrtc_remote_display.md`：对应行为。
