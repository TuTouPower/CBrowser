# bundle_local_backend_core

## responsibilities

- 已核对实现：src/backend/main.py 是 legacy FastAPI 应用（profile CRUD、launch/stop、VNC/CDP WebSocket 代理、产物文件、剪贴板中继、settings、update-check、SPA 静态托管），且为当前 Docker 部署的实际入口（config/docker/entrypoint.sh:27 执行 uvicorn backend.main:app，属单元外证据）。
- 已核对实现：browser_manager.py 负责每 profile 的 CloakBrowser 进程生命周期（CDP 端口预留、许可证拒绝识别、截图预览、下载捕获接线、VNC 分配）；database.py 以原生 sqlite3 维护 profiles/profile_tags/artifacts 三表，并在 init_db 时按列集差异自动重建 profiles 表。
- 已核对实现：artifacts.py + downloads.py 实现产物存储（流式上传、配额、picker 视图符号链接、未发布字节回收）与 CDP 下载事件到产物行的状态机；diagnostics.py 提供启动指纹、全局崩溃钩子、stderr tee 与运行时事件脱敏日志。
- 已核对实现：migrations/ 是 v2 栈的 Alembic 迁移（0001 八表、0002 auth 三表、0003 artifacts 校验和列），服务对象是 cbrowser 包的 SQLAlchemy 模型与另一个数据库文件（cbrowser/api/main.py 默认 CBROWSER_DB_PATH=/data/cbrowser.db），不是 legacy 的 profiles.db；env.py 支持程序化传入 sync connection，实际由 cbrowser/adapters/database/migrations.py 程序化调用（单元外证据）。
- 文档声明（未在本单元内核对真伪）：AGENTS.md 与任务索引显示存在 t010_v2_data_migration、t011_v2_remove_legacy 两个后续任务，即双栈并存是已知的过渡状态而非无意遗留。

## interfaces

- HTTP/WS API：/api/profiles\*（CRUD/reorder/reset/duplicate/launch/stop/status/files/clipboard/vnc/cdp/screenshot）、/api/auth/\*、/api/settings、/api/status、/api/health、/api/update-check、/api/shutdown、/api/open-external（main.py）
- Pydantic 契约：models.py 的 ProfileCreate/ProfileUpdate（extra=forbid）、ProfileResponse、ArtifactResponse 等
- 进程内接口：database.py 函数式仓储（create/get/list/update/delete_profile 与 artifacts 系列）、BrowserManager.launch/stop/get_status/hold_stopped、artifacts.save_stream/check_quota、downloads.watch/DownloadTracker
- Alembic 契约：migrations/env.py 以 cbrowser.adapters.database.models.Base 为 target_metadata；alembic.ini 只定义 script_location 与日志，无 sqlalchemy.url

## dependencies

- 第三方包 cloakbrowser（launch_persistent_context_async、license、geoip、download）是浏览器启动与许可证的唯一通道
- pyproject.toml 与 src/backend/requirements.txt 两份依赖清单并存且内容不一致（见 f_backend_core_07）
- diagnostics.py 反向 import v2 包 cbrowser.domain.runtime_policy.ExitReason，legacy 栈对 cbrowser 包存在编译期耦合
- database.py 在 import 时即执行 resolve_runtime() 并固定 DATA_DIR/DB_PATH；main.py 在 import 时加载 .env、建日志目录、构造 BrowserManager 单例

## flows

- 启动：load_env_file → import database（resolve_runtime）→ BrowserManager 单例 → lifespan: init_db → artifacts.reclaim_all + sync_picker_view → cleanup_stale → resolve_binary_status（线程）→ auto_launch_all
- 启动浏览器：POST launch → BrowserManager.launch（锁内登记 \_launching → VNC 分配 → 删除 Singleton 锁（仅 docker）→ 一次性搜索引擎设置 → 代理规范化/校验 → CDP 端口预留 → launch_persistent_context_async → denial 文件检查 + \_wait_for_cdp 验证 webSocketDebuggerUrl）
- 上传文件：POST files → Content-Length/配额预检 → artifacts.save_stream 流式落盘（.incoming- 临时文件 + os.replace 发布）→ 真实大小复检配额 → db.create_artifact → sync_picker_view
- 下载捕获：downloads.watch 通过 CDP Browser.downloadWillBegin/Progress 事件驱动 DownloadTracker，完成后从 staging 区 os.replace 到产物目录并更新行状态

