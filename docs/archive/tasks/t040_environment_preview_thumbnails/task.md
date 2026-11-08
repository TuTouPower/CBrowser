# Task spec

## 背景

`docs/plan_20261105_ui_redesign.md` 第 6.7 节（D5、D12，用户 2026-11-05 确认）：环境卡片显示实时缩略图，用 CDP 采集（Docker 与将来的独立桌面应用 p041 中都可用）。2026-11-05 按外部审阅重新设计授权与存储。2026-11-05 于 main@3101540 核实现状：

- `capture_preview` 字段存在（默认 true，`adapters/database/models.py:53`）但没有实现；t035 把它定为即时策略，不进入配置版本。
- Browser 容器只挂载 `/data/profiles/{id}/profile`、`/data/runtime-events/{id}`、引擎缓存与下载交换目录（`supervisor/container_spec.py`）；API 挂载整个数据目录（`compose.yaml` 的 api 服务）。
- 现有 Artifact 链路是「共享数据目录 + 每事件一个 JSON 文件 + 游标」（`supervisor/artifact_forwarder.py`），面向持久下载；不适合每 15 秒覆盖一次的缩略图。
- `RuntimeEventBroadcaster` 的所有事件共用一个 `maxlen=1000` 的重放环（`api/runtime_coordinator.py:48`）；前端 SSE 客户端没有按事件类型分发（`shared/api/sse.ts`）。

## 契约区

### 范围

- 预览授权是即时策略：
    - API 是权威，持久化 `capture_preview` 与递增的策略代次。
    - 策略变化经 Supervisor 即时下发给运行中的 Agent，不需要重启或应用配置。
    - 采集、落盘、通知、读取四个环节都校验策略代次与 runtime 实例；任一不一致时丢弃，并删除残留文件。
- 采集：Agent 在 running 且策略允许时，每 15 秒经已有 CDP 连接截取当前活动标签页（JPEG 质量 70，缩放到宽 480px），只截网页区域。
- 存储：
    - Agent 原子写入 `profiles/{id}/preview/latest.jpg` 与 `meta.json`（`captured_at`、`runtime_instance_id`、策略代次），权限 0600。
    - 该目录单独挂载进 Browser 容器，不放进浏览器 user data 目录，因此不会被「含浏览器状态」的复制带走。
    - 停止后保留最后一帧。
- 通知：
    - Agent 健康状态携带最新 `captured_at`；Supervisor 观测到变化时通知 API。
    - API 广播 `profile_preview` 事件（`profile_id`、`captured_at`）。该事件只实时扇出，不进入 runtime 事件的重放环。
    - `ProfileRuntimeResponse` 与 runtime 状态事件含 `preview_captured_at`，首屏据此决定显示图片或占位。
- API：`GET /api/v1/profiles/{profile_id}/preview` 需要登录会话，返回 `image/jpeg` 与 `Cache-Control: no-store`，ETag 取 `captured_at`；无预览或策略已撤销时返回 404。
- 前端：SSE 客户端按事件类型分发；卡片视图以 `captured_at` 作为图片 URL 的版本参数刷新缩略图。
- 撤销与清除：
    - 关闭 `capture_preview` 时立即停止采集并删除已有预览。
    - 重置、删除 Profile 时清除预览。
    - 新的 runtime 实例不接受旧实例的迟到写入。
- 隐私：截图视同 Cookie 级私密数据，内容与路径不进日志、错误与事件。
- OpenAPI 与前端类型同步。

### 非范围

- X11 截图或视频流抽帧。
- 历史缩略图或时间线。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：running 且策略允许的 Profile 约每 15 秒产生一帧宽 480px 的 JPEG 预览，内容为当前活动标签页的网页区域，不含浏览器标签栏与地址栏（真实栈 E2E 以已知页面内容比对）。
- [x] AC-002：预览接口未登录时拒绝；有预览时返回 `image/jpeg`、`Cache-Control: no-store` 与基于 `captured_at` 的 ETag；无预览或策略已撤销时返回 404。
- [x] AC-003：runtime 响应含 `preview_captured_at`，没有预览时为 null，卡片直接显示占位而不请求图片；每产生一帧新预览，SSE 下发 `profile_preview`，卡片据此刷新。`profile_preview` 不进入重放环，SSE 重连后的 runtime 状态重放不受缩略图事件数量影响。
- [x] AC-004：运行中关闭 `capture_preview` 后，不需要重启或应用配置即停止采集，已有预览被删除且接口返回 404。以下情况的迟到写入均被丢弃，不会重新出现预览：关闭时截图正在进行；旧代次的通知延迟到达；重置后旧实例回传（集成测试注入时序）。
- [x] AC-005：Profile 停止后保留最后一帧；重置或删除 Profile 后预览被清除；「含浏览器状态」的复制不复制预览。
- [x] AC-006：预览文件权限为 0600；截图内容与文件路径不出现在日志、错误响应与事件中。
- [x] AC-007：截图前后页面的 `document.visibilityState`、焦点与活动标签页不变（真实栈 E2E 断言）。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：`docs/plan_20261105_ui_redesign.md` WP13 与第 6.7 节（2026-11-05 于 main@3101540 核实，结论见背景）；即时撤销策略、存储挂载、SSE 重放隔离与 `preview_captured_at` 按 2026-11-05 外部审阅补全。

### 有意不测

- 无。

### 测试策略

- unit 覆盖采集调度、原子写入与权限、策略代次校验。
- integration 覆盖策略下发、Supervisor 通知、SSE 事件与重放环隔离，并注入三类迟到写入时序。
- 真实栈 E2E 验证截图内容区域与对页面行为无影响。
- 所有浏览器测试无头运行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- CDP 没有直接的「当前活动标签页」字段；在 CloakBrowser 146 / Xvfb 下识别活动标签页的方法，以及 `Page.captureScreenshot` 对后台标签页、焦点和页面可见性的影响：**已验证（s016 / d035）**。CDP `Target.getTargets` 无 active 字段、页面 visibility/focus 在多标签下恒真，活动标签须由产品自维护（Agent 记录激活 target 或外部焦点 `client_tab_id` 映射）；`Page.captureScreenshot` 对前台/后台页均返回有效 JPEG 且截图前后可见性、焦点、页面事件与 target 列表不变，只截 viewport。验证方式：`docs/spikes/s016_cdp_active_tab_capture_probe/report.md` 与 `code/result_headless.json` / `code/result_xvfb.json`，真实 Chromium 146 引擎在 headless 与容器 Xvfb 两组实测；依据 `docs/findings/d035_cdp_active_tab_capture_screenshot.md`。

### 风险与回退

- 风险：截图触发页面可见性或焦点变化，成为可被网站观测的自动化特征；撤销后迟到写入让预览重新出现。
- 回退：回退本 task commit；采集可按 Profile 关闭。

### 依赖与约束

- 依赖 t037（卡片视图）；经 t037 间接依赖 t035。
- 与 t038、t039 同改前端共享文件，用 `conflicts_with` 串行。
- 所有浏览器测试无头运行。

### Finalization 时更新的 blueprint

- `docs/blueprint/browser_runtime.md`：缩略图采集与策略代次。
- `docs/blueprint/supervisor.md`：预览目录挂载、策略下发与变化通知。
- `docs/blueprint/security.md`：预览隐私与撤销语义。
- `docs/blueprint/frontend.md`：SSE 按事件类型分发。
- 新建 `docs/specs/profile_preview.md`。
