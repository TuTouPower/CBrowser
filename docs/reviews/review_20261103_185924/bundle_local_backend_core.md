# bundle_local_backend_core

## responsibilities

- legacy 单体应用骨架：src/backend/main.py（1843 行）是 FastAPI 入口，承载 profile CRUD、启停、VNC/CDP WebSocket 代理、剪贴板中继、产物上传/下载、设置、关机与 SPA 托管；AuthMiddleware 在 AUTH_TOKEN 设置时对 /api/* 做 Bearer/cookie 校验，未设置时全放行
- browser_manager.py：CloakBrowser 持久上下文的启停/追踪、CDP 端口预留、license 拒绝文件解读、搜索默认引擎一次性设置、截图循环、hold_stopped 文件系统互斥
- database.py：legacy profiles.db 的手写 sqlite 层（profiles/profile_tags/artifacts），含按列集差异触发的整表重建迁移；artifacts.py/downloads.py 实现每-profile 产物存储（流式落盘、配额、picker 视图符号链接）与 CDP 下载捕获状态机
- v2 数据面入口：migrations/ 是 cbrowser.db 的 Alembic 链（0001 八表初始 → 0002 auth → 0003 artifact sha256/storage_path → 0004 删 profiles 的 runtime_mode/viewer_mode 列 → 0005 automation token 过期 → 0006 清理 config 快照中的 mode 键）
- 支撑模块：runtime.py 解析宿主 OS/运行模式/数据目录；settings_store.py 以原子写存 settings.json（license key 等）；env_file.py 把 manager 根 .env 载入 os.environ；diagnostics.py 提供启动指纹、崩溃钩子、stderr tee 与运行时事件脱敏日志；secret_files.py 是 v2 内部凭据文件的严格权限读取器；vnc_manager.py 管理 KasmVNC 显示号/端口分配与进程生命周期

## interfaces

- legacy REST：/api/auth/{status,login,logout}、/api/profiles CRUD + reorder/reset/duplicate、/api/profiles/{id}/files（上传/下载/删除）、launch/stop/status、/api/health、/api/status、/api/update-check、/api/open-external、/api/shutdown、/api/settings、/api/profiles/{id}/clipboard（GET/POST）、center-window
- legacy WS：/api/profiles/{id}/vnc（RFB 过滤/剪贴板转译代理）、/api/profiles/{id}/cdp 与 /cdp/devtools/{path}（CDP 透传，附下载行为变更检测）
- 进程内接口：database.* 同步函数被 async handler 直接调用；BrowserManager.running/get_status/is_active/hold_stopped 供 main.py 全部端点使用；Alembic env.py 以 adapters.database.models.Base 为 target_metadata

## dependencies

- cloakbrowser（launch_persistent_context_async、license、geoip）、fastapi/starlette、httpx、websockets（CDP/VNC 代理）
- sqlite3（legacy 手写层）与 SQLAlchemy/Alembic（仅 migrations/env.py 引用 v2 models）双轨并存
- KasmVNC Xvnc 进程（vnc_manager 以 subprocess 拉起，-interface 127.0.0.1、SecurityTypes None，靠 FastAPI 代理对外）
- GitHub releases API（update-check，6 小时缓存）；宿主默认浏览器（webbrowser.open）

## flows

- 启动：load_env_file → 数据库/日志初始化 → lifespan 中 init_db（列集不符则整表重建）→ artifacts.reclaim_all 回收未发布字节 → cleanup_stale → resolve_binary_status（线程）→ auto_launch_all
- 上传：X-File-Name 解码+safe_filename → Content-Length 预检 413 → check_quota(declared) → save_stream 流式落 .incoming 后原子 replace → check_quota(真实 size) → create_artifact 建行 → sync_picker_view
- 下载捕获：Browser.setDownloadBehavior allowAndName 到 staging → downloadWillBegin 建 pending 行 → downloadProgress 终态时 _publish（真实大小复检配额后 os.replace 发布）或 _discard/_fail
- 关闭浏览器：context close 事件 → _on_browser_closed 读 denial 文件记录 last_error → _dispose_running 取消截图/下载任务并 reconcile 未决下载

## constraints

- AUTH_TOKEN 是 legacy 唯一的访问控制：未设置即全开放（代码注释明示为 local dev 语义）；部署侧缓解（compose 绑 127.0.0.1 且注入 AUTH_TOKEN）在本单元之外
- legacy 与 v2 两套数据库（profiles.db 手写 DDL vs cbrowser.db + Alembic）同仓并存，schema 演进互不感知；legacy init_db 以列集相等为唯一版本判据
- 静态审阅：未运行任何代码/测试/构建，运行期行为结论按 suspected/static 区分

## decisions

- 产物字节以 artifact id 为目录信任边界、文件名只做 safe_filename 净化；配额在到达时与发布时各检一次（但建行在两次检查之后，见 f_backend_core_06）
- 下载只认 Chromium 事件终态发布，不认目录中出现文件；被外部 CDP 客户端改道下载路径的事件按 guid/staging 存在性甄别归属
- profile 状态操作以 hold_stopped + _stopping 计数预留保证 launch 与文件系统操作不交错；克隆先填目录后建行，半成品克隆不可见
- 0004/0006 迁移把 runtime_mode/viewer_mode 从『每-profile 存储值』收敛为运行时推导值，快照中的旧键就地清除且 downgrade 不恢复（单值常量的既定取舍）

## evidence

- src/backend/main.py:1301,1399 剪贴板日志行与 src/backend/diagnostics.py:280 的脱敏承诺原文对照
- src/backend/main.py:1835-1843 serve_spa 实现；src/backend/main.py:305-330 AuthMiddleware 对非 /api/ 路径的放行分支
- src/backend/database.py:104-160 _rebuild_profiles 全文（copied 列集逻辑在 :122）
- src/backend/main.py:900-937 上传端点四步顺序（预检、save_stream、复检、create_artifact）
- src/backend/migrations/versions/0004_remove_runtime_viewer_mode.py 与 0006_clean_snapshot_modes.py 全文；grep 确认 src/backend/cbrowser/adapters/database/models.py 已无 runtime_mode/viewer_mode 列，模型与迁移一致
- compose.yaml:11,17（单元外上下文）：端口绑 127.0.0.1 且注入 AUTH_TOKEN——部署侧缓解存在，但不改变应用代码默认
- grep src/backend/tests：serve_spa/full_path 零命中；git log 显示 main.py/database.py 自重组提交 524e34e 后未再修改（legacy 栈冻结状态）

## uncertainties

- f_backend_core_02（serve_spa 穿越）的运行期可达性取决于随仓 Starlette/uvicorn 对 %2e%2e%2f 的解码与点段处理，本轮静态审阅未做运行复现，verification 标 suspected
- 生产启动路径中是否存在不经 compose 的 legacy 入口（原生冻结应用同样加载 main.py，其监听绑定与 AUTH_TOKEN 注入由本单元之外的入口决定），决定 f_backend_core_03 的实际暴露面
- 本单元 tests 视角为 partial：断言级覆盖裁决（尤其 test_api.py 对剪贴板端点到底断言了什么）在 backend_tests 单元，本单元未逐行核对
- tests 视角由独立 viewfix 补审完成（原审阅者仅做定点 grep）：补审全量通读 backend_tests 单元 11 个文件（src/backend/tests/*，约 4,700 行），并对 main.py 全部路由及 open-external/shutdown/serve_spa/env_file 等关键字在 src/backend/tests、tests/unit、tests/integration 三处做定点 grep 核对；结论基于静态阅读，未运行测试。v2 迁移链（migrations/）的覆盖位于 tests/unit 的模型↔迁移漂移检查、不在 backend_tests 单元内，本补审未逐行复核该部分；secret_files.py 的覆盖同样在 tests/unit（test_secret_file_permissions.py），已定点确认存在。

## Findings

- [High][95] src/backend/main.py:1301 — 剪贴板正文被写入 manager.log，与 diagnostics 的脱敏承诺直接冲突
  - ID: f_backend_core_01; verification: static
  - Evidence: main.py:1301 set_clipboard 在检查 profile 是否运行之前就执行 logger.info("Clipboard SET ... preview=%r", ..., body.text[:60])，剪贴板前 60 字符原文进日志；404 的请求同样落盘; main.py:1399 get_clipboard 的 CDP 读取路径同样以 preview=%r 记录 text[:60]; diagnostics.py:280 emit_runtime_event_log 的 docstring 明示 "Never logs passwords, tokens, cookies, clipboard content, or private strings"——同一日志体系内的承诺与实现相反; diagnostics.py 模块 docstring 表明 manager.log 的设计用途就是供用户在支持场景中提交/分享（make a crash diagnosable from the rotating manager.log alone），剪贴板常含密码等凭据，落盘即随日志外发
  - Impact: 用户复制的任意文本（含密码、令牌、私密内容）以明文进入 2MB×3 轮转的 manager.log；该文件正是项目设计上要被发给支持方的诊断材料，构成凭据随日志泄漏的现实通道；且日志行在鉴权后的业务校验之前执行，未运行 profile 的伪造请求也能把任意文本写进日志（日志注入/污染）。
  - Fix: 删除两处 preview=%r，只保留 text_len 与 profile_id；如需调试内容，改为记录长度与不可逆摘要（如 sha256 前 8 位）。同时排查 cbrowser.events 之外的其他 logger 是否还有同类正文记录。

- [High][85] src/backend/main.py:1835-1843 — serve_spa 兜底路由无路径包含校验，疑似可未授权穿越读取应用文件
  - ID: f_backend_core_02; verification: suspected
  - Evidence: serve_spa 实现：file_path = FRONTEND_DIR / full_path；仅判 exists() 与 is_file() 即 FileResponse 返回，无 resolve() 后的 containment 校验；full_path 为 Starlette path 转换器捕获的解码后路径; AuthMiddleware（main.py:305-330）对非 /api/ 路径直接放行，SPA 路由不在鉴权范围内——穿越一旦可达即未授权; uvicorn 将请求目标百分号解码后写入 scope path，Starlette 路由不对 path 参数做点段折叠；以 ..%2f / %2e%2e%2f 形式构造的 full_path 可使 FRONTEND_DIR / full_path 指向 dist 之外（源码、profiles.db、.env 所在层级取决于部署布局）; 本轮为静态审阅，未做运行复现；随仓 fastapi/starlette 无版本锁定（requirements.txt 为 >= 浮动），具体构建的解码行为决定最终可利用性
  - Impact: 若穿越可达，局域网/本地任意未授权请求可读取 Manager 进程可读的任意文件，包括后端源码、含全部 profile 配置与代理凭据的 profiles.db、.env 中的 AUTH_TOKEN 与 license key——拿到 AUTH_TOKEN 后整个 /api 面随之失守。
  - Fix: serve_spa 改为先 resolved = (FRONTEND_DIR / full_path).resolve()，仅当 resolved 位于 FRONTEND_DIR.resolve() 之内且为文件时返回，否则回退 index.html；或改用 StaticFiles(html=True) 挂载（其 lookup_path 自带包含校验）。同时补 %2e%2e%2f 与 ../ 两类穿越的回归测试。

- [Medium][90] src/backend/main.py:143-147 — legacy 应用鉴权为代码级 opt-in：AUTH_TOKEN 未设置时全部 /api/* 无条件放行
  - ID: f_backend_core_03; verification: static
  - Evidence: _check_auth 在 AUTH_TOKEN is None 时直接 return True（main.py:146）；AuthMiddleware 在 not AUTH_TOKEN 时对所有 scope 直通（main.py:309）; 文件头注释明示该语义："If not set, all routes are open (local dev)"; 放行面包括 /api/shutdown、/api/open-external、profile 的 CDP/VNC 代理与文件上传下载——即浏览器身份的 cookie 目录可达面; 单元外上下文：根 compose.yaml 已绑 127.0.0.1 并注入 AUTH_TOKEN（compose.yaml:11,17），出厂 Docker 路径有缓解；但原生冻结应用与直接 uvicorn 启动同样加载本文件，其绑定与 token 注入不在本应用控制内
  - Impact: 任何不经该 compose 的启动方式（原生应用、开发直跑、第三方改编 compose）都会得到一个零凭据的管理面；『空 token = 开放』的语义靠部署纪律兜底，而非应用自身 fail-closed。
  - Fix: 将默认改为 fail-closed：AUTH_TOKEN 未设置时仅监听回环并在日志中明确警告，或直接拒绝启动并给出生成方式；至少把『开放模式』改为显式环境变量（如 CBROWSER_ALLOW_NO_AUTH=1）而非空值默认。

- [Medium][80] src/backend/main.py:1171-1183 — /api/open-external 缺少 /api/shutdown 已有的同源 CSRF 防护，可被跨站简单请求触发打开宿主浏览器
  - ID: f_backend_core_04; verification: static
  - Evidence: shutdown_manager（main.py 约 :1237 起）专门调用 _same_origin_request 并注释说明 bodyless POST 是 CORS 简单请求、无预检即可跨站命中; open_external 同为状态改变型 POST 且无任何 Origin 校验；其 payload 为 dict，Starlette 按 JSON 解析请求体而不看 Content-Type，跨站 fetch 以 text/plain 发送 JSON 文本即构成简单请求、无需预检; 效果是 webbrowser.open 在宿主打开攻击者选定的任意 http(s) URL；同文件 /api/profiles/test-proxy 同样无 Origin 校验，可使服务端经任意代理发起连接（受害面较小）; AUTH_TOKEN 开启时 auth_token cookie 为 SameSite=strict，跨站请求不带 cookie，此路径主要在 auth 关闭（见 f_backend_core_03 的默认）时成立
  - Impact: 用户在原生应用模式下浏览任意恶意网页时，该网页可静默让宿主浏览器打开钓鱼/恶意 URL；在 auth 关闭的局域网部署下，同网段主机也可直接调用。与 f_backend_core_03 叠加时是默认配置下可达的跨站操作面。
  - Fix: 对 open_external（及 test-proxy 等无副作用豁免理由的 POST）统一应用 _same_origin_request 校验，与 shutdown 保持同一防护口径；或将同源校验提升为中间件级、覆盖全部状态改变型 /api POST。

- [Medium][90] src/backend/database.py:122 — init_db 整表重建静默丢弃列集之外的全部列数据，无日志无备份
  - ID: f_backend_core_05; verification: static
  - Evidence: init_db 以 old_columns != set(_PROFILE_COLUMNS) 为唯一触发条件进入 _rebuild_profiles；重建时 copied = [c for c in _PROFILE_COLUMNS if c in old_columns]，不在当前列集中的列（如另一 schema 代际写过的 runtime_mode/viewer_mode/current_config_version，或未来版本新增列）的数据不复制、随 DROP TABLE 消失; database.py 全文无 logging：丢弃发生时不留任何记录，运维无从察觉；重建前也不做 profiles.db 备份; 本仓恰有双轨 schema 并存（legacy 手写层与 v2 Alembic 0001 的 profiles 表含 current_config_version 等额外列），一个被 v2 侧碰过的 profiles.db 回到 legacy 启动即触发此路径; 对照：gpu_vendor/gpu_renderer 的旧值有专门的 CASE 映射保留逻辑，说明『保留用户数据』是该函数的既定意图，未知列的静默丢弃与之不一致
  - Impact: 跨版本/跨栈切换启动一次即可永久丢失列集外数据且无声无息；对以 profile 配置（代理、指纹、备注）为核心资产的应用，这是升级路径上的静默数据损失点。
  - Fix: _rebuild_profiles 前先把将被丢弃的列名与行数写日志，并把原表改名保留为 profiles_backup_<timestamp> 而非直接 DROP；或对未知列直接中止启动并报错，让迁移走显式 Alembic/脚本路径。

- [Medium][85] src/backend/main.py:909-937 — 产物配额检查与建行分离，并发上传可绕过每-profile 数量与总量上限
  - ID: f_backend_core_06; verification: static
  - Evidence: 上传顺序：check_quota(declared) → save_stream 落盘 → check_quota(真实 size) → db.create_artifact 建行；artifacts.check_quota 的计数依据是 db.list_artifacts 的现有行数与 ready 行 size 之和; 两次检查时本次上传的行都还不存在；两个并发上传同一 profile 时，各自看到的都是上传前状态，可双双通过，最终行数与总字节同时越限; chunked 请求 declared 为 None 时预检 incoming=0，数量上限在建行前对任何并发都无约束；发布后复检同样看不到对方未建行的字节; artifacts.save_stream 本身只执行单文件 MAX_ARTIFACT_BYTES 上限，不做 profile 级记账
  - Impact: 在本机/局域网可达的管理面上，并发上传可把单 profile 产物数量推过 200、总量推过 2GiB 上限，配额从硬约束降为串行场景下的软约束；磁盘占满会连带影响同数据盘上的 profiles.db 与浏览器状态。
  - Fix: 把配额记账前移到落盘之前并串行化：例如先以 pending 行占位（size=预估/0）再流式写入、发布时以 replacing 语义复检（downloads._publish 已采用此模式），或对 check+create 加 per-profile 锁。

- [Low][90] src/backend/database.py:66-76 — 同步 sqlite 与文件系统调用遍布 async handler，且 list_profiles 为 N+1 标签查询
  - ID: f_backend_core_07; verification: static
  - Evidence: get_db 每次调用新建连接并重复执行 WAL/foreign_keys pragma；全部 db.* 函数为同步实现，被 main.py 的 async 端点直接调用，无一处 to_thread 卸载; _hydrate_profile 对每行单独查 profile_tags，list_profiles 为 N+1；get_system_status、auto_launch_all 均走此路径; upload/download/delete 端点在事件循环内联调用 artifacts.sync_picker_view（iterdir + 逐个 resolve 符号链接）与 refresh_picker_bookmarks（全量重建）; 单用户小规模下影响有限，但产物多、profile 多时单次列表/上传会以同步 IO 阻塞全部会话（含 WS 代理的心跳与帧转发）
  - Impact: 规模增长后表现为全应用级卡顿而非单请求变慢：任一重列表/大批量产物操作都会冻结同进程的 VNC/CDP 代理转发。
  - Fix: list_profiles 的标签查询改为一次 IN 查询后按 profile_id 分组；重型同步段（picker 视图重建、list_profiles 全量水合）经 asyncio.to_thread 卸载，或给连接加缓存复用。

- [Low][85] src/backend/models.py:13-44 — ProfileCreate/Update 缺数值范围与长度校验，异常值直达 Xvnc 几何与 Chromium 参数
  - ID: f_backend_core_08; verification: static
  - Evidence: screen_width/screen_height 为裸 int（可负、可为天文数字），fingerprint_seed 为任意 int，name/notes/proxy 无 max_length，launch_args/extension_paths 列表长度与单项长度均无上限; 这些值未经范围检查即进入 vnc_manager.start_vnc 的 -geometry 参数、browser_manager 的 --window-size 与 --fingerprint-screen-* 参数（browser_manager._build_fingerprint_args）; 对照同文件 ClipboardRequest 有 max_length、ProxyTestRequest 有 min/max_length——校验口径在模型间不一致; 结果多为启动期失败（Xvnc 以非法 geometry 退出、launch 500）而非数据损坏，故定 Low
  - Impact: 误填或恶意构造的 profile 配置可让启动路径以难懂的底层错误失败（Xvnc 退出日志、CDP 超时），排障成本高；超长字段还会撑大 profiles.db 与列表响应。
  - Fix: 给 screen_width/height 加合理区间（如 320–7680）、name/notes/proxy 加 max_length、launch_args/extension_paths 加列表与单项长度上限，与 ClipboardRequest 的既有口径对齐。

- [Low][90] src/backend/browser_manager.py:56-71 — _normalize_proxy 以冒号切分启发式解析，含冒号/＠的凭据与 IPv6 主机会被误解析
  - ID: f_backend_core_09; verification: static
  - Evidence: _normalize_proxy 对 host:port:user:pass 形式做 raw.split(":")，密码含 ':' 时段数不为 4，整串原样返回，随后 _validate_proxy 以 scheme 缺失等不相干理由报错；密码含 '@' 时即使走 http:// 直通路径，后续 urlparse 也会错位主机; 拼装 f"http://{user}:{passwd}@{host}:{port}" 时 user/passwd 未做 URL 编码，含特殊字符的凭据会改变 URL 结构; IPv6 主机（含多个冒号）在任何分支下都无法正确处理; test_proxy 与 launch 共用此函数，错误在两处一致地表现为『代理不可用』类误报
  - Impact: 使用含特殊字符密码的常见住宅代理格式会静默失败或连到错误端点，用户只能得到与真实原因无关的验证错误；属正确性缺陷而非安全问题（输入来自 profile 所有者本人）。
  - Fix: 四段式解析改为从右侧切分（rsplit）并对凭据做 quote 后再拼 URL，或要求四段式先按 host:port 与 user:pass 两组各切一次；补含 ':'/'@' 密码与 IPv6 的单测用例。

- [Low][90] src/backend/artifacts.py:22-24 — _env_int 对畸形环境变量未捕获 ValueError，模块导入期即崩溃且报错不指向配置项
  - ID: f_backend_core_10; verification: static
  - Evidence: _env_int 直接 int(os.environ.get(name) or default)，ARTIFACT_MAX_BYTES/ARTIFACT_MAX_COUNT/ARTIFACT_MAX_TOTAL_BYTES 任一被设为非数字（如带单位的 '512M'）即在 import artifacts 时抛 ValueError; artifacts 被 main.py 顶层导入，异常使整个应用启动失败，traceback 只指向 int() 转换，不含变量名上下文; 同文件其余配置路径（picker、quota）都有明确的异常类型与文案，此处口径不一致
  - Impact: 运维误配一个环境变量即全站无法启动，且排障线索最差（导入期裸 traceback）。概率低、后果集中在可用性。
  - Fix: _env_int 捕获 ValueError 后抛带变量名与原始值的 RuntimeError，或回退默认值并 logger.warning 记录被忽略的畸形值。

- [Low][95] src/backend/requirements.txt:1-9 — requirements.txt 与 pyproject.toml 依赖声明漂移：同一包版本约束冲突且集合互不一致
  - ID: f_backend_core_11; verification: static
  - Evidence: cloakbrowser[geoip]：pyproject.toml 钉 ==0.6.4，requirements.txt 写 >=0.6.3; requirements.txt 不含 pyproject 的 sqlalchemy/alembic/aiosqlite/docker/argon2-cffi/aiohttp，却多出 pyproject 没有的 pywebview；实际装哪套取决于入口（各 runtime Dockerfile 在其他单元）; requirements.txt 全部为 >= 浮动约束且无 lock 文件，legacy 栈的实际解析版本随安装时点漂移（pyproject 侧同样多为 >=，仅 cloakbrowser 钉版）
  - Impact: 同一代码在不同安装路径下解析出不同依赖组合，『在我这能跑』类问题难以归因；框架行为差异（如 Starlette 路径解码）还会让 f_backend_core_02 这类结论的可达性随安装路径变化。
  - Fix: 明确单一权威依赖源（pyproject + 生成的 lock），requirements.txt 改为由其生成或删除；至少把 cloakbrowser 的约束对齐为 ==0.6.4 并注明 pywebview 仅属原生入口。

- [Low][55] src/backend/main.py:1560-1600 — VNC 代理以 WebSocket 帧数而非 RFB 字节流计数握手，前 3 帧假设与分片方式耦合
  - ID: f_backend_core_12; verification: suspected
  - Evidence: client_to_vnc 以 handshake 计数器按 WS 消息递增，前 3 条消息原样转发、之后才走 _filter_rfb_client_messages；RFB 握手是字节流协议，帧边界由 noVNC 的发送方式偶然决定; 若客户端把握手字节拆成 4 条以上 WS 消息，第 4 条起的握手残余会被当作普通客户端消息过滤（未知类型即截断丢弃），可致协商损坏、连接建立失败; 反之若首帧合并了握手与后续消息，整帧原样放行会绕过编码白名单过滤（当前实现对此情形无防护，但 KasmVNC 对 SetEncodings 的处理在握手后消息中才有意义，影响有限）; 本轮静态审阅未构造实际分片序列复现，noVNC 1.4 的默认发送方式是否触发未知
  - Impact: 在 noVNC 或网络层改变分片方式时，VNC 连接可能以『握手后立即断开』的难复现方式失败；属健壮性隐患而非当前已证故障。
  - Fix: 改为按字节流状态机识别握手完成（ProtocolVersion 12 字节 + SecurityTypes 协商结束）后再启用过滤，或把过滤器改为对未完成握手前缀透传并缓存残余字节。

- [Info][90] src/backend/settings_store.py:22-29 — settings_store 对损坏 JSON 静默回退为空设置，license key 无声失效且无日志
  - ID: f_backend_core_13; verification: static
  - Evidence: load_settings 捕获 FileNotFoundError/JSONDecodeError/OSError 一律返回 {}，不区分『从未设置』与『文件损坏』，也无任何日志; main.py 在导入期以 _STORED_SETTINGS 解析 LICENSE_KEY，文件损坏时应用以 keyless 模式启动，用户只会看到 tier 变化而不知原因; settings.json 内含 license key 明文（save_settings 经 mkstemp 落盘，POSIX 下为 0600），属原生应用的既定取舍，此处仅记录
  - Impact: 设置文件损坏的故障形态是『Pro 功能静默消失』，排障需比对文件内容才有线索；与本仓其他模块的显式报错口径不一致。
  - Fix: JSONDecodeError 时 logger.warning 记录文件路径与异常，并把损坏文件改名保留（如 settings.json.corrupt-<ts>）后再回退空设置。

- [Info][95] src/backend/main.py:1690-1705 — 跨模块私有成员耦合：main.py 直读 vnc._allocated 并回写 browser_mgr._auto_launch_task
  - ID: f_backend_core_14; verification: static
  - Evidence: vnc_proxy 的收尾路径以 browser_mgr.vnc._allocated.get(running.display) 判断 Xvnc 存活，绕过 VNCManager 已有的 active_displays/get_ws_port 公共面（但公共面不提供 process 存活状态，这正是耦合的成因）; lifespan 中 main.py 直接赋值 browser_mgr._auto_launch_task；browser_manager 侧多处读 context 的 _cloak_denial_path 私有属性（上游 wrapper 约定）; 当前均能工作，但任一侧重构私有结构都会以 AttributeError 形式在运行期暴露，无类型/契约层面的约束
  - Impact: 可维护性风险：VNC 存活判断与任务句柄管理的所有权分散在两个模块，后续修改 VNCManager 内部结构时容易漏改 main.py 的直读点。
  - Fix: 在 VNCManager 上补 is_alive(display) 公共方法供代理收尾使用；_auto_launch_task 改由 BrowserManager 提供 start_auto_launch()/属性 setter 管理。

- [Medium][80] src/backend/main.py:1835-1843 — serve_spa 与剪贴板日志行为在本单元自有测试落点中零覆盖（据定点 grep）
  - ID: f_backend_core_15; verification: static
  - Evidence: grep src/backend/tests（本单元代码的包内测试落点）对 serve_spa/full_path 零命中——SPA 兜底的正常服务与穿越拒绝两个方向都没有任何用例钉住; test_api.py 等文件出现 clipboard 字样，但本轮未逐行核对断言内容；f_backend_core_01 的日志泄漏行为没有任何 caplog 类断言被本单元审阅所见; 本单元 tests 视角因此标 partial：断言级裁决在 backend_tests 单元，此处仅记录可定点验证的缺席事实
  - Impact: f_backend_core_01/02 这类缺陷即使被修复，也没有任何本单元落点的回归网阻止其复发；SPA 服务路径重构（换 StaticFiles、改挂载顺序）时无测试能发现穿越面或正常面被打坏。
  - Fix: 在 src/backend/tests/test_api.py 补 serve_spa 用例：正常静态文件、index.html 回退、api/ 前缀 404、../ 与 %2e%2e%2f 穿越拒绝；并给剪贴板端点加 caplog 断言（日志只含长度、不含正文）。

- [Medium][90] src/backend/main.py:1171（open-external）、src/backend/main.py:1220（shutdown） — 宿主机控制端点测试缺口：/api/open-external 零测试，/api/shutdown 只测了拒绝路径
  - ID: f_backend_core_16; verification: static
  - Evidence: 对 open-external / open_external 在 src/backend/tests、tests/unit、tests/integration 三处 grep 均为零命中——该端点在整个测试树中没有任何一例测试。; test_api.py:669-681 对 /api/shutdown 只有跨源、跨端口两条 403 拒绝用例，另有 _same_origin_request 纯函数用例（test_api.py:684-708）；同源请求真正进入关闭流程的成功路径从未被测。; 与 f_backend_core_04 对照：open-external 恰是缺了 shutdown 已有同源 CSRF 防护的那个端点，最需要回归网的端点反而一例测试都没有。
  - Impact: 这两个端点直接作用于宿主机（在宿主上打开外部浏览器、终止 Manager 进程）。open-external 的防护现状或 shutdown 的同源成功路径若被后续改动悄悄改坏（例如中间件调整误伤 _same_origin_request 的复用），没有任何测试会变红。
  - Fix: 为 /api/open-external 补跨源拒绝与同源成功（mock 掉实际打开动作）成对用例；为 /api/shutdown 补同源请求进入关闭流程的用例（mock 掉实际退出动作），与现有拒绝用例成对。

- [Low][90] src/backend/main.py:583（test-proxy）、:1184（update-check）、:1335（center-window）、:1622（screenshot） — 四个 legacy 路由在 backend_tests 中零覆盖：test-proxy、update-check、center-window、screenshot
  - ID: f_backend_core_17; verification: static
  - Evidence: 对 test-proxy/test_proxy、update-check/update_check、center-window/center_window、/screenshot 在 src/backend/tests 中 grep 均为零命中；通读该单元全部 11 个文件亦无这四个端点的调用（screenshot 仅以 user_data_dir 内的 last_screenshot.jpg 文件名出现）。; 对照之下，同文件的 profile CRUD、files、clipboard、settings、duplicate、CDP 代理等路由均有成组行为测试，这四个端点是路由表中的整片空白。
  - Impact: test-proxy 是创建 profile 前的代理连通性检查、update-check 驱动升级提示、screenshot 是前端预览图来源；它们多是对外部服务/子进程的薄封装，最容易被依赖升级或封装改动悄悄改坏响应形状与状态码，而本地测试无一拦截。
  - Fix: 给四个端点各补最小行为测试：依赖以 mock 注入，断言状态码与关键响应字段；test-proxy 额外覆盖代理不可达时的失败形状。

- [Low][85] src/backend/main.py:1434（vnc_proxy） — VNC 代理转发回路无端到端测试：纯函数层覆盖扎实，接线层空白，与 CDP 代理覆盖不对称
  - ID: f_backend_core_18; verification: static
  - Evidence: test_rfb.py（341 行）对 _rfb_msg_length、_filter_rfb_client_messages、_rewrite_set_encodings、_rewrite_pointer_event、_parse_kasmvnc_clipboard、_build_server_cut_text 有细粒度断言，纯函数层覆盖扎实。; test_api.py:592-659 对 /vnc WebSocket 只有 Origin 拒绝/放行四例，连接建立后即断开；从未接入假 KasmVNC 上游验证帧转发、过滤在真实流中的效果，或 KasmVNC 剪贴板消息（type 180）→ ServerCutText 的转换路径（main.py:1545-1549）。; 对照：CDP 代理回路有完整的假上游测试（test_api.py:1288 起的 _FakeUpstream 与 re-arm 系列），两条代理的覆盖明显不对称。
  - Impact: 过滤/改写逻辑与代理循环的接线（缓冲切分、偏移、剪贴板转换触发条件）若回归，纯函数测试仍会全绿；剪贴板中继是本单元的隐私敏感面，其端到端行为没有任何测试钉住。
  - Fix: 仿 CDP 的 _FakeUpstream 模式为 vnc_proxy 补假上游测试：标准帧透传、扩展消息剥离、KasmVNC 剪贴板消息转换三条路径各一例。

- [Info][90] src/backend/env_file.py — env_file.py 在全部测试树中零覆盖
  - ID: f_backend_core_19; verification: static
  - Evidence: 对 env_file 在 src/backend/tests、tests/unit、tests/integration 三处 grep 均为零命中。; 该模块（39 行）在 import 期把 manager 根 .env 载入 os.environ，是 AUTH_TOKEN 等配置进入进程的通道之一（与 f_backend_core_03 的鉴权默认行为相邻）。
  - Impact: 畸形行、引号与空值的解析行为若回归，只会在真实部署启动时暴露；解析逻辑简单，影响面小，故记 Info。
  - Fix: 补少量解析单测：键值、引号、空行/注释，以及与已存在环境变量同名时的当前语义各一例。

## views

```json
{
  "contracts": {
    "reviewer": "0594e549-361a-49c4-bf18-c6684b664e0c",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "0594e549-361a-49c4-bf18-c6684b664e0c",
    "status": "completed"
  },
  "design": {
    "reviewer": "0594e549-361a-49c4-bf18-c6684b664e0c",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "0594e549-361a-49c4-bf18-c6684b664e0c",
    "status": "completed"
  },
  "performance": {
    "reviewer": "0594e549-361a-49c4-bf18-c6684b664e0c",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "0594e549-361a-49c4-bf18-c6684b664e0c",
    "status": "completed"
  },
  "security": {
    "reviewer": "0594e549-361a-49c4-bf18-c6684b664e0c",
    "status": "completed"
  },
  "tests": {
    "reviewer": "35a17c6b-39b6-48e2-8c67-a3ce425b7866",
    "status": "completed"
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
  "src/backend/migrations/versions/0004_remove_runtime_viewer_mode.py",
  "src/backend/migrations/versions/0005_automation_token_expiry.py",
  "src/backend/migrations/versions/0006_clean_snapshot_modes.py",
  "src/backend/models.py",
  "src/backend/requirements.txt",
  "src/backend/runtime.py",
  "src/backend/settings_store.py",
  "src/backend/vnc_manager.py"
]
```
