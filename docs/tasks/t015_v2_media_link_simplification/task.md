# Task spec

## 背景

2026-11-02 intensive review（docs/reviews/review_20261102_201727）确认 CBrowser 的部署包络是单机单人、同机 Chrome 访问，但媒体链路仍按多主机流媒体服务维护：coturn、TURN 凭证 24h/12h 轮换、同 PeerConnection 的 ICE 代次接管，后者依赖给 Selkies 2.1.0 私有 ABI 打补丁，并且是多条缺陷的来源。用户决策采纳 A42（证据门控的简化）及媒体链路相关的 A8、A9、A10、A11、A12、A16、A18、A26、A30、A34、A47。目标是最好的架构与最少的技术债，不考虑工作量。

## 契约区

### 范围

- 先以 spike 验证同机真实 Chrome 经 local 直连（不经 TURN）在全部会话场景可行；通过后删除 coturn、TURN 凭证生成与轮换、ICE 代次接管及 Selkies 私有 ABI 补丁，Gateway 收缩为 Agent 注册、信令路由与可见性/配额控制。
- Gateway 与 Stream Agent 的缺陷与加固：接入/注册拒绝顺序、心跳与捕获仲裁循环的异常隔离、控制面输入校验、信令限流、传输层帧上限、统一密钥读取、配置启动期校验。
- Stream 线协议契约完整化（按 action 判别的 payload 全部入契约并双向校验，FPS 单一权威）。
- 前端浏览器会话层（features/browser-session）：删除生产 adapter 中的测试钩子，宿主与 iframe 只保留生产契约；会话页运行时检查与诊断、监听器释放。
- 架构文档：ADR 记录单机单人部署包络与媒体链路决定，同步 blueprint、spec、计划修订块与指南状态。

### 非范围

- 不改 API 控制面、数据模型、Supervisor 与 Runtime Agent（归 t016）；不改前端外壳、profiles 页面与共享 API 客户端（归 t017）；不做测试体系整体整改（归 t018）；不迁移用户数据、不删除 legacy 栈。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] [deploy] AC-001：在不运行 coturn、不下发任何 TURN 凭证的拓扑中，同机真实 Chrome 对同一 Profile 的多页面连接、刷新、复制标签、关闭首个页面、断线 resume、后台暂停与恢复、视频/音频/键鼠与中文输入全部正常，证据写入 findings。
- [x] AC-002：运行时配置、协议契约与仓库中不再存在 TURN 凭证、凭证轮换、ICE 代次接管与对 Selkies 私有接口的补丁；Gateway 只承担 Agent 注册、信令路由与可见性/配额控制；对应配置项、夹具、测试与文档同步移除。
- [x] AC-003：Gateway 对 Viewer 接入与 Agent 注册的所有拒绝都在升级 WebSocket 与改动注册表之前完成，客户端收到可识别的拒绝，Gateway 内无残留 viewer 或 agent 条目，已注册的健康 Agent 不受影响。
- [x] AC-004：Stream Agent 的心跳与捕获仲裁在单次异常后继续按节奏工作，Gateway 不误驱逐仍在推流的 Agent；循环任务意外退出时告警并按退避重启。
- [x] AC-005：Gateway 控制面与信令入口：非法配额请求返回 400 且不下发；Viewer 信令失败按来源与 Profile 限流返回 429；超限 WebSocket 帧在传输层被拒绝；所有密钥文件经统一的权限与长度校验读取；心跳超时等配置非法时进程启动即失败并给出明确错误。
- [x] AC-006：Stream 线协议契约覆盖全部实际收发的 payload（按 action 判别），Gateway 与 Agent 收发两侧按契约校验，契约导出有漂移守卫测试；FPS 只有一个权威配置来源。
- [x] AC-007：生产前端 adapter 不再记录 DataChannel/WebSocket 报文，不暴露测试用全局对象；宿主与 iframe 只经有文档的生产契约交换会话统计；E2E 与单元测试通过测试自身注入的探针获得同等证据。
- [x] AC-008：浏览器会话页的运行时检查经统一 API 客户端：会话过期跳转登录，API 不可达显示带原因的 runtime_not_ready，Web Locks 不可用显示专门诊断；所有事件监听在完成与超时路径上都被释放。
- [x] AC-009：ADR 记录单机单人部署包络与媒体链路决定；blueprint、spec、计划修订块与媒体相关指南同新架构一致（含 architecture.md 章节编号、计划 §8.4/§19.3 替代标记、隔离分析指南标为 Superseded、上一轮 adoption_decision 的 D1 标为已决策）。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001：需真实 Chrome + OrbStack，可用 headless Chrome 自动化执行，人工核对音频与中文输入证据；结果写入 findings。
- AC-009：文档一致性以人工复核为主，结合 grep 校验不再引用已删除机制。
- 其余 AC 可自动测试。

## 上下文区

- 来源：docs/reviews/review_20261102_201727/adoption_decision.md 的 A42（用户决策 B）、A8、A9、A10、A11、A12、A16（架构/计划/指南/上轮 adoption 部分）、A18（adapter 部分）、A26（stream 协议部分）、A30、A34（browser-session 部分）、A47（用户决策 A）；对应 finding 见该文件映射。2026-11-02 核实。

### 有意不测

- 公网与原生 Linux x86_64 环境：用户已豁免（NOT_RUN / USER_WAIVED）。

### 测试策略

- spike 先行：在 .scratch 或正式 spike 目录用真实 Chrome（headless）+ OrbStack 跑完 AC-001 全部场景，结论入 findings 后再删除机制。
- 删除后保留并改写现有媒体 E2E（多观看者、可见性、resume、输入），以直连拓扑运行；Gateway/Agent 缺陷先写失败测试再修复。
- adapter 测试钩子迁移：E2E 由测试夹具在复制后的 Selkies index 中于 adapter 之前注入探针脚本，vitest 用测试内包装。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 同机 Chrome 经 local 直连在 AC-001 全部场景可替代 TURN：已由 s011/d026 在真实 Chrome + OrbStack 验证通过，见 `docs/spikes/s011_direct_media_validation/` 与 `docs/findings/d026_direct_media_local_only.md`；据此删除 TURN/ICE 机制。

### 风险与回退

- 风险：直连在某些场景（重连、可见性切换、多页面）不稳定；删除范围大，可能误删仍被引用的配置或测试夹具。
- 回退：spike 不通过即不删除；删除在独立 worktree 进行，失败保留分支与证据，不合入主干。

### 依赖与约束

- 无硬前置；与 t016 同改 docs/blueprint 与 schemas/，串行执行。Selkies 固定 2.1.0；所有浏览器测试 headless，不弹窗。

### Finalization 时更新的 blueprint

- `docs/blueprint/decisions.md`：新增单机单人部署包络与媒体链路 ADR
- `docs/blueprint/architecture.md`、`gateway.md`、`stream_runtime.md`、`security.md`、`frontend.md`：去除 TURN/代次机制，补测试钩子与宿主契约说明
- `docs/specs/webrtc_remote_display.md`：直连拓扑与协议契约
