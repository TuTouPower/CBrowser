# Task spec

## 背景

2026-11-10 intensive review 在预览缩略图管线（第 92–101 项）列出一组完整性与隐私缺陷，adoption_decision 采纳为 A32–A38：落盘不校验开关、Supervisor 观测去重先记后验、Coordinator 重发换新 request_id 且 pending 无条件 pop、提交两步写非原子与读端 TOCTOU、临时文件名只用 pid、截取第一个 page 而非活动标签、生产采集无帧有效性校验（pixel-verified 声称不实）、前端 preview SSE 无围栏。

## 契约区

### 范围

- A32：预览落盘时校验 Profile 的 `capture_preview` 为开启，否则丢弃。
- A33：Supervisor 预览观测校验与上报成功后才写去重缓存；上报失败记 warning（限频）；Profile 删除时清理预览去重状态。
- A34：Coordinator pending 保存首次 request_id，重发复用；pending 删除为比较后删除。
- A35：预览帧按 captured_at 内容寻址命名，meta 原子指向当前帧，旧帧延后清理；读端先打开帧文件再生成 ETag 并从同一文件输出；原子写临时名唯一（uuid + 独占创建）。
- A36（2026-11-12用户裁定）：缩略图采集该Profile容器内完整浏览器显示画面，包含标签栏、地址栏与当前可见页面；不采集宿主Mac桌面，不再根据CDP页面可见性选择标签。
- A37：落盘前校验帧为可解码 JPEG 且尺寸与请求一致，不通过即丢弃并记录；E2E 采集判据改为结构特征；文档与提交说明不再使用 pixel-verified 表述。
- A38：前端 preview SSE 事件按 captured_at 单调写入，且仅在缓存中 `capture_preview` 开启时写入。
- 2026-11-12用户追加授权：修复d041中策略helper在OCI启动失败后残留created容器；保留零残留断言及原故障镜像。

### 非范围

- 保持15秒采集、480px宽、JPEG质量70及backoff策略；高度按整张画面比例生成。
- 不改预览开关与 epoch 的 DB 语义。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：`capture_preview` 已关闭（无论 epoch 是否变化）时到达的采集通知不更新时间戳、不发 SSE。
- [x] AC-002：上报 API 瞬时失败后，同一帧在下一次上报时仍被处理，不因去重而永久丢失；失败有 warning 日志。
- [x] AC-003：同一策略重发时携带与首次相同的 request_id，Supervisor 识别为重复；epoch 7 失败入 pending、epoch 6 随后成功时，epoch 7 的 pending 仍保留并被重发。
- [x] AC-004：读取预览时返回的字节与 ETag 对应同一帧；读取期间发生清除或新帧替换，不会返回与 ETag 不符的字节。
- [x] AC-005：API、Supervisor、Agent 并发写同一预览路径时，不会互相替换或删除对方的半成品文件。
- [x] AC-006：缩略图包含该Profile浏览器的标签栏、地址栏及当前可见页面；多标签切换后反映实际浏览器画面，不截取后台页面或宿主桌面。
- [x] AC-007：截断或损坏的帧数据不落盘、不更新时间戳；合法帧（含纯色页面）正常落盘。
- [x] AC-008：预览关闭后迟到的 SSE 事件不会恢复缩略图；较旧的 captured_at 不覆盖较新的值。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试（repository / Coordinator / Supervisor 单测、并发写单测、真实引擎整张浏览器多标签 E2E、前端 hook 测试）。

## 上下文区

- 来源：`docs/reviews/review_20261110_200842/adoption_decision.md` A32–A38（审阅原文第 92–100 项及未证实疑点中 `_preview_*` 只写不清）。2026-11-10 已抽验第 99 项（`preview_capture.py:127-139` b64decode 后直接落盘）。

### 有意不测

- 浏览器窗口最小化等宿主级可见性状态：沙箱内无宿主窗口管理，不适用。

### 测试策略

- 后端单测覆盖开关校验、去重时序、request_id 复用、比较后删除、内容寻址读写与临时名唯一。
- 真实引擎 E2E：打开结构特征不同的两个标签页、切换前台后断言整张浏览器画面来源及浏览器界面区域；损坏帧注入。
- 前端：SSE 单调与开关围栏。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 已完成真实引擎实验，见`docs/findings/d038_target_engine_tab_visibility_unreliable.md`：多标签可见性信号不能识别活动页。2026-11-12用户明确裁定改采容器内整张浏览器画面，原可见性选页方案不再采用。

- 容器内Pillow 13.0.0/XCB已实测：独立Xvfb 1280×800，生产SDK启动真实Chromium146，两个结构页面切换0→1→0，整张画面缩放为480×300 JPEG，前台内容与浏览器界面均保留。证据：.scratch/t057/display_probe.py及display_probe.log；无宿主截图回退。

- 目录inode flock已由实施侧及独立review实测，见`docs/findings/d039_orb_stack_directory_flock_scope.md`：同一Linux虚拟机的共享目录在容器间互斥，Mac宿主与虚拟机不互通；该锁只覆盖既定全Docker生产拓扑，读端快照不依赖跨虚拟机锁。

- jpeginfo严格码流校验接口已在真实Docker实测，见`docs/findings/d040_jpeg_decoder_warning_integrity.md`：`--check -`合法纯色返回0、补回EOI的截断帧返回1；首次无位置参数的`--check --stdin`对合法帧亦返回1，未采纳。

- 全量门禁发现既有策略helper启动异常残留，见`docs/findings/d041_policy_helper_oci_start_leak.md`；2026-11-12用户已授权纳入最小修复，并明确修复后仅重跑此前失败的真实E2E，不重复全量门禁。完整B原始失败记录保留，后续定向结果单列。

### 风险与回退

- 风险：显示采集或帧解码失败时本轮不更新；记录脱敏错误类型，不回退宿主截图或CDP后台页面截图。
- 回退：revert 实现 commit。

### 依赖与约束

- 与 t055（Supervisor `core.py`）存在文件重叠，按 `conflicts_with` 串行。

### Finalization 时更新的 blueprint

- `docs/blueprint/browser_runtime.md`：容器整张浏览器画面采集与帧校验。
- `docs/blueprint/supervisor.md`：预览观测去重与 request_id 语义。
- `docs/specs/profile_preview.md`：开关校验、读写一致性与前端围栏。
