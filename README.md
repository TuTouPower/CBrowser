# CBrowser

CBrowser 是面向隐私浏览器与多身份隔离的单机 Docker 管理系统。以 Google Chrome 作为唯一外部客户端，通过 Selkies 2.2.1 WebRTC 传输画面，每个 Profile 由独立 Browser/Stream 容器沙箱隔离。

## 1. 架构

- Caddy：HTTPS、SPA 静态资源、`/api/*` 与 `/stream/*` 反向代理
- cbrowser-api：FastAPI、SQLite 唯一写者、Runtime Coordinator
- cbrowser-supervisor：唯一 Docker Socket 持有者，创建和管理 Profile 容器
- cbrowser-gateway：Stream Agent 注册与 Viewer 信令路由
- Browser/Stream Runtime：每个 Profile 动态创建，媒体同机 `127.0.0.1` 直连，无 coturn/TURN

## 2. 界面特性

- 单用户极简侧边栏：左侧栏提供「环境管理 / 代理管理 / 工作台」主导航，左下角固定放置「设置」（含亮暗色主题与中英文切换）；支持拖拽调宽（200–360px）与折叠，折叠态点击左上角应用图标即可展开。
- 环境管理与参数自动对齐：支持按状态、分组、系统平台（Windows / macOS）、代理筛选及列表/卡片图标切换；备注与种子有效范围采用感叹号悬浮提示；选择代理自动匹配对应时区、语言与可读平台字体包。
- 代理管理与闪电测速：支持按协议与位置筛选、列表/卡片视图切换，提供单条与右上角批量闪电测速（可用性与延迟检测）。
- 最大化工作台会话：左上角环境切换器为每个环境提供状态指示灯，右上角支持一键全屏隐私浏览器，画面区最大化铺满视口。

## 3. 部署

```bash
# 构建前端
npm ci --prefix src/frontend
npm run build --prefix src/frontend

# 管理员密码由你提供（脚本不生成、不打印任何秘密）
mkdir -p config/deploy/secrets
printf '%s' '你的管理员密码' > config/deploy/secrets/admin_password
chmod 600 config/deploy/secrets/admin_password

# 生成内部密钥、构建镜像、发布不可变 release 并做 readiness 验收
bash scripts/deploy.sh
```

访问 `https://127.0.0.1:56661`，管理密码见 `config/deploy/secrets/admin_password`。数据在 `data/instance`，密钥在 `config/deploy/secrets`，两者均不入库。每次发布生成不可变 release（`config/deploy/releases/`），回退用 `bash scripts/deploy.sh rollback`。

## 4. 停用与备份

```bash
docker compose --env-file config/deploy/releases/<release_id>.env -f compose.yaml down
bash scripts/deploy.sh env-backup     # 环境恢复点：数据库（named volume）+ 全部 Profile 数据
bash scripts/deploy.sh env-restore data/backups/restore-points/<point-dir>   # 恢复
```

完整部署、升级、备份恢复与故障定位见 `DOCKER_DEPLOYMENT.md`。

## 5. 研发

本项目遵循 `repo_template` 规范；测试入口为 `scripts/run_gates.sh`，任务状态在 `docs/tasks`。