## constraints

- Linux 只允许 docker runtime、非 Linux 只允许 native（runtime.resolve_runtime 强校验）
- AUTH_TOKEN 未设置时 legacy API 完全开放（main.py:116 附近注释自述为 local dev 取向）
- settings.json 由 tempfile.mkstemp 创建（0600）后 os.replace，许可证密钥以明文 JSON 落盘（settings_store.py:34-48）
- v2 secret_files.read_secret_file 拒绝 group/other 可读的凭据文件（mode & 0o077），legacy 的 .env 加载无此检查
- 产物上限由环境变量 ARTIFACT_MAX_BYTES/ARTIFACT_MAX_COUNT/ARTIFACT_MAX_TOTAL_BYTES 控制，默认 256MB/200 个/2GB（artifacts.py:26-28）

## decisions

- 源码注释明确记录的决策：产物字节存放在 user_data_dir 之外，以免克隆/导出携带商户文档（artifacts.py 头注）；下载只认 CDP 完成事件、不认文件名出现（downloads.py 头注）；reset 保留 Bookmarks/Preferences/Web Data 以免重建默认搜索引擎（main.py \_RESET_STATE_FILES 上方注释）
- 源码注释明确记录的决策：stop/launch 用 \_launching/\_stopping/\_held 三组状态保证 profile 目录在任一时刻只有一个所有者（browser_manager.py）

## evidence

- src/backend/main.py:116-140 AUTH_TOKEN 可选与豁免路径定义
- src/backend/main.py:1835-1843 serve_spa 以 FRONTEND_DIR / full_path 直接 FileResponse，无 resolve/包含校验
- src/backend/main.py:1301,1399 剪贴板 SET/GET 均以 preview=%r 记录正文前 60 字符
- src/backend/main.py:228-252,1221-1236 \_same_origin_request 仅用于 /api/shutdown
- src/backend/database.py:22-45,104-185 legacy 列集与自动重建逻辑；src/backend/migrations/versions/0001_initial_schema.py:65-75 v2 profiles 多出 runtime_mode/viewer_mode/current_config_version 列
- src/backend/migrations/alembic.ini:1-6 无 sqlalchemy.url；src/backend/migrations/env.py:26,69 运行时读取该键
- pyproject.toml:6-19 与 src/backend/requirements.txt:1-9 依赖清单差异
- src/backend/browser_manager.py:63-82 \_normalize_proxy 按冒号切分拼接；836-845 \_headless_launch 无条件删除 Singleton 锁，与 launch 中 docker-only 删除及其注释相左
- config/docker/entrypoint.sh:27（单元外）Docker 入口为 backend.main:app；src/backend/cbrowser/api/main.py:10（单元外）v2 默认 DB 为 /data/cbrowser.db，与 database.py 的 DATA_DIR/profiles.db 不同
- tests view completed by dedicated follow-up review (viewfix_backend_core_tests.json, reviewer 82c921a9-332e-46c3-a441-938249245c44): 本文件补齐 backend_core 单元 tests 视角的裁决：原 reviewer 只确认了测试存在性，本次通读 test_api.py（1398 行）、test_browser_manager.py（705 行）、test_database.py（373 行）全文，并以 backend_tests 单元的全量审阅结论为可信度映射依据，另以全 tests 目录 grep 核实若干『不存在』断言。结论：本单元的多数主干行为（profile CRUD、launch/stop 状态机、duplicate hold 语义、下载捕获重装、数据库 CRUD/排序、代理与指纹参数构建）有行为级测试且质量在套件平均线之上；但三个承重行为没有任何测试钉住其安全形态——剪贴板日志（f_backend_core_02 的泄漏在现有剪贴板测试下可任意存续）、SPA catch-all 静态托管（全套件零测试

## uncertainties

- serve_spa 路径遍历未做运行时复现（本次禁止运行）：Starlette/uvicorn 对 %2e%2e%2f 的解码与路径参数传递按静态推理判断可达，实际可利用性取决于部署侧代理/服务器是否先行规范化路径。
- compose.yaml 是否默认注入 AUTH_TOKEN 未核对（属 contracts_deploy 单元），f_backend_core_05 的实际暴露面取决于部署配置。
- legacy 与 v2 两套数据库在同一部署中是否同时被写入、是否存在数据同步，未在本单元范围内核对；t010 数据迁移任务的现状未读。

## Findings

