# Task review t069（reviewer_focus: 代码）

- task：`t069_strict_control_contracts`
- spec：`docs/tasks/t069_strict_control_contracts/task.md`
- diff_anchor：`501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90`
- target：`git -C '/home/hatch/workspace/CBrowser_t069' diff 501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90`
- round：1
- reviewed_at：2026-11-14T05:57:07+08:00

reviewed_scope: a38f0719a1a0bd19

## Findings

### t069_code_f001 - task.md 全部 AC 未打勾，验收声明缺失，与实施完成自述矛盾

- 严重度：important
- 锚点：AC-001、AC-002、AC-003、AC-004——契约要求实施验证通过后由实施 Agent 在 task.md 就地打勾（`- [x]`），未打勾按未完成处理
- 位置：`docs/tasks/t069_strict_control_contracts/task.md:37-40`
- 问题：交付状态下 task.md 四条 AC 全部仍为 `- [ ]`（本 reviewer 直接读取 task.md 原文核实）。其中 AC-003 是 [deploy]、实施侧明确不打勾并顺延 p095，尚有依据；但 AC-001/AC-002/AC-004 在 progress.md 中被记为「实施完成」「门禁终局」且收尾报告模板写明「AC 判定：见 task.md 行内打勾」，实际却无任何一条打勾。结果是：按契约口径，本 task 没有任何一条 AC 被实施侧声明完成，验收结论无从成立，review 无法 PASS。实现层本身经本轮独立复验大体真实（见 AC 复验方式），缺的是打勾这一验收动作与其依据的一致性。
- 建议：实施侧按真实验证状态逐条处理：AC-001/AC-002/AC-004 若确已验证通过则在 task.md 就地打勾后重新派审；AC-003 保持未勾并在 progress.md 明确写清其余三条与 AC-003 的打勾口径差异（当前 progress 只交代了 AC-003 不打勾，未交代其余三条为何也不打勾）。

### t069_code_f002 - Finalization 清单中的 docs/blueprint/testing.md 未更新

- 严重度：minor
- 锚点：文档与规格一致性——task.md「Finalization 时更新的 blueprint」列明 `docs/blueprint/security.md、docs/blueprint/testing.md、docs/blueprint/decisions.md：归属与输入拒绝策略`
- 位置：`docs/tasks/t069_strict_control_contracts/task.md`（Finalization 节）与本轮 diff（无 testing.md 改动）
- 问题：diff 实际更新了 conventions.md、architecture.md、security.md、decisions.md 与 specs/spec_index，但未触及清单中的 `docs/blueprint/testing.md`；progress.md 的「文档闭环」自述清单同样未含 testing.md，与 task.md 的 Finalization 清单不一致。归属与输入拒绝的测试口径（如「缺失身份夹具须断言失败、不得用 mock 替代 [deploy] 验收」）未沉淀到长期测试蓝图，后续 task 可能重新引入被本 task 废止的旧夹具口径。
- 建议：在 testing.md 补一段 t069 严格契约的测试口径（非规范响应负矩阵、归属负矩阵、存量 launch_args 拒绝断言、[deploy] 项不可 mock 替代），或在 progress.md 说明 testing.md 无需更新的理由并同步修正 task.md 清单口径。

## 结论

- 本轮新发现：2 条（1 important、1 minor）
- 未进表的提示：
    - 文件过大（按降级规则仅提示，不进 finding 表）：本 task 触及的多个存量实现文件本身已超阈值——`src/backend/cbrowser/supervisor/core.py` 3223 行、`docker_adapter.py` 2682 行、`adapters/database/repository.py` 1950 行、`api/runtime_coordinator.py` 1298 行、`agent_executor/session.py` 1016 行、`domain/models.py` 930 行、`scripts/deploy.sh` 1131 行；本 task 对这些文件多为净减或小幅净增，未见由本 task 新堆出的单文件膨胀缺陷。`src/frontend/src/features/browser-session/adapter.ts` 现 429 行（≥400 minor 阈值）且本 task 净增 12 行，仅作提示。
    - 圈复杂度：本 task 新增/修改函数（`parse_error_response`、`_downstream_error_text`、`_report_observed`、`_owns_deployment`、`network_ownership_matches`、`run_supervisor` 入口校验、`installSelkiesClientAdapter`）手算 CC 均 \<10，无提示项。
    - 范围外观察：worktree 内 `src/frontend/node_modules` 为指向主仓的未跟踪符号链接（环境产物，非交付文件），不影响本轮指纹判定，提示实施侧收尾时勿将其纳入交付。
    - 七视角扫描确认：安全（viewer 身份收敛、归属凭据单一化均为收紧方向；`parse_error_response` 对外部响应体做类型校验后才取字段，无注入面新增）、契约·Breaking（`network_ownership_matches` 签名删 prefix/name 两参，仓内唯一调用点 docker_adapter.py:1555 已同步；`installSelkiesClientAdapter` profileId 改必填，前端全部调用点均已显式传参，含既有 adapter_restart/adapter_types 测试）、性能·资源（无循环查库、无新增同步 IO 阻塞）、健壮性（gateway 非规范 503 记 warning 并返回 None，不静默吞错）均已扫过，除上表外未命中。
