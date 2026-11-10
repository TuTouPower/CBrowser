# Task spec

## 背景

部署时 `network_config_cli read` 拦截报错 `applied network configuration is corrupt; empty caddyfile_sha256`。2026-11-10 核实：

- 当前 CLI `_init`（`network_config_cli.py`）先算哈希再落盘，不再产出空哈希；本次空哈希文件是 `294dbbb`（2026-11-09 引入 CLI）之前旧初始化流程写入的残留（`data/v2/network/applied_network_version.json.bak`：`applied_at=2026-11-08T10:30:28Z`、`caddyfile_sha256=""`）。
- 但模型契约本身允许非法状态存在，且仍在生产路径中被使用：
    - `AppliedNetworkAccessVersion.caddyfile_sha256` 默认 `""`（`domain/models.py`）；
    - `create_default_applied_version()` 返回空哈希的半成品对象，被 `repository.get_network_access_settings` 的无数据回退（其结果经 `api/app.py` 作为 `snapshot_hash` 使用）与 `network_service._restore_old` 的无快照回退直接消费；
    - `network_service._restore_old` 在 `old.caddyfile_sha256` 为空时**跳过**哈希校验，并把空哈希下发给 Supervisor `restore_network_snapshot`，完整性校验被空值绕过；
    - `network_service` 申请新版本时以 `caddyfile_sha256=""` 的 `dummy_ver` 占位生成 Caddyfile。

按核心架构铁律，从模型层根治：已应用网络版本在构造时即携带与其 Caddyfile 一致的哈希，空哈希不可表示，校验无豁免分支。

## 契约区

### 范围

- `AppliedNetworkAccessVersion.caddyfile_sha256` 改为必填，非空且为 64 位小写十六进制 SHA-256；移除默认空值。
- 统一单一构造入口：由网络配置、版本号与 upstream 参数一次生成 Caddyfile 文本、哈希与 origin whitelist；删除 `create_default_applied_version` 产出空哈希的形态、`network_service` 的 `dummy_ver` 占位与 CLI 事后补哈希写法，所有构造方（CLI init、repository 无数据回退、`_restore_old` 无快照回退、申请新版本）改用该入口。
- `network_service._restore_old` 删除"哈希为空则跳过校验"分支，旧快照一律校验后才允许绑定。
- 单元测试覆盖上述行为。

### 非范围

- 不迁移、不修复已存在的空哈希历史数据（磁盘文件与 DB `network.applied_version` 行）；按无遗留数据约定，遇到即校验失败，由使用者重置数据目录。
- 不改 Caddyfile 生成内容与 upstream 取值。
- 不改 Supervisor 对账逻辑（见 t049）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：以缺失、空字符串或非 64 位十六进制的 `caddyfile_sha256` 构造或反序列化已应用网络版本时校验失败，不产生对象。
- [x] AC-002：任何构造方得到的默认（v1）已应用网络版本，其 `caddyfile_sha256` 等于同一 upstream 参数下生成的 Caddyfile 文本的 SHA-256，`origin_whitelist` 与配置推导结果一致。
- [x] AC-003：DB 无已应用版本且磁盘无导出文件时，`get_network_access_settings` 返回的已应用版本哈希非空并与按 API 实际 upstream 生成的 Caddyfile 一致。
- [x] AC-004：`network_service` 回滚旧版本时，旧快照哈希与重新生成的 Caddyfile 不一致即拒绝绑定，不存在因哈希为空而跳过校验的路径；下发给 Supervisor 的 `caddyfile_sha256` 恒为非空且经过校验的值。
- [x] AC-005：申请新网络版本时生成的版本哈希与写出的 Caddyfile 一致，过程中不构造空哈希的中间版本对象。
- [x] AC-006：`network_config_cli init` 在空目录写出的版本文件可被 `network_config_cli read` 无错读出；目录中版本文件哈希为空时 `read` 以 corrupt 退出码失败。
- [x] AC-007：全量门禁 `scripts/run_gates.sh`（不含 `CBROWSER_RUN_E2E=1`）通过。E2E suite 全量运行因既有的 Docker stream 容器启动基线故障不计入本 task 验收，登记 p056 追踪（用户 2026-11-10 批准缩窄）。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：用户 2026-11-10 提交的部署故障分析（Bug 1）；同日核对代码与 `data/v2/network/` 现场，结论见背景。

### 有意不测

- 历史空哈希数据迁移：非范围，按无遗留数据约定不提供迁移。
- E2E 全量：本机 Docker stream 容器启动基线故障（p056）使 `CBROWSER_RUN_E2E=1` 无法收敛；用户 2026-11-10 批准把 AC-007 缩窄为非 E2E 全量门禁，E2E fixture 的版本构造仍随单一入口更新。

### 测试策略

- 单元：模型校验（AC-001）、构造入口与 Caddyfile 哈希一致性（AC-002/AC-005）、repository 回退（AC-003）、`_restore_old` 拒绝不一致与无空哈希下发（AC-004）、CLI init/read 往返与空哈希拒绝（AC-006）。
- 既有 `tests/unit/test_a24_network_config_cli.py`、`test_a24_deploy_v2_network_source.py` 等若依赖空哈希构造，按 TDD 规则整体删除并写明理由或保留原样，不就地改预期。
- 门禁：`scripts/run_gates.sh`（不含 E2E）；E2E fixture 中的默认版本构造随单一构造入口一并替换。E2E 全量基线问题见 p056。与 t049 并行时错开执行（共享 OrbStack）。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无

### 风险与回退

- 风险：本地已有 DB `network.applied_version` 行或导出文件含空哈希时，API 启动或部署将校验失败。
- 回退：重置本地 `data/` 下网络状态后重新 `network_config_cli init`；代码层 revert 本 task 实现 commit。

### 依赖与约束

- 无前置 task。与 t049 无文件交集，可并行。
- 无遗留数据约定：不写兼容读取与迁移代码。

### Finalization 时更新的 blueprint

- `docs/blueprint/conventions.md` 或 `docs/blueprint/architecture.md` §6（安全、网络与端口矩阵）：已应用网络版本构造即完整、哈希非空且无校验豁免。
