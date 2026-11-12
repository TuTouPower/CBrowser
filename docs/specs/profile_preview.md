# 需求规范：环境实时缩略图 (profile_preview)

需求级 spec，累积 t040 / t057。契约来源 `docs/archive/plans/plan_20261105_ui_redesign.md` 第 6.7 节 / WP13，关联 task `docs/archive/tasks/t040_environment_preview_thumbnails/task.md`（AC-001~007）。交互与视觉约束见 `DESIGN.md` 与 `docs/blueprint/frontend.md`，采集与隔离见 `docs/blueprint/browser_runtime.md` / `supervisor.md` / `security.md`。CDP 行为依据 spike `docs/spikes/s016_cdp_active_tab_capture_probe/report.md` 与 finding `docs/findings/d035_cdp_active_tab_capture_screenshot.md`。

## 1. 范围

- 运行中且策略允许的 Profile 每约 15 秒产生一帧该Profile容器内整张浏览器画面的缩略图（包含标签栏、地址栏），供环境卡片等比完整展示；不同比例留白，不裁掉浏览器界面；经独立Xvfb显示采集，不读取宿主桌面。
- 覆盖即时策略授权、采集、独立存储、变化通知、鉴权读取、SSE 按事件类型分发、撤销清除与隐私边界。
- 非范围：视频流抽帧、宿主桌面截图、历史缩略图与时间线、未经授权的预览读取。
- `capture_preview` 不进入 `ProfileConfigVersion`，不触发重启或应用配置。

## 2. 策略与代次

- `capture_preview` 是即时策略；API 是权威，持久化策略并维护递增代次。`ProfileModel.capture_preview_epoch` 每次 PATCH 变化 +1，只作 DB 内部代次，不暴露到 `ProfileResponse` 或前端。
- 共享模块 `src/backend/cbrowser/preview.py` 定义 `PreviewPolicy(enabled, epoch, runtime_instance_id)` 与 `PreviewMeta(captured_at, runtime_instance_id, policy_epoch, image_sha256)`。
- 采集、落盘、通知、读取四环节都校验策略代次与 runtime 实例，任一不一致即丢弃并清理残留文件；迟到写入（关闭时截图进行中、旧代次通知迟到、reset 后旧实例回传）不会让预览重新出现。
- `commit_preview` 落盘前重读 policy 校验 enabled / epoch / instance，不一致即拒绝，不删除其它已发布的新帧；`read_preview`在同一帧快照上校验代次、实例及摘要。
- 策略变化经 Supervisor 即时下发给运行中的 Agent：API PATCH → 本地写 policy（关闭时清预览）→ `RuntimeCoordinator.request_preview_policy` POST `/supervisor/v1/profiles/{id}/preview-policy`（`PreviewPolicySyncRequest`，带 request_id）→ Supervisor `apply_preview_policy` 写 policy 并经 Agent UDS `/control` 以 `action=preview_policy` 下发；runtime_instance_id + request_id 双重围栏丢弃旧实例与重复请求，不重启、不应用配置。

## 3. 采集 / 存储 / 通知 / 读取

### 3.1 采集

- Runtime Agent `PreviewCaptureLoop` 每15秒采集该Profile独立Xvfb的完整显示画面，通过Pillow/XCB读取，包含浏览器标签栏、地址栏和当前可见页面。只接受显式容器display，禁止宿主截图或外部命令回退；浏览器未就绪时不采集。
- 缩放为480px宽、保持整张画面宽高比，JPEG质量70；落盘前用Pillow检查JPEG格式/尺寸并完整解码，再通过jpeginfo `--check -`拒绝码流解码警告（stdin传字节、输出丢弃、2秒超时，缺工具失败封闭），损坏/截断/尺寸不符丢弃，纯色合法帧接受。截图不激活标签或改变焦点。独立Agent启动时读取Runner的Profile专属Xauthority，在截图线程启动前设置认证环境，不放开X服务器访问控制。
- 2026-11-12用户明确裁定整张浏览器画面，覆盖t040旧网页viewport限定；d035/s016与d038的CDP实验保留历史事实，不再作为生产截图选页方案。

### 3.2 存储

- `data_root/profiles/{id}/preview/` 下 `policy.json` / `frame_<timestamp_key>_<image_sha256>.jpg` / `meta.json` 全部 0600 原子写。
- API 数据根由 `CBROWSER_DB_PATH` 的父目录**单一派生**（生产 compose 为 `/data/cbrowser.db` → `/data`，artifacts 与 preview 同源）；E2E harness 与生产拓扑一致，`data_dir` 挂 `/data`，不为 preview 单开配置变量。
- 该目录独立挂载进 Browser 容器 `/data/preview`，不进入 `/data/profiles/{id}/profile`（user data dir），因此「含浏览器状态」复制不带走预览（AC-005）。

|文件|内容|
|---|---|
|policy.json|`PreviewPolicy`：enabled / epoch / runtime_instance_id|
|frame\_\*.jpg|最新一帧 JPEG|
|meta.json|`PreviewMeta`：captured_at / runtime_instance_id / policy_epoch / image_sha256（原子指针）|

