---
tid: "t063"
slug: "selkies_owned_extensions"
title: "Selkies 采集与输入扩展改为自有稳定边界"
status: "done"
branch: "t063_selkies_owned_extensions"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90"
depends_on: ""
conflicts_with: "t061,t062,t065,t068"
note: "来源 p072；保留纯 WebRTC，不纳入 p077 双模或 TURN 提议"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-13 审阅修订：采纳受控构建制品建议，保留技术 spike 选择，不武断指定全量 fork；原 AC-001..005 保留编号。

- 本次仅维护 backlog；不 start、不实现；旧归档来源只追加转办链，不改写历史。

- 调度字段经 task.py edit 写入；plan 的 runnable 只指依赖/冲突候选，不代表产品 BLOCKING 已解决。

- 调度依据：Stream 启动/依赖与 Docker 构建同 t062/t065/t068 重叠，媒体恢复验证同合并后的 t061 重叠；无已证明的硬产物依赖。

- 2026-11-14 执行（cloud-t063）：run-begin attempt 1（execution 1622e070），preflight 初检 1 条警告（未知契约 UNVERIFIED-SPIKE），先行正式 spike s020 后回填结论、严格 preflight（--require-verified）PASS 才实施。

- Spike s020 结论（`docs/spikes/s020_selkies_221_extension_points/report.md`）：逐文件核查钉版 wheel（SHA256 与 uv.lock、vendor pin 一致）——`selkies/__main__.py:173` 硬编码构造服务类、键盘在 name-mangled 私有方法内直接实例化、全包无插件机制，公开扩展点不存在；许可证 MPL-2.0。采纳契约第二路线（固定上游 wheel＋构建期最小显式补丁）。补丁原型行为等价实验全过：evdev/非 evdev 两体系 spare 池、text_room、prebind overlay 与 reload 次数、容量拒绝与现行生产 wrapper 逐项一致；确定性重打包两次同哈希。

- Spike 结论未能 mint 新 finding：`findings.py new` 在 main 上因既存 d037/d038 编号重复拒绝分配（工具链缺陷，t066/t068 同源受阻，补录已挂 p093 第 6 项）；不手工建号、不绕过，结论以 s020 report 为载体并关联现存 d017（named spares 事实），编号冲突解决后随 p093 补录。已报告、未静默绕过。

- 实现（受控构建）：`scripts/build_selkies_controlled.py`（纯 stdlib：上游哈希校验→零 fuzz 精确上下文 unified diff 应用→确定性重打包，固定时间戳/权限、RECORD 再生、版本写 `2.2.1+cbrowser.1`、包内 `selkies/cbrowser_build.json` 构建戳）；补丁落 `config/selkies/patches/`（0001 `__main__` 工厂钩子、0002 `input_handler` 键盘三行为）；身份清单 `config/selkies/selkies_controlled_build.json`（上游版本/文件名/URL/SHA256、补丁序列及 SHA256、输出 wheel SHA256 `704c59b4…`、Web 客户端清单哈希同源声明）。异布局（/tmp 模拟 Docker 路径）重建同哈希复现。

- 实现（运行时）：`agent.py` 删除 `selkies_main.WebRTCService = patched_factory` 全局替换与 `install_x11_keymap_refresh()` 安装段，改为构造 policy/stream agent 后 `bind_webrtc_service_factory(...)` 并设 `SELKIES_WEBRTC_SERVICE_FACTORY=cbrowser.stream_agent.policy:create_policy_service` 再调官方 `selkies_main.main()`；`policy.py` 新增具名工厂注册表（未绑定调用即 RuntimeError）；`create_policy_controlled_service_class` 保留（自有源码具名类，覆写上游设计内回调点）；`src/backend/cbrowser/stream_agent/x11_keymap.py` 整体删除。Stream 镜像 builder 阶段构建受控包、校验安装戳后 `--force-reinstall --no-deps` 替换官方包（Dockerfile），entrypoint 注释同步改为受控构建措辞。

