# Stream Runtime 验证

本指南用于隔离组件验证。当前基准为 M1 Max 10核、64 GiB Mac，OrbStack arm64 配额10 CPU、约15.66 GiB，同机官方 Google Chrome Stable。正式 Docker 编排由后续部署任务交付。

## 构建与准备

- Browser 镜像按 browser_runtime_validation.md 构建，预先准备 Linux 引擎缓存；不得将 macOS 二进制挂入 Linux。
- Stream 构建上下文只包含 Dockerfile、entrypoint、cbrowser/__init__.py、cbrowser/secret_files.py 和 stream_agent 包，不包含 .env、用户数据、测试或缓存；以 Dockerfile 的 COPY 列表为准。使用 config/docker/stream_runtime/Dockerfile 构建后，取 docker image inspect 返回的 sha256 ID。
- Python 测试环境需要 pytest、pytest-asyncio、pydantic、aiohttp、Playwright；Playwright 指定 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome，不下载替代 Chromium。

在允许写域内预先创建独立 TMPDIR；设置 CBROWSER_RUNTIME_TEST_IMAGE、CBROWSER_STREAM_TEST_IMAGE 为实际 sha256 ID，CBROWSER_RUNTIME_ENGINE_CACHE 为已初始化缓存目录。测试命令见 docs/blueprint/testing.md。所有 pytest --basetemp 和 cache_dir 必须指向本次测试专属目录。

## 实际观察与判据

完整 E2E 启动全新 Browser、Stream 与独立 bridge，仅发布 localhost 测试端口；媒体同机 `127.0.0.1` 直连，无 coturn。夹具不读已有 Profile，不接管现有 cbrowser 容器。测试资源按唯一名称在 finally 清理，不使用 prune。

验证两页真实1920×1080视频、音频字节与能量增长；复制标签继承旧 sessionStorage 后独立重签，新页解码时原页保持原 PC；刷新、关闭与静音按页隔离。共享策略（静止8/运动30）通过认证 Agent 连接发送并在本指南的组件级用例中检查；Supervisor 配额（15/恢复）与客户端越权拒绝不在本指南的证据范围内，由配额链 E2E（`tests/e2e/test_supervisor_quota_chain_e2e.py`）经生产控制客户端在真实 Gateway 拓扑中以 Viewer 解码帧数验证。页面隐藏暂停、全部后台停捕获与恢复关键帧只走 Selkies 官方 STOP_VIDEO/START_VIDEO（计划 9.3），由 t006 Gateway E2E 以真实 Chrome 页面可见性验证。

测试核对两页 selected remote candidate 为 `127.0.0.1` host/udp，视频 1920×1080 与音频持续增长；覆盖复制标签、刷新、关闭首 tab、可见性暂停/恢复与 Viewer 断线 resume。不得以 Mock Peer 或合成音频替代真实 Chrome。

保存每次 pytest 输出、media_proof.json、active_media_phase.json 与 duplicate_tab_media_proof.json，并记录源 SHA、镜像 ID、独立目录和实际结果。不要复制凭证文件或用户数据到评审材料。

当前组合输入用例通过外部 Chrome CDP 触发可信 composition，沿官方 co,end 到真实 X11，另以原生剪贴板哨兵确认未借剪贴板提交。此证据不等于桌面中文候选窗口人工验收，也不等于1000次压力测试。P95、首帧、1/3/10流、8小时与1000次输入/剪贴板留待后续实测；公网和原生 x86 按用户明确豁免单独记录。
