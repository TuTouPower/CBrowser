# bundle_local_tests_e2e_stream_frontend

## responsibilities

- 端到端验证 stream/gateway/frontend/runtime 四条链路的已声明 AC 行为：多观看者 WebRTC 媒体与输入、ICE/TURN 轮换与失败恢复、Selkies token 门禁、可见性暂停、网关鉴权/CSRF、全应用 UI（登录/Profile/会话/显示应用/ICE 失败诊断）、Runtime Coordinator 收敛、浏览器运行时持久化与权限边界
- 构建接线验证：vendored Selkies 客户端的版本/hash 钉扎、frontend build 产出的 selkies_adapter.js 单一来源、vendor 脚本注入顺序与 verify_frontend_dist 校验脚本的正反用例
- 多数文件驱动真实 Docker 拓扑（真实 Chrome、Selkies、Caddy、Gateway、Supervisor、coturn 容器）并把运行证据写入 tmp_path/evidence；少数文件以容器内 probe 脚本运行生产代码并断言其输出的 proof JSON

## interfaces

- 环境变量契约：CBROWSER_RUNTIME_TEST_IMAGE / CBROWSER_STREAM_TEST_IMAGE / CBROWSER_TURN_TEST_IMAGE / CBROWSER_GATEWAY_TEST_IMAGE / CBROWSER_SUPERVISOR_TEST_IMAGE / CBROWSER_RUNTIME_ENGINE_CACHE / CBROWSER_RUNTIME_GEOIP_CACHE / CBROWSER_TEST_NEGATIVE_TURN_QUOTA
- fixtures 探针接口：gateway_probe.browser_oracle.browser_eval、gateway_probe.topology.GatewayTopologyHarness、frontend_probe.harness.FrontendTopologyHarness、frontend_app_probe.harness.FrontendAppTopologyHarness、stream_probe/\*.py 的 stdout 末行 proof JSON、runtime_probe/audio_analyzer.py、supervisor_resource_probe/stream_monitor.py、chrome_relay.py
- 页面侧契约：iframe 内 \_\_getWebRTCStats()、\_\_sentDataChannelMessages、\_\_restartOffers、sessionStorage selkies_tab_id、data-testid 选择器、Gateway 内部 /gateway/v1/internal/profiles/{id}/visibility 接口

## dependencies

- 宿主机依赖：Docker、真实 Google Chrome（stream 文件硬编码 macOS 路径 /Applications/Google Chrome.app，frontend/gateway 文件用 Playwright channel=chrome）、本机 Chrome 需支持 RTCRtpScriptTransform 等特性
- 构建产物依赖：src/frontend/dist（gitignore，harness 只检查存在不构建）、.scratch/selkies_wheels 缓存（缺失时 vendor 脚本走网络下载 PyPI wheel）
- 生产代码：cbrowser.api.app.create_app、cbrowser.domain.models、cbrowser.supervisor.artifact_forwarder、scripts/vendor_selkies_web.py、scripts/verify_frontend_dist.py

## flows

- 全应用流：pytest -> module 级 harness 启动真实拓扑（Caddy/API/Supervisor/Gateway/coturn）-> Playwright Chrome 经 UI 登录/建 Profile/启动 -> iframe 内官方 Selkies 客户端建 WebRTC -> 经 CDP/UDS oracle 驱动远端 media_page.html 并断言统计增长、输入到达、容器身份不变
- probe 流：pytest 以 docker run 把 fixtures/stream_probe/\*.py 挂入不可变镜像运行生产 stream_agent 代码，解析 stdout 末行 JSON 后断言布尔 proof 字段
- 负向流：test_gateway_ac005 的 negative 模式以子进程再跑一遍 pytest 并断言其非零退出且输出含指定失败文案

## constraints

- 镜像钉扎口径不一：stream probe 家族要求 sha256 并在缺 env 时 skip，test_browser_runtime_e2e 默认可变 tag cbrowser-t003-impl-runtime:latest，test_runtime_profile_defaults 与 test_stream_selkies_tokens 内置作者机 sha256 兜底值
- 多处用固定 sleep 充当测量窗或状态传播等待（帧增量采样、健康状态传播、SSE 不重连、fps 上限测量），与已归档 p009/p013 的整改方向（带超时条件轮询）只在被点名用例中落实
- 证据文件会落盘会话级材料（resume_key、全部 WS 发送帧），位于 tmp_path/evidence，非仓库内

## decisions