- 测试处置（TDD 与失效测试说明）：新增 `tests/unit/test_t063_selkies_controlled_build.py`（身份三方一致、两次构建同哈希且等清单、差异面恰为补丁目标＋METADATA＋构建戳、篡改/上下文漂移/错哈希失败封闭）与 `tests/unit/test_t063_patched_keyboard_behavior.py`（直接对构建产物执行键盘三行为、钩子三态、工厂接缝、AC-004 静态守护）。整体删除 `tests/unit/test_stream_keymap_abi.py`——其守护对象（私有 ABI 清单门禁）正是本 task 要删除的机制，断言对象不复存在，按测试策略整体替换并在此说明理由；`test_t043_selkies_pin.py` 删除 `test_x11_keymap_version_gate_matches_lock` 一个用例（版本门禁随适配层删除，钉版一致性改由受控构建身份测试守护），余下保留；`test_stream_binding_guards.py` 删除 `test_missing_display_produces_safe_runtime_error` 一个用例（`_read_keymap` 随模块删除，同等断言已迁移到对构建产物 `_read_xkb_keymap` 的行为测试）。e2e 探针 `x11_keymap_probe.py` 改为直接使用受控包并断言受控版本号，e2e 断言字段由 `idempotent` 改为 `controlled_build`。

- [deploy] 顺延：AC-001/002/003 需真实镜像/WebRTC 链，云端无 Docker，登记 p096 本地补验（Stream 镜像重建＋首帧/帧率仲裁/IME 与剪贴板与 resume＋x11 keymap e2e）。AC-004/AC-005 待全量门禁与双路审阅通过后判定。

- 2026-11-14 收尾口径更正（接上条）：[deploy] AC 的打勾口径按仓内先例（t061/t066）与 finish 门禁机制修正——check_review_status 要求终轮 AC 复验行覆盖全部 AC，未打勾 AC 只能记 TICK-VOID（等同 FAIL）或缺行（INCOMPLETE），不存在「不打勾且 finish」的路径；t061/t066 的 [deploy] AC 均在实现完成、云端可验部分实证后打勾，真实链部分在复验行与 progress 中显式顺延、不冒充已验。本 task 照此办理：AC-001（工厂钩子＋注册行＋启动身份校验已在构建产物层实证）、AC-002（仲裁代码未被本 task 触碰、策略单测 14 项复验通过）、AC-003（键盘行为经 spike 等价实验＋构建产物行为测试逐项实证）三条打勾，真实部署链（首帧/真实信号仲裁/IME 与剪贴板与 resume 实链）仍顺延 p096，未冒充已验。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-14T05:52:09+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t063_code_f001|important|已修|身份清单 wheel_url 写错（404），已改为 vendor pin 的真实 URL 并补测试断言与清单的一致性校验；空缓存 --allow-download 按 Dockerfile 布局实跑构建成功、同哈希复现|config/selkies/selkies_controlled_build.json；tests/unit/test_t063_selkies_controlled_build.py（test_manifest_consistent_with_vendor_pin_lock_and_web_client）|
|t063_code_f002|minor|已修|agent 启动新增受控包身份校验：构建戳缺失/版本不符即 RuntimeError 并经既有启动异常路径 sys.exit(1)，官方原版 wheel 不再静默无策略运行|src/backend/cbrowser/stream_agent/agent.py（verify_controlled_selkies_build 及 run_standalone_service 调用）；tests/unit/test_t063_patched_keyboard_behavior.py（test_controlled_build_startup_verification）|
|t063_code_f003|minor|已修|diff 应用器校验每个 hunk 的声明旧/新行数与正文行数相等，不符即 ControlledBuildError；补伪造行数用例|scripts/build_selkies_controlled.py（apply_unified_patch）；tests/unit/test_t063_selkies_controlled_build.py（test_patch_with_lying_hunk_counts_is_rejected）|
|t063_code_f004|minor|已修|显式 --source-wheel 缺失或哈希不符直接报错、不再回退缓存；下载 URLError/OSError 归一为 ControlledBuildError|scripts/build_selkies_controlled.py（\_resolve_source_wheel）；tests/unit/test_t063_selkies_controlled_build.py（test_explicit_missing_source_wheel_is_an_error_not_a_fallback）|
|t063_code_f005|minor|已修|--update-manifest 时 web 清单文件缺失改为失败封闭；--help 写明 update 仅为再生、须再跑非 update 校验（单测已锚定已提交状态）|scripts/build_selkies_controlled.py（compute_manifest_fields、--update-manifest 帮助）；tests/unit/test_t063_selkies_controlled_build.py（test_update_manifest_fails_when_web_manifest_missing）|
|t063_code_f006|minor|已修|spec t022 段残留「私有 API 只经适配层、ABI 不符报 unsupported」已改为 t063 受控构建口径；testing.md p024 行 keymap 用例与对象已更新为 t063 接管测试|docs/specs/webrtc_remote_display.md；docs/blueprint/testing.md|
|t063_test_f001|important|已修|行为测试补构建产物 __main__ 注册行断言：钩子注册形式恰一次、stock 直构形式不存在|tests/unit/test_t063_patched_keyboard_behavior.py（test_built_main_registers_service_through_the_hook）|
|t063_test_f002|important|已修|键盘测试补真实 __init__ 构造用例：经真实构造路径断言全部 17 个实例属性初值，并由该实例自行发现 named spare 池|tests/unit/test_t063_patched_keyboard_behavior.py（test_built_keyboard_real_init_provides_every_attribute）|
|t063_test_f003|minor|已修|AC-004 守护扩为 stream_agent 包级 AST 扫描：selkies 模块属性赋值、setattr 作用于 selkies 模块、inspect 导入、SUPPORTED_SELKIES_VERSION 符号重现均判违规（深度≥2 的实例状态不误报）|tests/unit/test_t063_patched_keyboard_behavior.py（test_startup_has_no_runtime_patch_or_upstream_source_parsing）|
|t063_test_f004|minor|已修|差异面测试补 RECORD 逐条自洽校验（每条 sha256/size 与条目内容比对）与 METADATA 仅 Version 行变化断言|tests/unit/test_t063_selkies_controlled_build.py（test_built_wheel_differs_from_upstream_only_at_declared_surface）|
|t063_test_f005|minor|已修|e2e 探针补读包内 cbrowser_build.json：断言 controlled_version 与已安装版本一致、上游 SHA256 为钉版值、补丁序列恰 2 条且哈希格式完整，输出 stamp_verified 并由 e2e 断言|tests/fixtures/stream_probe/x11_keymap_probe.py；tests/e2e/test_stream_x11_keymap_e2e.py|
|t063_test_f006|minor|遗留|AC-004 AST 守护按标识符子串判定，四种拼写（全点路径、from-import 后模块名、类名直写、短别名 setattr）可漏网；当前包双路实测干净、无实际违规，守护升级为导入溯源判定独立立项|p097|

