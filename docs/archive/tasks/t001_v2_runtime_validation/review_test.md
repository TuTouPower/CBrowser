# Task review t001（reviewer_focus: 测试）

- task：`t001_v2_runtime_validation`
- spec：`docs/tasks/t001_v2_runtime_validation/task.md`
- diff_anchor：`3c8bdbc55570e85aaeb6365a3d512da9c0ce180c`
- target：`git -C '<repo>_t001' diff 3c8bdbc55570e85aaeb6365a3d512da9c0ce180c`
- round：1
- reviewed_at：2026-10-27T19:28:00+08:00

reviewed_scope: d63c641b0d94c2f9

## Findings

无

## 结论

- 前轮 finding 复核：无（Round 1）
- 改测方向复核：无（diff 中未直接修改既有测试文件；历史 baseline 与契约测试保持原样运行，无迁就实现的改测）
- 本轮新发现：0 条
- 未进表的提示：
  1. 契约区自 diff_anchor 以来对范围与可测试性声明进行了调整（明确公网候选与原生 Linux x86_64 执行由用户指示豁免，标记为 NOT_RUN/USER_WAIVED；测试基准更新为本地 Mac Docker + 本机 Chrome）；该变更已在 `docs/tasks/t001_v2_runtime_validation/scope_adjustment.md` 与 `note.md` 中充分披露。
  2. 6 条 AC 真实核验与分层验证详情披露：
     - AC-001：独立重跑复制版 `s007_profile_isolation` 探针（18.9s exit 0），证实真实非 root/只读/Xauthority/Pulse 隔离卷、MIT-SHM 底层正反例及真实 48000Hz WebAudio PCM 采集通过；
     - AC-002：独立重跑复制版 `s004_media_connections` 探针（exit 0），证实同 Context 双 tab 1080p 解码、UDP 30006 mux、真实 DOM 交错输入（121212）、刷新保持 ID、WebLocks 冲突重映射与关闭首 tab 次 tab 持续视频/音频通过；
     - AC-003：
       - `Core 9 场景`：独立重跑复制版 `s005` 之 `test_e2e_real_pipeline.py`（exit 0，9 项端到端场景全通过），证实 static 8fps、canvas animation 30fps、0.5Hz 慢闪回 8fps、真实 DataChannel 输入提升 30fps、前台保护、全后台暂停捕获与恢复可见先 8fps 后 30fps 重建画面完全通过；
       - `Native 7 场景`：独立重跑复制版 `s005` 之 `native_visibility_e2e.py`（exit 0，7 场景全通过，日志保存在 own scratch `s005_native_run/native_visibility_e2e.log`），证实通过真实 Chrome 子进程（单窗口双 tab）、直接 CDP websockets 控制与 document.visibilitychange 适配层，验证了：前台激活 tab2（doc.hidden 对应 active_peers=1）、前台 30fps 增长/后台 0 帧 delta、切回 tab1 保持全局 30fps、原生窗口最小化双 hidden 触发 capture pause、窗口恢复审计 trace（严格 set_framerate 8.0 先于 resume_screen_capture 后 motion 跃升 30fps）、关闭单个 tab 继续解码、全关 tab 暂停捕获且底层 CloakBrowser 持续存活；
     - AC-004：独立重跑复制版 `s008_turn_generation_media` 分离配置双探针，证实本地 UDP mux 媒体发布、同一 PC 下跨代 TURN 刷新（两轮切换）、relay-to-relay 严格接管、双侧独立 URL/凭证、以及单侧无效凭证两组严格拒绝（Session 1 客户端错/服务端对拒绝切换，Session 2 服务端错/客户端对 HTTP 400 拒绝，退出码 1，生成 fresh 拒绝证据 JSON）全部成立；公网单列 NOT_RUN/USER_WAIVED；
     - AC-005：
       - 跨容器 UDS 下载与恢复：独立重跑复制版 `s003` 宿主与容器隔离验证（`--case override_control` 与无参数默认 recovery 各跑一次，均 exit 0）；
       - 进程编排与退出事件：独立重跑复制版 `s003` 之 `test_orchestration.py`（exit 0，涵盖真实 API 离线、Supervisor 存盘 SIGKILL 崩溃恢复、队列持久化重放去重、避免误重启与新实例防误杀验证）；
     - AC-006：验证执行于 macOS OrbStack arm64 环境，17 项映射表完备，原生 Linux x86_64 单列 NOT_RUN/USER_WAIVED（此项为环境与矩阵文档核实，非重跑）。
  3. 执行过程重试与工具行为披露：
     - 在本轮实测 `s006` Gateway 恢复探针时，首次调用 bash 工具因指定的 `workdir` 路径笔误为不存在的 `.scratch/t006_test` 导致工具报错 `NotFound: FileSystem.access`（此为测试 reviewer 操作环境目录笔误，非产品或探针缺陷）；修正为正确目录 `.scratch/t001_review_test/s006_test` 后立即重跑成功，完整通过 12 项 Gateway 崩溃与无缝恢复验证。
     - 归档探针代码未就地执行或修改，所有探针均在独立 scratch 目录复制运行并在 finally 中严格清理容器、卷与网络；所有重跑证据文件与日志（包括 `s005_native_run/native_visibility_e2e.log`）均保留在 own scratch 目录下备查。
  4. 门禁命令与 baseline 自检确认：
     - `pytest .repo_template/tests -q -m contract`（169 passed）；
     - `src/backend/tests`（384 passed）；
     - `curl -sf http://127.0.0.1:56661/api/health`（status: ok，现有基线服务完全未受破坏）；
     - `repo_sync status`（返回未初始化，exit 0）。
