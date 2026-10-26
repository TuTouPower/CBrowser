# 需求规范：浏览器沙箱与数据隔离 (browser_isolation)

## 1. 业务目标与适用范围

本文档规定 CBrowser Profile 容器化沙箱隔离与数据隔离的具体契约。
系统为每个浏览器 Profile 分配独立的 Docker 容器实例，杜绝不同身份之间的进程、内存、网络、调试端口与存储冲突。

## 2. 行为契约

### 2.1 容器生命周期与命名

- 每个 Profile 创建后分配唯一的 `profile_id`。
- 容器命名规则固定为：`cbrowser-runtime-{profile_id}`。
- 容器标签必须包含：
    - `com.cbrowser.managed=true`
    - `com.cbrowser.profile-id={profile_id}`
    - `com.cbrowser.config-version={version}`
    - `com.cbrowser.runtime-image={digest}`
- 容器只能由特权受限的 `cbrowser-supervisor` 创建与管理，外部客户端无法传入自定义镜像、宿主机挂载或容器命令。

### 2.2 宿主机数据目录隔离

宿主机数据存储布局固定为：

```text
/data/
├── cbrowser.db
├── settings/
├── engine-cache/
├── profiles/
│   ├── {profile_id_A}/
│   │   ├── profile/          # 浏览器真实用户数据（Cookies, 网站存储, 历史）
│   │   ├── exchange/         # 文件上传与下载交换区
│   │   └── runtime.json      # 当前只读运行参数快照
│   └── {profile_id_B}/
├── artifacts/
└── backups/
```

- 每个运行容器只挂载自身对应的 `profiles/{profile_id}/profile` 与 `exchange` 目录。
- 严禁任何容器访问其他 Profile 的数据目录。
- 浏览器容器关闭或销毁时，宿主机数据必须完整保留。

### 2.3 权限与安全限制

- 容器内运行用户必须为非 root 用户（UID 1000）。
- 开启 `no-new-privileges`，删除非必要 Linux capabilities（如 `SYS_ADMIN`、`NET_ADMIN`）。
- 容器根文件系统配置为只读（Read-Only Rootfs），仅允许对 `/tmp`、`/dev/shm` 以及 Profile 专属数据目录进行写入。
- 严禁挂载 `/var/run/docker.sock`。
- 严禁使用宿主机网络模式（`--net=host`）。
- Chromium CDP 调试端口仅监听容器内回环（`127.0.0.1`），不得对公网或容器网络直接暴露。

## 3. 验收标准

- [ ] AC-001：同时运行 Profile A 与 Profile B 时，Docker 存在两个独立的容器 `cbrowser-runtime-A` 与 `cbrowser-runtime-B`。
- [ ] AC-002：Profile A 设置的 Cookies 与 LocalStorage 在 Profile B 中不可见，且相互不产生任何污染。
- [ ] AC-003：Profile A 容器内无法通过文件系统访问 Profile B 的数据目录。
- [ ] AC-004：浏览器运行容器中执行 `docker ps` 或探测 Docker Socket 均失败。
- [ ] AC-005：外部网络无法直接连接容器内的 CDP 调试端口。
