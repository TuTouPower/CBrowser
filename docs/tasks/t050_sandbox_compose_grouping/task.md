# Task spec

## 背景

Supervisor 动态创建的 Browser/Stream 沙箱容器不属于 compose 项目，Docker Desktop 只能把它们与基础设施分组分离地逐个列出；Profile 越多越难辨认。用户要求把所有 Profile 沙箱聚合到一个独立分组（`<prefix>-profiles`），同时不改变部署 prefix 冲突判断、清理与隔离语义。

Docker Desktop 的分组依据是 `com.docker.compose.project` 标签；基础设施容器已由 compose 提供该标签，沙箱没有。因此本 task 的根因方案是：为沙箱容器显式声明聚合项目标签，并让部署脚本把该派生项目识别为同一实例的自有资源。

## 契约区

### 范围

- Supervisor 创建 Browser/Stream 容器时写入聚合标签：`com.docker.compose.project=<prefix>-profiles`、`com.docker.compose.service=browser|stream`；保留全部既有 `com.cbrowser.*` 归属标签。
- `scripts/deploy.sh` 的 prefix 冲突检查把 `<PROJECT>-profiles` 项目、且 `role=browser|stream` 的容器视为本实例自有沙箱，不触发“prefix 被其他实例占用”拒绝；真实异项目仍拒绝。
- 单元/集成测试覆盖标签契约与部署冲突判定；真实部署验证分组呈现与沙箱重建。

### 非范围

- 不按 Profile 拆分分组，不引入每 Profile 一个伪 compose 项目。
- 不改 media network、UDP 端口、策略 helper、其它 `com.cbrowser.*` 标签语义。
- 不改真实 compose 服务（api/gateway/supervisor/caddy）的项目归属。
- 不为 Docker Desktop 之外的工具提供分组兼容。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：Profile 启动后，其 Browser 与 Stream 容器同时带 `com.docker.compose.project=<prefix>-profiles`，并分别带 `com.docker.compose.service=browser` / `stream`；既有 `com.cbrowser.*` 归属标签保持不变。
- [ ] AC-002：compose 定义的 api/gateway/supervisor/caddy 容器仍归属 `<prefix>` compose 项目，其标签与分组不受本 change 影响。
- [ ] AC-003：存在 `<PROJECT>-profiles` 自有沙箱容器时，`scripts/deploy.sh` 的 prefix 冲突检查不拒绝部署；存在真实异项目占用同一 prefix 时仍拒绝启动。
- [ ] AC-004：Profile 停止、重建与清理仍按既有归属标签工作：停止后 Browser/Stream 容器被删除，新增聚合标签不改变扫描、清理与 fail-close 判定。
- [ ] AC-005：[deploy] 对升级前已在运行的 Profile 执行一次停止→启动，重建后的 Browser/Stream 带聚合标签，Profile 用户数据与配置版本不变，readiness 通过且可重新获得画面。
- [ ] AC-006：[deploy] Docker Desktop 容器列表出现且仅出现一个 `<prefix>-profiles` 分组，包含全部运行中 Profile 的 Browser/Stream；不出现每 Profile 一个的额外分组。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001、AC-002、AC-003、AC-004：可自动测试（标签断言、fake Docker CLI 驱动部署脚本、现有停止/清理测试）。
- AC-005：需真实部署与 Docker 环境；替代验证为真实 `scripts/deploy.sh` 部署后停止→启动该 Profile，`docker inspect` 校验标签、API 校验配置版本、readiness 校验就绪。
- AC-006：Docker Desktop UI 呈现无法脚本断言；替代验证为 `docker inspect` 确认唯一 `<prefix>-profiles` 项目标签集合 + 实际界面截图/人工确认。

## 上下文区

- 来源：用户 2026-11-10 需求与问答结论（Docker Desktop 仅按 `com.docker.compose.project` 分组；沙箱为动态创建故无项目标签）。

### 有意不测

- Docker Desktop 私有渲染细节（分组图标、排序）：非契约，只验证标签与唯一分组事实。

### 测试策略

- 单元：`container_spec`/adapter 构造 Browser/Stream 容器时标签包含聚合项目与 service；真实名称与归属标签保持。
- 单元：用 fake docker CLI 驱动 `scripts/deploy.sh` 的 prefix 冲突检查，覆盖自有 `<PROJECT>-profiles` 放行与异项目拒绝（沿用 `test_t027_release_controller.py` 的 fake Docker 模式）。
- 集成/E2E：真实拓扑启动 Profile 后 `docker inspect` 校验 browser/stream 标签；停止后确认容器删除。
- 部署：`scripts/deploy.sh deploy` 成功后再对该 Profile 停止→启动，核对 AC-005/006。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。Docker Desktop 分组依据 `com.docker.compose.project` 已由现有基础设施容器分组事实核对；本 task 只依赖标签契约。

### 风险与回退

- 风险：伪 compose 项目可能被误用 `docker compose -p <prefix>-profiles down` 删除沙箱；文档与命名需明确其只读分组语义。
- 风险：部署冲突检查若过度放行，可能放过真实异项目占用；测试必须保留异项目拒绝的负例。
- 回退：revert 本 task 实现 commit；下次沙箱重建自动消失聚合标签，不影响数据。

### 依赖与约束

- 无前置 task。仅改 Supervisor 容器标签与部署脚本判定，不改容器生命周期与数据模型。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md`：Supervisor 沙箱容器标签契约（聚合 compose 项目 `<prefix>-profiles` 与 service）。
- `docs/blueprint/testing.md`：部署 prefix 冲突检查对自有沙箱伪项目的覆盖与真实分组验证。
