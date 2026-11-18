# d051 GPU 身份由引擎按种子+平台派生，SDK 无 GPU 选择面

- 来源：s026 spike（t075 实施）
- 结论：CloakBrowser 的 GPU 身份（WebGL vendor/renderer 等）由引擎编译内指纹补丁按 `--fingerprint=<seed>` 与 `--fingerprint-platform=<platform>` 派生；cloakbrowser SDK（0.6.4，与生产镜像同版）不提供任何 GPU 选择参数，项目自加的 `--fingerprint-gpu-vendor` 只是被 SDK 原样透传的 Chromium flag，不构成平台/种子一致性能力证明。受支持组合只有（windows，引擎自动派生）与（macos，引擎自动派生）；macOS×NVIDIA 等手选组合无真实硬件对应。
- 证据：`docs/spikes/s026_gpu_platform_capability/report.md`（SDK 源码逐项核对：`launch_async` 参数面、`build_args` 合并规则、唯一 GPU 相关逻辑 `--ignore-gpu-blocklist` 仅关可用性）；动态实测（多 seed WebGL/WebGPU 实值与重启稳定性）云端无引擎，顺延 p137 本地补验，推翻结论须回 s026 修订。
- 影响：t075 据此删除 `gpu_family` 字段、Runner 的 GPU flag 拼接与前端 GPU 选择；旧 `nvidia`/`intel` 取值在迁移 0013 中按不可等价映射阻塞。后续任何「手选 GPU」需求须先有引擎/SDK 能力证据，不得以透传 flag 冒充。
- 现状：有效
