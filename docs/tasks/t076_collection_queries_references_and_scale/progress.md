---
tid: "t076"
slug: "collection_queries_references_and_scale"
title: "环境代理集合读模型、引用一致性与规模适配"
status: "done"
branch: "t076_collection_queries_references_and_scale"
worktree: ""
review_level: "full"
review_limit: "8"
verify_limit: "5"
diff_anchor: "0445346773ab1c1152be2cbcfd4357395dc31b20"
spec_source_sha: "0445346773ab1c1152be2cbcfd4357395dc31b20"
depends_on: ""
conflicts_with: "t075"
note: "用户已授权13项todo聚合立项、commit与push；只创建backlog，不实施。; budget: review_limit: 5->8; 契约修订后需新一轮审阅"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 创建授权：2026-11-18T00:00:06+08:00，用户要求全部todo按已讨论架构聚合为少量task并commit/push；来源为p119、p121、p122。本条仅登记创建事实，未实施、未验证业务AC。
- 关联spec：docs/specs/profile_management.md、docs/specs/proxy_management.md、docs/specs/runtime_lifecycle.md、docs/specs/runtime_persistence.md、docs/specs/gate_verification.md；执行收尾时登记本tid并同步新契约，保留旧task历史。
- 实施（2026-11-18，云端，owner cloud-muse-20261117）：后端集合页（profiles/proxies/groups collection + candidates + proxies/countries + proxies/{id}/used-by + profiles/runtime-summary）、3-SELECT 引用聚合（`_proxy_reference_map`）、SSE `config_version` 围栏与原地缓存更新；前端两列表页迁到集合端点（每页 50 条、筛选变页重置为 1、翻页器）、`SessionEntryPage` 与 `EnvironmentSwitcher` 改读批量摘要、`ProxyUsedByPopover` 按需读明细。OpenAPI 重导出 + `npm run generate:api`。
- 关键决策：
    - 每个 Profile 建库即有一条 runtime 行，故当前代理等于绑定版本代理时 kind 为 `both`（不是 `current`）；“current-only” 夹具须先无代理创建再改绑。
    - 摘要条目补齐列表行渲染所需的全部字段（启停/预览捕获时间、失败计数、`updated_at`），列表不再逐行读 runtime；`preview_captured_at` 未被静默丢弃。
    - 代理国家筛选值改为稳定国家代码（选项由 `GET /proxies/countries` 提供）；旧 URL 参数 `country=<国家名>` 不再匹配——零兼容口径下的有意变更，测试已改用代码。
    - 代理列表默认按名称排序（服务端 `default`）；批量测速只覆盖当前页（页面不再加载全量）。
    - 表头全选为当前页语义；批量操作目标仍按稳定 ID。
    - `GroupManagerDialog` 只用一次全量 profiles 查询计数组内数量、无逐环境 runtime 扇出，不在本 task 改动范围。
    - 响应模型中语义必填的集合字段（`ProxyUsedByResponse.entries`、`RuntimeSummaryResponse.entries`、`ProxyCountryRange.cities`）去掉 `default_factory`——带默认值的字段会从 OpenAPI `required` 掉落，生成的前端类型变成可选，调用方被迫重复判空；`CollectionPage.items` 与 `RuntimeSummaryEntry` 的可选字段保留默认值，前端已用 `??` 防御。
    - `docs/blueprint/testing.md` 的 `uv run` 导出命令缺 `httpx`（应用导入链依赖），已补 `--with httpx`；导出以 gate venv 为准。