- p009（multi_viewer 固定 sleep）与 p013（静止画面帧增长）在归档中标记 resolved(323efaa/A28)：复核确认 test_stream_runtime 已改为 wait_for_viewer_count 轮询、test_frontend_app dual-tab 已在帧增长前调用 animate_remote_fixture（经 browser_oracle 重新导航到动画 media_page.html）
- Web Locks 身份仲裁的 shim 被既往 review(A24, commit 1215a61) 明确定位为 test-only 并移入 fixtures；生产 adapter.ts 另有一份实现，二者无一致性校验（见 finding 03）
- frontend 全应用测试复用预构建 dist 而非现场构建，是 harness 的显式设计（prepare_frontend_app 缺失即抛 RuntimeError），但无新鲜度校验（见 finding 02）

## evidence

- tests/e2e/test_stream_runtime_e2e.py:44-54 viewer 数条件轮询；:844 注入 WEB_LOCK_SHIM_JS；:1528-1545 mute 后未断言音频增量即关页
- tests/fixtures/stream_probe/web_lock_shim.js:34-38 无 tab_id 时 close(1008) 与 src/frontend/src/features/browser-session/adapter.ts:266-282 生成 UUID 继续的语义分叉（上下文核对）
- tests/fixtures/frontend_app_probe/harness.py:19-39 dist 仅拷贝不构建（上下文核对）；.gitignore:16 src/frontend/dist 被忽略
- tests/e2e/test_stream_ice_failure_e2e.py:15、test_stream_rtc_config_e2e.py:15,78、test_stream_ice_commit_e2e.py:15、test_stream_ice_relay_e2e.py:18、test_stream_x11_keymap_e2e.py:17、test_runtime_profile_defaults_e2e.py:444 的 pytest.skip 门禁
- tests/e2e/test_frontend_media_e2e.py:68-84 module 级共享 media_profile/remote_page；:883 振荡器置 0；:900 在共享容器 pkill pulseaudio 且不恢复
- tests/e2e/test_gateway_ac007_visibility_e2e.py:189-190 精确零增量与 >=40 帧硬阈值；:265 以全量日志含 'stopped' 证明捕获暂停
- tests/e2e/test_browser_runtime_e2e.py:886,1061,1214,1421,1647,1959,2246,2456,2642 显示号由 run_id 哈希在重叠区间取值
- tests/fixtures/stream_probe/ice_restart_failure.py:36-127 probe 内以生产 cbrowser.stream_agent 代码真实计算 proof（上下文核对，probe 模式本身可信）

## uncertainties

- docs/blueprint/testing.md 的前端门禁命令是否在跑 pytest 前统一执行 npm run build 未在本单元内完全核实（已见 stream/runtime/gateway 三条门禁命令均不含构建步骤）；若外部流水线另有构建步，finding 02 的影响收窄为本地临时跑测场景
- 门禁是否使用 pytest-xdist 或随机序插件未核实；finding 07/08 的触发概率取决于串行文件序这一当前默认
- stream 文件硬编码 macOS Chrome 路径与作者机镜像 sha256 兜底，可能是有意的单机门禁约束而非缺陷；按可移植性/静默跳过风险记录，未按缺陷定级
- adapter.ts 与 shim 在缺失 tab_id 分支的分叉是否可达：官方 Selkies 客户端通常先写 sessionStorage 再连接，若恒成立则该分支生产不可达，影响限于夹具保真度

## Findings

- [High][90] tests/e2e/test_stream_ice_failure_e2e.py:13-21 — 整个 stream probe 家族在缺镜像 env 时以 pytest.skip 静默跳过，门禁可全绿但零覆盖

    - ID: f_tests_e2e_stream_frontend_01; verification: static
    - Evidence: test_stream_ice_failure_e2e.py:15、test_stream_rtc_config_e2e.py:15 与 :78、test_stream_ice_commit_e2e.py:15、test_stream_ice_relay_e2e.py:18、test_stream_x11_keymap_e2e.py:17 均为 `pytest.skip("NOT_RUN: provide an immutable ... image")`；test_runtime_profile_defaults_e2e.py:444 的 autouse fixture 同样 skip 全部 5 个用例; 同一套件内口径相反：test_stream_runtime_e2e.py:497-499 对缺失/非 sha256 镜像直接 assert 失败，test_frontend_display_apply_e2e.py:269 `assert image` 硬失败; docs/blueprint/testing.md:77 的 stream 门禁命令直接列出这些文件运行，未在命令内设置镜像 env 检查；env 漏配时命令退出 0 且用例显示 skipped
    - Impact: ICE 失败恢复、TURN 中继轮换、RTC 配置、X11 keymap、profile defaults 五个文件可在门禁里整体不执行而无人察觉，'测试通过'语义不确定
    - Fix: 统一门禁口径：要么在 gate 入口脚本集中校验 env 并硬失败，要么把 skip 改为在 CI/门禁 profile 下 assert；至少让 NOT_RUN skip 在门禁报告中显式计数并阻断

