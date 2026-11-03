# p019 normal_exit_replay 仍写仓库 .scratch

- 来源：t018 遗留（`t018_test_f021`）
- 原始登记内容：`tests/integration/test_normal_exit_replay.py` 为满足 API 事件收敛仍需仓库内短路径，四个用例继续写 `.scratch/normal_exit_fix`。改到 `/tmp` 后 `desired_state` 无法收敛，原因未定位。后续应定位路径依赖并把测试状态移出仓库写入域。
- 处理：未开

## 分析基线

- 分析时间：2026-11-04T00:00:12+08:00。
- CBrowser 基线：main@bba5412b623729e3fb44d5c8b9d2ef150fb60604；工作区含既有前端未提交改动。
- 证据范围：源码、现行文档与 backlog 静态核对；未运行测试、复现实验或外部站点验证。
- 以下方案与验证条件均为分析建议，决策待定；原处理状态和目录归属保持不变。

## 当前情况与承接关系

- tests/integration/test_normal_exit_replay.py 四个用例仍使用固定仓库根 .scratch/normal_exit_fix，再附加随机后缀作为 data_root。
- 测试 UDS server 将 socket 路径转换为相对当前工作目录的路径。
- Supervisor 查询 Agent health 时，Linux 有 /proc/self/fd 路径分支，其他环境回退为相对工作目录路径。
- 这些源码支持“路径与环境存在耦合”的判断；不能仅凭源码证明改到 /tmp 后不收敛的根因。
- t024 A27 / AC-006 已明确承接本条，未知契约清单标为 UNVERIFIED-SPIKE：先定位路径依赖，再迁移测试数据根，并保留原退出收敛断言。

参考：[测试源码](../../../tests/integration/test_normal_exit_replay.py)、[Supervisor UDS 健康查询](../../../src/backend/cbrowser/supervisor/core.py)、[t024](../../tasks/t024_delivery_verification_evidence/task.md)。

## 分析意见

1. 保持本条有效，不再重复立项；t024 是已有承接，不代表问题已修复。
2. 优先核对实际传入 socket API 的完整路径、相对路径长度、cwd、平台差异和 Agent 是否真正可达。UDS 路径长度是候选解释，尚非已验证根因。
3. 需要把“socket 未连通”“health 未通过”“事件未转发”“API 拒绝事件”“状态收敛等待不足”分开观察，避免把所有结果归因于临时目录。
4. 不宜先把 /tmp 替换成功当成验收；目标是测试不再依赖固定仓库位置，且原正常退出、owner-loss 与离线恢复语义保持。
5. 后续实验仍须遵守允许写域约束，不能仅为满足标题而写入未授权系统目录。可比较允许写域内不同长度、层级的数据根，短 UDS 根的最终方案需明确适用环境。
6. 不通过放宽状态预期、删除用例、增加任意 sleep 或无限重试掩盖不收敛。

## 后续验证条件（候选，未执行）

- 保留原四个用例断言，建立数据根、UDS 路径、cwd 与平台分支对照。
- 先证明 UDS health 实际响应，再检查 Supervisor 事件、API 接纳与最终 desired_state。
- 正常退出收敛 stopped、owner-loss 保持异常语义、离线恢复不影响其他健康 Profile。
- 从不同工作目录执行仍能找到源码和测试资源，数据与 socket 无固定仓库路径依赖。
- fixture 持有并清理本次短路径、token 文件与 UDS server；失败也清理本次资源，不扩大删除范围。
- 记录根因和前后对照证据后，再判断能否闭环；本轮未复现、未运行测试。

## 相关边界

本条是测试隔离与路径可移植性问题，不等于生产正常退出链路一定失效。若后续证据指向生产 UDS 路径处理缺陷，再依据实际影响区分测试修复与产品修复，不以推测扩大当前结论。
