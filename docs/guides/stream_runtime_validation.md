# Stream Runtime 验证

本指南用于隔离组件验证。当前基准为 M1 Max 10核、64 GiB Mac，OrbStack arm64 配额10 CPU、约15.66 GiB，同机官方 Google Chrome Stable。正式 Docker 编排由后续部署任务交付。

## 构建与准备

- Browser 镜像按 browser_runtime_validation.md 构建，预先准备 Linux 引擎缓存；不得将 macOS 二进制挂入 Linux。
- Stream 构建上下文只包含 Dockerfile、entrypoint、cbrowser/__init__.py 和 stream_agent 包，不包含 .env、用户数据、测试或缓存。使用 config/docker/stream_runtime/Dockerfile 构建后，取 docker image inspect 返回的 sha256 ID。
- coturn 使用计划固定的 coturn/coturn:4.6-alpine，拉取后记录实际不可变 ID、架构与版本。测试不使用 latest。
- Python 测试环境需要 pytest、pytest-asyncio、pydantic、aiohttp、Playwright；Playwright 指定 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome，不下载替代 Chromium。

在允许写域内预先创建独立 TMPDIR；设置 CBROWSER_RUNTIME_TEST_IMAGE、CBROWSER_STREAM_TEST_IMAGE、CBROWSER_TURN_TEST_IMAGE 为实际 sha256 ID，CBROWSER_RUNTIME_ENGINE_CACHE 为已初始化缓存目录。测试命令见 docs/blueprint/testing.md。所有 pytest --basetemp 和 cache_dir 必须指向本次测试专属目录。

## 实际观察与判据

完整 E2E 启动全新 Browser、Stream、coturn 与独立 bridge，仅发布 localhost 测试端口。夹具不读已有 Profile，不接管现有 cbrowser 容器。测试资源按唯一名称在 finally 清理，不使用 prune。

验证两页真实1920×1080视频、音频字节与能量增长；复制标签继承旧 sessionStorage 后独立重签，新页解码时原页保持原 PC；刷新、关闭与静音按页隔离。策略通过认证 Agent 连接发送，检查静止8/运动30、配额15/恢复、隐藏聚合、关键帧及客户端越权拒绝。

TURN 测试使用不同客户端/服务端 URL 和 HMAC 短期凭证；coturn relay-ip 必须是实际容器地址，external-ip 明确 localhost/容器地址映射。loopback 放行与 no-cli 仅为隔离测试配置，不能直接复制到公网部署。连续新代接管与旧代关闭并拒绝发送后，才核对新 ufrag 的 selected pair、双 relay 类型、候选字节及重新采样的音视频增量。测试保留 PC/DTLS/Track 引用检查，旧代继续传流不能使测试假绿。

## 负例和证据

设置测试专用 CBROWSER_STREAM_TURN_REJECT_SIDE=server 或 client，分别注入单侧错误凭证。预期 pytest 非零，失败点为无 fresh offer 或新代未提交，且 coturn 日志出现真实认证拒绝；如果失败发生在镜像、CLI 配置或 Chrome 启动阶段，只算夹具失败。负例结束后取消变量再跑正常门禁。

保存每次 pytest 输出、media_proof.json、duplicate_tab_media_proof.json、relay_generations.json、coturn.log 和 relay_stream.log，并记录源 SHA、镜像 ID、独立目录和实际结果。不要复制凭证文件或用户数据到评审材料。

当前组合输入用例通过外部 Chrome CDP 触发可信 composition，沿官方 co,end 到真实 X11，另以原生剪贴板哨兵确认未借剪贴板提交。此证据不等于桌面中文候选窗口人工验收，也不等于1000次压力测试。P95、首帧、1/3/10流、8小时与1000次输入/剪贴板留待后续实测；公网和原生 x86 按用户明确豁免单独记录。