- [High][75] tests/e2e/test_frontend_adapter_build.py:47-61 — 前端 E2E 只消费磁盘上既有的 dist，不构建也不校验新鲜度，可对着过期构建全绿

    - ID: f_tests_e2e_stream_frontend_02; verification: static
    - Evidence: tests/fixtures/frontend_app_probe/harness.py:19-39 prepare_frontend_app 仅在 dist 缺失时抛错，随后原样 copytree 到拓扑静态根；src/frontend/dist 在 .gitignore:16 中忽略，新克隆默认无 dist; test_frontend_adapter_build.py:47-61 只断言 dist/selkies/selkies_adapter.js 存在且含 '\_\_cbrowserAdapterSource' 等标记字符串，不与 adapter.ts 的内容/hash/mtime 做任何比对; 本单元内无任何用例执行 npm run build；app/media/auth/display/ice 五个全应用文件的 module 级 harness 都建立在这份未验证新鲜度的 dist 上
    - Impact: 改动 adapter.ts 或前端源码后直接跑 pytest，测到的是旧构建：假绿（漏检回归）或假红（旧构建缺陷）都可能，且与门禁是否另有构建步强耦合
    - Fix: 在 harness 准备阶段记录 src 关键源文件 hash 并与 dist 内嵌标记比对，或在门禁命令中强制先 npm run build 并让 harness 校验构建时间戳晚于源文件；adapter 构建测试改为现场构建到 tmp 目录后校验

- [Medium][90] tests/e2e/test_stream_client_identity_e2e.py:21-139 — 身份仲裁只测 test-only shim，且 shim 与生产 adapter.ts 已出现语义分叉

    - ID: f_tests_e2e_stream_frontend_03; verification: static
    - Evidence: 本文件页面是裸探针页（仅 <title>Identity probe</title>），被测仲裁逻辑全部来自 tests/fixtures/stream_probe/web_lock_shim.js；test_stream_runtime_e2e.py:844 也以 add_init_script 注入同一 shim 代替生产适配器; 分叉实例：web_lock_shim.js:34-38 在 sessionStorage 无 selkies_tab_id 时直接 close(1008, 'tab_identity_required') 永不发送；src/frontend/src/features/browser-session/adapter.ts:266-282 则是生成 UUID 写入 sessionStorage 后继续 acquireLock 并发送; git log 1215a61 显示 shim 是既往 review(A24) 有意保留的 test-only 实现；本单元内没有任何用例交叉校验 shim 与 adapter.ts 行为一致
    - Impact: adapter.ts 的 Web Locks 仲裁若回归，stream/identity 这一组用例仍会全绿；shim 与生产实现继续各自演化时，e2e 结论对生产行为的证明力持续下降
    - Fix: 让 identity 用例改为经真实构建产物（dist 中的 adapter）驱动，或新增一条一致性用例：同一组 HELLO/碰撞场景分别跑 shim 与 adapter 并断言可观察行为（close code、remap 后 tab_id、转发条数）一致

- [Medium][95] tests/e2e/test_stream_runtime_e2e.py:67-378 — 多观看者主用例以测试内重写的 GatewayMockServer 代替生产 Gateway 验证信令协议

    - ID: f_tests_e2e_stream_frontend_04; verification: static
    - Evidence: GatewayMockServer 是文件内 aiohttp 重实现（注册/HELLO 转发/静态资源代理），仅从生产代码 import 了 DEFAULT_GATEWAY_PORT 一个常量；静态资源经 docker exec 到 Stream 容器内取回并注入改写 WebSocket 路径的脚本; 协议断言写在 mock 的 WS handler 里（:235-237 注册字段 assert、:262-266 转发包字段 assert），违规时以 handler 异常/断连形式表现，不是可读的断言失败; 生产 Gateway 的真实行为只由 gateway_ac00x 文件经另一套 GatewayTopologyHarness 覆盖，本文件的 AC-001..006 结论建立在 mock 与生产协议不漂移的假设上
    - Impact: Gateway 协议演进（字段/版本/关闭语义）时本文件要么误报要么与 mock 一起被改掉，无法起到独立回归网作用；handler 内 assert 还会在 -O 或异常路径下吞掉定位信息
    - Fix: 将该用例迁到真实 Gateway 容器拓扑（复用 gateway_probe.topology），mock 只保留在无法起真实网关的单元层；handler 内 assert 改为记录违规包并在测试主体断言

