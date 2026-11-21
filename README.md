# cbrowser

cbrowser 是面向隐私浏览器与多身份隔离的单机 Docker 管理系统。以 Google Chrome 作为唯一外部客户端，通过 Selkies 2.2.1 WebRTC 传输画面，每个 Profile 由独立 Browser/Stream 容器沙箱隔离。

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

- **预构建安装**：从 [GitHub Releases](https://github.com/TuTouPower/cbrowser/releases) 下载适合宿主架构的部署包，解压并运行 `bash install.sh`。
- **源码自建**：克隆仓库并切换到所需的发布 tag，运行 `bash scripts/build_images.sh`，成功后运行 `bash scripts/deploy.sh`。

先按手册创建管理员密码文件。两种方式均自动交付前端和 Windows、macOS 字体。部署成功后，在运行 Docker 的同一台机器上用 Chrome 打开 `https://127.0.0.1:56661`。

## 4. 运维

安装前提、密码文件、引擎下载代理、升级回退、停止和备份见 [部署手册](DOCKER_DEPLOYMENT.md)。

## 5. 研发

本项目遵循 `repo_template` 规范；测试入口为 `scripts/run_gates.sh`，任务状态在 `docs/tasks`。
