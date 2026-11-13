# Task spec

## 背景

控制面兼容分支与跨服务纯代码归属混乱构成同一模块边界整改。错误解析、归属判定、输入校验与基础设施 helper 应只有一个权威实现；镜像不应为跨包 import 维护逐文件补丁。

## 契约区

### 范围

- 删除旧错误形状、裸文本兼容读取与 422 删字段重发，非规范下游响应转为显式协议错误。
- 部署/资源归属仅凭非空 instance-id；删除无标签或未配置时的 prefix/project 认领。严格输入校验替代历史行静默过滤、多参数别名及死输出；对合法可空业务字段先核实语义，不因 legacy 注释直接删除。
- 中立包承载共享端点、origin、凭证 DTO、原子写及锁基础设施；保留各服务独立实例与锁域，不能把不同进程锁误当跨进程互斥。
- 收口 fence、投递分类、默认端口/路径，拆开现有大类中与上述边界相关的职责；HTTP 不使用 ORM 类型或 service 私有属性，domain 不承担 httpx/文件 I/O。统一镜像打包并守护依赖方向。

### 非范围

- 不改变 API 唯一 SQLite 写者、Supervisor 唯一 Docker Socket、Gateway 无 ORM 等权限边界。
- 不创建兼容层，不改变数据库降级禁令，不重建已存在的幂等与 reconcile。
- 不按文件行数做无关重构；不清除 gitignored 本地部署数据。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：下游合法 ErrorResponse 保留 error/message/retryable/details；旧 detail、裸文本、缺失必填字段产生可观测协议错误，不再被当作有效业务结果。
- [ ] AC-002：observed-state 返回 422 时同一次上报只发送一次，不丢弃 browser_product/browser_user_agent 重试；失败保持可观测且不会伪报收敛。
- [ ] AC-003：缺失、不匹配或空 instance-id 的容器/网络不会被认领或删除；部署身份缺失时在资源变更前失败，匹配身份仍可恢复与清理。
- [ ] AC-004：非法持久化 launch_args、旧参数别名与缺少必要身份的会话输入被明确拒绝；当前合法 locale/timezone 自动推导语义不被误删；network_config CLI 不再输出无消费方字段。
- [ ] AC-005：Gateway、Supervisor、API 与部署工具只从中立模块导入跨服务纯逻辑；增加共享模块后无需向多个 Dockerfile 添加跨服务逐文件 COPY，全部运行镜像可独立导入并启动。
- [ ] AC-006：原子写失败注入不破坏旧文件；同锁域同 Profile 串行、不同 Profile 可并行；origin、fence、投递分类在全部消费方产生一致结果且无重复权威实现。
- [ ] AC-007：HTTP 响应保持声明 DTO 形状，不直接暴露 ORM 或访问 service 私有锁；domain 模块导入不触发网络或文件 I/O。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；涉及真实 Chrome、引擎、Docker 或网络行为的 AC 使用隔离真实环境探针，不以 mock 结果替代。界面视觉补人工核验，第三方公网检查仅显式 opt-in。

## 上下文区

- 来源：`p071`、`p073`。2026-11-13 核实 runtime_coordinator.\_downstream_error_text、gateway_client 旧 detail、core.py 422 重发、network_spec.network_ownership_matches、DockerAdapter.\_owns_deployment、deploy.sh 缺标签豁免；确认 Supervisor→gateway.endpoint 与 Gateway→supervisor.agent_credentials 双向依赖及 Dockerfile 补 COPY。profile_locale 的 None 同时承载自动推导，须逐调用方辨析。

### 有意不测

- 不改变 API 唯一 SQLite 写者、Supervisor 唯一 Docker Socket、Gateway 无 ORM 等权限边界。：超出本 task 范围；其余已声明 AC 不豁免。

### 测试策略

- 先复现严格契约、资源归属和输入校验缺口，扫描对称调用方；测试须调用生产函数。
- 补 import 方向与镜像导入门禁、原子写失败与锁并发测试；复用 test_t051_supervisor_identity.py、test_t056_coordinator_errors.py、network_policy 和服务层集成测试，真实六镜像构建及 readiness 冒烟。
- 项目门禁：按 docs/blueprint/testing.md 的 doctor_cmd / test_cmd / blackbox_verify 执行；本批创建仅验证文档结构，不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 跨镜像共享包最小依赖闭包：UNVERIFIED-SPIKE，执行期在隔离构建环境做全部服务 import/readiness 探针，确定包边界后删除旧落点。

### 风险与回退

- 风险：错误契约收紧、资源归属与打包同时变化可能导致拒绝启动或误清理；负向归属测试和无资源变更预检优先。
- 回退：停止新服务后回退本 task release；先验证数据备份可恢复，不恢复无标签资源自动认领逻辑，不自动删除孤儿资源。

### 依赖与约束

- 保持本机 Docker/OrbStack 与唯一外部 Chrome 客户端边界；不复活 parked 条目。依赖建议见 progress.md；产品 BLOCKING 未确认前不可 start，SPIKE 先验证后回填。

### Finalization 时更新的 blueprint

- docs/blueprint/architecture.md：跨服务依赖、资源归属与严格协议边界。
- docs/blueprint/conventions.md：共享模块、原子写与单一 ErrorResponse；移除混版本兼容表述。
- docs/blueprint/supervisor.md、docs/blueprint/gateway.md：拆分后的模块职责与镜像打包。
- docs/blueprint/decisions.md：记录直接替换旧路径的 ADR。