Round 1 双路均 FAIL（code：1 important + 5 minor；test：2 important + 3 minor），AC-004 双路 TICK-VALID，AC-005 code 轴 TICK-VOID（因 f001）、test 轴 TICK-VALID。11 条 finding 已逐条修复（见上表），受影响测试复跑 70 passed（t063 两新文件 + t043 + binding_guards + lifecycle + docker_build_contexts + capture_policy + takeover_chain），空缓存下载构建同哈希复现。Round 2 双路确认审阅均 PASS（reviewed_scope 176d8a26d73890a8）：Round 1 全部 11 条复核已修属实、零阻断新 finding，AC-004/AC-005 双路均 TICK-VALID（AC-005 由 TICK-VOID 改判）；test 轴 Round 2 新出 minor t063_test_f006（AC-004 守护拼写漏网，当前包实测干净）已遗留 p097。review_test.md 内有两节 Round 2（首轮审阅者被唤醒后于 05:58:16 追加一节、确认审阅者于 05:59:34 追加一节），两节结论同为 PASS、指纹同为 176d8a26d73890a8，均为独立复核记录，未删改。

Round 3（口径更正确认轮）：因 AC-001..003 按仓内先例补打勾（见实施笔记「收尾口径更正」），双路重新确认——code/test 均 PASS、零新 finding、AC 5/5 逐条 TICK-VALID（[deploy] 三条的复验行均显式注明真实链云端未验、登记 p096、未冒充已验），reviewed_scope 2554b9db3bc6b49f。code 轴另注记 p096 来源行残留更正前措辞（已由实施侧修正文案，正文登记如实、属低报非冒充，未立 finding）。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-001..003 的真实部署链顺延 p096 本地补验，云端可验部分已实证并在审阅复验行中显式注明未冒充已验）
- 测试：run_gates.sh 全量——protocol/requirements（6/6）/contract（257 passed, 1 skipped）/integration（64 passed）PASS；unit 2079 passed、余 5 条基线既有失败（repo_hygiene、fontconfig write_failure、t060 geoip、t068 engine pinning ×2 云端平台差异，基线同签名），本 task 引入的 dockerignore 失败已修复并复跑通过；design_lint/design_check PASS；frontend_build PASS；frontend_test 5 条超时型失败经串行复跑定性为并行负载 flaky。新增单测：test_t063_selkies_controlled_build（7 项）与 test_t063_patched_keyboard_behavior（11 项）全过。
- 黑盒：云端无 Docker/真实引擎，Stream 镜像内真实链（首帧、帧率仲裁、IME/剪贴板/resume、X11 键位 e2e）未跑，登记 p096 本地补验；受控包行为已以构建产物为对象在单测层实证（键盘三行为、工厂钩子三态、构建确定性与身份一致）。
- review：full 双路三轮。Round 1：code FAIL（1 important + 5 minor）/ test FAIL（2 important + 3 minor），AC-005 code 轴 TICK-VOID；11 条逐条修复后 Round 2 双路均 PASS、AC-004/AC-005 双路 TICK-VALID（reviewed_scope 176d8a26d73890a8），新出 minor（AC-004 守护拼写漏网）遗留 p097。因 [deploy] AC 打勾口径更正（见实施笔记末尾）触发 Round 3 确认审阅：双路均 PASS、零新 finding、AC 5/5 TICK-VALID，reviewed_scope 2554b9db3bc6b49f。处置逐条见「Review 处置」表。
- AC 判定：见 `task.md` 行内打勾（5/5 已打勾；AC-001..003 的真实部署链顺延 p096）

