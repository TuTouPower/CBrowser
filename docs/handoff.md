# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-05T08:37:52+08:00 本地 t032 真实验收收口中；目标引擎探针仍缺环境

### 主仓

- branch `main`，head_commit `c63856a`（本 handoff 提交紧随其后）。
- `origin/main` 当前为 `4b2be2f`；本地领先 4 个提交，未 push：
    `c7a72cd`、`488734c`、`d58d39e`、`c63856a`。
- 工作区无未提交改动。
- 按用户指示，t032 直接在主分支执行，没有创建 task worktree；`docs/tasks/t032_local_target_environment_acceptance/` 仍是 backlog、AC 未勾选，与本轮实际执行状态不一致，收口时必须补文档。
- 之前创建的 5 个 t032 worktree 与分支已删除；被取消的 frontend/supervisor 草稿保存在
    `.scratch/t032/wip/frontend_wip.patch`、`.scratch/t032/wip/supervisor_wip.patch`（gitignored，仅参考，未采用）。

### 本轮已完成并实跑通过

- p035、p036：已实现并归档。
    - p035：抽出 `_watch_network_events`，补停机竞态测试。
    - p036：锁存释放按 `(profile, instance)` 前缀清除终态去重 key，补版本不对称回归测试。
- AC-001/AC-002/AC-010：
    - 隔离实例冷构建、镜像 import、Supervisor/Stream/API 产物检查；
    - 重复发布容器不重建、镜像 ID 稳定；
    - 回滚成功、迁移版本过高时拒绝回滚且指针不动；
    - 双实例并存、同 prefix 第三实例启动前拒绝。
- Gateway lane（已合入 `efad96f`）：
    - registration budget、gateway AC-003 media、AC-007 visibility、stream selkies tokens、quota chain 全部通过。
    - 修复：UDP mux 范围只接通 PortAllocator、注册失败预算误计中止握手、nft/iptables-save 规则规范化导致策略漂移误判。
- Font lane（`9c80572`）：
    - `test_browser_font_bundles_e2e.py` 5 passed，`test_font_bundles.py` 22 passed。
    - 根因：Chromium 146 把 `DOM.getPlatformFontsForNode` 迁到 `CSS` 域；generic fallback 断言过期；并发 Profile 共享 PulseAudio 目录。
- Browser runtime lane（`1da2be3`）：
    - 下载捕获/恢复、Agent 重启对账 2 passed。
    - 修正 t030 隧道拒绝语义与可信实例绑定。
- Supervisor 定向 lane（最终代码 `c63856a`，t032fix 镜像）：
    - `test_runtime_coordinator_e2e.py` 1 passed（35s，不再卡死）。
    - `test_supervisor_container_graph_e2e.py` 1 passed（43s）。
    - `test_supervisor_offline_recovery_e2e.py` 1 passed（46s）。
    - `test_supervisor_reconciliation_e2e.py` 2 passed（2s）。
    - `test_supervisor_startup_recovery_e2e.py` 2 passed（4s）。
- Frontend 定向 lane（最终代码 `c63856a`，t032fix 镜像）：
    - `test_t019_switch_and_refresh_first_frame_within_2s_host_only` 1 passed（switch 1.341s、refresh 0.333s）。
    - `test_ac004_ac005_input_mute_size_no_activity_frames` 1 passed。
    - `test_ac007_lifecycle_resume_and_isolated_media_diagnostics` 1 passed。
    - `test_frontend_session_freeze_resume_and_diagnostics` 1 passed。
- 最终门禁中途中断时发现并已修复的 4 个 unit 失败：
    - 清理重试导致 mock 预期 remove 次数不符；
    - `udp_mux.py` 未加入 gateway/stream/supervisor 的 Dockerfile.dockerignore 白名单。
    - 修复后相关 32 个 unit passed；完整 unit 全量复跑被用户中断。

### 本轮修复的产品缺陷

- Supervisor 镜像缺 `cbrowser.services.tunnel_registry`。
- 构建上下文混入 `__pycache__`/`.pyc`，镜像不可复现。
- BuildKit attestation 导致重复发布镜像 ID 变化、容器重建。
- 长数据根下 AF_UNIX path 超限，影响健康检查与 CDP。
- 嵌套 `run_gates` 继承外层证据目录，污染证据。
- API CDP 代理丢弃 Supervisor 的 4403 关闭码。
- Artifact 转发 host 路径，跨挂载点被 API ingest 拒绝。
- control service 写路径先读后写导致并发 bind `database is locked`；改为 `BEGIN IMMEDIATE`。
- 媒体网段分配竞争；policy helper 自动命名导致孤儿回收误判。
- PulseAudio 默认空闲退出导致 `audio_ready=False`。
- native exit 事件投递成功后才登记，启动恢复优先级错误。
- 前端未清除 Selkies 默认外部 STUN，产生 `prflx` 并拖慢会话。

### 未完成 / 阻塞

