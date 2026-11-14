# Task review t065（reviewer_focus: 测试）

- task：`t065_proxy_credential_isolation`
- spec：`docs/tasks/t065_proxy_credential_isolation/task.md`
- diff_anchor：`a4726b33bbfa3e2262a7b5a450271f2c6fdeebe4`
- target：`git -C '<home>/workspace/CBrowser_t065' diff a4726b33bbfa3e2262a7b5a450271f2c6fdeebe4`
- round：5
- reviewed_at：2026-11-14T11:19:54+08:00

reviewed_scope: 4dd19121e8e93b53

## Findings

### t065_test_f001 - [deploy] AC-001～004 已打勾，但真实拓扑验证未做，单测用 fake 上游/mock Docker 冒充覆盖

- 严重度：important
- 锚点：AC-001、AC-002、AC-003、AC-004
- 位置：`docs/tasks/t065_proxy_credential_isolation/task.md`（AC-001～004 均 `- [x]`）；`docs/pending/todo/p098_t065_local_deploy_verification.md`（处理：未开）
- 问题：task.md 的可测试性声明写明 AC-001～004“需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代”。本次交付对这四条的验证只有：(1) 进程内 fake 上游（`tests/unit/test_t065_proxy_forwarder.py` 的 FakeHttpProxy/FakeSocks5/FakeOrigin，loopback socket）；(2) mock 掉 Docker client 的挂载断言（`tests/unit/test_t065_proxy_forwarder_mounts.py`）。真实 Docker/Chrome/引擎拓扑验收被明确顺延到 p098，而 p098 状态仍是“未开”，即四条 [deploy] AC 在本轮没有任何真实拓扑证据，却已全部打勾。按测试策略“先在隔离真实 Docker/引擎验证凭据全路径不可读”，单测只能证明 volume_spec/forwarder 函数的映射关系，不能证明 Browser 容器在真实部署里读不到凭据、真实引擎经转发器认证成功、故障时不回退直连。
- 建议：撤回 AC-001～004 的打勾；或在 Mac 真实部署拓扑下执行 p098 的四项验收并把实测证据（容器内 argv/挂载/日志检查、三协议真实出站、故障封闭、基线对比）写入 p098/收尾报告后重新打勾。本轮最小修复是先撤勾，不以单测绿冒充部署验收。

### t065_test_f002 - 未知契约清单仍含 UNVERIFIED-SPIKE，实施前门禁未闭合

- 严重度：important
- 锚点：spec 上下文区「未知契约清单」
- 位置：`docs/tasks/t065_proxy_credential_isolation/task.md:71`
- 问题：该行仍为“- 外置认证拓扑、上游协议/DNS、首包和 407 基线：UNVERIFIED-SPIKE，实际引擎与本地受控代理验证……”。审阅 prompt 明确规定：进入 review 前未知契约清单应已无 UNVERIFIED-BLOCKING/UNVERIFIED-SPIKE/裸 UNVERIFIED，仍有任一标记说明实施前门禁被绕过，按 blocking finding 处理。spike s021 的 report（`docs/spikes/s021_proxy_auth_forwarder_topology/report.md:57-58`）自己也写明首包延迟与 407 往返的基线对比“云端无 Docker，按口径顺延 pending（本地补验）”，即该 SPIKE 并未在交付内闭合，task.md 也未改写为结论和验证方式。
- 建议：完成 s021 承诺的实际引擎与本地受控代理验证（与 f001 的 p098 同一次本地验收可合并），把 task.md 该行改写为结论＋验证方式；未验证前不得视为契约已核实。

### t065_test_f003 - AC-004 无基线对比：只有一个 250ms 绝对阈值 loopback smoke，无成功率/407 往返报告

- 严重度：important
- 锚点：AC-004
- 位置：`tests/unit/test_t065_proxy_forwarder.py:629`（`test_first_byte_overhead_is_small`，断言在约 650 行 `assert samples[len(samples) // 2] < 0.25`）
- 问题：AC-004 要求“相同拓扑/目标/样本下认证成功率不低于基线；报告首包延迟、407 往返与可观测协议差异，默认不接受超出测量噪声的性能退化”。交付中唯一与性能相关的测试是 loopback 上 5 个样本的中位数 < 0.25 秒：没有直连/无转发器的基线对照，没有认证成功率统计，没有 407 往返计时，没有任何报告输出。250ms 是凭空给的绝对阈值，在 loopback 上必然通过，测不出转发器相对基线的退化——AC-004 的核心条款（与基线比、不超测量噪声）完全无测试。测试策略也写明“认证延迟用同机重复样本报告噪声，不凭空要求绝对零开销”，该测试恰恰反其道而行之：凭空绝对阈值、无噪声报告。
- 建议：补一个基线对比方法（同机同目标：直连/旧内联路径 vs 经转发器，重复样本，报告首包延迟分布、407 往返、认证成功率），或把 AC-004 的验证明确并入 p098 本地验收并撤回打勾；删除或改写该 smoke 测试，使其不再以绝对阈值冒充 AC-004 证据。

### t065_test_f004 - AC-003 第三容器生命周期无测试：只重建转发器的 reconcile、孤儿清理、stop/重启、未配代理模式均未覆盖

- 严重度：important
- 锚点：AC-003
- 位置：`src/backend/cbrowser/supervisor/core.py:921`（`_replace_proxy_forwarder_only`）、`src/backend/cbrowser/supervisor/core.py:1450`（reconcile 中调用点）；测试侧全仓无引用
- 问题：AC-003 要求“创建失败、stop、重启与孤儿恢复不留无归属代理组件，未配代理模式保持原行为”，测试策略要求“故障注入覆盖第三容器全部生命周期”。但全仓 grep `_replace_proxy_forwarder_only` / `proxy_forwarder_missing` / `proxy_forwarder_replacement` 只有 core.py 生产代码命中，零测试引用。本轮新增的 29 个测试只覆盖创建（`test_create_proxy_forwarder_wires_secret_only`）、扫描计数（`test_scan_counts_proxy_forwarder_role`）、按名清理（`test_cleanup_by_name_removes_proxy_forwarder`）和 forwarder 协议层故障封闭；以下生产分支无任何测试：转发器缺失时 reconcile 只重建转发器（300 秒/3 次预算、预算耗尽报错）、创建失败是否留孤儿转发器、stop/teardown 是否删干净转发器、重启后是否恢复、未配代理的 Profile 是否仍只有 Browser+Stream 且不创建转发器。新增的生产逻辑（core.py 约 189 行改动）中生命周期分支基本处于无测试状态。
- 建议：补单测（fake adapter/core 级）：转发器缺失触发 `_replace_proxy_forwarder_only` 且 Browser 不动、预算耗尽报错、创建失败无残留容器、teardown 删转发器、未配代理不创建转发器；或把这部分并入 p098 本地验收并撤回 AC-003 打勾。

### t065_test_f005 - 新挂载测试 mock 掉被测类自己的内部方法，且该 mock 在本 task 已掩盖过一个真实 bug

