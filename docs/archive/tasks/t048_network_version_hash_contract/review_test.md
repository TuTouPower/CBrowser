# Task review t048（reviewer_focus: 测试）

- task：`t048_network_version_hash_contract`
- spec：`docs/tasks/t048_network_version_hash_contract/task.md`
- diff_anchor：`13e631695e93182cd1f190223e6a8b9759967e89`
- target：`git -C <t048 worktree> diff 13e631695e93182cd1f190223e6a8b9759967e89`
- round：1
- reviewed_at：2026-11-10T08:48:20+08:00

reviewed_scope: a4af68f340690971

独立复验命令（均在 `CBrowser_t048` 下，`TMPDIR=/tmp/t048 PYTHONPATH=src/backend`，解释器
`<gate venv>/bin/python`）：

- 定向：`pytest tests/unit/test_network_config.py tests/unit/test_a24_network_config_cli.py tests/unit/test_network_repository.py tests/unit/test_network_service.py tests/integration/test_a35_recovery.py tests/integration/test_ac007_origin_whitelist_sync.py -q` → `40 passed`。
- 关联：`test_gateway_fixtures.py`、`test_baseline_fixture_regressions.py`、`test_gateway_config.py`、`test_a35_gateway_ack.py`、`test_a35_network_transaction.py`、`test_control_migration.py`、`test_network_router.py` → `74 passed`。
- AC 用例点名：8 个关键用例逐一 PASS。
- 全量 unit：`pytest tests/unit -q -n 1`，结果与基线/环境缺陷见「未进表的提示」。

## Findings

### t048_test_f001 - AC-004 未断言下发 Supervisor 的 caddyfile_sha256 字段

- 严重度：minor
- 锚点：AC-004（「下发给 Supervisor 的 `caddyfile_sha256` 恒为非空且经过校验的值」缺少直接断言）
- 位置：`tests/integration/test_a35_recovery.py:496-510`、`src/backend/cbrowser/services/network_service.py:611`
- 问题：`_restore_old`（及 retry 路径）确实以 `caddyfile_sha256=old.caddyfile_sha256` 调用
    `restore_network_snapshot`，但成功路径测试只断言 `restore_network_snapshot.called`
    （`test_a35_recovery.py:364`）与 `execution_generation`（`:502`、`:508`），从未断言该 kwarg
    为非空的 64 位十六进制、且等于被校验过的旧快照哈希。哈希非空目前由模型契约结构性保证，
    但「下发给 Supervisor 的值」这一可观察契约本身未落到断言上。
- 建议：在成功型恢复用例（`test_restart_with_abort_restores_old_config` /
    `test_restore_fails_once_then_retry_succeeds_with_bumped_generation`）追加
    `kwargs["caddyfile_sha256"] == old.caddyfile_sha256` 且长度 64 的断言。

### t048_test_f002 - AC-006 缺少「空目录 init 后直接 read」的端到端往返

- 严重度：minor
- 锚点：AC-006（「`init` 在空目录写出的版本文件可被 `read` 无错读出」仅被拆分验证）
- 位置：`tests/unit/test_a24_network_config_cli.py:53-71`（init 后仅校验文件内容）、`:88-107`（init 命中已存在状态 + read）、`:125-159`（空哈希 corrupt）
- 问题：fresh-init 分支（`:55`）测试只读文件字节并与 `hashlib.sha256` 比对，未再调用
    `_cli("read", ...)`；而真正执行 `read` 的用例（`:97`）其状态由 `_write_custom_state`
    先写入，`init` 走的是「保留已存在状态」分支。于是「空目录 init 产出的文件能被 read 无错
    读出」这条 AC 只由两条分离用例合成推断，无单条端到端证据。空哈希 `read` 报 corrupt
    （`:153-155`）已直接覆盖，故仅为可加 case 的覆盖扩展。
- 建议：在 `test_init_first_run_writes_real_hash` 内追加一次
    `_cli("read", ...)` 并断言 `returncode == 0`、`CADDYFILE_SHA256` 与写入值一致。

## 结论