- [High][70] src/backend/main.py:1835-1843 — SPA catch-all 以未校验的 full_path 拼路径返回文件，可越出 frontend/dist 读取任意文件

    - ID: f_backend_core_01; verification: suspected
    - Evidence: serve_spa: file_path = FRONTEND_DIR / full_path，仅判断 exists()/is_file() 即 FileResponse，无 resolve() 后的包含关系校验; AuthMiddleware 对非 /api/ 路径直接放行（main.py:276），该路由无其他门禁; full_path 为 Starlette :path 路径参数（已百分号解码），编码点段可形成 ../ 序列；FRONTEND_DIR 在源码运行时位于仓内，向上可达仓根 .env、src 源码乃至 data 目录
    - Impact: 未认证远程请求可通过构造路径读取前端目录之外的文件（如仓库 .env 中的 AUTH_TOKEN/许可证密钥、数据库文件），具体可达范围取决于 uvicorn/代理是否先行规范化路径。
    - Fix: 在 serve_spa 中对 (FRONTEND_DIR / full_path).resolve() 做 is_relative_to(FRONTEND_DIR.resolve()) 校验，越界时回退 index.html 或 404；或改用 StaticFiles 的 html 模式托管整个 dist。

- [High][95] src/backend/main.py:1299-1301 — 剪贴板正文前 60 字符被以 INFO 级别写入 manager.log（SET 与 GET 两处）

    - ID: f_backend_core_02; verification: static
    - Evidence: set_clipboard: logger.info("Clipboard SET for %s: text_len=%d preview=%r", ..., body.text[:60])（main.py:1301）; get_clipboard: logger.info("Clipboard GET for %s (CDP): len=%d preview=%r", ..., text[:60])（main.py:1399）; 日志经 RotatingFileHandler 落盘到 data_dir/logs/manager.log（main.py:79-96），diagnostics.py 的设计目标即让支持人员凭该日志诊断问题，日志会被外发; diagnostics.emit_runtime_event_log 的 docstring 明示『Never logs passwords, tokens, cookies, clipboard content』，与此处实现直接矛盾
    - Impact: 剪贴板常含密码、一次性验证码与商户文档片段；这些内容被持久化进轮转日志并可能随支持工单外发，形成凭据泄漏面。
    - Fix: 两处日志删除 preview 字段，只保留长度；如确需调试内容，改为显式 debug 开关且默认关闭，并同步修正 diagnostics 的声明与实现一致性。

- [High][90] src/backend/main.py:1-60 — 两套后端栈同时在线且数据存储分叉：Docker 入口跑 legacy main.py（profiles.db），v2 cbrowser 包用另一数据库（cbrowser.db）与另一套 schema/API

    - ID: f_backend_core_03; verification: static
    - Evidence: config/docker/entrypoint.sh:27（单元外取证）：exec uvicorn backend.main:app，即当前发货入口是 legacy 栈; legacy 栈 database.py 使用 DATA_DIR/profiles.db，原生 sqlite3 手写仓储；v2 api/main.py:10（单元外取证）默认 CBROWSER_DB_PATH=/data/cbrowser.db，走 SQLAlchemy + Alembic; schema 已分叉：migrations 0001 的 profiles 含 runtime_mode/viewer_mode/current_config_version 等列，legacy database.py 的 \_PROFILE_COLUMNS 没有这些列；auth、artifacts 在两栈各有一套实现; docs/tasks 索引（单元外）存在 t010_v2_data_migration、t011_v2_remove_legacy，说明迁移未完成、双栈仍是当前事实
    - Impact: 同一产品面（profile/产物/认证）有两份实现与两份数据，修复与安全补丁只落一栈即在另一栈留洞；用户数据可能按入口不同落在不同 DB，迁移与排障成本翻倍，且审阅/测试结论无法跨栈复用。
    - Fix: 按 t010/t011 既定方向收敛：明确唯一权威栈与 DB，完成数据迁移后删除或冻结 legacy 入口；在收敛前至少在 main.py/database.py 头注与 README 中标明哪套是当前权威、哪套待删，避免新功能继续双写。

