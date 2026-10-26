# CBrowser 容器化部署与运维手册

本文档记录当前 CBrowser 的实际容器化部署架构、配置参数、网络端口以及数据备份与恢复流程。

______________________________________________________________________

## 1. 运行现状与访问信息

当前服务已通过 Docker Compose 部署运行（支持 Linux 及 macOS OrbStack Docker 后端）：

- **容器名称**：`cbrowser`
- **宿主机监听端口**：`56661`（映射至容器内部 `8080`）
- **网络监听绑定**：`0.0.0.0:56661`
- **访问入口**：
    - 本机访问：`http://127.0.0.1:56661`
    - 局域网访问：`http://<宿主机IP>:56661`
- **访问凭证**：若设置了 `AUTH_TOKEN`，系统启用令牌保护。初次打开前端页面时需在弹窗中输入配置的访问密码，API 请求需携带 `Authorization: Bearer <AUTH_TOKEN>` 请求头。

______________________________________________________________________

## 2. 容器架构与目录拓扑

```text
宿主机 Chrome / 局域网客户端
         │
         ▼
  0.0.0.0:56661 (HTTP / WebSocket)
         │
         ▼
  ┌───────────────────────────────────────────────────────────┐
  │ Docker 容器: cbrowser (内部端口 8080)                     │
  │                                                           │
  │  FastAPI (Uvicorn)                                        │
  │   ├── 前端静态产物托管 (React 19 SPA, /app/frontend/dist) │
  │   ├── 控制与配置 API (/api/*)                             │
  │   └── CloakBrowser 隐私指纹引擎进程生命周期管理           │
  │                                                           │
  │  运行沙箱支持:                                            │
  │   ├── Xvfb / KasmVNC                                      │
  │   └── 字体与环境防关联配置                               │
  └─────────────────────────────┬─────────────────────────────┘
                                │ 卷挂载: ~/.cbrowser -> /data
                                ▼
                       宿主机持久化目录:
                       ~/.cbrowser/
                       ├── profiles.db       (配置元数据)
                       ├── settings.json     (运行时配置)
                       └── profiles/         (各浏览器会话数据与 Cookies)
```

______________________________________________________________________

## 3. 部署与启动命令

所有命令在项目根目录下执行：

### 3.1 构建并启动服务

```bash
# 拷贝环境配置
cp config/.env.example .env

# 构建并启动容器
docker compose up --build -d

# 查看容器日志
docker compose logs -f
```

### 3.2 容器启停与检查

```bash
# 检查运行状态与健康检查
docker compose ps

# 停止容器
docker compose down

# 检查健康接口
curl -s http://127.0.0.1:56661/api/health
```

______________________________________________________________________

## 4. 数据备份与恢复

所有浏览器持久化数据（Cookies, 本地缓存, Profile 配置）均存放在宿主机目录：

```bash
~/.cbrowser/
```

### 备份

```bash
# 建议先停止服务确保写入完整
docker compose stop
tar -czvf cbrowser_backup_$(date +%Y%m%d_%H%M%S).tar.gz -C ~/.cbrowser .
docker compose start
```

### 恢复

```bash
mkdir -p ~/.cbrowser
tar -xzvf cbrowser_backup_XXXX.tar.gz -C ~/.cbrowser
docker compose up -d
```
