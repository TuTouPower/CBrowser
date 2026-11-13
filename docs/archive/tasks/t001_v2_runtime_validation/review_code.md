# Task review t001（reviewer_focus: 代码）

- task：`t001_v2_runtime_validation`
- spec：`docs/tasks/t001_v2_runtime_validation/task.md`
- diff_anchor：`3c8bdbc55570e85aaeb6365a3d512da9c0ce180c`
- target：`git -C '<repo>_t001' diff 3c8bdbc55570e85aaeb6365a3d512da9c0ce180c`
- round：1
- reviewed_at：2026-10-27T19:30:00+08:00

reviewed_scope: d63c641b0d94c2f9

## Findings

### t001_code_f001 - s008 启动脚本缺少 set -e 导致子命令失败未及时阻断

- 严重度：minor
- 锚点：健壮性·错误处理
- 位置：`docs/archive/spikes/s008_turn_generation_media/code/stage2_containers.sh:1`
- 问题：前文初审时误报该脚本缺少 `set -euo pipefail`。
- 状态与更正：**已撤回（WITHDRAWN）**。经复核源码真实快照，`docs/archive/spikes/s008_turn_generation_media/code/stage2_containers.sh` 第 2 行已精确声明 `set -euo pipefail`。原描述系误读，予以全量撤回，不作为有效代码缺陷。

### t001_code_f002 - stage2_media_restart_probe 在异常清理分支未对可选连接关闭做异常保护

- 严重度：minor
- 锚点：健壮性·资源释放
- 位置：`docs/archive/spikes/s008_turn_generation_media/code/stage2_media_restart_probe.py:590`
- 问题：前文初审描述“await ws.close()/finally 附近抛异常”。
- 状态与更正：**已撤回（WITHDRAWN）**。经复核源码真实快照，`stage2_media_restart_probe.py` 内部并不存在 `await ws.close()` 或 `finally` 块；第 590 行实际为探针执行摘要日志输出，收尾调用为 `await ctx.close()`。原描述定位与调用关系失准，予以全量撤回，不作为有效代码缺陷。

### t001_code_f003 - Gateway 注册超时处理使用固定 sleep 轮询检查

- 严重度：minor
- 锚点：性能与资源·异步控制流
- 位置：`docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_verification.py:396-407`
- 问题：在网关验证脚本中，重启网关后等待现有 Agent 自动重连注册时（第 396–407 行），采用 `for _ in range(15): await asyncio.sleep(1)` 结合 `curl` 探测网关返回码（HTTP 400 表明 websocket upgrade 就绪，HTTP 503 表明未就绪）。该实现虽然满足本地黑盒测试的确定性重连等待，但在高并发或快速自愈场景下存在固定步长轮询延迟（而非事件驱动）。
- 建议：在后续正式微服务开发（`cbrowser-stream-gateway`）中，网关与 Agent 内部注册状态应采用事件通知（如 `asyncio.Event` / 异步广播通道）替代外部 HTTP 轮询。归档 spike 代码作为历史快照保持不可变，本项记录为后续生产服务实现的架构参考。

## 结论

- 前轮 finding 复核：
  - `t001_code_f001`：已撤回（源码第 2 行确有 `set -euo pipefail`，前述报告失实）。
  - `t001_code_f002`：已撤回（无 `ws.close()` 与对应 `finally`，前述报告失实）。
  - `t001_code_f003`：保留更正版（精确定位到 `run_verification.py:396-407` 轮询点，建议供后续任务参考）。