- [Medium][80] src/backend/main.py:1221-1236 — 同源 CSRF 防护只加在 /api/shutdown，launch/stop/reset/duplicate 等无 body 的状态变更 POST 未设防

    - ID: f_backend_core_04; verification: static
    - Evidence: \_same_origin_request（main.py:228-252）仅在 shutdown_manager 中被调用（main.py:1230）; launch_profile（994）、stop_profile（1032）为无 body POST；reset_profile（694）无 body 且会删除 Cookies/History/Login Data 等状态文件；duplicate_profile（768）的 body 可选; shutdown 的注释自述：bodyless POST 是 CORS 简单请求、无预检，任意网站可借用户浏览器命中 localhost 端点——同一推理适用于上述端点; AUTH_TOKEN 设置时 auth cookie 为 SameSite=strict，可缓解浏览器 CSRF；未设置（默认）时无任何缓解
    - Impact: 用户浏览恶意网页时，该页可借其浏览器向本机 Manager 发起简单请求，启动/停止浏览器、重置 profile（销毁登录态与历史）或克隆 profile，造成数据损失与骚扰。
    - Fix: 将 \_same_origin_request 提升为中间件级校验，覆盖全部状态变更方法（或至少全部无 body/简单请求可达的 POST）；或要求所有变更请求带自定义头并统一校验。

- [Medium][85] src/backend/main.py:116-140 — AUTH_TOKEN 未设置时整个 API 无认证开放，而同一应用是监听 0.0.0.0:8080 的 Docker 发货入口

    - ID: f_backend_core_05; verification: static
    - Evidence: main.py:116 AUTH_TOKEN = os.environ.get("AUTH_TOKEN") or None；AuthMiddleware 在 AUTH_TOKEN 为空时全量放行（main.py:262-266）; 注释自述该取向是『local dev』，但 config/docker/entrypoint.sh:27（单元外）以 --host 0.0.0.0 运行同一 app; 开放面包含 CDP 代理（等价于浏览器完全控制）、PUT /api/settings 改许可证密钥、POST /api/shutdown 关停、profile 与产物全部 CRUD
    - Impact: 部署者若未注入 AUTH_TOKEN（或 .env 漏配），同网段任何人可完全控制 Manager 与全部浏览器 profile。实际暴露取决于 compose/部署是否强制注入（未在本单元核对），故定 Medium。
    - Fix: Docker 模式下 AUTH_TOKEN 缺失应 fail-closed（拒绝启动或仅绑回环并显式告警）；至少在 lifespan 启动日志中对无认证状态打出醒目警告，并在部署文档中标为必填。

- [Medium][85] src/backend/database.py:104-185 — legacy init_db 的自动重建只复制与新列集相交的列，且 alembic.ini 未配置 sqlalchemy.url，迁移安全性依赖隐含约定

    - ID: f_backend_core_06; verification: static
    - Evidence: \_rebuild_profiles: copied = [c for c in \_PROFILE_COLUMNS if c in old_columns]，旧表中任何不在 legacy 列集内的列（例如 v2 的 runtime_mode/viewer_mode/current_config_version）在重建时被静默丢弃; init_db 只要 old_columns != set(\_PROFILE_COLUMNS) 即触发全表重建，无版本标记、无备份、无降级路径; migrations/alembic.ini 只有 script_location 与日志配置，没有 sqlalchemy.url；migrations/env.py:26,69 读取该键，独立执行 alembic CLI 时 URL 为空无法运行，实际只能由 cbrowser/adapters/database/migrations.py 程序化注入（单元外取证）
    - Impact: 若任一工具/脚本误将 legacy init_db 指向 v2 schema 的数据库（或反之），重建会静默丢失列数据；同时迁移入口不自包含，换人/换机时按 alembic 常规用法操作会直接失败，易诱发手工改库。
    - Fix: \_rebuild_profiles 对『旧列集多于新列集』的情况拒绝自动重建并报错留痕（只允许加列型迁移自动执行）；在 alembic.ini 或 env.py 中给出 URL 的显式来源说明与默认值（如从 CBROWSER_DB_PATH 推导），使迁移可独立复现。

- [Medium][95] pyproject.toml:6-19 — 两份依赖清单分叉：pyproject 与 src/backend/requirements.txt 的包集合与版本约束不一致

    - ID: f_backend_core_07; verification: static
    - Evidence: pyproject.toml: cloakbrowser[geoip]==0.6.4 精确钉版，且含 sqlalchemy/alembic/aiosqlite/docker/argon2-cffi/aiohttp; src/backend/requirements.txt: cloakbrowser[geoip]>=0.6.3（下限而非钉版），完全没有 sqlalchemy/alembic/aiosqlite/docker/argon2-cffi/aiohttp，却多出 pyproject 没有的 pywebview; 两条安装路径（源码/pytest 走 pyproject，冻结/native 构建走 requirements.txt）会产出实质不同的运行环境
    - Impact: 同一代码在两种安装下依赖版本不同，cloakbrowser 行为差异（许可证/下载/指纹）难以复现与定位；v2 栈在 requirements 路径下直接缺包不可运行。
    - Fix: 确立单一权威清单并由它生成另一份（如 pip-tools），或在两份文件头注中明确各自适用场景与同步要求；至少对齐 cloakbrowser 的版本约束方式。

