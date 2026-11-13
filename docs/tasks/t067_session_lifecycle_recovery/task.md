# Task spec

## 背景

viewer 恢复与 launch/reconcile 同属会话生命周期治理。现有 client_tab_id/resume_key、desired-state 幂等与 registration grace 已存在，补断线只恢复媒体、时限治理、启动进度与恢复归因，不复制另一套控制面。

## 契约区

### 范围

- 保留 Profile/Browser runtime，信令中断按 backoff 恢复并仅在必要时替换媒体 peer；后台恢复重新启用音视频。
- 绝对会话期限、断线保活 TTL、viewer 链接 TTL 分离，idle 由授权 CDP/输入/在线 viewer 活动驱动；先 standby 停编码再按策略销毁。
- 复用幂等键、operation journal、现有 desired-state 与 reconcile，补并发启动、取消/失败清理及重启恢复证据；长启动进度、点击时占位 tab、适配器不匹配明确提示。
- 记录 releaseReason、viewer 帧率/瓶颈与恢复阶段；仅在配置 webhook 时签名投递并支持密钥轮换，密钥由用户提供，不添加默认秘密。

### 非范围

- 不改变已闭环 resume_key/token 淘汰语义与 ADR 007 并发输入；不新增 HLS/录制或公网 TURN。
- 不照搬 watchfiles/第二份状态存储与 30 秒固定全量轮询；原子写和锁基础设施由 t062 提供。
- 不把幂等重试失败解释为允许重复容器，不因关闭一个 viewer 销毁 Browser。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：信令断线与恢复不改变 Profile 身份、cookie、现有 tab 和 Browser runtime instance；必要时仅替换媒体 peer，仍存活媒体在信令中断期间不被主动停止，恢复首帧满足已确认预算。
- [ ] AC-002：反复重连不能延长绝对 deadline；断线保活与 viewer 链接到期互不续期，授权活动按已确认规则重置 idle；standby 保状态停编码，最终到期有 releaseReason。
- [ ] AC-003：同幂等键并发/重试得到同一操作结果，同 Profile 不重复创建 Browser/Stream；失败后按现行策略可安全重试，跨 payload 复用键明确冲突。
- [ ] AC-004：长启动阶段可查询并在前端显示；点击打开会话时预留 tab，失败/取消显示结果且不残留半成品容器、窗口或孤立 DB 行。
- [ ] AC-005：控制面重启后在已确认收敛窗口内恢复与 Docker 实际状态一致；只处理本实例标签资源，外国资源不清理，注册宽限不被误判失败。
- [ ] AC-006：适配器协议不匹配时显示明确升级提示；viewer 帧率、瓶颈、释放原因可按非敏感稳定标识查询，错误日志无 URL 凭据。
- [ ] AC-007：配置 webhook 后事件携带可校验签名、事件标识与时间，轮换窗口内可验旧/新签名，重放可识别；无配置时不向外部发消息。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；涉及真实 Chrome、引擎、Docker 或网络行为的 AC 使用隔离真实环境探针，不以 mock 结果替代。界面视觉补人工核验，第三方公网检查仅显式 opt-in。

## 上下文区

- 来源：`p079`、`p083`。2026-11-13 核实 router.py/服务已有 Idempotency-Key 和 resolve_operation_id，tests/unit/test_t056_idempotency.py、useProfilesQuery.actionkeys.test.tsx、test_api_subprocess.py 已覆盖键复用与意愿重试；Supervisor 已有锁、operation journal/reconcile，非整体缺位。现行 architecture.md 5.1/5.3/5.4 已明确 viewer 关闭不关闭 Browser，新增项必须在其上补测。

### 有意不测

- 不改变已闭环 resume_key/token 淘汰语义与 ADR 007 并发输入；不新增 HLS/录制或公网 TURN。：超出本 task 范围；其余已声明 AC 不豁免。

### 测试策略

- 故障注入：WS 静默、中断、媒体停帧、后台恢复、API/Supervisor 重启、重复 launch 与取消；验证 Profile 状态与容器身份不变。
- 使用可控时钟测三个 TTL/deadline/idle，避免固定 sleep；真 Chrome 测 tab 占位与恢复首帧。
- 签名与轮换使用运行期测试秘密；验证无配置不投递、重放和错误脱敏，不连接真实第三方 webhook。
- 项目门禁：按 docs/blueprint/testing.md 的 doctor_cmd / test_cmd / blackbox_verify 执行；本批创建仅验证文档结构，不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 绝对上限、断线 TTL、viewer TTL、idle 规则和默认启停值，以及首帧/对账窗口预算：UNVERIFIED-BLOCKING，先测现状恢复分布并给出配置方案，再由用户确认；不得因调研建议默认销毁现有长驻 Profile。
- 锁定 Selkies 媒体 peer 替换、信令离线保持与客户端恢复接口：UNVERIFIED-SPIKE，真链断线实验后定稿；若依赖私有补丁先完成 t063。

### 风险与回退

- 风险：新增时间治理可能误销毁长驻会话，取消可能与幂等提交竞争；默认策略与数据保留必须先确认。
- 回退：停用新治理后回退 release，已到期删除的状态只能从备份恢复；验证前不对现有 Profile 启用破坏性超时。

### 依赖与约束

- 保持本机 Docker/OrbStack 与唯一外部 Chrome 客户端边界；不复活 parked 条目。依赖建议见 progress.md；产品 BLOCKING 未确认前不可 start，SPIKE 先验证后回填。

### Finalization 时更新的 blueprint

- docs/blueprint/architecture.md、docs/blueprint/domain.md：viewer、媒体与会话三个时限和释放原因。
- docs/blueprint/supervisor.md、docs/blueprint/gateway.md：启动进度、重启对账与媒体恢复。
- docs/blueprint/security.md、docs/blueprint/testing.md：webhook 签名、协议匹配与恢复预算；同步 runtime_lifecycle/webrtc_remote_display spec。
