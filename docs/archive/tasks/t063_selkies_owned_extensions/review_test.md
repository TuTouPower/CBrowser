# Task review t063（reviewer_focus: 测试）

task: t063_selkies_owned_extensions
spec: docs/tasks/t063_selkies_owned_extensions/task.md
diff_anchor: 501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90
target: tests/unit/test_t063_selkies_controlled_build.py、tests/unit/test_t063_patched_keyboard_behavior.py、被删 tests/unit/test_stream_keymap_abi.py、被改 tests/unit/test_t043_selkies_pin.py 与 tests/unit/test_stream_binding_guards.py、tests/e2e/test_stream_x11_keymap_e2e.py、tests/fixtures/stream_probe/x11_keymap_probe.py、scripts/build_selkies_controlled.py、config/selkies/selkies_controlled_build.json
round：1
reviewed_at：2026-11-14T05:51:26+08:00
reviewed_scope: 316029d874de8907

## Findings

### t063_test_f001 - 构建产物内 _webrtc_service 钩子本身有三态测试，但 run() 注册行这一唯一集成接缝无任何断言

- 严重度：important
- 锚点：AC-005（受控包行为即出厂行为）/ 覆盖缺口（patch 0001 的运行时效果行）
- 位置：tests/unit/test_t063_patched_keyboard_behavior.py:295-339（_materialize_hook 切片）；config/selkies/patches/0001-webrtc-service-factory-hook.patch（register_service 行）
- 问题：行为测试用文本切片只提取 `def _webrtc_service` 到 `async def run()` 之间的函数体单独 exec，三态（默认 stock、具名工厂、非法引用 ValueError）测的都是这个孤立函数。patch 0001 在产物中真正产生运行时效果的是 `run()` 里的一行 `server.register_service("webrtc", _webrtc_service(server))`；审阅者实测：该行在构建产物中确实存在，但全仓 t063 测试对 `register_service` 零断言（grep tests/unit/test_t063_*.py 无命中）。复现实验：把构建产物 `selkies/__main__.py` 的注册行改回 `WebRTCService(server)` 后，按测试同款方式切片物化，钩子函数仍可调用且默认仍返回 stock 类——即注册行回退/丢失时现有全部单测仍会绿，只有顺延 p096 的 [deploy] AC-001 真机链能发现。差异面测试也救不了：它只断言变更文件集合与可编译，不看注册行内容。
- 建议：在 test_t063_patched_keyboard_behavior.py 增加对构建产物全文的断言：`selkies/__main__.py` 中 `register_service("webrtc", _webrtc_service(server))` 恰出现一次且 stock 直构形式不再出现于 run()；或直接物化 run() 的注册段做接缝测试。

### t063_test_f002 - 键盘行为测试绕过真实 __init__ 手工灌入 15 个实例属性，被删 ABI 门禁的实例属性覆盖在单测层无接管

- 严重度：important
- 锚点：覆盖缺口（被删 tests/unit/test_stream_keymap_abi.py 的实例属性断言组）
- 位置：tests/unit/test_t063_patched_keyboard_behavior.py:186-210（_make_keyboard）；基线 test_stream_keymap_abi.py 的 test_missing_instance_attribute_is_unsupported_abi 等
- 问题：`_make_keyboard` 用 `__new__` 跳过真实 `__init__`，手工灌入 `_d/_xkb/_group_hold/_group_restore/_shift_kc/_shift_r_kc/_altgr_kc/_effective_mod_keycodes/_synth_mods/_spare_keycodes/_spare_set/_text_codes/_overlay/_overlay_value_kc/_settle_until/_overlay_order/_pressed_kc`。被删 ABI 测试逐项守护的 6 个实例属性（_spare_keycodes/_spare_set/_text_codes/_overlay/_pressed_kc/_settle_until）是否由上游真实 `__init__` 初始化，在新单测里被手工灌入掩盖：上游 __init__ 改名/漏初始化任一属性，单测仍全绿。spike s020 的 verify_behavior.py 同样用 `__new__`＋手工灌入，未提供该证据。目前唯一真正执行 `_XTestKeyboard(connection)` 真实构造的是 tests/fixtures/stream_probe/x11_keymap_probe.py，而它属 [deploy] 顺延 p096、本轮未执行。逐项覆盖映射（基线 ABI 测试 7 例）：完整 ABI 通过→对象已删、由构建期上下文精确匹配＋行为测试部分接管；缺方法 _layout_keycode→prebind 路径在行为测试中间接行使（构建产物 prebind 确含 _layout_keycode 调用且 4 例键盘测试通过）；prebind 签名错误→行为测试按位置参数调用 prebind，签名漂移会报错，视为接管；缺实例属性→本 finding 的缺口；_BIND_SETTLE_S 常量→构建产物实测为 0.025，行为测试断言 settle ≥ 起点+0.02，弱接管；注释中属性不算数（AST 检查）→门禁机制本身被删，不再需要；不可内省签名→同门禁删除，不再需要。另：审阅提示中的 _modmask_from_held、_originals 在 diff_anchor 基线全仓 git grep 零命中，不存在该覆盖，无需接管。
- 建议：补一条不依赖真实 X 服务的 __init__ 覆盖：对构建产物类做 AST/源码级断言（__init__ 确实赋值补丁方法依赖的全部实例属性，即把被删门禁的该项断言以「自有受控包」形式保留），或在 p096 之外把探针的真实构造纳入可在 CI 跑的 Xvfb 单测。

