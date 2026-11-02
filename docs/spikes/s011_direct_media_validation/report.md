# Spike report

## 问题

单机单人部署包络下，同机 Google Chrome 能否只靠 local 直连（Stream 容器 UDP mux 发布到 127.0.0.1，无 coturn、无 TURN 凭证）覆盖全部会话场景？若成立，coturn、TURN 凭证轮换、ICE 代次接管与 Selkies 私有 ABI 补丁即可删除。

## 成功判据

- 不运行 coturn，Gateway 不下发 RTC 配置；真实 Chrome 的 selected remote candidate 为 127.0.0.1 host 候选。
- 同一 Profile 两页同时解码 1920×1080 视频与非静音音频；复制标签、刷新、关闭克隆页与关闭首 tab 不影响其余页。
- 页面隐藏只暂停该页视频，可见页继续；恢复可见后继续出帧。
- Viewer 信令 WebSocket 断开后官方客户端以原 tab 身份重连并继续解码。
- 键鼠输入到达同一 Browser；中文 composition 经 Native 通道提交。
- 真实 Browser/Stream 容器、真实 Chrome、OrbStack；公网与原生 Linux x86_64 不在范围（用户已豁免）。

## 尝试

- 从 t004 直连 E2E 复制探针到 `code/direct_media_probe.py`，删除 TURN relay/代次轮换与资源配额探针，新增可见性暂停/恢复与 Viewer 断线 resume 两个阶段。
- 使用当前源码构建的不可变镜像：Browser `sha256:16ee6831...`、Stream `sha256:afc32c64...`，初始化引擎缓存 `t003_engine_cache`。
- 运行入口见 `code/run.sh`；pytest 以显式 basetemp 保留证据 JSON。

## 证据

- `direct_media_probe.py::test_s011_direct_media_matrix` PASS，80 秒，退出码 0（`.scratch/s011/run3.log`）。
- 两页 selected remote candidate：`address=127.0.0.1, port=30097, protocol=udp, candidateType=host`。
- 视频 1920×1080 帧持续增长；音频 `bytesReceived` 与 `totalAudioEnergy` 持续增长。
- 可见性：隐藏页帧数不变、可见页继续增长，恢复后继续出帧。
- Viewer 断线：tab_id 不变，重连后帧数继续增长，活动 viewer 恢复为 2。
- 复制标签、刷新保身份、关闭克隆页与关闭首 tab 后次页媒体/输入继续；8 组中文 composition 均产生可信 compositionstart 与 `co,end` 提交。
- 证据 JSON：`.scratch/s011/basetemp/test_s011_direct_media_matrix0/run_3af865e5/media_proof.json`、`active_media_phase.json`、`duplicate_tab_media_proof.json`。

## 结论

单机同机 Chrome 经 127.0.0.1 host 候选直连在全部目标场景可用，TURN/coturn 不是单机单人部署的必要条件。限制：仅验证 macOS + OrbStack + headless 官方 Chrome；未验证公网、NAT、原生 Linux x86_64 或多主机。

## 是否采纳

- 决定：是
- 理由：全部成功判据在真实拓扑与真实 Chrome 上闭环，证据可复核。
- 后续 task：t015
- 无需后续理由：不适用

## 关联 findings

- d026
