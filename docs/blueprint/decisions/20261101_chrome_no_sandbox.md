# 011 Chrome 在容器内以 `--no-sandbox` 运行并依赖容器边界（2026-11-01T10:13:32+08:00）

- 背景：CloakBrowser/Chrome 自带沙箱依赖 user namespace 或 setuid helper；当前 Browser Runtime 以 UID 1000 非 root、只读根文件系统、`cap-drop ALL` 与 `no-new-privileges` 运行，不启用浏览器沙箱，以避免为此放宽容器权限。Runtime Agent 固定注入 `--no-sandbox`，用户 `launch_args` 中的同名标志被安全白名单拒绝。
- 选项：
    1. 放宽容器权限以启用 Chrome 沙箱（privileged、额外 capabilities 或可写/特权 helper）。
    2. 继续使用 `--no-sandbox`，把隔离责任交给容器边界。
- 结论：采用选项 2。容器边界补偿：非 root UID 1000、只读根文件系统、`cap-drop ALL`、`no-new-privileges`、禁止挂载 Docker Socket、每 Profile 独立容器/网络/卷，且仅 Supervisor 可创建容器。残余风险：Chrome renderer 逃逸不再由浏览器沙箱拦截，可影响同容器内的 Xvfb、PulseAudio、Browser Agent 及本 Profile 挂载数据；跨 Profile 仍由容器、网络与卷边界阻断。`--no-sandbox` 只允许由 Runtime Agent 在受管容器内注入，严禁在宿主机或容器外运行 Chrome 时使用。
- 替代：无
