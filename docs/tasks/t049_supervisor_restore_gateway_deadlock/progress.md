---
tid: "t049"
slug: "supervisor_restore_gateway_deadlock"
title: "Supervisor 存量沙箱恢复解耦网关可见性探测与带载升级自愈"
status: "done"
branch: "t049_supervisor_restore_gateway_deadlock"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "13e631695e93182cd1f190223e6a8b9759967e89"
depends_on: ""
conflicts_with: ""
note: ""
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 2026-11-10T05:20:00+08:00 实施（阻塞于全量门禁的既有缺陷）

- 根因与修复：`supervisor/core.py` 删除存量恢复路径 `gateway_control is None` 抛错与 `has_foreground_viewers` 前置阻断；恢复流程改为 label/instance/API fence → policy_ready 宽限 → UDP mux 端口恢复 → 实例化 `ActiveSession` → 同一轮 `_converge_session`。
- 媒体网络挂载收敛抽为 `_ensure_media_attachment`（`MediaAttachmentOutcome` + `MEDIA_ATTACH_*`），由 `_converge_session` 与 `_recover_attachment_offline` 共用；不再依赖内存 session 或 Gateway 可见性。
- 恢复后预置 `RegistrationState(lost_at=...)`，让首个未注册读数走既有 90s 恢复宽限（而非立即 Stream-only 替换），宽限内 transport=recovering。
- 单元测试：`tests/unit/test_t049_supervisor_restore.py` 覆盖 AC-001..006；用真实 `GatewayControlClient` + `httpx.MockTransport` 注入真实 503/ConnectError，未打桩 `has_foreground_viewers`。红验证：对未修复实现 5/8 失败。
- E2E：`tests/e2e/test_supervisor_upgrade_recovery_e2e.py`（AC-007）经 `UpgradeTopologyHarness`（`GatewayTopologyHarness` 子类）运行：Profile 运行中强制重建 Gateway+Supervisor，300s 内 readiness 恢复、无死锁诊断、新 viewer 重新解出视频帧。通过（103s）。红验证：用未修复 supervisor 镜像复现 300s 超时，诊断恰为 `session_instance_mismatch`、`gateway_not_attached_at_fixed_endpoint`、`policy_unverifiable`、`agent_not_registered`。
- Harness 增补：`rebuild_gateway`、`rebuild_supervisor`、`rebuild_gateway_and_supervisor`；Supervisor 改传稳定容器名（与 compose 一致），重建后可按 label 解析新 Gateway；`scripts/gate_container_cleanup.py` 登记 `t049-` 前缀。

#### 全量门禁（AC-008）证据与遗留

- 用户批准在 t049 内修复相关 E2E 测试夹具（仅测试基础设施，不改生产代码）：
    - `tests/fixtures/supervisor_recovery_probe/offline_fixture.py`、`tests/e2e/test_supervisor_container_graph_e2e.py` 的 Supervisor 容器 `cap_add` 补 `CHOWN`（root 下 `manage_ownership=True` 会 chown socket 目录；缺 `CAP_CHOWN` 即 `PermissionError`）。
    - `test_supervisor_container_graph_e2e.py`：补挂 `data/sockets`，并给 Gateway 传与 Supervisor 相同的 `CBROWSER_UDP_MUX_MIN_PORT/MAX_PORT`（否则注册 `udp_port` 超出 Gateway 解析范围，被 `invalid_payload` 拒绝）。
    - `tests/unit/test_baseline_fixture_regressions.py` 同步夹具安全选项期望（CHOWN）。
- 用户决定将 t019 首帧预算从 2s 调整为 5s（本机基线镜像实测 3.4–3.7s）：`tests/e2e/test_frontend_app_e2e.py` 用例改名 `..._within_5s_host_only`，`docs/blueprint/testing.md` 同步；该用例在后续门禁中通过。
- 生产栈按用户批准临时 stop 后，标准 4 worker 全量门禁多次运行：
    - unit 1540 passed / integration 173 passed（18 skip 为既有环境豁免）/ frontend 499 passed / build 通过，多次稳定全绿；
    - E2E 每次 56–59 passed，失败项每次不同且均为超时类（`test_ac007...`、`test_supervisor_policy_failure...`、`test_supervisor_retry...` 等），单独复跑均通过；宿主机被其他会话压到 load 100–200，`wait.py` 就绪判定/容器启动在高负载下随机超时。
- 用户 2026-11-10 明确同意「用户豁免合入」：AC-008 按豁免打勾，task.md 原地记录豁免范围（各套件已分别全绿；单次全量在宿主高负载下随机超时但失败项单独复跑通过；不要求一次完整全绿）。生产栈已恢复（api/gateway/supervisor/caddy/browser/stream running，Profile observed=running）。
- 若后续需要补齐严格 AC-008：在机器空闲时重跑 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 并在 task 归档前更新证据。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-10T13:07:54+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t049_test_f001|important|撤回|用户 2026-11-10 明确指示将 t019 首帧预算改为 5 秒后合入；已在 `docs/specs/webrtc_remote_display.md` 写明新契约、本机实测 3.4–3.7s 样本与「原 2s 不再满足」，并同步 blueprint 与用例名。属用户批准的产品契约变更，非掩盖回归。|docs/specs/webrtc_remote_display.md:32|

代码轴 Round 1 零 finding（PASS）。

### Round 2 (2026-11-10T14:55:00+08:00)

代码轴与测试轴均 PASS，0 新增 finding；t049_test_f001 按用户授权撤回（新契约与实测记录见 `docs/specs/webrtc_remote_display.md:32`）。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-008 按用户 2026-11-10 豁免记录）
- 测试：unit 1540 / integration 173 / frontend 499 / build 多次全绿；t049 单测 8 条红绿验证；升级 E2E 修复版 103s 通过
- 黑盒：`tests/e2e/test_supervisor_upgrade_recovery_e2e.py` 通过；基线 supervisor 镜像复现 300s 超时与三类死锁诊断
- review：full 两轴 Round 2 PASS（reviewed_scope `ef51a572d2463cb9`）
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 待执行时填写；遗留只写引用，不复制正文

### 长期文档闭环

在 specs_index 行的 task 清单中登记当前 tid（格式见 `.repo_template/docs/usage.md`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
