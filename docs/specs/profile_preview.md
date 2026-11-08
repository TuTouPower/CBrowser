# 需求规范：环境实时缩略图 (profile_preview)

需求级 spec，累积 t040。契约来源 `docs/plan_20261105_ui_redesign.md` 第 6.7 节 / WP13，关联 task `docs/tasks/t040_environment_preview_thumbnails/task.md`（AC-001~007）。交互与视觉约束见 `DESIGN.md` 与 `docs/blueprint/frontend.md`，采集与隔离见 `docs/blueprint/browser_runtime.md` / `supervisor.md` / `security.md`。CDP 行为依据 spike `docs/spikes/s016_cdp_active_tab_capture_probe/report.md` 与 finding `docs/findings/d035_cdp_active_tab_capture_screenshot.md`。

## 1. 范围

- 运行中且策略允许的 Profile 每约 15 秒产生一帧当前活动标签页网页区域的缩略图，供环境卡片展示；经 CDP 采集，在 Docker 与将来的独立桌面应用中都可用。
- 覆盖即时策略授权、采集、独立存储、变化通知、鉴权读取、SSE 按事件类型分发、撤销清除与隐私边界。
- 非范围：X11 截图或视频流抽帧、历史缩略图与时间线、未经授权的预览读取。
- `capture_preview` 不进入 `ProfileConfigVersion`，不触发重启或应用配置。

## 2. 策略与代次

- `capture_preview` 是即时策略；API 是权威，持久化策略并维护递增代次。`ProfileModel.capture_preview_epoch` 每次 PATCH 变化 +1，只作 DB 内部代次，不暴露到 `ProfileResponse` 或前端。
- 共享模块 `src/backend/cbrowser/preview.py` 定义 `PreviewPolicy(enabled, epoch, runtime_instance_id)` 与 `PreviewMeta(captured_at, runtime_instance_id, policy_epoch)`。
- 采集、落盘、通知、读取四环节都校验策略代次与 runtime 实例，任一不一致即丢弃并清理残留文件；迟到写入（关闭时截图进行中、旧代次通知迟到、reset 后旧实例回传）不会让预览重新出现。
- `commit_preview` 落盘前重读 policy 校验 enabled / epoch / instance，不一致清理并返回 False；`is_current_preview` 供读取端点做同等校验。
- 策略变化经 Supervisor 即时下发给运行中的 Agent：API PATCH → 本地写 policy（关闭时清预览）→ `RuntimeCoordinator.request_preview_policy` POST `/supervisor/v1/profiles/{id}/preview-policy`（`PreviewPolicySyncRequest`，带 request_id）→ Supervisor `apply_preview_policy` 写 policy 并经 Agent UDS `/control` 以 `action=preview_policy` 下发；runtime_instance_id + request_id 双重围栏丢弃旧实例与重复请求，不重启、不应用配置。

## 3. 采集 / 存储 / 通知 / 读取

### 3.1 采集

- Runtime Agent `PreviewCaptureLoop` 每 15 秒（`CAPTURE_INTERVAL_SEC`）采一帧，经已有 CDP 连接：`Target.getTargets` 枚举 page target 取首个，`Target.attachToTarget` → `Page.getLayoutMetrics` → `Page.captureScreenshot`，`clip.scale=480/viewport_width`、JPEG 质量 70，只截 viewport 网页区域，不含浏览器标签栏与地址栏（AC-001）。
- CDP 无 active 字段、页面可见性与焦点在多标签下恒真，活动标签由产品自维护（s016 / d035）；采集**不调用** `Page.bringToFront` / `Target.activateTarget`，截图前后 `document.visibilityState`、焦点与活动标签不变（AC-007）。

### 3.2 存储

- `data_root/profiles/{id}/preview/` 下 `policy.json` / `latest.jpg` / `meta.json` 全部 0600 原子写。
- API 数据根由 `CBROWSER_DB_PATH` 的父目录**单一派生**（生产 compose 为 `/data/cbrowser.db` → `/data`，artifacts 与 preview 同源）；E2E harness 与生产拓扑一致，`data_dir` 挂 `/data`，不为 preview 单开配置变量。
- 该目录独立挂载进 Browser 容器 `/data/preview`，不进入 `/data/profiles/{id}/profile`（user data dir），因此「含浏览器状态」复制不带走预览（AC-005）。

