# Task review t006（reviewer_focus: 测试）

- task：`t006_v2_gateway_auth_rtc`
- spec：`docs/tasks/t006_v2_gateway_auth_rtc/task.md`
- diff_anchor：`c33e55f77cb221510396628e792a08b905b2ebe0`
- target：`git -C '<repo>_t006' diff c33e55f77cb221510396628e792a08b905b2ebe0`
- round：1
- reviewed_at：2026-10-31T13:40:00+08:00

reviewed_scope: 8a0b74f272c14c47

## Findings

### t006_test_f001 - 基础设施测试中 coturn 测试容器启动逻辑多处重复

- 严重度：minor
- 锚点：代码质量与测试基础设施可维护性
- 位置：`tests/e2e/test_supervisor_core_e2e.py:188-225`, `tests/e2e/test_supervisor_recovery_e2e.py:241-278`, `tests/e2e/test_supervisor_offline_recovery_e2e.py:114-151`, `tests/e2e/test_supervisor_retry_e2e.py:147-184`
- 问题：由于 ADR 010 要求 Stream 运行时启动必须绑定 coturn，4 个既有 Supervisor E2E 测试文件中直接内联了近乎一致的 coturn 测试容器拉取、配置文件生成与容器启动代码（约 35 行代码直接重复 4 次）。目前功能和断言完全正常，但若后续 coturn 配置或参数变动，需在多处手工同步维护。
- 建议：可在后续测试重构中将 coturn 测试容器的创建与生命周期统一抽象为共享 fixture。

## 结论

- 前轮 finding 复核：无（Round 1 首轮审查）
- 改测方向复核：无「迁就实现」的改测。既有测试变更仅限于：1) 因计划修订 9.3 废弃 Gateway 聚合与下发 visibility_update 而删除失效协议片段（`test_stream_runtime_e2e.py`），新语义在 `test_gateway_ac007_visibility_e2e.py` 中补全覆盖；2) 为既有 API/Supervisor 测试补充真实认证上下文与必需的 coturn 容器，原有断言与业务逻辑完全保持。
- 本轮新发现：1 条（minor 1 条，blocking 0 条）
- 未进表的提示：
  1. 页面可见性触发手段评估：无头 Chrome 模式下切标签或最小化不派发原生 `visibilitychange` 事件。测试通过在页面上下文中覆盖 `document.visibilityState` / `hidden` 属性并派发标准 `visibilitychange` 事件，成功触发了 Selkies 官方客户端代码内的 `STOP_VIDEO` 与 `START_VIDEO` WebSocket 控制帧，并通过 Stream 容器日志与帧率/关键帧统计验证了底层视频捕获与传输的启停。该手段既满足了用户要求不弹窗的约束（d023），又完整驱动了端到端逻辑，替代是充分且可信的。
  2. 边界声明披露：AC-001 中“master token 不返回前端”因当前 Stream 尚未配置 Selkies 每 Profile token，目前为空满足（已登记 p004）；AC-006 自动化 Bearer Token 凭证管理已在此 task 交付并在内部控制面端点验证，外部统一 CDP 代理入口属于后续 t008 AC-002。
- 总体判断：AC-001 ~ AC-007 验收标准打勾真实可信，测试直接触达生产逻辑与真实 Docker/Chrome 环境，无假绿或危险模式，综合判定通过。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：`re_verified`。reviewer 独立执行 `tests/unit/test_auth_service.py` 与 `tests/integration/test_auth_api.py` 验证 Argon2id 存储与校验、登录 Cookie 属性（HttpOnly/Secure/SameSite=Strict）、写请求缺少 CSRF 报 403、WS 鉴权负例；并核对 `tests/e2e/test_gateway_ac001_auth_e2e.py` 真实 HTTPS Chrome 运行证据与响应无凭据泄漏。
- AC-002：`re_verified`。reviewer 独立执行 `tests/unit/test_stream_agent_protocol_v2.py`（计划 7.2 注册字段必填校验）、`tests/unit/test_stream_agent_lifecycle.py`（10s 心跳节奏、1/2/4/8/16/30s 退避计算与实际执行）、`tests/integration/test_gateway_signaling.py`（过期实例注册拒绝且不影响当前连接、未就绪 503 拒绝）。
- AC-003：`trust_prior`。双真实 Chrome 页面解码音视频、各自 tab_id、无锁并发键盘输入、关闭一页另一页持续出帧、Gateway SIGKILL 浏览器 PID 保持与重启后重连恢复，依赖主控 round7b 门禁日志与 basetemp 原始 evidence JSON。
- AC-004：`re_verified`。reviewer 独立执行 `tests/unit/test_rtc_config.py`（HMAC 凭证生成、24h/12h/6h 时间窗口计算）、`tests/integration/test_gateway_rotation.py`（新连接取当前代、Agent 确认接管才提交本代、报错退避重试）；并核查真实 Stream SDK 提交用例 `tests/e2e/test_stream_ice_commit_e2e.py` 与 `test_stream_rtc_config_e2e.py`。
- AC-005：`trust_prior`。真实无头 Chrome relay-only 双端 WebRTC、一代二代三代两次切换增量证明（视频+音频+字节增量且 remoteUfrag 匹配 offer_ufrag、同一 PC/Track 保持）、凭证损坏负例子进程非零退出，依赖主控 round7b 门禁日志与 basetemp 原始 evidence JSON。
- AC-006：`re_verified`。reviewer 独立执行 `tests/integration/test_auth_api.py` 与 `tests/unit/test_auth_service.py` 验证自动化独立 Bearer Token、无 Origin 允许、Cookie 不能代替自动化凭证、撤销立即生效、越权拒绝、审计无明文泄漏。
- AC-007：`trust_prior`。真实无头 Chrome 官方客户端 STOP_VIDEO/START_VIDEO 暂停与恢复、前后台帧率表现、捕获暂停与关键帧增量、Gateway 端点准确反映上报值，依赖主控 round7b 门禁日志与 basetemp 原始 evidence JSON。

coverage = 4 / 7 = 57.1%
建议合并前人工抽查 trust_prior 项。

verdict: PASS