- 验证（实数）：
    - 后端：`tests/unit/test_t076_collection_queries.py` 12 通过（含新增 1000 规模矩阵：1000 代理/100 绑定运行行下 `list_proxies` SELECT 数 ≤8，与 20 代理规模相等；1000 环境分页 10×100 无重复遗漏，末项搜索与候选命中）、`tests/integration/test_t076_collection_api.py` 5 通过（真实 TestClient + 登录/CSRF）。
    - 前端：`EnvironmentListPage.test.tsx` 28、`ProxyListPage.test.tsx` 26、`SessionEntryPage.test.tsx`、`useProfilesQuery.test.tsx`、`useProfilesQuery.control.test.tsx`、`EnvironmentSwitcher.test.tsx` 合计 73 通过；`npm run test:types` 通过。
    - 旧测试 `useProfilesQuery.test.tsx` 中断言 SSE 后重取的用例已按 TDD 铁律整体删除，改为断言原地更新且不重取；`EnvironmentListPage` 的 SSE 用例改为写摘要缓存（页面现读摘要）。
    - 全量门禁（`scripts/run_gates.sh`，日志 `~/workspace/cloud-task-logs/t076_gates.log` + `t076_gates_rest.log`）：protocol drift / requirements / contract（388 通过、1 跳过）/ design lint / design check / frontend build 全部通过；integration 220 通过、0 失败、7 跳过（引擎缓存/Xvfb 缺失，云端预期）；unit 2204 通过、1 跳过，4 失败 + 10 错误均为干净主干同款基线（t063/t068，Mac 绝对路径与引擎产物缺失，已在 0445346 上复跑确认同为 4 失败 + 10 错误）；frontend 670/670 通过。单条命令的门禁因 unit 基线失败而 fail-fast，未跑完 integration/frontend，故后几项按门禁同一命令逐项补跑并留证。
    - 门禁在云端跑通的前置处理（均不改动门禁本身）：worktree 缺 gate venv，`uv` 须在 PATH 内；Selkies wheel 缓存指主仓已有文件（SHA256 与预期一致）；按门禁提示从上游源码本地构建 jpeginfo v1.7.1（libjpeg-turbo 2.1.5.1 头文件 + 静态库）进 worktree `.scratch/jpeginfo`，门禁自检 d040 契约通过；`gate_container_cleanup.py` 在无 Docker 时返回 1 且 `run_gates.sh` 在 `set -e` 下直接退出，故以后续套件改用 `CBROWSER_GATE_ENV_READY=1` + 已备好的 venv 跑（`CBROWSER_GATE_RUNS_DIR` 不设，清理短路为 0；该变量只被清理脚本消费，各套件命令与门禁一致）。
    - 门禁发现的两处回归均已修并重验：(1) `ProfileRuntimeStatusEvent` 新增 `config_version` 使 `test_api_models_and_sse.py` 的全量 dump 断言失败——期望字典补 `"config_version": 1`（字段本身是 t076 交付）；(2) `AppLayout.shell.test.tsx` 的 coordinator 横幅用例仍走逐环境 `getRuntime`——改为写摘要缓存并断言 `getRuntimeSummary` 只调用 1 次。
    - 返修重验（2026-11-18，Round 1 10 条 finding 修复后，全量门禁 evidence4，日志 `~/workspace/cloud-task-logs/t076_fix_gates_rerun3.log`，证据 `.scratch/t076_fix_evidence4/`）：protocol drift / requirements / contract（388 通过、1 跳过）/ design lint / design check / frontend build 通过；unit 2208 通过、1 跳过，5 失败 + 10 错误（逐项归因见收尾报告）；integration 210 通过、7 跳过，3 错误（同文件时序 flaky）；frontend 673 通过、1 失败（ConfigTab 5000ms 超时 flaky，单跑 3/3 通过；手动全量 `npm test` 674/674 通过，日志 `/tmp/t076_frontend_manual.log`）。门禁环境绕法：`ensure_jpeginfo` 优先取系统 /usr/bin/jpeginfo 并把 /usr/bin 顶到 PATH 最前，盖住 Node 26；重跑前把 worktree `.scratch/jpeginfo` 顶到 PATH 最前，使 which 先命中缓存二进制——未改门禁本身，工具链 PATH 排序缺陷已报主会话定夺。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

- Round 1（2026-11-18，reviewer_focus 代码 + 测试，verdict 均为 FAIL，`reviewed_scope` 76c92b68bd25644a）：AC-001–AC-007 已按流程全部撤回未勾选，修复后重验再打勾。

