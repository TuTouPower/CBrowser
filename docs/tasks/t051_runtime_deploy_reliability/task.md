# Task spec

## 背景

四个运行与部署层缺陷集中在同一交付面（`compose.yaml`、`scripts/deploy.sh`、Supervisor Docker 适配层、API 数据库错误边界），合并为一个 task 交付：

1. **控制面数据库失稳（p068）**：`cbrowser.db` 位于 `${CBROWSER_DATA_ROOT}` 宿主 bind mount（macOS → OrbStack VM）。SQLite WAL 要求 `-shm` wal-index 以 mmap 在同机进程间共享，跨宿主/VM 边界时 mmap 一致性与锁语义不可靠，返回 `SQLITE_IOERR`（`disk I/O error`）。2026-11-10 18:37–18:51 登录与 `/auth/session` 持续 500，自愈后 `integrity_check` 正常。应用层放大故障：`api/app.py` 的 `DBAPIError` 处理器把非 `IntegrityError` 一律映射为 `500 database_error retryable=false`；`AuthService` 等服务无 `DBAPIError` 分类；`ProfileService._handle_db_error` 只识别 `SQLITE_BUSY/LOCKED`；日志只记异常类名与 `str(exc.orig)`，无 SQLite 扩展错误码；前端 `LoginPage.tsx` 直接透传英文 `err.message`。
2. **平台字体集在部署环境不可见（p063）**：t041 导入工具与 `.worktreeinclude` 把字体集存于主仓 `data/fonts`；`compose.yaml` 把 `CBROWSER_FONTS_DIR` 硬编码为 `${CBROWSER_DATA_ROOT}/fonts`，`deploy.sh` 默认 `CBROWSER_DATA_ROOT=$ROOT/data/v2`，于是服务挂载空目录 `data/v2/fonts`，`GET /api/v1/font-sets` 返回空，新建 Profile 回退 Linux 基础字体。
3. **沙箱启动失败丢弃 Docker 原始错误（p059）**：`start_stream_container` 等包装 `DockerException` 时只保留异常类名（`start_browser_container` 则未经脱敏直接拼接 `{e}`），端口占用、网络冲突、镜像参数错误等根因无法从日志定位。
4. **沙箱 compose service 不带编号（p066）**：`container_spec.sandbox_compose_labels` 把 `com.docker.compose.service` 固定为 `browser` / `stream`，OrbStack / Docker Desktop 在 `<prefix>-profiles` 分组下只显示同名 service，多 Profile 无法区分（t050 规范写为 `service=browser|stream`，本 task 按用户要求修订）。

用户 2026-11-10 裁决：控制面数据库**仅 DB** 移入 Docker named volume，保留 WAL；profiles / artifacts / runtime 等仍为 bind mount。

## 契约区

### 范围

- 控制面数据库（`cbrowser.db` 及 `-wal` / `-shm`）改存 Docker named volume，API 独占读写；`compose.yaml` 不再让数据库落在宿主 bind mount。
- `scripts/deploy.sh` 的 schema 代际只读检查、部署前数据库备份与恢复路径改为经容器访问 named volume；备份产物可在宿主取得并可恢复。
- 本机旧 `data/v2/cbrowser.db` 改名保留，不迁移内容（无真实用户，见 memory no-legacy-data）；部署脚本对“volume 为空且宿主存在旧库”给出明确提示，不静默丢弃。
- API 数据库错误分类：识别 SQLite 主错误码与扩展错误码；`SQLITE_BUSY` / `SQLITE_LOCKED` / `SQLITE_IOERR*` 归为瞬时故障，映射为可重试响应（`503`、稳定错误码、`retryable=true`）；约束冲突等确定性错误保持原语义。
- 认证与会话路径（登录建会话、会话校验、登出、automation token）对瞬时数据库故障有界重试，重试耗尽返回上述可重试错误。
- 数据库错误日志携带 `sqlite_errorcode` / `sqlite_errorname`、请求方法与路径，不含 SQL 参数值、密码、token。
- 前端登录页按错误码显示 i18n 文案（中/英），可重试错误提示稍后重试，不再透传后端英文原文。
- 平台字体目录：`CBROWSER_FONTS_DIR` 成为独立部署输入（默认主仓 `data/fonts`），`compose.yaml` 按该值只读挂载到 API 与 Supervisor，与 `CBROWSER_DATA_ROOT` 解耦；`deploy.sh` 预检字体目录存在且至少有一个通过完整性校验的字体集，否则给出可执行提示（不阻断无字体部署时须明确告警）。
- Supervisor 沙箱启动（Browser、Stream、cache initializer、X11 helper、网络创建、策略 helper）失败时，异常与日志保留 Docker 原始错误信息的脱敏文本；统一脱敏规则覆盖代理凭据、URL userinfo、token、密钥类环境变量值。
- 沙箱 `com.docker.compose.service` 带 Profile 编号（`<NNNN>-browser` / `<NNNN>-stream`），`com.docker.compose.project` 聚合不变。
- 更新 t050、t041 相关测试中与新契约冲突的断言（按 TDD 规则：新增覆盖新语义的测试，旧测试整体删除或保留并写明理由）。