- 本轮新发现：0 条（无新增 finding，杜绝凑数）。
- 7 视角体检与静态代码事实核验：
  - 安全审视：静态审查 diff 新增/修改的归档脚本及配置，无硬编码生产凭证；`start_coturn.sh:14` 采用 `secrets.token_hex(24)` 动态生成临时 secret 并安全落盘本地 `.scratch`；Profile 隔离探针采用非 root（UID 1000）、独立 Xauthority 卷及专属 PulseAudio socket 卷隔离，有效防止跨 Profile 越权。
  - 正确性：AST 静态解析全部 96 个 spike 文件中的 Python 脚本，语法与导入依赖结构完整；数学分析算法（`estimate_frequency_autocorr`）与 Web Locks 冲突重映射逻辑在静态 AST 分支覆盖上严谨。
  - 契约·Breaking：实现层变动仅为技术验证归档、架构决策蓝图及 spec 契约文档，未破坏既有代码基线（`src/backend`、`src/frontend` 保持完全未变，基线测试 384 passed / 49 passed）。
  - 性能与资源：蓝图明确将容器内存配额硬限制在 15.66 GiB，视频编码采用纯 CPU 软件基准；静态分析 8/30 FPS 自适应与全后台暂停捕获逻辑与宿主机资源守卫约束完全吻合。
  - 架构与可维护性：双容器 shareable IPC 供体契约（d004）、三层对象解耦与废弃控制租约在文档中保持严密一致。
  - 健壮性与可观测：Supervisor 重启离线事件重放、网关 SIGKILL 浏览器进程保活在静态代码与发现记录（d006, d008）中逻辑闭环。
  - 文档与规格一致性：`docs/specs/v2_runtime_validation.md`、`docs/blueprint/architecture.md`、`docs/blueprint/decisions.md`、`docs/blueprint/testing.md` 与验证矩阵高度一致；明确区分“技术验证通过”与“生产已完成”，对用户豁免项（公网及原生 Linux x86）严格单列 `NOT_RUN / USER_WAIVED`。
- 未进表的提示：
  - 文件过大提示（归档不可变 spike，包含完整正负例测试编排，免拆分）：
    - `docs/archive/spikes/s007_profile_isolation/code/run_isolation_probe.py`：1054 行
    - `docs/archive/spikes/s004_media_connections/code/media_e2e_probe.py`：787 行
    - `docs/archive/spikes/s005_capture_policy/code/native_visibility_e2e.py`：601 行
    - `docs/archive/spikes/s008_turn_generation_media/code/stage2_media_restart_probe.py`：604 行
  - 圈复杂度提示：部分归档探针主驱动函数（如 `media_e2e_probe.py:run_suite_v4` CC=114、`stage2_media_restart_probe.py:run_stage2` CC=71）圈复杂度较高，系端到端多阶段线性测试流程编排所致，归档代码保持只读快照，不进 finding 表。
- 总体判断：所有 6 条有效 AC 均有确定性的技术探针资产、架构 ADR 及 Finding 文档支撑；用户豁免项客观准确单列；无未解决的 critical 或 important finding。
- 系统性 follow-up：正式 v2 生产组件（`cbrowser-api` v1、`cbrowser-supervisor`、`cbrowser-stream-gateway`）将在后续实现任务（t002+）推进。

### AC 复验方式

- AC-001：`re_verified`（静态查证 `s007_profile_isolation/code/` 源码及 d011 发现：XShmGetImage 正例、非 root 独立卷与 Pulse 48000 Hz 误差 ≤ 1% 真实音频断言）。
- AC-002：`re_verified`（静态查证 `s004_media_connections/code/` 源码及 d007 发现：双 Chrome 页面 1080p 视频解码、交错输入 121212 及 Web Locks 防复制冲突逻辑）。
- AC-003：`re_verified`（静态查证 `s005_capture_policy/code/` 源码及 d013 发现：8/30 FPS 动态仲裁、全后台暂停捕获及恢复前台先 8 后 30 FPS 状态机逻辑）。
- AC-004：`re_verified`（静态查证 `s006_gateway_media_recovery/code/` 动态隧道与 `s008_turn_generation_media/code/` 源码及 d012 发现：本地分离 RTC 配置、同 PC ICE 换代接管及单侧无效凭证 401 拒绝；公网可达性单列 `NOT_RUN / USER_WAIVED`）。
- AC-005：`re_verified`（静态查证 `s003_selkies_control/code/` 源码及 d002/d006 发现：CDP UDS 代理、下载自动捕获与断开恢复，API 离线退出事件持久化落盘与 Supervisor 重启重放防误重启）。
- AC-006：`re_verified`（静态查证 `docs/tasks/t001_v2_runtime_validation/validation_matrix.md` 及全部 9 个 spike 报告：macOS OrbStack arm64 逐项映射 18 章 17 项，原生 Linux x86_64 单列 `NOT_RUN / USER_WAIVED`）。

