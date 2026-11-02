# bundle_local_backend_tests

## responsibilities

- pytest 套件，覆盖 legacy 后端（src/backend/）的可观察行为：main.py 的 FastAPI 路由（profile CRUD/launch/stop/reset/duplicate、settings、clipboard、CDP/VNC 代理、shutdown CSRF）、database.py 的 SQLite CRUD 与旧 schema 迁移、models.py 的 Pydantic 契约、browser_manager.py 的 launch 生命周期与参数构建、vnc_manager.py 的 display/port 分配、artifacts.py 的文件产物配额/命名/回收、downloads.py 的 CDP 下载捕获会话、runtime.py 的平台策略、main.py 内 RFB 协议解析函数、AUTH_TOKEN 中间件
- conftest.py 在任何 backend 模块导入前向 sys.modules 注入 cloakbrowser 假模块（外部边界 mock），并提供 tmp_db/app_client/sample_profile/native_runtime/docker_runtime 夹具与 HOME 隔离

## interfaces

- HTTP 面：经 starlette TestClient 或直接驱动 ASGI app（test_artifacts.py 的 _drive_upload）调用 /api/profiles、/api/profiles/{id}/files、/api/settings、/api/auth/*、/api/status、/api/shutdown、WS /vnc 与 /cdp
- 模块面：直接调用 db.*、artifacts.*、downloads.DownloadTracker/_Session、BrowserManager/VNCManager 方法与 main.py 的路由协程（duplicate 生命周期交错测试）

## dependencies

- 被测实现：src/backend/{main,database,models,browser_manager,vnc_manager,artifacts,downloads,runtime,settings_store}.py
- pytest + pytest-asyncio（pyproject.toml:23 asyncio_mode = "auto"，未标注的 async 测试也会运行，已静态核对）
- unittest.mock（AsyncMock/MagicMock/patch）、starlette TestClient

## flows

- profile 创建→启动→停止/删除/重置/复制的主链路及并发 hold 语义（duplicate 复制期间 launch/reset/delete 应被 409 拒绝，取消须等工作线程结束并清理）
- 产物上行链路：声明长度预检（413/507 且不读 body）→ 流式落盘计数 → 配额 → picker 视图符号链接 → 启动回收无行字节
- 下载捕获链路：CDP Browser.downloadWillBegin/downloadProgress 事件 → staging → 发布/失败/幻影下载剔除 → 客户端 detach 后 re-arm
- 设置链路：PUT /api/settings 热更新 browser_mgr.license_key/release_channel 并落盘 settings.json，GET 时掩码返回

## constraints

- main.browser_mgr 是模块级单例（src/backend/main.py:295），全套件共享，所有对它的修改都是进程级可见的
- cloakbrowser 必须在导入期 mock（conftest.py:20-48），否则 browser_manager/main 无法导入；mock 用 sys.modules.setdefault，环境中若已有真实模块被先导入则 mock 不生效
- 套件不得启动真实浏览器/Xvnc/cloak 二进制：靠 monkeypatch 替换 launch_persistent_context_async、validate_available、cleanup_* 等
- async 测试依赖 asyncio_mode=auto；同步 TestClient 测试与 async 协程直调测试混排在同一文件（test_api.py）

## decisions

- artifacts/downloads 两个套件以文件系统+DB 行作为可观察断言面，并发用事件/队列脚本化 FakeSocket 驱动，属于行为级测试（本单元的质量标杆）
- duplicate 生命周期测试选择直接 await 路由协程并用 _PausableCopy 阻塞复制，以获得确定性的交错时序，代价是耦合 main 的私有符号（_copy_browser_state、_held、_launching）
- test_rfb 直接测 main.py 的私有协议函数（_rfb_msg_length 等），断言在字节级可观察，但与私有命名耦合

## evidence

- src/backend/tests/conftest.py:20-123（导入期 mock、tmp_db、app_client、HOME 隔离夹具）
- src/backend/tests/test_api.py:242-252（test_system_status 手工清理泄漏的 running 条目）
- src/backend/tests/test_api.py:1082-1089（real_lifecycle 夹具注释自述：早先测试替换 launch/stop 后从不还原）
- src/backend/tests/test_api.py:1099-1250（duplicate 并发 hold/取消的协程直调测试群）
- src/backend/tests/test_artifacts.py:472-605（ASGI 直驱验证超限请求在读 body 前被拒绝）
- src/backend/tests/test_downloads.py:252-581（FakeSocket 脚本化 CDP 会话、重连后下载发布）
- src/backend/tests/test_database.py:35-63（旧 schema 重建迁移的行为断言）
- pyproject.toml:23（asyncio_mode = "auto"）
- src/backend/main.py:295（browser_mgr 模块级单例）
- src/backend/browser_manager.py:505-528（生产 launch 过滤调试参数后追加 user_launch_args）

## uncertainties

- test_api.py 中出现的完整格式 license key 字面量是否为真实密钥，静态审阅无法判定；仅知其只出现在测试文件（全仓 grep 仅 3 处，均在 test_api.py），若为真实密钥则构成公开仓泄漏
- WebSocket origin 拒绝测试在运行时究竟因 origin 校验还是因后续代理连接失败而抛异常，静态无法区分——这正是 f_backend_tests_02 的疑点本身，未执行测试故不断言其必错
- 套件是否在 CI 中以 pytest-xdist 并行运行未核查；f_backend_tests_01 的影响在串行单进程下表现为顺序依赖，在并行下会放大

## Findings

- [High][90] src/backend/tests/test_api.py:143-206 — 多个测试用普通赋值替换单例 browser_mgr.launch/stop 且从不还原，造成跨测试污染与顺序依赖
  - ID: f_backend_tests_01; verification: static
  - Evidence: test_api.py:143 与 :867 直接执行 main.browser_mgr.stop = AsyncMock(...)；:196、:206 直接执行 main.browser_mgr.launch = AsyncMock(side_effect=...)，均非 monkeypatch，测试结束后不恢复; main.browser_mgr 是模块级单例（src/backend/main.py:295），赋值对整个 pytest 进程后续所有测试可见; test_api.py:1082-1089 的 real_lifecycle 夹具注释自述：『Earlier tests swap browser_mgr.launch/stop for AsyncMocks and never put them back; these tests need the real state machine』，并靠 BrowserManager.launch.__get__ 手工装回真方法; test_api.py:242-244 的 test_system_status 需手工 main.browser_mgr.running.clear() 并注释『Clear any leaked running profiles from prior tests』
  - Impact: 套件结果依赖文件内执行顺序：任何在 launch 被换成必抛异常的 mock 之后、又需要真实 launch 且未用 real_lifecycle 的新增测试会无故失败；改序、-k 子集运行或并行化（xdist 按文件分发时同文件仍同进程）都会放大。real_lifecycle 只修 launch/stop 两处，running 字典等其它泄漏仍靠各测试自觉清理
  - Fix: 将四处直接赋值改为 monkeypatch.setattr(main.browser_mgr, 'launch'/'stop', AsyncMock(...))，使夹具 teardown 自动还原；随后删除 real_lifecycle 的补救逻辑（或保留为空兼容），并让 running 注入统一走一个带清理的夹具

- [Medium][85] src/backend/tests/test_api.py:593-660 — WebSocket Origin 校验的正反两组测试都接近恒真：拒绝组接受任意异常，通过组只排除异常文本含 4403
  - ID: f_backend_tests_02; verification: static
  - Evidence: test_vnc_ws_rejects_cross_origin / test_cdp_ws_rejects_cross_origin（:593、:608）用 with pytest.raises(Exception) 包裹连接，任何异常（路由 404、代理连接失败、mock 缺失）都算通过; test_ws_allows_same_origin / test_ws_allows_no_origin（:623、:644）的判定是 except Exception as exc: assert '4403' not in str(exc)；若端点在 origin 校验之前就坏掉（如 CDP/VNC 代理抛其它错误），测试同样通过; 两组测试都无法区分『因 origin 被拒/放行』与『因无关原因失败』，origin 校验被整体删除时拒绝组大概率仍绿（连接会在代理阶段以其它异常失败）
  - Impact: CSWSH 防护（VNC/CDP WebSocket 的跨源拒绝）失去回归保护：校验逻辑被误删或改坏时套件不报警，属于验证假行为
  - Fix: 拒绝组改为断言具体的 WebSocketDisconnect 且 code == 4403（或握手 HTTP 403）；通过组改为先断言连接确实越过 origin 校验层（如连接建立成功或收到代理层特有的后续错误/帧），而非对任意异常做文本排除

- [Medium][90] src/backend/tests/test_browser_manager.py:204-233 — 三个 launch_args 测试在测试体内复刻生产拼接逻辑（args += profile['launch_args']），未驱动生产 launch 路径
  - ID: f_backend_tests_03; verification: static
  - Evidence: test_launch_args_appended_to_fingerprint_args / test_launch_args_empty_no_effect / test_launch_args_none_no_effect 均先调 _mgr._build_fingerprint_args(profile)，再由测试自己执行 args += profile.get('launch_args') or [] 并断言结果; 生产拼接位于 BrowserManager.launch 内（src/backend/browser_manager.py:505-528）：先过滤 --remote-debugging-* 冲突参数，再 extra_args += user_launch_args；测试体内的复刻不含过滤与顺序语义; 若生产 launch 停止追加 launch_args 或改了追加位置，这三个测试仍全部通过
  - Impact: launch_args 透传这一用户可配置行为的核心断言是假的；真实 launch 路径对该行为仅有 test_launch_passes_license_config（test_browser_manager.py:380 附近）顺带覆盖顺序，覆盖面与测试名给人的印象不符
  - Fix: 删除三个复刻型测试，改为经 manager.launch（mock launch_persistent_context_async）断言最终传给 cloak 的 options['args'] 包含且正确排序 launch_args，并覆盖空/None 情形；或至少将测试改名并注明其只验证 _build_fingerprint_args 与 launch_args 无关

- [Medium][95] src/backend/tests/test_auth.py:123-134 — test_logout_clears_cookie 名为验证登出清 cookie，实际只断言 200 与 ok=true，未验证 cookie 被清除
  - ID: f_backend_tests_04; verification: static
  - Evidence: 测试先 POST /api/auth/login，再 POST /api/auth/logout，仅 assert resp.status_code == 200 与 resp.json()['ok'] is True; 未检查 logout 响应的 Set-Cookie（过期/删除 auth_token），也未用登出后会话再请求受保护端点验证变为 401; 对照 test_login_correct_sets_cookie（:116-120）有 'auth_token' in resp.cookies 的实质断言，logout 侧明显弱化
  - Impact: 若 logout 处理器回归为不清 cookie（会话令牌继续有效），该安全相关行为无任何测试报警，测试名还会误导审阅者以为已覆盖
  - Fix: 补断言：logout 响应应删除/过期 auth_token cookie（如 Set-Cookie 含 Max-Age=0 或空值），且登出后同一 client 再 GET /api/profiles 应为 401

- [Low][80] src/backend/tests/test_api.py:1318-1385 — CDP detach 与数据库排序测试依赖固定 sleep 推进时序，存在慢 CI 下的假通过/假失败窗口
  - ID: f_backend_tests_05; verification: static
  - Evidence: test_api.py:1326 在 _run_proxied_client 中 time.sleep(0.05) 并注释『let the proxy run to the end after the browser hung up』，随后断言 seen_closed == [True]，代理任务推进速度依赖调度; test_api.py:1379 test_a_proxy_that_never_reached_the_browser_does_not_re_arm 用 time.sleep(0.1) 后断言 download_rearm 未 set——负断言靠『等够久』成立; test_api.py:1196、:1229 取消类测试在 task.cancel() 后 asyncio.sleep(0.05) 再断言任务未完成; test_database.py:220、:290、:342 用 time.sleep(0.01) 制造不同时间戳，排序/updated_at 断言依赖墙钟分辨率
  - Impact: 负载高的 CI 上可能偶发失败（flake）或反过来在代理尚未推进时假通过；负断言（rearm 未触发）在机器很慢时也可能在断言后才被推翻而无人察觉
  - Fix: 用可等待的同步点替代固定睡眠：如轮询等待条件（已有 _wait_for 模式）并对负断言等待一个确定的屏障事件（如代理任务 done 回调）；数据库排序改用可注入时钟或直接比较 sort_order 而非时间戳

- [Low][55] src/backend/tests/test_api.py:748-774 — 设置测试硬编码完整格式的 license key 字面量（cb_ 前缀 + 32 位十六进制，已脱敏），公开仓中无法与真实密钥区分
  - ID: f_backend_tests_06; verification: suspected
  - Evidence: 同一 key 字面量出现在 test_api.py:748、:761、:774 三处（本报告不记录其值）; 全仓 grep 该字面量仅命中这三处测试代码，生产代码与文档中无出现; test_get_settings_masks_key 还断言掩码输出包含该 key 的首尾片段（掩码格式本身即如此设计）
  - Impact: 若该字面量是曾真实使用的 Pro license key，则已随公开仓泄漏且掩码测试进一步确认其首尾；若是合成夹具值，其真实感使后续审阅者无法快速排除泄漏可能
  - Fix: 将夹具 key 换成明显合成的值（如 cb_test_fixture_0000...），并在 conftest 或测试文件头注明夹具密钥均为虚构；若该值曾为真，应轮换密钥并按泄漏处理历史

- [Low][85] src/backend/tests/test_vnc_manager.py:56-80 — VNC 分配测试绕过公开释放路径、直接增删私有 _allocated 并以其为主要断言面
  - ID: f_backend_tests_07; verification: static
  - Evidence: test_allocate_fills_gap（:56-66）用 vnc._allocated.pop(100) 模拟释放，而生产有正式路径 stop_vnc（src/backend/vnc_manager.py:111-114，同样 pop _allocated 并处理进程）; test_allocate_tracks_instances / test_allocate_instance_fields（:69-80）直接断言 _allocated 的内容与 VNCInstance 私有字段; test_api.py 的生命周期测试同样以 browser_mgr._held、_launching 的成员关系为关键断言（如 :1243-1249、test_duplicate_profile_leaves_nothing_behind 断言 not main.browser_mgr._held）
  - Impact: 内部表示一旦重构（如分配表换数据结构、hold 改为计数器），行为未变的测试会批量变红；反之若公开行为（如 stop_vnc 的端口回收）坏掉而 _allocated 仍正确，测试测不出来。注：test_browser_manager 对停止预留已改用公开 is_active() 断言，是同仓内的较好范式
  - Fix: fills_gap 改走 stop_vnc（process 为 None 时应可安全调用）或 allocate 对外提供的释放 API；实例字段断言改为经 get_ws_port/active_displays 等公开面验证；_held/_launching 断言尽量替换为 is_active()/hold_stopped 的可观察结果

- [Low][75] src/backend/tests/test_auth.py:46-151 — 认证覆盖只验证 GET /api/profiles 的拦截，变更类路由与异常登录体无测试
  - ID: f_backend_tests_08; verification: static
  - Evidence: 全部 auth 断言只打 GET /api/profiles、GET /api/auth/status、POST /api/auth/login、POST /api/auth/logout; 无测试验证 POST/PUT/DELETE /api/profiles 在无令牌时同样 401（若中间件按方法或路径漏配，现有测试无感）; 无 login 畸形请求体（缺 token 字段/非 JSON）的状态码断言；test_auth_status_authenticated 只测正确 cookie，未测错误 cookie 值时 authenticated 应为 False
  - Impact: 认证中间件的覆盖面被高估：按路由逐条挂载或方法豁免类的配置错误可能绕过变更类接口而套件全绿
  - Fix: 补一条参数化测试：对 POST /api/profiles、PUT/DELETE 各取一例断言无令牌 401、有令牌非 401；补 login 缺字段 422 与错误 cookie 的 status 断言

- [Info][95] src/backend/tests/conftest.py:64-90 — lifespan 中和补丁块在三处夹具中逐字复制，后续漂移风险；另 test_rfb 有未用导入
  - ID: f_backend_tests_09; verification: static
  - Evidence: conftest.py:76-84 的 app_client 与 test_auth.py:17-25、:32-40 的 client_no_auth/client_auth 重复同一组四行 monkeypatch（validate_available/cleanup_stale/cleanup_all/vnc.cleanup_stale）; test_rfb.py:14 导入 _ALLOWED_ENCODINGS 但全文仅在 :204 的注释中提及，未实际使用
  - Impact: lifespan 新增需中和的方法时要改三处，漏改一处表现为某组测试莫名连真实资源；未用导入属噪音
  - Fix: 在 conftest 提取 _neutralise_lifespan(monkeypatch, main) 辅助函数供三处夹具共用；删除 test_rfb 的未用导入或改为断言被过滤编码确实不在 _ALLOWED_ENCODINGS 中

- [Info][90] src/backend/tests/test_browser_manager.py:1-1 — 文件头 docstring 自称『pure functions』测试，与文件实际内容（完整 launch/stop 异步生命周期套件）不符
  - ID: f_backend_tests_10; verification: static
  - Evidence: test_browser_manager.py:1 docstring：『Tests for browser_manager pure functions — proxy parsing, fingerprint args, profile defaults.』; 文件后半（约 :240 起）包含 launch 重试、CDP 预留、停止预留计数、下载捕获开关等完整生命周期与并发测试，已远超 docstring 描述
  - Impact: 误导维护者对覆盖范围的判断（与 f_backend_tests_03 的假覆盖叠加时更明显）；属文档与实现不一致
  - Fix: 更新 docstring 为实际范围（纯函数参数构建 + launch/stop 生命周期与并发预留）

## views

```json
{
  "contracts": {
    "reviewer": "ef544da2-1781-4bef-8beb-ec5f71ced28b",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "ef544da2-1781-4bef-8beb-ec5f71ced28b",
    "status": "completed"
  },
  "design": {
    "reviewer": "ef544da2-1781-4bef-8beb-ec5f71ced28b",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "ef544da2-1781-4bef-8beb-ec5f71ced28b",
    "status": "completed"
  },
  "performance": {
    "reviewer": "ef544da2-1781-4bef-8beb-ec5f71ced28b",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "ef544da2-1781-4bef-8beb-ec5f71ced28b",
    "status": "completed"
  },
  "security": {
    "reviewer": "ef544da2-1781-4bef-8beb-ec5f71ced28b",
    "status": "completed"
  },
  "tests": {
    "reviewer": "ef544da2-1781-4bef-8beb-ec5f71ced28b",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "src/backend/tests/conftest.py",
  "src/backend/tests/test_api.py",
  "src/backend/tests/test_artifacts.py",
  "src/backend/tests/test_auth.py",
  "src/backend/tests/test_browser_manager.py",
  "src/backend/tests/test_database.py",
  "src/backend/tests/test_downloads.py",
  "src/backend/tests/test_models.py",
  "src/backend/tests/test_rfb.py",
  "src/backend/tests/test_runtime.py",
  "src/backend/tests/test_vnc_manager.py"
]
```
