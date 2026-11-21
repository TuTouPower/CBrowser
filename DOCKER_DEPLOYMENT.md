# cbrowser 容器化部署与运维手册

## 1. 当前拓扑

固定服务：`cbrowser-caddy`、`cbrowser-api`、`cbrowser-gateway`、`cbrowser-supervisor`（容器名随实例 prefix 变化，见第 6 节）。

动态服务：每个 Profile 创建 `{prefix}-browser-{profileId}` 与 `{prefix}-stream-{profileId}`。Browser 持有 CloakBrowser/Xvfb/PulseAudio/Browser Agent；Stream 持有 Selkies/Stream Agent。媒体 UDP 端口发布到宿主 `127.0.0.1`，同机 Chrome 直连，不使用 TURN。

## 2. 首次部署

部署机需要运行中的 Linux Docker daemon（macOS 可使用 OrbStack）、Docker Compose v2、Bash、Python 3.15+（`python3`）、OpenSSL，以及 `sha256sum` 或 `shasum`。使用运行 Docker 的同一台机器上的 Google Chrome 打开管理页和 Viewer。默认 HTTPS 地址为 `https://127.0.0.1:56661`，Profile 媒体通过宿主 UDP 端口直连。

### 2.1 选择安装方式

|方式|取得安装文件|安装命令|
|---|---|---|
|预构建镜像|从 [GitHub Releases](https://github.com/TuTouPower/cbrowser/releases) 下载适合宿主架构的 Linux 部署包，解压到固定目录，进入含 `install.sh` 和本手册的目录|完成 2.2 后运行 `bash install.sh`|
|源码自建|克隆仓库并切换到选定的发布 tag，进入仓库根目录|完成 2.2 后运行 `bash scripts/build_images.sh`，成功后运行 `bash scripts/deploy.sh`|

预构建安装按部署包内 `images.json` 的不可变摘要从 `ghcr.io` 拉取六个镜像，不需要 Git、Dockerfile 或前端构建工具。根据对应 Release 的说明选择架构。下载部署包及配套 `.sha256` 文件后，从下载目录校验并解压。将下面的文件名替换为该 Release 的实际资产名称。Linux 也可用 `sha256sum -c` 校验。

```bash
bundle=cbrowser-install-linux-arm64.tar.gz
shasum -a 256 -c "$bundle.sha256" &&
  mkdir -p "$HOME/cbrowser-deploy" &&
  tar -xzf "$bundle" -C "$HOME/cbrowser-deploy" &&
  cd "$HOME/cbrowser-deploy"
```

源码自建还需 Git、Docker Buildx 和 curl。将示例的 `v0.2.1` 替换为 Release 标注的版本 tag：

```bash
git clone https://github.com/TuTouPower/cbrowser.git
cd cbrowser
git switch --detach v0.2.1
```

构建脚本读取 `config/font_assets.lock.json`，自动从锁定地址下载字体包并校验 SHA-256，构建六个镜像并生成 `.scratch/images.json`。前端在 Docker 构建阶段打包进 Caddy 镜像。两条安装路径都会从 Browser 镜像把 Windows 和 macOS 字体导入 fonts 卷；重复部署复用同一内容版本。普通用户无需寻找、另行下载或安装字体。

Browser、Stream 和 Caddy 构建使用清华 Debian 镜像站。可通过 `CBROWSER_APT_MIRROR` 指定其他 Debian 镜像站域名。构建继续使用 Docker 配置的代理，只有明确要求某些站点直连时，才将站点域名加入构建终端的 `NO_PROXY`。

### 2.2 写入管理员密码

在部署目录用 Bash 执行下列命令。输入自选随机强密码，终端不回显。已有密码文件时跳过这一步。

```bash
(
  umask 077
  set -o noclobber
  mkdir -p config/deploy/secrets
  read -rs -p '输入管理员密码: ' admin_password
  printf '\n'
  [ -n "$admin_password" ] || exit 1
  printf '%s\n' "$admin_password" > config/deploy/secrets/admin_password
)
```

### 2.3 首次启动和引擎下载

执行 2.1 的安装命令，等待脚本输出成功。用 Chrome 访问 `https://127.0.0.1:56661`，按浏览器提示确认本地 Caddy CA 或在系统中信任本机 CA，再以 2.2 设置的密码登录。运行 `bash scripts/deploy.sh status` 可查看当前 release。

首次启动 Profile 时，如实例的 data 卷缺少引擎缓存，下载辅助容器会从上游获取并校验引擎。只有上游需要经代理访问时，才在执行安装、升级或回退前设置 `CBROWSER_ENGINE_DOWNLOAD_PROXY`。下例适用于 OrbStack 且本机代理实际监听 7890 的情况：

```bash
export CBROWSER_ENGINE_DOWNLOAD_PROXY=http://host.docker.internal:7890
```

代理地址必须能从 Docker 容器访问。部署脚本将该配置交由 Supervisor，只给下载辅助容器设置 `HTTP_PROXY` 和 `HTTPS_PROXY`。Profile 出口代理由管理页单独配置。

## 3. Release 模型

- 每次发布生成 `config/deploy/releases/<release_id>.json`（manifest：六个镜像的不可变 ID、compose/渲染后 Caddyfile/前端产物指纹、数据库迁移版本、readiness 能力）与同名 `.env`（compose 用的固定变量，凭据由部署脚本另行注入）。
- `config/deploy/release_pointer.json` 是唯一指针文件（`{"current": …, "previous": …}`），只在发布/回退通过 readiness 验收后才原子更新；失败发布不覆盖上一份有效 release，上一 release 的镜像仍在 daemon 中。旧版两个独立指针文件 `config/deploy/current_release` / `config/deploy/previous_release` 已退役并删除，不再使用。
- `bash scripts/deploy.sh status` 查看当前/上一 release。
- compose.yaml 的服务镜像全部来自 release env 且没有 build 块，生产操作使用部署脚本，以保留 secret 注入和 readiness 检查。

## 4. 升级与回退

升级前在旧版本目录按第 8 节创建恢复点，并备份凭据目录及当前版本的部署文件。保持同一绝对部署目录和实例配置，避免创建第二套实例。

- 源码自建：切换到新发布 tag 后，重新执行 `bash scripts/build_images.sh` 和 `bash scripts/deploy.sh`。
- 预构建镜像：在临时目录解压新部署包，再将包内文件覆盖到原部署目录，保留 `config/deploy/` 中的凭据、release 记录和指针。进入原目录执行 `bash install.sh`。
- 重复安装会检查镜像与配置，未变化的服务复用现有容器。Caddy 的部署配置或镜像变化时会更新。

回退会恢复目标 release 的全部镜像与配置，并保留 Browser、Profile 数据和数据库。回退到指定版本时，先将 `target_release` 设为 `config/deploy/releases/` 中该版本的文件名（去掉扩展名）：

```bash
bash scripts/deploy.sh rollback              # 回到 release_pointer.json 的 previous
bash scripts/deploy.sh rollback "$target_release" # 回到指定 release
```

回退同样执行 readiness 验收后才切换指针，且自动采用目标 release 记录的实例身份（项目、prefix、端口、数据根、secrets 目录）执行，不受你当前 shell 里这些环境变量的影响——默认实例直接裸命令 `rollback` 即可。唯一例外是 release 存放位置本身：若该实例发布时用了自定义 `CBROWSER_DEPLOY_DIR`（见第 6 节），回退时也要带上同一个 `CBROWSER_DEPLOY_DIR`，否则会命中默认实例的指针。以下情况回退会在任何变更前被拒绝并说明原因：目标 release 不具备 readiness 能力；目标 release 的迁移 head 与当前数据库实际 stamp 不等（无降级迁移：同代旧 head 与跨代旧 release 均拒绝，含需已删除 `ALLOWED_ORIGINS` 的旧 t042 release——拒绝即可，不做兼容，重建数据目录）；工作树 `compose.yaml` 指纹与目标 `compose_sha256` 不一致（防旧镜像配新 compose 混用）。当前数据库版本以只读读取的实际 `alembic_version` stamp 为准（空库留给 API 启动创建/升级）；一次拉起后验收失败的发布若已把数据库升版，stamp 已变，旧 head 回退同样拒绝，不要手工绕过。

## 5. 凭证

- `config/deploy/secrets/admin_password`：用户提供，登录用；脚本只提示文件位置，永不打印、永不自动生成。
- 其余内部密钥：首次缺失时脚本随机生成、0600 保存，服务间内部使用，运维不需要知道其值。
- 脚本输出、日志与 release manifest 都不含秘密真值。

## 6. 第二实例（隔离测试）

实例身份可参数化，第二个实例与生产实例可在同一 Docker daemon 并存：

```bash
CBROWSER_COMPOSE_PROJECT=cbrowser-test \
CBROWSER_PREFIX=cbrowsertest \
CBROWSER_HTTPS_PORT=56662 \
CBROWSER_DATA_ROOT=$PWD/data/test-instance \
CBROWSER_SECRETS_DIR=$PWD/config/deploy/test-secrets \
CBROWSER_DEPLOY_DIR=$PWD/config/deploy/test-instance \
bash scripts/deploy.sh
```

注意：新实例的 secrets 目录同样需要先放好它自己的 `admin_password`。**prefix 是 Supervisor 的资源扫描边界**：两个实例绝不能共用同一 prefix；若目标 prefix 已被另一个运行中的实例占用，脚本会在启动前拒绝。上例使用默认媒体端口范围。两套实例同时启动 Profile 时，需在各自的 Compose 文件为 `supervisor.environment` 配置不重叠的 `CBROWSER_UDP_MUX_MIN_PORT` 和 `CBROWSER_UDP_MUX_MAX_PORT`。默认实例使用 UDP 30000–30991。

## 7. 真实环境演练（t032 执行）

云端交付只用 fake Docker 与受控 HTTP 验证过脚本逻辑；以下演练必须在真实 daemon 上执行并留存输出，才算部署验收（t032 AC-009）：

1. 冷构建首发：清空本项目镜像后按第 2 节发布，断言六镜像各构建一次、六镜像 ID 与 manifest 一致、全部 desired=running Profile readiness 收敛。
2. 重复发布：不改任何输入再发布一次，断言服务不重建、Caddy 不重启、指针前进且 previous 指向上一 release。
3. 回退成功：`rollback` 后断言镜像/配置回到上一 release 且 readiness 再次通过；Profile 数据与数据库行数不变。
4. 回退拒绝：构造迁移版本更高的一次发布后回退到低迁移 release（或使用无 readiness 能力的旧 manifest），断言变更前拒绝、指针不动。
5. 双实例并存：按第 6 节起第二实例（不同 prefix/项目/端口/数据根），断言两边 Profile 互不扫描清理；再以相同 prefix 起第三实例，断言启动前拒绝。

现场保存规则：任一演练失败时保留失败 release 的 `.env`/`.json`、`release_pointer.json` 指针、脚本完整输出与 `docker compose ps` 快照，不要删除 releases 目录或手工改指针；先按第 9 节定位，再决定修复重发或回退。

## 8. 备份与恢复

环境级备份恢复走**恢复点**（t066）：一个恢复点是同一静默时刻的控制面数据库（在 named volume `db` 中，不在 `data/instance` 里——旧版 `tar data/instance` 会漏掉整个数据库，禁止再用它做环境备份）与全部 Profile 浏览器数据目录的成套快照，带逐文件 SHA-256 清单、数据库完整性与 schema 版本记录。凭据文件不进恢复点，清单只记恢复前提的文件名，恢复站点须另行备好 `config/deploy/secrets`。

备份（可设置 `point_dir` 指定输出目录。所有 Profile 须已停止；任一 Profile 在运行或仍绑定运行时实例时命令拒绝执行）：

```bash
bash scripts/deploy.sh env-backup            # 默认写 data/backups/restore-points/point-<时间>
bash scripts/deploy.sh env-backup "$point_dir"
```

校验一个恢复点。将 `point_dir` 设为恢复点的绝对路径，将 `api_image` 设为当前 release 清单里的 API 镜像 ID：

```bash
docker run --rm -v "$PWD/scripts:/scripts:ro" -v "$point_dir:/point:ro" \
  "$api_image" python3 /scripts/restore_point.py verify --point /point
```

恢复（命令会先停止 compose；恢复先全量校验清单、完整性、版本与磁盘空间，再成套切换；切换中断会在下次调用时先回滚到恢复前状态，恢复前的整套数据保留在原位置旁的 `.pre-restore-*` 目录/文件中，确认无误后可手工删除；恢复在 staging 阶段被中断时留下的 `.restore-staging-*` 残留会在下一次恢复开始时自动清扫，也可直接手工删除——它们不属于任何完整集）：

```bash
bash scripts/deploy.sh env-restore "$point_dir"
```

将 `point_dir` 设为恢复点目录。恢复完成后，源码部署运行 `bash scripts/deploy.sh`，预构建部署运行 `bash install.sh`。

`deploy.sh restore <backup-file>` 只恢复数据库单件（发布流程的备份），不恢复 Profile 数据，不能替代环境恢复点。

t035 起迁移链只有一个 baseline 修订（ADR 023）。旧 schema 代（0001-0009）数据库不受支持：API 启动与 `scripts/deploy.sh` 部署都会失败封闭并输出重建指引，不自动升级、不修改该库。生产数据须先备份，再经用户批准的迁移流程重建 `data/instance`；legacy 迁移脚本已随该破坏性升级移除。

## 9. 停止与故障定位

先在管理页停止全部 Profile，再从部署目录关闭控制面。以下命令读取默认部署目录中当前 release 的 ID。常规停止保留实例的 named volumes。自定义实例请使用其实际凭据和 release 路径。

```bash
release_id="$(python3 -c 'import json; print(json.load(open("config/deploy/release_pointer.json"))["current"])')"
CBROWSER_EDGE_PROOF_SECRET="$(cat config/deploy/secrets/edge_proof_key)" \
  docker compose --env-file "config/deploy/releases/$release_id.env" -f compose.yaml down
```

故障定位时沿用上方的 `release_id`：

```bash
bash scripts/deploy.sh status
CBROWSER_EDGE_PROOF_SECRET="$(cat config/deploy/secrets/edge_proof_key)" \
  docker compose --env-file "config/deploy/releases/$release_id.env" -f compose.yaml ps
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
- 字体下载 404：核对当前 tag 对应的字体 Release 是否已发布，并检查构建机能否访问锁定 URL。
- 镜像拉取失败：核对部署包架构、GHCR 访问和 `images.json` 中报错的 digest。
- 首个 Profile 卡在引擎初始化：查看 Supervisor 日志，检查下载辅助容器能否访问上游。使用显式代理的环境按 2.3 重新部署。

## 10. 维护者发布

1. 核对分发权限后，将 `cbrowser-fonts.tar.zst` 和 `cbrowser-fonts.tar.zst.sha256` 放在 `font-assets-v1` Release。构建入口固定使用锁文件中的 URL 和摘要。更换字体内容时，用新资产版本更新锁文件，已发布链接保持可用。

2. 将六个正式镜像推到 `ghcr.io/tutoupower/cbrowser-<角色>`，确认仓库可公开访问。各架构的应用部署包须引用能在该架构运行的镜像。

3. 从实际推送结果建立 `images.json`，在 `images` 对象中写入 `api`、`browser`、`caddy`、`gateway`、`stream`、`supervisor` 六个 `ghcr.io/tutoupower/cbrowser-<角色>@sha256:<digest>` 引用。

4. 在对应版本的已提交源码上生成部署包。脚本从当前 Git `HEAD` 取文件，输入清单必须与发布版本匹配。

    ```bash
    bundle=cbrowser-install-linux-arm64.tar.gz
    python3 scripts/package_install.py images.json "$bundle" &&
      shasum -a 256 "$bundle" > "$bundle.sha256"
    ```

5. 将部署包和校验文件上传到对应应用 Release，注明 CPU 架构，并链接本手册。源码用户经字体 Release 自动取得字体；预构建用户经 GHCR 镜像取得字体和前端。

构建机可通过 `CBROWSER_FONT_ARCHIVE=/path/to/cbrowser-fonts.tar.zst bash scripts/build_images.sh` 使用匹配锁文件 SHA-256 的本地制品。该入口用于维护者准备发布时。