- **AC-011 目标引擎矩阵：待容器化执行。**
    - 2026-11-05 用户决定改用实际交付引擎 `146.0.7680.177.3`，不再要求云端基线 `.5`。
    - 执行方式改为 Linux arm64 容器：挂载仓库与 `.scratch/t032/data/engine-cache`，容器内安装 pytest/xte，Xvfb 有头运行探针；macOS 宿主不能直接执行 Linux 引擎。
    - 探针代码尚未改成 `.3`/容器入口；这是下一步实现，不是已完成。
- **AC-012 指纹对照**：范围收窄为 `.3` 引擎 L0–L6 自动自对照；外站人工判读/因果复核移除，无法自动采集时记 `INCONCLUSIVE`，不与 t029 `.5` 强制对比。
- **AC-013 输入比较**：保留自动 CDP/XTEST 坐标、DPR、装饰、滚动、iframe、复杂交互、焦点争用；原生权限/设备、真人 CAPTCHA/2FA、IME 人工交接移出本轮，报告记 `OUT_OF_SCOPE_BY_USER`。程序化 control handoff 已通过。
- **AC-014 最终全量门禁**：未完成。最后一次 `evidence-final` 只完成 contract（169 passed）、integration（157 passed）、unit（993 tests，4 failed，现已修复）；e2e 未跑。
- **AC-015 最终报告**：未写。
- t032 `task.md` AC 勾选、`note.md`、`specs_index`、`docs/blueprint/testing.md`/`automation.md`/`decisions.md` 均未收口。

### 当前验证环境

- venv：`.scratch/venv-tests/bin/python`
- 门禁 venv/证据：`CBROWSER_GATE_SCRATCH=.scratch/t032/gate-final`，证据目录 `.scratch/t032/evidence-final`（中途中断，不能作为最终 PASS 证据）。
- 当前 t032fix 镜像 ID（`.scratch/t032/fix-env.sh`）：
    - browser `sha256:e594fe5c8c08105b26298e6f5925b12962c72759d6739baff3099be01921d309`
    - stream `sha256:48365822d7eb9d9bc00e3111fe80de178dfc1766933971403d242d6a0323c7a3`
    - supervisor `sha256:660f4c5f6beff10509409480ee630d452542ead02270fb22db5dba340bb516ac`
    - gateway `sha256:9ad524e0d86ec5efe97e3ee0077364280ab3ae389b42b7f92ed6ef40f37a461f`
    - api `sha256:057218ae8ff5d3fbb023cf23d343504cb6fd60e9c6a8d5ca100d084ec10a8e1b`
    - caddy `sha256:af32e97399febea808609119bb21544d0265c58a02836576e32a2d082c262c17`
- 引擎/GeoIP 缓存：`.scratch/t032/data/engine-cache`、`.../geoip`。
- 并行 lane 环境：`CBROWSER_E2E_UDP_BASE`、`CBROWSER_E2E_HTTP_BASE`、`CBROWSER_E2E_MEDIA_POOL`；单 lane 用 30000/35000/10.251.0.0/16。
- Docker：生产栈 `cbrowser-*` 未动；隔离验收栈 `cbrowser-t032`/`cbrowser-t032b` 已销毁；测试容器、网络、卷、旧测试镜像已清理；仅保留 t032fix 镜像与 BuildKit 缓存（约 5GB）。

### 已知风险与注意事项

- **不要再“修一个就全量跑”**。定向用例单次约 20–50 秒；全量 e2e 一轮约 33 分钟，整套门禁约 37 分钟。
- 必须保留 t032fix 镜像到最终门禁结束；测试文件改动不需要重建镜像，改哪个服务才重建哪个。
- 新 e2e 必须有硬超时；`test_runtime_coordinator_e2e.py` 已加 uvicorn 关停上限与 `server_task` 超时。
- 拓扑清理必须先停 supervisor/api/gateway，再删 profile 容器；否则 Supervisor 会在清理过程中重建 Stream。
- t019 的 getStats 会出现 Docker 端口发布 NAT 造成的 local `prflx`；当前断言以 SDP 信令候选为 host-only 契约，getStats 远端仍断言 host-only。最终报告需写明这一取舍。
- t019 切换耗时出现过 1.341s（通过）和 3.4s（失败）；可能与 iframe 切换时 stats 求值/调度有关，最终门禁复跑需关注，不能只凭一次通过下结论。
- frontend freeze/resume 必须让远端页面持续绘制（damage-gated capture 对静态页不出帧），测试已注入 canvas 动画。

### 下一步（顺序固定）

1. 跑一次完整 `tests/unit`，确认 `c63856a` 上无剩余 unit 失败。
2. 用 t032fix 镜像跑一次完整 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`，证据目录重新建；不再逐项全量重跑。
3. 实现探针 `.3` 版本选择与 Linux 容器入口；在容器内跑 AC-011 全链/Dialog 矩阵。
4. 在容器内跑 AC-012 L0–L6 自动自对照；AC-013 只跑自动 CDP/XTEST 比较；人工项记 `OUT_OF_SCOPE_BY_USER`。
5. 写 AC-015 报告，勾选 t032 `task.md`，更新 `note.md`、`specs_index`、`docs/blueprint/testing.md`/`automation.md`/`decisions.md`。
6. 最终清理 t032fix 镜像、BuildKit 缓存、临时测试资源；确认 Docker 只剩生产与用户服务。
