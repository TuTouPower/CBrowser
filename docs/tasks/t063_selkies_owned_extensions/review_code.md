# Task review t063（reviewer_focus: 代码）

task: t063
spec: docs/tasks/t063_selkies_owned_extensions/task.md
diff_anchor: 501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90
target: t063_selkies_owned_extensions
round: 1
reviewed_at: 2026-11-14T05:52:09+08:00
reviewed_scope: 316029d874de8907

## Findings

### t063_code_f001 - 身份清单的 upstream wheel_url 是错的，干净环境下 Stream 镜像构建在下载步直接失败

- 严重度：important
- 锚点：AC-005（受控包可从固定上游制品重复构建、两端来源关系可追溯）
- 位置：config/selkies/selkies_controlled_build.json:28；scripts/build_selkies_controlled.py:285；config/docker/stream_runtime/Dockerfile:41-47
- 问题：清单记录的 `wheel_url` 为 `https://files.pythonhosted.org/packages/68/c8/8122b46b…/selkies-2.2.1-py3-none-any.whl`，与 vendor pin 的 URL 不一致（`scripts/vendor_selkies_web.py:23-27` 为 `packages/40/33/ece2923d0…`）。我实测：清单 URL `curl -sI` 返回 `HTTP 404 Not Found`（`Reason: Incorrect project bucket`），vendor URL 返回 `HTTP 200 OK`。Dockerfile builder 阶段把脚本拷到 `/tmp`，其 `DEFAULT_CACHE_DIR` 解析为 `/.scratch/selkies_wheels`（空缓存），`--allow-download` 是唯一取源路径、且下载地址正是清单 URL；我按 Dockerfile 同款布局在 /tmp 模拟运行（脚本+清单+补丁同位拷贝、空缓存、`--allow-download`），进程以未捕获的 `urllib.error.HTTPError: HTTP Error 404: Not Found` 退出（exit 1），根本走不到哈希校验。本地门禁之所以全绿，是因为本地缓存里已有钉版 wheel、下载路径从未被 exercising；且 `tests/unit/test_t063_selkies_controlled_build.py` 的 `test_manifest_consistent_with_vendor_pin_lock_and_web_client` 只断言 wheel_sha256/filename/version 与 vendor pin 一致，从不断言 URL——这条漂移没有任何门禁守得住。ADR 034 与 progress 把该清单称为「上游版本/文件名/SHA256/URL」完整身份记录，按记录的 URL 无法取回所钉制品，身份记录本身失实。
- 建议：将清单 `wheel_url` 改为 vendor pin 的真实 URL（`packages/40/33/ece2923d0…`）；在身份一致性测试中补 `upstream["wheel_url"] == vendor_module.PINNED_WHEEL_URL` 断言；修复后以空缓存实跑一次 `--allow-download` 构建复验。

### t063_code_f002 - agent 启动不校验受控包身份，装到官方原版 wheel 时工厂被静默忽略、策略层整体不生效也不报错

- 严重度：minor
- 锚点：AC-001/AC-004 的启动接缝行为（policy.py 声称「未绑定调用即失败」只在受控钩子存在时成立）
- 位置：src/backend/cbrowser/stream_agent/agent.py:1190-1199
- 问题：`run_standalone_service` 只是 `bind_webrtc_service_factory(...)` + 设置 `SELKIES_WEBRTC_SERVICE_FACTORY` 环境变量 + 调 `selkies_main.main()`，全程不检查已安装 selkies 是否为受控构建（不查 `selkies/cbrowser_build.json` 构建戳、不查 `selkies.__main__` 是否有 `_webrtc_service`、不查版本是否为 `2.2.1+cbrowser.1`）。我核对钉版原版 wheel 的 `selkies/__main__.py:173` 仍是硬编码 `WebRTCService(server)`、从不读该环境变量——所以一旦运行环境装的是官方 2.2.1（例如 pyproject `stream` 组与 `config/docker/stream_runtime/requirements.txt` 钉的正是 `selkies==2.2.1`，任何非镜像方式拉起 agent 都是这个状态），工厂永远不会被调用，采集仲裁、输入拦截与 takeover 上报静默缺席，进程表面正常启动，与「fail loudly」的设计口径不符。现行唯一部署路径（Stream 镜像）在构建期有戳校验兜底，故定 minor。
- 建议：在 `run_standalone_service` 的边界校验段增加受控包身份校验（构建戳存在且 upstream/补丁哈希与清单一致，或版本号等于受控版本），不符按 `BOUNDARY_ERROR` 同款 `sys.exit(1)` 失败封闭。

