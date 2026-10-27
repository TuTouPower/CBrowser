# d005 Selkies 编码帧数不能直接判定画面运动

- 来源：t001 / s002_selkies_protocol；2026-10-27T02:18:00+08:00 主控逐行核对固定提交
- 结论：默认 Turbo 模式编码每帧，StreamWatch.encoded_fps 统计编码输出而非像素变化；不能用 encoded_fps>1 直接证明播放视频或显著画面变化。
- 证据：固定提交 `6ee68a7a815956e6745e916741f13335e0b3ff53` 的 `src/selkies/settings.py:717` 中 video_streaming_mode 默认 True；`src/selkies/webrtc_media_pipeline.py:165` 说明 Turbo 为每帧编码而非 damage-gated；`src/selkies/stream_stats.py:211` 的 rates 通过累计 frames 差值计算 encoded_fps，且调用会重置采样窗口。主控确认这些源码；尚未把此统计作为运动检测验收通过。
- 影响：t004 和 t001 媒体策略必须用经实际静止/动画对照验证的信号，避免恒定30 FPS掩盖无自适应策略。Agent 若采样 StreamWatch.rates 会干扰原统计窗口，应使用独立采样状态或明确共享采样。真实内部控制入口为异步 MediaPipelinePixel.set_framerate/pause_screen_capture/resume_screen_capture；watch 位于 service.display_pipelines[primary].stream_watch，不存在已验证的 service.stream_watches 字段。
- 现状：有效