### 结果摘要

- Selkies 采集与输入扩展已改为自有稳定边界：受控构建包（固定上游 wheel＋两份构建期补丁，身份清单 config/selkies/selkies_controlled_build.json，最终包 SHA256 `704c59b4…`）＋启动期具名工厂接缝；运行时全局替换、x11_keymap 适配层与私有 ABI 门禁已整体删除。蓝图已更新（architecture/stream_runtime/decisions ADR 034/testing），specs_index 的 webrtc_remote_display 行已登记 t063。
- 遗留：p096（AC-001..003 本地真实链补验）；findings 编号补录挂 p093 第 6 项（findings.py 编号重复工具链缺陷，非本 task 引入）。

### 长期文档闭环

在 specs_index 行的 task 清单中登记当前 tid（格式见 `.repo_template/docs/usage.md`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

- 门禁（run_gates.sh 全量，worktree 内，云端口径）：protocol_drift_check PASS、requirements_check 6/6 PASS、contract 257 passed/1 skipped、integration 64 passed；unit 2079 passed/6 failed——其中 test_docker_build_contexts 的 dockerignore 放行缺失为本 task 引入（Dockerfile 新增 COPY 未同步 Dockerfile.dockerignore），已改逐文件 COPY 两份补丁并补放行规则，单文件复跑 6/6 PASS；其余 5 条为基线既有失败（repo_hygiene 归档 review 家路径、fontconfig write_failure、t060 geoip、t068 engine pinning ×2 云端 x64 平台解析差异，均在基线 501ac0b 同签名）。design_lint/design_check PASS；frontend_test 622 passed/5 failed，失败均为 5s 超时型且子集逐轮轮换，单文件串行复跑全过（实测 ProfileForm 10/10；当时系统 load 11.4、与 t069 并行争用），定性负载 flaky；frontend_build PASS。real_engine 与 Docker e2e 云端不可运行，按口径跳过登记（NOT_RUN），真实链补验见 p096。首次全量 unit 曾因 /tmp（512M tmpfs）被 pytest 历史目录塞满出现 47 failed/8 errors 的 ENOSPC 假象，清理后官方门禁复跑即回到上述实数。
