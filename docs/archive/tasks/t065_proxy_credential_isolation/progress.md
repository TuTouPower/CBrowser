---
tid: "t065"
slug: "proxy_credential_isolation"
title: "代理凭据隔离与认证转发失败封闭"
status: "done"
branch: "t065_proxy_credential_isolation"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "a4726b33bbfa3e2262a7b5a450271f2c6fdeebe4"
depends_on: "t062"
conflicts_with: "t061,t062,t063,t066,t068,t069"
note: "来源 p082；Web 客户端托管已存在，只纳入代理凭据剩余缺口"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-13 审阅修订：采纳第二暴露面及拓扑影响；AC-004 统一为默认无可测退化，预算属先测后决的技术取舍，删除无测量依据的通用 BLOCKING。

- 本次仅维护 backlog；不 start、不实现；旧归档来源只追加转办链，不改写历史。

- 调度字段经 task.py edit 写入；plan 的 runnable 只指依赖/冲突候选，不代表产品 BLOCKING 已解决。

- 调度依据：消费 t062 的运行镜像打包/中立端点；条件代理组件与 Browser 启动、挂载、恢复和镜像验证任务重叠。

- 2026-11-14 实现完成（执行者 muse-cloud-t065，基线 main a4726b3）：
  - 架构：每 Profile 一个独立认证转发器容器 `src/backend/cbrowser/proxy_forwarder/`（stdlib only，监听 18080）。凭据只写 secret 目录 `data_root/runtime/.secrets/{profile_id}/proxy_credentials.json`（0600），只 ro 挂进转发器；Browser 任何挂载源都不含凭据；升级前写在 runtime 目录的旧凭据文件在每次 `start_profile` 写端点时无条件删除（Round 1 code f001 修复：原“残留旧文件也被忽略、不挂载”表述不成立——rw 父目录挂载下旧文件仍可读）。Runner 只读无凭据端点文件 `proxy_forwarder.json`（scheme http、转发器容器名、18080、冻结 credential_revision），修订号漂移即 `proxy_credentials_changed` 失败封闭；`build_proxy_server_arg`（内联凭据构造）整体删除。
  - 转发器协议：HTTP/HTTPS CONNECT 隧道＋注入 Proxy-Authorization（407 失败封闭）、absolute-form 直发；SOCKS5 用户名/密码认证、目标域名 domain 直通（远端 DNS）。上游不可达/407/认证失败/畸形请求均关连接、无响应体、无直连；日志经 `cbrowser.redact`。TDD 修掉：`IncompleteReadError` 误写、`_relay` FIRST_COMPLETED 语义、absolute-form 分流、`_relay` 参数交叉回环。审阅修复（Round 1）补：https 上游先包 TLS 再发 CONNECT；SOCKS5 IPv6 字面目标 ATYP 0x04（CONNECT 先剥方括号）；absolute-form 非 2xx 不透传响应体；用户名无密码时 Basic 恒为 `user:`（RFC 7617）；超 64 KiB 请求头捕获 `LimitOverrunError` 关连接；`UpstreamConfig.from_dict` 拆为 6 个小校验函数；`create_proxy_forwarder` 拆为编排器＋5 助手函数（行为不变）。
  - 网络策略：`NetworkPolicySpec` 新增角色 `proxy-forwarder` 与 `input_tcp_ports`（入站只允 18080，出站只允上游端点 IP 字面量＋Docker DNS 127.0.0.11:53/udp，OUTPUT 默认 DROP）；Browser 代理出站只允转发器端点；loopback host-gateway 映射与 `extra_hosts` 改由转发器承担。实现中补回一次误删：首版编辑曾丢 `validate_endpoints` 校验器，`test_network_policy_spec_validation` 抓出后已恢复并补 forwarder 渲染断言。
  - 启动顺序网络 → 转发器 → Browser → Stream；转发器缺失/退出时 reconcile 只重建转发器（`_replace_proxy_forwarder_only`，与 Stream 同型预算 300 秒/3 次）；readiness 增 `proxy-forwarder` 检查与策略复核；teardown、`_confirm_sandbox_gone`、scan、`get_profile_containers` 计入转发器；启动 gate `--role` 接受 `proxy-forwarder`；`cleanup_container_by_name` 与 `cleanup_network_by_name` 的 role 白名单补 `proxy-forwarder`（否则转发器删不掉、网络清不掉——实现中实测抓出，非测试发现）。
  - 镜像与部署：新镜像 `config/docker/proxy_forwarder_runtime/`（钉版 python:3.15-slim-trixie、tini、只 COPY `proxy_forwarder` 包＋`redact.py`，无 pip 步骤）；deploy.sh 构建并以 `CBROWSER_PROXY_FORWARDER_IMAGE` 不可变 id 写入 release env；compose.yaml 传入 Supervisor。browser/supervisor 镜像补 COPY `proxy_forwarder`（＋browser 补 `redact.py`）及 dockerignore 白名单，否则闭包测试报 `No module named 'cbrowser.proxy_forwarder'`；闭包测试 IMAGES 表新增 `proxy-forwarder`。
  - 旧测试整体删除（TDD 规则，理由见各文件内 NOTE）：t035 的 5 个内联凭据测试（4 个 `build_proxy_server_arg`＋`test_matching_revision_returns_proxy_arg`）、`test_supervisor_written_credentials_are_accepted_by_runner`、`test_browser_container_mounts_credentials_read_only_and_resolves_egress`、`test_start_profile_with_proxy_end_to_end`、t052 的 3 个 Browser-start loopback 测试。替换覆盖在 `tests/unit/test_t065_proxy_forwarder_mounts.py`（凭据挂载、Runner 端点解析、forwarder loopback 三则、start_profile 端到端、cleanup/gate）与 `tests/unit/test_network_policy.py`（forwarder 渲染）。另修一处测试与仓内惯例对齐：`create_proxy_forwarder` 的 image 是位置参数（与 Browser/Stream 一致），断言改读 `call_args.args[0]`。
  - 门禁首跑（2026-11-14）抓出两处实现自查未覆盖的缺口，均已修：
    - `create_proxy_forwarder` 漏传 `_prepare_policy_gate` 的 `role` 必填参数（测试 mock 了该方法故未暴露；复查时逐项核对未 mock 调用的签名时发现）——补 `"proxy-forwarder"`（否则运行时 TypeError、转发器建不出）；同轮把 `_wait_for_proxy_forwarder_ready` 的 `asyncio.get_event_loop()` 改为 `get_running_loop()`。
    - deploy.sh 新增第六镜像后 `test_t027_release_controller::test_deploy_success_builds_once_and_pins_everything`（断言 5 镜像）与 `test_a24_deploy_network_source::test_render_failure_refuses_deploy_and_publishes_nothing`（隔离仓 fixture 只有 5 个 runtime 目录，前置检查先于渲染失败退出）失效。处置：① 发现 release manifest 的 `images` 未记 `proxy-forwarder`（env 里有、manifest 里无，回滚/鉴真读 manifest 会丢该镜像）——deploy.sh manifest 补 `"proxy-forwarder": "$proxy_forwarder_id"`；② t027 旧测试整体删除（理由见文件头 NOTE），新写 `test_t065_deploy_success_builds_six_images_once_and_pins_proxy_forwarder` 复写整套断言（6 构建、6 dockerfile、manifest 7 键含 proxy-forwarder 且为 Dockerfile 内容哈希、env 含 `CBROWSER_PROXY_FORWARDER_IMAGE=sha256:`、pointer/compose/无秘密）；③ a24 只是 fixture 缺新前置目录（断言 exit 2/拒绝发布/无产物本身未变），fixture 元组补 `"proxy_forwarder_runtime"`。两条定向 2/2 通过。
  - 门禁（见收尾报告）：全量 `scripts/run_gates.sh`，云端跑不了的 Docker e2e、real_engine、[deploy] 真实拓扑按口径跳过记 pass。
  - 2026-11-14 审阅修复（双路审阅 Round 1＋Round 2 均为 FAIL，16 条 finding；父级 09:46 裁决照此执行）：5 条 AC 打勾已撤回。生产侧：`start_profile` 写端点时无条件删除 runtime 目录旧凭据文件（code f001；ADR 036、spec 第 9 节、本文件同步订正“残留也被忽略”表述）；forwarder.py 修 f002/f003/f005/f006/f007/f009（见上一条协议行）；docker_adapter.py 修 f008 拆函数。测试侧：协议测试补 f002 TLS（openssl 自签证书＋fake TLS 上游）、f003 SOCKS5+IPv6、f005 absolute-form 407 带体、f006 用户名无密码冒号、f007 70KB 请求头，smoke 测试如实改名改述（test f003）；挂载测试去掉 4 个内部方法自 mock、gate 准备真实执行并 spy 锁定 `role="proxy-forwarder"`（test f005）；新建 `tests/unit/test_t065_proxy_forwarder_lifecycle.py` 11 测试（test f004）；start_profile 测试预置旧文件断言删除（code f001）。定向结果：协议测试 17/17、挂载测试 17/17、生命周期 11/11。文档：task.md 未知契约清单按 s021 改写为已核实（test f002）；p098 第 4 项明确承接 AC-004 基线对比（test f003）；本文件前端门禁摘要订正（code f004/test f006）、复验行区分云端可验与 p098 真实拓扑（test f001）。证据：前端 4 文件单跑日志归档 `logs/frontend_test_single_run.log`；integration 两段补跑日志归档 `logs/integration_parallel.log`、`logs/integration_serial.log`，`integration.tsv` 命令列改为实际两段命令＋合并步骤（test f007）。门禁重跑与重新打勾见收尾报告。
  - 2026-11-14 Round 3 后补修 code f010（Round 3 code 轴新发现 minor，非阻断）：`_open_http_upstream` 的 CONNECT 握手 `readuntil` 是三处 `readuntil` 中唯一未捕获 `LimitOverrunError` 的一处（f007 只补了另两处）；except 补该类型并转 `UpstreamError`（失败封闭，客户端 writer 已关闭）；补测试 `test_oversized_connect_response_head_fails_closed`（上游回超 64 KiB CONNECT 响应头，断言 Browser 侧收到空且无未处理异常；反向验证：临时撤掉修复则测试失败，恢复则通过）。SOCKS5 段只用 `readexactly`（定长读，无该异常）。协议测试现 18/18，三件套合跑 46/46。处置行见 Review 处置表 Round 2 节末行。
  - [deploy] AC 打勾口径（沿用 t061/t066/t063/t069 先例）：AC-001～004 实现完成、云端可验部分实证后打勾，真实部署链登记新 pending p098（本地补验），复验行与本文件显式写明未冒充已验；AC-005 可自动测试实证打勾。
  - Spike s021：report 已写并采纳；`findings.py new` 因既存 d037/d038 编号重复拒绝取号（与 t063 相同工具链缺陷，已挂 p093 第 6 项），未绕过工具链手建 finding——结论以 s021 report 为载体，report 内已写明该缺陷与 p093 关联。finish 的 spike 引用检查若卡此项，由父级裁决。
  - 收尾口径更正：本 task 的 [deploy] AC 按上述先例打勾（同 t063/t069 在 06:30 汇报里向用户说明过的口径）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 2（2026-11-14，审阅修复环节）

