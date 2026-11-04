# Task spec

## 背景

容器启动不等于运行 Profile 信令可用，现行发布链路多处假成功或不可回退：

- `scripts/deploy_v2.sh`：API 镜像连续构建两次（:21、:23）；`compose.env` 非原子覆盖且只固定 Browser/Stream/Supervisor 镜像 ID（:25-35）；`up -d` 后无条件重启 Caddy（:37）；末尾打印管理员密码（:40）；缺失时自动 `openssl rand` 生成全部 5 个 secret（:9-14）。
- `compose.yaml`：api/gateway/supervisor 的 `image:` 写死 `cbrowser-*:deploy` 且带 `build:` 块（:5、:28、:55），切回旧 env 仍用最新 tag，`up` 可能触发构建；无健康检查；写死项目名、容器名、prefix、edge 网络、数据目录与端口（:1、:9、:32、:37、:59、:79、:92、:106），无法并存第二个隔离实例。若第二套栈沿用 prefix `cbrowser`，Supervisor 会把生产 Profile 视为 API 404 孤儿并 teardown（`core.py:468-475`）。
- 健康：Gateway 没有健康路由（`gateway/server.py:744-757`）；Supervisor `/supervisor/v1/health` 需 token（`control_server.py:90`），且控制面在初始扫描完成后才启动（`runner.py:161-185`）。
- 构建上下文：Browser/Stream 没有 `Dockerfile.dockerignore`，`docker build -f ... .` 把含 `data/` 与 `config/deploy/secrets` 的仓库根发送给 daemon；`test_docker_build_contexts.py:128-133` 对缺失 ignore 文件静默跳过。
- 文档：`DOCKER_DEPLOYMENT.md:39` 声称 `*-deploy` 标签可回滚，实际每次覆盖同名 tag 与 `compose.env`，没有上一版 release。

发布应消费 t026 的单一收敛与 readiness，脚本不再实现网络编排。

## 契约区

### 范围

- 发布构建：每个镜像按当前源只构建一次并打本 release 不可变标签保留；全部运行时镜像构建上下文受 ignore 规则限制。
- release manifest/env：以不可变 ID 固定 API、Gateway、Supervisor、Browser、Stream、Caddy 全部镜像，记录 compose、Caddyfile、前端产物指纹、数据库迁移版本与 readiness 能力；原子写入并保留上一份有效 release；compose 全部服务镜像改为读取 release 变量，`up` 不构建。
- 健康检查：API、Gateway、Supervisor 增加匹配实际能力的 compose 健康检查；Gateway 新增健康路由；Supervisor 存活判定不被初始扫描阻塞、不需要宿主机持有 secret。
- 发布流程：有界 compose `--wait`，再经 `docker compose exec` 调用 t026 的 reconcile_all 与 readiness 做逐 Profile 验收；只有配置变化才重建相关服务（含 Caddy）。
- 回退：显式选择上一 release 重部署并重新验收；目标 release 不具备 readiness 能力或迁移版本低于当前数据库时拒绝。
- 凭证：管理员密码由用户提供，缺失即失败并列缺项；容器间内部密钥首次缺失时随机生成、0600 保存、永不打印；输出只提示密码文件位置。
- 实例隔离：发布实例身份（compose 项目、容器名、资源 prefix、edge 网络、数据根、secrets 目录、HTTPS 端口）参数化，供 t032 在同一 daemon 起独立测试实例；prefix 冲突时启动前拒绝。
- 更新 `DOCKER_DEPLOYMENT.md` 的升级、回退与凭证说明。

### 非范围