### t063_code_f003 - unified diff 应用器不校验 hunk 声明行数，行数说谎的补丁会被静默接受

- 严重度：minor
- 锚点：行为缺陷（构建脚本「零 fuzz 精确上下文应用」的完整性）
- 位置：scripts/build_selkies_controlled.py:68、91-117
- 问题：`_HUNK_RE` 只取 hunk 起始行，解析时把声明的旧/新行数（group 2/4）完全丢弃、正文按「直到下一个 @@ 为止」收集，与声明行数从不比对。我实测：源 `a\nb\nc\nd\ne\n` 配补丁头 `@@ -2,99 +2,99 @@`、正文只有一行 `-b/+B`，`apply_unified_patch` 照常成功输出 `a\nB\nc\nd\ne\n`——标准 `git apply` 会拒绝这种补丁。另注：正文里删除一行以 `-- ` 开头的内容（diff 行形如 `--- x`）会被误判为文件头并以 target 不一致拒绝（fail-closed，不产生静默错果，仅记录）。当前两份已提交补丁无此问题：我逐 hunk 核对 8 个 hunk 的声明行数与正文全部一致，`git apply --check` 通过，且 git apply 产物与构建器产物逐字节相同——故对当前制品无影响，仅是应用器口径缺口。
- 建议：每个 hunk 落盘前校验解析出的旧行数/新行数与声明值相等（声明缺省按 1 计），不符即 `ControlledBuildError`。

### t063_code_f004 - _resolve_source_wheel 对显式 --source-wheel 缺失静默回退缓存，下载错误也不归一为 ControlledBuildError

- 严重度：minor
- 锚点：行为缺陷（构建脚本失败封闭的完整性）
- 位置：scripts/build_selkies_controlled.py:265-292、main 的异常处理（仅捕获 ControlledBuildError）
- 问题：候选循环对「不是文件」的候选直接跳过——显式传了 `--source-wheel <路径>` 而该路径不存在时，不报错、静默改用缓存 wheel，调用方的路径写错被掩盖（哈希对得上就照常出包）。另外 `urlopen` 的 `HTTPError/URLError` 不在换算之列：f001 的模拟运行实测就是以原始 traceback 退出而非脚本定义的 `controlled build failed: …` 清洁失败口径。两者都不产生错误产物（退出码仍为非零），故定 minor，但与脚本 docstring「Every check fails closed」的表述有落差。
- 建议：`source_arg is not None` 时该路径不存在或哈希不符直接报错，不进缓存回退；下载段把 `urllib.error.URLError` 归一为 `ControlledBuildError`。

### t063_code_f005 - --update-manifest 模式下 web 清单哈希可静默沿用旧值，且受控包哈希为自填自验

- 严重度：minor
- 锚点：AC-005（清单字段与实际产物处处一致的要求）
- 位置：scripts/build_selkies_controlled.py:293-311、329-345
- 问题：`compute_manifest_fields` 仅当 `REPO_ROOT / web_client.manifest` 是文件时才重算 `manifest_sha256`，否则静默保留清单里的旧值并照常报告更新成功。`REPO_ROOT` 取脚本文件位置的父父目录——在脚本被单独拷走的布局（正是 Dockerfile 的 /tmp 布局形态）下该路径指错地方，web 清单根本不存在，于是「已更新」的清单可以带着一条从未复算过的 web 哈希出门。同一模式下 `controlled.wheel_sha256` 由本次构建产物回填、且本轮跳过 expected 比对——作为再生工具这本身合理，但意味着 update 模式自身不构成任何独立验证，独立锚点只有已提交清单在非 update 路径（单测与 Dockerfile 构建）里的比对；update 后若无人再跑非 update 校验，自填值即成「事实」。
- 建议：update 模式下 web 清单文件缺失应直接失败而非沿用旧值；并在脚本帮助或清单说明中写明 update 只是再生、合入前必须再跑一次非 update 构建校验（现行单测已覆盖已提交状态，此条针对未来改版流程）。