- 严重度：important
- 锚点：测试可信（mock 边界）
- 位置：`tests/unit/test_t065_proxy_forwarder_mounts.py:136-139`（`test_browser_container_mounts_no_credentials` 内 `_prepare_policy_gate` / `_resolved_endpoint` / `_install_network_policy` 均 MagicMock）；同文件约 190-193 行（`test_create_proxy_forwarder_wires_secret_only` 同样 mock 这三个内部方法）
- 问题：`_prepare_policy_gate`、`_resolved_endpoint`、`_install_network_policy` 都是 DockerAdapter 自己的内部方法，不是系统边界（外部 API/DB/文件系统/时钟）。mock 掉它们后，测试只断言传给 mock 的参数字典，真实的策略门生成、端点解析、策略安装是否执行、签名是否匹配一概测不到。progress.md 自己承认：门禁首跑抓出 `create_proxy_forwarder` 漏传 `_prepare_policy_gate` 的 `role` 必填参数，“测试 mock 了该方法故未暴露；复查时逐项核对未 mock 调用的签名时发现”——即这个 mock 在本 task 内已经掩盖过一个“运行时 TypeError、转发器建不出”的真实 bug，生产代码修了，但测试仍原样 mock 该方法，同类签名漂移下次仍会被 mock 吞掉。`_wait_for_proxy_forwarder_ready` 被 mock 也有同类盲区（readiness 从未被真实执行）。
- 建议：对 `create_proxy_forwarder` / `start_browser_container` 的测试，至少保留一条不 mock `_prepare_policy_gate` 与 `_install_network_policy` 的路径（用 tmp_path 真实 gate 目录与可断言的策略渲染结果验证），或加一条签名/调用契约测试，显式断言 `_prepare_policy_gate` 被以 `role="proxy-forwarder"` 调用；不要只靠 mock 参数断言冒充接线正确。

## 结论

- 改测方向复核：删除的旧测试均为整体删除并附 NOTE 说明理由（t035 的 `build_proxy_server_arg` 4 测试＋`test_matching_revision_returns_proxy_arg`、`test_supervisor_written_credentials_are_accepted_by_runner`、Browser 挂载凭据与 start_profile 端到端 2 测试；t052 的 3 个 Browser-start loopback 测试；t027 的 5 镜像部署测试），且均有等价或更强的替换测试（新文件 `test_t065_proxy_forwarder_mounts.py` 的凭据挂载/Runner 端点解析/forwarder loopback 三则/start_profile 端到端，`test_t065_proxy_forwarder.py` 的特殊字符 Base64 往返与配置校验，t027 的 6 镜像替换测试重断言整套契约）。未发现“就地把旧测试预期改成新实现输出”的迁就实现改测；a24 的改动只是 fixture 补 `proxy_forwarder_runtime` 目录，断言本身未变。本轮改测方向复核：无迁就实现。
- 本轮新发现：5 条（t065_test_f001～f005，全部 important，无 critical、无 minor）
- 未进表的提示：
  - 危险模式扫描已逐条调查，未进表项：`tests/unit/test_t065_proxy_forwarder.py` 中的 `# type: ignore`（7 处）只落在 `server.sockets[0].getsockname()[1]` 等 socket 类型收窄行与测试辅助函数签名上，未压制任何断言或生产错误，已核实放行；`test_http_upstream_ipv6_and_special_chars`（约 556 行）在 IPv6 loopback 不可用时 `pytest.skip`——本机实测该测试实际跑过且通过（169 项 0 skipped），跳过只在无 IPv6 的环境触发且会显式报 skipped，但须注意在无 IPv6 的机器上 AC-002 的 IPv6 证据会静默消失，建议 p098 本地验收中显式确认 IPv6 loopback 可用而非依赖跳过。
  - 删除测试的替换关系已逐项核对：特殊字符百分号编码旧测试由 forwarder 的 `us@er` / `p@ss:w/rd?` Base64 往返测试替代（内联凭据 URL 已删除，百分号编码不再适用）；无效凭据参数化旧测试由 `test_config_validation_fails_closed` 替代（覆盖 ftp/空 host/端口越界/单边密码等 8 类）；t052 loopback 三则由 forwarder 三则替代。以上替换成立，不另出 finding。
  - 范围外观察：新交付文件（`src/backend/cbrowser/proxy_forwarder/`、`tests/unit/test_t065_*.py`、`docs/spikes/s021_*/report.md`、p098）目前仍是未跟踪状态（`git status` 为 `??`），未执行 `git add -N`，因此不在 `git diff a4726b33...` 的输出里；本审阅是直接读文件并实跑测试完成的，范围未因此缩小，但请实施方按 prompt 要求对新交付文件执行 `git add -N`，以便指纹校验与后续轮次复核以 diff 为准。
- 总体判断：AC-001～004 的打勾无真实拓扑证据支撑且未知契约仍标 UNVERIFIED-SPIKE，AC-004 与 AC-003 生命周期另有具体覆盖缺口，测试 mock 还存在已证实掩盖过 bug 的盲区；FAIL。
- 系统性 follow-up：无（f001～f005 均可在本 task 内修复：撤勾＋补 p098 本地验收、补生命周期与基线对比测试、去 mock 化接线测试；无跨 task 基础设施缺口需新立 tid）。

### AC 复验方式

- AC-001：TICK-VOID，trust_prior。打勾无真实 Docker/Chrome 拓扑证据，p098 未开，单测只验 volume 映射且 mock 了 Docker，可测试性声明明言 mock 不可替代。
- AC-002：TICK-VOID，trust_prior。打勾无真实引擎/上游证据，p098 未开；进程内 fake 上游与 loopback 测试不能替代真实三协议上游验收。
- AC-003：TICK-VOID，trust_prior。打勾无部署证据，p098 未开；且 reconcile/孤儿/stop/重启/未配代理模式在测试中零覆盖。
- AC-004：TICK-VOID，trust_prior。打勾无基线对比证据，p098 未开；唯一性能测试是无基线的 250ms 绝对阈值 loopback smoke。
- AC-005：TICK-VALID，re_verified。Selkies pin/asset probe/wheel cache/controlled build/vendor 安全测试未被 diff 改动，我用 gate venv 重跑含这批文件在内的 169 项全部通过（29 项 t065 新测试亦在内）。

coverage = 1 / 5

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 2 (2026-11-14T09:39:37+08:00)

- task：`t065_proxy_credential_isolation`
- diff_anchor：`a4726b33bbfa3e2262a7b5a450271f2c6fdeebe4`
- round：2

reviewed_scope: 96b7ac3770b9beb7

## Findings

本轮为独立重验轮。Round 1 落盘后实施方无任何改动：本轮复算指纹与 Round 1 一致（`96b7ac3770b9beb7`）；除 `.scratch/` 外无文件在 09:24:57 后被修改；progress.md 的 Review 处置表仍为空模板，无任何 finding 被标记已修/遗留/撤回；task.md 五条 AC 仍全勾。以下逐条独立复核 Round 1 的 5 条 finding（均以本轮直读、grep 与独立重跑为据，非转述），全部确认成立；另新增 2 条 minor。

### t065_test_f001 - [deploy] AC-001～004 已打勾，但真实拓扑验证未做，单测用 fake 上游/mock Docker 冒充覆盖