- 不重复实现 Docker 网络附着或注册恢复；不在云端实际发布，不操作用户现有服务/数据。
- 不新增远程发布平台、集群编排、Gateway 双协议兼容、数据回滚或降级迁移。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：成功发布的 release manifest/env 以不可变 ID 固定 API、Gateway、Supervisor、Browser、Stream、Caddy 全部镜像，并记录 compose、Caddyfile、前端产物指纹与数据库迁移版本；每个镜像本次只构建一次，`up` 不触发构建；生成或部署中途失败不覆盖上一份有效 release，上一 release 的镜像仍存在。
- [ ] AC-002：全部运行时镜像的构建上下文受 ignore 规则限制，`data/`、`config/deploy/secrets`、`.scratch` 不进入任何构建上下文；任一运行时镜像缺失 ignore 规则时测试失败而非跳过。
- [ ] AC-003：API、Gateway、Supervisor 具备匹配实际能力的 compose 健康检查，Supervisor 存活判定不被初始扫描阻塞；健康检查失败、服务不 ready 或 readiness 报告任一 desired=running Profile 未收敛时，脚本在明确截止时间内非零退出并输出脱敏逐 Profile 诊断，绝不打印成功。
- [ ] AC-004：只有服务健康且 t026 readiness 确认全部 desired=running Profile 收敛后才返回成功；脚本只调用显式收敛入口，不自行执行网络编排或停止 Browser。
- [ ] AC-005：连续相同配置发布幂等，未变化的 Caddy 不重启；配置变化时只重建受影响服务。
- [ ] AC-006：回退到上一 release 恢复其全部镜像与配置，不删除当前 Browser、Profile 数据或数据库；目标 release 不具备 readiness 能力或其迁移版本低于当前数据库时在变更前拒绝并说明原因；回退后执行同一 readiness 验收，状态未知不报成功。
- [ ] AC-007：缺少用户提供的管理员密码或其他发布前提时先失败并列出缺项；容器间内部密钥缺失时以随机值生成并以 0600 保存；不生成公网默认凭证，脚本输出、日志与 manifest 不含任何秘密真值。
- [ ] AC-008：发布实例身份可参数化，两个实例在同一 Docker daemon 并存时互不扫描、不清理对方资源；目标 prefix 已被另一运行实例占用时启动前拒绝。
- [ ] AC-009：shell/配置验证与受控 Docker CLI/HTTP 测试执行生产脚本，覆盖成功、超时、部分失败、重复发布、回退拒绝与回退成功、实例冲突；交付真实演练步骤和现场保存规则给 t032。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；AC 中“目标探针/用例交付”只验入口、断言、报告和收集，不表示已完成目标实跑。真实环境行为执行只在 t032 判定。

## 上下文区

### 执行环境与参考来源

- 执行环境：云端 Muse。完成实现、触达生产逻辑的 unit/integration、可用的普通 Chromium 测试，以及可收集的真实环境用例和逐项运行说明。不要求访问宿主 Mac、OrbStack、用户局域网或真实 CloakBrowser/Stream 镜像；这些执行义务集中到 t032。本 task 的 AC 只验云端交付，不把模拟结果、collect-only、skip 或历史 trust_prior 当作目标环境 PASS。代码交付完成不表示目标环境已验收；t032 通过前不得据此发布或宣称指纹安全。

- 来源：p034（发布部分）；2026-11-04，main@c6a9322 核实，同日按三方审阅修订。审阅补充：compose 写死 tag 与 build 块使回退失效、manifest 不全、Gateway 无健康路由、Supervisor 健康需 token 且晚于初始扫描、构建上下文无 ignore、固定命名阻止隔离实例、回退目标与迁移/readiness 能力不兼容、凭证自动生成与“缺失即失败”冲突（用户 2026-11-04 决定：管理员密码用户提供，内部密钥可自动随机生成）。本轮只读，不执行任何发布。

### 有意不测

- 宿主 Mac/OrbStack、目标 CloakBrowser、真实媒体/X11/指纹站点：当前 task 执行端为云端 Muse，统一由 t032 执行；不得记为 PASS。

### 测试策略

- 受控 Docker CLI 与 readiness 服务验证命令顺序、退出码、deadline、env 原子替换、实例参数化及回退拒绝；必须执行生产脚本，不能仅 grep 文本。
- 静态 shell 检查与 Compose 配置渲染不打印秘密；构建上下文测试对缺失 ignore 文件失败；真实冷构建、重复发布与回退交 t032。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无；发布控制契约由 t026 提供，实际 Docker Compose 版本与镜像构建条件在 t032 前置检查。

### 风险与回退

- 风险：错误 release env 混用版本；失败后自动重试覆盖现场；参数化遗漏导致测试实例触达生产资源。
- 回退：保留上版不可变 release 及当前失败状态，显式选择上版重部署并重新验收；不自动重试非幂等发布或回滚数据。

### 依赖与约束

- 硬依赖 t026，需其执行结果已进入本 task 基线；与 t028 互斥（共用 E2E 夹具与镜像身份校验）。
- 云端/本地边界遵循“执行环境与参考来源”；真实执行义务只在 t032 判定。

### Finalization 时更新的 blueprint

- docs/blueprint/architecture.md：发布与运行时边界、实例身份参数。
- docs/blueprint/decisions.md：release 不可变身份、回退约束与凭证分级 ADR。
- docs/blueprint/testing.md：健康检查、收敛验收、构建上下文和回退演练。
- `DOCKER_DEPLOYMENT.md`：升级、回退与凭证说明。