- 总体判断：所有被打勾的 AC 均有充分、权威且可独立复现的验证资产支撑；无危险测试模式，无假绿断言；符合技术验证阶段验收要求。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：`re_verified`（独立运行复制版 `s007` 探针，18.9s exit 0，真实非 root/MIT-SHM/Xauth/Pulse/WebAudio 48000Hz 校验通过）
- AC-002：`re_verified`（独立运行复制版 `s004` 探针，exit 0，真实双 tab 1080p 解码、DOM 121212 交错输入与生命周期验证通过）
- AC-003：`re_verified`（独立运行复制版 `s005` 之 Core 9 场景与 Native 7 场景双探针，全部 exit 0，验证真实 Chrome 前后台/最小化 visibility、前台保护与 8/30 动态帧率转换）
- AC-004：`re_verified`（独立运行复制版 `s008` 探针正常与单侧失效矩阵，正常两轮接管 exit 0，单侧失效严格拒绝 exit 1 产生非假绿 JSON）
- AC-005：`re_verified`（独立运行复制版 `s003` 跨容器 UDS override 与 recovery 探针，及独立进程编排恢复探针，exit 0）
- AC-006：`trust_prior`（文档与环境查验：macOS OrbStack arm64 实际执行环境确认，17 项映射表完备，原生 Linux x86_64 单列 USER_WAIVED）

coverage = 5 / 6

verdict: PASS

## Round 2 (2026-10-27T19:35:00+08:00)

reviewed_scope: bdaea2ca98d286a6

### Findings

无

### 结论

- 前轮 finding 复核：Round 1 无 finding，本轮核验交付物本身与测试覆盖均保持一致。
- 改测方向复核：无（无任何迁就实现的测试修改）。
- 范围指纹变更说明：Round 1 报告中的指纹 `d63c641b0d94c2f9` 包含了此前 reviewer 运行 `uv` 工具时意外由根目录生成的未跟踪 `uv.lock`；该文件现已被移动至已忽略的 `.scratch/t001_gates/reviewer_generated_uv.lock`，仓库交付内容与规范完全一致；经独立重算与验证，当前标准指纹为 `bdaea2ca98d286a6`。
- 本轮新发现：0 条。
- 未进表的提示：
  1. 交付物与测试代码保持不变，Round 1 实测之 AC-001 至 AC-005（含 s007、s004、s005 Core/Native、s008 分离配置与失效矩阵、s003 UDS/恢复）实测结果及自身 scratch 留存证据（包括 `native_visibility_e2e.log`）均持续有效。
  2. 契约测试与后端测试基线再次核对，环境干净，无额外生成根目录锁文件。
- 总体判断：所有 AC 均通过严格且可复现的验证，测试可信且覆盖完备。
- 系统性 follow-up：无

verdict: PASS
