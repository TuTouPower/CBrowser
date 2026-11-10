# Task spec

## 背景

Supervisor 动态创建的 Browser/Stream 沙箱容器既没有稳定的人类可读身份，也不属于 compose 项目：Docker Desktop 只能按 UUID 命名的独立容器逐个展示，无法与产品里的 Profile 对应。用户要求每个 Profile 有稳定可读编号（0001、0002…，永不复用），同一 Profile 的刷新/重启沿用同一编号，并把全部沙箱聚合到一个独立分组（`<prefix>-profiles`）。

Docker Desktop 的分组依据是 `com.docker.compose.project`。因此根因方案是：把编号做成 Profile 的持久化领域属性（DB 唯一列，创建时分配），由 API 传入 Supervisor，用于容器命名与标签；沙箱显式声明聚合项目标签；部署脚本把该派生项目识别为同一实例自有资源。

## 契约区

### 范围

- `profiles` 表新增唯一 `display_number`（迁移：现有 Profile 按 `created_at, id` 顺序回填 1..N；新 Profile 分配 `max+1`；删除后不复用、不重排）。
- API 的 Profile 响应与内部 runtime 响应暴露 `display_number`；Runtime Coordinator 启动请求携带 `profile_number`；Supervisor `StartProfileRequest` 必填 `profile_number`。
- Supervisor 用编号命名沙箱：`<prefix>-<NNNN>-browser` / `-stream`（4 位补零），并写 `com.cbrowser.profile-number`、聚合标签 `com.docker.compose.project=<prefix>-profiles` 与 `com.docker.compose.service=browser|stream`；同一 Profile 重建沿用同一编号与名称。
- 沙箱发现/停止/清理从容器标签恢复编号与归属，不依赖旧 UUID 命名；实例观察按标签查找 Browser，不再按名字拼接。
- `scripts/deploy.sh` 的 prefix 冲突检查把 `<PROJECT>-profiles` + sandbox 角色视为本实例自有；真实异项目仍拒绝。
- 前端在 Profile 列表/详情展示编号，使产品界面与 Docker 容器名可对应。
- 测试覆盖迁移回填/分配、API 字段、启动协议、命名与标签、部署冲突判定；真实部署验证。

### 非范围

- 不改 Profile UUID 主键、配置版本、网络名、UDP 端口或策略 helper 命名。
- 不按 Profile 拆分 Docker 分组，不提供编号手工重排。
- 不为旧 UUID 命名容器提供兼容（升级后需重建沙箱）。
- 不改 Docker Desktop 分组以外的工具行为。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：迁移后所有既有 Profile 获得唯一 `display_number`，按创建顺序为 1..N；新建 Profile 获得 `max+1`；删除 Profile 后其编号不复用、其余编号不变化。
- [x] AC-002：Profile 响应、内部 runtime 响应与 Runtime Coordinator 启动请求均携带 `display_number` / `profile_number`，类型一致且为正整数。
- [x] AC-003：Profile 启动后 Browser/Stream 容器名为 `<prefix>-<NNNN>-browser` 与 `<prefix>-<NNNN>-stream`，并带 `com.cbrowser.profile-number=<NNNN>` 与聚合标签 `<prefix>-profiles` / `browser|stream`；同一 Profile 停止再启动后编号与名称不变。
- [x] AC-004：compose 定义的 api/gateway/supervisor/caddy 仍归属 `<prefix>` compose 项目，标签与分组不受影响。
- [x] AC-005：存在 `<PROJECT>-profiles` 自有沙箱容器时 `scripts/deploy.sh` 不因 prefix 冲突拒绝部署；真实异项目占用同一 prefix 时仍拒绝。
- [x] AC-006：Profile 停止、重建与清理仍按既有归属标签工作：停止后 Browser/Stream 被删除；实例观察、启动、停止不再依赖 UUID 容器名。
- [x] AC-007：[deploy] 升级前运行的 Profile 停止→启动后：沙箱带新名称/编号/聚合标签，Profile 用户数据与配置版本不变，readiness 通过且可重新出图。
- [x] AC-008：[deploy] Docker Desktop 出现且仅出现一个 `<prefix>-profiles` 分组，包含全部运行中 Profile 的 Browser/Stream；前端 Profile 列表显示与容器名一致的编号。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001..006：可自动测试（迁移测试、API/协议 schema、adapter 命名与标签单测、fake Docker CLI 部署脚本）。
- AC-007：真实部署验证；替代验证为 `scripts/deploy.sh deploy` 后停止→启动 Profile，检查标签/名称/数据版本/readiness。
- AC-008：Docker Desktop UI 私有不作脚本断言；替代验证为 `docker inspect` 的唯一 `<prefix>-profiles` 标签集合 + 界面截图/人工确认，前端编号由组件测试与构建验证。

## 上下文区

- 来源：用户 2026-11-10 需求与方案选择（A：持久化编号；并入 t050）。

### 有意不测

- Docker Desktop 私有渲染细节（分组图标、排序）：非契约。
- 编号手工重排：非范围。

### 测试策略

- 单元：迁移回填/新分配/删除不复用；ProfileResponse/内部 runtime/StartProfileRequest schema；browser/stream 命名与标签；adapter 扫描从标签恢复编号；frontend Profile 列表编号渲染。
- 单元：fake Docker CLI 驱动 `scripts/deploy.sh` prefix 冲突（t027 夹具），覆盖自有 `<PROJECT>-profiles` 放行与异项目拒绝。
- 集成/E2E：真实拓扑启动 Profile 后 inspect 名称/标签；停止删除；重启编号不变。
- 部署：`scripts/deploy.sh deploy` → 停止→启动 Profile → 核对 AC-007/008。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。Docker Desktop 按 `com.docker.compose.project` 分组已由现有基础设施容器分组事实核对。

### 风险与回退

- 风险：旧 UUID 命名沙箱升级后不再被识别，需在部署后重建；实现中已让扫描把缺失编号的旧容器视为不可用并保留，由用户停止/启动完成迁移。
- 风险：伪 compose 项目被误用 `docker compose -p <prefix>-profiles down` 删除沙箱；文档明确其分组语义。
- 风险：部署冲突检查过度放行；保留异项目拒绝负例测试。
- 回退：revert 本 task 实现 commit；数据列保留但不影响旧版（旧版不读该列）。沙箱标签随重建消失。

### 依赖与约束

- 需要数据库迁移（0005），部署时自动升级；无前置 task。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md`：Profile 显示编号、沙箱命名与聚合 compose 标签契约。
- `docs/blueprint/testing.md`：迁移/命名/部署冲突与真实分组验证。
- `docs/specs/runtime_lifecycle.md`、`docs/specs/profile_management.md`：持久编号与沙箱命名语义。
