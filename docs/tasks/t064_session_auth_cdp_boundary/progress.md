---
tid: "t064"
slug: "session_auth_cdp_boundary"
title: "会话入口鉴权与 CDP 自动化边界收敛"
status: "done"
branch: "t064_session_auth_cdp_boundary"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "680d850067075caf9356ee6c71771f6dc779c543"
depends_on: "t062"
conflicts_with: "t061,t062,t069"
note: "来源 p075、p084；合并边缘鉴权、会话凭证与 CDP 隔离"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-13 审阅修订：删除虚设 AC-003，不复用编号；AC-005 改为现状回归。保留一项安全边界交付，不机械拆成两个独立任务。

- 本次仅维护 backlog；不 start、不实现；旧归档来源只追加转办链，不改写历史。

- 调度字段经 task.py edit 写入；plan 的 runnable 只指依赖/冲突候选，不代表产品 BLOCKING 已解决。

- 调度依据：消费 t062 的领域认证/端点公共边界；Gateway 握手和自动化鉴权同 t061/t069 重叠。

- 2026-11-13 执行基线更正：run-begin 按 depends_on=t062 正规叠栈，worktree 基线为 t062 finish 提交 680d850（非 main c5f8329），t062 的 cbrowser/shared 边界直接消费；不含 t061（646e24b）。与 t062 为基线关系而非重叠关系。

- preflight=PASS（1 条警告：2 项 UNVERIFIED-SPIKE）；已建正式 spike s018（边缘与 Gateway 授权证明）、s019（Chromium loopback Host/Origin 边界）并完成云端可验部分，结论回填 task.md 未知契约清单。findings.py 被基线既存编号重复阻断：docs/findings 内 d037、d038 各有两条不同条目，`findings.py new` 拒绝分配新号（与 t062 所遇同一缺陷，非本 task 引入，未绕过、未改工具链）；结论以 spike 报告＋task.md 回填为据。

