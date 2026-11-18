# d050 docker-py 可序列化 volume subpath 挂载，旧 volumes 字典形式无此表达能力

- 来源：s025 spike（t080 实施期）
- 结论：本仓锁定 docker-py 7.2.0 的 `Mount(target, source, type="volume", subpath=...)` 会序列化为 create 配置 `HostConfig.Mounts[].VolumeOptions.Subpath`，只读标志正确；旧 `volumes={host_path: {"bind": ...}}` 字典形式无法表达 subpath，迁移必须切换到 `mounts=[Mount]`。
- 证据：`docs/spikes/s025_docker_volume_subpath_mounts/code/probe_sdk_subpath.py` 于 2026-11-18 云端实跑 PASS（三项挂载的 Subpath 与 ReadOnly 均按预期序列化）；脚本不接触 daemon，只证明客户端序列化。
- 影响：t080 的 MountPlanner 与 DockerAdapter 挂载构造以此为据；daemon 对 subpath 缺失/越界/只读/UDS 的实际行为不在本条结论内，见 p127 待本地补验。
- 现状：有效