帧以captured_at哈希与JPEG SHA256命名，同名内容相同；先写完整帧，再原子替换meta指针。原子写暂存名采用uuid并以O_EXCL创建，0600、fsync后替换，只清理自身暂存文件。发布、清除、回收在同一目录inode锁内串行化，仅协调同一Linux虚拟机的生产容器（见d039）；策略原子写独立进行，锁不代替epoch/实例围栏。metadata失败回收本次未发布帧，但保留已被当前metadata选中的同名帧；成功/失败提交均回收超过保留期的未选中JPEG（包含旧格式遗留）。旧帧保留至少60秒后回收，撤销/reset/delete立即清除全部帧与meta。读取只读一次meta，先打开选定帧并读取同一描述符，再校验摘要、生成ETag并返回同一字节快照；并发清除/替换不串帧。

### 3.3 通知与首屏

- Agent `/health` 的 details 携带 `preview_captured_at`；Supervisor 观测到变化且校验 `meta.policy_epoch == policy.epoch` 与 instance 匹配后，POST API 内部端点 `/api/v1/internal/supervisor/profiles/{id}/preview`（`PreviewObservedRequest`）。
- API `record_preview_capture` 校验capture_preview开启、代次与实例，失败丢弃并清预览；`publish_profile_preview` 经 `RuntimeEventBroadcaster.publish_transient` **只实时扇出 `event: profile_preview` 帧，绝不进重放环**（AC-003：SSE 重连后的 runtime 状态重放不受缩略图事件数量影响）。不复用 Artifact 的事件文件 + 游标模式。
- `ProfileRuntimeResponse.preview_captured_at`（无预览为 null）供首屏决定显示图片或占位；前端仅在缓存明确允许capture_preview时接受时间严格递增的captured_at（按时间点比较，支持时区偏移），缓存缺失、任一已缓存开关为关闭、无效时间及旧事件均丢弃。`shared/api/sse.ts` 解析 `event:` 行按类型分发（`runtime_state` 走原通道、`profile_preview` 走 `onPreviewEvent`），`useProfilesQuery.ts` 订阅 preview 事件刷新 runtime 缓存，`EnvironmentCard` 以 `?v=<captured_at>` 作为图片 URL 版本参数，404 / onError 回退占位；**无值不请求图片**。

### 3.4 读取

- `GET /api/v1/profiles/{id}/preview` 需登录会话，返回 `image/jpeg` + `Cache-Control: no-store` + ETag（`captured_at:image_sha256`），条件请求 304（AC-002）。
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

- 截图视同 Cookie 级私密数据：`frame_<timestamp_key>_<image_sha256>.jpg` 内容与预览目录路径不进日志、错误响应与事件，日志只记 error_type / 计数（AC-006）。
- 预览文件 0600 原子写、独立挂载、跨 Profile 归属校验；读取端点鉴权且 `no-store`，404 错误体不含路径与截图内容。

## 6. AC 映射

完整 AC 与可测试性声明见关联 task `t040` / `t057`；本 spec 只作需求级累积。

|AC|本文契约|摘要|
|---|---|---|
|AC-001|3.1 / 3.2|running 且策略允许约 15 秒一帧 480px JPEG，整张浏览器画面，包含标签栏 / 地址栏，不采宿主桌面|
|AC-002|3.4|预览接口鉴权、`image/jpeg` + `no-store` + ETag，无预览 / 撤销 404|
|AC-003|3.3|`preview_captured_at` 首屏占位、`profile_preview` SSE 刷新、不进重放环|
|AC-004|2 / 4|关闭即时停止并删除预览，三类迟到写入丢弃|
|AC-005|3.2 / 4|停止保留最后一帧、reset / delete 清除、状态复制不复制预览|
|AC-006|5|0600 权限，内容与路径不进日志 / 错误 / 事件|
|AC-007|3.1|截图前后 visibilityState、焦点与活动标签不变|

## 7. 依据

- `docs/spikes/s016_cdp_active_tab_capture_probe/report.md`：真实 Chromium 146 引擎 headless 与容器 Xvfb 两组实测，`Target.getTargets` 无 active 字段、`Page.captureScreenshot` 对可见性 / 焦点 / 活动标签无影响、只截 viewport。
- `docs/findings/d035_cdp_active_tab_capture_screenshot.md`：活动标签须产品自维护、截图无副作用、480px 缩放与 JPEG q70 由产品侧处理。Chromium 主版本升级或改用真实宿主窗口时重跑 s016 复核。

### t057完整性与隐私验收

|AC|行为|
|---|---|
|AC-001|预览关闭时，无论epoch是否变化均拒绝通知，不改时间戳/不发SSE|
|AC-002|Supervisor仅在校验及API上报成功后缓存去重；失败warning限频30秒且同帧可重试|
|AC-003|Coordinator pending保存首次request_id，重试复用、成功比较后删除，旧成功不删新策略|
|AC-004|返回字节与ETag来自同一已打开帧|
|AC-005|进程/线程间唯一暂存文件与独占创建，失败不删除他人暂存|
|AC-006|整张浏览器画面包含界面与实际前台页面，不采宿主桌面|
|AC-007|JPEG完整解码/尺寸检查拒绝损坏帧，合法纯色帧通过|
|AC-008|SSE受缓存开关与captured_at严格单调围栏约束|