- [Medium][90] tests/e2e/test_stream_selkies_tokens_e2e.py:327-340 — AC-010 的 Agent token 注入由测试内仿真函数完成，且 viewer 冒充 controller 的'被降级'断言缺失

    - ID: f_tests_e2e_stream_frontend_05; verification: static
    - Evidence: agent_forward_hello 注释自述 'Emulates StreamAgent upstream worker HELLO token injection'，注入逻辑是测试本地 dict 拼接，未经真实 Stream Agent 代码路径; 同文件前两个用例以测试自带 bootstrap 脚本（:53-85）直接拉起上游 selkies.settings/stream_server，验证的多为上游 Selkies 行为而非 CBrowser 组件; Case D（:271-287）声称 viewer token 冒充 controller 应 'Accepted but coerced'，实际只断言回复以 HELLO 开头，未校验服务端回告的 role/slot 是否已被降为 viewer
    - Impact: 真实 Agent 的注入实现损坏（漏注入/注入错 token）时本组用例不报；viewer 越权未被降级这类安全回归可无声通过
    - Fix: 注入用例改为经真实 Stream Agent 容器建立观看者连接（gateway 拓扑用例已具备条件），或在断言中解析 HELLO server 回告并断言 role 被强制为 viewer

- [Medium][80] tests/e2e/test_gateway_ac007_visibility_e2e.py:160-215 — 可见性用例仍以固定 settle sleep 后精确零增量/硬 FPS 阈值断言，属 p013 同类 flake 模式

    - ID: f_tests_e2e_stream_frontend_06; verification: static
    - Evidence: Phase 1：visibility override 后固定 sleep(0.5)（注释称 Selkies 250ms debounce），随后 2 秒窗内断言 delta_B_p1 == 0 且 delta_A_p1 >= 40（:189-190）；Phase 2 同样断言两页 delta == 0（:254-272）; test_frontend_media_e2e.py:471-485 同模式：隐藏后 sleep(1.0) 再测 2 秒窗 delta == 0，并对前台页设 ACTIVE_FPS_FLOOR=20（3 秒 >=60 帧）; STOP_VIDEO 生效前已在解码管线中的帧可在测量窗内落账，使精确零断言偶发失败；>=40 帧/2 秒阈值在宿主高负载时同样可误报——p013 归档记录的正是这类时序偶发失败
    - Impact: 可见性 AC 在负载机器上偶发红/绿，降低整套 e2e 的可信度并诱发'复跑即过'式放行
    - Fix: 零增量断言改为带宽限的条件轮询（如 STOP 确认后先等一帧周期再采样，或允许 \<=1 的在途帧并注释依据）；FPS 阈值改为相对基线（同页可见期帧率的比例）而非绝对值

- [Medium][90] tests/e2e/test_frontend_media_e2e.py:68-84 — module 级共享 media_profile 被最后一个用例破坏性修改且不恢复，结论依赖文件执行顺序

    - ID: f_tests_e2e_stream_frontend_07; verification: static
    - Evidence: media_profile 与 remote_page 为 module scope fixture，四个用例共用同一 Browser/Stream 容器与同一远端页面; test_ac005_audio_diagnostics 在 :883 把远端振荡器频率置 0、:900 对共享 Browser 容器 exec pkill -9 pulseaudio，全程无重启/恢复；test_ac005_remote_tab_switch 在 :750-762 把 media page 置 motionEnabled=false 并填红也不还原 motion 状态; 当前文件序恰好把 diagnostics 排在最后才未爆；用 -k 单跑或调整顺序后，后续依赖音频的用例会继承无声/无音频栈的远端环境
    - Impact: 选择性重跑与顺序调整会产生与产品无关的失败，失败定位指向错误的用例；共享可变远端状态也使单个用例的证据不可独立复现
    - Fix: 破坏性用例改用 function 级独立 profile，或在 diagnostics 结尾恢复 PulseAudio/振荡器状态并断言恢复成功；至少在 fixture teardown 中重建远端页面状态

