# Task review t094（reviewer_focus: 代码）

- task：`t094_egress_probe_subsystem_root_refactor`
- spec：`docs/tasks/t094_egress_probe_subsystem_root_refactor/task.md`
- diff_anchor：`b1f979ba5e7ea2ee3a1bfb22d9d5d52703834434`
- target：`git diff b1f979ba5e7ea2ee3a1bfb22d9d5d52703834434`
- round：5
- reviewed_at：2026-11-20T17:37:26+08:00

## Round 5 (2026-11-20T17:37:26+08:00)

最终确认轮。自 Round 4 以来代码交付内容未变（HEAD 仍为 `b1f979ba`，相对锚点的 diff 不变），仅 `progress.md` 的收尾报告/实施笔记补齐为最终版；`progress.md`、`review_*.md`、`docs/pending` 均为流程排除文件，不参与审查范围指纹。独立复算当前 worktree 指纹 `e79f445344eca869`，与派审注入指纹一致；无 reviewer 不可见的未跟踪交付文件。

## Findings

本轮无新发现（0 条 critical / important / minor）。finding 编号跨轮全局续编，本轮起点 f012；因无新增不产出条目。前轮 f001–f010 全部已修闭环（见 Round 1–4）。

## 结论

- 前轮 finding 复核（Round 5，以当前 diff 为准）：f001–f010 均已在前轮确认修复；本轮代码未变，抽查关键锚点无回归（`shared/egress.py:177,347` 保持 `trust_env=False`；`services/egress_probe.py:134` 保持 `asyncio.to_thread`；`proxies_router.py:167` 为 `202` + `job_id`；`profile_service.py:1897` 保留 `resume_pending_probe_jobs`；`useProfilesQuery.ts:938,1211` 进度由服务端 job 状态驱动）。证据见「AC 复验方式」各行 `file:line`。
- 本轮新发现：0 条（critical 0 / important 0 / minor 0）。
- 未进表的提示：
    - 文件过大（不进表）：`repository.py`、`profile_service.py`、`docker_adapter.py` 为既有大文件、本 task 继续净增；`schemas/openapi/*.json` 与 `generated/cbrowser_v1.d.ts` 为生成物，排除。
    - 圈复杂度：本轮无代码改动；`_drive_probe_job` / `_drive_profile_batch_job` 线性，未达阈值。
    - 契约区 drift：自 b1f979ba 仅 AC 打勾、`[deploy]` 处置注记与 AC-007 服务端作业实现补强，AC 原文一字未改；按用户判定视为实施 Agent 正常收尾，不出 blocking finding。
    - `[deploy]` AC-008/AC-009 按契约区「`[deploy]` AC 打勾处置注记（2026-11-20）」判 TICK-VALID（处置型），p151（`docs/pending/p151_t094_deploy_e2e_verification.md`）已登记；本机未执行真实 Docker/Chrome 链不作为 VOID 依据。
    - 全量门禁：派审声明 EXIT=0（contract 388 / unit 2410 / integration 216 / frontend 730 + build）；本轮无代码改动，不影响门禁结果。

reviewed_scope: e79f445344eca869

- 总体判断：代码交付内容相对 Round 4 未变，前轮 f001–f010 全部经 diff 复核确认已修，9 条 AC 全部 TICK-VALID，无 critical/important，判 PASS。
- 系统性 follow-up：p151 跟踪真实 Docker/Chrome E2E 延期验证（`[deploy]` AC-008/AC-009 处置型打勾），属既定 pending，非本轮新增缺口。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`docs/blueprint/supervisor.md`、`security.md:84`、`docs/specs/proxy_management.md`、`profile_management.md` 与 i18n/UI 文案均将探针限定为测速与出口信息展示；`security.md:84` 显式声明「不把探针当作防泄露保证」（否定式免责，非阳性误述），防泄露由 AC-008/AC-009 测试承担；f008 过期注释已更新，无阳性「自检隔离/防泄露保证」表述。
- AC-002：TICK-VALID，re_verified。三协议依赖与 `trust_env=False`／固定白名单 `ECHO_URLS`（`shared/egress.py:38,177,347`）成立；`asyncio.to_thread` 隔离且 timeout 传入（`services/egress_probe.py:134`）；`monotonic()` 只覆盖一次成功 HTTP 往返（`egress.py:301-308`）；loopback 映射与 compose `extra_hosts` 齐备（f001/f002 已修）；并行探测各建 client 不串扰，凭据不入命令行/日志。
- AC-003：TICK-VALID，re_verified。`proxies_router.py:167` 返回 `202` + `job_id`，入参为过滤条件/选择集；冻结目标集、零匹配 `total=0`；`repository.py` 零项作业直接 `done` 并回执终态（f005 已修）；超时收敛限定本 task 作业提交与批量动作。
- AC-004：TICK-VALID，re_verified。读模型/围栏/重启恢复齐备（`repository.py` job/member 表、`update_probe_job_member` 终态围栏 `:2975`、`finalize_probe_job :3011`、`resume_pending_probe_jobs` 经 `profile_service.py:1897` 与 `app.py:373`）；刷新恢复与全 kind 首读快照（`router.py:239-254`）具备；失败成员 `error_code` 可读（f006 已修）。
- AC-005：TICK-VALID，re_verified。本地 `probingId`/`probingAll` 进度状态已删（残留 `probingAll` 仅是由 `probeJobRunning` 派生的按钮禁用 prop，非并行本地进度状态）；SSE 单一处理器直写共享 job key（`useProfilesQuery.ts:938`），稳态无 refetch；首读快照、sessionStorage 刷新恢复与超窗 `resync-required` 补齐具备（f004 已修）。
- AC-006：TICK-VALID，re_verified。`list_proxy_ids_for_filters`（`repository.py:3035`）以服务端过滤条件解析且与列表同源；提交时写入 member 表冻结，后续测速观测导致归属变化不改写冻结集合；分页仅影响视图。
- AC-007：TICK-VALID，re_verified。后端服务端作业；前端进度条与汇总条（`EnvironmentListPage.tsx:433-450`）读共享 job key，`useProfileBatchJobQuery`（`useProfilesQuery.ts:1206-1211`）与 SSE 写入（`:938`）共用 `probeJobKeys.detail`，进度随 SSE 实时推进，满足「进度呈现与代理测速一致」；Round 2 的 TICK-VOID 缺口已由 f009 消除。
- AC-008：TICK-VALID，trust_prior。依 `[deploy]` 打勾处置注记与 p151 登记判处置型有效；依赖云端契约/实现/单元集成与前端门禁及 E2E 用例改写证据，本机未执行真实 Docker 探针链，不独立复验。
- AC-009：TICK-VALID，trust_prior。依 `[deploy]` 打勾处置注记与 p151 登记判处置型有效；Browser 侧双栈 `OUTPUT DROP` 保留，依赖云端契约与门禁证据，本机未执行真实 Chrome 链，不独立复验。

coverage = 7 / 9

verdict: PASS
