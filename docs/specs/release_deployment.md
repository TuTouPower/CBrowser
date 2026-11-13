# 需求规范：Release 发布与回退

本文描述 t027 实现行为。发布由 `scripts/deploy.sh` 单一入口执行，运行时收敛与 readiness 契约由 t026 提供；真实部署演练（冷构建、重复发布、回退、双实例并存）在 t032 判定，本 spec 的云端断言不冒充真实环境证据。

## 不可变 release

- 每次发布是一个不可变 release：五个运行时镜像各按当前源只构建一次并打 release 标签，Caddy 使用固定上游引用；release manifest/env 以不可变镜像 ID 固定 API、Gateway、Supervisor、Browser、Stream、Caddy 全部六个镜像，并记录 compose 文件、Caddyfile、前端产物的 SHA-256 指纹与数据库迁移版本（alembic head），以及 readiness/reconcile 能力标记。t034 起基础镜像为 digest 固定的 `python:3.15-slim-trixie` / `debian:trixie-slim`（辅助阶段），Caddy 为 digest 固定的 2.x，`CADDY_REF` 默认值随之更新；Python 依赖由 `uv.lock` 单一来源按依赖组导出。
- release 文件保存在 `config/deploy/releases/<release_id>.{env,json}`，同名 release 禁止覆盖。当前/上一 release 只经单一 JSON 指针文件 `config/deploy/release_pointer.json`（`{"current": …, "previous": …|null}`）表示，指针只在发布或回退通过验收后原子写（文件 + 父目录 fsync）；生成或部署中途失败不覆盖上一份有效 release，上一 release 的镜像保留在 daemon 中。指针文件损坏时 fail-soft 替换（previous 丢失）。
- compose.yaml 的全部服务镜像只读 release 变量且无 build 块，`up` 永不触发构建。

## 验收而非假成功

- 发布与回退都以同一验收收尾：先有界 `docker compose up -d --no-build --wait`（服务健康），再经 `docker compose exec` 把 `scripts/supervisor_readiness_probe.py` 喂入 Supervisor 容器执行——探针调用唯一的 `reconcile_all` 收敛入口并轮询 `readiness`，宿主机不持有 Supervisor 密钥、不新增发布端口，脚本不自行做网络编排或停止 Browser。
- 任一 desired=running Profile 未收敛、服务不健康或超过截止时间：脚本非零退出并输出脱敏的逐 Profile 诊断（仅 profile id、ready 标志与诊断码），不打印成功、不移动指针。
- API、Gateway、Supervisor 均有与能力匹配的 compose 健康检查：API `/api/v1/health`、Gateway `/gateway/v1/health`（t027 新增，无鉴权存活）、Supervisor `/supervisor/v1/health`（检查在容器内读已挂载的 token 文件执行）。Supervisor 控制面在初始扫描之前启动，存活判定不被初始扫描阻塞。

## 幂等与最小重建

- 连续以相同配置发布是幂等的收敛操作：脚本从不显式重启任何服务；Caddy 的重建只由其环境中的 Caddyfile/前端产物指纹变化触发，配置未变时 Caddy 不重启，配置变化时只重建受影响服务。

## 回退约束

- 回退显式选择上一（或命名）release 重部署并跑同一 readiness 验收；不删除 Browser、Profile 数据或数据库。回退一律采用目标 release env 记录的实例身份执行（compose 插值中 shell 环境优先于 env 文件，调用方 shell 的身份值不得覆盖目标 release 的项目/prefix/数据根/secrets）。
- 目标 release 不具备 readiness 能力、其迁移 head 与当前数据库实际 stamp 不等、或工作树 `compose.yaml` 指纹与目标 `compose_sha256` 不一致时，在任何变更前拒绝并说明原因；不存在降级迁移。回退时按目标 release 记录的端口重渲染 Caddyfile，渲染产物 SHA-256 与目标 manifest 的 `caddyfile_sha256` 不一致同样拒绝（t054）。当前数据库版本为只读读取的实际 `alembic_version` stamp（空库/无表留给 API 启动处理）：同代旧 head、跨代旧 release（含需已删除 `ALLOWED_ORIGINS` 的旧 t042 release，不做兼容）均因不等被拒绝；一次已拉起又验收失败的发布若已把数据库升版，stamp 已变，旧 head 回退同样拒绝。回退验收失败时不报成功、指针不变。