- [Medium][75] tests/e2e/test_browser_runtime_e2e.py:886 — X 显示号由 run_id 哈希在多个重叠区间取值，跨用例/并行门禁可撞号；另有固定名容器探针

    - ID: f_tests_e2e_stream_frontend_08; verification: static
    - Evidence: 各用例 disp 取值基数分别为 120/130/140/140/150/160/170/180 再加 int(run_id[:4],16)%300（:886、:1061、:1214、:1421、:1647、:1959、:2246、:2456、:2642），区间大面积重叠；t013 还使用 display_number+1（:2642 起）; test_stream_runtime_e2e.py 固定使用 :99，test_stream_x11_keymap_e2e.py 固定 :99；test_frontend_display_apply_e2e.py:296 容器名写死 't007-display-config-probe' 且 docker run --rm，上次泄漏的同名容器会让下次直接失败
    - Impact: 同一宿主上并行跑两条门禁 lane（或同文件两用例哈希碰撞）时 Xvfb 显示冲突，表现为浏览器起不来/画面串扰类难定位失败
    - Fix: 显示号改为启动时探测空闲号（扫描 /tmp/.X11-unix 已占用集合后原子分配）或纳入全局唯一的 run 前缀命名空间；固定名探针容器加 run 后缀

- [Medium][85] tests/e2e/test_browser_runtime_e2e.py:1070-1102 — 固定 sleep 后单次断言的时序模式在 browser runtime 文件内多处残留（p009/p013 整改未覆盖）

    - ID: f_tests_e2e_stream_frontend_09; verification: static
    - Evidence: AC-002 负向用例 pkill pulseaudio/Xvfb 后固定 sleep(1.0) 即断言 /health '立即' 变为 not ready（:1070-1102），健康传播慢于 1 秒即偶发失败; AC-001 在 close 后固定 sleep(2.0) 假设 Cookie SQLite 已落盘再重建容器校验持久化（:864-870）；AC-004 在外部客户端断开后固定 sleep(1.5) 假设 rearm 完成（:1340-1346）；test_t008 重启后固定 sleep(2.0) 即断言 scan_events() 与重启前完全相等（:1679-1684），Agent 慢启动时先报错或假过; 同文件正面用例已普遍改用 wait_for_uds_ready/条件轮询，显示该模式是局部遗漏而非统一约定
    - Impact: 这批用例是门禁 browser_runtime 车道的核心成员，时序偶发失败会持续消耗复跑与审查轮次
    - Fix: 逐处改为带超时的条件轮询：health 轮询到 ready False、cookie 校验轮询到值出现、rearm 以第二次下载成功为条件、scan 等值断言先轮询到 Agent 就绪且事件数稳定

- [Low][90] tests/e2e/test_frontend_session_e2e.py:411-425 — freeze/resume 用例不校验媒体真正恢复，且文件头 docstring 声称了不存在的 resume_key 断言

    - ID: f_tests_e2e_stream_frontend_10; verification: static
    - Evidence: setWebLifecycleState 恢复后固定 sleep(1.0)，随后单次 get_iframe_webrtc_stats 只断言 connected 与 tab_id 相同（:411-425），从不比较 framesDecoded 是否增长，连接活着但媒体停滞可通过; 文件头 docstring（:9）写 'Refresh preserves tab identity and resume key'，但本文件 refresh 段只断言 tab_id；兄弟文件 test_frontend_app_e2e.py 对 refresh 的口径是 resume_key 必须轮换，二者文档口径不一致
    - Impact: AC-007 生命周期恢复的关键可观察行为（帧恢复）未被该用例证明；docstring 夸大覆盖会误导后续维护者以为 resume_key 已在此验证
    - Fix: 恢复后用 wait 类轮询断言 framesDecoded 严格大于冻结前值；修正 docstring 为与实际断言一致的表述

- [Low][90] tests/e2e/test_gateway_ac001_auth_e2e.py:197-233 — 多处存在性/宽口径断言可被无关内容满足：整日志子串、状态码三选一、3 秒不重连

    - ID: f_tests_e2e_stream_frontend_11; verification: static
    - Evidence: :227-228 以 '401'/'403' 出现在全部 Gateway 日志任意位置证明拒绝被记录，端口号/字节数等无关数字串即可满足; :197 与 :210 对未授权 profile 的 WS 拒绝接受 403/404/503 任一，与同文件证据体要求 body 含 'profile_not_found' 的口径不完全一致; test_gateway_ac007_visibility_e2e.py:265 以全量 Stream 日志含 'stopped' 子串作为 capture paused 的证据之一；test_frontend_app_auth_e2e.py:206-210 以固定 sleep(3.0) 后 /api/v1/events 计数不变证明 SSE 不重连，重连退避超过 3 秒即假过
    - Impact: 这类断言在实现漂移时给出假绿，或在无关日志增长时给出假红，削弱 AC-001/AC-007 与 auth 车道的证明力
    - Fix: 日志断言限定到本次请求对应的时间窗/结构化字段；状态码收敛为契约规定的单一值；不重连断言改为观察至少一个完整退避周期或直接断言前端 SSE 客户端已销毁