- 严重度：important
- 锚点：AC-001、AC-002、AC-003、AC-004
- 位置：`docs/tasks/t065_proxy_credential_isolation/task.md`（AC-001～004 均 `- [x]`）；`docs/pending/todo/p098_t065_local_deploy_verification.md`（处理：未开）
- 问题（本轮独立确认）：task.md 可测试性声明写明 AC-001～004“需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 另代”。本轮直读 p098 全文：四项子句齐备、明写“真实链未冒充已验”，处理状态确为“未开”。交付的验证只有两类：(1) 进程内 fake 上游（`tests/unit/test_t065_proxy_forwarder.py` 的 FakeHttpProxy/FakeSocks5/FakeOrigin，12 个测试全在 loopback socket 上）；(2) mock 掉 Docker client 与 adapter 内部方法的挂载断言（`tests/unit/test_t065_proxy_forwarder_mounts.py`）。所谓“start_profile 端到端”测试（`test_start_profile_with_proxy_writes_secret_and_endpoint`，约 347 行起）同样用 MagicMock 容器与 fake `create_forwarder`，只验了“转发器先于 Browser 创建”的顺序与文件落点，Docker 层全被 mock——名为端到端，实为 core 级编排单测，不能证明真实部署里 Browser 读不到凭据、真实引擎经转发器认证成功、故障时不回退直连。Round 1 的定性成立。
- 建议：与 Round 1 同：撤回 AC-001～004 的打勾；或在 Mac 真实部署拓扑下执行 p098 四项验收并把实测证据写入 p098/收尾报告后重新打勾。

### t065_test_f002 - 未知契约清单仍含 UNVERIFIED-SPIKE，实施前门禁未闭合

- 严重度：important
- 锚点：spec 上下文区「未知契约清单」
- 位置：`docs/tasks/t065_proxy_credential_isolation/task.md:71`
- 问题（本轮独立确认）：本轮直读 task.md:71，原文仍为“- 外置认证拓扑、上游协议/DNS、首包和 407 基线：UNVERIFIED-SPIKE，实际引擎与本地受控代理验证……”，未改写为结论和验证方式。s021 report 第 57–58 行自述首包延迟与 407 往返的基线对比“云端无 Docker，按口径顺延 pending（本地补验）”，即该 SPIKE 未在交付内闭合。Round 1 的定性成立。
- 建议：与 Round 1 同：完成 s021 承诺的实际引擎与本地受控代理验证（可与 f001 的 p098 同一次本地验收合并），把 task.md 该行改写为结论＋验证方式；未验证前不得视为契约已核实。

### t065_test_f003 - AC-004 无基线对比：只有一个 250ms 绝对阈值 loopback smoke，无成功率/407 往返报告

- 严重度：important
- 锚点：AC-004
- 位置：`tests/unit/test_t065_proxy_forwarder.py:629`（`test_first_byte_overhead_is_small`）
- 问题（本轮独立确认）：本轮直读该测试全文（约 629–655 行）：5 个 loopback 样本取中位数断言 `< 0.25`，无直连/无转发器基线对照、无认证成功率统计、无 407 往返计时、无任何报告输出。测试 docstring 自称“AC-004 methodology smoke”，但 AC-004 的核心条款是“相同拓扑/目标/样本下认证成功率不低于基线、报告首包延迟与 407 往返、不接受超出测量噪声的退化”，该测试一条都不覆盖；250ms 绝对阈值在 loopback 上必然通过，测不出相对退化。测试策略“认证延迟用同机重复样本报告噪声，不凭空要求绝对零开销”亦被违反。Round 1 的定性成立。
- 建议：与 Round 1 同：补基线对比方法（同机同目标直连 vs 经转发器，重复样本，报告首包延迟分布、407 往返、认证成功率），或把 AC-004 验证并入 p098 本地验收并撤回打勾；删除或改写该 smoke 测试，使其不再以绝对阈值冒充 AC-004 证据。

### t065_test_f004 - AC-003 第三容器生命周期无测试：只重建转发器的 reconcile、孤儿清理、stop/重启、未配代理模式均未覆盖

- 严重度：important
- 锚点：AC-003
- 位置：`src/backend/cbrowser/supervisor/core.py:921`（`_replace_proxy_forwarder_only`）、`core.py:1450`（reconcile 调用点）；测试侧全仓无引用
- 问题（本轮独立确认）：本轮全仓 grep `_replace_proxy_forwarder_only` / `proxy_forwarder_missing` / `proxy_forwarder_replacement`：命中仅在 `core.py`（921 行定义、938/961 行错误文案、1446 行预算耗尽 `proxy_forwarder_missing_budget_exhausted`、1450 行调用点），测试零引用。本轮新增的 29 个 t065 测试只覆盖创建接线、扫描计数、按名清理与 forwarder 协议层故障封闭；以下生产分支无任何测试：转发器缺失时 reconcile 只重建转发器（300 秒/3 次预算、预算耗尽报错）、创建失败是否留孤儿转发器、stop/teardown 是否删干净转发器、重启后是否恢复、未配代理的 Profile 是否仍只有 Browser+Stream 且不创建转发器。Round 1 的定性成立。
- 建议：与 Round 1 同：补单测（fake adapter/core 级）：转发器缺失触发 `_replace_proxy_forwarder_only` 且 Browser 不动、预算耗尽报错、创建失败无残留容器、teardown 删转发器、未配代理不创建转发器；或把这部分并入 p098 本地验收并撤回 AC-003 打勾。

### t065_test_f005 - 新挂载测试 mock 掉被测类自己的内部方法，且该 mock 在本 task 已掩盖过一个真实 bug

- 严重度：important
- 锚点：测试可信（mock 边界）
- 位置：`tests/unit/test_t065_proxy_forwarder_mounts.py:139-142`（`test_browser_container_mounts_no_credentials` 内 `_prepare_policy_gate` / `_install_network_policy` / `_resolved_endpoint` 均 MagicMock）、同文件 188-191、544-547、564-567、593-594 行（`test_create_proxy_forwarder_wires_secret_only`、forwarder loopback 三则同样 mock）
- 问题（本轮独立确认）：`_prepare_policy_gate`、`_resolved_endpoint`、`_install_network_policy`、`_wait_for_proxy_forwarder_ready` 都是 DockerAdapter 自身的内部方法，不是系统边界；mock 后测试只断言传给 mock 的参数字典，真实的策略门生成、端点解析、策略安装与 readiness 是否执行、签名是否匹配一概测不到。本轮核实：全仓只有 `tests/unit/test_t051_docker_error_detail.py:252` 真实调用过 `_prepare_policy_gate`（且是 `"browser"` 角色），没有任何测试真实执行 `"proxy-forwarder"` 角色的 gate 准备；`create_proxy_forwarder` 内对 `_prepare_policy_gate` 的调用（`docker_adapter.py:2292-2294`，确已传 `"proxy-forwarder"`）与 `_install_network_policy` 的调用（`docker_adapter.py:2348` 起，policy dict 含 `"role": "proxy-forwarder"`，2351 行）均无任何测试断言其被调用或传参正确。progress.md 自述的教训属实：门禁首跑抓出 `create_proxy_forwarder` 漏传 `role` 必填参数，“测试 mock 了该方法故未暴露”——生产代码已修（2292 行已传 role），但测试仍原样 mock，同类签名漂移下次仍会被 mock 吞掉。`_wait_for_proxy_forwarder_ready` 被 AsyncMock 同样导致 readiness 从未被真实执行。Round 1 的定性成立。
- 建议：与 Round 1 同：对 `create_proxy_forwarder` / `start_browser_container` 的测试，至少保留一条不 mock `_prepare_policy_gate` 与 `_install_network_policy` 的路径（用 tmp_path 真实 gate 目录与可断言的策略渲染结果验证），或加一条签名/调用契约测试，显式断言 `_prepare_policy_gate` 被以 `role="proxy-forwarder"` 调用；不要只靠 mock 参数断言冒充接线正确。

### t065_test_f006 - progress.md 把前端 5 条失败全记为 5000ms 超时，其中 1 条实为断言失败

