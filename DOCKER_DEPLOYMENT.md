# CBrowser 容器部署与运行架构说明

本文档记录当前 CBrowser 的容器化部署架构、网络配置、数据持久化机制以及针对指纹防关联与局域网接管的专项优化。

---

## 1. 运行现状与访问信息

当前服务已通过 Docker Compose 容器化部署在 macOS（OrbStack Docker Backend / arm64）上：

* **容器名称**：`cbrowser`
* **宿主机监听端口**：`56661`（映射至容器内部 `8080`）
* **网络监听绑定**：`0.0.0.0:56661`（已开启局域网共享）
* **访问入口**：
  * **本机访问**：[http://127.0.0.1:56661](http://127.0.0.1:56661)
  * **局域网访问**：`http://<宿主机局域网IP>:56661`（如 `http://192.168.31.76:56661`）
* **身份认证（Auth Token）**：已启用密码保护。在未登录状态下访问 API 均会被 `401 Unauthorized` 拦截，访问前端网页时需在弹窗中输入访问密码。

---

## 2. 核心架构与解耦机制

```
                                  [ 局域网 / 本机浏览器 ]
                                            │
                                (HTTP / WebSockets 端口 56661)
                                            ▼
┌─ Docker 容器 (Debian Linux, arm64) ────────────────────────────────────────────────┐
│                                                                                   │
│  FastAPI 后端 (:8080) ◄──► 前端静态资源 (React WebUI, 支持中英切换)                │
│       │                                                                           │
│       ├── (CDP 控制通道) ──► 虚拟 Chromium 实例 (CloakBrowser 内核)                │
│       │                         │                                                 │
│       └── (WebSocket 代理) ─► KasmVNC / Xvnc (:100, :6100) ──► (虚拟桌面渲染)      │
│                                                                                   │
│  * 基础环境：纯净 Linux，仅装有 Windows 英文人设字体（Arial、Times 等）            │
│  * 彻底移除：文泉驿（WenQuanYi）、Unifont 等所有中文字体包                         │
│  * 网络穿透：宿主机网关映射 (host-gateway)                                        │
└───────────────────────────────────────────────────────────────────────────────────┘
                                            │
                             (卷挂载持久化 /data)
                                            ▼
                           宿主机目录：~/.cbrowser/
                           ├── profiles.db   (SQLite 数据库)
                           ├── settings.json (全局配置与 License)
                           └── profiles/     (各浏览器会话 Session/Cookies 数据)
```

---

## 3. 关键特性与专项优化（落地项）

### 3.1 彻底清除中文字体指纹（防止暴露中文环境）
* **背景**：在宿主机 Mac 原生运行浏览器时，底层 Chromium 会直接通过 CoreText 读取系统的中文字体（如苹方 `PingFang SC`、黑体 `STHeiti` 等）并暴露给检测站；同时官方 Docker 镜像在构建时由于 Playwright 自动安装了推荐包 `fonts-wqy-zenhei`（文泉驿正黑）。
* **优化实施**：
  1. 在 `Dockerfile` 中执行依赖安装后，主动 purge 清理 `fonts-wqy-zenhei`、`fonts-unifont`、`fonts-ipafont-gothic`、`fonts-tlwg-loma-otf`；
  2. 刷新字体缓存 `fc-cache -f`；
* **效果**：容器内 `fc-list :lang=zh` 计数归 **0**，各类指纹检测网站（如 CreepJS / BrowserLeaks）探测到的中文字体数量彻底为 0，同时不再泄露 Apple M2 GPU 硬件信息。

### 3.2 局域网 HTTP 下的剪贴板双向同步重构
* **背景**：现代浏览器强制限制 `navigator.clipboard` 必须在安全上下文（HTTPS 或 localhost）中才能读写。在局域网纯 HTTP（`http://192.168.x.x:56661`）下，原版代码会直接报错并触发误判逻辑将同步开关自动关闭；同时原代码在输入框（`<input>` / `<textarea>`）内复制时无法捕获选区。
* **优化实施**：
  1. **宿主机 → 容器粘贴**：引入原生透明输入框捕获层（监听原生 `paste` 事件），在非 HTTPS 环境下通过浏览器底层行为无阻碍捕获 `Cmd+V` / `Ctrl+V`，并自动调用 API 将内容灌入容器内 X11 剪贴板；
  2. **容器 → 宿主机复制**：修复 `browser_manager.py` 内部注入脚本，增加对输入框 `selectionStart` / `selectionEnd` 的选区读取；在写回宿主机剪贴板时引入 `document.execCommand('copy')` 降级支持；
  3. **工具栏直推按钮**：在 WebUI 工具栏新增「文本直推（纸飞机图标）」按钮，支持展开单行文本框直接粘贴任意字符回车推送至远程 Chrome；
  4. **操作流水日志**：后端 `/api/profiles/{id}/clipboard` 补齐详细日志，实时输出写入与读取的文本长度及前缀预览。

### 3.3 窗口防拖偏与一键居中复位
* **背景**：Docker 容器内的虚拟显示环境未安装重型桌面窗口管理器，手动拖拽 Chrome 标题栏可能将窗口拖偏至 1920×1080 分辨率之外无法拉回。
* **优化实施**：
  1. 启动参数增加 `--window-position=0,0` 及 `--window-size=1920,1080`，默认贴紧左上角启动；
  2. 后端新增 `POST /api/profiles/{id}/center-window` 接口，通过 CDP 协议向浏览器分派 `Browser.setWindowBounds`；
  3. 控制台全屏按钮旁新增「居中复位窗口（旋转复位图标）」按钮，点击即可一键将偏移窗口拉回原点铺满。

### 3.4 局域网地址直连与 Mac 域名穿透（方案二）
* **背景**：配置了代理（如 `host.docker.internal:7890`）的 Profile 默认会把所有请求丢给代理，导致无法访问 Mac 宿主机上的本地服务，且 `.local` 域名在容器内默认被错误解析到 `127.0.0.1`。
* **优化实施**：
  1. **宿主机域名映射**：在 `docker-compose.yml` 中配置 `extra_hosts` 将 `karsondemacbook-pro.local:host-gateway` 映射至宿主机网关；
  2. **代理白名单放行**：启动 Chrome 时追加 `--proxy-bypass-list=<-loopback>;localhost;127.0.0.1;host.docker.internal;*.local;192.168.*;10.*`；
* **效果**：在容器内 Chrome 的地址栏中可直接无缝访问宿主机服务（例如 `http://karsondemacbook-pro.local:37281/`），外网请求继续走代理，内网请求自动直连。

---

## 4. 常用运维与管理命令

所有命令均在项目根目录（`/Users/karson/kar/code/CBrowser`）下执行：

### 4.1 容器启停
```bash
# 后台构建并启动
docker compose up --build -d

# 停止容器
docker compose stop

# 重启容器
docker compose restart

# 销毁容器（数据保存在宿主机 ~/.cbrowser，不受影响）
docker compose down
```

### 4.2 查看运行日志
```bash
# 查看实时日志
docker compose logs -f

# 过滤剪贴板同步日志
docker compose logs -f | grep Clipboard
```

### 4.3 数据备份与恢复
所有浏览器数据、Cookie、插件、配置文件均存放在宿主机目录：
```bash
~/.cbrowser/
```
若需备份环境，只需在停止容器后完整复制该目录即可。