- 总体判断：实现层与契约基本一致——统一解析落点 `src/backend/cbrowser/shared/error_response.py:28-51` 严格校验 error/message 非空字符串与 retryable 为 bool（与服务端 `_http_error_content` 恒产出 retryable 的形状对齐）；三处消费方（runtime_coordinator.py `_downstream_error_text`、gateway_client.py `agent_registered` 503 分支、agent_executor/session.py 409 分支）均已改用该解析并删除 detail/裸文本兜底；core.py `_report_observed` 的 422 去字段重发已删除、单次定论返回 `status_code == 200`；归属三处（network_spec.py:48-61、docker_adapter.py `_owns_deployment`、deploy.sh `check_prefix_conflict` 豁免段）均只认非空 instance-id，runner.py:82-87 的启动校验位于 `docker.from_env()` 之前；`filter_launch_args` 已删除且全仓无残留引用，ProfileConfig 与 repository 加载边界（repository.py `_to_domain_profile`，指名 Profile 的 RuntimeError）均走严格校验；viewer 只剩 `?profileId=` 单通道（SessionPage.tsx:224 宿主页传参、selkies_adapter_entry.ts 拒绝 profile_id/缺失、adapter.ts 拒绝空 id 与全局注入并删除 "default"）；network_config_cli 已删 BIND_HOST/PUBLIC_ORIGIN 且全仓无消费方残留；非范围保持面未动（幂等键三源无 diff、profile_locale 仅 docstring 改述、None 语义保留）。但 task.md 全部 AC 未打勾（f001），按规则四条 AC 均记 TICK-VOID，verdict 必须 FAIL。
- 系统性 follow-up：AC-003 真实 Docker 拓扑验收已有 pending `p095_t069_local_deploy_ownership_verification` 登记顺延本地，本报告不重复建项；其余无。

### AC 复验方式

- AC-001：TICK-VOID，re_verified。task.md 未打勾（- [ ]），按规则打勾不成立；实现层已独立复验：shared/error_response.py 严格解析、三消费方删除 detail/裸文本兜底，定向测试批 122 passed（含 test_t069 parser 负矩阵、coordinator 协议错误标记、gateway 三类 503、agent 409 协议错误）。
- AC-002：TICK-VOID，re_verified。task.md 未打勾；实现层已独立复验：supervisor/core.py `_report_observed` 已无 422 重发分支、422 返回 False 不伪报收敛，test_t069 的 422 单次定论用例与 test_t035 迁移用例在本轮定向批次中通过。
- AC-003：TICK-VOID，trust_prior。task.md 未打勾且为 [deploy]：代码层（network_ownership_matches/\_owns_deployment 只认 instance-id、run_supervisor 在 Docker 客户端构造前拒绝缺失身份、deploy.sh 豁免段删除）已查证，但真实 Docker 拓扑下「无标签资源不被删除、合法资源可恢复清理」云端无 Docker 无法独立复验，只能依赖实施侧证据与已登记的 p095 本地补验。
- AC-004：TICK-VOID，re_verified。task.md 未打勾；实现层已独立复验：filter_launch_args 删除且无残留引用、ProfileConfig 改严格 validate、repository 加载指名拒绝、viewer 单通道三处拒绝逻辑、network CLI 死输出删除且无消费方，定向批次中 test_launch_args/test_profile_launch_args_api/test_t054 与前端 adapter 身份契约（代码查证）均与新口径一致。

coverage = 3 / 4

