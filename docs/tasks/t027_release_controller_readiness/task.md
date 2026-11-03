# Task spec

## 背景

deploy_v2.sh 重复构建 API、覆盖 release env、compose up 后无条件重启 Caddy，并直接打印成功。容器启动不等于运行 Profile 信令可用。发布应消费 t026 单一收敛与 readiness，避免脚本再实现网络编排。

## 契约区

### 范围

- 构建并固定全部发布镜像身份，保存上一版 release env 和失败诊断；API/Gateway/Supervisor 增加匹配实际能力的健康检查。
- 用有界 compose --wait、认证 reconcile_all/readiness 与逐 Profile 验收组成幂等发布流程；只有配置变化才重建相关 Caddy。
- 提供明确、可演练的版本回退与运行说明；凭证来自用户提供的安全来源，不打印管理员密码或密钥，不引入默认 secret。

### 非范围

- 不重复实现 Docker 网络附着或注册恢复；不在云端实际发布，不操作用户现有服务/数据。
- 不新增远程发布平台、集群编排、Gateway 双协议兼容或数据回滚。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：成功 release manifest/env 固定 API、Gateway、Supervisor、Browser、Stream 与 Caddy 使用的镜像身份及配置；生成中途失败不覆盖上一份有效 release，重复构建/部署没有无条件额外重启。
- [ ] AC-002：健康检查失败、服务不 ready、某活跃 Profile 附着/策略/当前实例注册不满足时，脚本在明确截止时间内非零退出并输出脱敏逐 Profile 诊断；这些失败绝不打印成功。
- [ ] AC-003：只有服务健康且 t026 readiness 确认全部 desired=running Profile 收敛后才返回成功；调用显式收敛入口但脚本自身不执行网络编排或停 Browser。
- [ ] AC-004：连续相同配置发布幂等，未变化 Caddy 不被无条件 restart；配置变化可重建；API 只构建一次。
- [ ] AC-005：选择上一版 release env 可恢复上一版基础设施镜像与配置，不删除当前 Browser、Profile 数据或数据库；回退后仍执行同一 readiness 验收，不对状态未知报成功。
- [ ] AC-006：缺失凭证或发布前提时先失败并列缺项；不生成公网默认凭证、不打印密码/token，脚本/日志/manifest 均不含秘密真值。
- [ ] AC-007：shell/配置验证和受控 Docker CLI/HTTP 测试覆盖成功、超时、部分失败、重复发布及回退；交付真实演练步骤和现场保存规则给 t032。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；AC 中“目标探针/用例交付”只验入口、断言、报告和收集，不表示已完成目标实跑。真实环境行为执行只在 t032 判定。

## 上下文区

### 执行环境与参考来源

- 执行环境：云端 Muse。完成实现、触达生产逻辑的 unit/integration、可用的普通 Chromium 测试，以及可收集的真实环境用例和逐项运行说明。不要求访问宿主 Mac、OrbStack、用户局域网或真实 CloakBrowser/Stream 镜像；这些执行义务集中到 t032。本 task 的 AC 只验云端交付，不把模拟结果、collect-only、skip 或历史 trust_prior 当作目标环境 PASS。代码交付完成不表示目标环境已验收；t032 通过前不得据此发布或宣称指纹安全。

- ego-lite 参考仓库：https://github.com/citrolabs/ego-lite ；固定研究基线：https://github.com/citrolabs/ego-lite/tree/12407167f84a58af24044f072868051952131491 。云端可直接读取公开源码，无需本机目录。其 AGENTS.md 明确只开源 harness/Skill，浏览器本体与 globalThis.ego 原生绑定闭源；只能借鉴公开实现与故障案例，不依赖原生绑定，不照搬合成事件兜底，不将上游效果当成本项目证据。

- 来源：p034（发布部分）；2026-11-04，main@c6a9322 核实。当前 scripts/deploy_v2.sh API docker build 连续出现两次；up -d 后无条件 restart caddy，随后输出 URL 与管理员密码，未查询活跃 Runtime。compose.yaml 缺少发布所需健康检查。本轮只读，不执行任何发布。

### 有意不测

- 宿主 Mac/OrbStack、目标 CloakBrowser、真实媒体/X11/指纹站点：当前 task 执行端为云端 Muse，统一由 t032 执行；不得记为 PASS。

### 测试策略

- 受控 Docker CLI 与 readiness 服务验证命令顺序、退出码、deadline、env 原子替换及回退；必须执行生产脚本，不能仅 grep 文本。
- 静态 shell 检查与 Compose 配置渲染不打印秘密；真实冷构建/重复发布/回退交 t032。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无；发布控制契约由 t026 提供，实际 Docker Compose 版本与镜像构建条件在 t032 前置检查。

### 风险与回退

- 风险：错误 release env 可能混用版本；失败后自动重试可能覆盖现场。
- 回退：保留上版不可变 release 及当前失败状态，显式选择上版重部署并重新验收；不自动重试非幂等发布或回滚数据。

### 依赖与约束

- 硬依赖 t026，需其执行结果已进入本 task 基线。
- 云端/本地边界遵循“执行环境与参考来源”；真实执行义务只在 t032 判定。

### Finalization 时更新的 blueprint

- docs/blueprint/architecture.md：发布与运行时边界。
- docs/blueprint/testing.md：健康检查、收敛验收和回退演练。
