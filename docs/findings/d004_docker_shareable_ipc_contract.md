# d004 Docker IPC 供体必须显式 shareable 才可被另一容器加入

- 来源：t001 / s001_selkies_runtime；2026-10-27T01:36:00+08:00 Docker 实验
- 结论：Browser Runtime 必须显式设置 HostConfig.IpcMode=shareable，Stream Runtime 才能用 IpcMode=container:<browser-id> 加入。shareable 仍是该供体专属 IPC 命名空间，不是宿主 IPC。
- 证据：实验 Docker 29.4.0 对默认私有 IPC 供体执行 `docker run --ipc container:cbrowser-spike-runtime-browser ...`，返回 `failed to join IPC namespace: ... non-shareable IPC (hint: use IpcMode:shareable for the donor container)`；主控检查并确认该输出。供体改用 `--ipc shareable` 后 Stream 容器可启动，docker inspect 显示 shareable，XShmGetImage 正例实际取到像素。负例、安全隔离、音频及媒体端到端测试仍需单独通过。
- 影响：Supervisor 创建 Browser Runtime 时显式指定 shareable 与 1 GiB shm；禁止使用 host IPC。此结论不代表 Xauthority 或跨 Profile 访问控制已验收。
- 现状：有效