### t063_test_f003 - AC-004 静态守护只匹配字面字符串，setattr 式运行时替换/AST 解析/私 ABI 清单换址重入都测不出来

- 严重度：minor
- 锚点：AC-004
- 位置：tests/unit/test_t063_patched_keyboard_behavior.py:363-379（test_startup_has_no_runtime_patch_or_upstream_source_parsing）
- 问题：守护只断言 agent.py 不含 `selkies_main.WebRTCService =` 与 `install_x11_keymap_refresh` 两条字面串、src 全树不含 `getsource(`、x11_keymap.py 不存在。审阅者实测当前 src/backend/cbrowser/stream_agent/ 内确无 ast./getsource/inspect 的上游源码解析（仅 policy.py:202 文档字符串含 "inspects" 一词），AC-004 现状属实；但守护形式过窄：用 `setattr(selkies_main, "WebRTCService", ...)` 做运行时替换、在其他模块用 `ast.parse(上游源码)`、或把私有 ABI 清单换名重入，均不会触发该测试。属守护强度问题，非现状违规。
- 建议：把守护扩到 stream_agent 包级：禁止 `setattr(` 作用于 selkies 模块对象、禁止对 selkies 包路径做 ast.parse/inspect.getsource、禁止 SUPPORTED_SELKIES_VERSION/_ABI_ 类清单符号在 src 内重现。

### t063_test_f004 - 差异面断言以文件为粒度且跳过 RECORD，该测试单独看不验证目标文件内任意改写与 RECORD 自洽

- 严重度：minor
- 锚点：AC-005
- 位置：tests/unit/test_t063_selkies_controlled_build.py:98-136
- 问题：`changed == declared_targets | {METADATA}` 中 declared_targets 是整文件级（selkies/__main__.py、selkies/input_handler.py），两文件内部任意幅度改写都通过此断言（仅再加 compile 检查）；且循环对 RECORD 直接 `continue` 跳过，该测试不校验 RECORD 各条哈希与内容自洽。缓解事实（审阅者实测）：test_build_is_reproducible_and_matches_manifest 用整 wheel SHA256 与清单比对，钉住包括 RECORD 在内的每一字节；审阅者独立校验构建产物 RECORD 自洽为 True、手工篡改 RECORD 后整包哈希即与清单不一致。故套件层面已封闭，仅该测试的独立声称（「differs only at declared surface」）强于其自身断言。
- 建议：在差异面测试内补 RECORD 逐条自洽校验（每条 sha256/size 与条目内容比对），并注明目标文件粒度为有意声明面、内容正确性由补丁哈希＋行为测试承担。

### t063_test_f005 - e2e 探针的受控版本断言只验前缀，镜像内构建戳身份不由探针复核

