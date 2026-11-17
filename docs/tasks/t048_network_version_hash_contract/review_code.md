# Task review t048（reviewer_focus: 代码）

- task：`t048_network_version_hash_contract`
- spec：`docs/tasks/t048_network_version_hash_contract/task.md`
- diff_anchor：`13e631695e93182cd1f190223e6a8b9759967e89`
- target：`git -C <t048 worktree> diff 13e631695e93182cd1f190223e6a8b9759967e89`
- round：1
- reviewed_at：2026-11-10T08:49:40+08:00

## Findings

无（0 条）。

## 结论

- 前轮 finding 复核：Round 1，无前轮。
- 本轮新发现：0 条。
- 未进表的提示：
    - 文件过大：`tests/fixtures/gateway_probe/topology.py` 725 行（测试源码 ≥600 阈值，本 task 净增 11 行，Docker E2E 拓扑夹具，未拆）。
    - 复杂度：`network_service._abort` / `_restore_old` 的异常补偿分支近似 McCabe 10–13（含短路条件），本 task 净删除了空哈希旁路分支，分支数下降，不进 finding。
    - 范围外观察（属上下文区「有意不测」的历史空哈希数据分支，按规则不出 finding）：DB 无行但磁盘存在空哈希 `applied_network_version.json` 时，`read_applied_network_state`（`network_config.py:180-187`）吞掉 pydantic 校验错误返回 `None`，API 侧回退为默认 v1（端口 56661、仅回环），而非 spec「风险与回退」所述的“API 启动校验失败”。该吞错逻辑非本 task 新增，且历史空哈希数据已明确列入有意不测，仅作记录。
- 总体判断：实现与 spec 契约区一致，构造入口统一、空哈希形态被模型契约彻底排除、恢复/回滚无空哈希旁路；专项单测与全量非 E2E 门禁（除既有基线失败）均通过，未发现 critical / important / minor。
- 系统性 follow-up：无（p056 已登记 E2E 基线问题）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`models.py:869` 改为无默认的 `Field(pattern=r"^[0-9a-f]{64}$")`；独立脚本对缺失、空串、`dummy`、63/65 位、大写、非十六进制、整数全部抛 `ValidationError`，与 `test_network_config.py::test_applied_network_version_requires_complete_lowercase_hash` 一致。
- AC-002：TICK-VALID，re_verified。`network_config.py:76-104` 单入口一次产出文本/哈希/白名单；独立脚本验证本地与 LAN 两种 config 下 `caddyfile_sha256 == sha256(generate_caddyfile(config))` 且 `origin_whitelist == derive_origin_whitelist(config)`；CLI/repository/`_restore_old`/apply 均走该入口。
- AC-003：TICK-VALID，re_verified。`repository.py:1357-1363` 无 DB 行且无导出文件时用 `build_applied_network_version(...,version=1)`；`test_network_repository.py` 断言哈希 64 位且等于 `compute_caddyfile_sha256(generate_caddyfile(config))`，生产 `app.py:265-274` 未覆盖 upstream，与构造默认值一致。
- AC-004：TICK-VALID，re_verified。`network_service.py:584-599` 与 `664-674` 均无条件比较重新生成哈希再绑定；集成用例 `test_restore_old_rejects_snapshot_hash_mismatch` 通过（篡改哈希后 `_restore_old` 返 False 且不调用 `restore_network_snapshot`）；下发字段 `611/685` 取自模型约束的非空 64 位值。
- AC-005：TICK-VALID，re_verified。`network_service.py:231-237` 删除 `dummy_ver` 直接由单入口产出，`_finalize_commit`（:495-502）用同一 config/upstream 再生同一文本；`test_network_service.py` 断言申请后写出的 Caddyfile 哈希与版本哈希一致。
- AC-006：TICK-VALID，re_verified。实跑 `network_config_cli init` 退出 0、`read` 退出 0 且输出含 `CADDYFILE_SHA256`；把版本文件哈希改为空串后 `read` 退出 4（corrupt，pydantic pattern 报错）；`test_read_corrupt_variants_rejected` 覆盖空串与不匹配两路。
- AC-007：TICK-VALID，re_verified。在本 worktree 实跑 `scripts/run_gates.sh`（不含 E2E，复用 gate venv/wheel cache）：requirements_check、contract、integration、design_lint、design_check、frontend_test、frontend_build 全 0；unit 1541 passed，仅 `test_repo_hygiene::test_tracked_files_do_not_leak_developer_home_paths` 失败，系基线 t047 归档路径问题（main e118a22 修复、p056 登记），非 t048 引入。

coverage = 7 / 7

reviewed_scope: a4af68f340690971

verdict: PASS