- 严重度：minor
- 锚点：门禁证据叙述准确性
- 位置：`docs/tasks/t065_proxy_credential_isolation/progress.md` 收尾报告（“frontend_test 并行 628 passed / 5 failed，5 条全为 5000ms 超时”）；对照 `.scratch/frontend_tests.json`
- 问题：本轮直读 `frontend_tests.json`：5 条失败中 4 条确为 `Test timed out in 5000ms`，但第 5 条（`ProfileForm.t058.test.tsx` 的 “AC-001: a timezone change carries its linked locale change, nothing else”）是 `AssertionError: expected "vi.fn()" to be called 1 times, but got 2 times`——并行负载下的 mock 重复调用断言失败，不是超时。收尾报告“5 条全为 5000ms 超时”的说法与证据不符。实质影响有限：本轮单文件串行重跑 4 个文件 18/18 全部通过（含该断言失败用例），且 5 个失败文件均不在本 task diff 内（t065 未改任何前端代码），可定性为并行负载 flake；但证据叙述须与 junit/json 一致，不得把断言失败写成超时。
- 建议：把收尾报告该句订正为“4 条 5000ms 超时＋1 条并行负载下断言抖动（mock 重复调用），4 文件单跑 18/18 通过”；不阻断本轮之外的结论。

### t065_test_f007 - integration 证据缺补跑日志，tsv 记录的命令与实际两段补跑命令不一致

- 严重度：minor
- 锚点：门禁证据可追溯性
- 位置：`.scratch/gate_evidence_t065/suites.d/integration.tsv`；`.scratch/gate_evidence_t065/logs/integration.raw.log`；`.scratch/gate_evidence_t065/junit/integration.xml`
- 问题：progress.md 已披露 evidence 全量跑中途遇环境重启中断、integration 系手动补跑合并（并行 197 passed / 7 skipped、串行 4 passed）。本轮核实：junit 算术与该说法一致（208 例＝201 passed＋7 skipped，208 个 testcase 唯一、无重复、0 失败），补跑数字可信；但证据链有两处缺口：(1) `integration.raw.log` 只有 5 行、停在 70% 且无汇总行，是被中断的那次运行的残片，手动补跑的两段命令本身没有任何日志留在证据内，补跑命令无法从证据复核；(2) `integration.tsv` 记录的是 `run_gates.sh` 的展示命令（`pytest tests/integration -q -n 4`、exit 0），而非实际执行的两段命令（按 `run_gate_suite` 口径应为并行 `-m "not serial" -n 4` 与串行 `-m serial -n 0`），tsv 的命令列与实际执行不一致。鉴于 progress.md 已明示手动合并、junit 无重复且数字闭合，本项定 minor，不作伪造认定。
- 建议：把两次补跑的命令与汇总行补进证据（或在 integration.tsv 旁附注说明两段命令与合并方式），使 tsv 的命令列与实际执行一致。

## 结论

- 前轮 finding 复核：t065_test_f001～f005 全部经本轮直读、grep 与独立重跑逐条确认成立，无一可撤回。AC-001～004 的打勾仍无真实拓扑证据支撑、未知契约仍标 UNVERIFIED-SPIKE、AC-004 与 AC-003 生命周期仍有具体覆盖缺口、挂载测试的 mock 盲区仍在且生产侧的 role 修复未被任何测试锁定。
- 改测方向复核：无“迁就实现”的改测。本轮逐处核对 diff 中的既有测试修改：t035 的 5 个内联凭据测试与 `test_matching_revision_returns_proxy_arg`、`test_supervisor_written_credentials_are_accepted_by_runner`、Browser 挂载凭据与 start_profile 端到端测试均为整体删除并附 t065 NOTE（文件内 75/304/405 行）；t052 的 3 个 Browser-start loopback 测试整体删除并附 NOTE（280 行）；t027 的 5 镜像部署测试整体删除并由 `test_t065_deploy_success_builds_six_images_once_and_pins_proxy_forwarder`（387 行）整体替换、重断言 6 镜像全套契约，模块 docstring 已写明删除理由；a24 只是 fixture 元组补 `"proxy_forwarder_runtime"` 目录，断言本身未变；t062 只加 IMAGES 表一行。删除均有等价或更强的替换测试，不存在就地改预期。
- 危险模式扫描：对两个新增测试文件与全部测试 diff 逐条扫描——无恒真断言、无删/反转 expect、无注释掉的断言、无 `.skip`/`.only`/`pytest.mark.skip`（除 `test_http_upstream_ipv6_and_special_chars` 在 IPv6 loopback 不可用时显式 `pytest.skip`，本机实测该测试实际跑过且通过）、无 `# type: ignore` 压制断言（7 处均落在 socket 类型收窄与测试辅助签名上）、无阈值增大、无赋值替代真实交互。mock 边界除 f005 外合规：fake 上游（HTTP/SOCKS5/origin）是协议层系统边界的合理替身，问题只在 adapter 内部方法被 mock。
- 本轮新发现：2 条（t065_test_f006、t065_test_f007，全部 minor，无 critical、无 important）。
- 未进表的提示：
  - IPv6 证据：本轮 169 项合跑 0 skipped，`test_http_upstream_ipv6_and_special_chars` 在本机实际跑过且通过；跳过分支只在无 IPv6 的环境触发，p098 本地验收中仍须显式确认 Mac 的 IPv6 loopback 可用，而非依赖跳过。
  - `test_start_profile_with_proxy_writes_secret_and_endpoint` 名为端到端、实为 core 级编排单测（MagicMock 容器＋fake `create_forwarder`），已并入 f001 的论证，不另出 finding。
  - `_wait_for_proxy_forwarder_ready` 被 AsyncMock 导致 readiness 从未真实执行，已并入 f005，不另出 finding。
  - s021 的“12/12 本地桩验证通过”已核实：即 `tests/unit/test_t065_proxy_forwarder.py` 的 12 个测试函数（346/369/401/431/464/490/518/549/573/607/629/656 行），非凭空数字。
  - 引用逐项核对：本轮引用的文件、行号、套件名均已实测存在；Round 1 的引用中仅一处行号需微调——f005 的 mock 行实为 `test_t065_proxy_forwarder_mounts.py:139-142`（Round 1 写 136-139），其余引用（task.md:71、forwarder.py:629、core.py:921/1450、188-191 行等）逐项核对无误。
- 总体判断：5 条 important 未解决（f001～f005），另 2 条 minor（f006、f007）；FAIL。
- 系统性 follow-up：无（f001～f007 均可在本 task 内修复：撤勾＋补 p098 本地验收、补生命周期与基线对比测试、去 mock 化接线测试、订正两处证据叙述；无跨 task 基础设施缺口需新立 tid）。

## Round 2 Reviewer 独立重跑记录（证据）