- 严重度：minor
- 锚点：AC-005 / [deploy] AC-001 顺延证据强度
- 位置：tests/fixtures/stream_probe/x11_keymap_probe.py:16-19
- 问题：探针断言 `version.startswith("2.2.1+cbrowser.")`，任意本地后缀（如与当前补丁无关的构建）都通过；探针不读包内 `selkies/cbrowser_build.json` 构建戳核对补丁哈希序列。e2e 两侧字段一致性已核：探针输出 controlled_build/controlled_version/held_slots_unchanged，e2e 断言 controlled_build、rounds==5、held_slots_unchanged，无被删 install 幂等断言残留，此点无问题。缓解：Dockerfile 构建阶段 RUN 已断言安装戳的上游哈希与补丁哈希序列与清单一致（config/docker/stream_runtime/Dockerfile:48），镜像构建时即失败封闭；本项仅指运行时探针一侧的身份断言弱于构建戳可达成的强度。
- 建议：探针补读 cbrowser_build.json 并断言 controlled_version 与补丁 sha256 序列非空且格式完整（镜像内无清单原件时至少断言戳存在且 upstream.wheel_sha256 为钉版值）。

## 结论

verdict: FAIL

结论说明：实施质量总体扎实——审阅者独立重建受控 wheel 两次，SHA256 均为 704c59b4fee1d150565515c86d5eb45a6ee00d455cbebaf0f1be34d13dc590f5，与清单 controlled.wheel_sha256 完全一致；对上游 wheel 与补丁文件各翻转 1 个字节均触发 ControlledBuildError 失败封闭（上游 SHA256 mismatch、补丁 SHA256 drift），与套件内篡改/上下文漂移/错哈希三例互证。复跑实数：test_t063_selkies_controlled_build.py 7 passed、test_t063_patched_keyboard_behavior.py 10 passed、test_t043_selkies_pin.py 2 passed、test_stream_binding_guards.py 7 passed、test_t045_selkies_wheel_cache.py 4 passed、test_docker_build_contexts.py 6 passed（合计 36 passed），另 test_vendor_selkies_security.py 8 passed、test_stream_capture_policy.py＋test_stream_takeover_chain.py 14 passed。test_stream_binding_guards 删除的 _read_keymap 用例确有等价接管：test_built_keymap_query_without_display_fails_with_safe_message 对构建产物 _read_xkb_keymap 断言同一 RuntimeError 文案，实测有效。test_t043 删除的版本门禁例由受控构建身份三方一致测试接管，成立。但 f001（钩子注册行无断言）与 f002（真实 __init__ 实例属性覆盖缺口）两项 important 未解决：两处都是「产物已装配/已构造」的集成接缝，现有单测以切片与 __new__ 手工灌入绕过，只剩顺延 p096 的真机探针能兜底，不符合失效测试须有等价覆盖的测试策略，按规则判 FAIL。另注：test_repo_hygiene.py 复跑 1 failed（test_tracked_files_do_not_leak_developer_home_paths），违规文件全部为 docs/archive/tasks/t061/t062/t064/t066 的既存审阅文件，不在本 task diff 内，属基线问题、不计入本轮 finding。AC-001..003 未打勾系契约内 [deploy] 顺延 p096，未据此判负。

### AC 复验方式

- AC-004：TICK-VALID，re_verified。独立证据：x11_keymap.py 已删且 src/backend/cbrowser/stream_agent/ 全文 grep 无 ast./getsource/inspect 上游解析（仅文档词 "inspects"）；agent.py 改为 bind_webrtc_service_factory＋SELKIES_WEBRTC_SERVICE_FACTORY，无全局替换字面；策略单测以自有 MockWebRTCBaseService 为基类（test_stream_capture_policy.py、test_stream_takeover_chain.py 共 14 passed），不依赖上游私有类；新行为文件内 AC-004 静态守护与工厂未绑定 RuntimeError 接缝测试随 10 passed 一并通过。守护形式过窄记 f003（minor），不推翻打勾。
- AC-005：TICK-VALID，re_verified。独立证据：用仓内构建器在两个不同目录独立重建，wheel SHA256 两次均为 704c59b4fee1d150565515c86d5eb45a6ee00d455cbebaf0f1be34d13dc590f5，与 selkies_controlled_build.json 的 controlled.wheel_sha256 一致；上游 wheel 与补丁各翻转 1 字节均 ControlledBuildError 失败封闭；清单与 vendor pin/uv.lock/web 客户端清单哈希三方一致由 test_t063_selkies_controlled_build.py 7 passed 覆盖，客户端独立完整性由 test_t045_selkies_wheel_cache.py 4 passed 与 test_vendor_selkies_security.py 8 passed 复验未被本 task 破坏；构建产物 RECORD 经独立脚本校验自洽为 True。