### t063_code_f006 - 现行 spec/blueprint 仍残留已被 t063 删除的 ABI 适配层表述，与同文件新段落互相矛盾

- 严重度：minor
- 锚点：Finalization 文档闭环（blueprint/spec 与实现一致）
- 位置：docs/specs/webrtc_remote_display.md:65；docs/blueprint/testing.md:230
- 问题：spec 第 65 行仍以现行口径写「Selkies 私有 API 只经适配层访问，钉版 ABI 不符明确报 unsupported」——适配层（`x11_keymap.py`）与 ABI 门禁正是本 task 删除的对象，该行与同文件末尾新增的「Selkies 扩展边界（t063）」段（「运行时不替换上游模块、不解析上游源码、不校验私有 ABI」）直接矛盾，实施时未顺手修正。testing.md 第 230 行的 t032 运行映射表仍把已删除的 `test_stream_keymap_abi.py` 列为 keymap 的 unit 门禁与「Stream keymap ABI 适配层」对象。archive 与历史 ADR 内的旧表述属历史记录、不计入本条。
- 建议：第 65 行改为受控构建口径或标注已被 t063 段取代；testing.md 第 230 行更新为 t063 的两个新测试文件或标注该行已废止。

## 结论

verdict: FAIL

受控构建的核心机制本身成立：我独立复跑了构建，两次产物字节一致、SHA256 `704c59b4fee1d150565515c86d5eb45a6ee00d455cbebaf0f1be34d13dc590f5` 与清单相等；RECORD 逐条哈希/长度校验合规、dist-info 改名完整（METADATA 仅 Version 行变化，WHEEL/entry_points.txt/top_level.txt/licenses 改名后逐字不变）、固定时间戳/权限/ZIP_STORED 与条目顺序确定；`git apply --check` 通过且 git apply 产物与构建器产物逐字节相同；补丁 0002 与基线 `x11_keymap.py` wrapper 逐行比对语义等价（named 过滤的 preferred/_text_codes 重算、text_room 整池回退、prebind 以 batch 为口径的 protected 容量扣除与绑定后 reload+settle 重置均一致）；补丁 0001 钩子默认/覆盖/非法三态与错误传播（ValueError 经 selkies main 归一为 exit 1）无误；agent 绑定顺序（bind 与 env 设置均在 `selkies_main.main()` 之前）正确；`x11_keymap`/`install_x11_keymap_refresh`/`SUPPORTED_SELKIES_VERSION` 在现行 src/tests/fixtures 中无残留（仅 archive 与历史文档提及）。但 f001 是 important 级硬伤：身份清单里记录的上游 URL 是假的（实测 404），按清单与 Dockerfile 在干净环境根本构建不出受控包——AC-005 的「可重复构建、来源可追溯」按所记录的身份不成立，必须先修 f001 才能 PASS；其余 5 条为 minor，不单独阻断。

### AC 复验方式

- AC-004：TICK-VALID，re_verified。我独立 grep 全仓 src/：stream_agent 内无 `getsource`、无对 Selkies 的 ast/inspect 源码解析（仓内仅 api/supervisor 两处对 websockets 的 `inspect.signature`，与 Selkies 无关），`x11_keymap.py` 已不存在，agent.py 无 `selkies_main.WebRTCService =` 赋值；独立复跑 t063 两个新测试文件 17 passed，其中含策略工厂未绑定即 RuntimeError 与对构建产物执行的行为断言。
- AC-005：TICK-VOID，re_verified。我以本地缓存 wheel 独立构建确可复现且哈希与清单相等、RECORD 校验合规，但清单记录的 `wheel_url` 实测 404、与 vendor pin 的真实 URL 不一致，按 Dockerfile 同款布局（空缓存 + `--allow-download`）模拟构建以 HTTPError 404 失败——「可从固定上游制品重复构建、来源关系可追溯」按清单所记录的身份在干净环境不成立，见 t063_code_f001。

