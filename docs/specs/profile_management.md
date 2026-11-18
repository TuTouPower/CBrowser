---
slug: profile_management
status: active
tasks: [baseline, t075, t076, t077, t078, t079]
---
# 需求规范：Profile 管理与外部标签页

本文描述 t007 交付的前端 Profile 管理、页面独立选择与运行意愿行为，取代旧 `chrome_external_tabs`（控制租约模型已废弃，见 docs/archive/specs/）。文件/自动化页面由 t008、复制/重置由 t013 补充；生效状态以 specs_index 为准。

## 登录与入口

- 未登录访问任何应用页面跳转 `/login` 并保留原目标（含 `?profileId=`），登录后回到原目标；目标只接受同源相对路径。使用中会话失效（API 401）同样回到登录页。
- 运行状态推送（SSE）只在已登录时运行。

## Profile 列表与编辑

- Profile 列表、创建、编辑（名称、屏幕尺寸、备注）与设置均通过 `/api/v1` 完成，前端类型由 OpenAPI 生成。
- 运行状态由服务端 SSE 推送，断线自动重连；前端不保存控制状态，重连后以服务端状态为准。

## 集合读取与运行摘要（t076）

- 列表不再拉全量再客户端拼装：`GET /api/v1/profiles/collection`（搜索 / 分组 / 代理 / 状态 / 平台 / 排序 `default|manual|name|recent|created`，分页 `page_size` 服务端钳制 1..100，总数计全量筛选集）、`GET /api/v1/proxies/collection`、`GET /api/v1/groups/collection`，有界候选 `…/candidates`（`limit` 钳制 1..50）与代理国家→城市范围 `GET /api/v1/proxies/countries`（键为稳定国家代码）。排序默认稳定（`sort_order`、`created_at`、`id`），分页无重复遗漏。
- 运行状态只读一次批量摘要：`GET /api/v1/profiles/runtime-summary` 返回全部环境 `desired_state` / `observed_state` / `config_version` / 实例 / 失败计数 / 启停时间 / 预览捕获时间 / 协调器错误与运行总数；列表、卡片、工作台入口与关闭的切换器都只读它，不再按环境逐个发 runtime 请求。单环境详情仍按需读 `GET /api/v1/profiles/{id}/runtime`。
- SSE `runtime_state` 事件带 `config_version` 围栏：旧版本或旧实例的迟到事件丢弃，重复/重放事件无副作用且不触发列表重取；有效事件原地更新 runtime 缓存与摘要缓存。`GET /api/v1/proxies/{id}/used-by` 返回当前配置 ∪ 运行绑定版本的并集明细（每项标 `current` / `bound` / `both`），计数、导航与删除保护用同一口径。

## 表单布局与长集合选择交互（t077）

- 创建/编辑表单（`ProfileForm`）的分区按弹窗实际可用宽度规划，不再按外部视口断点切列：表单为容器查询根（`@container`），Section 在容器宽 ≥24rem 时两列、≥36rem 时三列；时区/语言、配色/CJK 为直接网格项，不再嵌套半列；字段占宽明确（种子输入 `w-seed` 5rem、6 位数字不裁切，刷新按钮在标签行）。普通/窄/低高度窗口与中英长文本下字段不重叠、不越出表单，提交/取消可达。
- 固定少量枚举（状态/平台/排序/协议/语言/配色/拟人化预设）用有界 `Select`（长值单行截断 + `title` 回显全名，触发器在表单格内 `w-full`）；增长型实体（代理/环境/分组/国家/城市）用可搜索选择 `SearchableSelect`（顶部搜索框 + 完整候选数组客户端过滤 + Enter 选首个匹配），选择身份始终是稳定 ID，不与显示名称/排序混用；候选来自 t076 的有界端点（首 50 条 + 已选值单读回显）。200 代理与 100 分组/地区候选下列表内部滚动、滚轮可达末项、搜索可找到未加载末项、选中值准确回显。
- 共享浮层契约：`Select`/`Popover` 内容限高为 Radix 可用高度（`max-h-available-height`，`--radix-popper-available-height`），内容区内部滚动、定位与碰撞翻转走 Radix；`Popover` 内容为纵向 flex 列 + 内部滚动区；长列表的键盘（方向键/Home/End/Enter 提交/Escape 关闭/焦点回归）与 p070/t053 的既有提交判据保持不变，同值重选只触发一次既有提交语义。时区候选走 Radix Popover Portal（锚定输入框，`side="bottom"` + 碰撞翻转），不再被外层 Dialog 滚动区裁切。
- 批量移动分组菜单（`MoveGroupMenu`）为锚定到移动按钮的 Popover（搜索 + 内部滚动 + 键盘导航 + Escape 焦点回归），取代旧的页面底部固定菜单；100 分组下在常规与 400px 低视口中均受实际可用视口约束。环境切换器列表内部滚动；关联环境浮层（`ProxyUsedByPopover`）列表内部滚动。分组管理弹窗与外层 Dialog 保持既有内部滚动，末项与提交可达。
- 全部高级布尔选项（拟人化、自动启动、Google 默认、透明代理、预览、剪贴板、第三方 Cookie、恢复会话、便携 Cookie）与拟人化预设、启动参数、扩展路径字段旁均有可聚焦的感叹号帮助入口，鼠标与键盘均可读到当前界面语言的说明，内容与实际运行行为一致。注意：`auto_launch` 当前无任何消费点（后端/前端均不读取），帮助文案如实写“保存但当前不触发任何自动启动”；实现或删除该字段不在 t077 范围内，待另行定夺。

