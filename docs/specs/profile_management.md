# 需求规范：Profile 管理与外部标签页

本文描述 t007 交付的 v2 前端 Profile 管理、页面独立选择与运行意愿行为，取代旧 `chrome_external_tabs`（控制租约模型已废弃，见 docs/archive/specs/）。文件/自动化页面由 t008、复制/重置由 t013 补充；生效状态以 specs_index 为准。

## 登录与入口

- 未登录访问任何应用页面跳转 `/login` 并保留原目标（含 `?profileId=`），登录后回到原目标；目标只接受同源相对路径。使用中会话失效（API 401）同样回到登录页。
- 运行状态推送（SSE）只在已登录时运行。

## Profile 列表与编辑

- Profile 列表、创建、编辑（名称、屏幕尺寸、标签）与设置均通过 `/api/v1` 完成，前端类型由 OpenAPI 生成。
- 运行状态由服务端 SSE 推送，断线自动重连；前端不保存控制状态，重连后以服务端状态为准。

## 中文字体包（t020）

- Profile 配置含 `font_bundle`，取值 `none`、`wqy-microhei`、`wqy-zenhei`，默认 `none`；创建、更新、读取与配置版本快照均携带该字段，非法值与显式 null 被拒绝，存量 Profile 迁移后读为 `none`。
- Browser 镜像把文泉驿微米黑与正黑的 `.ttc` staged 在 fontconfig 默认扫描路径之外的 `/opt/cbrowser-fonts/{wqy-microhei,wqy-zenhei}`；默认容器内 `sans-serif` 的中文解析不命中任何中文字体。
- Browser Runner 按快照中的 `font_bundle` 生成 Profile 专属 fontconfig 配置（include 系统配置并追加对应 bundle 目录），仅对非 `none` 档位为 Chrome 进程设置 `FONTCONFIG_FILE`；生成失败时不设置该变量、保持系统默认配置。修改 `font_bundle` 产生新配置版本，重建容器后生效，不影响其他 Profile。
- 前端创建与编辑界面提供三档选择并回显 API 返回值；不提供 Windows 专有字体，不挂载宿主字体目录。

## 启动参数校验与 PATCH 三态（t021）

- 更新 DTO 对 `launch_args` / `extension_paths` 只做严格校验（条数、单条长度、危险参数拒绝），不再在校验阶段过滤合法条目；历史行读取时的过滤保持不变。
- PATCH 语义三态：字段缺失 = 不变；显式 `null` = 清空为 `[]`；给出列表 = 整体替换。`ProfileConfig` 把显式 null 的这两个列表归一为 `[]`，仓储合并不得因此 500；越界内容返回 422。

## 页面独立选择

- 主界面以 `/?profileId=` 表示当前页面的操控目标，刷新恢复该目标。每个 Chrome 标签页独立切换 Profile，不改变其他标签页的目标或连接；不使用跨标签页共享的 `localStorage.currentProfileId`。
- 同一 Profile 可在多个标签页同时打开，均可输入、各自独立静音；不存在租约、接管或唯一控制者。新标签页以 `noopener` 打开。
- 关闭、刷新或切换页面只关闭本页连接，不停止 Profile；只有用户明确停止才关闭真实浏览器。

## 运行意愿

- 启动/停止只经 `/api/v1` 设置运行意愿，由 API 驱动 Supervisor 真实启停该 Profile 的 Browser/Stream。
- Supervisor 不可达时意愿保留，页面显式显示运行协调错误；恢复后自动收敛并清除错误。
- 运行时未就绪时会话页显示“运行时未就绪”与启动操作，而不是空白画面。
- 运行中修改屏幕尺寸只保存配置，页面显示“设置已保存，重启后生效”；用户点击“应用并重启”后才以新尺寸运行。

## 复制与重置

- 配置复制：`POST /api/v1/profiles/{id}/duplicate`（`include_browser_state=false`）创建新 Profile 与配置版本，保留全部有效配置字段、分组与代理引用及同一指纹种子；不复制浏览器用户数据和 Artifact，源 Profile 不变。
- 状态复制：同一接口 `include_browser_state=true` 仅在源 `desired_state` 与 `observed_state` 均为 stopped 时执行；复制用户数据目录（跳过 SingletonLock/Cookie/Socket），逐文件校验后创建新 Profile。源运行中返回 409，前端引导停止；Artifact 不复制。
- 重置：`POST /api/v1/profiles/{id}/reset` 要求显式 `confirm=true`，且源已停止；将用户数据目录移动到备份、更新指纹种子并生成新配置版本，成功后删除备份，失败恢复原目录。保留设置、分组与代理引用、备注与 Artifact，不影响其他 Profile。
- 重复请求使用 `Idempotency-Key` 返回同一结果；并发状态复制或源启动通过停止检查与复制后复检拒绝，不发布半复制目录。
- 前端 Profile 详情页提供复制（仅配置/含状态）与重置确认面板，重置明确列出将清除的浏览器数据。

