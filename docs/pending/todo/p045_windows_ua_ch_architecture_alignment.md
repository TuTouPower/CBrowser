# p045 windows Profile 的 UA-CH architecture 对齐（待引擎层手段）

- 来源：t041 / `docs/spikes/s014_fingerprint_platform_fonts/` 正式 spike 遗留；结论见 `docs/findings/d032_ua_ch_architecture_no_engine_switch.md`，用户 2026-11-06 裁决。
- 内容：Linux arm64 宿主上 windows Profile 的 UA 为 `Win64; x64`，但 UA-CH `getHighEntropyValues().architecture` 与 `Sec-CH-UA-Arch` 请求头为 `arm`（真实 Windows on ARM 组合存在但人群占比低，抬高指纹辨识度）。目标：windows 统一 `architecture=x86` / `bitness=64`，macos 保持 `arm`（与 Apple Silicon 一致），且主文档、iframe、Worker、ServiceWorker、请求头全上下文一致。**现在未做**的原因：cloakbrowser 0.6.4 / Chromium 146 无引擎层 flag；CDP `Emulation.setUserAgentOverride` 页面级覆盖实测能覆盖主文档/iframe/Worker/请求头，但 ServiceWorker 独立 target 仍报 `arm`，属半套覆盖，按裁决不做。
- 处理：未开
- 前置条件：cloakbrowser 暴露 arch/bitness 引擎层开关，或 Chromium 提供可作用于所有 target（含 ServiceWorker）的 UA-CH 覆盖机制；届时用 s014 三个探针脚本重测全上下文一致性，再纳入 t041 后续实现并补 AC-004 实现细节的测试断言（AC 文本不改）。
