# Archived spikes

这些目录是历史实验证据快照，不是当前可运行代码。

- 请勿在仓库内直接运行；先完整复制到 `.scratch/<probe_name>/`，按各目录 `report.md` 的依赖与清理契约执行。
- 部分旧 harness 会关闭 X11/PulseAudio/Selkies 鉴权或启动无认证控制面，只允许在隔离探针网络与临时容器中运行。
- 旧报告中的 `docs/spikes/` 路径对应现在的 `docs/archive/spikes/`。
- 探针写出的秘密与工作目录（如 `probe_work/turn_secret.txt`）已被 `.gitignore` 忽略，不得入库。
