# CBrowser 容器化部署与运维手册

## 1. 当前拓扑

固定服务：`cbrowser-caddy`、`cbrowser-api`、`cbrowser-gateway`、`cbrowser-supervisor`（容器名随实例 prefix 变化，见第 6 节）。

动态服务：每个 Profile 创建 `{prefix}-browser-{profileId}` 与 `{prefix}-stream-{profileId}`。Browser 持有 CloakBrowser/Xvfb/PulseAudio/Browser Agent；Stream 持有 Selkies/Stream Agent。媒体 UDP 端口发布到宿主 `127.0.0.1`，同机 Chrome 直连，不使用 TURN。

## 2. 首次部署

前置（脚本会在任何变更前一次性列出全部缺项并退出）：

- Docker CLI 与 compose 插件可用；
- **管理员密码由你提供**：写入 `config/deploy/secrets/admin_password`（权限 0600）。脚本不会生成它，也不会打印任何秘密；
- 前端产物已构建：`npm ci --prefix src/frontend && npm run build --prefix src/frontend`。

```bash
mkdir -p config/deploy/secrets
printf '%s' '你的管理员密码' > config/deploy/secrets/admin_password
chmod 600 config/deploy/secrets/admin_password
bash scripts/deploy.sh            # 等同于 bash scripts/deploy.sh deploy
```

脚本做的事：生成缺失的容器间内部密钥（`supervisor_key`、`agent_key`、`gateway_key`、`gateway_api_key`，随机、0600、永不打印）→ 每个运行时镜像只构建一次并打 release 标签 → 生成不可变 release（见第 3 节）→ `docker compose up -d --no-build --wait` 等服务健康 → 在 Supervisor 容器内执行 readiness 探针，确认全部 desired=running 的 Profile 已收敛才算成功。任一步失败都会非零退出并保留上一份有效 release 为当前版本，不打印成功。

访问 `https://127.0.0.1:56661`。Caddy 使用内部 CA，首次自签证书需在 Chrome 中确认或通过系统信任本地 CA。

## 3. Release 模型

- 每次发布生成 `config/deploy/releases/<release_id>.json`（manifest：六个镜像的不可变 ID、compose/`src/backend/cbrowser/network_config.py` 生成器/前端产物指纹、数据库迁移版本、readiness 能力）与同名 `.env`（compose 用的固定变量）。
- `config/deploy/current_release` 与 `config/deploy/previous_release` 是指针文件，只在发布/回退通过 readiness 验收后才原子更新；失败发布不覆盖上一份有效 release，上一 release 的镜像仍在 daemon 中。
- `bash scripts/deploy.sh status` 查看当前/上一 release。
- compose.yaml 的服务镜像全部来自 release env 且没有 build 块，手工 `docker compose --env-file config/deploy/releases/<id>.env -f compose.yaml up -d` 也不会触发构建。

## 4. 升级与回退

升级就是再次发布：

```bash
npm run build --prefix src/frontend   # 前端有变化时
bash scripts/deploy.sh
```

相同配置重复发布是幂等的：镜像与配置未变的服务不会被重建，Caddy 只在其配置指纹（`network_config.py` 生成器或前端产物）变化时才重建。

回退到上一 release（恢复其全部镜像与配置，不删除 Browser、Profile 数据或数据库）：

```bash
bash scripts/deploy.sh rollback              # 回到 previous_release
bash scripts/deploy.sh rollback <release_id> # 回到指定 release
```

回退同样执行 readiness 验收后才切换指针，且自动采用目标 release 记录的实例身份（项目、prefix、端口、数据根、secrets 目录）执行，不受你当前 shell 里这些环境变量的影响——默认实例直接裸命令 `rollback` 即可。唯一例外是 release 存放位置本身：若该实例发布时用了自定义 `CBROWSER_DEPLOY_DIR`（见第 6 节），回退时也要带上同一个 `CBROWSER_DEPLOY_DIR`，否则会命中默认实例的指针。以下情况回退会在任何变更前被拒绝并说明原因：目标 release 不具备 readiness 能力；目标 release 的迁移版本低于当前数据库版本（当前数据库版本以实际已应用的最高迁移为准：一次拉起后验收失败的发布可能已经把数据库升过版，即使它没有成为 current release；系统没有降级迁移，不要手工绕过）。

