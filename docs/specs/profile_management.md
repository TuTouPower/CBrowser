# 需求规范：Profile 管理与外部标签页

本文描述 t007 交付的前端 Profile 管理、页面独立选择与运行意愿行为，取代旧 `chrome_external_tabs`（控制租约模型已废弃，见 docs/archive/specs/）。文件/自动化页面由 t008、复制/重置由 t013 补充；生效状态以 specs_index 为准。

## 登录与入口

- 未登录访问任何应用页面跳转 `/login` 并保留原目标（含 `?profileId=`），登录后回到原目标；目标只接受同源相对路径。使用中会话失效（API 401）同样回到登录页。
- 运行状态推送（SSE）只在已登录时运行。

## Profile 列表与编辑

- Profile 列表、创建、编辑（名称、屏幕尺寸、标签）与设置均通过 `/api/v1` 完成，前端类型由 OpenAPI 生成。
- 运行状态由服务端 SSE 推送，断线自动重连；前端不保存控制状态，重连后以服务端状态为准。

## 启动参数校验与 PATCH 三态（t021）

- 更新 DTO 对 `launch_args` / `extension_paths` 只做严格校验（条数、单条长度、危险参数拒绝），不再在校验阶段过滤合法条目；历史行读取同样严格（t069）：存量 `launch_args` 不合法时加载即拒绝并指名 Profile，不再静默过滤。
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
- 迁移目录以 t035 单 baseline 修订为起点，t041 追加增量迁移 `0002_fingerprint_platform.py`（新增 `fingerprint_platform` / `font_set_id`、删除 `font_bundle`）；旧 schema 代的 DB 在 API 启动与部署时失败封闭并输出重建指引，release controller 按修订链判定回退下限（ADR 023）。

## 指纹平台与平台字体集（t041）

- Profile 运行配置新增 `fingerprint_platform`（`windows` 默认 / `macos`）与 `font_set_id`（引用同平台不可变字体集，可为 null），经增量迁移 `0002_fingerprint_platform.py` 加入；两者属运行配置，修改任一都生成新 `ProfileConfigVersion`（AC-003）。
- `font_set_id` 必须引用已存在且平台一致的字体集，引用不存在或平台不一致的集被拒绝；新建 Profile 默认使用后端按完整性规则给出的默认集（`GET /api/v1/font-sets` 的 `default_font_set_id[platform]`，只取完整性通过的集，其中最新导入的胜出，无可用集时为 null），前端不再自行按创建时间推导（t053 A16）。
- `font_bundle`（文泉驿三档）已删除：字段、镜像字体包、代码、文档与测试引用一并清理（AC-009）。
- runtime 响应与 SSE 下发实际使用的 `font_set_id` 与 `missing_fonts`；绑定字体集缺失或 manifest / 文件不一致时启动失败封闭 `font_set_unavailable`，`font_set_id` 为 null 时正常启动并报告平台字体未配置（AC-006 / AC-007）。

## 语言、时区与高级选项默认值（t053）

- 新建 Profile 默认值：`humanize` 与 `portable_cookies` 开启；`transparent_proxy` 与 `auto_launch` 关闭；`allow_3p_cookies` / `set_google_default` / `clipboard_sync` / `restore_session` / `capture_preview` 开启。前后端与 ORM 默认值一致，OpenAPI 与前端类型重新生成；既有 Profile 的已存值在升级后不变。
- 语言只支持 `zh-CN` / `en-US`（新建默认 `en-US`），后端校验拒绝其它值与非法时区，返回字段级错误；时区为空表示自动（随出口 IP）。
- 时区 → 语言：中文地区时区（`Asia/Shanghai`、`Asia/Chongqing`、`Asia/Urumqi`、`Asia/Harbin`、`Asia/Hong_Kong`、`Asia/Macau`、`Asia/Taipei`）→ `zh-CN`，其余 → `en-US`；时区为空时语言保持当前值。
- 前端时区选择为组合框：可键入过滤候选、未键入时可展开并滚动浏览全部 IANA 时区、键盘可操作、常用时区置顶；选时区后语言自动联动，用户可手动切换语言后保存。
- 语言变更生成新配置版本，重启后生效。
- 字体集「无」为显式选项，提交显式 null，后端按显式 null 保存；绑定字体集时 fontconfig 生成失败即启动失败 `font_set_unavailable`，不回落系统配置；字体集文件被删除或篡改后重新导入可恢复完整性，字体集缺失或损坏时 REST 与 SSE 立即报告缺失，无需重启 API；同一 `set_id` 在 windows 与 macos 下的引用数各自独立，manifest 平台与目录不一致的条目显示为完整性失败；字体集完整但未覆盖部分探测字体时，会话详情显示「探测字体未覆盖」而非完整性损坏。

