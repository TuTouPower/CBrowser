# Task spec

## 背景

完整落实 docs/v2_architecture_plan.md 对应正式实施阶段的收尾切换：实现可回退完整数据迁移与备份恢复，把在用的 legacy 部署切换到 v2 正式部署，并移除 VNC 与原生桌面旧路径；t001全项技术验证通过前不实施。2026-11-02 按用户审批的 adoption（docs/reviews/review_20261102_201727）合并原 t011（移除 legacy）与原 t012 AC-004（真实部署到本机并冒烟）。

## 契约区

### 范围

- Alembic/迁移CLI、数据根备份恢复、旧字段/运行状态映射和隔离fixture真实演练；现有用户数据仅在明确批准具体数据根并验证可恢复备份后执行。
- 按计划17逐项删除旧VNC/RFB、租约、native-window、原生入口/脚本/packaging、config/docker/entrypoint.sh旧VNC与遗留进程清理逻辑、legacy后端（src/backend/main.py等）及其测试与失效依赖；正式切换到新API/前端/v2正式拓扑（t012产物），保留明确要求的旧CDP薄适配。
- 在当前电脑Docker完成v2正式部署并由本机Chrome冒烟，停用旧版容器。

### 非范围

- 不越过前置验证门禁，不静默缩减计划或改写验收标准；不处理与本阶段无关重构；不覆盖未获具体授权的用户数据或外部环境；外部镜像推送/公网发布不在本次范围。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：迁移前停止旧服务和浏览器并拒绝活跃写者；--dry-run 不修改源或目标，列出 Profile/Tag/Artifact 数量、旧字段映射、无效运行模式和文件校验，缺字段/路径冲突明确阻断。
- [ ] AC-002：计划15.2全部仍有效配置字段、标签/顺序、用户数据、Artifact、设置和运行事件迁移无丢失；旧运行模式与查看模式字段不再保留（v2仅Docker+WebRTC，见t016 A28）；新数据库可真实启动浏览器并保留Cookie/设置/内部页面恢复。
- [ ] AC-003：旧running与真实容器核对，initializing映射待检查，stopped保持desired stopped；不因旧DB标记自动假定容器存在，正常退出事件迁移后不触发误启动。
- [ ] AC-004：备份覆盖DB/settings/profiles/artifacts/runtime-events，校验后可恢复到独立空数据根；故障注入任一步失败时恢复旧DB和目录，源文件hash/数量与恢复结果一致，禁止不可恢复原地升级。
- [ ] AC-005：真实旧格式fixture包含各有效字段和文件，dry-run、成功迁移、重复执行、失败回滚、备份恢复均独立黑盒通过；用户实际数据操作需单独记录具体授权范围，不以演练代替实际迁移完成。
- [ ] AC-006：正式入口仅提供 /api/v1 和新WebRTC架构；旧内部ProfileCRUD和可选AUTH_TOKEN正式模式移除，旧CDP入口只转发新授权代理，不发布旧CDP端口。（原t011 AC-001）
- [ ] AC-007：vnc_manager/RFB代理/native-window/app_entry/原生启动脚本/packaging、legacy后端模块及相关依赖配置均移除，config/docker/entrypoint.sh不再包含旧VNC与遗留进程清理逻辑，源码、构建和文档不再引用失效运行链路，实际Docker+Chrome完整路径仍通过。（原t011 AC-002）
- [ ] AC-008：旧语义测试整项移除并逐项说明替代覆盖，新Runtime/媒体/输入/鉴权/恢复测试保持通过；不就地改旧测试预期来迁就实现。（原t011 AC-003）
- [ ] AC-009：全新环境与迁移fixture均可由正式入口启动/停止Profile、双页面WebRTC、文件/CDP自动化；无失效资源路径/路由，旧数据备份保留且可恢复。（原t011 AC-004）
- [ ] [deploy] AC-010：本次正式部署到当前电脑Docker，由本机Chrome访问；部署前核对版本/配置/凭据来源/数据根和回滚方案，实际Chrome冒烟并保存结果，旧版容器停用且数据备份可恢复；失败不盲重试或删除用户数据。（原t012 AC-004）

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-005中的用户实际数据迁移与AC-010的本机正式部署需用户单独授权并人工确认，保存操作记录与冒烟证据；其余AC可自动验证（迁移以真实旧格式fixture、故障注入与独立黑盒验证）。

## 上下文区

- 来源：docs/v2_architecture_plan.md（2026-10-27逐项核对）；t001 已完成并归档（docs/archive/tasks/t001_v2_runtime_validation），技术门禁已通过
- 2026-11-02 用户审批的 adoption（docs/reviews/review_20261102_201727/adoption_decision.md）：合并原 t011（AC-001~004 依次编为本task AC-006~009）与原 t012 AC-004（编为 AC-010）；R1（legacy后端与测试的问题）随本task删除legacy栈关闭；A48 已将旧版容器端口绑定到 127.0.0.1；同日用户决定直接停用旧版容器（`docker compose stop`，容器与数据根 `~/.cbrowser` 保留，供本 task 迁移使用）。

### 有意不测

- 公网与原生Linux x86_64：用户已豁免（NOT_RUN / USER_WAIVED）。

### 测试策略

- 真实SQLite旧数据库/目录fixture、文件hash、独立新旧进程、故障注入与可恢复备份；迁移破坏性变更由fullreview核对；切换与删除后以正式入口跑完整Docker+Chrome路径。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- UNVERIFIED-SPIKE：以前置task最终已验证协议/模型/镜像为准；现有原型不得直接视为正式契约。涉及原生Linux/公网/实际数据/外部发布时必须核实入口与授权。

### 风险与回退

- 风险：跨服务权限、并发恢复、凭证或数据一致性可能失败；真实数据迁移与切换影响在用环境；任何未验证行为不得凭配置字段或模拟通过。
- 回退：隔离worktree、测试数据根和容器资源；保留失败日志，回退本阶段产物。真实数据迁移前验证备份可恢复；切换失败时恢复旧数据根并重新启用旧版容器。

### 依赖与约束

- 必须先取得t009完成产物；所有正式实施继承t001全项通过硬门禁。公共文档/索引由主控串行收尾。

### Finalization 时更新的 blueprint

- docs/blueprint/persistence.md：迁移与回退契约；DOCKER_DEPLOYMENT.md：停机/备份/恢复与切换步骤；docs/blueprint/architecture.md：删除legacy描述。