### 非范围

- 不迁移 profiles / artifacts / runtime / exchange 等目录出 bind mount。
- 不改 SQLite 为其它数据库，不改 journal 模式。
- 不迁移旧数据库内容，不保留旧挂载路径兼容。
- 不改字体集导入工具与字体集内容格式。
- 不改容器命名（`<prefix>-<NNNN>-browser|stream`）与 compose project 聚合。
- 不做数据库以外服务的通用重试框架。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：部署后控制面数据库文件（含 `-wal` / `-shm`）不位于任何宿主 bind mount 上；compose 结构测试对此断言。
- [ ] AC-002：`deploy.sh` 的 schema 代际检查在新存储位置上仍按原语义放行合法代际、拒绝退役代际，且检查过程不以写模式打开数据库。
- [ ] AC-003：部署前备份产生宿主可取得的数据库副本；用该副本恢复后 API 正常启动且数据一致。
- [ ] AC-004：volume 中无数据库而宿主旧路径存在 `cbrowser.db` 时，部署输出明确提示旧库位置与处置方式，旧文件不被删除或覆盖。
- [ ] AC-005：数据库操作抛出 `SQLITE_IOERR`、`SQLITE_BUSY`、`SQLITE_LOCKED`（含扩展码）时，API 返回 503、稳定错误码且 `retryable=true`；`IntegrityError` 等确定性错误响应不变。
- [ ] AC-006：登录建会话遇到有限次瞬时数据库故障后恢复时，登录成功；故障持续超过重试上限时返回 AC-005 的可重试错误，不返回 500。
- [ ] AC-007：数据库错误日志包含 SQLite 错误码名、请求方法与路径，不包含 SQL 参数值、密码、会话 token。
- [ ] AC-008：登录页收到可重试数据库错误时显示当前界面语言的本地化文案，不显示后端英文原文。
- [ ] AC-009：`deploy.sh` 默认部署时 API 与 Supervisor 看到主仓 `data/fonts` 中的字体集，`GET /api/v1/font-sets` 返回已导入字体集；字体目录可经 `CBROWSER_FONTS_DIR` 覆盖。
- [ ] AC-010：字体目录缺失或无有效字体集时，部署输出可执行提示；compose / deploy 的字体路径与 `.worktreeinclude` 一致性由测试断言。
- [ ] AC-011：Browser、Stream 及其辅助容器启动失败时，抛出的异常与日志包含 Docker 原始错误信息；若原文含代理凭据、URL userinfo、token 或密钥类环境变量值，输出中均被替换为脱敏占位。
- [ ] AC-012：两个不同编号的 Profile 同时运行时，各自 Browser / Stream 容器的 `com.docker.compose.service` 分别为 `<NNNN>-browser` / `<NNNN>-stream` 且互不相同，`com.docker.compose.project` 仍为 `<prefix>-profiles`。
- [ ] AC-013：[deploy] 真实部署后：登录、Profile 启动出图正常；`docker inspect` 显示数据库在 named volume；设置页显示平台字体集；OrbStack 分组中可按编号区分沙箱 service。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001..012：可自动测试（compose 结构测试、fake Docker CLI 驱动 deploy.sh、注入 `OperationalError` 的单元/集成测试、前端组件测试、container_spec / adapter 单测）。
- AC-013：真实部署验证；替代验证为 `scripts/deploy.sh deploy` 后执行登录、启动 Profile、`docker inspect` 挂载、设置页截图与 OrbStack 分组人工确认。p068 原始故障为间歇性、不可按需复现，存储位置结构断言（AC-001）替代“故障不再出现”的直接验证。

