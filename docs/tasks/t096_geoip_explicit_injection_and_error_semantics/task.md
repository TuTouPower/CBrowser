# Task spec

## 背景

生产批量测速 88 个代理全部失败，真因非代理或网络：t094 把探测从 Supervisor 临时容器迁入 API 进程后，GeoIP 数据库路径靠隐式环境变量 `CBROWSER_GEOIP_DB`/`CBROWSER_GEOIP_CACHE` 传递，而这两个变量只配在 supervisor 服务、api 服务漏配。API 探测回显阶段成功拿到出口 IP，随后查国家时 `db_path=None`，抛 `geoip_db_missing`——88 个失败中 84 个是此因，仅 4 个是真实节点不可达。前端错误码表无 `geoip_db_missing`/`geoip2_missing`，兜底成通用「测速失败」，掩盖根因并把排查引向代理本身。

按开发铁律（架构至上、拒绝妥协、零兼容负担）分析：

- 架构至上：靠"某进程恰好配了某变量"才能工作是隐式耦合，不是架构；依赖应在构造时显式交付。
- 拒绝妥协：笼统失败文案吞掉故障语义，属用显示掩盖问题；失败原因必须可诊断。
- 零兼容负担：为旧沙箱形态服务的"GeoIP 路径只配 supervisor"假设应在破坏性重构时连根拔除，而非残留。

## 契约区

### 范围

- 依赖显式化：API 进程的探测 runner 在构造时显式注入 GeoIpLookup（或等价的数据库路径来源），不再依赖隐藏的全局环境变量决定行为；路径由调用方明确提供。
- 配置归位：API 服务声明并承载其探测所需的全部配置（GeoIP 缓存路径等）；compose 中按"谁用谁配"给 api 服务补齐所需变量，与 supervisor 自洽，不留跨服务隐式供给。
- 错误语义保真：为 `geoip_db_missing`、`geoip2_missing`、`geoip_lookup_failed` 等资源类失败定义正式本地化文案，与真实网络失败（`echo_unreachable` 等）区分；展示层呈现可诊断原因，不兜底成笼统「测速失败」。
- 验证闭环：补一条从 runner 构造注入到 GeoIP 查询的端到端测试，覆盖"路径未配置"与"路径已注入"两态；现有用假对象绕过真实路径查找的盲区须补测。
- 同步 OpenAPI/生成类型（若涉及契约）、i18n、blueprint/spec 文档与相关测试。

### 非范围

- 不重做测速作业的进度语义与并发（t095 已处理）。
- 不新增代理协议支持、不改变白名单回显/防泄露边界。
- 不在生产环境做破坏性验证；生产发布另行授权。
- 4 个真实节点不可达（`echo_unreachable`）属代理网络状况，按需单独处理，不在本 task 修复代理本身。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：API 服务测速探测能正确取得出口 IP 并完成 GeoIP 查询，不再因 `geoip_db_missing` 失败；生产上原本 84 个该类失败应转为成功（真实节点不通的除外）。
- [ ] AC-002：探测 runner 的 GeoIP 依赖在构造时显式提供，不依赖隐藏的全局环境变量；未配置路径时能被明确判定为资源类失败而非运行崩溃。
- [ ] AC-003：compose 中 api 服务具备其探测所需的 GeoIP 缓存路径配置，且与 supervisor 配置自洽；部署后 API 进程可解析到真实 mmdb 文件。
- [ ] AC-004：`geoip_db_missing` / `geoip2_missing` / `geoip_lookup_failed` 等资源类失败在前端有独立本地化文案，与「经代理无响应」等网络失败区分，不再统一兜底成「测速失败」。
- [ ] AC-005：测试覆盖"路径未注入 → 资源类失败"与"路径注入 → 成功完成 GeoIP 查询"两态，触达真实路径查找逻辑而非仅用假对象绕过。
- [ ] [deploy] AC-006：生产规模（约 88 代理）重新测速，GeoIP 类失败归零、测速结果可用，剩余失败仅为真实节点网络原因。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-002~005 可自动测试：单元/集成覆盖构造注入、两态失败语义、i18n 文案、真实路径查找。AC-001/006 涉及 API 进程在真实部署拓扑下解析 mmdb，须以隔离真实环境验证；云端以"注入真实 mmdb 路径的 runner 单测"替代，不冒充生产实测。

## 上下文区

- 关联 spec：docs/specs/proxy_management.md
- 受影响 spec：`docs/specs/gate_verification.md`、`docs/blueprint/architecture.md`、`docs/blueprint/domain.md`、`docs/blueprint/frontend.md`、`docs/blueprint/supervisor.md`；执行 finalization 时一并更新。
- 来源：p153（用户 2026-11-20 授权立项；独立子代理排查结论）；核实于 2026-11-20T21:26:11+08:00。生产 release decd8bd 作业 049e0ef6 实证 failed=88，其中 geoip_db_missing 84、echo_unreachable 4；mmdb 文件实际存在于 API 容器 /data/engine-cache/geoip/，仅路径未配。根因与解决方向已按开发铁律确认。

### 有意不测

- 真实公网代理节点可达性与订阅有效性：属 AC-006 [deploy] 与代理运维，云端不冒充实测。
- 测速进度/并发语义：t095 已覆盖，不在本 task 重复。

### 测试策略

- TDD 先红后绿：先写"路径未注入 → geoip_db_missing"与"真实 mmdb 路径注入 → 成功"两态失败测试，再驱动显式注入实现。
- 单元/集成覆盖构造注入、compose 配置自洽（配置解析测试）、前端错误码文案映射；前端 i18n 覆盖新增文案键。
- 黑盒在隔离真实拓扑按 AC-001/006 执行并留证。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无未核实外部契约。mmdb 文件位置、compose 配置键与错误码语义均已由子代理在生产核实。

### 风险与回退

- 风险：显式注入改动 runner 构造签名，影响所有构造点；compose 配置变更需重新部署才生效；错误码文案变更影响前端断言。
- 回退：保留旧构造路径的兼容期为零（按铁律不留兼容层），所有构造点一次性改到位；回退按 deploy.sh 既定口径执行，不丢观测历史。

### 依赖与约束

- 当前无 active/backlog task，无依赖与冲突需登记。
- 与 t094 的 runner/egress_probe、api/app.py、compose.yaml、i18n 共用文件，须单一实现 commit 完成。
- Browser/Stream 的 ADR 038 双栈策略与探测白名单不受影响。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md`：依赖显式注入原则，去掉对隐式全局环境变量的依赖。
- `docs/blueprint/domain.md`：资源类失败语义与可诊断错误分类。
- `docs/blueprint/frontend.md`：错误码本地化文案呈现。
- `docs/blueprint/supervisor.md`：compose 配置按谁用谁配、api 服务 GeoIP 路径归位。
