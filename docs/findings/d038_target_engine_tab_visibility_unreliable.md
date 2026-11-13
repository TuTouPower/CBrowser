# d038 当前目标引擎多标签可见性不能唯一识别活动页

- 来源：t057_preview_pipeline_integrity 的 UNVERIFIED-SPIKE 实测，base main@12380b2。
- 结论：Chromium 146.0.7680.177（缓存构建146.0.7680.177.3）在本机Docker arm64 / Xvfb非headless模式下，同一浏览器窗口的三个测试标签在轮流bring_to_front后仍全部报告document.visibilityState=visible；主世界与CDP隔离世界一致。普通Playwright与生产SDK launch_persistent_context_async两条路径均如此，不能从该信号选择唯一活动页。
- 证据：本task从base构建Browser镜像 `sha256:b5433dea6b04f8e4fec9cd54c2ba1a087c0dc3a363c5cbcb02599e41a51e80de`；`.scratch/t057/visibility_probe.py` 与 `visibility_result.json` / `visibility_probe.log` / `visibility_image.txt`。两路径各3次前台切换，每次采样3个不同marker/target；记录的window_id在各路径内相同，排除把不同窗口当作不同标签。探针容器专属标签com.cbrowser.task=t057，--rm结束已核对无残留；未打开宿主窗口、未访问真实用户页面。
- 限制：这是当前Linux arm64目标引擎与Xvfb的实际证据，不代表原生Mac窗口或其它Chromium版本；SDK路径使用临时空白Profile、geoip=false，未冒充完整生产拓扑E2E。结论与d035既有结果一致。
- 影响：A36若严格限定按页面可见性选择活动页，只能在歧义时跳过，无法据此证明AC-006的多标签正向采集。可靠活动页事实来源或验收调整须先由用户裁定，不用getTargets顺序猜活动页。
- 现状：有效。

## 后续采纳

2026-11-12用户在t057明确选择整张浏览器画面，包含标签栏/地址栏；不再依赖可见性选页。真实Docker内Pillow13/XCB探针读取1280×800独立Xvfb，两个标签切换0→1→0，480×300 JPEG同时保留前台页面与浏览器界面。证据位于t057 worktree .scratch/t057/display_probe.py及display_probe.log；仅证明显示采集契约，未冒充完整E2E。

## 独立Agent的X11认证

完整拓扑首帧超时后，真实Xvfb探针验证：移除XAUTHORITY时Pillow/XCB报OSError，恢复Runner cookie文件后成功读取1280×1024显示。独立Agent不继承Runner进程环境，须在启动截图线程前加载该Profile的Xauthority；不通过放开X服务器访问控制绕过认证。探针容器须带--init，避免xvfb-run作为PID1时的信号握手问题。证据：.scratch/t057/xauthority_probe.log。