双路审阅 Round 1＋Round 2 均为 FAIL（overall FAIL，指纹 `96b7ac3770b9beb7`），共 16 条 finding；父级 2026-11-14 09:46 已裁决：[deploy] 打勾口径维持 t061/t066/t063/t069 先例，AC-002 仍判 VOID（HTTPS/IPv6 语义云端可验层面即坏）、AC-004 判 VALID（基线对比属 p098 真实部署测量）、code 第二份审阅 f002/f003 升 important 采纳。5 条 AC 打勾已撤回，修复并重验后重新打勾。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t065_code_f001|important|已修|start_profile 写端点时无条件删除 runtime 目录旧凭据文件；测试预置旧文件断言启动后消失；ADR 036、spec 第 9 节、progress.md 订正“残留也被忽略”表述|src/backend/cbrowser/supervisor/core.py；tests/unit/test_t065_proxy_forwarder_mounts.py|
|t065_code_f002|important|已修|https 上游先包 TLS（ssl.create_default_context 经 open_connection 透传），否则明文 CONNECT 发往 TLS 端口必败；补自签证书 fake TLS 上游测试|src/backend/cbrowser/proxy_forwarder/forwarder.py；tests/unit/test_t065_proxy_forwarder.py|
|t065_code_f003|important|已修|SOCKS5 IPv6 字面目标用 ATYP 0x04（inet_pton 识别），CONNECT 先剥方括号；补 IPv6 目标测试（ATYP 0x04＋16 字节断言）|src/backend/cbrowser/proxy_forwarder/forwarder.py；tests/unit/test_t065_proxy_forwarder.py|
|t065_code_f004|minor|已修|progress.md 前端门禁摘要订正为 4 条 5000ms 超时＋1 条 ProfileForm.t058 mock 调用次数断言失败；单跑复绿日志归档进 evidence 目录|docs/tasks/t065_proxy_credential_isolation/progress.md；.scratch/gate_evidence_t065/logs/frontend_test_single_run.log|
|t065_code_f005|minor|已修|absolute-form 经 HTTP 上游拿非 2xx（407 抛 UpstreamAuthError）即关连接、不透传响应体；补 407 带体测试（Browser 侧收到空）|src/backend/cbrowser/proxy_forwarder/forwarder.py；tests/unit/test_t065_proxy_forwarder.py|
|t065_code_f006|minor|已修|用户名无密码时 Basic 恒拼冒号（RFC 7617：`user:`）；补断言测试|src/backend/cbrowser/proxy_forwarder/forwarder.py；tests/unit/test_t065_proxy_forwarder.py|
|t065_code_f007|minor|已修|handle_client 捕获 asyncio.LimitOverrunError（_MAX_HEAD_BYTES 长度检查保留为第二层）；补 70KB 请求头测试（连接关闭、无未处理异常）|src/backend/cbrowser/proxy_forwarder/forwarder.py；tests/unit/test_t065_proxy_forwarder.py|
|t065_code_f008|minor|已修|create_proxy_forwarder 拆为编排器＋_validate_forwarder_image/_load_forwarder_upstream/_run_forwarder_container/_install_forwarder_policy/_reclaim_failed_forwarder；行为不变，挂载测试 17/17|src/backend/cbrowser/supervisor/docker_adapter.py|
|t065_code_f009|minor|已修|UpstreamConfig.from_dict 拆为 6 个小校验函数（scheme/host/port/username/password/revision）|src/backend/cbrowser/proxy_forwarder/forwarder.py|
|t065_test_f001|important|已修|progress.md 与复验行明确区分云端可验部分（本地桩协议测试＋容器接线测试）与 p098 真实拓扑部分，不把 fake 上游/mock Docker 写成拓扑证据|docs/tasks/t065_proxy_credential_isolation/progress.md|
|t065_test_f002|important|已修|task.md 未知契约清单按 s021 结论改写为已核实（结论＋验证方式），基线对比部分明确顺延 p098；s021 report 同步订正（https 包 TLS、IPv6 ATYP 0x04、smoke 只做存活验证）|docs/tasks/t065_proxy_credential_isolation/task.md；docs/spikes/s021_proxy_auth_forwarder_topology/report.md|
|t065_test_f003|important|已修|smoke 测试改名 test_first_byte_smoke_reports_latency_samples：只断言 5/5 成功并报告样本中位数，不再以 0.25s 绝对阈值冒充基线对比；p098 第 4 项明确承接基线对比|tests/unit/test_t065_proxy_forwarder.py；docs/pending/todo/p098_t065_local_deploy_verification.md|
|t065_test_f004|important|已修|新建 tests/unit/test_t065_proxy_forwarder_lifecycle.py（11 测试）：reconcile 只重建转发器（缺失/退出）、预算耗尽（300 秒/3 次）、创建失败无孤儿、teardown 删转发器、readiness 标记缺失转发器、无代理模式不建转发器|tests/unit/test_t065_proxy_forwarder_lifecycle.py|
|t065_test_f005|important|已修|挂载测试去掉 _prepare_policy_gate/_resolved_endpoint/_install_network_policy/_wait_for_proxy_forwarder_ready 的自 mock（曾掩盖 role 必填参数 bug），gate 准备真实执行并以 spy 锁定 role="proxy-forwarder" 调用；策略以 helper 容器收到的真实 JSON 断言|tests/unit/test_t065_proxy_forwarder_mounts.py|
|t065_test_f006|minor|已修|同 code f004（前端摘要订正＋单跑日志归档，单跑 18/18 通过，注明并行负载 flake）|docs/tasks/t065_proxy_credential_isolation/progress.md；.scratch/gate_evidence_t065/logs/frontend_test_single_run.log|
|t065_test_f007|minor|已修|integration 两段补跑日志归档 logs/integration_parallel.log 与 logs/integration_serial.log；integration.tsv 命令列改为实际两段命令＋合并步骤；junit 算术 208 例＝201 passed＋7 skipped 保持闭合|.scratch/gate_evidence_t065/logs/integration_parallel.log；.scratch/gate_evidence_t065/logs/integration_serial.log；.scratch/gate_evidence_t065/suites.d/integration.tsv|
|t065_code_f010|minor|已修|Round 3 新发现（f007 同族残留）：_open_http_upstream 的 CONNECT 握手 readuntil 未捕获 LimitOverrunError；except 补该类型并转 UpstreamError（失败封闭），补超 64 KiB CONNECT 响应头测试（反向验证：撤修复则测试失败）；SOCKS5 段只用 readexactly，无同类问题|src/backend/cbrowser/proxy_forwarder/forwarder.py；tests/unit/test_t065_proxy_forwarder.py|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：审阅修复完成，16 条 finding 已修（处置见 Review 处置表）；Round 3 code 轴新发现 f010 已补修（见实施笔记），确认轮 Round 4 已完成（双 PASS，指纹 4dd19121e8e93b53，两轴一致；code 轴 9/9 前轮 finding 消除，test 轴 7/7 消除；f010 消除，无新 finding）。门禁重跑见下；5 条 AC 已重新打勾（AC-001～004 为 [deploy]：云端可验部分已满足并按 t061/t066/t063/t069 先例打勾，真实 Docker/Chrome/引擎拓扑验收顺延 p098 本地补验，不冒充已验；AC-005 全部满足并打勾）。
- 测试：protocol_drift 通过（修复后重跑）；requirements 通过；contract 257 passed / 0 failed / 1 skipped（258 例，重跑后刷新 junit，无变化）；unit 2222 passed / 5 failed / 1 skipped（2228 例，重跑后刷新 junit），5 failed 与 501ac0b 基线逐条同签名（fontconfig write_failure、repo_hygiene 家路径、t060 geoip、t068 pinning 2 条云端 x64 平台差异），无新增（修复后新增 17 测试：协议 6、生命周期 11，全部通过）；integration 201 passed / 0 failed / 7 skipped（208 例）；design_lint 0 error（修复后重跑）、design_check 通过（修复后重跑）、frontend_build 通过；frontend_test 并行 628 passed / 5 failed：4 条 5000ms 超时＋1 条 ProfileForm.t058 mock 调用次数断言失败（期望 1 次、实调 2 次），并行负载 flake，与 t065 改动无关——4 个文件单跑 18/18 通过，日志归档 `logs/frontend_test_single_run.log`。证据 `.scratch/gate_evidence_t065/`（suites.d 各套件 exit、junit 三份）；说明：evidence 模式全量跑中途遇运行环境重启中断，integration 未及跑完，已用与 `run_gates.sh` 相同的两段命令（并行 197 passed / 7 skipped、串行 4 passed）手动补跑并合并 junit，算术 208 例＝201 passed＋7 skipped；审阅修复后第二次两段重跑：并行段 189 passed / 7 skipped / 8 个 setup error（均为 supervisor_api fixture 的 “isolated API process did not become ready”，并行负载下 API 子进程 10 秒就绪超时，时值 omni t613 vitest 并发、load 约 6；非测试本体失败、与 t065 改动无关），8 条按仓内惯例串行单跑复核 8/8 通过（日志 `logs/integration_rerun_serial_8.log`），串行段 4/4，合计 201 passed / 7 skipped，junit 算术保持闭合；补跑日志归档 `logs/integration_parallel.log`、`logs/integration_serial.log`，`integration.tsv` 命令列为实际两段命令＋合并步骤；unit 两段与 contract 重跑日志归档 `logs/unit_parallel.log`、`logs/unit_serial.log`、`logs/contract.log`；其余套件结果出自该次 evidence 运行。
- 黑盒：云端无 Docker，Docker e2e 与 real_engine 按云端口径跳过记 pass；云端证据为本地桩协议测试（fake 上游）与容器接线测试（fake Docker 客户端、真实执行 adapter 内部方法），不是真实拓扑证据；AC-001～004 真实拓扑黑盒顺延 p098 本地执行，不冒充已验。
- review：Round 4 双 PASS（指纹 4dd19121e8e93b53，两轴一致；review_level=full；code 轴 9/9 前轮 finding 消除，test 轴 7/7 消除；Round 3 新发现 code f010 已消除，无新 finding；check_review_status.py 实测 code_verdict=PASS、test_verdict=PASS、overall=PASS、review_scope=ok、ac_review=ok、round=4、next_action=finalize）。AC 判定表两轴一致：AC-001～005 全部 TICK-VALID（AC-004 为 trust_prior，按父级 09:46 裁决：基线对比属 p098 第 4 项）。
- AC 判定：见 `task.md` 行内打勾（五条全勾；AC-001 修 code f001 后打勾、AC-002 修 code f002/f003 后打勾、AC-003 修 test f004 后打勾、AC-004 按父级裁决判 VALID（基线对比顺延 p098 第 4 项）、AC-005 维持 VALID；AC-001～004 [deploy] 真实拓扑部分顺延 p098）

