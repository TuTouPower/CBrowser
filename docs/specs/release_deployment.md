# 需求规范：Release 发布与回退

本文描述 t027 实现行为。发布由 `scripts/deploy.sh` 单一入口执行，运行时收敛与 readiness 契约由 t026 提供；真实部署演练（冷构建、重复发布、回退、双实例并存）在 t032 判定，本 spec 的云端断言不冒充真实环境证据。

## 不可变 release

- 每次发布是一个不可变 release：五个运行时镜像各按当前源只构建一次并打 release 标签，Caddy 使用固定上游引用；release manifest/env 以不可变镜像 ID 固定 API、Gateway、Supervisor、Browser、Stream、Caddy 全部六个镜像，并记录 compose 文件、Caddyfile、前端产物的 SHA-256 指纹与数据库迁移版本（alembic head），以及 readiness/reconcile 能力标记。t034 起基础镜像为 digest 固定的 `python:3.15-slim-trixie` / `debian:trixie-slim`（辅助阶段），Caddy 为 digest 固定的 2.x，`CADDY_REF` 默认值随之更新；Python 依赖由 `uv.lock` 单一来源按依赖组导出。
- release 文件保存在 `config/deploy/releases/<release_id>.{env,json}`，同名 release 禁止覆盖。当前/上一 release 只经 `current_release`/`previous_release` 指针文件表示，指针只在发布或回退通过验收后原子更新；生成或部署中途失败不覆盖上一份有效 release，上一 release 的镜像保留在 daemon 中。
- compose.yaml 的全部服务镜像只读 release 变量且无 build 块，`up` 永不触发构建。

## 验收而非假成功

- 发布与回退都以同一验收收尾：先有界 `docker compose up -d --no-build --wait`（服务健康），再经 `docker compose exec` 把 `scripts/supervisor_readiness_probe.py` 喂入 Supervisor 容器执行——探针调用唯一的 `reconcile_all` 收敛入口并轮询 `readiness`，宿主机不持有 Supervisor 密钥、不新增发布端口，脚本不自行做网络编排或停止 Browser。
- 任一 desired=running Profile 未收敛、服务不健康或超过截止时间：脚本非零退出并输出脱敏的逐 Profile 诊断（仅 profile id、ready 标志与诊断码），不打印成功、不移动指针。
- API、Gateway、Supervisor 均有与能力匹配的 compose 健康检查：API `/api/v1/health`、Gateway `/gateway/v1/health`（t027 新增，无鉴权存活）、Supervisor `/supervisor/v1/health`（检查在容器内读已挂载的 token 文件执行）。Supervisor 控制面在初始扫描之前启动，存活判定不被初始扫描阻塞。

## 幂等与最小重建

- 连续以相同配置发布是幂等的收敛操作：脚本从不显式重启任何服务；Caddy 的重建只由其环境中的 Caddyfile/前端产物指纹变化触发，配置未变时 Caddy 不重启，配置变化时只重建受影响服务。

## 回退约束

- 回退显式选择上一（或命名）release 重部署并跑同一 readiness 验收；不删除 Browser、Profile 数据或数据库。回退一律采用目标 release env 记录的实例身份执行（compose 插值中 shell 环境优先于 env 文件，调用方 shell 的身份值不得覆盖目标 release 的项目/prefix/数据根/secrets）。
- 目标 release 不具备 readiness 能力、其迁移 head 与当前数据库实际 stamp 不等、或工作树 `compose.yaml` 指纹与目标 `compose_sha256` 不一致时，在任何变更前拒绝并说明原因；不存在降级迁移。当前数据库版本为只读读取的实际 `alembic_version` stamp（空库/无表留给 API 启动处理）：同代旧 head、跨代旧 release（含需已删除 `ALLOWED_ORIGINS` 的旧 t042 release，不做兼容）均因不等被拒绝；一次已拉起又验收失败的发布若已把数据库升版，stamp 已变，旧 head 回退同样拒绝。回退验收失败时不报成功、指针不变。

## 凭证分级

- 管理员密码由用户提供：缺失时部署在任何变更前失败并列出全部缺项（连同其他发布前提）。
- 容器间内部密钥（supervisor/agent/gateway/gateway-api）首次缺失时随机生成并以 0600 保存，永不打印；脚本输出、日志与 manifest 不含任何秘密真值，只提示密码文件位置。不生成公网默认凭证。

## 实例隔离

- 发布实例身份可参数化：compose 项目名、容器名、资源 prefix、edge 网络、数据根、secrets 目录与 HTTPS 端口由 release env 提供（`CBROWSER_COMPOSE_PROJECT`、`CBROWSER_PREFIX`、`CBROWSER_DATA_ROOT`、`CBROWSER_SECRETS_DIR`、`CBROWSER_HTTPS_PORT`），两个实例可在同一 daemon 并存且互不扫描、互不清理。
- 目标 prefix 已被另一运行实例（不同 compose 项目）占用时，启动前拒绝：同 prefix 的 Supervisor 会把对方 Profile 视为孤儿 teardown。

## 构建上下文

- 全部运行时镜像的构建上下文受各自 `Dockerfile.dockerignore` 白名单限制：`data/`、`config/deploy/secrets`、`.scratch` 永不进入上下文；任一运行时镜像缺失 ignore 规则时门禁测试失败而非跳过（t027 起）。

## 确定性 Caddyfile 生成与边缘端口重建（t042）

- 删除仓库入库的静态 Caddyfile：Caddy 配置由已应用不可变版本从生成器 `src/backend/cbrowser/network_config.py` 确定性生成；release manifest 对生成器代码取指纹。
- 端口绑定环境参数化：`compose.yaml` 中 Caddy 端口映射默认使用 `${CBROWSER_BIND_HOST:-127.0.0.1}:${CBROWSER_HTTPS_PORT:-56661}:443`；本机模式绑定 `127.0.0.1`，局域网模式绑定 `0.0.0.0`。
- 运行时原子重建：网络模式切换由 Supervisor 接管 Caddy 容器原地原子重绑并重启；`compose.yaml` 中 Caddyfile 挂载对齐 `${CBROWSER_DATA_ROOT}/network/Caddyfile`。
- 已应用网络版本构造即完整（t048）：`AppliedNetworkAccessVersion.caddyfile_sha256` 为必填的 64 位小写十六进制 SHA-256；版本只经 `build_applied_network_version(config, version=..., upstream...)` 构造，同一次调用生成 Caddyfile 文本、哈希与 origin whitelist。CLI init、repository 无数据回退、`_restore_old` 无快照回退与申请新版本都走该入口，不存在空哈希中间对象或跳过校验的分支；聚合同一 Caddyfile 的旧快照才允许重绑。
