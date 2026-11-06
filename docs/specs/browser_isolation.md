# 需求规范：浏览器沙箱与数据隔离 (browser_isolation)

## 1. 业务目标与适用范围

本文档规定 CBrowser v2 Profile 容器化沙箱隔离与数据隔离契约。t003 实现 Browser Runtime；Stream、Supervisor 编排及正式部署由后续 task 集成，以下完整双容器拓扑是目标契约。
系统为每个浏览器 Profile 分配独立的沙箱环境（同 Profile 双容器：Browser Runtime 与 Stream Runtime），杜绝不同身份之间的进程、内存、网络、调试端口与存储冲突。

## 2. 行为契约

### 2.1 容器生命周期与双容器拓扑

- 每个 Profile 启动时由 Supervisor 编排为一对专属沙箱容器：
    - `{prefix}-browser-{profile_id}`：核心运行沙箱，以 `HostConfig.IpcMode=shareable` 和 1 GiB `/dev/shm` 运行真实 CloakBrowser、Xvfb、PulseAudio（48000Hz）与 UDS Agent。
    - `{prefix}-stream-{profile_id}`：远程显示沙箱，以 `IpcMode=container:{prefix}-browser-{profile_id}` 加入同 Profile IPC 命名空间，通过 MIT-SHM 共享内存捕获画面并进行 WebRTC 编码。
- `{prefix}` 由 Supervisor 的 `--prefix` / `CBROWSER_PREFIX` 配置提供（默认 `cbrowser-t005`），用于隔离不同部署或测试栈的容器、网络与端口所有权。
- 容器标签必须包含：
    - `com.cbrowser.managed-by=supervisor`
    - `com.cbrowser.profile-id={profile_id}`
    - `com.cbrowser.instance-id={runtime_instance_id}`
    - `com.cbrowser.role=browser` 或 `stream`（Supervisor 的 cache-init / network-policy 辅助容器使用各自角色值）
    - `com.cbrowser.network-policy={policy_version}`（当前 `v1`）
    - `com.cbrowser.config-version={version}`
    - `com.cbrowser.prefix={prefix}`
- Stream Runtime 的 UDP mux 端口当前仅发布到宿主回环 `127.0.0.1`；本机 Chrome 可直连，跨机或公网直连需在部署阶段调整绑定与网络策略。
- 容器只能由特权受限的 `cbrowser-supervisor` 创建与管理，外部客户端无法传入自定义镜像、宿主机挂载或容器命令。

### 2.2 宿主机数据目录隔离

宿主机统一数据存储布局为：

```text
/data/
├── cbrowser.db
├── settings/
├── engine-cache/                     # 只读挂载：统一引擎二进制缓存（/data/engine-cache:ro）
├── profiles/
│   └── {profile_id}/
│       └── profile/                 # 读写挂载：浏览器真实用户数据（/data/profiles/{id}/profile）
├── runtime-events/
│   └── {profile_id}/                # 读写持久：退出与终态事件（/data/runtime-events/{id}）
├── runtime/
│   └── {profile_id}/                # 瞬态卷：UDS 套接字、Xauthority 与 PulseAudio
├── artifacts/{profile_id}/downloads/ # 读写挂载：下载交换区（/exchange/downloads）
└── backups/
```

- 每个 Browser Runtime 仅挂载自身专属的 `profiles/{profile_id}/profile`、`artifacts/{profile_id}/downloads` 及只读 `engine-cache`。
- Stream Runtime 严格禁止挂载浏览器用户数据目录。
- 严禁任何容器跨 Profile 访问其他 Profile 的数据目录或上级 `/data` 目录。
- 浏览器容器关闭或销毁时，宿主机用户数据必须完整保留。

### 2.3 权限与安全限制

- 容器内运行用户必须为非 root 用户（UID 1000 / GID 1000）。
- 开启 `no-new-privileges`，删除所有 Linux capabilities（`--cap-drop ALL`）。
- 容器根文件系统配置为只读（Read-Only Rootfs），仅对 `/tmp`、`/dev/shm` 以及 Profile 专属数据目录进行写入。
- 严禁挂载 `/var/run/docker.sock`。
- Chromium CDP 调试端口仅监听容器内回环（`127.0.0.1`），不得对公网或容器网络直接暴露。
- 外部自动化必须经由受控 UDS（`/run/cbrowser/runtime/agent.sock`）以标准 HTTP/WebSocket 协议受权访问。

### 2.4 指纹平台与平台字体集隔离（t041）

- 每个 Profile 绑定一个指纹平台（`windows` 默认 / `macos`）与可选的同平台不可变字体集（`font_set_id`）；两者属运行配置，修改任一生成新 `ProfileConfigVersion`。
- 字体可见集合按 Profile 严格隔离：绑定平台字体集时，`FONTCONFIG_FILE` 只以 `<dir>` 白名单声明该集目录（Supervisor 只读挂到 `/run/cbrowser/fonts/{platform}/{set_id}`，不挂整个字体根目录、不挂给 Stream），不 include `/etc/fonts/fonts.conf`；Liberation / Nimbus / 文泉驿等 Linux 专属字体对两平台都不可见，windows 与 macos 的专有字体互不串扰。`font_set_id` 为 null（平台字体未配置）时回退为镜像内基础字体目录 `/opt/cbrowser-base-fonts` 可见，保证页面可用，runtime 状态报告「平台字体未配置」并在 `missing_fonts` 标明当前暴露 Linux 基础字体。
- 平台一致性：`navigator.platform`、UA 与 UA-CH `platform` / `platformVersion` 与所选平台一致；CH `architecture=arm` 与 windows UA `x64` 的差异按用户裁决不做半套覆盖（`d032` + `p045`）。
- 失败封闭：绑定字体集缺失或 manifest / 文件不一致时启动失败并报告 `font_set_unavailable`；`font_set_id` 为 null 正常启动、回退基础字体可见，runtime 状态报告平台字体未配置并在 `missing_fonts` 标明当前暴露 Linux 基础字体。
- 平台字体不进入任何镜像层与 git 仓库；`font_bundle` 已删除（AC-009）。

## 3. 验收标准

- [x] AC-001：同时运行 Profile A 与 Profile B 时，Docker 存在两个独立的容器沙箱，Cookie 与存储互不污染。
- [x] AC-002：Profile A 容器内无法通过文件系统访问 Profile B 的数据目录或宿主 `/data/cbrowser.db`。
- [x] AC-003：浏览器运行容器中执行 `docker ps` 或探测 Docker Socket 均失败。
- [x] AC-004：外部网络及宿主网络无法直接连接容器内的 CDP 调试端口。
- [x] AC-005：获授权的同 Profile Stream 客户端才能接入 X11 与音频，未授权连接被严格拒绝。
- [x] AC-006（t041）：windows Profile 检出 Windows 检测字体而检不出 Mac 专有字体，macos 反之；两平台都检不出 Liberation 等 Linux 专属字体，可见字体只来自基础字体与绑定集。
- [x] AC-007（t041）：绑定字体集缺失或 manifest / 文件不一致时启动失败封闭 `font_set_unavailable`；`font_set_id` 为 null 正常启动并报告平台字体未配置。
- [x] AC-008（t041）：任一镜像层与 git 仓库不含平台字体文件，字体只在运行时只读挂载。