## Round 2 (2026-11-14T05:59:58+08:00)

reviewed_scope: 176d8a26d73890a8

本轮为 Round 1 code 轴 6 条 finding 的确认审阅：逐条独立读码、独立探针与独立复跑，不采信实施方自述。复跑实数：t063 两个新测试文件 23 passed（test_t063_selkies_controlled_build.py 10 项 + test_t063_patched_keyboard_behavior.py 13 项）；与 test_t043_selkies_pin.py、test_stream_binding_guards.py 合跑 32 passed（干净状态复跑）。

### Findings 复核

#### t063_code_f001（important）— 已修属实

- 复核结论：已修属实。
- 证据：`config/selkies/selkies_controlled_build.json:28` 的 `upstream.wheel_url` 已为 `https://files.pythonhosted.org/packages/40/33/ece2923d078b414bed7c1e74e15ba83be34f77ecfc5092d58103bda3f210/selkies-2.2.1-py3-none-any.whl`，与 `scripts/vendor_selkies_web.py` 的 `PINNED_WHEEL_URL` 逐字一致；我对该 URL 实测 `curl -sI` 返回 `HTTP 200 OK`（`x-pypi-file-project: selkies`）。`tests/unit/test_t063_selkies_controlled_build.py:65` 新增断言 `upstream["wheel_url"] == vendor_module.PINNED_WHEEL_URL`，漂移从此有门禁。决定性复验：我按 Dockerfile 布局在仓内 `.scratch/r2sim/tmp` 拷贝脚本+清单+两份补丁（脚本派生的缓存目录 `.scratch/r2sim/.scratch/selkies_wheels` 初始为空）、以 `--allow-download` 实跑，exit 0，下载落盘上游 wheel 并构建成功，产物 SHA256 为 `704c59b4fee1d150565515c86d5eb45a6ee00d455cbebaf0f1be34d13dc590f5`，与清单 `controlled.wheel_sha256` 相等；模拟目录已清理。Round 1 的 404 干净环境失败不再复现。

#### t063_code_f002（minor）— 已修属实

- 复核结论：已修属实。
- 证据：`src/backend/cbrowser/stream_agent/agent.py` 新增 `verify_controlled_selkies_build()`：构建戳 `selkies/cbrowser_build.json` 缺失、戳不可读、`controlled_version` 与已安装 dist 版本不符、戳内 `upstream.wheel_sha256` 为空，四种情形均 raise RuntimeError（其中空 sha 与坏 JSON 两情形为我直接调用该函数的独立探针实测：空 sha 报「lacks upstream identity」、坏 JSON 报「stamp unreadable」）。`run_standalone_service` 在启动 try 段内、于 `bind_webrtc_service_factory(...)`（后续行）之前调用该校验，失败经既有启动异常路径 `sys.exit(1)` 封闭——官方原版 wheel（无戳）不再能静默无策略启动。`test_controlled_build_startup_verification` 覆盖戳缺失/版本不符/合法三态，在 23 passed 集合内通过。

#### t063_code_f003（minor）— 已修属实

- 复核结论：已修属实。
- 证据：`scripts/build_selkies_controlled.py` 的 `apply_unified_patch` 现解析并保留每个 hunk 声明的旧/新行数（声明缺省按 1 计），落盘前校验正文旧/新行数与声明相等，不符 raise ControlledBuildError。我以 Round 1 同款说谎补丁（`@@ -2,99 +2,99 @@`、正文仅 `-b/+B`）直接调用实测被拒，错误为「declares -99/+99 but carries -1/+1」；缺省计数补丁（`@@ -2 +2 @@`）仍正常应用，无误伤。新用例 `test_patch_with_lying_hunk_counts_is_rejected` 在 23 passed 集合内通过。

#### t063_code_f004（minor）— 已修属实

