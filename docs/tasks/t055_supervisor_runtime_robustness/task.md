# Task spec

## 背景

2026-11-10 intensive review 在后端并发与 Supervisor 生命周期主题（第 5–23 项）列出一组边沿缺陷，adoption_decision 采纳为 A4–A13。共同特征：主路径正确，但异常、竞态、恢复与关停路径上收口不一致——清理异常会覆盖结果、恢复时没有健康证据就报 running、宽限被重置、异常穿透结果类型、静默无日志、同一 env 两套解析、socket 无属主校验即 unlink、watcher 互相关闭对方的流，且多处只在 lookup 层自证。

## 契约区

### 范围

- A4：`_run_policy_helper` 清理异常不覆盖校验结果；`_install_network_policy` 失败时先抓取 helper 日志（截断、脱敏）再删除 helper。
- A5：`forget_instance_events` 对 native exit 记录按 (profile_id, instance_id) 精确清理。
- A6：`_ensure_media_attachment` 对 gateway 解析失败转为状态返回，不抛异常；离线恢复消费返回值，非成功状态写日志（限频）。
- A7：恢复路径在 Agent 健康未知时不预置 running；注册宽限从恢复时刻起算，Gateway 不可达不重置宽限。
- A8：Browser 容器查找的非 NotFound 异常写日志；实例不匹配时报告全部异实例；删除不可达分支；补调用方级测试。
- A10：CDP 关码只在对端主动关闭时透传，且在本地 close 之前读取；`upstream.close()` 异常不阻断向客户端发送关码。
- A11：UDP mux 范围在进程启动时解析一次，protocol 校验、网络策略、分配器与 runner 共用；非法 env 启动即失败。
- A12：socket slot 清理前校验属主、类型与活跃性；socket root 长度在 Supervisor 启动时校验。
- A13：runner 两个 watcher 各自只关闭自己的流；container watcher 的停机竞态抽出为与 network 版对称的函数并补测试。

### 非范围

- 不改媒体子网分配（见 t051 A3）与网络运行时应用（见 t054）。
- 不改恢复的 label / API 双 fence 主逻辑。
- 不改 CDP 隧道的命令拒绝策略。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：policy helper 删除失败时，调用方仍得到原校验结果，失败仅记日志；网络策略安装失败时，日志包含 helper 输出摘要且不含凭据。
- [ ] AC-002：旧实例收尾清理事件时，同 Profile 新实例已登记的 native exit 记录保留，新实例终态按该记录分类。
- [ ] AC-003：Gateway 扫描失败时，媒体 attach 返回失败状态，收敛与恢复流程继续执行并写入 transport 观测；离线恢复遇到非成功状态时有日志。
- [ ] AC-004：恢复时 Agent 健康查询无结果，Profile 不报 running，CDP 代理在此期间拒绝连接；Agent 健康后转为 running。
- [ ] AC-005：恢复后 Gateway 持续不可达时，Stream 替换在恢复时刻起 90s 内触发，不因每轮收敛而顺延。
- [ ] AC-006：Docker API 故障导致 Browser 容器查找失败时有日志，且与「容器不存在」可区分；同 Profile 存在多个异实例容器时，观测报告全部异实例 id。
- [ ] AC-007：客户端先断开 CDP 连接时，不向客户端透传对端关码；Supervisor 以 4403 主动关闭时，客户端收到 4403；`upstream.close()` 抛错时客户端仍收到关码。
- [ ] AC-008：UDP mux 范围 env 为空时全部消费者使用默认值；非法值使 Supervisor 启动失败并给出明确错误；进程内各消费者使用的范围一致。
- [ ] AC-009：slot 中已有属于另一在跑实例的活跃 socket 时，新启动报冲突且不删除该 socket；socket root 过长时 Supervisor 启动即失败。
- [ ] AC-010：关停时 network watcher 收尾不关闭 container watcher 的流；container watcher 的停机竞态分支关流且不 pump，有测试断言。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试（fake Docker client / 注入异常的单元测试、CDP websocket 集成测试、runner 事件流单测）。

## 上下文区

- 来源：`docs/reviews/review_20261110_200842/adoption_decision.md` A4–A8、A10–A13（审阅原文第 5–14、16–23 项；第 15 项 A9 归 t060）。决策时未逐项复现，实施前按审阅给出的位置核实（`docker_adapter.py:336-360,1935-1937`、`core.py:433-448,631,866-890,1284-1292,1478-1500,1673-1677,1823-1872`、`automation_router.py:236-252`、`protocol.py:14`、`network_policy.py:63`、`udp_mux.py:22-40`、`runner.py:111-112,307-394`、`socket_root.py:32-131`）。

### 有意不测

- docker-py `containers.list` 抛 NotFound 的形态：库行为以空列表表示缺失，分支删除后无需测试。

### 测试策略

- 单元：每个 AC 至少一条触达生产逻辑的测试，使用 fake Docker client 注入异常与时序。
- 集成：CDP 关码透传用真实 websocket 链路。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- websockets 库在本地 close 之后 `close_code` 的取值语义：UNVERIFIED-SPIKE，实施时以最小 websocket 对端实验确认后再定读取点。

### 风险与回退

- 风险：恢复路径 running 判定收紧，可能延长恢复后可用时间；以 AC-004 的健康转换测试兜底。
- 回退：revert 实现 commit。

### 依赖与约束

- 与 t051（`docker_adapter.py`）、t054（`core.py` 网络链路删除）、t057（`core.py` 预览部分）存在文件重叠，按 `conflicts_with` 串行。

### Finalization 时更新的 blueprint

- `docs/blueprint/supervisor.md`：恢复 running 判定、注册宽限、UDP mux 配置单一来源、socket slot 校验。
- `docs/blueprint/automation.md`：CDP 关码透传语义。
- `docs/specs/runtime_lifecycle.md`：恢复与观测行为。
