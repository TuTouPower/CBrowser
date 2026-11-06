# d032 Chromium 146 无引擎层开关修正 UA-CH architecture，CDP 覆盖会漏 ServiceWorker

- 来源：`docs/spikes/s014_fingerprint_platform_fonts/` 正式 spike（t041），2026-11-06 在 Linux arm64 探针容器 `cbrowser-t032-probe:final` 内以真实引擎 `chromium-146.0.7680.177.3/chrome` 实测；脚本 `code/platform_probe.py`、`code/ua_ch_flag_probe.py`、`code/ua_ch_cdp_probe.py`。
- 结论：**cloakbrowser 0.6.4 / Chromium 146 没有引擎层命令行开关设定 UA-CH `architecture` / `bitness`；`Emulation.setUserAgentOverride` 的 CDP 页面级覆盖无法覆盖 ServiceWorker 上下文，属半套覆盖，t041 不做该修正。**
- 证据：
    - 二进制 switch 清单只有 `fingerprint-platform` / `fingerprint-platform-version` / `fingerprint-brand` / `fingerprint-gpu-*` / `fingerprint-fonts-dir` 等，**无 arch/bitness 对应项**；符号表有 `blink::UpdateUserAgentMetadataFingerprint`，但只 patch platform 相关字段。
    - 实测候选 flag `--fingerprint-arch=x86`、`--fingerprint-architecture=x86`、`--ch-ua-arch=x86`、`--force-ua-ch-arch=x86`、`--fingerprint-bitness=64` 全部无效：`getHighEntropyValues()` 恒为 `architecture=arm, bitness=64`，`Sec-CH-UA-Arch: "arm"` 请求头亦不变。
    - `--fingerprint-platform=windows` 下 `navigator.platform=Win32`、UA `Win64; x64`、CH `platform=Windows` / `platformVersion=19.0.0` 均一致；但 CH `architecture=arm`（Linux arm64 宿主真实值），与 UA 的 x64 并存。用户裁决：真实 Windows on ARM 有该组合，但人群占比低、抬高辨识度，属 t041 范围内应处理的问题。
    - CDP `Emulation.setUserAgentOverride({userAgentMetadata:{architecture:"x86",bitness:"64",...}})` 实测：主文档、同源 iframe、dedicated Worker 的 `getHighEntropyValues()` 与所有 `Sec-CH-UA-Arch` 请求头（`/`、`/iframe`、`/probe`、`/favicon.ico`）均变为 `x86`，**但 ServiceWorker 上下文的 `self.navigator.userAgentData` 仍为 `arm`**（SW 是独立 target，不继承页面 override）。即「主文档 x86 / SW arm」跨上下文矛盾，比原问题更糟。
    - 引擎层无 flag + 页面级覆盖漏 SW ⇒ 按用户裁决第 3 点，不做半套覆盖。
- 影响：t041 AC-004 文本不改、不加入 architecture 断言；windows Profile 保留 UA `Win64; x64` + CH `arm` 现状并在 progress 如实登记。追踪见 `docs/pending/todo/p045_windows_ua_ch_architecture_alignment.md`。实现 E2E 若读 UA CH 必须用 `http://127.0.0.1` / HTTPS 安全上下文（`about:blank` 下 `navigator.userAgentData` 为 null）。
- 现状：有效
- 复查条件：cloakbrowser 升级暴露 arch/bitness 引擎层开关，或 Chromium 提供可作用于所有 target（含 ServiceWorker）的 UA-CH 覆盖时，重跑 s014 三个脚本再评估。