- 复核结论：已修属实。
- 证据：`_resolve_source_wheel` 对显式 `--source-wheel` 改为权威处理：路径不存在直接 ControlledBuildError（新用例 `test_explicit_missing_source_wheel_is_an_error_not_a_fallback` 通过）；哈希不符直接 ControlledBuildError——我以内容错误的同名文件直接调用独立探针实测被拒，不回退缓存。下载段 `urlopen` 外包 try，`URLError/OSError/TimeoutError` 归一为 ControlledBuildError；我 mock `urlopen` 抛 URLError 独立实测得到归一后的 ControlledBuildError（`HTTPError` 为 `URLError` 子类，Round 1 的原始 traceback 退出路径已消除）。

#### t063_code_f005（minor）— 已修属实

- 复核结论：已修属实。
- 证据：`compute_manifest_fields` 在 web 清单文件缺失时改为 raise ControlledBuildError（「web client manifest not found for hash recompute」），不再静默沿用旧哈希；新用例 `test_update_manifest_fails_when_web_manifest_missing` 在 23 passed 集合内通过。`--update-manifest` 的 `--help` 文本我实跑核对，已注明「regeneration only; afterwards re-run without this flag to verify the committed manifest against an independent build」，Round 1 建议的「update 仅再生、须再跑非 update 校验」口径已落地；已提交清单的非 update 校验由单测持续锚定。

#### t063_code_f006（minor）— 已修属实

- 复核结论：已修属实。
- 证据：`docs/specs/webrtc_remote_display.md:65` 已改 t063 口径：「Selkies 扩展自 t063 起经受控构建包承载（见『Selkies 扩展边界（t063）』），不再经适配层访问私有 API、启动不做 ABI 校验」，与同文件 t063 段（受控构建包、运行时不替换上游模块、不解析上游源码、不校验私有 ABI）不再矛盾。`docs/blueprint/testing.md:230` 的 p024 keymap 行已更新为 `test_t063_patched_keyboard_behavior.py`、`test_stream_binding_guards.py`，对象改为「Stream keymap 行为（t063 起为受控构建包内实现，原 ABI 适配层已删除）」，已删除的 `test_stream_keymap_abi.py` 与「Stream keymap ABI 适配层」表述在被引两处均已消失。

### 新 finding

本轮零新 finding（t063_code_f007 起无新增）。

## 结论

verdict: PASS

Round 1 的 important（f001）已彻底修复并经空缓存下载构建独立复现同哈希，5 条 minor（f002–f006）逐条复核已修属实、证据如上；受控构建的核心事实与 Round 1 独立验证一致（两次构建字节一致、最终哈希 `704c59b4fee1d150565515c86d5eb45a6ee00d455cbebaf0f1be34d13dc590f5` 与清单相等），且本轮下载路径、启动身份校验、补丁行数校验、失败归一与 update 失败封闭均经独立探针而非仅读测试。无 critical/important 未决项，判 PASS。

### AC 复验方式

- AC-004：TICK-VALID，re_verified。我独立 grep 全仓 src/ 无 `getsource`、`stream_agent/x11_keymap.py` 不存在、agent.py 无 `selkies_main.WebRTCService =` 运行时赋值；t063 两新文件 23 passed 内含包级 AST 守护、策略工厂未绑定即 RuntimeError、构建产物行为断言，以及本轮新增的受控包启动身份校验三态用例——启动不再解析上游源码/私有 ABI 清单的打勾持续成立。
- AC-005：TICK-VALID，re_verified（Round 1 的 TICK-VOID 改判）。f001 修复后身份清单 `wheel_url` 与 vendor pin 逐字一致且实测 HTTP 200、一致性测试已补 URL 断言；我按 Dockerfile 布局以空缓存 `--allow-download` 独立构建成功，产物 SHA256 `704c59b4fee1d150565515c86d5eb45a6ee00d455cbebaf0f1be34d13dc590f5` 与清单相等——「可从固定上游制品重复构建、两端来源关系可追溯」按清单所记录的身份在干净环境现已成立。

## Round 3 (2026-11-14T06:05:07+08:00)

