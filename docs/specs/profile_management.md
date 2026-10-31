# 需求规范：Profile 管理与外部标签页

本文描述 t007 交付的 v2 前端 Profile 管理、页面独立选择与运行意愿行为，取代旧 `chrome_external_tabs`（控制租约模型已废弃，见 docs/archive/specs/）。文件/自动化页面由 t008、复制/重置由 t013 补充；生效状态以 specs_index 为准。

## 登录与入口

- 未登录访问任何应用页面跳转 `/login` 并保留原目标（含 `?profileId=`），登录后回到原目标；目标只接受同源相对路径。使用中会话失效（API 401）同样回到登录页。
- 运行状态推送（SSE）只在已登录时运行。

## Profile 列表与编辑

- Profile 列表、创建、编辑（名称、屏幕尺寸、标签）与设置均通过 `/api/v1` 完成，前端类型由 OpenAPI 生成。
- 运行状态由服务端 SSE 推送，断线自动重连；前端不保存控制状态，重连后以服务端状态为准。

## 页面独立选择

- 主界面以 `/?profileId=` 表示当前页面的操控目标，刷新恢复该目标。每个 Chrome 标签页独立切换 Profile，不改变其他标签页的目标或连接；不使用跨标签页共享的 `localStorage.currentProfileId`。
- 同一 Profile 可在多个标签页同时打开，均可输入、各自独立静音；不存在租约、接管或唯一控制者。新标签页以 `noopener` 打开。
- 关闭、刷新或切换页面只关闭本页连接，不停止 Profile；只有用户明确停止才关闭真实浏览器。

## 运行意愿

- 启动/停止只经 `/api/v1` 设置运行意愿，由 API 驱动 Supervisor 真实启停该 Profile 的 Browser/Stream。
- Supervisor 不可达时意愿保留，页面显式显示运行协调错误；恢复后自动收敛并清除错误。
- 运行时未就绪时会话页显示“运行时未就绪”与启动操作，而不是空白画面。
- 运行中修改屏幕尺寸只保存配置，页面显示“设置已保存，重启后生效”；用户点击“应用并重启”后才以新尺寸运行。

## 验收与边界

由 t007 真实栈 E2E（构建产物 + Caddy/API/Supervisor/Gateway/coturn/Browser/Stream + 无头 Google Chrome 双标签页）与 Vitest 验证。公网与原生 Linux x86_64 执行按用户豁免记 NOT_RUN / USER_WAIVED。