## 删除生命周期（t078）

- 删除是服务端持久化生命周期，不是单次请求：`POST /api/v1/profile-deletions` 以明确 ID 集合受理，逐目标返回操作回执（`batch_id` + 每目标 `stage`）；`GET /api/v1/profile-deletions/batches/{batch_id}` 与 `GET /api/v1/profile-deletions/{operation_id}` 查询进度，`POST /api/v1/profile-deletions/{operation_id}/retry` 重试失败目标。重复提交同一目标返回既有未终结意图，不产生重复删除。
- 阶段为 `accepted → stopping → cleaning → done`，失败记 `failed` + `failed_stage` + 具体错误：stopping 阶段置停止意愿并等待写者消失（超时不删数据）；cleaning 阶段先复核停止时绑定的实例未被新实例替换（围栏），再依次清理 Artifact、Profile 目录、预览图与数据库行，任一步失败即整体失败、Profile 行保留。每步结果记入操作 `detail`，可追踪。
- 服务重启后未终结意图自动恢复推进；已删除目标的迟到运行事件不能复活目标，清理后新绑定的实例不受影响。旧 `DELETE /api/v1/profiles/{id}` 收敛为同步驱动同一状态机：删除失败返回 409 并带失败阶段，不再以「运行中」拒绝删除。
- 列表与卡片共用操作定义：停止与删除独立呈现，删除固定最右且 danger 样式，运行行删除表示「先停止再删除」；环境管理页头不再显示运行数量统计，表格不再有最后活跃列（相对时间仅卡片保留）。
- 单项与批量删除共用居中模态：确认前不发请求，确认目标集合在打开时冻结（翻页/筛选不漂移），进度与逐项结果在弹窗内呈现，失败项保留阶段、错误与重试入口；成功项从选择中移除，失败项保留。批量不再逐个调用单删接口。

## 启动参数校验与 PATCH 三态（t021）

- 更新 DTO 对 `launch_args` / `extension_paths` 只做严格校验（条数、单条长度、危险参数拒绝），不再在校验阶段过滤合法条目；历史行读取同样严格（t069）：存量 `launch_args` 不合法时加载即拒绝并指名 Profile，不再静默过滤。
- PATCH 语义三态：字段缺失 = 不变；显式 `null` = 清空为 `[]`；给出列表 = 整体替换。`ProfileConfig` 把显式 null 的这两个列表归一为 `[]`，仓储合并不得因此 500；越界内容返回 422。

## 页面独立选择

- 每个 Chrome 标签页独立维护会话目标（`/session/:profileId`），不改变其他标签页的目标或连接；不使用跨标签页共享的 `localStorage.currentProfileId`。
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

## 指纹平台与平台字体集（t041，t075 修订）

- Profile 运行配置新增 `fingerprint_platform`（`windows` 默认 / `macos`）与 `font_set_id`（引用同平台不可变字体集），经增量迁移 `0002_fingerprint_platform.py` 加入；两者属运行配置，修改任一都生成新 `ProfileConfigVersion`（AC-003）。
- t075 起 `font_set_id` 为后端托管绑定：创建/克隆/切平台由服务按资产目录默认规则解析（`GET /api/v1/font-sets` 的 `default_font_set_id[platform]`，只取 verified 的集，其中最近一次验证通过的胜出），创建/更新请求不再接受该字段；字体根已配置（一切真实部署）而平台无可用集时创建/切换在写入前失败，部署中不再产生「无字体集」的 Profile（未配置字体根的进程可暂无绑定，但启动失败封闭）。旧 t053 A16 的显式 null 语义废止。
- t075 新增运行配置 `include_cjk_fonts`（中文字体暴露开关，创建默认按语言派生）；`color_scheme` 收敛为 `light` / `dark`；`gpu_family` 删除（GPU 身份由引擎按种子+平台派生）。旧形状由迁移 `0013_profile_identity.py` 一次性改写，不可等价映射改写前阻塞（详见 fingerprint_platform spec 2.1 与 ADR 040）。
- `font_bundle`（文泉驿三档）已删除：字段、镜像字体包、代码、文档与测试引用一并清理（AC-009）。
- runtime 响应与 SSE 下发实际使用的 `font_set_id` 与 `missing_fonts`（t075 起读 Runner 启动前验证结论，不逐请求重扫）；绑定字体集缺失或 manifest / 文件不一致时启动失败封闭 `font_set_unavailable`，未绑定同样失败封闭（AC-006 / AC-007，旧 null 正常启动语义废止）。