reviewed_scope: 2554b9db3bc6b49f

本轮为收尾口径修正的确认审阅：只复核 AC-001..003（[deploy]）补打勾的依据是否成立，并确认 Round 2 之后无实现回退，不重开 Round 1/2 已闭环事项。写前以门禁同款函数实算指纹为 2554b9db3bc6b49f，与预期一致。复跑实数：test_t063_patched_keyboard_behavior.py 13 passed、test_t063_selkies_controlled_build.py 10 passed、test_stream_capture_policy.py 12 passed、test_stream_takeover_chain.py 2 passed，合计 37 passed。

### AC-001 复核（实现面与云端证据）

受控包实现面完整：补丁 0001 在受控包 `selkies/__main__.py` 新增 `_webrtc_service(server)` 钩子——无 `SELKIES_WEBRTC_SERVICE_FACTORY` 时回落 stock `WebRTCService(server)`、有值时按 `module:attribute` 解析、格式非法 raise ValueError——且 `run()` 的注册行由直构改为 `server.register_service("webrtc", _webrtc_service(server))`，会话仍走官方 server 与 HELLO/client_tab_id/resume_key 路径，钩子只替换服务构造来源。运行时侧 `policy.py` 新增具名工厂注册表（`bind_webrtc_service_factory`/`create_policy_service`，未绑定调用 raise RuntimeError），`agent.py` 的 `run_standalone_service` 在调 `selkies_main.main()` 之前先 `verify_controlled_selkies_build()` 校验构建戳与受控版本、再 `bind_webrtc_service_factory(service_factory)` 并设置环境变量指向 `cbrowser.stream_agent.policy:create_policy_service`；原 `selkies_main.WebRTCService = patched_factory` 全局替换与 `install_x11_keymap_refresh()` 安装段已删除。云端证据真实存在且本轮复跑通过：产物钩子三态用例（默认 stock、具名工厂解析、非法引用拒绝）、注册行断言用例（`test_built_main_registers_service_through_the_hook`：钩子注册形式恰一次且 stock 直构形式不存在）、工厂接缝未绑定即失败用例与启动身份校验用例均在 13 passed 集合内。真实镜像内首帧链云端未验，已登记 p096 第 1 项顺延，未冒充已验。

### AC-002 复核（仲裁语义未被本 task 改变）

`git diff 501ac0b -- src/backend/cbrowser/stream_agent/policy.py` 只有一个 hunk（`@@ -28,13 +28,47 @@`）：`__all__` 新增两名与文件头工厂注册表，位置在 `LiveCapturePolicyAgent` 类定义之前，该类及其依赖的 `policy_rules.py`、前端与 gateway 侧均不在本 task 变更集内，仲裁语义未被触碰。策略行为证据有效且本轮复跑通过：test_stream_capture_policy.py 12 passed（静止回落 8 FPS、运动/输入升 30 FPS、恢复先设 8 FPS 再 resume 并请求 IDR、配额规则等）与 test_stream_takeover_chain.py 2 passed，合计 14 passed，与 progress 所称「策略单测 14 项复验通过」一致。真实信号下的仲裁链（active_peers/consumer 实信号、零 consumer 暂停恢复、单 consumer 暂停不压低其他 consumer）云端未验，已登记 p096 第 2 项顺延，未冒充已验。

### AC-003 复核（键盘等价与未触碰面）

键盘三行为已入受控包补丁 0002（named spare 过滤与 `_text_codes` 重算、text_room 整池回退、prebind 以 batch 为口径的 protected 容量扣除与绑定后 reload 加 settle 重置），与被删 `x11_keymap.py` wrapper 的等价性有两层独立证据：spike s020 报告的逐项等价实验（evdev 与非 evdev 两体系 spare 池同为 [191, 192, 193, 210, 211]、text_codes 分别 0 与 3、text_room 分别 4 与 2、prebind 双方各恰一次重载、4/5 池槽被按住时双方均拒绝），以及直接对构建产物执行的产物行为测试（named 过滤、text_room 回退、prebind 单次重载、容量拒绝、真实 `__init__` 构造断言全部 17 个实例属性），均在本轮 13 passed 集合内通过。剪贴板、复制标签隔离与 viewer resume 相关实现未被本 task 触碰：`git diff 501ac0b --name-only` 的变更集不含前端、gateway 与信令/resume 处理文件，`agent.py` 的 diff hunk 仅限 import、新增 `verify_controlled_selkies_build` 与 `run_standalone_service` 启动段，HELLO/resume_key/viewer worker 处理区域不在 hunk 内。中文 IME 与普通键盘的真实输入链、剪贴板、复制标签隔离与 viewer resume 实链云端未验，已登记 p096 第 3 项顺延，未冒充已验。

