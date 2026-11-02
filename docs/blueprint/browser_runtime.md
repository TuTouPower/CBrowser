# Browser Runtime

## 职责与交付边界

Browser Runtime 运行单个 Profile 的真实 CloakBrowser、Xvfb、Openbox、PulseAudio 和受控 UDS Agent。t003 提供独立镜像与协议；动态容器编排、引擎缓存初始化、API 事件消费和 Stream Runtime 分别由 t005、t008、t004 等后续 task 对接。正式 compose 与旧入口尚未切换。

运行用户为 UID/GID 1000，根文件系统只读，删除全部 capabilities，开启 no-new-privileges。Supervisor 创建容器时设置 restart=no、IPC=shareable、1GiB /dev/shm，只挂载该 Profile 专属数据和只读引擎缓存，禁止 Docker Socket、宿主 X11、其他 Profile 目录或上级 /data。

## 数据与挂载

|宿主统一数据根下路径|容器路径|用途|
|---|---|---|
|engine-cache|/data/engine-cache:ro|SDK 初始化完成的 Linux 引擎缓存|
|profiles/{id}/profile|/data/profiles/{id}/profile|浏览器真实用户数据|
|artifacts/{id}/downloads|/exchange/downloads|默认下载目录|
|artifacts/{id}/uploads|/exchange/uploads|用户上传文件；页面文件选择对话框侧栏 `Uploads` 书签指向此目录|
|runtime-events/{id}|/data/runtime-events/{id}|独立于用户数据的持久运行与下载事件|
|专属运行卷|/run/cbrowser/runtime|agent.sock、runner_info.json、Xauthority、进程配置|
|专属 X11 Socket 卷|/tmp/.X11-unix|Xvfb Socket，目录 0750|
|专属 Pulse Socket 子目录|/run/cbrowser/runtime/pulse|Browser 生成 Pulse Socket/cookie；Stream 仅挂载该子目录到自己的 /pulse|

镜像安装 GTK 3：Chromium 在 Linux 上只经 GTK 或 xdg portal 打开页面 `<input type=file>` 对话框，两者皆无时点击无任何反应（p014 实测）。Runtime Agent 固定注入 `--disable-gtk-ime`：GTK 输入法在 Selkies 为组合文本临时重映射键码后读取过期键表，会提交错误汉字（t004 composition E2E 实测）。入口在 tmpfs 的 `$XDG_CONFIG_HOME/gtk-3.0/bookmarks` 写入 `file:///exchange/uploads Uploads`，每次启动重建。

运行卷与持久事件目录用途不同，不允许用瞬态运行卷代替事件持久化。初始化卷的所有权与 sticky 位由 Supervisor 负责；运行容器以非 root 消费。Mac bind 的 UID 映射须实际验证，不能按宿主 UID 数字推断容器权限。

引擎版本由 SDK 当前平台版本或显式 --engine-build 选择。路径为 chromium-{build}/chrome；Pro 缓存目录支持 SDK 的 -pro 后缀。启动前验证 Linux ELF64 架构、缓存路径归属与实际 --version，缺失或不匹配即失败，不下载、不回退到 /opt。Supervisor 的初始化角色可写缓存，Runtime 只读；许可参数由外部配置提供，不写镜像或示例默认值。当前真实执行证据仅覆盖 arm64 普通引擎，不能据目录支持声称 Pro 或 x86 执行通过。

## 进程与退出事实

容器 PID1 为 tini，子进程 supervisord 管理两个独立服务：

- Browser Runner：autorestart=false，启动 PulseAudio、Xvfb、Openbox 及 SDK persistent context；SDK driver 与真实 Chrome 生命周期由 Runner 持有。
- UDS Agent：autorestart=true，独立连接 Chrome loopback CDP，重启不会重启浏览器。supervisord 不配置管理 RPC Socket。

固定 SDK CloakBrowser0.6.4、Playwright1.64.1。Runner 使用真实 SDK persistent-context API 保留配置语义，通过受控 wrapper 观察 Chrome 子进程真实 wait 状态。Chrome exit0 且 SDK driver/Xvfb 存活才记正常退出；SIGKILL Chrome 规范化为137；SDK driver 或显示基础设施丢失导致 Chrome0 时记 lifecycle/process_observation_lost、state=error，不能据0清除 running 意愿。私有 Playwright driver 进程访问依赖固定版本，升级须重验（d016）。