- [Low][90] tests/e2e/test_frontend_build_wiring.py:79-87 — 构建接线测试以文本/常量断言为主：package.json 字符串、钉扎的产物 hash 文件名、常量等于字面量

    - ID: f_tests_e2e_stream_frontend_12; verification: static
    - Evidence: test_frontend_build_wiring.py:79-87 断言 package.json scripts 的精确字符串；test_frontend_adapter_build.py:89-98 与 :124-127 把官方 bundle 的 hash 文件名 'index-BpOBp7NB.js' 写死在期望中；test_frontend_session_vendor.py:20-24 只断言 PINNED 常量等于字面量，从不校验任何 vendored 文件或 wheel 的实际 hash; test_frontend_adapter_build.py 的 vendor 用例把 cache_dir 指向仓库 .scratch/selkies_wheels，scripts/vendor_selkies_web.py:62-73 在缓存缺失时经 urlopen 联网下载 wheel，使这些用例隐含网络依赖且会写共享缓存; 同文件 test_valid_dist_passes 等用例测的是 verify_frontend_dist 脚本本身对合成 dist 的反应，属单元测试却放在 tests/e2e 下随重型门禁一起调度
    - Impact: Selkies 升级或构建脚本改名时这批用例以文本不匹配形式爆红，与真实接线是否可用无关；反之文本未变但产物损坏时可假绿；网络受限环境下 vendor 用例会以下载失败形式误报
    - Fix: hash 文件名从 vendor 产物 index.html 动态解析而非写死；vendor 常量测试补一条对实际 wheel 文件 sha256 的校验（离线缓存存在时）；把 verify 脚本的合成用例移入 tests/unit 并标注其层级

- [Low][85] tests/e2e/test_stream_runtime_e2e.py:1528-1545 — 主用例宣称的'independent mute'未被验证：静音后未断言任一页音频增量即关页

    - ID: f_tests_e2e_stream_frontend_13; verification: static
    - Evidence: 文件头 docstring（:1-5）与用例 docstring 把 independent mute 列为验证目标；实际流程在 :1533 对 Tab 1 发 pipelineControl audio disabled 后，仅 wait 本地 video 元素 muted 标志并 sleep(1.0)，随即关闭 Tab 1; 关页后对 Tab 2 的断言（:1547-1565）比较基线是静音前的 stats2_later，只能证明 Tab 2 在关页后继续，不能证明静音期间 Tab 1 音频已停、Tab 2 未受影响; 对照 test_frontend_media_e2e.py AC-005 与 test_frontend_app_e2e.py AC-004 均有逐页音频字节增量断言，说明本文件的该 AC 点是覆盖缺口而非口径选择
    - Impact: Stream 层逐连接静音回归（全员静音/静音无效）可被本主用例漏检，只能依赖前端车道兜底
    - Fix: 在关页前采样两页 audio bytesReceived/totalAudioEnergy 增量：Tab 1 应停滞、Tab 2 应继续增长，再进入关页流程

- [Low][85] tests/e2e/test_runtime_coordinator_e2e.py:535-542 — cleanup 在 finally 中抛 RuntimeError 会掩盖原始测试失败；容器出现等待以 0.5 秒间隔全量 list 长达 180 秒

    - ID: f_tests_e2e_stream_frontend_14; verification: static
    - Evidence: finally 末尾 `if cleanup_errors: raise RuntimeError(...)`（:539-541），当测试主体已抛异常时该 raise 替换原始异常与定位信息; :308-318 等待 Browser/Stream 出现时每 0.5 秒 client.containers.list() 全量枚举，最长 360 次；同文件其余轮询（:330-345 等）同为固定间隔短轮询
    - Impact: 失败现场的第一根因被 cleanup 错误覆盖，增加排障成本；高频全量 list 在容器多的宿主上放大 Docker API 压力并拖慢收敛判定
    - Fix: cleanup 错误改为记录并在主体成功时才升级为失败（或用 exception note 附加）；容器等待改用按 name/label 过滤的 list 并适当拉长间隔