- 落点仓库校验：以 workdir 为仓库目录执行不带 `-C` 的 `git rev-parse --show-toplevel`，输出精确等于 `<home>/workspace/CBrowser_t065`；当前分支 `t065_proxy_credential_isolation`；基线 `a4726b3`；Round 1 后实施方零改动（指纹复算 `96b7ac3770b9beb7` 与 Round 1 一致）。
- 后端第一批（主仓 gate venv，`PYTHONPATH=src/backend`，`CBROWSER_GATE_ENV_READY=1`，`--basetemp` 落仓内 `.scratch/tmp/r2unit`）：13 个文件合跑 169 passed（120 秒，0 skipped）：两个 t065 新测试文件、Selkies AC-005 五件（t043 pin、t044 asset probe、t045 wheel cache、t063 controlled build、vendor selkies security）、t035 proxy runtime、network policy、t027 release controller、a24 deploy network source、t052 supervisor probe、t062 image closure。
- contract 套件（同环境，`.repo_template/tests -q -m contract`）：257 passed、1 skipped（3.6 秒），与 progress.md 数字一致。
- 前端 4 文件单文件串行重跑（src/frontend 下 `./node_modules/.bin/vitest run <file>`）：ConfigTab.test.tsx 3 passed、ProfileCreateDialog.test.tsx 7 passed、ProfileForm.t058.test.tsx 5 passed（含 f006 的断言失败用例）、SettingsPage.test.tsx 3 passed，合计 18/18 通过。
- 门禁 junit 独立解析（`.scratch/gate_evidence_t065/junit/`）：contract 258 例 0 失败 1 跳过（＝257 passed）；unit 2211 例 5 失败 1 跳过（＝2205 passed），5 条失败签名与 progress.md 所列基线逐条一致（fontconfig write_failure、repo_hygiene 家路径、t060 geoip、t068 pinning 2 条），且 30 个 t065 用例 0 失败；integration 208 例 0 失败 7 跳过（＝201 passed），208 个 testcase 唯一、无重复；frontend JSON：633 例 628 passed / 5 failed（4 超时＋1 断言抖动，见 f006）。
- 未跑全量 unit 套件（约 11 分钟）与全量 frontend 套件、Docker 类验证（本机无 Docker）；全量门禁数字除上述 junit/JSON 解析外仍作 progress.md claim 引用。

### AC 复验方式

- AC-001：TICK-VOID，trust_prior。打勾无真实 Docker/Chrome 拓扑证据，p098 未开；进程内 fake 上游与 mock Docker 的挂载断言不能替代真实拓扑验收，可测试性声明明言 mock 不可替代。
- AC-002：TICK-VOID，trust_prior。打勾无真实引擎/上游证据，p098 未开；进程内 fake 上游（HTTP CONNECT、SOCKS5 远端 DNS、IPv6 与特殊字符）经本轮 169 项合跑通过，但只是协议层单测，不能替代真实三协议上游验收。
- AC-003：TICK-VOID，trust_prior。打勾无部署证据，p098 未开；且 reconcile 只重建转发器、孤儿清理、stop/重启、未配代理模式在测试中零覆盖（见 f004）。
- AC-004：TICK-VOID，trust_prior。打勾无基线对比证据，p098 未开；唯一性能测试是无基线的 250ms 绝对阈值 loopback smoke（见 f003）。
- AC-005：TICK-VALID，re_verified。Selkies pin/asset probe/wheel cache/controlled build/vendor 安全五件未被 diff 改动，本轮独立重跑 169 项合跑全部通过（含这批文件与 30 个 t065 用例）；篡改被拒的校验入口测试在其中。

coverage = 1 / 5

verdict: FAIL

## Round 3 (2026-11-14T10:46:00+08:00)

- task：`t065_proxy_credential_isolation`
- diff_anchor：`a4726b33bbfa3e2262a7b5a450271f2c6fdeebe4`
- round：3

reviewed_scope: c6aaa3c19097122d

本轮为确认轮。Round 2 落盘后实施方按父级 09:46 裁决修复并重新打勾：本轮复算指纹为 `c6aaa3c19097122d`（与 Round 1/2 的 `96b7ac3770b9beb7` 不同，实施方确有改动）。以下逐条独立复核 Round 1/2 的 7 条 test finding（均以本轮直读、grep 与独立重跑为据，非转述处置表）。

## Findings

本轮无新 finding。Round 1/2 的 7 条 test finding 复核结论如下（逐条见结论段）。

## 结论

- 前轮 finding 复核（逐条，证据为本轮直读与独立重跑）：
  - t065_test_f001：消除。消除依据不是新增真实拓扑证据，而是父级 09:46 裁决已改定 [deploy] 打勾口径（打勾不要求真实部署证据，要求实现完成＋云端可验部分实证＋真实链登记 p098＋复验行明写未冒充已验），本轮核实 progress.md 确已按该口径执行：收尾报告“验收与验证”写明“AC-001～004 为 [deploy]：云端可验部分已满足并按 t061/t066/t063/t069 先例打勾，真实 Docker/Chrome/引擎拓扑验收顺延 p098 本地补验，不冒充已验”；黑盒行写明“云端证据为本地桩协议测试（fake 上游）与容器接线测试（fake Docker 客户端、真实执行 adapter 内部方法），不是真实拓扑证据；AC-001～004 真实拓扑黑盒顺延 p098 本地执行，不冒充已验”；另有独立的“[deploy] AC 打勾口径”一节引述先例。p098 四项齐备、处理仍为“未开”，与“顺延、未冒充”口径一致，未见把 fake 上游/mock Docker 写成拓扑证据的表述。
  - t065_test_f002：消除。直读 task.md 未知契约清单：原 UNVERIFIED-SPIKE 行已改写为已核实（结论＋验证方式）——本地转发器终结未认证流量、三协议与失败封闭的结论，验证方式写明云端以本地桩协议测试（`tests/unit/test_t065_proxy_forwarder.py`）与容器接线测试（`tests/unit/test_t065_proxy_forwarder_mounts.py`）实证，真实拓扑端到端与首包/407 基线对比顺延 p098（基线对比明确归 p098 第 4 项）。全仓 grep：task.md 与 s021 report 除模板规范行（“未核实的外部契约标为 …”）外已无 UNVERIFIED 标记。s021 report 同步订正属实：https 上游先包 TLS、SOCKS5 IPv6 字面 ATYP 0x04、smoke“仅存活验证，报告样本中位数；基线对比顺延 p098 第 4 项”、未验证段明写真实部署顺延 pending。
  - t065_test_f003：消除。直读 `tests/unit/test_t065_proxy_forwarder.py:841`：测试已改名 `test_first_byte_smoke_reports_latency_samples`，docstring 明写“AC-004 liveness smoke — NOT a baseline comparison”“基线对比是 p098 第 4 项的真实部署测量，不属于本测试”；5 次 loopback 取回全断言 `body == ORIGIN_BODY`，样本经 `record_property` 报告中位数与全量列表，全文件 grep 已无 `0.25` 阈值。p098 第 4 项明确承接基线对比（相同拓扑/目标/样本、成功率、首包延迟、407 往返），并明写云端 smoke“不作基线对比证据”。本轮重跑该测试通过。
  - t065_test_f004：消除。新建 `tests/unit/test_t065_proxy_forwarder_lifecycle.py`（460 行）：10 个测试函数、参数化后共 11 个收集项——reconcile 缺失/退出转发器只重建转发器（2 参数，退出态即重启恢复）、预算耗尽（预置 3 次 300 秒内尝试，断言 `proxy_forwarder_missing_budget_exhausted` 且不再创建）、创建失败返回 False 且上报 `proxy_forwarder_replacement_failed:DockerSandboxError`、无端点文件（无代理模式）不创建转发器、readiness 缺失转发器报 `proxy_forwarder_not_running`／无端点时空洞通过／运行中通过、`_confirm_sandbox_gone` 计入转发器、创建失败（DNS 解析失败）由回收删孤儿（`container.remove` 断言一次 force=True）、teardown 删转发器。`_replace_proxy_forwarder_only` 全仓测试引用现为该文件 3 处（216/246/250 行相关断言），零测试状态已消除。本轮重跑 11/11 通过。
  - t065_test_f005：消除。直读 `tests/unit/test_t065_proxy_forwarder_mounts.py`：文件头 docstring 明确 mock 边界——只 fake Docker SDK 面（`client.containers.run/create/get`、`container.exec_run`），`_prepare_policy_gate`、`_resolved_endpoint`、`_install_network_policy`、`_wait_for_proxy_forwarder_ready` 均真实执行。核实三处：(1) `_spy_gate`（106-119 行）以 side_effect 包裹真实方法，真实执行并记录调用；`test_create_proxy_forwarder_wires_secret_only` 断言 `gate.assert_called_once_with("p1", "i1", "proxy-forwarder")` 且真实 gate 目录含 `startup_gate.py`、`ready.json` 的 role 为 `proxy-forwarder`——Round 1/2 指出的 role 缺失 bug 若重现，此断言必败；(2) `_policy_from_helper`（100-104 行）读 helper 容器 create 命令里的真实 JSON：策略断言 `policy["role"] == "proxy-forwarder"`、`allowed_tcp == [["203.0.113.7", 18081]]`、`allowed_udp == [["127.0.0.11", 53]]`、`input_tcp_ports == [18080]`；(3) `_resolved_endpoint` 真实执行：fake 容器的 `exec_run` 只回答 Docker-DNS 脚本（getaddrinfo），Browser 策略断言 `allowed_tcp == [["172.18.0.3", 18080]]`、loopback 映射断言 `allowed_tcp == [["192.168.65.254", 7890]]` 均为真实解析结果。剩余 stub（`create_browser_network`、`ensure_runtime_cache`、`setup_x11_permissions`、`cleanup_container_by_name`、`_validate_cache_paths`）为 Docker 守护进程/文件系统操作且另有覆盖，不在被测接线内；`test_start_profile_with_proxy_writes_secret_and_endpoint` 的 fake adapter 属于 core 级编排单测，不在 f005 的挂载接线范围内。本轮重跑挂载文件 17/17 通过。
  - t065_test_f006：消除。progress.md 收尾报告已订正为“4 条 5000ms 超时＋1 条 ProfileForm.t058 mock 调用次数断言失败（期望 1 次、实调 2 次），并行负载 flake”。日志 `.scratch/gate_evidence_t065/logs/frontend_test_single_run.log` 已归档，本轮核实：4 个文件各 1 passed——ProfileCreateDialog 7、ConfigTab 3、ProfileForm.t058 5（含原断言失败用例）、SettingsPage 3，合计 18/18，0 failed，日志内无 FAIL。
  - t065_test_f007：消除。证据已补齐并逐项核实：(1) `logs/integration_parallel.log` 尾行 `189 passed, 7 skipped, 4 warnings, 8 errors`，8 个 ERROR 均为 setup error，逐条核对 8 个测试名与 fixture 报错——均为 supervisor_api fixture 的 `Failed: isolated API process did not become ready`，fixture 源码为 100 次 × 0.1 秒轮询健康端点后失败，即 10 秒就绪超时，与 progress.md 说法一致；(2) `logs/integration_rerun_serial_8.log` 尾行 `8 passed`；(3) `logs/integration_serial.log` 尾行 `4 passed, 204 deselected`；(4) `suites.d/integration.tsv` 命令列已改为实际两段命令（并行 `-n 4 -m "not serial"`、串行 `-n 0 -m serial`）＋ `scripts/merge_junit.py` 合并步骤，不再是 run_gates.sh 展示命令；(5) 本轮独立解析 `junit/integration.xml`：208 个 testcase、208 个唯一 (classname, name)、0 failure、0 error、7 skipped，即 201 passed＋7 skipped；算术闭合（189＋4＋8＝201）。8 条 setup error 的测试在合并 junit 中以串行单跑的通过结果计入，progress.md 已明示该合并方式，不作伪造认定。
