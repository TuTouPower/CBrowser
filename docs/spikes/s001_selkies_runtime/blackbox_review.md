# 独立黑盒验证报告：CBrowser v2 Runtime Spike 运行环境原型

- **测试执行时间**：2026-10-27T01:57:21+08:00
- **工作目录**：`<repo>/.scratch/v2_orchestration/review/.scratch/runtime_reproduce`
- **执行命令**：`bash run_spike.sh`
- **退出码**：`0` (PASS)

______________________________________________________________________

## 1. 验证项核对矩阵

|验证项|预期条件|黑盒测试实测结果|结论|
|---|---|---|---|
|**01 分辨率与 DPR**|Xvfb 1920x1080 24bpp，DPR=1|`xdpyinfo`: 1920x1080 pixels; DOM Metrics: `innerWidth=1920, innerHeight=907, outerWidth=1920, outerHeight=1032, devicePixelRatio=1`|**PASS**|
|**05 真实浏览器 UI**|存在顶栏/地址栏垂直空间占用 (50~180px)|`outerHeight - innerHeight = 125px`，Window 尺寸 `1920x1080+0+0` 严格位于屏幕内|**PASS**|
|**03 MIT-SHM 正例**|`--ipc container:browser` 下零拷贝正常获取|C 原生 `test_mitshm` 成功读取像素 `(fd, e3, d3)`；pixelflux 成功捕获 8 帧 XShm 图像 (首帧 67583 字节)|**PASS**|
|**03 MIT-SHM 负例**|跨 IPC 隔离环境下明确拒绝且报错|C 原生报错 `CONFIRMED_SHM_DENIED: XShmGetImage failed (status=0, x_err=0)`；pixelflux 捕获异常 `X11 error X11Error { error_kind: Access, error_code: 10, request_name: Some("Attach") }`|**PASS**|
|**04 跨容器 PCM 采样**|PulseAudio 采样非零真实音频|`gst-launch-1.0` 录制 `cbrowser_sink.monitor` 得到 88200 字节 PCM，非零字节 83782 (95.0%)|**PASS**|
|**02 端口绑定证据**|127.0.0.1 绑定与 UDP 监听证据|宿主只映射 `127.0.0.1:18080` (HTTP 200) 与 `127.0.0.1:30005:30005/udp`；`/proc/net/udp` 确认端口 `7535` (30005) 处于监听状态|**PASS**|
|**12 WebRTC 音视频传输**|禁止将 HTTP200/截图/PCM 判定为音视频通过|**NOT_RUN / 未测试**：HTTP 200、pixelflux 截图与 PCM 仅作为组件运行证据，不代表完整 WebRTC 音视频管线闭环|**INCOMPLETE (符合要求)**|

______________________________________________________________________

## 2. 资源隔离与环境清理核对

1. **资源作用域约束**：
    - 脚本全程仅操作 `cbrowser-spike-runtime` 前缀资源。
    - `cbrowser-spike-media-browser`、`cbrowser-spike-media-stream` 及现有 `cbrowser`、`kkmail` 等生产容器未受任何影响，状态保持原状。
2. **清理状态核对**：
    - 退出陷阱清理后：`cbrowser-spike-runtime-browser` 与 `cbrowser-spike-runtime-stream` 均已销毁（`docker ps -a` 结果为空）。
    - 临时卷 `cbrowser-spike-runtime-x11-vol`、`cbrowser-spike-runtime-pulse-vol` 及网络 `cbrowser-spike-runtime-net` 已完全删除。
    - 镜像 `cbrowser-spike-runtime-browser:test` 与 `cbrowser-spike-runtime-stream:test` 保持复用未清除。

______________________________________________________________________

## 3. 结论

黑盒测试完全通过，各项参数、IPC 负例拦截与清理行为符合规范，无需修复代码。