verdict: FAIL

## Round 2 (2026-11-14T06:06:47+08:00)

- task：`t069_strict_control_contracts`
- diff_anchor：`501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90`
- target：`git -C '/home/hatch/workspace/CBrowser_t069' diff 501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90`

reviewed_scope: d6a502ead0b5dbf2

## Findings

本轮无新 finding（0 条）。全量 diff 回归扫描未发现修复引入的新问题，详见结论段。

## 结论

- 前轮 finding 复核：
    - t069_code_f001（important）：打勾动作部分已消除。`docs/tasks/t069_strict_control_contracts/task.md:28-31` 现为 AC-001/002/004 已勾（`- [x]`）、AC-003 未勾，本 reviewer 直读原文核实，且三条已勾 AC 的实现与证据经本轮独立复验成立（见 AC 复验方式）；AC-003 未勾口径已在 progress.md 实施笔记与收尾报告中写清（[deploy] 不勾、顺延 p095，`docs/pending/todo/p095_t069_local_deploy_ownership_verification.md` 实存且内容覆盖真实拓扑四项补验）。但 AC-003 未打勾按复验规则仍须记 TICK-VOID，故 f001 导致的 FAIL 中仅剩 AC-003 这一项部署顺延因素，不再是打勾缺失的疏漏。
    - t069_code_f002（minor）：已消除。`docs/blueprint/testing.md` 末尾新增「严格契约与归属拒绝验证（t069）」一节（diff +14 行），内容经核实属实：error_response 解析器负矩阵与三处消费方对称用例对应 `tests/unit/test_t069_strict_control_contracts.py` 及三消费方实现（`src/backend/cbrowser/shared/error_response.py:28-51`、runtime_coordinator/gateway_client/session 三处改用统一解析）；observed-state 422 请求计数单次断言对应 core.py 删除重发分支后的实现；归属「先拒绝后零变更」、启动缺身份先于 Docker 失败、repository 指名拒绝均与代码一致；[deploy] 层不以 mock 替代、顺延 p095 的表述与 p095 文件一致。
    - t069_test_f001（important，code 轴视角复核）：已消除（与 code_f001 同因）。AC-001/002/004 已打勾，progress.md 收尾报告已实填（验收与验证、结果摘要、长期文档闭环三节俱在，不再是占位），AC 判定口径与 task.md 行内打勾一致；AC-003 例外同上。
    - t069_test_f002（important）：已消除。身份解析已抽为纯函数模块 `src/frontend/src/features/browser-session/selkies_profile_id.ts:6-20`（`resolveSelkiesProfileId`：出现 `profile_id` 即抛错、profileId 缺失/空即抛错、否则原样返回，与原入口严格逻辑逐字等价、无宽松回退）；`selkies_adapter_entry.ts` 现 9 行只做装配（`resolveSelkiesProfileId(window.location.search)` 直传 `installSelkiesClientAdapter`，无 catch、无兜底）；`adapter_identity.test.ts:104-122` 新增 3 条入口解析用例（仅 profileId 正常、profile_id 单独/混用均抛错、缺失/空抛错）。本 reviewer 独立重跑前端定向三文件 20 passed（其中 adapter_identity 6/6，含新增 3 条）；审阅期间曾观测到该纯函数文件短暂呈现旧宽松实现时新增用例中 2 条即失败、恢复严格实现（850 字节，md5 b4e353639335ef16e0d1f2f5cd329d1d，连续采样稳定）后全绿，说明新增用例真实守卫该逻辑、非假绿。