- 设计定稿（s018 采纳）：Caddy 对 /stream/*/signal 走 forward_auth → API 新端点 GET /api/v1/internal/edge/viewer-authorize（边缘证明头 X-CBrowser-Edge-Proof 校验、复用 AuthService.authorize_viewer 判定会话/Origin/Profile），放行时回注 X-CBrowser-Authorized-Profile 与短期 HMAC viewer grant（TTL 60s、绑定 Profile、claims 不含会话标识）；Caddy 对该路由删除待代理请求的 Cookie 头并在站点层对外部 /api/v1/internal/* 显式 404；Gateway 改为本地验 grant（签名/到期/Profile 绑定），删除读 Cookie 与内部 viewer-authorize 调用，API 旧端点与 GatewayApiClient.authorize_viewer 一并删除。两跳秘密按既有一对一秘密文件模式新增 edge_proof_key（Caddy 进程环境＋API 文件）与 viewer_grant_key（API＋Gateway 文件），deploy.sh ensure_internal_secrets 生成，grant 签发/校验落 cbrowser/shared 中立模块。

- 旧测试语义处置预告：viewer 握手鉴权语义整体变更（Cookie 直验 → grant 验签），GatewayHarness 的 FakeApi viewer-authorize 与 set_viewer_auth、以及 API 旧内部端点 HTTP 层测试将按新语义整体改写（harness 改本地签发 grant），理由即本条；AuthService.authorize_viewer 服务层测试语义不变、保留。

- 实现完成（云端）：`cbrowser/shared/viewer_grants.py`（ViewerGrantAuthority mint/verify、TTL 60 秒、坏输入恒 None）；API 新增 `api/internal_edge.py` 边缘解析端点并在 `api/app.py` 装配（env `CBROWSER_EDGE_PROOF_FILE`/`CBROWSER_VIEWER_GRANT_KEY_FILE`），旧 `internal_gateway.py` 的 viewer-authorize 端点与模型删除；Gateway `handle_viewer_signal` 改本地 grant 验签（无 grant 401、验签失败/可信头不一致 403、节流与就绪检查顺序不变），`GatewayApiClient.authorize_viewer` 删除，`gateway/config.py` 新增必填 `viewer_grant_key_file`；`network_config.generate_caddyfile` 新增内部路径 404 与 signal 路由 forward_auth＋Cookie 删除；compose/deploy.sh 完成两跳秘密接线（edge_proof_key 仅 API 文件＋Caddy 进程环境、viewer_grant_key 仅 API＋Gateway 文件，deploy.sh compose_with 调用时从秘密文件注入 Caddy 环境、不打印不落盘）；内部 OpenAPI schema 已再生（公开 v1 schema 无变化）。

- 旧测试整体改写已按预告执行：`test_gateway_signaling.py` 整体改写为 grant 语义（含「只有 Cookie 也 401」）；`test_auth_api.py::test_internal_gateway_endpoints` 与 `test_internal_service_config.py` 改探 runtime 面＋旧端点 404；Gateway 测试 harness（test_gateway_fixtures、supervisor_recovery_probe）改本地签发 grant。另：supervisor_recovery_probe 的 `FakeGatewayApiClient` 已删除其 viewer 授权面、`ProductionGatewayService` 新增 grant 支持（先前笔记中「重复类定义」一说经 test 轴审阅直查基线 680d850 证伪——基线只有一份定义，该说已订正删除）；findings.py 编号重复阻断见前条。

- [deploy] e2e 已按新流更新（云端只改不跑）：gateway_probe topology 给 API/Gateway/Caddy 容器供两跳秘密；`test_gateway_ac001_auth_e2e.py` 改为边缘流断言（Cookie Path=/、无会话 401、伪造边缘头 401、外部解析端点 404、坏 Origin/跨 Profile 403，删除旧 Gateway Cookie 拒绝体与 Gateway 日志断言——拒绝已前移到边缘、旧前提失效）；`test_browser_runtime_e2e.py` 新增 `test_t064_cdp_loopback_host_origin_boundaries`（合法回环正例、域名 Host 403、跨 Origin CDP WS 403）。两文件 collect-only 通过。

- AC 逐条判定（云端证据＋[deploy] 顺延口径，与 t062 的 p092 先例一致）：

    - AC-001：云端验足——shared grant 单元 15 例、API 边缘集成 8 例（登出撤销后 401）、Gateway 集成（无 grant/只有 Cookie 401、跨 Profile 403、就绪后建隧道）、Caddyfile 渲染契约（Cookie 删除、Path=/ 不变由 e2e 断言守）。真实 Caddy/Chrome 链顺延 p094。
    - AC-002：云端验足——Caddyfile 契约（内部路径 404 先于 /api 代理、伪造头先删）、边缘端点证明校验（缺/错证明 403、未配置 503）、Gateway 直连无 grant 401/伪造 403、Agent register 集成回归全过。真实拓扑顺延 p094。
    - AC-004：云端验足——`test_automation_api.py` 新增普通 Profile detail/list 不含 cdp_ws_path 与 token 的契约断言、专用 Automation 状态端点唯一披露面不变、automation token 拒绝矩阵全过；CDP 本体不可达由配置走读（s019）与既有 AC-003 peer 拒绝例守。真实引擎 Host/Origin 负向例已写、云端 collect-only，实跑顺延 p094。
    - AC-005：云端全验打勾——本 task 未触 snapshot/wait_for/extract 与同源客户端代码；integration 全量中的 test_agent_executor_chain、test_automation_probe_chain 与 unit 的 test_agent_executor_refs/cli 全过，前端 test/build 复跑全过。
    - AC-006：云端完成全部前置（真实拓扑 harness 与 e2e 用例已按新流就绪、collect-only 通过）；真实 Caddy/Chrome 登录/首帧/重连/退出撤销/认证自动化实跑顺延 p094。

- 全量门禁（2026-11-14，worktree 内 evidence 模式实跑）：requirements_check PASS；contract 257 passed/1 skipped；unit 并行 2031 passed/1 skipped＋串行 64 passed，4 failed 全定性——`test_a16_protocol_drift` 为 worktree 缺 node_modules 的环境失败（`npm ci` 后单文件复跑 15 passed）；`test_repo_hygiene`（t062 review 文件含家路径）与 `test_fontconfig`（t062 把 fontconfig 的 os import 迁走后测试 monkeypatch 失效，AttributeError）均在 pristine 680d850 临时 worktree 同签名复现，属叠栈基线继承、非本 task 引入且不在本 task 修；`test_t060_gate_boundaries` 为任务简报既知基线失败，签名一致（AttributeError: 'GatewayTopologyHarness' object has no attribute 'data_dir'）。integration 并行 183 passed/7 skipped＋串行 2 passed，16 errors 全为子进程服务器 10 秒启动超时，串行分批复跑 14 passed、余 2 例单独复跑 2 passed，定性负载 flaky。protocol_drift_check、design_lint、design_check、frontend_test、frontend_build 首跑因 Node 版本/PATH 与缺 node_modules 失败，环境修正（Node 26 字面路径＋npm ci）后逐项复跑全过。e2e/real_engine 云端无 Docker 按口径跳过记 pass：e2e 全树 collect-only 102 例无错误，实跑顺延 p094。

- 长期文档闭环：blueprint 的 architecture/gateway/security/testing/automation 已更新（automation.md 仅修正「Gateway 只调用 viewer-authorize」的失效句）；specs 已累积 t064 节（access_control、webrtc_remote_display），specs_index 两行均已登记 t064。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-14T00:38:27+08:00)

code 轴 verdict FAIL（1 critical / 2 minor），test 轴 verdict PASS（3 minor）。按规矩已撤回全部 AC 打勾，逐项修复并重验后重新打勾（见表下散文）。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t064_code_f001|critical|已修|渲染 Caddyfile 的 signal 块未用 route 包裹，Caddy 默认指令序 forward_auth 先于 request_header，会删掉刚回注的 grant 头，合法握手恒 401；已整体包入 route 保序|src/backend/cbrowser/network_config.py signal 块；tests/unit/test_t064_edge_caddyfile.py 补 route 与顺序断言|
|t064_code_f002|minor|已修|specs/access_control.md 把 Gateway 校验顺序写反（实现为 Origin→grant）|docs/specs/access_control.md:39 已改「先验 Origin，再验 grant」|
|t064_code_f003|minor|已修|内部 OpenAPI 未声明边缘证明要求；端点已加声明式 Header 参数并再生内部 schema|src/backend/cbrowser/api/internal_edge.py；schemas/openapi/cbrowser_internal.json；tests/unit/test_runtime_agent_protocol_export.py 补参数断言|
|t064_test_f001|minor|已修|Gateway 集成层缺「过期 grant 被拒」用例（原仅 shared 单元层覆盖）|tests/integration/test_gateway_signaling.py 在拒绝矩阵补过期 grant 403|
|t064_test_f002|minor|已修|AC-004「信令/错误不提供 CDP 凭据」面无直接断言|tests/integration/test_gateway_signaling.py 补 401/403 拒绝响应体无 cdp 断言|
|t064_test_f003|minor|已修|新增交付文件未跟踪、单独 diff 不可见|收尾时全部交付文件 git add 暂存（finish 前置动作）|

Round 1 修复复验（2026-11-14）：f001 经 Caddy 官方指令序文档独立核实成立（forward_auth 在 request_header 之前、route 内容保声明序）；修复后 test_t064_edge_caddyfile、test_edge_viewer_authorize、test_gateway_signaling、test_automation_api、test_runtime_agent_protocol_export、test_t054_deploy_network_config 合计 54 passed，另 test_t054_origin_whitelist_deploy、test_a25_compose_secret_mounts、test_shared_viewer_grants 23 passed。AC-001/AC-006 的 TICK-VOID 随 f001 修复解除，待 Round 2 复核。test 轴另指出实施笔记「重复类定义」与基线不符，已按其直查结果订正（见实施笔记）。

### Round 2 (2026-11-14T00:48:36+08:00)

code 轴与 test 轴均 verdict PASS、零新 finding：六条 Round 1 finding 逐项复核「已修成立」（code 轴实跑两组 24＋21 passed；test 轴复跑 progress 两组数字 54＋23 passed 逐字复现）；AC 五条全部 TICK-VALID（AC-001/AC-006 的真实链部分按 [deploy] 口径顺延 p094，review 中明确不表示已验）。task.md 打勾已在修复并重验后恢复，收尾成立。

### Round 3 (2026-11-14T02:39:10+08:00)

确认轮（落盘补正，非新一轮业务复审）：接续执行者首跑 finish 被 review 门禁判 INCOMPLETE、零写入退出——两份报告的 `reviewed_scope` 仍停在 Round 1 指纹 `e979cc1914d912d9`（Round 2 复核未把最终交付指纹落盘），且 review_test.md 最后一轮小节题为「AC TICK 判定（Round 2）」、不合门禁对「AC 复验方式」小节的识别。双轴确认审阅在最终交付上各自独立复算指纹均为 `3cd6ec932d29a297`，并核对交付字节自 Round 2 审阅后未变（交付文件 mtime 全部 ≤ 00:44:32 CST，早于 Round 2 两份报告落盘 00:49:40/00:51:37 CST，Round 1 指纹过期纯属落盘缺口、非字节差异）；抽验与定向复跑（code 轴 caddyfile＋edge 12 passed；test 轴 54＋23 passed 逐字复现）与 Round 2 记录一致，双轴均 verdict PASS、AC 五条全部 TICK-VALID，指纹两路一致后重新执行 finish。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（[deploy] 项按云端验足＋p094 顺延口径）
- 测试：全量门禁实数与逐项定性见实施笔记末条；非绿项为叠栈基线继承 3 条（repo_hygiene、fontconfig、t060 既知基线）与负载 flaky 16 errors（复跑全过），均非本 task 引入
- 黑盒：云端无 Docker，e2e/real_engine 未实跑；e2e 全树 collect-only 通过，真实拓扑补验登记 p094
- review：双轴 Round 1 code FAIL / test PASS → 逐项修复 → Round 2 双轴均 PASS、零新 finding，五条 AC 全部 TICK-VALID（见 Review 处置）
- AC 判定：见 `task.md` 行内打勾与实施笔记逐条证据

### 结果摘要

- viewer 握手授权收敛为 Caddy forward_auth → API 边缘解析（AuthService.authorize_viewer 唯一判定）→ 60 秒单 Profile HMAC grant → Gateway 本地验签；Gateway 不再接收会话 Cookie，旧 viewer-authorize 端点与客户端方法已删除；外部 listener 对内部路径 404，Agent register 独立认证不变；CDP 唯一认证自动化入口保留，普通 Profile 响应不泄漏 cdp_ws_path/token，真实引擎 Host/Origin 负向例已备。
- 遗留：p094（合入后本地真实拓扑补验 AC-001/002/004 引擎部分/006）。

### 长期文档闭环

- specs_index：access_control 与 webrtc_remote_display 两行已登记 t064，specs 正文已累积 t064 节。
- 正式 spike s018/s019 均有 report 与采纳结论，后续即 t064；findings 抽取被基线既存编号重复（d037/d038 各两条）阻断，未绕过、未改工具链，结论以 spike 报告与 task.md 回填为据（见实施笔记）。