### Round 2 后变更集复核

对照 Round 2 时点（reviewed_scope 176d8a26d73890a8）的变更集，本轮全量变更集仍为同一批实现与测试文件（agent.py、policy.py、x11_keymap.py 删除、受控构建脚本与清单与两份补丁、t063 两新测试文件及既有测试的处置、Dockerfile 与蓝图/spec 更新），其实质内容与 Round 2 逐条复核过的描述一致，本轮 37 passed 复跑亦证明无实现回退；Round 2 之后的增量仅限 task.md 对 AC-001..003 的打勾、progress.md 的收尾口径更正与收尾报告、test 轴 Round 2 minor 遗留 p097 与审阅文件本身。另注：p096 来源行仍留更正前的「未打勾」措辞，但其正文三项与「处理：未开」如实登记真实链未验，progress 的更正条已明确取代旧口径——该残留是低报而非冒充已验，不影响打勾依据成立，不立 finding。

### Findings

本轮零新 finding（t063_code_f007 起无新增）。

## 结论

verdict: PASS

AC-001..003 的打勾依据成立：三条的实现均已完成，云端可验部分（受控包钩子与注册行与接缝与启动身份校验、帧率仲裁单测、键盘产物行为与 spike 等价实验）经本轮独立复跑实证，真实部署链部分如实登记 p096 顺延且未冒充已验，口径与仓内 t061/t066 先例及 finish 门禁机制一致；AC-004/AC-005 的 Round 2 TICK-VALID 判定在本轮复跑下持续成立。无 critical/important/minor 新问题，判 PASS。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。补丁 0001 钩子三态与 run() 注册行、policy.py 工厂注册表、agent 工厂绑定与环境变量设置均在 selkies_main.main() 之前且无运行时全局替换，verify_controlled_selkies_build 在启动段先行校验，产物钩子三态与注册行断言与接缝测试在本轮 13 passed 内通过；真实首帧链云端未验，已登记 p096 顺延，未冒充已验。
- AC-002：TICK-VALID，re_verified。policy.py 相对锚点仅一个 hunk 新增工厂注册表，LiveCapturePolicyAgent 类体与 policy_rules 未被触碰，test_stream_capture_policy 与 test_stream_takeover_chain 合计 14 passed 复验仲裁行为；真实信号仲裁链云端未验，已登记 p096 顺延，未冒充已验。
- AC-003：TICK-VALID，re_verified。键盘三行为已入受控包补丁 0002，s020 等价实验与构建产物行为测试逐项实证且在本轮 13 passed 内通过，剪贴板与复制标签隔离与 viewer resume 相关代码经 diff 核对未被本 task 触碰；IME 与剪贴板与 resume 真实链云端未验，已登记 p096 顺延，未冒充已验。
- AC-004：TICK-VALID，re_verified。本轮复跑的 13 passed 行为测试含包级 AST 守护与策略工厂未绑定即 RuntimeError 与受控包启动身份校验，Round 2 的独立 grep 结论持续成立，启动不解析上游源码与私有 ABI 清单的打勾有效。
- AC-005：TICK-VALID，re_verified。本轮复跑的 10 passed 受控构建测试含身份三方一致与两次构建同哈希与差异面恰为声明面，Round 2 以空缓存下载独立构建同哈希 704c59b4fee1d150565515c86d5eb45a6ee00d455cbebaf0f1be34d13dc590f5 的结论持续成立，打勾有效。