- 本轮新发现：0 条。全量 diff 回归扫描确认：`parse_error_response` 三消费方无 detail/裸文本残留兜底；core.py 422 重发分支删除干净、单次定论；`network_ownership_matches` 新签名仓内唯一调用点 `docker_adapter.py:1555` 已同步，`_owns_deployment` 未配置返 False，runner.py 身份校验位于 Docker 客户端构造前，deploy.sh 标签缺失豁免段已删；`filter_launch_args` 全仓无残留引用，repository 加载边界指名拒绝；`network_config_cli` 已删 BIND_HOST/PUBLIC_ORIGIN 输出与 `derive_origin_whitelist` import（该函数仍被 api/app.py 与 gateway/config.py 正常使用，非死代码误伤）；viewer 全部 `installSelkiesClientAdapter` 调用点均显式传 profileId；幂等键三源与 locale/timezone None 语义无 diff 触碰。七视角（安全/正确性/契约·Breaking/性能·资源/架构·可维护性/健壮性·可观测/文档·规格）均已扫过，除 AC-003 顺延外未命中。
- 未进表的提示：文件过大沿 Round 1 结论（core.py 3223 行、docker_adapter.py 2682 行、repository.py 1950 行、runtime_coordinator.py 1298 行、deploy.sh 1131 行均为存量超阈值、本 task 多为净减或小增；adapter.ts 429 行仅提示）；新增文件均未超阈值（selkies_profile_id.ts 20 行、error_response.py 51 行、test_t069 353 行）；新增/修改函数手算圈复杂度均 \<10；worktree 内 `src/frontend/node_modules` 未跟踪符号链接为环境产物、非交付文件，沿 Round 1 提示。
- 总体判断：Round 1 的 4 条 finding 处置全部真实成立，无新 blocker；但 AC-003（[deploy]）未打勾，按规则记 TICK-VOID，本轮 verdict 仍为 FAIL——唯一驱动因素是 AC-003 的真实 Docker 拓扑验收尚未完成（云端无 Docker），须待 p095 本地补验通过、AC-003 打勾后另行复审。
- 系统性 follow-up：无。AC-003 补验已有 p095 登记，不重复建项。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。task.md:28 已勾；直读 shared/error_response.py:28-51 严格校验（error/message 非空 str、retryable 为 bool）与三消费方删除兜底属实，本轮独立重跑后端定向批 141 passed（含 test_t069 parser 负矩阵、coordinator 协议错误标记、gateway 三类 503、agent 409 协议错误）。
- AC-002：TICK-VALID，re_verified。task.md:29 已勾；直读 supervisor/core.py `_report_observed` 已无 422 去字段重发分支、422 单次定论返 False，test_t069 422 用例与 test_t035 迁移用例在本轮 141 passed 批次内通过。
- AC-003：TICK-VOID，trust_prior。task.md:30 未打勾（[deploy]），按规则打勾作废；代码层已查证（network_spec.py:48-61 只认非空 instance-id、\_owns_deployment 未配置不认领、run_supervisor 在 Docker 动作前拒绝缺失身份、deploy.sh 豁免段删除），但真实 Docker 拓扑下「无标签资源不被删除、合法资源可恢复清理」云端无 Docker 无法独立复验，只能依赖实施侧证据与 p095 本地补验登记。
- AC-004：TICK-VALID，re_verified。task.md:31 已勾；filter_launch_args 删除无残留、ProfileConfig 严格校验、repository 指名拒绝、viewer 单通道（含本轮新抽 selkies_profile_id.ts 与入口装配直读核实）、network CLI 死输出删除均属实，本轮后端 141 passed 与前端定向 20 passed（含 adapter_identity 新增 3 条入口解析用例）支撑。

coverage = 3 / 4

verdict: FAIL

## Round 3 (2026-11-14T06:27:00+08:00)

- task：`t069_strict_control_contracts`
- diff_anchor：`501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90`
- target：`git -C '/home/hatch/workspace/CBrowser_t069' diff 501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90`

reviewed_scope: 9b0299b2a9e03c58

## Findings

本轮无新 finding（0 条）。本轮唯一实质变更（AC-003 打勾 + progress.md 裁定段与前端数字措辞修正）经复核成立，全量 diff 回归扫描未发现新问题，详见结论段。

## 结论