Runner 接收 SIGTERM/SIGINT 后正常关闭 SDK context 与子系统；Supervisor 最终决策由 t005 负责。不可复用已初始化 runtime_instance_id 启动新浏览器，必须分配新实例。已落盘终态恢复只提供查询，不重新启动 Chrome。

## 持久化与恢复

- events/runtime/{instance_id}/{event_id}.json：逐事件保存运行事实；终态 event_id 根据实例确定，重放保持不变。
- instances/{instance_id}/state.json：实例状态权威。
- state.json：最后写入的发现缓存，不是当前代权威；运行期始终按明确实例读取。
- events/downloads/{event_id}.json：下载开始与完成/取消事实，使用相同 guid 关联，不保证列表按时间排序。

目录创建、文件写入及替换均要求 fsync；EIO/EINVAL/ENOTSUP 等错误失败关闭。先写终态事件，再写实例状态；进程在两步间消失时按该实例已落盘终态恢复。迟到旧实例可更新发现缓存，但不能覆盖新实例独立 journal。坏 JSON、身份/版本不一致、冲突终态或缺失已初始化状态均显式报错。该协议不等于实际断电测试已通过。

## 显示、音频与配置

Xvfb 使用 Profile 分辨率、24位色深，启用 MIT-SHM/XTEST/XFIXES，关闭 TCP。启动实际 Chrome 后按其 PID 查找顶层窗口并设置尺寸、位置；只有显示、浏览器、PulseAudio 和 CDP 均就绪才发布 ready。DPR 固定1，不能用根窗口尺寸代替 Chrome 完整 UI 测量。

PulseAudio 固定48000Hz与 cbrowser_sink，采集源为 cbrowser_sink.monitor。Runner 在 /run/cbrowser/runtime/pulse 生成 Socket/cookie；Stream 只挂载这个子目录，不能取得含 agent.sock、runner_info.json 的整个运行卷。相同 UID 可能绕过 cookie 校验，因此跨 Profile 隔离依赖专属挂载和 IPC，不能只依赖 cookie；不同 UID 错误凭据须实际拒绝（d011）。同 Profile XShm 需加入 Browser IPC，跨 IPC 必须验证 XShmAttach BadAccess，普通 X11 查询不等于 XShm 捕获。

配置消费 t002 不可变快照；身份、版本与配置先校验再创建目录或启动进程。受控 launch_args 不允许覆盖 CDP、用户数据、显示尺寸与危险进程启动参数，日志不回显原始拒绝参数。Google 默认搜索仅在首次成功初始化时经现有 context 设置页面完成，原子 marker 防止重启覆盖用户后续选择，不创建第二个浏览器。

## UDS 与下载协议

agent.sock 位于专属运行卷，父目录0750。先在 umask077 下绑定，再设置0660，最后交给 Uvicorn 接收连接，避免监听期间权限暴露。UDS 访问权来自 Supervisor 专属挂载与 API 鉴权边界，Agent 不提供远程登录或通用文件接口。

|接口|行为|
|---|---|
|GET /health|显示/音频/浏览器/CDP 实际健康；失败时 ready=false|
|GET /config_version|Profile、实例与配置版本；未知身份不猜版本1|
|POST /control|仅 close、rearm_downloads；等待命令 ACK，失败返回 error|
|GET /events/runtime|持久运行事实，供 Supervisor 转交唯一 SQLite 写入者|
|GET /events/downloads|下载事实，供后续 Artifact 服务消费|
|GET /cdp/version|CDP 元数据|
|WebSocket /cdp|双向 CDP 流，外部命令连接断开后自动恢复默认下载策略并等待 ACK|

Chrome CDP 仅监听容器回环，禁止宿主端口映射或容器网络直连。下载完整性以实际文件内容与 completed 事件共同证明；开始事件不能当完成事件。只有确实存在且位于默认下载目录的文件才公开 captured path，外部覆盖目录不能冒充默认 Artifact。事件接口没有消费确认/清理机制，后续 Supervisor/Artifact 服务须按 event_id 去重，不能按列表首条或文件名排序推断最新状态。
