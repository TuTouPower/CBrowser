# p059 Supervisor 沙箱启动失败保留 Docker 原始错误文本

- 现象：Supervisor 启动 Browser/Stream 容器失败时只记录 `error_type=DockerSandboxError`，Docker 原始 `APIError` message（端口占用、网络冲突、镜像参数错误等）被丢弃，调用方只能看到 500。
- 影响：启动失败无法从日志直接定位根因；p056 曾因此长期无法判断是哪类环境冲突。
- 根因：adapter 在 `start_browser_container` / `start_stream_container` 的 `DockerException` 包装中只保留异常类型，未保留脱敏后的 message。
- 测试缺口：无“启动失败异常/日志携带 Docker 原始 message 且不含密钥、代理凭证、token”的断言。
- 线索：`src/backend/cbrowser/supervisor/docker_adapter.py` 的 Browser/Stream 启动 `except DockerException` 包装；p056 历史失败证据。
- 处理：t051；resolution=transferred；reason=已核实范围并转交该 task
