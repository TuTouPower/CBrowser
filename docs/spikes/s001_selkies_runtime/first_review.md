# CBrowser v2 Runtime Spike (项1-5、12) 独立审查报告

## 1. 核心判定

报告声明的 "allPASS" 不成立。存在错误吞噬、无接收观察、断言假阳性及规格缩水；不能以截图或 HTTP 200 证明 WebRTC 媒体链路通过。

______________________________________________________________________

## 2. 逐项真实性缺陷与代码定位

### 2.1 音频验证假阳性：命令吞错且无音频样本

- **定位**：`run_spike.sh` L89-95；`report.md` L12。
- **事实**：
    - L94 使用 `timeout --preserve-status 2 gst-launch-1.0 pulsesrc ... >/dev/null 2>&1 || true`，`|| true` 吞噬所有退出码，GStreamer 崩溃或管道失败仍判定成功。
    - L89 仅用 `pactl info` 检查默认 Sink 名称，无任何音频产生（如 `audiotestsrc`）、无有效采样写入与消费，无法证实音频真实流动。

### 2.2 WebRTC UDP Mux 假阳性：单向 sendto 无接收端观测

- **定位**：`run_spike.sh` L120-123；`report.md` L14。
- **事实**：
    - L122 仅执行 Python UDP `sendto(b'ping', ...)`。UDP 为无连接协议，内核发包缓冲区成功即返回，完全不代表 Selkies 端接收、解析或处理该包。
    - L120 仅检查 HTTP 18080 返回 200 OK，仅证明信令 Web 服务存活，严禁作为 WebRTC 媒体通道及 UDP Mux 连通的证明。

### 2.3 MIT-SHM C 验证与负例假阳性

- **定位**：`test_mitshm.c` L78-89；`run_spike.sh` L74-83；`report.md` L38-39。
- **事实**：
    - `test_mitshm.c` L87 仅打印 `Sample pixel`，未对像素非空或内容有效性做断言；若 Xvfb 填充全零或读取黑屏，仍直接 exit 0。
    - `run_spike.sh` L74-83 负例测试直接用 `if docker run ... >/dev/null 2>&1`。Docker 启动失败、二进制缺失、DISPLAY 连接超时等任何容器报错均导致非零退出，全被误判为“MIT-SHM 隔离生效（BadAccess）”，掩盖真实隔离成因。

### 2.4 分辨率规格偏离：1280x720 替代规划 1920x1080 / DPR=1

- **定位**：`report.md` L13；`run_spike.sh` L59。
- **事实**：规划 18.5 要求 1920x1080 且 DPR=1。Spike 采用 1280x720，每帧像素内存为 3.68MB（规划应为 8.29MB），未覆盖目标分辨率下的 SHM 吞吐瓶颈与字体渲染 DPR 适配。

### 2.5 容器安全边界未落地：Root / 缺 Xauth / 共享网络

- **定位**：`run_spike.sh` L45-53, L98-106。
- **事实**：
    - 双容器均以默认 `root` 运行，未落地非 root 隔离。
    - X11 Socket 共享卷未配置 `Xauthority` / `MIT-MAGIC-COOKIE-1`，任何能挂载卷的容器均可任意窃听或操控 X11 会话。
    - 两容器置于同一 Bridge 网络，未落实仅暴露 UDS 的网络隔离。

### 2.6 可重跑性与资源清理不彻底

- **定位**：`run_spike.sh` L21-28, L37。
- **事实**：
    - L37 编译输出宿主机二进制 `/src/test_mitshm`，`cleanup()` 未清理该产物。
    - `cleanup()` 未清理测试镜像 `${PREFIX}-browser:test` 与 `${PREFIX}-stream:test`。
    - L33-34 若镜像存在则跳过构建，修改 Dockerfile 后重跑无法自动生效。

______________________________________________________________________

## 3. 最小修复建议

1. **音频修复**（`run_spike.sh`）：
    - 移除 L94 的 `|| true`，Browser 容器运行 `gst-launch-1.0 audiotestsrc wave=sine num-buffers=100 ! pulsesink` 灌入音频，Stream 容器运行 `gst-launch-1.0 pulsesrc num-buffers=50 ! fakesink`，校验退出码为 0 且捕获非空 buffer。
2. **UDP Mux 修复**（`run_spike.sh`）：
    - 发送 STUN Binding Request 探测包，接收并校验 STUN Binding Response；或检查容器内 Selkies 进程日志/统计指标中 UDP mux 实际收到并解包计数。
3. **MIT-SHM 正负例修复**（`test_mitshm.c` + `run_spike.sh`）：
    - `test_mitshm.c` 增加像素校验（断言非全 0 且匹配测试窗口背景色），捕获 X11 错误。
    - `run_spike.sh` 捕获负例 stderr，精准断言匹配 `BadAccess` 关键字，禁止以泛化非零退出码代表隔离成功。
4. **分辨率对齐**（`run_spike.sh`）：
    - 切换 Xvfb 与 Chromium 为 1920x1080x24，配置 `--force-device-scale-factor=1`，校验 `xwininfo -root` 宽高严格匹配 1920x1080。
5. **安全与清理补全**（`run_spike.sh`）：
    - 生成临时 Xauth cookie 并注入双容器；`cleanup()` 追加 `rm -f ${WORK_DIR}/test_mitshm`。
