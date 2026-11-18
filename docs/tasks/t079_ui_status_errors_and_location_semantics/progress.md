---
tid: "t079"
slug: "ui_status_errors_and_location_semantics"
title: "全站状态错误文案与代理地区呈现统一"
status: "done"
branch: "t079_ui_status_errors_and_location_semantics"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "a8c916410d2e470de38d18c0c2e450a487ab1036"
spec_source_sha: "dffadb298c123ae77a8e8b1f224731ba59030076"
depends_on: "t076"
conflicts_with: "t075,t077,t078"
note: "用户已授权13项todo聚合立项、commit与push；只创建backlog，不实施。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 创建授权：2026-11-18T00:00:06+08:00，用户要求全部todo按已讨论架构聚合为少量task并commit/push；来源为p113、p115、p123。本条仅登记创建事实，未实施、未验证业务AC。
- 关联spec：docs/specs/ui_design_system.md、docs/specs/profile_management.md、docs/specs/proxy_management.md；执行收尾时登记本tid并同步新契约，保留旧task历史。
- 实施（2026-11-18，云端，基线为 t078 finish a8c9164）：新建唯一呈现语义来源 `src/frontend/src/shared/presentation.ts`，三类映射集中于此，全站消费方收敛：
    - 环境状态：`environmentStatusDescriptor`（running/starting/stopping/error/stopped + 显式 unknown）。消费方：EnvironmentTable（原 STATUS_MAP 删除、statusDescriptor 改为共享映射再导出）、EnvironmentCard、ProfileDetailPage、EnvironmentSwitcher.currentStatus、SessionHeader.observedStatus、ProfileAutomationTab（原 stateTone 与 raw enum 直出删除）、SessionEntryPage 与状态筛选改用 status\* 词条。runtime 缺失/枚举外值呈「未知」，不再回落「已停止」。
    - 测速错误：`proxyProbeErrorLabelKey` 覆盖后端可达的全部机器码（probe_failed、probe_bad_response、supervisor_unavailable、proxy_credentials_unavailable、echo_unreachable、echo_proxy_unsupported、invalid_echo_response、geoip_lookup_failed 及存量 proxy_auth_failed、proxy_unreachable），未知/缺失回退 proxyProbeFailed。消费方：ProxyTable、ProxyListPage 卡片、ProxyFormDialog、SessionDetailsPanel；主状态只呈本地化说明，机器码保留在 title 作诊断。
    - 地区呈现：共享 `RegionBadge`（国旗 + 名称）替代 `RegionCode` 字母徽标，未知代码呈 Globe 占位 + regionUnknown 可访问名；消费方 ProxyTable、ProxyListPage 卡片、ProxyFormDialog。国家候选按规范英文名（Intl.DisplayNames en）排序、按代码去重；城市按同一 CLDR collator 规则排序去重；筛选身份始终是国家代码，「全部」固定首位（工具栏既有行为）。
    - 工作台下拉（AC-003）：EnvironmentSwitcher 各项移除右侧 StatusBadge，只留前置状态点 + 名称，状态以 aria-label 与 sr-only 文本承载；顶栏环境徽标改用共享短文案（运行中/Running），传输徽标保留带主语文案（数据传输正常/Data Ready）与之区分。
    - i18n 清理：删除与 status\* 完全重复的 sessRunning/sessStopped、envFilterRunning/envFilterStopped/envFilterError 与顶栏专属 sessHeaderEnv\* 五键（中英各 10 键）；新增 statusUnknown、regionUnknown 与 9 个 proxyError\* 键（中英齐全，i18n.test 键集合校验通过）；en 词典中文残留扫描仅 languageZh 本名一处（正当）。
- 测试：新增 `src/shared/presentation.test.ts` 10 条（状态映射含未知回退、错误码全集与兜底、国旗有效性、国家英文名排序与去重、城市排序稳定性）。旧语义测试整体替换并注明依据：ProxyListPage 三条（字母代码断言→国旗断言、筛选选项标签→国旗+名称、原始错误码直出→本地化说明 + title 保留机器码）、SessionHeader 四条（带主语长文案→共享短文案、runtime 为空回落 stopped→显式未知）、EnvironmentSwitcher/SessionEntryPage 各一条（sessRunning 键收敛 + 新增 aria-label 状态断言）。类型检查（tsc test 配置）通过。
- 门禁：见收尾报告（全量 run_gates 与基线对照）。
- Round 1 审阅修复后复验（2026-11-18）：前端全量 vitest 85 文件 697 条全过（修复前 693 条中 1 条负载超时 flaky，本轮全过）、test:types 通过；presentation 单测增至 12 条、ui 单测增至 16 条（含 RegionBadge 占位分支）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