- [Medium][85] src/backend/browser_manager.py:63-82 — \_normalize_proxy 按冒号裸切分拼接，密码含冒号/@ 或 IPv6 主机时生成错误代理 URL

    - ID: f_backend_core_08; verification: static
    - Evidence: host:port:user:pass 格式以 raw.split(':') 判段数：密码含 ':' 时段数大于 4，落入 return raw 原样返回，随后 \_validate_proxy 以无 scheme 报错，错误信息与真实原因无关; user/pass 未做 URL 百分号编码即拼入 http://{user}:{passwd}@host:port，含 @、:、/ 等字符的凭据会改变 URL 结构; host:port 两段式对 IPv6 字面量主机同样按冒号误切
    - Impact: 使用含特殊字符强密码的代理用户无法启动 profile，且收到误导性报错；test_proxy 与 launch 共用该函数，两处同时受影响。
    - Fix: 用 urllib.parse 构造 URL 并对 username/password 做 quote；host:port:user:pass 格式从右侧按最多 3 个分隔符切分（rsplit），或明确文档限定凭据字符集并给出针对性报错。

- [Low][80] src/backend/browser_manager.py:836-845 — \_headless_launch 无条件删除 Singleton 锁文件，与 launch() 明示的『native 模式须由 Chromium 自行仲裁』不变量相左

    - ID: f_backend_core_09; verification: static
    - Evidence: launch() 仅在 runtime_mode == docker 时删 SingletonLock/Cookie/Socket，并注释 native 模式删除会干扰 Chromium 的 profile 所有权仲裁; \_headless_launch（搜索引擎一次性设置用）对任何 runtime 都执行同样的 unlink，未区分模式; 当前调用链下该函数在 profile 未运行时执行，实际触发概率低，属不变量被第二处代码悄悄绕开
    - Impact: 若将来调用时机变化（如 profile 正在关闭中），native 模式下可能删掉仍有效的单例锁，导致同一 user_data_dir 被两个 Chromium 同时打开而损坏。
    - Fix: \_headless_launch 复用 launch() 的同一判断（仅 docker 删除），或抽出共享 helper 并注明前置条件。

- [Low][90] src/backend/browser_manager.py:1096-1117 — auto_launch_all 串行启动全部自启 profile，每个最长阻塞 60 秒；list_profiles 存在每行一次标签查询的 N+1

    - ID: f_backend_core_10; verification: static
    - Evidence: auto_launch_all 对每个 auto_launch profile 依次 await wait_for(launch, 60)，彼此独立却完全串行，N 个 profile 启动期最长 N×60s; database.list_profiles 对每行调用 \_hydrate_profile 单独查询 profile_tags（database.py:256-281）；仓内 profile_names 的 docstring 已承认该开销并为 bookmarks 场景另设了轻量查询，但列表主路径未改
    - Impact: 自启 profile 多时 Manager 启动后长时间不可用；profile 列表接口随 profile 数线性放大查询次数（单机场景影响有限，故 Low）。
    - Fix: auto_launch_all 用带并发上限（如 3）的 asyncio.gather/Semaphore 并行启动；list_profiles 用一次 IN 查询批量取标签后组装。

- [Low][85] src/backend/main.py:443-505 — VNC 代理热路径存在每帧 INFO 级日志，流式使用时会放大日志量并挤占事件循环

    - ID: f_backend_core_11; verification: static
    - Evidence: \_filter_rfb_client_messages 在 len(result) != len(data) 时每帧 logger.info 输入/输出字节数；\_rewrite_set_encodings 每次剥离编码都 INFO 输出保留/剥离的完整编码列表（main.py:443-505 区间）; 日志同时落控制台与 RotatingFileHandler 文件（2MB×3 轮转），高频帧可迅速冲掉真正有用的诊断记录; vnc_proxy 的 vnc_to_client 对每条 BinaryClipboard 也 INFO 一行
    - Impact: 长时间远程桌面会话产生大量低价值日志，轮转文件中的崩溃/启动诊断证据被提前覆盖，且同步日志格式化在 WS 转发路径上增加延迟。
    - Fix: 将逐帧/逐消息日志降为 DEBUG 并做采样或聚合计数（如每 N 帧汇总一次），INFO 只保留连接建立/断开与异常。

