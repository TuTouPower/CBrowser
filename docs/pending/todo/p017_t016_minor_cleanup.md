# p017 t016 收尾 minor 清理

- 来源：t016 遗留（t016_code_f010/f018/f019）
- 原始登记内容：删除 `ProfileUpdateRequest` 中重复的 `launch_args` 归一化校验器，明确 explicit null 语义；把 `docs/blueprint/domain.md` 状态图中的 `failed` 改为 `error`，删除 `docs/blueprint/artifacts.md` 中 0755/0644 回退描述；校验 CDP 重连 rearm 的实际 `error` 响应后再置 `_last_rearm_ok=True`。
- 处理：未开

## 分析基线

- 分析时间：2026-11-04T00:00:12+08:00。
- CBrowser 基线：main@bba5412b623729e3fb44d5c8b9d2ef150fb60604；工作区含既有前端未提交改动。
- 证据范围：源码、现行文档与 backlog 静态核对；未运行测试、复现实验或外部站点验证。
- 以下方案与验证条件均为分析建议，决策待定；原处理状态和目录归属保持不变。

## 当前情况与承接关系

本条包含不同风险层级事项。“minor”是来源标题，不应据此降低 rearm 健康误报或 API 校验问题优先级。

|子项|源码或文档现状|现有 backlog 承接|
|---|---|---|
|launch_args 重复校验与 explicit null|ProfileUpdateRequest 同时包含严格 validate_updated_launch_arguments 与 normalize_launch_arguments；null 的处理需要按现行 PATCH 契约确定|t021 A2 / AC-001|
|状态图 failed 与领域 error 不一致|domain.md 表格写 error，状态图仍写 failed|t024 A23 / AC-002|
|Artifact 文档权限回退|artifacts.md 仍描述无法 chown 时回退 0755/0644，与 ADR 014 失败即报错矛盾|t024 A23 / AC-002|
|CDP 重连 rearm 未核对 ACK 即健康|cdp_proxy.py 重连发送 Browser.setDownloadBehavior 后立即设置 \_last_rearm_ok=True|t022 A3 / AC-001|

参考：[更新 DTO](../../../src/backend/cbrowser/domain/models.py)、[CDP manager](../../../src/backend/cbrowser/runtime_agent/cdp_proxy.py)、[领域文档](../../blueprint/domain.md)、[Artifact 文档](../../blueprint/artifacts.md)、[ADR 014](../../blueprint/decisions.md)。

## 分析意见

1. 四个子项均已有明确 task 承接，不宜再次独立立项。但 task 仍为 backlog、相关 AC 未勾选，承接不等于修复。
2. launch_args 应将新写入严格校验与历史读取过滤分开。移除重复校验时，不能顺带放宽新请求校验，也不能把 null 直接当成未提供字段。
3. rearm 需要匹配命令 ID 的成功 ACK 才能报告健康；error、无 ACK、超时及再次断线均应保持不健康。
4. 当前重连逻辑由唯一 reader 消费响应；不能在同一 reader 内等待需要自己继续读取才能完成的 Future。t022 A3 已明确这一约束。
5. 文档应对齐现行领域枚举与 ADR 014，而不是用过时文案解释实现。这里只记录偏差，不改写 ADR 或历史验收。

## 后续验证条件（候选，未执行）

- launch_args 分别验证未提供、explicit null、合法参数、非法参数；真实 HTTP 错误应符合 PATCH 契约，历史配置读取仍按既有规则过滤。
- rearm 分别验证成功 ACK、error ACK、无 ACK、断线与重连；健康状态变化应依赖实际确认，而非发送成功或 rearm_count 增加。
- 核对文档状态图与接口领域枚举、权限说明与生产 chown 失败策略。
- 待所有子项拥有对应实施与验证证据后，再判断本条是否具备闭环条件；本次保持未开。

## 关联入口

- [t021 控制 API 与 Artifact 契约](../../tasks/t021_control_api_artifact_contracts/task.md)：A2 / AC-001。
- [t022 Runtime 与 Gateway 可靠性](../../tasks/t022_runtime_gateway_reliability/task.md)：A3 / AC-001。
- [t024 交付验证与证据](../../tasks/t024_delivery_verification_evidence/task.md)：A23 / AC-002。