## 环境管理界面（t037）

- 首页 `/` 为环境列表：8 列（选择 / 名称 / 分组 / 网络 / 指纹 / 状态 / 最后活跃 / 操作）与卡片视图；工具栏含搜索（名称、备注、代理名）、状态筛选（全部、运行中、已停止、异常）、分组筛选（全部、未分组、各分组、底部「管理分组…」）、代理筛选、排序（手动顺序、名称、最近活跃、创建时间）、列表/卡片切换（存 `cbrowser.environments.layout`）、新建环境主按钮。筛选与排序状态写入 URL 查询参数并可由 URL 还原；筛选无结果提供「清除筛选」。无预览时卡片缩略图位显示占位（内容由 t040 交付）。
- 无代理时网络列显示带警示样式的「直连」（真实 IP 暴露）；`geoip` 开启时指纹列显示「随代理」；状态为带文字的五态徽标（starting / stopping / running / error / stopped），error 悬停显示原因；最后活跃列运行中显示已运行时长，否则显示距最后停止的相对时间。
- SSE `runtime_state` 增量合并后行状态、可用操作与运行中数量实时更新，无需刷新页面。
- 批量启动、停止、移动到分组、删除逐项调用单项 API，每项独立幂等键；结束 toast 汇总成功与失败数量，失败项保持选中；运行中删除被 409 `profile_running` 拒绝时计入失败。
- 新建环境弹窗与详情配置标签共用同一个 `ProfileForm`：基本 / 网络 / 指纹 / 高级（默认折叠）四分区；名称必填；分组可就地新建；代理可从代理库选择或设为直连；平台与字体集可选，字体集只列出同平台的集、默认选中后端给出的默认集（t053 A16），显示来源版本与完整性，缺失或不一致时告警；种子可重新随机；「创建并启动」在创建成功后发起启动；校验错误显示在对应字段旁。
- 详情路由 `/profiles/:profileId/{config,files,automation,maintenance}`（`/profiles/:profileId` 重定向到 `config`）：页头含名称、状态、分组与打开会话、启动 / 停止；四个标签共享默认搜索初始化失败提示（含重试）与运行配置待应用提示（含「应用并重启」，沿用阶段跟踪语义）。只改元数据（名称、分组、备注、排序）保存后不出现待应用提示；运行中修改运行配置并保存后出现待应用提示。
- 文件与自动化标签按设计系统重建，能力与旧页面等价；维护标签含复制（仅配置 / 含浏览器状态，运行中禁用后者）、重置（列出将清除与保留的内容）、删除（运行中禁删）。
- 分组管理弹窗：列表（色块、名称、使用环境数）、新建 / 改名 / 改色（8 色调色板）/ 拖动与键盘排序 / 删除（确认框显示受影响环境数，删除后这些环境显示为未分组）。
- 旧页面组件（`ProfileNewPage` / `ProfileFilesPage` / `ProfileAutomationPage`）与旧 `data-testid` 全部删除，按 D16 重建、不保留兼容层；旧 `/profiles/new`、`/automation/:id`、`/?profileId=` 不再有任何特殊语义，未匹配的 `profileId` 按普通详情页处理。新页面结构下按 Profile 隔离动作状态、每个标签页独立目标、关闭页面不停止 Profile 均有测试覆盖。
- 中文界面用「环境」，英文用「Profile」；en / zh 文案键同步补齐。业务代码只用语义 token，不含 Tailwind 默认调色板类与颜色字面量。

