# p087 DLP 通道化到 per-Profile 策略

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P2-16），借鉴 Kasm DLP
- 内容：把剪贴板上下行 + mimetype 白名单（`chromium/x-web-custom-data` / `text/html` / `image/png`）、上传下载固定目录、音频/麦克风/摄像头、水印、区域遮蔽、键盘限速做成 Group/Profile 级开关，并加「服务崩溃即重启整个容器」fail-secure。现状已有 `clipboard_sync` 开关与会话内 `file_transfers=none`，但缺 per-Profile 通道策略与崩溃 fail-secure。本次为只读调研，未授权改生产代码。
- 处理：未开
- 时间：2026-11-13T19:16:54+08:00
- 关联：p015（archive，input/clipboard E2E）、p067（archive，clipboard_sync 默认值）、p055（archive，privacy allowlist）、p076（viewer 权限位）、p078（跨 Profile 泄漏面）

## 必须一并处理的泄漏面

外部 Viewer（唯一 Google Chrome）是共享面：`SELKIES_ENABLE_CLIPBOARD` + `SELKIES_CLIPBOARD_SEAMLESS`（`container_spec.py:282-284`）使多标签连接不同 Profile 时共享同一 Chrome/OS 剪贴板与下载目录，形成跨 Profile 剪贴板/文件名桥接。DLP 策略须与该泄漏面一起设计，不能只加开关。

## 验收

1. 每个 Profile 的剪贴板上下行、文件传输、音视频设备可独立开关，默认拒绝未声明通道。
2. DLP 服务异常时容器整体重启并回到拒绝态，而非降级为放行。
3. 多标签连接不同 Profile 时剪贴板与下载目录不互通；真链 E2E 覆盖跨 Profile 负向隔离。