### 结果摘要

- 代理凭据隔离：Browser 永不见凭据（argv/挂载/端点文件均无秘密），认证由独立转发器容器注入；失败封闭（407/上游不可达/认证失败/DNS 失败均关连接、无直连回退）；转发器缺失/退出只重建转发器（300 秒/3 次预算）；release manifest 与 env 均钉住第六镜像 `cbrowser-proxy-forwarder`。遗留只写引用，不复制正文：p098（本地真实部署补验）、p093 第 6 项（findings.py d037/d038 编号重复工具链缺陷，s021 结论未入 findings）。

### 长期文档闭环

- specs_index: not_applicable: 本 task 的 spec 累积在 `docs/specs/proxy_management.md`（头部加 t065、第 9 节）与 `docs/specs/runtime_lifecycle.md`（转发器生命周期节），二者本就不在 `docs/specs_index.md` 表内（与 t069 先例一致：表中只有 browser_isolation 与 webrtc_remote_display 两行）；ADR 036 已追加到 `docs/blueprint/decisions.md`，`docs/blueprint/supervisor.md`、`docs/blueprint/security.md`、`docs/blueprint/architecture.md` 已同步更新。
- spike s021：report 在 `docs/spikes/s021_proxy_auth_forwarder_topology/report.md`（已采纳）；现存 finding：无新建条目——`findings.py new` 因既存 d037/d038 编号重复拒绝取号（工具链缺陷，已挂 p093 第 6 项），未绕过工具链手建 finding；后续 tid：p098 本地真实部署补验。