Round 1（2026-11-18）：general 轴 FAIL 3 条（important 1、minor 2），AC-005 判 TICK-VOID，其余 AC TICK-VALID。全部 AC 一度撤回打勾，逐项修复后重验再打勾，进入 Round 2 复审。

|finding_id|status|fix_ref|说明|
|---|---|---|---|
|t079_gen_f001|已修|-|（important）格式合法但未分配/未知哨兵代码（XX/ZZ/AA）仍被拼出伪造国旗。修：新增 `isKnownRegion`——以 CLDR 规范名为准（DisplayNames 结果等于代码本身或为 "Unknown Region" 即未知），`regionFlagEmoji` 与 RegionBadge 占位分支、筛选标签均改走该判定；`regionEnglishName` 对未知代码回退代码本身作排序键。补测：presentation 新增未分配代码用例、ui.test 新增 RegionBadge 占位分支用例（断言不出现 🇽🇽）|
|t079_gen_f002|已修|-|（minor）排序比较器内每次比较新建 Intl.DisplayNames。修：DisplayNames 改模块级单例（en）与按 locale 缓存（regionDisplayName），`sortCountryCandidates` 排序前为每个代码预算一次英文名再比较|
|t079_gen_f003|已修|-|（minor）非拉丁城市排序测试未断言汉字相对顺序。修：新增用例断言 CLDR root 规则下的 上海 < 东京 < 北京 并注明规则依据与 ICU 升级时的复核要求|

Round 1 时的 AC 判定原文保留在 review_general.md，不改写。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：云端可做部分全部完成（本 task 无 [deploy] AC，6 条 AC 均以云端门禁与测试证据打勾）
- 测试：全量门禁（日志 ~/workspace/cloud-task-logs/t079_gate3.log＋.scratch/t079_gate_evidence3/）：protocol_drift_check、requirements_check、design_lint、design_check、frontend_build 均 exit 0；contract 388 过/1 跳；unit 2226 过、4 失败/10 错误与 t076/t078 基线逐项一致（t063×2 失败＋t063 built 系列 10 错误依赖本机外构建产物路径、t068×2 失败）；integration 213 过/7 跳、4 错误均为隔离 API 就绪窗口负载 flaky（test_normal_exit_replay×2、test_supervisor_observation_authority、test_supervisor_manual_retry，逐条单跑全过）；frontend 692 过/1 失败（ProxyListPage 列展示用例 5000ms 负载超时，单跑 582ms 通过）。相对基线无新增失败；新增 presentation 单测 10 条全过。前两轮门禁失败均为环境问题（gate venv 缓存缺失、jpeginfo 断链、Node 24 回落），已按既有配方修复后重跑，非交付问题。
- 黑盒：本 task 为纯前端呈现语义统一，无 [deploy] AC；真实浏览器长名称/窄窗口目视检查未在云端执行（无真实浏览器拓扑），组件级断言已覆盖下拉去徽标与可访问状态，余目视项不阻塞本 task 契约（AC 均可自动测试，见 task.md 可测试性声明）。
- review：Round 1 general 轴 FAIL（3 条：f001 important 未分配国家代码伪造国旗、f002 minor DisplayNames 重复构造、f003 minor 非拉丁排序断言缺失）→ 全部修复并写入 Review 处置表 → Round 2 复审（见 review_general.md 最新轮次）
- AC 判定：见 `task.md` 行内打勾；AC-001–AC-006 依共享映射单测、组件测试与全量门禁证据

### 结果摘要

- 全站呈现语义收敛为单一来源 `src/shared/presentation.ts`：环境状态（含显式未知）、测速错误码→本地化说明、地区国旗/名称与候选排序三套映射全站共用；字母代码徽标、原始错误码直出、各页面自维护状态文案与重复 i18n 键全部删除。工作台下拉去掉右侧重复徽标（状态点 + 可访问文本承载状态），顶栏环境徽标与列表/卡片同词，筛选身份始终是国家代码且排序与接口顺序、界面语言无关。

### 长期文档闭环

执行finalization时更新关联active spec的tasks清单及本task指定blueprint；创建阶段不提前声明实现或闭环。
