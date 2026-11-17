# 项目交接记录（最新）

## 2026-11-17T13:52:00+08:00 t074 合入、仓库整理与真实部署补验

### 状态与工作区

- branch `main`；写入时 head_commit `8e1bd9b6d1293a3cb9e5e78237a742fdfd706b72`。此处记录写入时 HEAD，后续提交由提交自身记录。
- t074 已 done 并合入 main（merge `012a230`），origin/main 与本地一致；`task.py ps` 无在飞、`effective-status` 无 backlog/active、`plan` 无可推荐链、`pending.py list` 无 todo。
- 已闭环：`p112` 归档（`transferred`，t074 AC-006 `[deploy]` 顺延转部署阶段现场验收）；t051–t060 历史 done task 目录迁入 `docs/archive/tasks/`（commit `4ba1c28`）；`docs/handoff.md` 过时段落与 s011–s024 完结 spike 迁入 `docs/archive/`（commit `8e1bd9b`）。
- 真实部署：`deploy.sh` 两次发布均 readiness-verified，current release `20261117133551-8e1bd9b`，DB stamp `8c3f1d0a7b92`（0010）；通过 API 导入 88 个 mihomo 真实节点（85 created / 1 updated / 2 skipped / 0 failed）。

### 门禁与交付

- 合入后全量门禁 9 suite `all_passed=true`（`.scratch/t074_step356/gate_evidence_merge_r4`）；归档整理后 9 suite 全绿（`gate_evidence_hygiene_r3`）；Supervisor 响应字段修复后 9 suite 全绿（`.scratch/deploy_t074/gate_evidence_fix`）。均用 `CBROWSER_GATE_WORKERS=1` 规避高负载下的时序 flake。
- t074 full 级双路独立 review Round 2 PASS，scope `6343a38bcc6ebd1f`；AC-001..005 `re_verified`，原 AC-006 `[deploy]` `trust_prior`。
- 冒烟发现并修复：`control_server.py:probe_proxy` 漏传 `country_name` / `city` / `latency_ms`，导致首次部署的观测三字段为 NULL；补字段 + 红灯测试后二次部署验证通过。
- AC-006 真实部署端到端已于本次补验完成（84/88 ok、延迟 418–7349 ms 中位 592、国家名/城市 84/84 填充、4 个 `echo_unreachable` 失败态、刷新持久化稳定、临时不可用代理验证错误码透传）；详见 `docs/archive/verification/t074_deploy_import_20261117.md`。
- 证据留存：主仓忽略目录 `.scratch/t074_step356/` 与 `.scratch/deploy_t074/`（门禁日志、review prompts、gate manifests、部署/导入/验证记录）。
- 剩余风险：0010 升版后 0009 release 的 `rollback` 被文档规则拒绝，本次未创建环境恢复点；4 个节点当前不可达属真实网络状况。
- parked 8 条（p031/p038/p039/p040/p041/p043/p045/p053）为用户确认暂搁，按约定保留不迁 archive。