## 语言、时区与参数自动对齐（t053+）

- 新建 Profile 默认值：`humanize` 与 `portable_cookies` 开启；`transparent_proxy` 与 `auto_launch` 关闭；`allow_3p_cookies` / `set_google_default` / `clipboard_sync` / `restore_session` / `capture_preview` 开启。前后端与 ORM 默认值一致，OpenAPI 与前端类型重新生成；既有 Profile 的已存值在升级后不变。
- 语言只支持 `zh-CN` / `en-US`（新建默认 `en-US`），后端校验拒绝其它值与非法时区，返回字段级错误；时区为空表示自动（随出口 IP）。
- 时区 → 语言：中文地区时区（`Asia/Shanghai`、`Asia/Chongqing`、`Asia/Urumqi`、`Asia/Harbin`、`Asia/Hong_Kong`、`Asia/Macau`、`Asia/Taipei`）→ `zh-CN`，其余 → `en-US`；时区为空时语言保持当前值。
- 代理 / 语言 / 平台参数自动联动：
    - 选择代理时，前端根据代理位置（国家码 / 地区标签 / 名称）自动匹配对应 IANA 时区，并联动切换对应语言（`zh-CN` / `en-US`）。
    - 切换语言（`locale`）时，在已设时区时对齐对应地区时区；CJK 字体开关在用户未手动设置前随语言派生（中文开、英文关），用户手动切换后不再被语言联动改写（t075）。
    - 切换平台（`fingerprint_platform`）时，自动切换默认分辨率（Windows 默认 `1920×1080`，macOS 默认 `1440×900`）；字体集绑定由后端按新平台重绑，表单不参与（t075）。
- 环境表单不再提供字体包与 GPU 选择（t075）：字体集在设置页平台字体区块只读展示人类可读名称（如「Windows 标准字体包」「Office 中文字体包」「macOS 苹方字体包」），不向用户展示冗长的 SHA256 哈希字符串；会话详情只读展示实际绑定。

## 环境管理界面（t037+）

- 首页 `/` 为环境列表：8 列（选择 / 环境 / 分组 / 代理 / 平台与时区 / 状态 / 最后活跃 / 操作）与卡片视图；工具栏单行紧凑排列，含搜索（名称、备注、代理名）、状态筛选（全部状态、运行中、已停止、异常）、分组筛选（全部分组、未分组、各分组）、系统筛选（全部系统、Windows、macOS）、代理筛选（全部代理、直连、各代理）、排序（手动排序、按名称排序、最近活跃、创建时间）、独立的「分组管理」按钮、图标化列表/卡片视图切换按钮（存 `cbrowser.environments.layout`）与「新建环境」主按钮。筛选与排序状态写入 URL 查询参数并可由 URL 还原；筛选无结果提供「清除筛选」。
- 列表与卡片均不向用户展示内部数字编号（`#0001`）或环境 ID；环境备注通过名称旁的感叹号图标悬浮 Tooltip 展示，不直接平铺占用行高。
- 代理列（原「网络」列统一改称「代理」）仅展示所选代理名称或「直连」，不堆砌冗余协议标签与长句警告；平台列显示本地化系统名称（`Windows` / `macOS`）与时区；状态为本地化五态徽标，error 悬停显示原因。
- 新建环境弹窗与详情配置标签共用同一个 `ProfileForm`：基本 / 代理 / 指纹 / 高级（默认折叠）四分区；指纹种子旁通过感叹号图标悬浮提示有效范围（`100000 – 999999`），重摇种子采用图标化刷新按钮；分辨率输入框隐藏原生微调箭头以适配深色模式。
- 文件标签页（`ProfileFilesTab`）同样提供图标化的列表/卡片视图切换按钮。

## 显示编号（t050）

- Profile 创建时后端分配部署内唯一显示编号（`display_number`），用于对应 Docker 沙箱容器名；前端界面不向用户直接暴露 `#0001` 编号。

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

## 状态呈现（t079）

- 环境运行状态的呈现统一走共享语义映射（见 ui_design_system §2.9）：列表、卡片、详情、状态筛选、工作台与自动化使用同一组状态词条；runtime 未加载或状态不在枚举内时显式呈「未知」，不回退为「已停止」。