## 凭证分级

- 管理员密码由用户提供：缺失时部署在任何变更前失败并列出全部缺项（连同其他发布前提）。
- 容器间内部密钥（supervisor/agent/gateway/gateway-api）首次缺失时随机生成并以 0600 保存，永不打印；脚本输出、日志与 manifest 不含任何秘密真值，只提示密码文件位置。不生成公网默认凭证。

## 实例隔离

- 发布实例身份可参数化：compose 项目名、容器名、资源 prefix、edge 网络、数据根、secrets 目录与 HTTPS 端口由 release env 提供（`CBROWSER_COMPOSE_PROJECT`、`CBROWSER_PREFIX`、`CBROWSER_DATA_ROOT`、`CBROWSER_SECRETS_DIR`、`CBROWSER_HTTPS_PORT`），两个实例可在同一 daemon 并存且互不扫描、互不清理。edge 子网（`CBROWSER_EDGE_SUBNET`）由 deploy.sh 按实例身份摘要派生并写入 release env 与 manifest 的 `instance` 块，受信代理 CIDR（`CBROWSER_TRUSTED_PROXY_CIDRS`）取同一值（t054）。
- 目标 prefix 已被另一运行实例（不同 compose 项目、instance-id 不符）占用时，启动前拒绝；Supervisor 从不认领或 teardown 异部署沙箱（t051，见下）。

## 构建上下文

- 全部运行时镜像的构建上下文受各自 `Dockerfile.dockerignore` 白名单限制：`data/`、`config/deploy/secrets`、`.scratch` 永不进入上下文；任一运行时镜像缺失 ignore 规则时门禁测试失败而非跳过（t027 起）。

## 确定性 Caddyfile 生成与部署期网络配置（t042；t054 重写）

- 删除仓库入库的静态 Caddyfile：Caddy 配置由生成器 `src/backend/cbrowser/network_config.py` 在部署期确定性渲染（`network_config render --network-dir $DATA_ROOT/network --https-port $HTTPS_PORT`），写入 `$DATA_ROOT/network/Caddyfile`；运行期不存在网络配置变更入口（t054：t042 的运行时应用链、已应用版本、Supervisor 边缘重建全部删除）。
- 端口只从部署输入来：默认端口收敛为唯一常量 `DEFAULT_HTTPS_PORT = 56661`；`compose.yaml` 中 Caddy 端口映射为 `127.0.0.1:${CBROWSER_HTTPS_PORT}:443`（固定回环绑定，无局域网模式）。部署指纹 `caddyfile_sha256` 改为渲染后 Caddyfile 产物的 SHA-256（生成器源码改动不改变指纹，端口改动改变指纹）；回退时按目标 release 记录的端口重渲染并校验与目标 manifest 一致。
- Origin 白名单由部署端口确定性派生：`derive_origin_whitelist(https_port)`（`127.0.0.1` / `localhost` + 端口，纯 https）；API 与 Gateway 在启动时从同一 `CBROWSER_HTTPS_PORT` 派生。
- edge 网络固定 IPAM 子网：`compose.yaml` 的 `edge` 网络按 `${CBROWSER_EDGE_SUBNET}` 固定子网；该值由 deploy.sh 按实例身份摘要派生（`172.{18 + digest mod 14}.0.0/16`），部署前预检与已存 Docker 网络子网、宿主接口地址的重叠；`CBROWSER_TRUSTED_PROXY_CIDRS` 取同一值并注入 API 与 Gateway。

## 控制面数据库进 named volume、部署身份与发布原子性（t051）

