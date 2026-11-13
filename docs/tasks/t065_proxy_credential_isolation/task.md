# Task spec

## 背景

代理凭据同时出现在 runner 的 --proxy-server 和 Browser 可读的 proxy_credentials.json；仅移走 argv 不足以隔离。受控认证组件需位于 Browser 容器之外，并消除共享父目录的间接泄漏。

## 契约区

### 范围

- 外置认证转发组件提供 Browser 可用的无凭据入口；移除 Browser 的代理凭据专用挂载及整个 runtime 父目录中同文件的可读性，秘密只挂到认证组件。
- 需要额外代理容器时纳入创建/分组/标签/网络白名单/readiness/reconcile/stop/重启/孤儿清理/资源计数，未配代理 Profile 仍保持 Browser+Stream。
- 真实验证 HTTP、HTTPS、SOCKS5 上游认证、DNS 行为与首包/407 往返；故障封闭且脱敏，不静默改变启动行为。

### 非范围

- 不实施 p078 的无代理强制出口、独立公网 IP 分配；Selkies Web 已有托管和完整性门禁只回归不重建。
- 不以 Browser 内多 UID 隔离满足秘密不可读；现有 UID 1000、cap_drop/no-new-privileges 不提供该边界。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] [deploy] AC-001：Browser 的 argv、/proc、ps、环境、日志、异常及全部可读挂载无代理凭据；包括移除专用 bind 后不能经 runtime 父挂载读取同一文件。
- [ ] [deploy] AC-002：实际引擎通过无认证本地入口使用 HTTP/HTTPS/SOCKS5 上游，特殊字符、IPv6 与 SOCKS 远端 DNS 语义正确，凭据不进入 Browser 或诊断。
- [ ] [deploy] AC-003：认证组件停止、认证拒绝、DNS/上游连接失败时代理 Profile 不回退宿主直连；创建失败、stop、重启与孤儿恢复不留无归属代理组件，未配代理模式保持原行为。
- [ ] [deploy] AC-004：相同拓扑/目标/样本下认证成功率不低于基线；报告首包延迟、407 往返与可观测协议差异，默认不接受超出测量噪声的性能退化或认证行为变化，若无法满足须带证据请求用户批准后修订 AC，不能按任意预算放行。
- [ ] AC-005：现有 Selkies Web 固定制品和 SHA256 校验继续生效，篡改资源在既有校验入口被拒，不新增 CDN。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-002：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-003：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-004：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-005：可自动测试，触达生产函数或实际工具入口。

## 上下文区

- 来源：2026-11-13 审阅复核：p082；docker_adapter.py 除代理凭据 ro bind 外还挂整个 runtime 目录；ro 只防写不防读。现行固定双容器假设需在此显式扩展；vendor 客户端已完成。

### 有意不测

- 非范围中的新增产品功能不作为本 task 验收；已声明 AC 不豁免。

### 测试策略

- 先在隔离真实 Docker/引擎验证凭据全路径不可读，覆盖专用 bind、父目录、环境与进程；仅日志脱敏不能证明隔离。
- 认证拓扑 spike 含三种上游协议、无凭据本地协议、egress 白名单与 DNS，故障注入覆盖第三容器全部生命周期。
- 复用分散在 vendor 安全、Selkies pin/asset probe/wheel cache 的完整性回归；认证延迟用同机重复样本报告噪声，不凭空要求绝对零开销。
- 按 docs/blueprint/testing.md 的 doctor_cmd/test_cmd/blackbox_verify 执行；本次仅改 backlog，创建校验不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 外置认证拓扑、上游协议/DNS、首包和 407 基线：UNVERIFIED-SPIKE，实际引擎与本地受控代理验证，并盘点所有双容器假设及父目录挂载；出现不可接受退化时再提交具体取舍，不预先制造用户无法回答的延迟 BLOCKING。

### 风险与回退

- 风险：跨模块/制品或状态变更需按上述负向测试与 spike 验证；产品 BLOCKING 未消除不得实施。
- 回退：回退本 task 的完整实现 release；涉及数据先停写者并从已验证成套备份恢复，禁止仅降级数据库或以旧兼容分支兜底。

### 依赖与约束

- 硬依赖和冲突以 progress.md 的 task.py 调度字段为准；不把文件重叠当硬依赖。plan 仅输出图上候选，不能替代 preflight；产品 BLOCKING 必须先确认，SPIKE 先验证并回填。

### Finalization 时更新的 blueprint

- docs/blueprint/architecture.md、docs/blueprint/supervisor.md：代理 Profile 条件第三容器与完整生命周期。
- docs/blueprint/security.md、docs/blueprint/testing.md：凭据挂载、协议/DNS、首包基线与失败封闭。