- [Low][90] src/backend/env_file.py:27-39 — legacy .env 加载对含密钥文件无权限检查与健壮性处理，与 v2 secret_files 的严格口径不一致

    - ID: f_backend_core_12; verification: static
    - Evidence: load_env_file 直接 read_text 解析，AUTH_TOKEN、许可证密钥等均可经此文件注入，但不做任何 mode 检查; v2 的 cbrowser/secret_files.read_secret_file 对凭据文件强制拒绝 group/other 可读（secret_files.py:15-21），两栈口径分明; 解析为朴素逐行 partition('=')：value.strip().strip('"').strip("'") 会剥掉值首尾所有引号字符，不支持 export 前缀与行内注释，异常值静默入 environ
    - Impact: 组/其他用户可读的 .env 会使 AUTH_TOKEN 与许可证密钥在本机被任意账号读取而无任何告警；个别合法值（含引号或 # 的密钥）会被静默改写导致认证异常且难排查。
    - Fix: 对含密钥的 .env 复用 secret_files 的权限检查（或至少在过宽权限时告警）；解析改用成熟 dotenv 语义或明确限定支持的子集并对越界行告警。

- [Low][85] src/backend/models.py:14-42 — ProfileCreate 缺少数值边界校验，非法屏幕尺寸/种子直接流入 Chromium 启动参数

    - ID: f_backend_core_13; verification: static
    - Evidence: ProfileCreate 的 screen_width/screen_height/fingerprint_seed 为裸 int（可为负或极大），name 无长度上限；对比 ProxyTestRequest 对 proxy 设有 min/max_length（models.py:210-212），同文件口径不一; 这些值在 browser_manager 中被拼成 --window-size={sw},{sh} 与 --fingerprint={seed} 等启动参数（browser_manager.launch 与 \_build_fingerprint_args）; legacy DB 的 screen 列无 CHECK 约束，非法值可一路落库
    - Impact: 误填或恶意输入造成浏览器启动失败并以笼统 500 返回，而非在 API 层 422 明确拒绝；排查成本落在启动日志里。
    - Fix: 为 screen_width/screen_height 加 gt=0 与合理上限（如 le=16384），fingerprint_seed 加非负约束，name 加 max_length，与 DB 列宽（v2 String(255)）对齐。

- [Low][85] src/backend/settings_store.py:22-48 — settings.json 解析失败时静默回退空 dict，许可证密钥会无声丢失（降级 keyless 无任何信号）

    - ID: f_backend_core_14; verification: static
    - Evidence: load_settings 对 FileNotFoundError/JSONDecodeError/OSError 一律 return {}，不区分『从未设置』与『文件损坏』; main.py 在 import 时以 \_STORED_SETTINGS 固定初始 LICENSE_KEY/RELEASE_CHANNEL，损坏发生在运行期写入一半（进程被杀）后，下次启动即静默 keyless; save_settings 虽用 mkstemp + os.replace 原子写，但无 fsync，断电场景仍可能留下空/半文件
    - Impact: 用户付费许可证在一次异常断电/磁盘问题后无声失效，表现为 Pro 功能消失而无任何错误提示，支持成本高。
    - Fix: load_settings 对 JSONDecodeError 记录 warning 日志（含路径、不含内容）；save_settings 在 replace 前对临时文件 fsync，并保留一份 .bak 供损坏时回退。

- [Low][80] src/backend/vnc_manager.py:112-126 — stop_vnc 使用已弃用的 get_event_loop 且 kill 后不再 wait，Xvnc 可能留僵尸进程；日志路径为可预测的 /tmp 文件

    - ID: f_backend_core_15; verification: static
    - Evidence: stop_vnc: asyncio.get_event_loop().run_in_executor(None, instance.process.wait, 5)——新代码应使用 get_running_loop; TimeoutExpired 后 instance.process.kill() 被调用但无人再 wait() 回收，子进程退出状态无人收取; start_vnc 以 open(f"/tmp/xvnc-{display}.log", "w") 打开可预测路径，共享 /tmp 下存在符号链接跟随风险（容器内单用户场景风险低）
    - Impact: 长期运行反复启停 profile 后可能积累僵尸 Xvnc 进程与句柄；事件循环获取方式在未来 Python 版本有兼容风险。
    - Fix: 改用 asyncio.get_running_loop()；kill 后再以短超时 wait 一次回收；日志改放 DATA_DIR/logs 下并以 O_EXCL 创建。