- 改测方向复核：无“迁就实现”的改测。f003 的 smoke 改名改述是把冒充基线对比的断言降为存活验证（断言收紧表述、删除绝对阈值），方向与 TDD 一致；其余本轮改动均为新增测试与文档订正，无既有测试预期被改写。
- 危险模式扫描：对新增生命周期文件与三处测试改动逐条扫描——无恒真断言、无删/反转 expect、无注释掉的断言、无 `.skip`/`.only`、无 `# type: ignore` 压制断言、无阈值增大、无赋值替代真实交互。仅有 3 处环境条件 `pytest.skip`（`test_t065_proxy_forwarder.py:581/605` IPv6 loopback 不可用时、`655` openssl 不可用时），本轮实跑 0 skipped，三项均实际执行并通过；跳过分支只在缺失环境触发且显式报 skipped。
- 本轮新发现：0 条。
- 未进表的提示：
  - 进度报告 09:46 裁决记录中“AC-002 仍判 VOID（HTTPS/IPv6 语义云端可验层面即坏）”描述的是裁决当时的状态（code f002/f003 未修）；本轮 test 轴核实：`test_https_upstream_wraps_tls`（646 行，自签证书 fake TLS 上游，真实 TLS 握手后才发 CONNECT）与 `test_socks5_ipv6_literal_target_uses_atyp4`（598 行，ATYP 0x04＋16 字节地址断言）均已新增并通过，云端可验层面的破损已补测。故本轮 AC-002 按修复后状态判 TICK-VALID（test 轴）；code 轴是否认可实现修复由 code 审阅 Round 3 另判。
  - IPv6 证据：本轮 45 项合跑 0 skipped，`test_http_upstream_ipv6_and_special_chars` 与 SOCKS5 IPv6 测试在本机实际跑过且通过；p098 本地验收中仍须显式确认 Mac 的 IPv6 loopback 可用，而非依赖跳过。
  - `test_start_profile_with_proxy_writes_secret_and_endpoint` 名为端到端、实为 core 级编排单测（fake adapter），已在 Round 1/2 并入 f001 论证；本轮 f001 的消除依据是父级改定的 [deploy] 打勾口径与 progress.md 的显式区分，不以该测试冒充端到端。
  - 本轮未重跑全量 unit 套件（约 11 分钟）与全量 frontend 套件、Docker 类验证（本机无 Docker）；全量门禁数字除本轮独立重跑与 junit/日志解析外仍作 progress.md claim 引用。
- 总体判断：7 条 test finding 全部消除，无新 blocker；5 条 AC 在父级改定的 [deploy] 口径下全部 TICK-VALID；PASS。

## Round 3 Reviewer 独立重跑记录（证据）

