# p016 恢复 Supervisor 网络隔离与 Stream 配额端到端覆盖

- 来源：t015 遗留（review_test f007）
- 原始登记内容：t015 删除 coturn 时一并移除了 `tests/e2e/test_supervisor_infrastructure_network_e2e.py`（Gateway 动态加入媒体网络、跨 Profile 网络负向隔离、运行容器附着时清理拒绝、未知端点清理拒绝、中途失败原子回滚）与 `tests/e2e/test_stream_runtime_e2e.py` 的 control_proof 块（Supervisor quota 下发、客户端不能越过 FPS cap、布局不变、motion/static 帧率切换、Stream CPU policy）。同时恢复 Agent 替换测试中删除的 close 1001、conn_id 差异、下行回复与 Viewer 存活断言（t015_test_f012/f013）。这些行为与 TURN 无关，应在无 coturn 直连拓扑下恢复为端到端测试；由 t018 测试体系整改时纳入。
- 处理：未开

## 分析基线

- 分析时间：2026-11-04T00:00:12+08:00。
- CBrowser 基线：main@bba5412b623729e3fb44d5c8b9d2ef150fb60604；工作区含既有前端未提交改动。
- 证据范围：源码、现行文档与 backlog 静态核对；未运行测试、复现实验或外部站点验证。
- 以下方案与验证条件均为分析建议，决策待定；原处理状态和目录归属保持不变。

## 当前情况与承接关系

原始登记记录 t015 删除测试时遗留的覆盖缺口；其中“由 t018 纳入”是当时处理意向，不代表当前已经恢复。当前应按直连拓扑和实际行为逐项核对，不能把缺少旧文件等同于全部行为未覆盖。

|行为范围|静态核对结果|现有承接与剩余缺口|
|---|---|---|
|跨 Profile 网络隔离、IPv4/IPv6 策略与启动 gate|已有 namespace、IPv6、策略失败 E2E 源码；这些文件存在不代表本轮运行通过|复用有效覆盖；另核对 Gateway 动态附网和原基础设施生命周期场景|
|运行容器仍附着时拒绝清网、未知端点拒绝清理、中途附网失败回滚|本轮未找到覆盖全部行为的明确现行验收映射|保留为独立核对项，不能因其他网络测试存在而关闭|
|Supervisor 配额下发至实际 Stream|资源 monitor E2E 使用 deliver 回调记录投递；Gateway 集成测试验证控制消息，但两者不能合成完整画面证据|t024 A25 / AC-004 已要求真实 GatewayControlClient 与 Gateway 链路；实际 Stream/Chrome 限帧仍需明确证明|
|客户端不能越过 FPS cap、布局保持、motion/static 切换与 CPU policy|资源算法、容器采样、媒体画面属于不同证据层级|t022 A48 / AC-015 涉及配额输入规则，不能替代本条全部实际画面验证|
|Agent 替换后的连接与存活语义|现有替换测试检查旧 Viewer 关闭及新 Viewer 上行；未完整恢复原登记列出的精确断言|close 1001、conn_id 差异、下行回复和后续 Viewer 存活仍需逐项映射；其他测试中的相似断言不能替代替换场景|

参考：[t024](../../tasks/t024_delivery_verification_evidence/task.md)、[t022](../../tasks/t022_runtime_gateway_reliability/task.md)、[资源 monitor E2E](../../../tests/e2e/test_supervisor_resource_monitor_e2e.py)、[Gateway signaling 集成测试](../../../tests/integration/test_gateway_signaling.py)。

## 分析意见

1. 本条仍有价值，优先保障隔离、清理保护与配额完整链路；它属于测试可信度和回归保护，不宜只按补回文件处理。
2. 应建立“原行为 → 现行测试 → 实际触达组件 → 证据缺口 → 承接 task”的矩阵。现有测试已覆盖的部分保留，不重复建设。
3. 以 ADR 009 的 namespace 策略和 ADR 013 的同机直连为现行边界；不恢复 coturn 或旧 TURN 网络假设。
4. 当前 t024 只明确承接部分内容，不能把本条整体记为已转办或已完成。现有 backlog 关系是分析记录，不改变其范围、依赖或状态。

## 后续验证条件（候选，未执行）

- 网络负向验证应有同条件正向基线；拒绝来自内核策略，不能由应用按对端来源过滤制造。
- 附网、清网和回滚验证应检查真实 Docker 资源归属与残留；未知资源保持保护。
- 配额证据应贯通 Supervisor、Gateway、Agent 与真实 Chrome 帧数，并分别记录资源采样和画面表现。
- 替换场景应证明旧连接按契约结束，新连接双向通信有效且持续存活；超时、异常关闭不能被宽泛断言吞掉。
- 未执行、环境不足或只覆盖组件层的场景应分别标识，不能用测试文件存在或局部通过宣称全部恢复。

## 依据入口

- [现行测试约定](../../blueprint/testing.md) 的 Supervisor 阶段验证明确要求网络正负对照，并区分资源算法、真实采样与实际画面。
- tests/e2e/test_supervisor_namespace_policy_e2e.py、test_supervisor_ipv6_policy_e2e.py、test_supervisor_policy_failure_e2e.py、test_supervisor_orphan_helpers_e2e.py。
- tests/integration/test_gateway_control.py 与 tests/integration/test_supervisor_gateway_client.py 提供组件契约入口，不代表本条整链路已通过。