- 改测方向复核：无「迁就实现」的改测。所有既有测试改动均为契约驱动的最小适配：
    `abc123hash`/`hash1`/`hash-{n}`/`""` 等占位哈希替换为合法 64 位十六进制
    （如 `test_network_repository.py:80,89`、`test_a35_network_transaction.py:48`、
    `test_control_migration.py:218`、`test_gateway_config.py`、`test_a35_gateway_ack.py`、
    `test_gateway_fixtures.py`、`test_network_router.py`），原断言语义（持久化往返、
    基线切换、白名单同步）保留；旧「先构造空哈希再回填」夹具改为走单一入口
    `build_applied_network_version`（`test_a24_network_config_cli.py:47`、
    `test_network_config.py`、`test_a35_recovery.py`），是被测契约变更后的合法迁移，
    未把断言预期改写成当前实现输出。无删测试 / 删 expect / `skip` / 恒真断言 / mock 被测逻辑。
- 本轮新发现：2 条（均 minor）。
- 未进表的提示：
    - AC-007 缩窄口径成立。t048 相关用例全绿；非 E2E 各 suite 在
        `/tmp/t048_gate_final/manifest.json` 中除 unit 外均 exit 0，unit 的 2 个失败为
        `test_api_runtime_coordinator`/`test_stream_transport_hardening` 的 asyncio/ws 超时
        环境 flake，我单独重跑两例 `2 passed`。我独立全量复跑 unit 仅剩三类非 t048 失败：
        `test_repo_hygiene`（基线 13e6316 已知、main e118a22 已修，按要求不计）、
        `test_t045_selkies_wheel_cache` 两例（本 worktree `.scratch/selkies_wheels/` 缺
        wheel，属 gitignore 环境产件，主仓存在）。无 t048 引入的失败。
    - AC-006 的「空哈希 read 以 corrupt 退出」现在实际由模型反序列化校验触发
        （`domain/models.py:870` 的 `pattern`），而非 CLI 里被删除的显式空值分支；行为等价，
        测试断言的是退出码这一可观察结果，判为有效。
- 总体判断：无未解决 critical / important，全部 AC 打勾有真实、可信测试支撑，PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`test_network_config.py::test_applied_network_version_requires_complete_lowercase_hash` 覆盖缺失/空串/63/65/大写/非十六进制/`model_validate_json`，我另以 worktree 模型实测 `x`+64hex、`a*64+"\n"`、大写均被拒，pattern 确有锚定。
- AC-002：TICK-VALID，re_verified。`test_network_config.py::test_build_applied_network_version_is_complete_and_consistent` 断言 `caddyfile_sha256==sha256(caddyfile)`、`origin_whitelist==derive(config)`、`bind_host`；`test_a24_network_config_cli.py::test_init_first_run_writes_real_hash` 用 `hashlib.sha256(磁盘内容)` 独立核对 CLI 产物。
- AC-003：TICK-VALID，re_verified。`test_network_repository.py::test_network_settings_defaults_and_pending_save`（:39-52）在空内存 DB、无 export_dir 下走无数据回退，断言哈希长度 64、等于 `compute_caddyfile_sha256(generate_caddyfile(fallback.config))`、白名单一致；生产 `app.py` 未覆盖 upstream，故与 API 实际默认 upstream 一致。
- AC-004：TICK-VALID，re_verified。新增 `test_a35_recovery.py::test_restore_old_rejects_snapshot_hash_mismatch` 篡改旧快照哈希为 `"b"*64` 后 `_restore_old` 返回 False 且 `restore_network_snapshot.assert_not_awaited()`；`test_restart_with_abort_restores_old_config` 覆盖匹配即绑定。空哈希旁路已由模型（非空）消除。
- AC-005：TICK-VALID，re_verified。`test_network_service.py::test_network_service_apply_lifecycle`（:125-133）在 apply 完成后读取 `tmp_path/Caddyfile` 真实字节，断言 `applied_version.caddyfile_sha256` 长度 64 且等于该文件 SHA-256。
- AC-006：TICK-VALID，re_verified。`test_init_first_run_writes_real_hash` 验证空目录 init 产物哈希；`test_read_corrupt_variants_rejected`（:145-155）验证版本文件空哈希时 `read` 返回 `EXIT_CORRUPT`；`test_init_keeps_applied_custom_port_and_lan`（:97）验证 `read` 无错读出。（直接 init→read 往返见 f002）
- AC-007：TICK-VALID，re_verified。t048 定向 40 例 + 关联 74 例全绿；非 E2E 各 suite 在 manifest 为绿（unit 仅环境 timeout flake，我单跑通过），独立全量 unit 仅剩基线 `repo_hygiene` 与 worktree `.scratch` 缺 wheel 两类非 t048 失败。

coverage = 7 / 7

verdict: PASS
