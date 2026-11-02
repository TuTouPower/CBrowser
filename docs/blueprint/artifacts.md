# Artifact 文件管理

Artifact 与浏览器用户数据严格分离：浏览器 Profile 目录只保存 Cookie、站点数据与浏览器状态；用户文件保存在数据库同级的 `artifacts/` 下（生产为 `/data/artifacts`），按 Profile 隔离。Supervisor 以 `--data-root/artifacts` 挂载同一目录，因此 API 与容器看到同一份文件。

## 存储布局

```text
artifacts/{profileId}/
├── uploads/{artifactId}/{name}
└── downloads/{artifactId}/{name}
```

- 上传与下载都先写入临时文件，成功后原子发布；失败或超限时删除临时文件，不留下半文件。
- 发布后的目录与文件应用 Browser runtime UID/GID（默认 1000），目录 0750、文件 0640；无法 chown 的宿主开发环境回退到 0755/0644，保证容器 UID 1000 可读。
- 容器内路径固定为 `/exchange/uploads/{artifactId}/{name}` 与 `/exchange/downloads/{artifactId}/{name}`；API 响应不返回宿主路径。
- 文件名经过单路径组件清洗（去掉目录、控制字符、Windows 保留名并截断到 255 字节）；Profile ID 限制为 `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`，`..` 与路径分隔符拒绝。
- 删除 Profile 时经 Artifact Service 删除数据库记录与该 Profile 的 Artifact 目录。

## 上传 API

`POST /api/v1/profiles/{profileId}/artifacts?filename={name}`，请求体为文件原始字节，`Content-Type` 为文件 MIME。

- 需要登录会话与 CSRF/Origin 校验；跨 Profile 的读取、下载、删除返回 404。
- 默认单文件上限 256 MiB、每 Profile 200 个、每 Profile 总量 2 GiB；磁盘保留 16 MiB。环境变量 `ARTIFACT_MAX_BYTES`、`ARTIFACT_MAX_COUNT`、`ARTIFACT_MAX_TOTAL_BYTES` 覆盖默认值；`create_app()` 参数可覆盖测试值。
- 拒绝危险可执行 MIME；`Content-Length` 超限直接 413。
- 成功返回 `ArtifactResponse`，包含 `id`、`name`、`size`、`kind`、`state`、`sha256`、`container_path` 与创建时间。
- `GET /api/v1/profiles/{profileId}/artifacts` 列表；`GET .../artifacts/{artifactId}` 下载（`application/octet-stream`、`nosniff`、`no-store`、`Content-Disposition: attachment`）；`DELETE ...` 删除需要 CSRF。

## 下载捕获与对账

- CDP 下载完成事件记录 `size_bytes` 与 `sha256`；Supervisor 的 `DownloadArtifactForwarder` 将容器路径翻译为宿主路径，经内部 Supervisor RPC 提交 API。
- `<path>.crdownload`、`.part`、`.partial`、`.download`、`.tmp`、`.incoming-*` 与 `.tmp-*` 永不入库。
- Agent 启动、终端重放与 CDP 会话重建时扫描 `/exchange/downloads` 的直接子文件一次，为缺少完成事件的已完成文件生成补登事件；判断键为 `(resolved_path, sha256)`。Artifact 子目录不参与扫描。
- API 侧按 `(profile, sha256, storage_path)` 去重；重复事件返回 `duplicate` 或不重复入库；同名不同路径视为新下载。
- 入库时把下载文件移动到 `downloads/{artifactId}/`，数据库记录 `kind=download`、`sha256`、`storage_path`。

## 前端

`/profiles/:profileId/files` 页面调用上述 API 列出、上传、下载、删除当前 Profile 的 Artifact，并显示 `container_path`；上传按钮使用隐藏 file input，删除前确认。

## 验证

- 单元：原子上传、半文件清理、MIME/配额/磁盘空间、文件名清洗、路径穿越、下载去重、扫描补登、事件校验和。
- 集成：真实 HTTP 上传/列表/下载/删除、跨 Profile 拒绝、内部 Supervisor ingest 鉴权与去重。
- 真实 E2E：真实 Chrome 容器下载后事件携带校验和；Agent 重启只补登缺少事件的文件，重复重启不重复补登。