## 验收与边界

由 t007 真实栈 E2E（构建产物 + Caddy/API/Supervisor/Gateway/Browser/Stream + 无头 Google Chrome 双标签页，无 coturn）与 Vitest 验证。公网与原生 Linux x86_64 执行按用户豁免记 NOT_RUN / USER_WAIVED。

## 会话动作隔离与应用阶段语义（t025）

- 会话页、页头与 Profile 详情页的动作状态（error/pending）按动作目标 Profile 隔离呈现：停留在组件实例上的共享 mutation 状态只在目标与当前查看的 Profile 一致时显示；切换到其他 Profile 不显示前一 Profile 的错误（含页头 `display-apply-error` 条）、不被其 pending 禁用，前一 Profile 的迟到响应不污染当前视图；详情页本地结果横幅（保存成功/失败）与处理器的后续导航/表单清理同样按发起 Profile 守卫，迟到结算不写入已切换到的 Profile。
- “应用并重启”是带阶段的逻辑动作：阶段与 stop 前的 runtime_instance_id 跨自动重试保存，重试先观测当前运行时再续跑——stop 已生效则不再等待已完成阶段；start 已在服务端生效而响应丢失时，识别 desired=running 的新实例并收敛到 running，不等待 stopped、不停止或重建新实例；「新实例」的认定在新旧实例 id 均已知时要求二者不同（同 id 的 running 视为旧实例被外部恢复，仍走完整 stop/start），任一 id 未知时回退 desired/observed 判定；stop/start 未生效时以同一操作键安全续跑，状态查询持续失败时有界报错。

## 前端请求与文案一致性（t023）

- 前端写操作的 `Idempotency-Key` 在每次调用边界生成：同一逻辑动作的自动重试复用同一键，并发或先后发生的独立动作必须使用不同键；复合动作（如应用显示设置的 stop→start）由单次动作键派生各步操作键。请求取消与超时可区分：外部取消不可重试，内部超时可重试。
- 页面与布局经应用上下文下发的 ApiClient 实例工作；页面流程测试在 ApiClient 边界注入独立桩并走真实数据 hooks，不 mock hooks 模块、不改共享单例。
- 界面文案键集以 en 字典为唯一来源派生，zh 字典编译期对齐同一键集；设置页健康状态只声称其真实探测的 Control API 状态。

## 分组库、代理库与配置版本三分（t035）

- Profile 请求与响应不再含 `tags` / `proxy`；导出 OpenAPI 按资源分组，不含 `v1` 分组（AC-012）。业务 Tag 概念从仓库移除。
- 分组：CRUD 与排序可用；名称重复、超长或颜色不在调色板内被拒绝；删除分组后原引用 Profile 的 `group_id` 变 null；创建与 PATCH 可设置或清除 `group_id`，引用不存在的分组被拒绝。
- 代理：CRUD 可用，协议/host/端口按规则校验、名称唯一；响应含 `has_password` 与 `used_by_count`，`password` 不出现在代理/Profile/配置版本/错误响应/SSE/日志，也不进配置版本快照。PATCH `password` 三态：缺失=不变、null=清除、字符串=设置（同时递增 `credential_revision`）。
- 代理被任一 Profile 的当前配置或 runtime 绑定版本引用时，删除返回 409 `proxy_in_use` 并附引用数量，代理与引用关系不变。
- 配置版本三分：只改元数据、只改 `capture_preview`、或提交与当前值相同的运行配置都不生成新版本，运行中 Profile 不出现待应用；修改代理连接字段时在同一事务内为每个引用 Profile 生成新版本并广播 SSE；只改代理名称/地区/备注不生成。
- 带认证 SOCKS5 按 spike `s013` 结论处理：Chromium 146 支持时端到端经代理出站；代理密码在 Profile 绑定版本之后被修改时，按旧版本重启失败封闭并报告 `proxy_credentials_changed`，应用新版本后启动成功。
- runtime 响应与 SSE 携带 `last_started_at` / `last_stopped_at` / `browser_product` / `browser_user_agent`；前端校验拒绝非法时间值。运行中 Profile 的浏览器版本字段与容器内 CDP `Browser.getVersion` 一致，未运行时为 null。
- 运行态或仍绑定实例的 Profile 删除返回 409 `profile_running`；error 且无实例可删除，删除成功后 DB 行、Artifact 与全部 Profile 专属目录都不存在。
- 迁移目录只有一个 baseline 修订；旧 schema 代的 DB 在 API 启动与部署时失败封闭并输出重建指引，release controller 按修订链判定回退下限（ADR 023）。