- 落点仓库校验：以 workdir 为仓库目录执行不带 `-C` 的 `git rev-parse --show-toplevel`，输出精确等于 `<home>/workspace/CBrowser_t065`；当前分支 `t065_proxy_credential_isolation`；基线 `a4726b3`；本轮指纹 `c6aaa3c19097122d`（Round 1/2 指纹 `96b7ac3770b9beb7` 已变，实施方确有改动）。
- 后端 t065 三文件合跑（主仓 gate venv，`PYTHONPATH=src/backend`，`CBROWSER_GATE_ENV_READY=1`，`--basetemp` 落仓内 `.scratch/tmp/r3unit`）：45 passed（协议 17、挂载 17、生命周期 11，0 skipped）。
- AC-005 相关 11 文件合跑（同环境，`.scratch/tmp/r3ac5`）：140 passed（Selkies pin/asset probe/wheel cache/controlled build/vendor 安全五件、t035 proxy runtime、network policy、t027 release controller、a24 deploy network source、t052 supervisor probe、t062 image closure）。
- 门禁 junit 独立解析（`.scratch/gate_evidence_t065/junit/integration.xml`）：208 例、208 唯一、0 failure、0 error、7 skipped（＝201 passed）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。父级改定的 [deploy] 口径下：实现完成（code f001 旧文件删除已入 core，挂载测试预置旧文件断言启动后消失）；云端可验部分实证——本轮重跑挂载 17/17 通过（Browser 挂载无凭据、secret 目录在 Browser 挂载之外、start_profile 写端点时删旧文件）；真实拓扑顺延 p098（未开），progress.md 复验行明写未冒充已验。
- AC-002：TICK-VALID，re_verified。云端可验部分实证——本轮重跑协议 17/17 通过，含新增 test_https_upstream_wraps_tls（真实 TLS 握手）与 test_socks5_ipv6_literal_target_uses_atyp4（ATYP 0x04＋16 字节断言），另有 IPv6＋特殊字符、SOCKS5 远端 DNS、407 失败封闭；真实三协议上游验收顺延 p098 第 2 项，未冒充已验。
- AC-003：TICK-VALID，re_verified。云端可验部分实证——本轮重跑生命周期 11/11 通过（reconcile 只重建转发器、预算耗尽、创建失败无孤儿、teardown 删转发器、readiness 标记缺失转发器、无代理模式不建转发器）与协议层故障封闭测试；真实故障封闭顺延 p098 第 3 项，未冒充已验。
- AC-004：TICK-VALID，re_verified。父级裁决：基线对比属 p098 第 4 项真实部署测量，云端只做 smoke——本轮核实 smoke 已改名改述、无绝对阈值、只断言 5/5 成功并报告样本中位数，p098 第 4 项明确承接基线对比；云端 smoke 不再冒充基线证据。
- AC-005：TICK-VALID，re_verified。Selkies pin/asset probe/wheel cache/controlled build/vendor 安全五件未被 diff 改动，本轮独立重跑含这批文件在内的 140 项全部通过；篡改被拒的校验入口测试在其中。

coverage = 5 / 5

verdict: PASS

## Round 4 (2026-11-14T11:11:03+08:00)

- task：`t065_proxy_credential_isolation`
- diff_anchor：`a4726b33bbfa3e2262a7b5a450271f2c6fdeebe4`
- round：4

reviewed_scope: 4dd19121e8e93b53

本轮为确认轮，只复核 Round 3 code 轴新发现的唯一 minor f010（测试覆盖与处置行）。前轮 test f001～f007 已在 Round 3 消除，本轮不重审，只以三件套重跑确认未被本次改动破坏。本轮指纹 `4dd19121e8e93b53`（与 Round 3 的 `c6aaa3c19097122d` 不同，实施方确有改动），由 `repo_task.monitoring.review_scope_fingerprint` 对同一 diff_anchor 独立算出。

## Findings

本轮无新 finding。f010 复核结论见结论段。

## 结论

- t065_code_f010：消除。直读与独立重跑证据如下（全部以绝对路径复核，`HOME=<home>` 已确认；中间相对路径 grep 曾短暂看到缺失行的旧视图，系 exec 跨调用 HOME 不稳定所致，已用绝对路径重核排除，不影响结论）：
  - 生产修复在位：`src/backend/cbrowser/proxy_forwarder/forwarder.py:475`，`_open_http_upstream` 的 CONNECT 握手 `readuntil` 的 except 元组已含 `asyncio.LimitOverrunError`（附注释“f010: third readuntil site; f007 fixed the other two”），转 `UpstreamError("upstream closed the CONNECT handshake")` 并先 `_close(writer)`，失败封闭；其余两处 `readuntil`（211/375 行）为 f007 已修，无同类残留。SOCKS5 段只用 `readexactly`，与处置行说法一致。
  - 新测试真实断言失败封闭，非空转。直读 `tests/unit/test_t065_proxy_forwarder.py:785-831` `test_oversized_connect_response_head_fails_closed`：fake 上游先读 CONNECT 请求头并记录，断言 `received == ["CONNECT 127.0.0.1:443 HTTP/1.1"]`（CONNECT 确已发出）；随后回 `HTTP/1.1 200 Connection Established` 加 70000 字节 `X-Pad`（超 64 KiB StreamReader 上限），并保持连接 0.5 秒（挂起的 CONNECT 会表现为挂起而非快速关闭）；Browser 侧 `reader.read()` 加 10 秒超时，断言 `data == b""`（收到空＝失败封闭）、`caplog`（asyncio logger、ERROR 级）中无 `LimitOverrunError`（无未处理异常）。
  - 反向验证已由本轮独立重复：临时删掉 475 行后单测失败，`asyncio.exceptions.LimitOverrunError: Separator is found, but chunk is longer than limit` 自 `readuntil` 经 `_open_http_upstream` 外泄（与声称的反向验证一致）；恢复后该行在位（grep 命中 475 行），单测 1 passed。恢复后又全量重跑三件套 46 passed，文件无残留改动。
  - 处置行恰好一行：`progress.md` 全文件 grep `t065_code_f010` 计数为 1（第 78 行），内容与修复一致（except 补类型并转 UpstreamError、补超 64 KiB 测试、反向验证、SOCKS5 无同类问题）。
  - 前轮 finding 未被破坏：三件套重跑 46 passed（协议 18、挂载 17、生命周期 11，0 skipped），与任务期望一致；f001～f007 的消除状态维持。
- 改测方向复核：本次改动只新增 1 个测试与 1 行 except，无既有测试预期被改写；新测试无恒真断言、无 `.skip`、无阈值放宽。
- 本轮新发现：0 条。
- 未进表的提示：反向验证期间 `/tmp` 备份文件在 exec 调用之间消失（tmpfs），恢复有效性以恢复后绝对路径 grep 命中 475 行＋单测通过＋三件套 46 passed 为据，不以 md5 对照备份为准。

## Round 4 Reviewer 独立重跑记录（证据）

- 落点仓库校验：绝对路径 `git rev-parse --show-toplevel` 输出 `<home>/workspace/CBrowser_t065`；基线 `a4726b3`；本轮指纹 `4dd19121e8e93b53`。
- 后端 t065 三文件合跑（主仓 gate venv，`PYTHONPATH=src/backend`，`CBROWSER_GATE_ENV_READY=1`，`--basetemp` 落仓内 `.scratch/tmp/r4unit2`）：46 passed（协议 18、挂载 17、生命周期 11，0 skipped）；逐文件收集计数同为 18/17/11。
- f010 反向验证：删 475 行后 `test_oversized_connect_response_head_fails_closed` 1 failed（`LimitOverrunError` 外泄）；恢复后 1 passed。
- 处置行计数：`progress.md` 中 `t065_code_f010` 恰好 1 处。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。维持 Round 3 结论：父级改定的 [deploy] 口径下实现完成＋云端可验部分实证（本轮挂载 17/17 通过），真实拓扑顺延 p098，未冒充已验；f010 改动不触及凭据隔离路径。
- AC-002：TICK-VALID，re_verified。维持 Round 3 结论：云端可验部分实证（本轮协议 18/18 通过，含新增 f010 超大 CONNECT 响应头失败封闭测试），真实三协议上游验收顺延 p098 第 2 项，未冒充已验。
- AC-003：TICK-VALID，re_verified。维持 Round 3 结论：云端可验部分实证（本轮生命周期 11/11 通过）与协议层故障封闭测试；真实故障封闭顺延 p098 第 3 项，未冒充已验。
- AC-004：TICK-VALID，re_verified。维持 Round 3 结论：云端 smoke 已改名改述、无绝对阈值、只断言 5/5 成功并报告样本中位数，基线对比属 p098 第 4 项，不冒充基线证据。
- AC-005：TICK-VALID，re_verified。维持 Round 3 结论：Selkies pin/asset probe/wheel cache/controlled build/vendor 安全五件未被 diff 改动；f010 改动仅限转发器 CONNECT 握手 except 与一个新增测试。