## 显示编号（t050）

- Profile 创建时分配部署内唯一显示编号（0001…），删除后不复用；API 返回 `display_number`，前端在列表与表格中与名称一同展示，便于对应 Docker 沙箱容器名。

## API 契约与数据层（t056）

- **显示编号必填（A21）**：`display_number` 为 NOT NULL（增量迁移 `0009`，先回填存量 NULL 再改约束）；领域模型 `Profile.display_number: int` 无默认值，读到 NULL 行时仓储抛明确错误，不静默补默认值。
- **引用校验是字段级 422（A28）**：创建或更新 Profile 时引用不存在的分组 / 代理，返回 422 `validation_error`，`details` 列出每个缺失字段的 `loc` / `msg` / `type`（两字段同时缺失一次报出两个）；PATCH 只校验请求中出现的引用键，显式 null 清除引用不查库。分组重排必须提交全集：缺失、未知或重复 id 一律 422。
- **分组与代理写操作幂等（A23）**：group / proxy 的 create / update / delete 支持 `Idempotency-Key`，与 Profile 同一审计语义；重放不重复触发探测等副作用。详见 `proxy_management.md` 第 8 节。
- **Profile 创建锁（A23）**：创建提交是同步 ref 锁，同一 tick 内双击只发一次请求；幂等键绑定到当前打开的创建弹窗，关闭重开复用同一键直至创建成功，成功后才换新键。
- **引用变更事件（A31）**：分组或代理写成功后服务端经 SSE 推送 `groups_changed` / `proxies_changed`，前端使对应列表查询与 Profile 列表查询失效重取；探测不发事件。
- **统一错误契约（A15）**：全部 API 错误响应体为 `ErrorResponse`（`error` / `message` / `retryable` + 可选结构化 `details`），422 的字段级错误列表进 `details`；429 为 `rate_limited` 并带 `Retry-After`。详见 `docs/blueprint/conventions.md` 第 7 节。

## 前端状态一致性（t058）

- Profile 编辑只提交与初始值不同的字段；字段分类（元数据 / 即时 / 运行配置）以后端三分常量为准，经生成类型同步，前后端逐值一致。
- 仅改 `capture_preview`（唯一即时字段）不产生新配置版本；保存成功时先取消在途 detail 查询再写入缓存，不再 invalidate detail，在途旧请求不回填旧值。
- 保存不改变运行实例绑定的 `config_version`，`useUpdateProfileMutation` 不再 invalidate runtime 缓存；SSE 事件到达时仍按既有语义 invalidate runtime。

## 环境数据保留、复制重置与 seed 统一（t066）

- 普通配置保存只写配置与版本，永不清空或重建浏览器用户数据目录；清状态只能来自明确确认的 reset，reset 全清用户目录、保留环境配置与独立 Artifact，失败时旧目录与配置成套恢复。
- 状态改写分两档判定：duplicate（带状态）/ reset 须完全停止（desired/observed 均为 stopped 且无 runtime_instance_id 绑定，error 态亦拒绝）；delete 用实际写者判定（desired=running、observed 处于迁移态、或实例残留绑定任一成立即拒绝；error 态且无绑定可删）。
- 指纹 seed 单一空间 100000..999999：创建、普通 reset、幂等 reset 同源；operation_id 经 SHA-256 确定性推导，重放同 seed，已保存 seed 不追溯改写。
- include-state clone 逐字复制（跳过 Singleton rendezvous 文件）并以 manifest 全等校验；引擎无按 Profile 锚定的 OSCrypt 密钥根（t066 spike 实测 Chromium 146），不删 Local State。

## launch_args 单一严格校验（t069）

- `launch_args` 全系统只有 `validate_launch_args` 一处校验：创建、更新与持久化加载（`ProfileConfig`）共用；删除原加载侧的静默过滤（`filter_launch_args`）。存量行含白名单外参数时，repository 加载即抛指名该 Profile 的错误，要求先修复数据；合法的 locale/timezone None 自动推导与 PATCH 缺省语义不变。
