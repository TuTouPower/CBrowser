---
tid: "t048"
slug: "network_version_hash_contract"
title: "网络版本 caddyfile_sha256 构造即完整契约"
status: "done"
branch: "t048_network_version_hash_contract"
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

- 模型契约：`AppliedNetworkAccessVersion.caddyfile_sha256` 移除默认值，改为必填 `pattern=r"^[0-9a-f]{64}$"`；缺失、空串、非 64 位、大写/非十六进制与反序列化旧空哈希全部由 pydantic 拒绝（AC-001）。
- 单一构造入口：`network_config.build_applied_network_version(config, *, version, api_upstream, gateway_upstream, frontend_dir)` 一次性返回版本与 Caddyfile；`generate_caddyfile` / `derive_origin_whitelist` 改为接收 `NetworkAccessConfig`（渲染本就不依赖版本其余字段）。删除 `create_default_applied_version`，CLI init、repository 无数据回退、`_restore_old` 无快照回退、`apply_configuration` 申请新版本全部改用该入口（AC-002/003/005/006）。
- 恢复路径：`_restore_old` 与 `_abort` 删除“哈希为空则跳过校验”的双分支，无条件比较重新生成的 Caddyfile 哈希后再绑定；`begin_network_transaction` 的 TOCTOU 哈希围栏也去掉空值旁路（AC-004）。
- 测试与夹具：`tests/unit/test_network_config.py` 整体替换旧占位哈希夹具并新增模型/构造入口契约测试；`test_a35_recovery.py` 用构造入口生成旧/新版本并新增哈希不符拒绝用例；`test_network_service.py` 断言申请新版本哈希与写出的 Caddyfile 一致；`test_network_repository.py` 断言无数据回退哈希非空且与生成器一致；CLI 空哈希 corrupt 用例经由模型校验继续成立。`gateway_probe/topology.py`、`supervisor_recovery_probe/gateway_service.py`、`test_supervisor_container_graph_e2e.py` 的默认版本构造改走单一入口。
- Schema/类型：`scripts/export_openapi.py` 重导出 `schemas/openapi/cbrowser_v1.json` 与 `cbrowser_internal.json`；前端 `generate:api` 重生成 `cbrowser_v1.d.ts`（仅移除 `@default` 注释）。
- 门禁基线：main 13e6316 的 `tests/unit/test_repo_hygiene.py` 因 t047 归档 allowlist 失同步而失败；经用户批准在 main 独立修复（p055，commit e118a22），E2E stream 容器启动基线故障另登记 p056。用户 2026-11-10 批准将 AC-007 缩窄为非 E2E 全量门禁。
- 验证：受影响 unit/integration 全部通过（见收尾报告）；在「main e118a22 + t048 改动」组合树以 `CBROWSER_GATE_WORKERS=1 scripts/run_gates.sh` 跑通 requirements/contract/unit/integration/design_lint/design_check/frontend_test/frontend_build，`all_passed=true`。`CBROWSER_RUN_E2E=1` 在基线旧镜像与按当前源重建镜像下均因 `Failed to run stream container ...: APIError` 大面积失败，且未含 t048 的 main 同样复现，见 p056。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-10T08:48:20+08:00)

code reviewer 零 finding；test reviewer 2 条 minor。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t048_test_f001|minor|撤回|AC-004 的「下发值非空且经过校验」已由模型必填 64 位十六进制与 `_restore_old` 先校验后调用结构保证，成功路径测试已断言调用发生与生成代次；补一条 kwarg 断言属可选覆盖增强，不构成契约缺口，不引入交付改动。|—|
|t048_test_f002|minor|撤回|init 产物哈希已用磁盘字节独立核对，`read` 无错读出由同一格式的自定义状态用例与空哈希 corrupt 用例覆盖；拆分验证已覆盖可观察行为，不构成契约缺口，不引入交付改动。|—|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：定向 unit/integration 40 例通过；受影响关联用例 74 例通过；组合树（main 86e3f6b + t048 改动）非 E2E 全量门禁 8 个 suite 全绿（`/tmp/t048_gate_final/manifest.json`，unit 两个环境 flake 单独重跑通过），独立全量 unit `1578 passed`。
- 黑盒：`CBROWSER_RUN_E2E=1` 因既有 Docker stream 容器启动基线故障（p056）无法收敛；AC-007 经用户批准缩窄为非 E2E 全量门禁，未声称 E2E 通过。
- review：code PASS（零 finding）；test PASS（2 条 minor 均撤回，附理由）。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 已应用网络版本在模型层强制 64 位小写十六进制哈希，空哈希不可表示；所有构造方收敛到 `build_applied_network_version`，恢复/回滚删除哈希空值豁免，旧快照一律校验后才绑定。
- 遗留：E2E stream 容器启动基线故障见 `p056`；本 task 无其它遗留。

### 长期文档闭环

- `docs/specs/release_deployment.md` 增加 t048 网络版本构造契约；`docs/specs_index.md` 的 release_deployment 行登记 t048 并更新日期。
- `docs/blueprint/architecture.md` §6 补充已应用网络版本构造即完整与无空哈希豁免约束。