## 上下文区

- 来源：p059、p063、p066、p068（2026-11-10 复核：`docker_adapter.py` Stream 路径仍只保留 `type(exc).__name__`、Browser 路径未脱敏拼接 `{e}`；`container_spec.py:64` service 仍为静态值；`compose.yaml:19/27/98/105` 字体路径仍绑 `CBROWSER_DATA_ROOT`，`data/v2/fonts` 为空、`data/fonts` 有 windows/macos 两组；`compose.yaml:18/26` DB 仍在 `${CBROWSER_DATA_ROOT}:/data` bind mount，`session.py` 启用 WAL，`app.py:391` 仍统一 500）。

### 有意不测

- OrbStack bind mount 上 SQLite mmap 失稳本身：间歇性宿主环境故障，无法稳定复现；以存储位置结构断言替代。
- OrbStack / Docker Desktop 分组 UI 渲染：私有实现，以标签断言 + 人工确认替代。

### 测试策略

- 单元：错误分类（主码/扩展码矩阵）、503 响应结构、认证路径有界重试、日志字段与脱敏、Docker 错误脱敏规则、compose service 标签多 Profile 区分。
- 结构：compose 中 DB 路径不落 bind mount；字体挂载路径与 `.worktreeinclude`、deploy 默认值一致。
- deploy.sh：fake Docker CLI 覆盖 schema 检查、备份/恢复、旧库提示、字体预检。
- 前端：登录页错误码 → i18n 文案。
- E2E / 门禁：`tests/e2e`、`tests/integration`、`tests/fixtures` 中直接按宿主路径读 `cbrowser.db` 的位点（`tests/e2e/conftest.py`、`test_supervisor_recovery_e2e.py`、`test_artifact_delete_resume_e2e.py`、`test_supervisor_container_graph_e2e.py`、`tests/fixtures/*`）改为经新存储位置访问；`run_gates.sh` 对 `CBROWSER_FONTS_DIR` 的处理同步调整。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。SQLite WAL 同机共享内存要求见 SQLite 官方 WAL 文档；named volume 位于 OrbStack VM 原生文件系统为 Docker 标准语义。

### 风险与回退

- 风险：E2E / 夹具大量依赖宿主路径读数据库，遗漏会导致门禁失败；实施时全量 grep `cbrowser.db` / `CBROWSER_DB_PATH`。
- 风险：备份改经容器执行后，API 运行中的一致性快照须使用 SQLite 在线备份语义，不得直接复制文件。
- 风险：Docker 错误脱敏规则遗漏某类凭据形态；以凭据形态矩阵测试覆盖。
- 回退：revert 实现 commit；旧库已改名保留，可手动放回原路径。

### 依赖与约束

- 无前置 task。
- 涉及 `compose.yaml`、`scripts/deploy.sh`；与同期其它修改这两个文件的 task 串行。

### Finalization 时更新的 blueprint

- `docs/blueprint/persistence.md`：控制面数据库存储位置、备份恢复与 SQLite 错误分类。
- `docs/blueprint/architecture.md`：数据目录与挂载拓扑。
- `docs/blueprint/supervisor.md`：Docker 错误脱敏与沙箱 compose service 命名。
- `docs/blueprint/decisions.md`：新增 ADR「控制面数据库移入 named volume」。
- `docs/blueprint/testing.md`：数据库访问方式变更后的 E2E / 夹具约定。
- `docs/specs/runtime_lifecycle.md`、`docs/specs/release_deployment.md`、`docs/specs/fingerprint_platform.md`、`docs/specs/access_control.md`：对应行为修订。
