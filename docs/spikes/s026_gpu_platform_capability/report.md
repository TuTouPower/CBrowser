---
slug: "gpu_platform_capability"
status: "completed"
sid: "s026"
---

# Spike report: 固定引擎 GPU 自动派生与平台能力矩阵核实

## 问题

t075 要取消无平台约束的 `gpu_family`（`auto` / `nvidia` / `intel`）手选契约，改为「固定引擎 + 平台 + 持久 seed 驱动的 GPU 自动策略」。冻结新契约前必须核实：

1. 固定引擎（CloakBrowser 146.0.7680.177.3 / SDK cloakbrowser 0.6.4）的 GPU 身份由什么决定？项目透传的 `--fingerprint-gpu-vendor` 是否被 SDK/引擎校验、是否与平台/seed 一致性挂钩？
2. 各平台可兑现的 GPU 组合是什么？不能兑现的组合如何处置？

## 成功判据

- 能从固定 SDK 源码与项目调用链指出 GPU 身份的决定因素与 flag 的处理方式（校验/透传）。
- 平台能力矩阵只包含有依据的组合；无依据的组合明确判为不支持，而不是继续透传 flag 冒充支持。
- 引擎实测才能回答的部分（各 platform × seed 下 WebGL unmasked vendor/renderer 实值、seed 重启稳定性）明确列为待实测项，不以源码推断冒充实测结论。

## 尝试

- 通读固定 SDK `cloakbrowser 0.6.4`（与生产镜像内版本一致，见 p124 实测记录）源码：`browser.py` 的 `build_args` / `launch_persistent_context_async`、`config.py` 的 `get_default_stealth_args`。
- 通读项目调用链：`runtime_agent/runner.py` 的启动参数构造（`--fingerprint=<seed>`、`--fingerprint-platform=<platform>`、gpu_family 分支）。
- 对照 p116 登记的用户质疑（macOS 与 NVIDIA 组合）与平台硬件事实。

## 证据

- **GPU 身份的决定因素是引擎编译内指纹补丁 + seed + platform**：SDK `config.py:get_default_stealth_args` 只生成 `--fingerprint=<seed>` 与 `--fingerprint-platform=<windows|macos>`；SDK 注释明确指纹补丁「compiled into the binary」，由 seed 驱动派生。SDK 的 launch API 没有任何 GPU 参数。
- **`--fingerprint-gpu-vendor` 是项目自加的原始 Chromium flag，SDK 不校验**：SDK `browser.py:build_args` 把调用方 `args` 按 flag 名合并进参数表（同名覆盖），对该 flag 无取值、平台或 seed 一致性校验；runner.py:600-603 仅在 `gpu_family` 为 `nvidia`/`intel` 时拼接 `NVIDIA`/`Intel`。即旧契约下「选了 NVIDIA」只证明 flag 被透传，不证明引擎产出的 WebGL 身份与平台相容。
- **SDK 唯一的 GPU 相关逻辑与身份无关**：`browser.py` 的 GPU blocklist bypass（`--ignore-gpu-blocklist`）只解决 Docker/Xvfb 下 SwiftShader 提供 WebGL、Windows 下 WebGPU 被块 list 拦截的可用性问题，不决定 vendor/renderer 身份。
- **macOS × NVIDIA 在真实硬件上不存在**：Apple 自 2013 年后不再出货 NVIDIA GPU 的 Mac，Apple Silicon 为 Apple 自研 GPU、Intel Mac 为 Intel/AMD；macOS 指纹声称 NVIDIA vendor 与平台常识冲突（p116 用户质疑成立）。Windows × Intel/NVIDIA/AMD 在真实硬件上均存在，但「存在」不等于本引擎在该 platform/seed 下产出的完整指纹（WebGL renderer 字符串、WebGPU adapter 信息）自洽——该点只能由引擎实测回答。
- **seed 持久性**：Profile 的 `fingerprint_seed` 持久化于配置并在每次启动以 `--fingerprint=<seed>` 传入（runner.py:596-597），SDK 另有 per-profile seed 文件钉固机制（config.py `ensure_profile_seed`）；同一 Profile 的 seed 跨重启不变，引擎派生身份的输入稳定。

## 结论

- 冻结平台能力矩阵：**仅 `(windows, 引擎自动派生)` 与 `(macos, 引擎自动派生)` 为受支持组合**——GPU 身份由固定引擎按持久 seed + 平台派生，产品不再提供任何手选 vendor。旧 `nvidia` / `intel` 强制值不属于可等价映射：迁移时列入阻塞清单（见 t075 AC-004），不静默改写。
- 待实测项（云端无 Docker/引擎二进制，后续已在 p137 本地实测回填，见下）。
- 本地真实容器实测补验（p137，基于部署 release `20261119011954-9af0098` / `browser` 镜像 `sha256:f14753884945f90f5193bf08741f3150e1fc268ce62425b9bcf003766615e9b0`，CloakBrowser `0.6.4` / Chromium `146.0.7680.177`）：
    - `windows` × `seed=111111`（两个独立 Profile 实例）：`UNMASKED_VENDOR_WEBGL = "Google Inc. (NVIDIA)"`，`UNMASKED_RENDERER_WEBGL = "ANGLE (NVIDIA, NVIDIA GeForce RTX 5090 Laptop GPU (0x00002C58) Direct3D11 vs_5_0 ps_5_0, D3D11)"`；跨实例完全一致；`navigator.gpu`（`webgpu.supported`）在容器无 GPU/SwiftShader 环境下为 `false`。
    - `windows` × `seed=222222`：`UNMASKED_VENDOR_WEBGL = "Google Inc. (NVIDIA)"`，`UNMASKED_RENDERER_WEBGL = "ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 (0x00002684) Direct3D11 vs_5_0 ps_5_0, D3D11)"`；`webgpu.supported = false`。
    - `macos` × `seed=333333`（Stop/Start 重启前后对照）：`UNMASKED_VENDOR_WEBGL = "Google Inc. (Apple)"`，`UNMASKED_RENDERER_WEBGL = "ANGLE (Apple, ANGLE Metal Renderer: Apple M4 Max, Unspecified Version)"`；重启前后逐字一致；`webgpu.supported = false`。
    - `macos` × `seed=444444`：`UNMASKED_VENDOR_WEBGL = "Google Inc. (Apple)"`，`UNMASKED_RENDERER_WEBGL = "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)"`；`webgpu.supported = false`。
    - 实测判定：引擎在 Windows 与 macOS 两平台上均按 `platform + seed` 自动派生出平台自洽的 WebGL 硬件身份，同 seed 跨重启与跨实例完全一致，原 s026 自动派生矩阵成立、无需推翻修订。

## 是否采纳

- 决定：是
- 理由：SDK 源码证据足以否定手选契约（flag 透传无校验），平台硬件事实足以否定 macos×NVIDIA；自动派生是引擎的设计路径，seed 输入稳定。
- 后续 task：t075
- 无需后续理由：不适用

## 关联 findings

- 已抽取：`docs/findings/d051_gpu_identity_engine_derived_no_sdk_control.md`（GPU 身份由引擎按 seed+平台派生、SDK 无 GPU 选择面）；契约决策见 ADR 040（`docs/blueprint/decisions/20261118_profile_identity_readiness.md`，取消 GPU 手选契约）。