- [Info][95] src/backend/main.py:300-505 — main.py 单文件 1843 行混合应用装配、RFB 协议转译、双 WS 代理与全部 CRUD，browser_manager.py 亦达 1220 行，变更耦合面大

    - ID: f_backend_core_16; verification: static
    - Evidence: main.py 同时包含：应用/中间件装配、KasmVNC RFB 消息过滤与重写（约 300-505 行）、VNC 代理、CDP 代理、profile/产物/设置/更新检查全部路由、SPA 托管; RFB 过滤已有独立测试文件（src/backend/tests/test_rfb.py，单元外）表明其可独立成模块；vnc 代理函数内还直接访问 browser_mgr.vnc.\_allocated 私有成员（main.py vnc_proxy 尾部）
    - Impact: 任一协议级小改都要在巨型文件中定位并承担全应用回归面；私有成员跨模块访问使 VNCManager 的重构被 main.py 锁死。
    - Fix: 随 t011 legacy 收敛一并处理：若 legacy 保留，应把 RFB 转译与两类 WS 代理拆为独立模块并为 VNCManager 补公开的实例查询方法；若按计划删除 legacy，则本条随删除关闭，不必单独投入。

- [Medium][95] src/backend/tests/test_api.py:351-395 — 剪贴板测试只断言 HTTP 结果：日志安全性无断言、xclip 实际写入未验证、多条分支未触达，f_backend_core_02 的泄漏在测试下可任意存续

    - ID: f_backend_core_17; verification: static
    - Evidence: test_set_clipboard_success（test_api.py:360-383）mock 了 create_subprocess_exec，但从未断言 mock_proc.stdin.write 被以提交文本调用——处理器即使什么都不写也会通过；断言面只有 status 200 与 {"ok": True}; test_get_clipboard_from_page 只断言返回 JSON 的 text 字段；两条测试均无 caplog 或任何日志断言（全 tests 目录仅 test_downloads.py 一处使用 caplog，与剪贴板无关）; 生产 set_clipboard 的第一行即 logger.info(... preview=%r...)（main.py:1301），在 running 检查之前执行——连 test_set_clipboard_not_running 都会把文本写进日志，而该测试只断言 404; 未触达分支：SET/GET 的 409（viewer_mode!= vnc 或 display 为 None；现有 mock_running 恒 display=100 且默认 docker runtime）、GET 的 xclip 回退（含超时与非零退出码返回空文本）、GET 的 \_CLIPBOARD_MAX_READ 截断、SET 对同 display 旧 xclip 进程的 kill/替换（main.py:1298-1432）
    - Impact: f_backend_core_02（剪贴板正文进日志）这类安全回归没有任何测试能报警：泄漏被引入、保留或扩大（如 preview 长度从 60 提到全文）时套件保持全绿；同时 SET 的核心可观察效果（文本字节确实送达 xclip）本身也未被钉住，端点退化为空转 200 同样无感。
    - Fix: 为 SET/GET 各补一条 caplog 断言：日志记录可含长度与 profile_id，但提交/读取的哨兵文本不得出现在任何日志记录中；SET 测试补断言 stdin.write 收到的字节等于请求文本；补 409 分支（native runtime 或 display=None）与 GET xclip 回退（page.evaluate 返回空 + mock xclip 输出）的用例。