- [Low][85] tests/e2e/test_frontend_app_e2e.py:1075-1090 — 会话恢复密钥被写入 evidence 产物长期留存于 basetemp

    - ID: f_tests_e2e_stream_frontend_15; verification: static
    - Evidence: ac007 的 \_save 把 initial_resume_key、resumed_resume_key、rebuilt_resume_key 明文写入 evidence JSON（:1083-1086）；test_frontend_media_e2e.py:557-575 把两页全部 WS 发送帧（含 HELLO 中的 resume_key/client_tab_id）写入 ac004 evidence; 对照同套件对 Selkies token 的口径（test_frontend_app_e2e.py AC-002 专门断言 token 不得出现在 DOM/存储/网络体中），resume_key 同属会话恢复凭据却被测试自身落盘
    - Impact: evidence 目录若被打包分享或长期保留，持有 resume_key 者可在会话有效期内冒用观看者连接恢复；与套件自身的防泄漏标准不一致
    - Fix: evidence 中对 resume_key 只存 hash 或前后 4 位指纹；WS 帧证据改为只存帧类型与长度统计

- [Low][80] tests/e2e/test_stream_selkies_tokens_e2e.py:94-105 — Selkies 测试服务以 docker -p 发布到宿主全部网卡，与同套件的 loopback 绑定口径不一致

    - ID: f_tests_e2e_stream_frontend_16; verification: static
    - Evidence: SelkiesE2ERunner 启动命令为 '-p {port}:{port}'（:96-97），Docker 默认绑定 0.0.0.0；该服务持有随机 master_token 且开启 token 供应接口，运行期间对局域网可达; 对照 test_stream_runtime_e2e.py 的 UDP mux 明确绑定 127.0.0.1、test_gateway_ac001 的拓扑端口均经 harness 受控发布
    - Impact: 在共享/不可信网络跑门禁时，测试期 Selkies 服务可被同网段第三方探测并尝试 token 接口，属不必要的暴露面
    - Fix: 端口发布改为 127.0.0.1:{port}:{port}，与套件其他组件保持一致

- [Low][90] tests/e2e/test_browser_runtime_e2e.py:381-495 — harness/oracle/启动样板多处复制且已漂移，单文件与单个用例规模过大

    - ID: f_tests_e2e_stream_frontend_17; verification: static
    - Evidence: test_stream_runtime_e2e.py:381-495 内嵌 browser_eval 副本，与 fixtures/gateway_probe/browser_oracle.py 同源但错误细节处理已不同（异常信息脱敏程度不一）；GatewayMockServer、wait 工具亦为文件内自备; test_stream_ice_commit_e2e.py / test_stream_ice_failure_e2e.py / test_stream_rtc_config_e2e.py 各自复制约 50 行几乎相同的 docker run 参数组装，仅 fixture 名与断言不同; test_frontend_session_e2e.py 与 test_frontend_app_e2e.py 以两套拓扑 harness 重复覆盖 AC-002/003/004/005/007；test_browser_runtime_e2e.py 达 2791 行、多观看者 stream 用例单个函数约 1190 行（:485-1678），失败时无法按阶段单独重跑
    - Impact: 夹具修复要多处同步且容易漏改（shim 分叉即同类问题）；巨型用例使门禁失败定位与选择性重跑成本高
    - Fix: stream 文件改用 gateway_probe.browser_oracle 唯一实现；probe 启动样板抽到 stream_probe 公共 helper 并参数化；巨型用例按 AC 阶段拆分并共享 module 级拓扑 fixture

- [Low][85] tests/e2e/test_runtime_profile_defaults_e2e.py:456-472 — profile defaults 宿主层断言多为回声校验，且容器内 UI 自动化靠固定 sleep 与版本敏感选择器

    - ID: f_tests_e2e_stream_frontend_18; verification: static
    - Evidence: 宿主断言 res.get('locale') == 传入的 locale 参数、res.status == 'PASS'（:463-472），真实校验全在内嵌 CONTAINER_SCRIPT 中以 assert 完成，宿主层无法区分哪条断言失败（只能看整段容器输出）; CONTAINER_SCRIPT 在 chrome://settings 导航后固定 sleep(1)（:158、:259、:371），切 Bing 走 shadow DOM 选择器 SETTINGS-SEARCH-ENGINE-ENTRY / cr-icon-button.icon-more-vert 加 350ms setTimeout（:330-375），Chrome 设置页改版即失效; \_run_docker_e2e 每次在仓库 .scratch/t003_profile_defaults/\<run_id> 写 e2e_runner.py 与 container.log（:405-408），finally 只删容器不删这些目录，长期累积
    - Impact: 该文件失败时定位成本高（整段容器日志回放），且随 Chrome 版本升级的脆弱点集中在无人轮询的 UI 时序上；.scratch 残留持续增长
    - Fix: 容器脚本改为输出结构化分阶段结果供宿主逐项断言；settings 页交互改用条件等待（轮询 getSearchEnginesList 结果）；finally 中清理 scratch_run 或改用 tmp_path