|finding_id|status|fix_ref|说明|
|---|---|---|---|
|t076_code_f001|已修||`useProfileEventsSync` 的摘要更新与单环境运行缓存解耦——围栏改读两份缓存中现有的那份（运行缓存优先、摘要条目兜底），围栏通过即更新摘要；运行缓存仅在已存在时同步更新，仍不从事件合成运行条目。新增测试：无运行缓存时事件仍更新摘要、运行缓存保持未合成、旧版本事件不覆盖新摘要。|
|t076_code_f002|已修||事件合并复制 `last_started_at`/`last_stopped_at`（缺失保留旧值），`changed` 比较纳入两字段；摘要映射同步复制 `failure_count`、`restart_blocked`、`last_started_at`、`last_stopped_at`、`preview_captured_at`、`updated_at`；预览事件同样原地更新摘要条目（捕获时间不倒退）。新增测试：纯时间事件进两份缓存、预览事件进摘要且不倒退。|
|t076_code_f003|已修||新增 `invalidateProfileLists`/`invalidateGroupLists`/`invalidateProxyLists`（列表键 + 集合键前缀双失效），全部变更路径与 SSE 引用事件处理（含 `useGroupReorder`）改走 helper；旧测试的失效断言仍以底层 `invalidateQueries` 调用核对。|
|t076_code_f004|已修||`proxy_country_ranges` 改为按 `_latest_observation_geo_subquery()`（最新且仍有效）的行聚合，与筛选侧同一口径。旧测试 `test_proxy_country_ranges_from_observations` 的单代理三地观测语义被新口径废止（每代理只贡献最新一处），已按 TDD 铁律整体重写为每代理一观测并写明理由；新增过期 ok 观测排除测试及筛选一致性断言。|
|t076_code_f005|已修||`_proxy_used_by*` 四个 helper 接受已算好的引用映射；`proxy_impact`、`update_proxy`（重放/连接变更/回滚三路）同一会话内只算一次映射。新增 SELECT 计数测试：`proxy_impact` 恰 3 条 SELECT。|
|t076_code_f006|已修||集合页行自带 `group_name`/`group_color`/`proxy_name`（服务端按页两条 `IN` 查询批量查名）；列表页筛选下拉与移动分组菜单改读有界候选（首 50 条 + 已选值单读回显，新增 `GET /api/v1/groups/{id}`）；入口页改读集合页（`status=running`，页大小 100）并保留“仅 running、不含 starting”的语义。OpenAPI 重导出 + `npm run generate:api`。|
|t076_code_f007|已修||新增 `_escape_like`（转义 `\`/`%`/`_`），六处 `ilike` 搜索点（环境/代理/分组集合页与候选接口）全部带 `escape="\\"`。新增通配符字面匹配测试。|
|t076_test_f001|已修||`created` 排序测试给两行可区分的 `created_at`，断言确切顺序（后建的先出）。|
|t076_test_f002|已修||候选断言抽成独立测试 `test_proxy_candidates_find_last_item_bounded`，游离 docstring 已删。|
|t076_test_f003|已修||新增 hook 级断线重连用例——卸载/重挂 `useProfileEventsSync`，重连快照后重放事件，断言摘要最终一致且 `getRuntimeSummary` 不被多余调用。|
|t076_code_f008|已修||后端集合端点新增精确状态 `running_exact`（仅 `observed_state="running"`；`running` 桶仍为 running+starting，供列表筛选）；入口页改读 `running_exact` 并新增 `useAllProfilesCollectionQuery` 逐页走访至服务端总数（空页兜底防死循环），不再假设一页即全部。新增测试：仓储 `running_exact` 排除 starting、HTTP 层同口径、入口页 105 running + 10 starting（桶 115 行）全部 105 行出现且无 starting 行。|
|t076_code_f009|已修||SSE 围栏改为每份缓存各自围栏：事件版本低于某份缓存版本、或同版本实例不同时，只跳过那份缓存、仍可更新另一份；`mergeShared` 的 `config_version` 按每份缓存各自取 `event.config_version ?? base.config_version`。新增混合版本双向测试：runtime v1/summary v2 时迟到 v1 事件只动 runtime、不倒退摘要；runtime v2/summary v1 时迟到 v1 事件只动摘要、不碰 runtime。|

- Round 2（2026-11-18，reviewer_focus 代码，verdict FAIL，`reviewed_scope` d2c4842386bbbb51）：AC-001–AC-007 已按流程再次全部撤回未勾选，修复后重验再打勾；AC-008 仍未勾（p126 待 Mac 补验）。

- Round 3（2026-11-18，reviewer_focus 测试，verdict FAIL，`reviewed_scope` 4945cf0e4ab78b2b）：AC-001–AC-007 已按流程再次全部撤回未勾选，修复后重验再打勾；AC-008 仍未勾（p126 待 Mac 补验）。本轮只加测试、不改生产代码；两处新增用例均做过变异红灯验证（生产代码已还原）。

|finding_id|status|fix_ref|说明|
|---|---|---|---|
|t076_test_f010|已修||新增用例 `treats a version-less SSE event as current for both caches`（`useProfilesQuery.test.tsx`）：两份缓存均预置 config_version 2 / inst-2 / running，发送无 `config_version` 的 stopped 事件，断言两份缓存均按“视为当前”更新为 stopped、config_version 保持 2、running_count 归 0。事件以 `as ProfileRuntimeEvent` 构造：生成类型里该字段为必填（`cbrowser_v1.d.ts:1627`；finding 所引 :2011 实为 SessionResponse 的同名字段），但线上传输是原始 JSON（`parseProfileRuntimeEvent` 作 `raw as` 强转），无版本事件是真实输入，故 cast 只构造线形输入、未 mock 被测围栏/合并逻辑。红灯验证：围栏 `event.config_version ?? cached.config_version` 改为 `?? 0` 后该用例失败、其余 15 通过，生产代码已还原。|
|t076_test_f011|已修||新增用例 `lists every running environment when the total is exactly one page`（`SessionEntryPage.test.tsx`）：100 个 running 环境、0 个 starting，断言 `listCollection` 恰好调用 1 次且 100 行全部出现（含末行 p-run-099）；现有 f008 用例的调用次数断言由 `>= 2` 收紧为恰好 2 次。红灯验证：逐页终止条件 `>=` 改为 `>` 后新用例失败、其余 3 通过，生产代码已还原。|

- AC-008 处置（2026-11-18，用户裁定）：用户明确裁定「云端把所有 task 能做的全部做完；云端做不了的记录 pending、留待本地统一做；不要在 [deploy] AC 上阻塞，就当它做完了、直接打勾」。据此 AC-008 已在 task.md 打勾，此勾为用户裁定的流程处置、**非已实测通过**；实际验证（真实环境经完整 API/SSE/Browser 链路改状态与代理配置后列表/计数/绑定一致、重连可恢复）留待本地统一补验，跟踪项 p126（`docs/pending/p126_t076_ac008_real_runtime_chain_verification.md`，status todo）。Round 1–4 审阅文件的 verdict 与 AC-008 TICK-VOID 原文不改，本处置经 Round 5 审阅复核。

- AC-008 契约修订（2026-11-18，主会话已定机制）：Round 5 代码审阅判定 AC-008 仍 TICK-VOID，理由是契约文字规定打勾＝实施验证通过、[deploy] 须真实链路留证，而契约文字未修订（reviewer 同时确认该勾有用户裁定为据、非擅自变更）。据此把裁定写进契约本身：task.md 契约区已新增「[deploy] AC 打勾处置注记（契约修订，2026-11-18）」——[deploy] AC 打勾语义修订为「云端可做部分已完成、按用户裁定视为流程完成，非已实测通过」，AC-008 验证内容原文一字未改，真实验证延期 p126 本地补验且仍须真实拓扑留证。`review_limit` 经 `task.py limits` 由 5 提高至 8（理由：契约修订后需新一轮审阅），后续轮次按修订后契约重新判定。

- AppLayout TDD 合规核查（主会话追加要求，2026-11-18）：`AppLayout.shell.test.tsx` 的 `getRuntime` 调 2 次 → `getRuntimeSummary` 调 1 次改动已独立核对，合规——产品代码 `useRuntimeSnapshot.ts` 本 task 已由逐环境 `getRuntime` 改为批量摘要，旧断言正是 AC-002 明文禁止的行为（“不再按每个环境发起 runtime HTTP 请求”），旧语义因新契约失效；用例按新契约整体重写（同一断言意图：横幅由 SSE 驱动数据呈现），理由写进 mock 与用例处两处注释，test 审阅者亦独立认定 spec 驱动。无需 revert。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：Round 1 10 条 finding、Round 2 2 条 finding（f008/f009）与 Round 3 测试轴 2 条 finding（f010/f011）均已修并重验，AC-001–AC-007 重新打勾；[deploy] AC-008 云端不可验，按用户 2026-11-18 裁定视为完成打勾（流程处置，非实测通过），实际验证留待本地统一补验，已登记 p126
- 返修重验（Round 3，2026-11-18，f010/f011 修复后，仅受影响文件，未重跑全量门禁——本轮不改生产代码，evidence5 全量门禁结论仍有效）：后端 `tests/unit/test_t076_collection_queries.py` + `tests/integration/test_t076_collection_api.py` 24/24 通过（gate venv pytest，52.69s）；前端 `useProfilesQuery.test.tsx` 16/16（含新增 f010 用例）+ `SessionEntryPage.test.tsx` 4/4（含新增 f011 用例），共 20/20 通过（Node 26.13.0）；`npm run test:types` 通过。两处新增用例均做过变异红灯验证（f010：围栏 `??` 改 `?? 0` 则用例失败；f011：终止条件 `>=` 改 `>` 则用例失败），生产代码已还原、无改动。
- 返修重验（Round 2，2026-11-18，f008/f009 修复后，全量门禁 evidence5，日志 `~/workspace/cloud-task-logs/t076_fix_gates_round2_fix3.log`，证据 `.scratch/t076_fix_evidence5/`）：protocol drift / requirements / contract（388 通过、1 跳过）/ design lint / design check / frontend build 通过；unit 2210 通过、1 跳过，4 失败 + 10 错误（t063 2 失败 + 10 错误、t068 2 失败，干净主干 0445346 同文件复跑逐项一致：同一 4 失败 + 10 错误，老基线，无新回归；a16 本轮通过——worktree 前端 node_modules 已按主会话决定恢复为 npm 风格，与主干一致）；integration 210 通过、7 跳过，0 错误；frontend 677 通过、0 失败（含新增 f008/f009 用例 4 个）。门禁环境问题（均不改门禁本身）：(1) 首轮重跑中途 /tmp（512M tmpfs）写满（ENOSPC 525 处 unit / 219 处 integration），unit/integration 大面积失败——已清 /tmp 陈旧项（`tmp.8hgKFA8qJh` 64M 等）并把 TMPDIR 改到磁盘 `~/workspace/gate-tmp-t076`（仓外，避免 contract 的“仓外无 root”测试误判）；(2) 首轮 PATH 缺 `~/.local/bin`，requirements_check（mise 不在 PATH）与 contract（md_kx 不在 PATH，27 失败）失败——补 PATH 后均通过；(3) 第二轮重跑的后台进程在 unit 进行中被 SIGTERM 杀掉，改用 `nohup setsid` 脱离会话重跑后全程跑完。另：首轮重跑暴露我新写 hook 的类型错误（`chunk.items` 可能 undefined），已修为 `?? []`，`npm run test:types` 通过。失败轮证据留存 `.scratch/t076_fix_evidence5_run1_failed/`（日志 `t076_fix_gates_round2_fix.log`），第二轮被杀的半程日志为 `t076_fix_gates_round2_fix2.log`。
- 测试：全量门禁 evidence5（日志 `~/workspace/cloud-task-logs/t076_fix_gates_round2_fix3.log`，证据 `.scratch/t076_fix_evidence5/`）：contract 388 通过/1 跳过；unit 2210 通过、1 跳过，4 失败 + 10 错误为干净主干 0445346 同款老基线（t063/t068）；integration 210 通过、7 跳过、0 错误；frontend 677 通过、0 失败；design lint/check 与 frontend build 通过。Round 6 审阅双轴独立重跑：后端 t076 两文件 24/24、前端受影响文件 85/85、`test:types` 通过。失败逐项归因见下行。
- 测试（返修后实数，evidence4 + 手动补跑）：后端 `tests/unit/test_t076_collection_queries.py` 17/17 通过（含新增 5 用例）、`tests/integration/test_t076_collection_api.py` + `test_api_models_and_sse.py` 8 通过；前端受影响文件 48/48、宽集 57 文件 477 通过；`npm run test:types` 通过；全量门禁 `scripts/run_gates.sh`（`CBROWSER_GATE_ENV_READY=1`，日志 `~/workspace/cloud-task-logs/t076_fix_gates_rerun3.log`，证据 `.scratch/t076_fix_evidence4/`）：contract 388 通过/1 跳过；unit 2208 通过/1 跳过/5 失败/10 错误；integration 210 通过/7 跳过/3 错误；frontend 673 通过/1 失败；design lint/check 与 frontend build 通过。失败逐项归因：unit——t063 2 失败 + 10 错误与 t068 2 失败为老基线（干净主干 0445346 同文件复跑：同一 4 失败 + 10 错误）；a16 1 失败为 worktree 环境（主干通过；worktree 里 `node <cli>` 对 0445346 原版 schema 同样失败——pnpm 11 生成的 shell shim 不能被 node 直接执行，主干 node_modules 为 npm 风格 JS 软链）；integration——3 错误全在 `test_normal_exit_replay.py`，均为 fixture setup“隔离 API 子进程 10 秒未就绪”，同文件在主干 4/4 通过、在 worktree 单跑时有时通过有时 error，属 CPU 争用下时序 flaky，与 t076 改动无交集；frontend——1 失败为 `ConfigTab.test.tsx` 保存用例 5000ms 超时，该文件不在本次改动内（最后改动 t058），单跑 3/3 通过（该用例 785ms），手动全量 `npm test` 674/674 通过。门禁环境问题：`scripts/ensure_jpeginfo.py` 候选顺序为系统二进制优先，`run_gates.sh` 的 `ensure_jpeginfo` 把其所在目录 /usr/bin 顶到 PATH 最前，盖住已准备好的 Node 26，导致 frontend_test/frontend_build 在 check:node 被拦（24.22.1）；重跑时按主会话办法把 worktree `.scratch/jpeginfo` 顶到 PATH 最前，使 which 先命中缓存二进制，frontend_build 随即通过——未改门禁本身；工具链 PATH 排序缺陷（系统候选优先 + 无条件顶 PATH 最前）报主会话定夺。
- 黑盒：云端无 Docker/Chrome/GPU，真实链路验证（AC-008）登记 p126，不在云端门禁内
- review：full 级；Round 1–4 共 14 条 finding 全部已修并重验消除；Round 5 代码轴因 AC-008 契约文字未修订判 TICK-VOID；契约修订（见上「AC-008 契约修订」条）后 Round 6 双轴均 PASS、0 条新 finding，AC-001–AC-007 TICK-VALID（re_verified），AC-008 按修订后契约判 TICK-VALID（处置型，非已实测通过，真实验证待 p126 本地补验闭环）；review-status overall=PASS
- AC 判定：见 `task.md` 行内打勾；创建时全部未勾选

### 结果摘要

- t076 交付：服务端集合页 + 批量运行摘要 + 3-SELECT 引用聚合 + SSE `config_version` 围栏；两列表页、入口页与切换器全部改读集合端点，不再逐环境扇出 runtime 请求；1000 规模矩阵实测 SELECT 数恒定。唯一未验项为 [deploy] AC-008（p126）。

### 长期文档闭环

执行finalization时更新关联active spec的tasks清单及本task指定blueprint；创建阶段不提前声明实现或闭环。

- 已更新：5 个 spec 的 `tasks` 清单加 t076（profile_management、proxy_management、runtime_lifecycle、runtime_persistence、gate_verification）及对应 t076 内容节；blueprint `architecture.md`（§5.8）、`domain.md`（集合查询与引用并集）、`frontend.md`（§7/§8/§10）、`testing.md`（0/1/100/1000 矩阵与计数证据，`uv run` 导出命令补 `--with httpx`）。
- 来源 pending p119/p121/p122 创建期已 closed（转办至本 task），实现完成即为闭环，无需再动。