## Round 2 (2026-11-14T05:58:16+08:00)

reviewed_scope: 176d8a26d73890a8（写前复算，与本轮实际审阅内容一致）

### Round 1 finding 复核

- t063_test_f001：已修属实。新用例 test_built_main_registers_service_through_the_hook 断言构建产物 `selkies/__main__.py` 中 `server.register_service("webrtc", _webrtc_service(server))` 恰出现一次且 stock 直构形式不存在；Round 1 的注册行回退变异现会被该断言逮住。随全套复跑通过。
- t063_test_f002：已修属实。新用例 test_built_keyboard_real_init_provides_every_attribute 经物化产物类的真实 `__init__`（传入 _FakeDisplay(113)）构造，逐项断言全部 17 个实例属性初值，并由该真实构造实例自行 `_find_spare_keycodes() == [191, 192, 193, 210, 211]`。一处保留说明：`_xkb` 的初值经模块头桩 `open_xkb_link` 返回 None（用例内已注明），断言的是 __init__ 的赋值路径与存在性、非真实 XKB 链接对象；其余 16 项均为真实初值。不构成缺口。
- t063_test_f003：主体已修，残留见本轮 f006。守护已扩为 stream_agent 包级 AST 扫描，真实包零误报（全套 70 passed 佐证，审阅者另以本地实例状态样本试探亦未误报）；审阅者注入试探确认可逮：别名深度 1 赋值 `selkies_main.WebRTCService = f`、同名 setattr、inspect 导入、SUPPORTED_SELKIES_VERSION 符号。但仍有拼写变体漏网，记 f006。
- t063_test_f004：已修属实。差异面测试已补 RECORD 逐条自洽校验（每条 sha256/size 与条目内容比对、记录条目集合与包内容集合相等、RECORD 自身条目格式）与 METADATA 仅 Version 行变化的双向行差断言，代码逐行核对无误且复跑通过。
- t063_test_f005：已修属实。探针已补读包内 cbrowser_build.json，断言 controlled_version == 已安装版本、上游 wheel_sha256 == 钉版值 18503b5c…、补丁序列恰 2 条且 sha256 为 64 位十六进制，输出 stamp_verified，e2e 已同步断言该字段。探针本体属 [deploy] p096 执行范围，本轮以代码核对＋字段两侧一致为准。

### Findings

### t063_test_f006 - AC-004 AST 守护按标识符含 selkies 子串判定，全点路径与 from-import 拼写的运行时替换仍漏网

- 严重度：minor
- 锚点：AC-004（f003 修复残留）
- 位置：tests/unit/test_t063_patched_keyboard_behavior.py（test_startup_has_no_runtime_patch_or_upstream_source_parsing 的 AST 扫描段）
- 问题：审阅者将守护逻辑原样复制到独立脚本、对临时包注入 8 种拼写逐一试探，结果：可逮 4 种（别名深度 1 赋值、含 selkies 名的 setattr、inspect 导入、ABI 符号）；漏网 4 种——`selkies.__main__.WebRTCService = f`（全点路径，深度 2 被收紧规则排除）、`from selkies import input_handler` 后 `input_handler._XTestKeyboard = f`（目标名不含 selkies 子串）、`from selkies.input_handler import _XTestKeyboard` 后 `_XTestKeyboard.prebind = f`（正是旧 monkey patch 最自然的拼写）、短别名 `setattr(m, 'WebRTCService', f)`。守护本质是标识符子串启发式，深度收紧解决了误报但留下上述真违规通道。属守护强度残留：当前包实测干净、AC-004 现状不受影响，故 minor。
- 建议：将判定从「名称含 selkies」改为导入溯源：先收集本文件内所有源于 selkies 包的导入绑定名（import / from-import 的全部别名），再对这些绑定名任意深度的属性赋值与 setattr 一律判违规；深度豁免只保留给非 selkies 溯源的对象。

### 结论

verdict: PASS

