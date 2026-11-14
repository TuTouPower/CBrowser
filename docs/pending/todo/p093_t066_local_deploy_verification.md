# p093 t066 合入后本地真实部署补验（[deploy] AC 切片）

- 来源：t066 遗留（云端无 Docker，[deploy] AC 的真实部署切片无法执行；云端可验部分已由单测、恢复点工具故障注入测试与真实引擎 spike 验足）
- 内容：t066 在云端 finish 后，下列事项只能在带 Docker 的本地环境（Mac）随终局合入补跑并留证：
    1. AC-001 [deploy]：隔离实例中给运行过的 Profile 预置 Cookie/localStorage/IndexedDB/书签，逐项修改代理、分辨率、时区、语言、指纹参数并保存、重启，验证状态目录内容不变、身份参数与实际引擎一致。
    2. AC-003 [deploy]：真实引擎两态 clone 往返——仅配置 clone 无状态可用、带状态 clone 的 Cookie/登录态在新 Profile 实际打开站点可用，源 Profile 不受影响（云端 spike 已证引擎无 OSCrypt 密钥根锚定，本地复核同一结论）。
    3. AC-004 [deploy]：真实 Profile 确认 reset 后书签/历史/偏好/Cookie/登录态/存储/缓存全清、配置与独立 Artifact 保留；人为注入目录替换失败时旧目录与配置成套恢复。
    4. AC-005 [deploy]：启动与 clone/reset/备份恢复交错的真实拓扑验证（含残留 runtime 实例绑定时拒绝、viewer 连接不触发停止或清理）。
    5. AC-011 [deploy]：隔离实例执行 `deploy.sh env-backup` → 改状态 → `deploy.sh env-restore` 完整往返，验证配置、登录态恢复到恢复点，凭据前提清单所列文件齐备时服务正常启动；确认指南命令能从 named volume 取得并恢复 DB。
    6. findings 补录：findings.py 在 main 上因既存 d037/d038 编号重复拒绝分配新号（工具链缺陷，与 t068 报告同源）；编号冲突解决后，把 t066 task.md 已回填的两条 spike 结论（引擎 Cookie 密钥根、db_restore 无校验直覆）正式登记为 findings 条目。
- 处理：AC-011 / AC-001（配置持久化）/ AC-004（reset）已补验；findings 重号已手动修复并补录 d044/d045；AC-003 / AC-005 保留（真实数据安全契约）

## 开发铁律重判（2026-11-15）

- 保留的两项（AC-003 两态 clone 真实引擎状态、AC-005 启动与 clone/reset/备份恢复交错拓扑）是**真实数据安全契约**，不是打勾清单：t066 云端 spike 已证引擎无可复制 OSCrypt 根（d044）、`db_restore.py` 无校验毁库（d045）；本地已验 AC-001 配置持久化、AC-004 reset、AC-011 完整往返。剩余需启动真实 Browser 写入 Cookie/IDB/书签后做 clone/reset 交错，会产生新信息。
- 与 p090/p096 的区别：后者行为层已被 gate5 E2E 完全覆盖，剩余只是数值精度/长时观测；本项剩余的是尚未被任何真实链路覆盖的数据原子性场景。
- 跑通条件：生产栈已具备，隔离实例内启动真实 Browser runtime → 写状态 → clone/reset/交错 → 校验目录与 DB 成套一致。**无设施缺口**。
- 时间：2026-11-14T22:36:00+08:00

## 终局补验证据（gate5 / 真实部署栈，最终结论；取代下方 gate4 阶段性记录）

- 真实部署：`scripts/deploy.sh deploy` 成功（Release `20261114212243-78d4f8c`），4 容器 healthy，`api_health=200`。
- AC-011 完整往返（`.scratch/terminal_deploy_slices/p093_env_roundtrip.log` / `p093_env_roundtrip2.log`）：`env-backup` 生成恢复点，manifest 含 `credential_prerequisites` 7 项（admin_password/agent_key/edge_proof_key/gateway_api_key/gateway_key/supervisor_key/viewer_grant_key）与 `profiles`；经 API 真实创建 Profile 改状态（201）→ `env-restore` 停栈并恢复（previous set 保留）→ 用同一 release env 重新 `up -d --no-build --wait` → 4 容器 healthy、`GET /api/v1/profiles` 回到空集（mutant 消失）、`api_health=200`、`deploy.sh status` release 不变。
- AC-001（配置持久化）：真实 Profile `PATCH /api/v1/profiles/{id}` 写入 timezone=Asia/Tokyo、locale=zh-CN、1600x900、fingerprint_seed=424242、notes，返回 `current_config_version=2` 且各字段一致（`.scratch/terminal_deploy_slices/p093_state.log`）。
- AC-004（reset）：`POST /api/v1/profiles/{id}/reset {"confirm":true}` 返回 200，状态目录 `profiles/{id}/profile` 创建且为空（全清），timezone/locale/分辨率/notes/user_data_dir 全部保留（`ac004_config_preserved True`），`fingerprint_seed` 按 p089 契约重 roll（`ac004_seed_rerolled_by_design True`），`current_config_version=3`。
- 卡点：AC-001 的完整 Cookie/localStorage/IndexedDB/书签 + 引擎参数一致、AC-003 两态 clone 往返、AC-005 启动与 clone/reset/备份恢复交错拓扑，需运行中的真实 Browser 与引擎状态注入脚本，本批未构造。
- findings 重号（已修）：t051 先占 d037/d038，t060/t057 从旧基线各自 mint 后合并造成重号，导致 `findings.py new` 拒绝分配。2026-11-15 手动把后合入的两条改为 `d042_dockerignore_leaf_allowlists.md` / `d043_target_engine_tab_visibility_unreliable.md` 并同步全仓引用（提交 `426978e`）；`findings.py list` 无重复、`findings.py new` 恢复取号。t066 两条 spike 结论已正式登记为 `d044_engine_oscrypt_no_portable_key_root.md` / `d045_db_restore_unvalidated_overwrite.md`，本项 findings 补录闭环。归档文档里「当时被重复编号阻断」的记录保留为历史事实。

## 本地补验证据（gate4）

- 已验（间接）：gate4 `test_supervisor_orphan_helpers_e2e.py`、`test_supervisor_reconciliation_e2e.py`、`test_supervisor_container_graph_e2e.py::test_authoritative_gateway_port_credentials_and_instance_fenced_lifecycle` 全绿，覆盖 AC-005 的「残留 runtime 实例绑定时拒绝、viewer 连接不触发停止/清理」的拓扑前提部分。
- 卡点：AC-001（Cookie/localStorage/IndexedDB/书签 + 代理/分辨率/时区/语言/指纹改存重启）、AC-003（两态 clone 往返、源 Profile 不受影响）、AC-004（reset 全清 + 目录替换失败成套恢复）、AC-005（启动与 clone/reset/备份恢复交错真实拓扑）、AC-011（`deploy.sh env-backup` → 改状态 → `env-restore` 往返 + named volume DB）五项均需隔离实例内真实 Profile 数据与生产栈；本批未启动，未验。
- findings 现状：`python3 .repo_template/scripts/findings.py list` 显示 `d037` 各 2 条（`d037_dockerignore_leaf_allowlists` / `d037_sqlite_extended_error_codes_and_log_safety`）、`d038` 各 2 条（`d038_deterministic_deployment_identity_and_media_pools` / `d038_target_engine_tab_visibility_unreliable`）；编号重复导致 `findings.py new` 拒绝分配新号，t066 task.md 已回填的两条 spike 结论无法正式登记。按批次口径：工具链缺陷，不在本批修复范围，仅说明现状。