- 前轮 finding 复核：
    - t069_code_f001（important）：已消除（含本轮补完的 AC-003 部分）。`docs/tasks/t069_strict_control_contracts/task.md:28-31` 现四条 AC 全部为 `- [x]`，本 reviewer 直读原文核实。AC-003 打勾口径与归档先例一致性已独立比对：t062 归档 `docs/archive/tasks/t062_control_plane_boundaries/task.md:30` 的 [deploy] AC-005 为 `- [x]`，其 progress 收尾明确「真实 Docker 构建/readiness 部分按 [deploy] 口径顺延本地，p092 登记」、Round 2 双轴 PASS 且 AC-005 判 TICK-VALID；t064 归档 `docs/archive/tasks/t064_session_auth_cdp_boundary/task.md:29-33` 的 [deploy] AC-001/002/004/006 均为 `- [x]`，progress 明示「云端验足＋p094 顺延口径」、双轴 PASS 且五条 AC 全部 TICK-VALID。本 task 形态与两先例同构：云端可验部分（实现 + fake 层负矩阵 + 启动拒绝 + deploy.sh 静态与 fake-docker 行为覆盖）已完成、真实拓扑部分以 pending 顺延登记并存、progress.md「Review 处置」Round 2 段后裁定段明示「不冒充已验」。故 AC-003 打勾成立，不再记 TICK-VOID。
    - t069_code_f002（minor）：Round 2 已确认消除，本轮 diff 中 `docs/blueprint/testing.md` 的「严格契约与归属拒绝验证（t069）」一节仍在，无回退。
    - t069_test_f001 / t069_test_f002（important，code 轴视角）：Round 2 已确认消除；本轮回归复跑前端 adapter 定向三文件 20 passed（adapter_identity 6/6，含 Round 1 修复新增的 3 条入口解析用例），无回退。
- p095 登记复核：`docs/pending/todo/p095_t069_local_deploy_ownership_verification.md` 实存（未跟踪新文件，`git status --short` 可见），内容覆盖四项补验，与 AC-003 语义逐项对应：(1) 缺失/为空/不匹配 `CBROWSER_INSTANCE_ID` 的存量容器与网络不被 Supervisor 认领或删除；(2) Supervisor 未配置部署身份时于任何 Docker 变更前启动失败；(3) 合法匹配 instance-id 的资源可正常恢复清理（scan/prune/孤儿 helper 清理）；(4) deploy.sh 前缀冲突检查对无标签历史容器不再按 compose project 豁免认领。且明示云端只完成代码与单元/契约层证据、「不能冒充真实部署已验」，与打勾裁定口径一致。
- progress 数字修正复核：收尾报告前端数字现表述为「总量 633：首跑（630 时点）629 绿 + 1 条 flaky；补入口 3 用例后终局复跑 626 绿 / 7 failed，串行复跑该 4 文件 28/28 全过，负载 flaky 定性」。算术自洽（630 + 3 = 633；626 + 7 = 633），与 Round 2 test 轴指出的修正方向（总量 633、非 632）一致；新增 3 条由 adapter_identity 文件独立复跑坐实（6/6，较 Round 1 的 17 passed 恰增 3 至三文件 20 passed，本轮再次复跑 20/20）。终局 7 条表单类失败的串行复跑 28/28 为实施侧复跑证据，本轴未独立重演该批，但其定性（profiles/settings 表单类超时、负载时点）与 Round 1/2 已独立观测到的同类负载 flaky 形态一致，不影响任何 AC 判定。
- 本轮新发现：0 条。全量 diff 回归扫描确认 Round 2 结论无回退：`src/backend/cbrowser/shared/error_response.py:28-51` 严格解析不变；supervisor/core.py 422 分支只余注释与单次定论 `return resp.status_code == 200`（diff 直读核实，无去字段重发）；`network_spec.py:48-61` `network_ownership_matches` 只认非空 deployment_id 与 instance-id label 相等；runner.py 身份校验（空/缺失抛 ValueError）位于 Docker 客户端构造前；deploy.sh `check_prefix_conflict` 的 label 缺失 compose project 豁免段已删除（diff 直读核实）；`filter_launch_args` 全仓仅余 test_launch_args.py:36 的历史说明注释、无实现残留；network_config_cli 无 BIND_HOST/PUBLIC_ORIGIN 输出。本轮独立重跑后端定向批 152 passed（test_t069、test_launch_args、test_runtime_coordinator_error_responses、test_agent_executor_control、test_t035、test_t051、test_t054、test_profile_launch_args_api、test_control_http_clients），前端 adapter 三文件 20 passed。七视角（安全/正确性/契约·Breaking/性能·资源/架构·可维护性/健壮性·可观测/文档·规格）均已扫过，未命中新问题。
- 未进表的提示：文件过大沿前两轮结论（core.py、docker_adapter.py、repository.py、runtime_coordinator.py、deploy.sh 均为存量超阈值、本 task 多为净减或小增；adapter.ts 429 行仅提示）；新增/修改函数手算圈复杂度均 \<10；worktree 内 `src/frontend/node_modules` 未跟踪符号链接为环境产物、非交付文件，沿前轮提示。
- 总体判断：Round 1 的 4 条 finding 全部真实修复，Round 2 遗留的唯一 FAIL 驱动因素（AC-003 未打勾的门禁 TICK-VOID）已按 t062/t064 归档先例补完打勾并保留 p095 顺延登记，口径一致、不冒充真实拓扑已验；本轮 0 新 finding，四条 AC 全部 TICK-VALID，verdict 为 PASS。注意：本 PASS 中 AC-003 的 TICK-VALID 遵循先例的「云端验足 + [deploy] 顺延」口径，明确不表示真实 Docker 拓扑已验——该部分仍待 p095 本地补验闭环。
- 系统性 follow-up：无。AC-003 真实拓扑补验已有 p095 登记，不重复建项。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。task.md:28 已勾；直读 shared/error_response.py:28-51 严格校验与三消费方删除兜底属实，本轮独立重跑后端定向批 152 passed（含 test_t069 parser 负矩阵、coordinator 协议错误标记、gateway 三类 503、agent 409 协议错误）。
- AC-002：TICK-VALID，re_verified。task.md:29 已勾；diff 直读 supervisor/core.py 422 去字段重发分支已删除、单次定论返 False 不伪报收敛，test_t069 422 用例与 test_t035 迁移用例在本轮 152 passed 批次内通过。
- AC-003：TICK-VALID，trust_prior。task.md:30 已勾（[deploy]）；打勾口径与 t062 AC-005（已勾 + p092 顺延、双轴 PASS 判 TICK-VALID）及 t064 [deploy] 四条（已勾 + p094 顺延、双轴 PASS 判 TICK-VALID）的归档先例同构，progress 裁定段明示不冒充已验，p095 实存且覆盖四项真实拓扑补验；云端可验部分已由本轴直读代码（network_spec.py:48-61 只认 instance-id、runner.py Docker 动作前拒绝缺失身份、deploy.sh 豁免段删除）与本轮 152 passed 中的归属负矩阵/\_owns_deployment/run_supervisor/deploy.sh 静态断言用例复验，但真实 Docker 拓扑下「无标签资源不被删除、合法资源可恢复清理」云端无 Docker 无法独立复验，只能依赖实施侧证据与 p095 顺延登记，故记 trust_prior。
- AC-004：TICK-VALID，re_verified。task.md:31 已勾；filter_launch_args 删除无实现残留、ProfileConfig 严格校验、repository 指名拒绝、viewer 单通道、network CLI 死输出删除均属实，本轮后端 152 passed 与前端 adapter 定向 20 passed（含 adapter_identity 6/6）支撑。