- [High][90] src/backend/main.py:1835-1843 — SPA catch-all 静态托管全套件零测试：正常发文件与路径穿越拒绝均无回归网，f_backend_core_01 无测试兜底

    - ID: f_backend_core_18; verification: static
    - Evidence: 对 src/backend/tests/ 全目录 grep serve_spa、index.html、full_path、FRONTEND_DIR、StaticFiles、dist 均零命中；无任何测试请求根路径或任一静态路径; serve_spa 是生产前端的唯一入口（catch-all 返回 dist 文件或 index.html），且 AuthMiddleware 对非 /api/ 路径直接放行——它是无认证的文件服务面; f_backend_core_01 已静态判定该处理函数以 FRONTEND_DIR / full_path 直接 FileResponse、无 resolve/包含校验（suspected 路径穿越）；此行为既没有被任何测试复现，也没有被任何测试钉住安全形态
    - Impact: 修复穿越时无既有测试可验证修复不破坏正常静态托管（index 回退、带 hash 的资源文件、嵌套路由路径）；不修时也无测试能在将来 FRONTEND_DIR 布局或 Starlette 版本变化使穿越变得可达时报警。该路由同时是全单元唯一完全裸奔的承重路径。
    - Fix: 补 TestClient 用例（以临时 FRONTEND_DIR 或 monkeypatch 指向 fixture 目录）：正常资源与未知路径回退 index.html 各一；穿越用例（../ 与 %2e%2e 编码变体指向目录外哨兵文件）断言不返回哨兵内容（404 或回退 index）。穿越用例在当前实现下预期失败，应作为 f_backend_core_01 的复现测试先行落盘。

- [Medium][90] src/backend/tests/test_database.py:35-63 — 数据库自动重建测试只覆盖已知/可翻译列：旧表含列集外列时的静默丢弃（f_backend_core_06 的破坏方向）无任何用例

    - ID: f_backend_core_19; verification: static
    - Evidence: 唯一的重建用例 test_init_db_rebuilds_old_schema_preserving_profile_and_tags 的旧表列全部是 legacy 已知列或有显式翻译的列（gpu_vendor->gpu_family 等），断言面是『已知数据保留 + 旧列消失 + 新列默认值』; 旧表从未包含任何 legacy 列集之外的列（如 v2 schema 的 runtime_mode/viewer_mode/current_config_version）；而 \_rebuild_profiles 的 copied 只取交集（database.py:104-185），列集外列被静默丢弃正是 f_backend_core_06 指出的破坏路径; 该用例因此与 f_backend_core_06 的修复方向（对『旧列集多于新列集』拒绝自动重建）直接冲突：一旦按建议改为 fail-closed，本用例仍通过，但若不改，丢弃行为也无用例记录——当前测试无法区分『按设计翻译』与『无声丢数据』
    - Impact: 双栈并存期间（f_backend_core_03），任一工具误把 legacy init_db 指向带 v2 列的数据库时的数据丢失没有任何测试层面的记录或报警；将来收紧重建策略时也没有用例界定哪些旧形态必须保留、哪些必须报错。
    - Fix: 补一条用例：旧表额外带 runtime_mode/viewer_mode/current_config_version 三列且含数据，断言期望行为（按最终决策：或报错拒绝重建且原表不动，或明确保留/迁移该数据）；决策未定前至少以 xfail/文档化断言把当前『静默丢弃』钉为已知行为，避免无声漂移。

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "1eb2940a-1591-4be7-9705-de9d7c51c4df"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "1eb2940a-1591-4be7-9705-de9d7c51c4df"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "1eb2940a-1591-4be7-9705-de9d7c51c4df"
  },
  "performance": {
    "status": "completed",
    "reviewer": "1eb2940a-1591-4be7-9705-de9d7c51c4df"
  },
  "design": {
    "status": "completed",
    "reviewer": "1eb2940a-1591-4be7-9705-de9d7c51c4df"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "1eb2940a-1591-4be7-9705-de9d7c51c4df"
  },
  "tests": {
    "status": "completed",
    "reviewer": "82c921a9-332e-46c3-a441-938249245c44"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "1eb2940a-1591-4be7-9705-de9d7c51c4df"
  }
}
```

## files_reviewed

```json
[
  "pyproject.toml",
  "src/backend/artifacts.py",
  "src/backend/browser_manager.py",
  "src/backend/cbrowser/secret_files.py",
  "src/backend/database.py",
  "src/backend/diagnostics.py",
  "src/backend/downloads.py",
  "src/backend/env_file.py",
  "src/backend/main.py",
  "src/backend/migrations/alembic.ini",
  "src/backend/migrations/env.py",
  "src/backend/migrations/script.py.mako",
  "src/backend/migrations/versions/0001_initial_schema.py",
  "src/backend/migrations/versions/0002_auth.py",
  "src/backend/migrations/versions/0003_artifact_storage.py",
  "src/backend/models.py",
  "src/backend/requirements.txt",
  "src/backend/runtime.py",
  "src/backend/settings_store.py",
  "src/backend/vnc_manager.py"
]
```