- [Info][80] tests/e2e/test_frontend_app_e2e.py:631-634 — 延迟类指标只记录不设门限，多条用例的墙钟预算使套件总时长达分钟级且无说明

    - ID: f_tests_e2e_stream_frontend_19; verification: static
    - Evidence: AC-004 记录 first_frame_ms 与 input_to_remote_ms 到 evidence（:690-697、:764-776）但从不断言上限，性能回归不可见; test_gateway_ac005_relay_e2e.py 依赖 40 秒一代的凭证轮换节奏观察两代（文件头注释 :20-27 给出 t=90s 时间线）；test_frontend_ice_failure_e2e.py 单个 stage 等待预算 240 秒；test_gateway_ac005 的 negative 用例以子进程完整重跑一遍正向用例拓扑
    - Impact: 套件变慢或媒体延迟劣化时没有信号，维护者只能凭经验判断某次门禁慢是正常还是回归
    - Fix: 为 first-frame 与输入延迟设宽松上限断言（如取历史 p95 的 2 倍）；在 testing.md 门禁说明中登记各重型文件的预期时长区间

## views

```json
{
  "contracts": {
    "reviewer": "cc5a975b-4b2e-46fc-b0f4-9f7d33e5ee45",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "cc5a975b-4b2e-46fc-b0f4-9f7d33e5ee45",
    "status": "completed"
  },
  "design": {
    "reviewer": "cc5a975b-4b2e-46fc-b0f4-9f7d33e5ee45",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "cc5a975b-4b2e-46fc-b0f4-9f7d33e5ee45",
    "status": "completed"
  },
  "performance": {
    "reviewer": "cc5a975b-4b2e-46fc-b0f4-9f7d33e5ee45",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "cc5a975b-4b2e-46fc-b0f4-9f7d33e5ee45",
    "status": "completed"
  },
  "security": {
    "reviewer": "cc5a975b-4b2e-46fc-b0f4-9f7d33e5ee45",
    "status": "completed"
  },
  "tests": {
    "reviewer": "cc5a975b-4b2e-46fc-b0f4-9f7d33e5ee45",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "tests/e2e/test_browser_runtime_e2e.py",
  "tests/e2e/test_frontend_adapter_build.py",
  "tests/e2e/test_frontend_app_auth_e2e.py",
  "tests/e2e/test_frontend_app_e2e.py",
  "tests/e2e/test_frontend_build_wiring.py",
  "tests/e2e/test_frontend_display_apply_e2e.py",
  "tests/e2e/test_frontend_ice_failure_e2e.py",
  "tests/e2e/test_frontend_media_e2e.py",
  "tests/e2e/test_frontend_session_e2e.py",
  "tests/e2e/test_frontend_session_vendor.py",
  "tests/e2e/test_gateway_ac001_auth_e2e.py",
  "tests/e2e/test_gateway_ac003_media_e2e.py",
  "tests/e2e/test_gateway_ac005_relay_e2e.py",
  "tests/e2e/test_gateway_ac007_visibility_e2e.py",
  "tests/e2e/test_runtime_coordinator_e2e.py",
  "tests/e2e/test_runtime_profile_defaults_e2e.py",
  "tests/e2e/test_stream_client_identity_e2e.py",
  "tests/e2e/test_stream_ice_commit_e2e.py",
  "tests/e2e/test_stream_ice_failure_e2e.py",
  "tests/e2e/test_stream_ice_relay_e2e.py",
  "tests/e2e/test_stream_rtc_config_e2e.py",
  "tests/e2e/test_stream_runtime_e2e.py",
  "tests/e2e/test_stream_selkies_tokens_e2e.py",
  "tests/e2e/test_stream_x11_keymap_e2e.py"
]
```