coverage = 3 / 4

verdict: PASS

## Round 4 (2026-11-14T06:29:24+08:00)

- task：`t069_strict_control_contracts`
- diff_anchor：`501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90`
- target：`git -C '/home/hatch/workspace/CBrowser_t069' diff 501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90`（本轮以暂存树 `git diff --cached` 为准）

reviewed_scope: 77d365c414ef2b91

## Findings

本轮无新 finding（0 条）。本轮为指纹确认轮：Round 3 PASS（指纹 9b0299b2a9e03c58）后交付文件全部 git add 暂存，finish 门禁按暂存树复算指纹得到新值，旧指纹判 stale；本轮仅按新指纹复核暂存内容与 Round 3 已 PASS 交付的实质一致性，未发现任何代码/测试/契约内容变更。

## 结论

- 前轮 finding 复核：t069_code_f001（important）与 t069_code_f002（minor）维持 Round 3 的「已消除」结论——`docs/tasks/t069_strict_control_contracts/task.md:28-31` 四条 AC 在暂存树中仍全部为 `- [x]`（本轮直读暂存 diff 核实）；`docs/blueprint/testing.md` 的「严格契约与归属拒绝验证（t069）」一节仍在暂存 diff 内，无回退。
- 暂存一致性复核：`git status --short` 为恰 52 个交付文件全部暂存（无未暂存、无未跟踪交付文件）；`git diff --cached 501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90` 共 52 files changed, 1272 insertions(+), 263 deletions(-)。核心实现暂存内容与 Round 3 已验版本逐项一致（本轮 diff 直读核实）：`src/backend/cbrowser/shared/error_response.py:28-51` 严格解析不变；supervisor/core.py 的 422 去字段重发分支删除干净、只余单次定论注释；`network_spec.py` 的 `network_ownership_matches` 只认非空 deployment_id 与 instance-id label 相等、签名删 prefix/name 两参；`launch_args.py` 的 `filter_launch_args` 已删除且全仓无实现残留；`network_config_cli.py` 已删 BIND_HOST/PUBLIC_ORIGIN 输出。本轮所述两处纯措辞/格式订正已核实存在且仅限流程文件：progress.md 收尾报告前端串行复跑表述已订正为「该 5 文件 28/28 全过」（与 Round 3 本轴指出的文件数口径一致）并经 md_kx 格式化；review_test.md 的 Round 2/Round 3「独立重跑记录」小节顺序调整属该报告内部排版，不触及任何实现、测试或契约文件。
- 本轮独立重跑：后端定向批 152 passed（test_t069、test_launch_args、test_runtime_coordinator_error_responses、test_agent_executor_control、test_t035、test_t051、test_t054、test_profile_launch_args_api、test_control_http_clients），与 Round 3 本轴复跑数完全一致；前端 adapter 定向三文件 20 passed（adapter_identity、adapter_restart、adapter_types，含 identity 6/6），与 Round 3 一致。注：暂存后 worktree 内 `src/frontend/node_modules` 符号链接已被移除，本轮为复跑前端定向临时重建该链接指向主仓 node_modules、跑完即删除，`git status` 已恢复为纯 52 文件暂存状态，该链接为环境产物、非交付文件，不影响指纹判定。
- 本轮新发现：0 条。七视角（安全/正确性/契约·Breaking/性能·资源/架构·可维护性/健壮性·可观测/文档·规格）在前三轮已全量扫过且本轮暂存内容无实质变更，未命中新问题。
- 未进表的提示：文件过大与圈复杂度沿 Round 3 结论（存量超阈值文件多为净减或小增、新增/修改函数手算 CC 均 \<10），本轮无变化。
- 总体判断：暂存树与 Round 3 已 PASS 的交付实质一致，差异仅为新指纹所绑定的暂存形态与两处流程文件措辞/格式订正；四条 AC 打勾与判定维持（AC-003 沿 t062/t064 先例口径 TICK-VALID/trust_prior，真实 Docker 拓扑仍待 p095 本地补验、不冒充已验），本轮 verdict 为 PASS。
- 系统性 follow-up：无。AC-003 真实拓扑补验已有 p095 登记，不重复建项。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。task.md:28 在暂存树中已勾；暂存 diff 直读 shared/error_response.py:28-51 严格校验与三消费方删除兜底与 Round 3 已验内容一致，本轮独立重跑后端定向批 152 passed（含 test_t069 parser 负矩阵、coordinator 协议错误标记、gateway 三类 503、agent 409 协议错误）。
- AC-002：TICK-VALID，re_verified。task.md:29 在暂存树中已勾；暂存 diff 直读 supervisor/core.py 422 去字段重发分支已删除、只余单次定论注释，test_t069 422 用例与 test_t035 迁移用例在本轮 152 passed 批次内通过。
- AC-003：TICK-VALID，trust_prior。task.md:30 在暂存树中已勾（[deploy]）；维持 Round 3 先例口径——打勾与 t062 AC-005（已勾 + p092 顺延、双轴 PASS 判 TICK-VALID）及 t064 [deploy] 四条（已勾 + p094 顺延、双轴 PASS 判 TICK-VALID）同构，p095 在暂存树中实存（52 文件之一）且覆盖四项真实拓扑补验，progress 明示不冒充已验；云端可验部分经本轮暂存 diff 直读（network_spec.py 只认 instance-id、runner.py Docker 动作前拒绝缺失身份、deploy.sh 豁免段删除）与 152 passed 中归属负矩阵用例复验，真实 Docker 拓扑云端无 Docker 无法独立复验，只能依赖实施侧证据与 p095 顺延登记，故记 trust_prior。
- AC-004：TICK-VALID，re_verified。task.md:31 在暂存树中已勾；暂存 diff 直读 filter_launch_args 删除无实现残留、network CLI 死输出删除属实，viewer 单通道与 repository 指名拒绝与 Round 3 已验内容一致，本轮后端 152 passed 与前端 adapter 定向 20 passed（含 adapter_identity 6/6）支撑。

coverage = 3 / 4

verdict: PASS
