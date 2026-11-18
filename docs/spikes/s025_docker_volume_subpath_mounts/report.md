---
slug: "docker_volume_subpath_mounts"
status: "completed"
sid: "s025"
---

# Spike report: Docker volume subpath 挂载的 SDK 序列化与 daemon 语义

## 问题

t080 需要以 named volume + 精确 subpath 取代 macOS 宿主 bind mount，作为 Browser/Stream 只能访问被授权子目录的隔离边界。须先核实两件事：

- 本仓锁定的 Docker SDK（pyproject `docker>=7.0.0`，门禁 venv 实测 docker-py 7.2.0）能否把 volume subpath 序列化进容器创建请求；
- 当前 Engine 对 subpath 不存在时的行为、只读精确子目录隔离、文件/UDS 经 subpath 挂载的实际语义。

## 成功判据

- SDK 侧：捕获 `containers.run(mounts=[Mount(..., subpath=...)])` 生成的 create 配置，`HostConfig.Mounts[]` 每项均为 `Type=volume` 且带 `VolumeOptions.Subpath`，只读标志正确。
- daemon 侧：在隔离 Engine 上以正负对照实测 subpath 缺失/越界/符号链接逃逸被拒、只读生效、UDS 文件经 subpath 挂载可达。此项须真实 Engine，云端无 Docker（`docker: command not found`、无 `/var/run/docker.sock`），不在本 spike 云端部分冒充完成。

## 尝试

- `code/probe_sdk_subpath.py`：进程内替换 APIClient 的 create/start/inspect，捕获 `containers.run` 生成的 host_config，不接触任何 daemon。

## 证据

- docker-py 7.2.0 输出（2026-11-18 云端实跑）：三项挂载全部序列化为 `Type: "volume"` + `VolumeOptions.Subpath`（`profiles/p1/profile`、`windows/abc`、`p1`），fonts 项 `ReadOnly: true` 正确；脚本末行 `PASS`。
- 旧 `volumes={host_path: {"bind": ...}}` 字典形式无 subpath 表达能力，构成必须切换到 `mounts=[Mount]` 的直接证据。
- daemon 侧：本轮未取得证据（云端无 Docker Engine），按用户 2026-11-18 裁定登记 p127 待本地统一补验，不以文档推定代替实测。

## 结论

- SDK 序列化契约成立：t080 可按 `Mount(target, <prefix>-<data|fonts|runtime>, type="volume", subpath=<卷内相对路径>)` 实现，缺失/越界 subpath 的拒绝点放在本仓 MountPlanner 的构造期校验（不依赖 daemon 兜底）。
- daemon 行为（subpath 不存在时是否创建、只读隔离、UDS 穿透）在真实 Engine 上仍未验证；设计按 Docker Engine ≥26 / API ≥1.45 的公开契约冻结，真实验证列入 p127 本地补验清单。结论可信度：SDK 侧高；daemon 侧待验。

## 是否采纳

- 决定：是
- 理由：SDK 序列化已实证，方案不依赖 daemon 私有卷物理路径；daemon 语义风险由构造期校验与 p127 本地补验承接，禁止退回 macOS 热数据 bind mount。
- 后续 task：t080
- 无需后续理由：不适用

## 关联 findings

- d050（docker-py 可序列化 volume subpath 挂载，旧 volumes 字典形式无此表达能力）