|文件|内容|
|---|---|
|policy.json|`PreviewPolicy`：enabled / epoch / runtime_instance_id|
|latest.jpg|最新一帧 JPEG|
|meta.json|`PreviewMeta`：captured_at / runtime_instance_id / policy_epoch|

### 3.3 通知与首屏

- Agent `/health` 的 details 携带 `preview_captured_at`；Supervisor 观测到变化且校验 `meta.policy_epoch == policy.epoch` 与 instance 匹配后，POST API 内部端点 `/api/v1/internal/supervisor/profiles/{id}/preview`（`PreviewObservedRequest`）。
- API `record_preview_capture` 校验代次与实例，失败丢弃并清预览；`publish_profile_preview` 经 `RuntimeEventBroadcaster.publish_transient` **只实时扇出 `event: profile_preview` 帧，绝不进重放环**（AC-003：SSE 重连后的 runtime 状态重放不受缩略图事件数量影响）。不复用 Artifact 的事件文件 + 游标模式。
- `ProfileRuntimeResponse.preview_captured_at`（无预览为 null）供首屏决定显示图片或占位；前端 `shared/api/sse.ts` 解析 `event:` 行按类型分发（`runtime_state` 走原通道、`profile_preview` 走 `onPreviewEvent`），`useProfilesQuery.ts` 订阅 preview 事件刷新 runtime 缓存，`EnvironmentCard` 以 `?v=<captured_at>` 作为图片 URL 版本参数，404 / onError 回退占位；**无值不请求图片**。

### 3.4 读取

- `GET /api/v1/profiles/{id}/preview` 需登录会话，返回 `image/jpeg` + `Cache-Control: no-store` + ETag（`captured_at`），条件请求 304（AC-002）。
- 无预览、策略已撤销或代次 / 实例不符 → 404，错误体不含路径与截图内容。

## 4. 撤销与清除

|动作|结果|
|---|---|
|关闭 `capture_preview`|即时停止采集、删除已有预览、接口 404，不重启不应用配置|
|Profile 停止|保留最后一帧|
|reset / delete|清除预览目录与 `preview_captured_at`|
|「含浏览器状态」复制|不复制预览|

- 所有迟到写入由策略代次 + runtime 实例围栏丢弃，撤销 / 重置后预览不会重新出现（AC-004）。

## 5. 隐私

- 截图视同 Cookie 级私密数据：`latest.jpg` 内容与预览目录路径不进日志、错误响应与事件，日志只记 error_type / 计数（AC-006）。
- 预览文件 0600 原子写、独立挂载、跨 Profile 归属校验；读取端点鉴权且 `no-store`，404 错误体不含路径与截图内容。

## 6. AC 映射

完整 AC 与可测试性声明见关联 task `t040`；本 spec 只作需求级累积。

|AC|本文契约|摘要|
|---|---|---|
|AC-001|3.1 / 3.2|running 且策略允许约 15 秒一帧 480px JPEG，只截活动标签页 viewport，不含标签栏 / 地址栏|
|AC-002|3.4|预览接口鉴权、`image/jpeg` + `no-store` + ETag，无预览 / 撤销 404|
|AC-003|3.3|`preview_captured_at` 首屏占位、`profile_preview` SSE 刷新、不进重放环|
|AC-004|2 / 4|关闭即时停止并删除预览，三类迟到写入丢弃|
|AC-005|3.2 / 4|停止保留最后一帧、reset / delete 清除、状态复制不复制预览|
|AC-006|5|0600 权限，内容与路径不进日志 / 错误 / 事件|
|AC-007|3.1|截图前后 visibilityState、焦点与活动标签不变|

## 7. 依据

- `docs/spikes/s016_cdp_active_tab_capture_probe/report.md`：真实 Chromium 146 引擎 headless 与容器 Xvfb 两组实测，`Target.getTargets` 无 active 字段、`Page.captureScreenshot` 对可见性 / 焦点 / 活动标签无影响、只截 viewport。
- `docs/findings/d035_cdp_active_tab_capture_screenshot.md`：活动标签须产品自维护、截图无副作用、480px 缩放与 JPEG q70 由产品侧处理。Chromium 主版本升级或改用真实宿主窗口时重跑 s016 复核。
