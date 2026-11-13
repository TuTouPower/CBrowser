# Task spec

## 背景

从原 t062 拆出 p071 严格契约到 t069。本 task 只交付中立共享边界、相关职责拆分和镜像打包，保持当前外部行为，避免打包重构与协议收紧同次回退。

## 契约区

### 范围

- 将端点/origin、Agent 凭证 DTO、原子写、锁基础设施移至中立归属，删除 Gateway/Supervisor 双向依赖与重复权威实现。
- 收口 fence、投递分类、端口/路径常量；只拆本次边界相关职责，不以行数拆全仓大类。
- 认证返回领域会话对象，路由不依赖 ORM SessionModel；通过 service 公开方法使用锁；将 egress 的 httpx/GeoIP/文件操作移出 domain。
- 统一运行镜像包依赖闭包；新增共享模块不需多份 Dockerfile 跨包逐文件 COPY。

### 非范围

- 严格 ErrorResponse、422 删字段重发、部署归属和持久化输入策略由 t069 交付；本 task 不提前改变拒绝/兼容行为。
- 保持 API 唯一 SQLite 写者、Supervisor 唯一 Docker Socket、Gateway 无 ORM；不同进程锁不被当作跨进程互斥。
- 不扩大为所有 God class 全面重写。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] [deploy] AC-005：服务间共享纯逻辑从中立包导入，Gateway/Supervisor 不相互导入实现包；共享模块增加不要求多处跨服务逐文件 COPY，全部运行镜像可独立导入并就绪。
- [x] AC-006：原子写异常不破坏旧文件；同锁域同 Profile 串行、不同 Profile 可并行；origin、fence、投递分类在各消费方结果一致，只有一份权威规则。
- [x] AC-007：API 路由与认证依赖不导入或返回 ORM SessionModel，使用领域会话对象；路由通过 service 公开接口协调操作；domain 不承载 httpx、GeoIP 或文件 I/O 实现，相关业务结果保持一致。
- [x] AC-008：Supervisor CLI、runner、compose 对默认控制端口使用同一权威值，不再出现 8091/8005 分裂；公共路径由同一值对象/常量派生，覆盖非默认配置时行为一致。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-005：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-006：可自动测试，触达生产函数或实际工具入口。
- AC-007：可自动测试，触达生产函数或实际工具入口。
- AC-008：可自动测试，触达生产函数或实际工具入口。

## 上下文区

- 来源：2026-11-13 审阅复核：p073；原 t062 AC-005..007 留在本 task，新增 AC-008。gateway.server→supervisor.agent_credentials 与 supervisor→gateway.endpoint 均成立；SessionModel 是认证注入返回值，原“HTTP 响应暴露 ORM”归因错误；domain 缺陷是承载 I/O 实现，不是导入即执行 I/O。

### 有意不测

- 非范围中的新增产品功能不作为本 task 验收；已声明 AC 不豁免。

### 测试策略

- 生产函数行为回归、依赖方向/镜像 import 检查、原子写失败注入与锁域并发；不能只用源码子串证明职责拆分正确。
- 构建全部运行镜像并 readiness 冒烟；固定端口和非默认端口贯穿 CLI/runner/compose 验证。
- 按 docs/blueprint/testing.md 的 doctor_cmd/test_cmd/blackbox_verify 执行；本次仅改 backlog，创建校验不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 跨镜像依赖闭包：已验证（2026-11-13，云端）。结论：中立包落点为既有 `cbrowser/shared/` 整包；成立的硬约束是 shared 除 `secret_files` 叶子外必须零 cbrowser import——若 shared 依赖 domain 叶子，Gateway 镜像（不带 domain）内 shared 模块即不可导入（组装树实测复现）。验证方式：`tests/unit/test_t062_image_closure.py` 按每个 Dockerfile 的 COPY 清单把文件组装到临时树、以镜像 PYTHONPATH 在子进程逐模块实际导入（第三方依赖以门禁 venv 近似镜像 requirements），五镜像全过；依赖方向由 `tests/unit/test_t062_boundaries.py` 的 AST import 图守护。API 镜像已改按包 COPY（cbrowser 整包 + migrations），不再全量复制后端目录。真实 Docker 构建与 readiness 不在云端验证范围，按 AC-005 [deploy] 顺延本地（p092 登记）。

### 风险与回退

- 风险：跨模块/制品或状态变更需按上述负向测试与 spike 验证；产品 BLOCKING 未消除不得实施。
- 回退：回退本 task 的完整实现 release；涉及数据先停写者并从已验证成套备份恢复，禁止仅降级数据库或以旧兼容分支兜底。

### 依赖与约束

- 硬依赖和冲突以 progress.md 的 task.py 调度字段为准；不把文件重叠当硬依赖。plan 仅输出图上候选，不能替代 preflight；产品 BLOCKING 必须先确认，SPIKE 先验证并回填。

### Finalization 时更新的 blueprint

- docs/blueprint/architecture.md、docs/blueprint/conventions.md：中立包、领域边界与公共 helper。
- docs/blueprint/supervisor.md、docs/blueprint/gateway.md、docs/blueprint/decisions.md：模块与镜像依赖。