- 控制面数据库（含 `-wal` / `-shm`）位于 compose named volume `db`（`name: ${CBROWSER_PREFIX:-cbrowser}-db`），API 挂载 `db:/data/db`、`CBROWSER_DB_PATH=/data/db/cbrowser.db`；数据库文件不位于任何宿主 bind mount 上。WAL 的 `-shm` wal-index 须与数据库同机共享内存，宿主 bind mount 跨 OrbStack VM 边界时锁语义失稳（p068：2026-11-10 登录持续 500 `disk I/O error`），named volume 是根因修正。
- 字体是独立部署输入：compose 以 `${CBROWSER_FONTS_DIR}:/fonts:ro` 挂载（API 与 Supervisor 容器内 `CBROWSER_FONTS_DIR=/fonts`），`CBROWSER_FONTS_DIR` 写入 release env；部署时字体 preflight 只警告、永不阻塞（缺失或无有效集时输出可执行提示）。
- 部署身份确定性派生：`instance_id = sha256("cbrowser-instance-v1\0<prefix>\0<data_root>")[:32]`，媒体子网池按 `pool_index = sha256(identity) mod 64` 得 `10.{192+index}.0.0/16`；两者写入 release env 与 manifest 的 `instance` 块，跨 release 稳定、跨（prefix, data_root）区分。compose 四服务带 `com.cbrowser.instance-id` 与 `com.cbrowser.media-subnet-pool` 标签。
- 冲突判定以 instance-id 为唯一依据：deploy.sh 扫描运行容器，instance-id 标签等于本实例 id 时认领；标签缺失时仅当容器项目为本实例项目才认领（早于标签的旧容器、数据根迁移重部署情形）；标签存在且不符即拒绝；`<prefix>-profiles` project 名豁免已删除。媒体池重叠在同一扫描内判定（与 prefix 无关，己方 instance-id 跳过），重叠即部署失败并提示。
- schema 代际检查在新存储位置上仍按原语义执行：先建 API 镜像，再以只读挂载的 volume 在容器内读 stamp（`db_inspect.py stamp`）；不可读库 fail-closed（部署前拒绝），不以写模式打开数据库。
- 部署前备份：有 live stamp 时 `up` 前容器内在线备份至 `$DEPLOY_DIR/backups/cbrowser-<ts>.db`，路径记 manifest `database_backup`；`deploy.sh restore <backup-file>` 可把备份拷回 volume（须有当前 release，永不删除备份文件）。volume 无库但宿主旧路径（`$ROOT/data/v2/cbrowser.db` 或 `$DATA_ROOT/cbrowser.db`）存在时，部署输出明确提示旧库位置与处置方式，旧文件不被删除、移动或覆盖。
- 前缀校验：deploy.sh 与 Supervisor 启动都在执行任何 Docker 操作前校验 prefix（`^[a-z0-9][a-z0-9_]*$`，不含连字符；默认 `cbrowser`，为 deploy.sh 与 compose 的默认值，Supervisor/runner/docker_adapter 的默认前缀为 `cbrowser-t005`）。

## 环境恢复点（t066）

- 环境级备份恢复唯一入口为恢复点：`scripts/deploy.sh env-backup [point-dir]` / `env-restore <point-dir>`，底层 `scripts/restore_point.py`（create/verify/restore）在一次性 API 镜像容器内挂载 named volume `db` 与数据根 `/data` 运行。
- 恢复点 = 同一静默时刻的成套快照：DB（SQLite 在线 backup、integrity_check、schema stamp）+ 全部 Profile 用户数据目录（逐文件 SHA-256 manifest）+ 凭据前提清单（只记文件名/大小，凭据不进恢复点）。任一 Profile 有实际写者（运行/迁移态/实例绑定残留）时备份拒绝。
- 恢复协议：先 staging 到目标旁并全量校验（哈希、完整性、schema stamp 与活库一致、空间足够），再按 journal 逐项 rename 成套切换；中断由下一次调用回滚到旧集并以退出码 3 报告，重跑完成恢复；恢复前整套数据保留在 `.pre-restore-<switch-id>`，不自动删除。跨代 stamp 拒绝恢复。
- 旧 `tar data/instance` 备份漏 named volume DB，废止为环境备份手段；`deploy.sh restore` 仅作 DB 单件恢复。