coverage = 5 / 5

verdict: PASS

## Round 5 (2026-11-14T11:19:54+08:00)

- task：`t065_proxy_credential_isolation`
- diff_anchor：`a4726b33bbfa3e2262a7b5a450271f2c6fdeebe4`
- round：5

reviewed_scope: 4dd19121e8e93b53

本轮为确认轮。Round 4 落盘后唯一改动是主会话补填了 `progress.md` 收尾报告的两行文字（“结果”行把“确认轮 Round 4 待执行”改为已完成并注明 Round 4 指纹与结论；“review”行填入 Round 4 实测结论与 AC 判定表摘要），无任何代码或测试改动。本轮复算指纹为 `4dd19121e8e93b53`，与 Round 4 完全一致——与 `repo_task.monitoring` 的口径一致：`progress.md` 属于 REVIEW_PROCESS_FILES，不计入被审 scope；两行文字改动不改变被审内容。

## Findings

本轮无新 finding。前轮 test f001～f007 的消除状态维持（见结论段）。

## 结论

- 被审范围未变：以 `repo_task.monitoring.review_scope_fingerprint` 对同一 diff_anchor 独立复算，本轮指纹 `4dd19121e8e93b53` 与 Round 4 一致；`git diff HEAD -- progress.md` 核实自 Round 4 以来唯一未暂存改动确为上述两行文字（结果行、review 行），无生产代码、测试、task.md 或其他交付文件改动。Round 4 的 PASS 结论所依赖的全部证据因此仍有效，无需重审。
- progress.md 两行填入内容核实无误：结果行所称“Round 4 已完成（双 PASS，指纹 4dd19121e8e93b53，两轴一致；code 轴 9/9 前轮 finding 消除，test 轴 7/7 消除；f010 消除，无新 finding）”与两份 review 文件的 Round 4 节逐项一致；review 行所称 `check_review_status.py` 实测（code PASS、test PASS、overall PASS、review_scope=ok、ac_review=ok、round=4、next_action=finalize）与本轮复跑该 checker 的输出一致（见重跑记录）；AC 判定表摘要“AC-001～005 全部 TICK-VALID（AC-004 为 trust_prior）”与两轴 Round 4 的 AC 表一致。
- 前轮 finding 消除状态维持：三件套重跑 46 passed（协议 18、挂载 17、生命周期 11，0 skipped），与 Round 4 计数一致；f010 修复仍在位（`forwarder.py:475`，except 含 `asyncio.LimitOverrunError` 并转 `UpstreamError`，附 f010 注释），f010 测试 `test_oversized_connect_response_head_fails_closed`（785 行）在三件套内通过；f001～f007 的消除所依赖的测试与文档（生命周期 11 测试、去 mock 化挂载测试、改名改述的 smoke 测试、订正的 s021/task.md、补齐的 integration 证据）均未被本次改动触及。
- 门禁证据独立解析（`.scratch/gate_evidence_t065/junit/`）：unit 2228 例、5 失败、0 错误、1 跳过——5 条失败签名与 progress.md 所列基线逐条一致（fontconfig write_failure、repo_hygiene 家路径、t060 geoip、t068 pinning 2 条），30 个 t065 用例 0 失败；contract 258 例、0 失败、1 跳过；integration 208 例、0 失败、7 跳过。数字与 progress.md 收尾报告完全一致，无新增失败。
- 改测方向复核：本次改动只改 progress.md 两行文字，无既有测试预期被改写；无恒真断言、无 `.skip`、无阈值放宽。
- 处置表完整性：`progress.md` 全文件 grep，17 个 finding_id（code f001～f010、test f001～f007）各恰好一行，无重复、无遗漏。
- 两轴一致性：code 轴 Round 4（`review_code.md` Round 4 节）verdict PASS、AC-001～005 全部 TICK-VALID（AC-004 trust_prior，其余 re_verified）、coverage 5/5，与本轴 Round 4/5 的 AC 表逐项一致；task.md 五条 AC 仍全勾，无未勾 AC。
- 本轮新发现：0 条。
- 未进表的提示：无。

## Round 5 Reviewer 独立重跑记录（证据）

- 落点仓库校验：以 workdir 为仓库目录执行不带 `-C` 的 `git rev-parse --show-toplevel`，输出精确等于 `<home>/workspace/CBrowser_t065`；当前分支 `t065_proxy_credential_isolation`；基线 `a4726b3`；本轮指纹 `4dd19121e8e93b53`（与 Round 4 一致，实施方/主会话均无被审内容改动）。
- 指纹复算：`repo_task.monitoring.review_scope_fingerprint('a4726b33bbfa3e2262a7b5a450271f2c6fdeebe4', 'docs/tasks/t065_proxy_credential_isolation')` 直接返回 `4dd19121e8e93b53`；`check_review_status.py` 复跑输出 review_level=full、code_verdict=PASS、test_verdict=PASS、overall=PASS、review_scope=ok、ac_review=ok、round=4、next_action=finalize（本轮 Round 5 落盘前）。
- 后端 t065 三文件合跑（主仓 gate venv，`PYTHONPATH=src/backend`，`CBROWSER_GATE_ENV_READY=1`，`--basetemp` 落仓内 `.scratch/tmp/r5unit`）：46 passed（协议 18、挂载 17、生命周期 11，0 skipped）。
- 门禁 junit 独立解析（`.scratch/gate_evidence_t065/junit/`）：unit 2228 例 5 失败 1 跳过、contract 258 例 0 失败 1 跳过、integration 208 例 0 失败 7 跳过；5 条 unit 失败签名逐条核对为基线。
- 未重跑全量 unit 套件（约 11 分钟）与全量 frontend 套件、Docker 类验证（本机无 Docker）；全量门禁数字除本轮三件套重跑与 junit 解析外仍作 progress.md claim 引用。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。维持 Round 3/4 结论：父级改定的 [deploy] 口径下实现完成＋云端可验部分实证（本轮挂载 17/17 通过），真实拓扑顺延 p098，未冒充已验；自 Round 4 以来无改动触及凭据隔离路径。
- AC-002：TICK-VALID，re_verified。维持 Round 3/4 结论：云端可验部分实证（本轮协议 18/18 通过，含 f010 超大 CONNECT 响应头失败封闭测试），真实三协议上游验收顺延 p098 第 2 项，未冒充已验。
- AC-003：TICK-VALID，re_verified。维持 Round 3/4 结论：云端可验部分实证（本轮生命周期 11/11 通过）与协议层故障封闭测试；真实故障封闭顺延 p098 第 3 项，未冒充已验。
- AC-004：TICK-VALID，trust_prior。维持 Round 3/4 结论：按父级 2026-11-14 09:46 裁决，基线对比属 p098 第 4 项真实部署测量；云端 smoke 已改名改述、无绝对阈值、只断言 5/5 成功并报告样本中位数，不冒充基线证据。
- AC-005：TICK-VALID，re_verified。维持 Round 3/4 结论：Selkies pin/asset probe/wheel cache/controlled build/vendor 安全五件未被 diff 改动；自 Round 4 以来无改动触及 Selkies 固定制品/SHA256 校验。

coverage = 5 / 5

verdict: PASS