## 5. 凭证

- `config/deploy/secrets/admin_password`：用户提供，登录用；脚本只提示文件位置，永不打印、永不自动生成。
- 其余四个内部密钥：首次缺失时脚本随机生成、0600 保存，服务间内部使用，运维不需要知道其值。
- 脚本输出、日志与 release manifest 都不含秘密真值。

## 6. 第二实例（隔离测试）

实例身份可参数化，第二个实例与生产实例可在同一 Docker daemon 并存：

```bash
CBROWSER_COMPOSE_PROJECT=cbrowser-test \
CBROWSER_PREFIX=cbrowser-test \
CBROWSER_HTTPS_PORT=56662 \
CBROWSER_DATA_ROOT=$PWD/data/test-v2 \
CBROWSER_SECRETS_DIR=$PWD/config/deploy/test-secrets \
CBROWSER_DEPLOY_DIR=$PWD/config/deploy/test-instance \
bash scripts/deploy.sh
```

注意：新实例的 secrets 目录同样需要先放好它自己的 `admin_password`。**prefix 是 Supervisor 的资源扫描边界**：两个实例绝不能共用同一 prefix；若目标 prefix 已被另一个运行中的实例占用，脚本会在启动前拒绝。

## 7. 真实环境演练（t032 执行）

云端交付只用 fake Docker 与受控 HTTP 验证过脚本逻辑；以下演练必须在真实 daemon 上执行并留存输出，才算部署验收（t032 AC-009）：

1. 冷构建首发：清空本项目镜像后按第 2 节发布，断言五镜像各构建一次、六镜像 ID 与 manifest 一致、全部 desired=running Profile readiness 收敛。
2. 重复发布：不改任何输入再发布一次，断言服务不重建、Caddy 不重启、指针前进且 previous 指向上一 release。
3. 回退成功：`rollback` 后断言镜像/配置回到上一 release 且 readiness 再次通过；Profile 数据与数据库行数不变。
4. 回退拒绝：构造迁移版本更高的一次发布后回退到低迁移 release（或使用无 readiness 能力的旧 manifest），断言变更前拒绝、指针不动。
5. 双实例并存：按第 6 节起第二实例（不同 prefix/项目/端口/数据根），断言两边 Profile 互不扫描清理；再以相同 prefix 起第三实例，断言启动前拒绝。

现场保存规则：任一演练失败时保留失败 release 的 `.env`/`.json`、`current_release`/`previous_release` 指针、脚本完整输出与 `docker compose ps` 快照，不要删除 releases 目录或手工改指针；先按第 8 节定位，再决定修复重发或回退。

## 8. 备份与恢复

```bash
tar -czf data/backups/cbrowser-$(date +%Y%m%dT%H%M%S).tar.gz data/v2
```

恢复：停止 compose，解压备份覆盖 `data/v2`，再发布。

t035 起迁移链只有一个 baseline 修订（ADR 023）。旧 schema 代（0001-0009）数据库不受支持：API 启动与 `scripts/deploy.sh` 部署都会失败封闭并输出重建指引，不自动升级、不修改该库。生产数据须先备份，再经用户批准的迁移流程重建 `data/v2`；legacy 迁移脚本已随该破坏性升级移除。

## 9. 故障定位

```bash
bash scripts/deploy.sh status
docker compose --env-file config/deploy/releases/<release_id>.env -f compose.yaml ps
docker logs --tail 200 cbrowser-api
docker logs --tail 200 cbrowser-supervisor
docker logs --tail 200 cbrowser-gateway
docker logs --tail 200 cbrowser-caddy
docker ps --filter 'label=com.cbrowser.prefix=cbrowser'
```

- 发布失败：脚本输出会指明阶段（前提缺项 / 构建 / compose 健康 / readiness 逐 Profile 诊断）；readiness 诊断只含 profile id 与诊断码，不含秘密。
- Profile 启动失败：先看 supervisor 日志中的 `Sandbox launch failed ... error=`，再检查镜像 ID、Docker 网络地址池和数据根权限。
- 媒体不通：检查 `docker ps` 中 Browser/Stream 是否 Up、Gateway 日志是否注册、宿主是否占用 UDP 30000-30991。
- 登录失败：确认 `config/deploy/secrets/admin_password` 与数据库同属一个数据根/实例。