结论说明：Round 1 的 2 条 important（f001、f002）与 2 条 minor（f004、f005）已修属实，f003 主体已修、残留拼写漏网以 minor 记 f006，不阻断本轮。复跑实数：受影响集合（t063 两新文件＋t043＋binding_guards＋stream_agent_lifecycle＋docker_build_contexts＋capture_policy＋takeover_chain）70 passed，与实施方申报一致；其中 test_t063_selkies_controlled_build.py 10 passed、test_t063_patched_keyboard_behavior.py 13 passed。同轮 code 轴修复对 test 轴的影响已核：身份清单 wheel_url 已与 vendor 真实 URL 一致且有断言（构建测试内 upstream["wheel_url"] == PINNED_WHEEL_URL）、agent 启动受控包身份校验三态用例在 13 passed 内。AC-001..003 仍为契约内 [deploy] 顺延 p096，未据此判负。

### AC 复验方式

- AC-004：TICK-VALID，re_verified。证据：包级 AST 守护随 13 passed 通过且真实包零违规（审阅者独立同逻辑扫描复核为 clean）；注入试探逮住历史拼写形式的运行时替换/inspect 导入/ABI 符号重入（残留变体记 f006，minor，不推翻现状打勾）；真实 __init__ 覆盖与工厂接缝、启动受控包身份校验用例均在复跑集合内通过。
- AC-005：TICK-VALID，re_verified。证据：test_t063_selkies_controlled_build.py 扩至 10 passed，含 RECORD 逐条自洽、METADATA 仅 Version 行变化、wheel_url 与 vendor pin 一致、伪造 hunk 行数/显式源缺失/update 时 web 清单缺失三条新失败封闭用例；构建可复现与清单哈希一致断言持续通过，探针构建戳断言已与 e2e 两侧对齐（stamp_verified）。

## Round 2 (2026-11-14T05:59:34+08:00)

reviewed_scope: 176d8a26d73890a8

本轮为 Round 1 test 轴 5 条 finding 的确认审阅，独立复跑与探针均由本审阅者执行，不采信实施方自述。写前指纹实算为 176d8a26d73890a8，与预期一致。

复跑实数（门禁环境，解释器为 gate_venv）：tests/unit/test_t063_selkies_controlled_build.py 与 tests/unit/test_t063_patched_keyboard_behavior.py 合计 23 passed；实施方声称的受影响集合（上述两文件 + test_t043_selkies_pin.py + test_stream_binding_guards.py + test_stream_agent_lifecycle.py + test_docker_build_contexts.py + test_stream_capture_policy.py + test_stream_takeover_chain.py）合计 70 passed，与声称一致。

### t063_test_f001 - 已修属实

- 复核结论：已修属实。
- 证据：tests/unit/test_t063_patched_keyboard_behavior.py 的 test_built_main_registers_service_through_the_hook 对构建产物全文断言 `server.register_service("webrtc", _webrtc_service(server))` 恰出现一次、且 `server.register_service("webrtc", WebRTCService(server))` 不存在，断言面比 Round 1 建议的 run() 局部更严（全文）。审阅者独立构建受控 wheel 后实测：产物原文钩子形式计数 1、stock 形式不存在；将该行改回 stock 直构形式后，钩子计数变为 0 且 stock 形式出现，新增断言必然失败——注册行回退可被逮住，不再只剩顺延 p096 的真机链兜底。该用例随 23 passed 一并通过。

### t063_test_f002 - 已修属实

- 复核结论：已修属实。
- 证据：同文件 test_built_keyboard_real_init_provides_every_attribute 经真实 `_XTestKeyboard(_FakeDisplay(113))` 构造（不再走 `__new__` 手工灌入），逐项断言 17 个实例属性的初值：_d 非 None、_xkb/_group_hold/_group_restore 为 None、_shift_kc/_shift_r_kc/_altgr_kc 为 0、_effective_mod_keycodes 为空 set、_synth_mods/_overlay/_overlay_value_kc/_pressed_kc 为空 dict、_spare_keycodes 为 None、_spare_set 为空 frozenset、_text_codes 为 0、_settle_until 为 0.0、_overlay_order 为空 list；并由该真实构造的实例自行 `_find_spare_keycodes()` 得到 [191, 192, 193, 210, 211]。对应关系：被删 ABI 门禁守护的 6 个属性（_spare_keycodes/_spare_set/_text_codes/_overlay/_pressed_kc/_settle_until）全部包含在这 17 项内，且断言的是初值相等而非仅存在性。审阅者另对构建产物 input_handler.py 的 `__init__` 做 AST 核查：17 个属性均为 `__init__` 内无条件 self 赋值（另有一处 _read_effective_modifiers 方法引用赋值，不在断言清单内、不影响结论），上游改名/漏初始化任一属性都会使该用例失败。该用例随 23 passed 一并通过。

