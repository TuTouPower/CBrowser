# Task spec

## 背景

2026-11-10 intensive review 在预览缩略图管线（第 92–101 项）列出一组完整性与隐私缺陷，adoption_decision 采纳为 A32–A38：落盘不校验开关、Supervisor 观测去重先记后验、Coordinator 重发换新 request_id 且 pending 无条件 pop、提交两步写非原子与读端 TOCTOU、临时文件名只用 pid、截取第一个 page 而非活动标签、生产采集无帧有效性校验（pixel-verified 声称不实）、前端 preview SSE 无围栏。

## 契约区

### 范围

- A32：预览落盘时校验 Profile 的 `capture_preview` 为开启，否则丢弃。
- A33：Supervisor 预览观测校验与上报成功后才写去重缓存；上报失败记 warning（限频）；Profile 删除时清理预览去重状态。
- A34：Coordinator pending 保存首次 request_id，重发复用；pending 删除为比较后删除。
- A35：预览帧按 captured_at 内容寻址命名，meta 原子指向当前帧，旧帧延后清理；读端先打开帧文件再生成 ETag 并从同一文件输出；原子写临时名唯一（uuid + 独占创建）。
- A36：缩略图只截取活动标签页（按页面可见性判定）；无法确定活动页时本轮跳过。
- A37：落盘前校验帧为可解码 JPEG 且尺寸与请求一致，不通过即丢弃并记录；E2E 采集判据改为结构特征；文档与提交说明不再使用 pixel-verified 表述。
- A38：前端 preview SSE 事件按 captured_at 单调写入，且仅在缓存中 `capture_preview` 开启时写入。

### 非范围

- 不改采集频率、尺寸与 backoff 策略。
- 不改预览开关与 epoch 的 DB 语义。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：`capture_preview` 已关闭（无论 epoch 是否变化）时到达的采集通知不更新时间戳、不发 SSE。
- [ ] AC-002：上报 API 瞬时失败后，同一帧在下一次上报时仍被处理，不因去重而永久丢失；失败有 warning 日志。
- [ ] AC-003：同一策略重发时携带与首次相同的 request_id，Supervisor 识别为重复；epoch 7 失败入 pending、epoch 6 随后成功时，epoch 7 的 pending 仍保留并被重发。
- [ ] AC-004：读取预览时返回的字节与 ETag 对应同一帧；读取期间发生清除或新帧替换，不会返回与 ETag 不符的字节。
- [ ] AC-005：API、Supervisor、Agent 并发写同一预览路径时，不会互相替换或删除对方的半成品文件。
- [ ] AC-006：多标签页时缩略图内容来自当前可见的标签页，不截取后台标签页。
- [ ] AC-007：截断或损坏的帧数据不落盘、不更新时间戳；合法帧（含纯色页面）正常落盘。
- [ ] AC-008：预览关闭后迟到的 SSE 事件不会恢复缩略图；较旧的 captured_at 不覆盖较新的值。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试（repository / Coordinator / Supervisor 单测、并发写单测、真实引擎多标签 E2E、前端 hook 测试）。

## 上下文区

- 来源：`docs/reviews/review_20261110_200842/adoption_decision.md` A32–A38（审阅原文第 92–100 项及未证实疑点中 `_preview_*` 只写不清）。2026-11-10 已抽验第 99 项（`preview_capture.py:127-139` b64decode 后直接落盘）。

### 有意不测

- 浏览器窗口最小化等宿主级可见性状态：沙箱内无宿主窗口管理，不适用。

### 测试策略

- 后端单测覆盖开关校验、去重时序、request_id 复用、比较后删除、内容寻址读写与临时名唯一。
- 真实引擎 E2E：打开两个标签页、切换前台后断言缩略图来源；损坏帧注入。
- 前端：SSE 单调与开关围栏。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 沙箱内 Chromium（无宿主窗口焦点）多标签时，后台标签的 `document.visibilityState` 是否为 `hidden`：UNVERIFIED-SPIKE，实施时以真实引擎开两个标签页实测，结论写入 findings 后再定活动页判定方式。

### 风险与回退

- 风险：活动页判定失效时缩略图长期不更新；以「无法确定即跳过」+ 日志使问题可见。
- 回退：revert 实现 commit。

### 依赖与约束

- 与 t055（Supervisor `core.py`）存在文件重叠，按 `conflicts_with` 串行。

### Finalization 时更新的 blueprint

- `docs/blueprint/browser_runtime.md`：活动标签采集与帧校验。
- `docs/blueprint/supervisor.md`：预览观测去重与 request_id 语义。
- `docs/specs/profile_preview.md`：开关校验、读写一致性与前端围栏。
