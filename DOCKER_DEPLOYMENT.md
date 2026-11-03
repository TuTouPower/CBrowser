# CBrowser 容器化部署与运维手册

## 1. 当前拓扑

固定服务：`cbrowser-caddy`、`cbrowser-api`、`cbrowser-gateway`、`cbrowser-supervisor`。

动态服务：每个 Profile 创建 `cbrowser-browser-{profileId}` 与 `cbrowser-stream-{profileId}`。Browser 持有 CloakBrowser/Xvfb/PulseAudio/Browser Agent；Stream 持有 Selkies/Stream Agent。媒体 UDP 端口发布到宿主 `127.0.0.1`，同机 Chrome 直连，不使用 TURN。

## 2. 首次部署

```bash
npm ci --prefix src/frontend
npm run build --prefix src/frontend
bash scripts/deploy_v2.sh
```

脚本会生成 `config/deploy/secrets/{supervisor_key,agent_key,gateway_key,gateway_api_key,admin_password}`、创建 `data/v2` 数据根、构建 API/Browser/Stream/Supervisor/Gateway 镜像并启动 compose。

访问 `https://127.0.0.1:56661`。Caddy 使用内部 CA，首次自签证书需在 Chrome 中确认或通过系统信任本地 CA。

## 3. 配置

- `.env.example`：入口端口与公开 origin
- `config/deploy/compose.env`：由部署脚本生成，含镜像 ID 与端口，不入库
- `config/deploy/secrets/`：不入库，权限 0600
- `data/v2/cbrowser.db`：API SQLite
- `data/v2/profiles/{profileId}/profile`：浏览器用户数据
- `data/v2/artifacts/{profileId}`：Artifact 文件
- `data/v2/engine-cache`：CloakBrowser/GeoIP 缓存

## 4. 启停与升级

```bash
bash scripts/deploy_v2.sh          # 构建并重启
docker compose --env-file config/deploy/compose.env down
docker compose --env-file config/deploy/compose.env up -d
```

升级前先备份；镜像标签 `*-deploy` 可回滚到上一份本地镜像，脚本会重写 `compose.env` 的镜像 ID。

## 5. 备份与恢复

```bash
tar -czf data/backups/cbrowser-$(date +%Y%m%dT%H%M%S).tar.gz data/v2
```

恢复：停止 compose，解压备份覆盖 `data/v2`，再启动。迁移 legacy 数据使用：

```bash
PYTHONPATH=src/backend uv run --no-project --python ">=3.12" --with alembic --with sqlalchemy --with aiosqlite   python scripts/migrate_legacy.py --source ~/.cbrowser --target data/v2 --apply
```

## 6. 故障定位

```bash
docker compose --env-file config/deploy/compose.env ps
docker logs --tail 200 cbrowser-api
docker logs --tail 200 cbrowser-supervisor
docker logs --tail 200 cbrowser-gateway
docker logs --tail 200 cbrowser-caddy
docker ps --filter 'label=com.cbrowser.prefix=cbrowser'
```

- Profile 启动失败：先看 supervisor 日志中的 `Sandbox launch failed ... error=`，再检查镜像 ID、Docker 网络地址池和 `data/v2` 权限。
- 媒体不通：检查 `docker ps` 中 Browser/Stream 是否 Up、Gateway 日志是否注册、宿主是否占用 UDP 30000-30991。
- 登录失败：确认 `config/deploy/secrets/admin_password` 与 `data/v2/cbrowser.db` 同属一个数据根。