### t063_test_f003 - 主体已修，残留见本轮 f006

- 复核结论：主体已修属实；拼写变体漏网残留记本轮 t063_test_f006（minor），不推翻本条主体修复与 AC-004 现状。
- 证据：test_startup_has_no_runtime_patch_or_upstream_source_parsing 已扩为 stream_agent 包级 AST 扫描（深度 1 的 selkies 模块属性赋值、setattr 作用于 selkies 模块名、inspect 导入、SUPPORTED_SELKIES_VERSION 名称与字符串重现均判违规），原有的 agent.py 字面断言、src 全树 getsource( 扫描与 x11_keymap.py 不存在断言保留。审阅者向 src/backend/cbrowser/stream_agent/policy.py 临时注入违规逐项试探，四种形式均被该守护逮住（各 1 failed）：`setattr(selkies_main, "WebRTCService", ...)`、`selkies_main.WebRTCService = ...`、`import inspect`、`SUPPORTED_SELKIES_VERSION = "2.2.1"`。试探后已还原，policy.py 的 sha256 与注入前备份一致（1a29787ddb1da034a033933095d4d8f4047b655d8d57ecd362df157349d68903），还原后该守护用例 1 passed；现有 stream_agent 代码在 70 passed 的全集合复跑中零误报，深度 ≥2 的实例状态未被误判。收紧后仍能逮住真违规，成立。

### t063_test_f004 - 已修属实

- 复核结论：已修属实。
- 证据：test_built_wheel_differs_from_upstream_only_at_declared_surface 已补两项：RECORD 逐条自洽校验（recorded 条目集合与 controlled 包内文件集合相等、每条 sha256/size 与条目内容逐一比对，RECORD 自身条目断言为空哈希/空大小形式）与 METADATA 仅 Version 行变化断言（上游侧多出的行恰为 `Version: 2.2.1`、受控侧多出的行恰为 `Version: 2.2.1+cbrowser.1`）。审阅者独立构建后复算：RECORD 共 2170 条、条目集合与包内文件集合相等、未篡改时逐条自洽为 True；对 selkies/__main__.py 内容追加 1 字节后，按同款逻辑复算即在该条目检出哈希/大小不一致——差异面测试自身已能验证 RECORD 自洽，不再单靠整包 SHA256 兜底。该用例随 23 passed 一并通过。

### t063_test_f005 - 已修属实

- 复核结论：已修属实。
- 证据：tests/fixtures/stream_probe/x11_keymap_probe.py 已补读包内 selkies/cbrowser_build.json，断言 stamp 的 controlled_version 与 importlib.metadata 的已安装版本相等、upstream.wheel_sha256 恰为钉版值 18503b5c1491a04194f0a45fa10c547ffe5b4a24f33496ce5d56e97370a6a3cd、补丁序列恰 2 条且每条 sha256 为 64 位十六进制全匹配；输出新增 stamp_verified，tests/e2e/test_stream_x11_keymap_e2e.py 已同步断言 proof["stamp_verified"]。审阅者对独立构建产物内的构建戳复算：controlled_version 为 2.2.1+cbrowser.1、upstream.wheel_sha256 与探针钉版值及清单一致、补丁 2 条哈希为 30d5d4a44a8bb84f2bd681f64dd1209009ed119535adaef311121c807776b82e 与 a6a3d22dae0a98b7af039b41a670df09ff4ba3a6a62478b24c070b7e22aab681，均与清单一致且格式完整。原前缀断言保留为第一道，戳身份断言强度已达构建戳可达成的水平。e2e 本身属 [deploy] 顺延 p096，本轮以探针代码与构建戳实物核对为准，未声称实跑。

### t063_test_f006 - AC-004 AST 守护按标识符含 selkies 子串判定，全点路径与 from-import 拼写的运行时替换仍漏网

- 严重度：minor
- 锚点：AC-004（f003 修复残留）
- 位置：tests/unit/test_t063_patched_keyboard_behavior.py（test_startup_has_no_runtime_patch_or_upstream_source_parsing 的 AST 扫描段）
- 问题：本节初稿完成后，文件内出现一节并发写入的 Round 2（2026-11-14T05:58:16+08:00）提出本条；本审阅者以守护逻辑原样复刻脚本独立复验属实：深度 1 别名赋值与含 selkies 名的 setattr 可逮，但 `selkies.__main__.WebRTCService = f`（全点路径、深度 2 被收紧规则排除）、`from selkies import input_handler` 后 `input_handler._XTestKeyboard = f`（目标名不含 selkies 子串）、`from selkies.input_handler import _XTestKeyboard` 后 `_XTestKeyboard.prebind = f`、短别名 `setattr(m, 'WebRTCService', f)` 四种拼写均漏网（复刻脚本输出均为未标记）。属守护强度残留：当前 stream_agent 包实测干净、AC-004 现状不受影响，故 minor、不阻断本轮。
- 建议：将判定从「名称含 selkies」改为导入溯源：先收集本文件内所有源于 selkies 包的导入绑定名（import / from-import 的全部别名），再对这些绑定名任意深度的属性赋值与 setattr 一律判违规；深度豁免只保留给非 selkies 溯源的对象。

本轮新 finding 1 条：t063_test_f006（minor，f003 残留，不阻断）。

## 结论

verdict: PASS

结论说明：Round 1 的 2 条 important（f001 注册行接缝、f002 真实 __init__ 属性覆盖）与 2 条 minor（f004 RECORD/METADATA 粒度、f005 探针戳断言弱）经独立复跑、产物实测与注入探针逐条确认均已修属实；f003 主体已修、残留拼写漏网以 minor 记 f006，不阻断本轮。复跑实数：t063 两文件 23 passed，受影响集合 70 passed，与实施方声称一致。同轮 code 轴修复带来的新增面（清单 wheel_url 一致性、构建器 hunk 行数/显式源/下载归一/update 失败封闭、agent.py 启动戳校验三态）已包含在上述 23/70 passed 的用例集合内，test 轴复跑未见回归。AC-001..003 仍为契约内 [deploy] 顺延 p096，未据此判负，与 Round 1 口径一致。

### AC 复验方式

- AC-004：TICK-VALID，re_verified。证据：包级 AST 守护用例随 23 passed 通过；审阅者四种违规注入（setattr 于 selkies 模块、selkies 模块属性赋值、inspect 导入、SUPPORTED_SELKIES_VERSION 重现）均被逮住（各 1 failed），还原后 1 passed 且文件哈希与注入前一致；现有 stream_agent 代码在 70 passed 全集合中零误报，x11_keymap.py 已删、src 全树无 getsource( 的 Round 1 证据基础未变；守护的拼写变体漏网记 f006（minor 残留，当前包实测干净，不推翻现状打勾）。
- AC-005：TICK-VALID，re_verified。证据：独立构建产物复算 RECORD 2170 条逐条自洽、集合相等、内容篡改 1 字节可被差异面同款逻辑检出，METADATA 与上游仅 Version 行不同（2.2.1 → 2.2.1+cbrowser.1）；包内构建戳 controlled_version/upstream 哈希/2 条补丁哈希与清单三方一致，探针已按戳断言且 e2e 同步断言 stamp_verified；t063 两文件 23 passed 与受影响集合 70 passed 复验了清单一致性、两次构建同哈希与失败封闭用例。

## Round 3 (2026-11-14T06:05:25+08:00)

reviewed_scope: 2554b9db3bc6b49f

本轮为收尾口径修正的确认审阅：AC-001..003（[deploy]）已按仓内先例（t061/t066）与 finish 门禁机制补打勾，本审阅者从测试/证据轴独立复核三条 [deploy] AC 的打勾依据（实现完成＋云端可验部分实证＋真实链顺延如实登记），并逐行重写全部 5 条 AC 的复验判定。写前指纹实算为 2554b9db3bc6b49f，与预期一致。

复跑实数（门禁环境，解释器为 gate_venv）：tests/unit/test_t063_selkies_controlled_build.py 与 tests/unit/test_t063_patched_keyboard_behavior.py 合计 23 passed（其中键盘/钩子行为文件 13 passed，逐例含钩子三态 test_built_hook_defaults_to_stock_service、test_built_hook_resolves_named_factory、test_built_hook_rejects_malformed_factory_reference，注册行断言 test_built_main_registers_service_through_the_hook，工厂接缝 test_policy_factory_seam_fails_loud_until_bound，启动身份校验 test_controlled_build_startup_verification，键盘行为 5 例与真实构造 1 例 test_built_keyboard_real_init_provides_every_attribute）；tests/unit/test_stream_capture_policy.py 12 passed、tests/unit/test_stream_takeover_chain.py 2 passed（策略单测合计 14 passed）；tests/unit/test_stream_clipboard_policy.py 2 passed、tests/unit/test_stream_resume.py 3 passed；另含 lifecycle、binding_guards、t043 的合并集合 46 passed，无回归。

仲裁未改动核查：policy.py 相对 diff_anchor 的 diff 为 34 行新增、0 行删除，内容仅为文件头部的具名工厂注册表（bind_webrtc_service_factory、create_policy_service 与 __all__ 增补），现行 active_peers/consumer 仲裁逻辑未被本 task 触碰。

真实链顺延核查：p096 逐项登记了 AC-001 的 Stream 镜像重建与 WebRTC 首帧（HELLO/client_tab_id/resume_key 实链）、AC-002 的真实信号帧率仲裁、AC-003 的中文 IME 与剪贴板与复制标签隔离与 viewer resume 实链及 x11 keymap e2e，处理状态为未开；progress.md 的「收尾口径更正」与收尾报告均显式写明真实部署链顺延 p096、未冒充已验，与 p096 登记一致。

### Findings

本轮零新 finding。

## 结论

verdict: PASS

结论说明：三条 [deploy] AC 的打勾依据成立——实现已完成，云端可验部分（构建产物层的工厂钩子三态、注册行、工厂接缝、启动身份校验、仲裁策略单测、键盘行为与真实构造、剪贴板/resume 既有单测）经本审阅者亲自复跑实证通过，真实部署链部分未验且已如实登记 p096 顺延、未冒充已验，符合仓内 t061/t066 先例与 finish 门禁口径。AC-004/AC-005 维持 Round 2 判定，未见回归。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。云端可验部分实证：钩子三态、注册行断言 test_built_main_registers_service_through_the_hook、工厂接缝与启动身份校验用例随 t063 两文件 23 passed 通过，产物层证据链完整；真实首帧即 HELLO/client_tab_id/resume_key 实链部分云端未验，已登记 p096 顺延，未冒充已验。
- AC-002：TICK-VALID，re_verified。云端可验部分实证：test_stream_capture_policy.py 12 passed 与 test_stream_takeover_chain.py 2 passed 合计 14 passed，仲裁语义的现行策略单测证据仍在且通过；policy.py 相对 diff_anchor 仅新增 34 行具名工厂注册表、0 行删除，仲裁逻辑未被本 task 改动；真实信号下的 8/30 FPS 仲裁与暂停恢复实链部分云端未验，已登记 p096 顺延，未冒充已验。
- AC-003：TICK-VALID，re_verified。云端可验部分实证：构建产物键盘行为 5 例与真实构造 1 例随 13 passed 通过，spike s020 已验证补丁后键盘三行为与现行生产 wrapper 逐项等价，剪贴板策略 test_stream_clipboard_policy.py 2 passed 与 resume test_stream_resume.py 3 passed 仍在且通过；真实中文 IME、剪贴板、复制标签隔离与 viewer resume 实链部分云端未验，已登记 p096 顺延，未冒充已验。
- AC-004：TICK-VALID，re_verified。维持 Round 2 判定：包级 AST 守护用例随 13 passed 通过、stream_agent 包实测干净，x11_keymap.py 已删且无运行时全局替换与上游源码解析；守护拼写漏网残留为 minor 并已遗留 p097，不推翻现状打勾，本轮未见回归。
- AC-005：TICK-VALID，re_verified。维持 Round 2 判定：test_t063_selkies_controlled_build.py 随 23 passed 通过，受控包可从固定上游制品与已记录补丁重复构建且最终哈希与清单一致，RECORD 逐条自洽与 METADATA 仅 Version 行变化断言持续通过，客户端静态资源独立完整性验证未被破坏，本轮未见回归。