coverage = 6 / 6 (100%)

verdict: PASS

## Round 2 (2026-10-27T19:40:00+08:00)

reviewed_scope: bdaea2ca98d286a6

### 前轮 finding 复核与本轮审查范围校验

1. **审查范围指纹核验**：
   - 相对 Round 1 变更：宿主清理了由工具命令偶然生成且未被 gitignore 的根目录 `uv.lock`，未变动任何交付源码、测试、蓝图或归档资产。
   - 权威当前指纹：`reviewed_scope: bdaea2ca98d286a6`，与本轮 worktree 状态完全一致。
2. **Finding 复核**：
   - `t001_code_f001`：维持撤回（已查证 `stage2_containers.sh:2` 存在 `set -euo pipefail`，事实无缺陷）。
   - `t001_code_f002`：维持撤回（已查证 `stage2_media_restart_probe.py` 内部无 `ws.close()` 与对应 `finally`，事实无缺陷）。
   - `t001_code_f003`：维持更正版（精确定位于 `run_verification.py:396-407`，保留作为后续 `cbrowser-stream-gateway` 微服务实现的异步事件通知参考建议）。
3. **本轮新发现**：0 条（无新增 finding，无为凑数制造的问题）。
4. **代码事实与声明严谨性说明**：
   - 明确 AST 静态解析仅证明脚本语法有效性、依赖声明及静态分支结构完备，不替代动态分支覆盖率测量；
   - 蓝图中的宿主 Docker 配额（10 CPU / 15.66 GiB RAM）代表当前宿主机 OrbStack 引擎分配的可用全局算力/内存边界，不代表后续每个独立微服务或 Profile 动态容器的单实例硬限制（各容器资源硬限由 Supervisor 动态配额约束）。
5. **总体判断**：
   - 契约区 6 条修订后有效 AC 在实现层由不可变归档技术验证资产（9 个 spikes）及架构蓝图完整覆盖，事实证据严密闭环；
   - 用户豁免项（公网入口与原生 Linux x86_64）在规范、蓝图及矩阵中均客观单列为 `NOT_RUN / USER_WAIVED`；
   - 无未解决的 critical 或 important finding。

### AC 复验方式

- AC-001：`re_verified`（静态查证 `s007_profile_isolation/code/` 源码及 d011 发现：XShmGetImage 正例、非 root 独立卷与 Pulse 48000 Hz 误差 ≤ 1% 真实音频断言）。
- AC-002：`re_verified`（静态查证 `s004_media_connections/code/` 源码及 d007 发现：双 Chrome 页面 1080p 视频解码、交错输入 121212 及 Web Locks 防复制冲突逻辑）。
- AC-003：`re_verified`（静态查证 `s005_capture_policy/code/` 源码及 d013 发现：8/30 FPS 动态仲裁、全后台暂停捕获及恢复前台先 8 后 30 FPS 状态机逻辑）。
- AC-004：`re_verified`（静态查证 `s006_gateway_media_recovery/code/` 动态隧道与 `s008_turn_generation_media/code/` 源码及 d012 发现：本地分离 RTC 配置、同 PC ICE 换代接管及单侧无效凭证 401 拒绝；公网可达性单列 `NOT_RUN / USER_WAIVED`）。
- AC-005：`re_verified`（静态查证 `s003_selkies_control/code/` 源码及 d002/d006 发现：CDP UDS 代理、下载自动捕获与断开恢复，API 离线退出事件持久化落盘与 Supervisor 重启重放防误重启）。
- AC-006：`re_verified`（静态查证 `docs/tasks/t001_v2_runtime_validation/validation_matrix.md` 及全部 9 个 spike 报告：macOS OrbStack arm64 逐项映射 18 章 17 项，原生 Linux x86_64 单列 `NOT_RUN / USER_WAIVED`）。

coverage = 6 / 6 (100%)

verdict: PASS
