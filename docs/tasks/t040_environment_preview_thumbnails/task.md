# Task spec

## 背景

`docs/plan_20261105_ui_redesign.md` 第 6.7 节（D5、D12，用户 2026-11-05 确认）：环境卡片显示实时缩略图。采集方式选 CDP 而不是 X11 截图，因为 CDP 在 Docker 与将来的独立桌面应用（p041）中都可用。2026-11-05 于 main@3101540 核实现状：Profile 配置字段 `capture_preview`（默认 true，`adapters/database/models.py:53`）已存在但没有实现；Artifact 已有 Agent → Supervisor → API 的转发路径（`supervisor/artifact_forwarder.py`、`api/internal_artifacts.py`）。t037 的卡片视图在无预览时显示占位。

## 契约区

### 范围

- 采集：Runtime Agent 在 running 且 `capture_preview=true` 时，每 15 秒经已有 CDP 连接对当前活动标签页调用 `Page.captureScreenshot`（JPEG 质量 70，缩放到宽 480px），只截网页区域。
- 存储：原子写入 Profile 专属目录的 `preview/latest.jpg` 与元数据（`captured_at`、`runtime_instance_id`），权限 0600；停止后保留最后一帧。
- 转发：复用 Artifact 的 Agent → Supervisor → API 转发模式，具体通道在实施时读代码确定。
- API：`GET /api/v1/profiles/{profile_id}/preview` 需要登录会话，返回 `image/jpeg` 与 `Cache-Control: no-store`，ETag 取 `captured_at`；无预览返回 404。
- SSE 新增 `profile_preview` 事件（`profile_id`、`captured_at`）；前端以 `captured_at` 作为图片 URL 的版本参数刷新卡片缩略图。
- 隐私：截图视同 Cookie 级私密数据，不进日志；重置或删除 Profile 时清除；`capture_preview` 改为 false 时停止采集并删除已有预览。
- OpenAPI 与前端类型同步。

### 非范围

- X11 截图或视频流抽帧。
- 历史缩略图或时间线。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：running 且 `capture_preview=true` 的 Profile 约每 15 秒产生一帧宽 480px 的 JPEG 预览，内容为当前活动标签页的网页区域，不含浏览器标签栏与地址栏（真实栈 E2E 以已知页面内容比对）。
- [ ] AC-002：预览接口未登录时拒绝；有预览时返回 `image/jpeg`、`Cache-Control: no-store` 与基于 `captured_at` 的 ETag；无预览时返回 404。
- [ ] AC-003：每产生一帧新预览，SSE 下发 `profile_preview`，卡片视图据此刷新缩略图，不需要刷新页面。
- [ ] AC-004：Profile 停止后保留最后一帧；`capture_preview` 改为 false 后停止采集并删除已有预览；重置或删除 Profile 后预览被清除。
- [ ] AC-005：预览文件权限为 0600；截图内容与文件路径不出现在日志、错误响应与事件中。
- [ ] AC-006：截图前后页面的 `document.visibilityState`、焦点与活动标签页不变（真实栈 E2E 断言）。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：`docs/plan_20261105_ui_redesign.md` WP13 与第 6.7 节（2026-11-05 于 main@3101540 核实，结论见背景）。

### 有意不测

- 无。

### 测试策略

- unit 覆盖采集调度、原子写入与权限、`capture_preview` 开关与清除。
- integration 覆盖 Agent → Supervisor → API 转发与 SSE 事件。
- 真实栈 E2E 验证截图内容区域与对页面行为无影响。
- 所有浏览器测试无头运行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- CDP 没有直接的「当前活动标签页」字段；在 CloakBrowser 146 / Xvfb 下识别活动标签页的方法，以及 `Page.captureScreenshot` 对后台标签页、焦点和页面可见性的影响：UNVERIFIED-SPIKE，实施前用真实引擎实测，结论写入 `docs/findings/`。

### 风险与回退

- 风险：截图触发页面可见性或焦点变化，成为可被网站观测的自动化特征；预览数据经日志或事件泄露。
- 回退：回退本 task commit；采集可经 `capture_preview` 按 Profile 关闭。

### 依赖与约束

- 依赖 t037（卡片视图）；经 t037 间接依赖 t035。
- 与 t038、t039 同改前端共享文件，与 t041 同改 Runtime Agent，用 `conflicts_with` 串行。
- 所有浏览器测试无头运行。

### Finalization 时更新的 blueprint

- `docs/blueprint/browser_runtime.md`：缩略图采集。
- `docs/blueprint/supervisor.md`：预览转发。
- `docs/blueprint/security.md`：预览隐私。
- 新建 `docs/specs/profile_preview.md`。
