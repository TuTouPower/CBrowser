> 范围更新：本报告保留对应实验快照及历史限制。用户随后明确豁免公网与原生Linux x86_64执行；当前有效门禁见t001/scope_adjustment.md及架构计划“执行调整”。未运行项不计为测试通过。

# Spike report

## 问题

验证 v2.3 第18.15–17项：UDS/CDP 下载及断开恢复可行性、运行事件恢复边界和平台缺口。此阶段只运行技术原型，不改生产代码或用户数据。

## 成功判据

- Chrome 经真实 UDS/loopback WebSocket 接收命令，真实 HTTP 下载产生完成事件和内容匹配文件。
- 外部客户端改变下载策略并断开后，由代理自动恢复；第二次下载落回默认目录且覆盖目录无文件。
- 不以代理内部计数或命令 ACK 替代实际下载行为；不把本地原型自测作为生产重启验收。

## 尝试

- 首版仅发送 setDownloadBehavior，恢复由测试客户端手工调用。主控与独立 Gemini reviewer 均判定不足，未采纳为通过证据。
- 补强 `code/test_cdp_real.py`：启动独立 headless Chrome、本地 HTTP 与 UDS 代理，核对两次真实下载；自动恢复等待 CDP 成功响应；45 秒总超时与退出清理。
- agent 首轮曾错误写入 `/tmp/test_chrome_cdp`。主控中断该 OpenCode 进程并确认相关测试进程退出；该目录未擅自删除，后续使用项目 `.scratch`。
- 原型 SQLite 事件脚本只验证自身编写逻辑，缺少真实 API/Supervisor 进程重启，未纳入通过证据或交付代码。

## 证据

- agent 于 2026-10-27T01:25:44+08:00 完成补强脚本，主控于 2026-10-27T01:26:38+08:00 独立重跑，退出码 0。
- 两次下载均接收 `Browser.downloadWillBegin` 和 `Browser.downloadProgress(state=completed)`，分别校验 50/51 字节预期内容；不同 GUID，默认目录存在两文件，外部覆盖目录为空。
- 自动恢复由 UDS 客户端断开触发，管理 CDP 返回对应 id 和空 result 后再记录成功；第二次下载证明策略实际恢复。
- 原始主控日志：主仓 `.scratch/v2_orchestration/root_cdp_verify.log`（未入库）；事实摘要见 d002。
- 环境：真实 macOS Chrome、Python 3.14.7、websockets。代码内 Chrome 路径为 macOS 固定路径，未验证容器内 CloakBrowser。

重跑时先复制脚本到 `.scratch`，避免生成数据进入文档目录。需要本机已安装 Google Chrome、uv、Python，：

```bash
mkdir -p .scratch/cdp_probe
cp docs/spikes/s003_selkies_control/code/test_cdp_real.py .scratch/cdp_probe/test_cdp_real.py
uv run --no-project --with websockets python .scratch/cdp_probe/test_cdp_real.py
```

重复运行只会重建该脚本目录下 `exp_cdp_real` 测试数据；禁止指向现有用户 Profile。测试 Chrome 与个人 Chrome 使用独立数据目录。

- 2026-10-27T01:38:05+08:00：主控将待交付脚本改为 Chrome `--remote-debugging-port=0`，从该独立 Profile 的 DevToolsActivePort 文件读取端口，并检查 Chrome 进程存活，避免误连其他调试服务；日志改为 ISO 8601。修改后在 task worktree 的 `.scratch/cdp_probe` 重跑退出码 0，两次真实下载仍通过。此前独立 review/黑盒报告对应原固定端口快照；最终交付内容仍须重新独立 review。

## 真实进程恢复补充验证

交付代码：`code/recovery_probe/{roles.py,container_agent.py,test_orchestration.py}`。三文件 SHA-256 与独立 reviewer 重跑快照逐字节一致，review 见 `recovery_review.md`。

- 主控于 2026-10-27T02:31:53+08:00 完成真实重跑，退出码 0；原始日志为主仓 `.scratch/v2_orchestration/root_recovery_verify.log`。
- 独立 Gemini 于 2026-10-27 上午另行重跑，耗时 29.3 秒、退出码 0。API 与 Supervisor 均为独立宿主进程；Browser 为真实 Docker CloakBrowser。
- API 离线后，经 UDS → loopback CDP `Browser.close` 正常退出，真实 exit_code=0。Supervisor 将退出事件持久化后、HTTP 上报前被 SIGKILL；API 仍离线时重启 Supervisor，再重启 API，事件送达后 desired/observed 收敛 stopped；5 轮 reconcile 无幽灵重启。
- SQLite 在独立 api_storage，Browser 只挂 runtime；docker inspect 和容器内访问失败构成负例。Supervisor 无 DB 参数，不写 SQLite。事件重放被幂等拒绝；实际启动新实例后，旧实例迟到事件被拒且新容器继续运行。

独立 review 明确限制：新实例启动后 observed_state 尚未上报 running；异常退出未实现 2/10/30 秒重试与 crash-loop 熔断；Agent 文件替换与 Supervisor 删除间存在多事件并发窗口；空队列文件导致测试额外等待。以上均非生产可采纳实现，这些生产实现缺口保留，不能把实验代码直接投入生产。本实验没有注入写入中途断电，不能证明断电无损；不采纳作者原报告中“100%”或“彻底根除”措辞。

复现先复制三个文件到 `.scratch/recovery_probe`，仅使用已建 `cbrowser-spike-runtime-browser:test` 镜像：

```bash
mkdir -p .scratch/recovery_probe
cp docs/spikes/s003_selkies_control/code/recovery_probe/*.py .scratch/recovery_probe/
uv run --no-project python .scratch/recovery_probe/test_orchestration.py
```

脚本只清理 cbrowser-spike-recovery 前缀容器及自身实验目录，使用 localhost:58083。不要并发运行该固定端口实验。该最小原型采用 http.server/sqlite3/Docker CLI，正式实现仍需 FastAPI/SQLAlchemy/Docker Engine API，并补全上述语义。

## 容器内CloakBrowser与跨容器UDS补充

见[container_download_report.md](container_download_report.md)。主控已真实运行独立Browser与Supervisor容器，均networknone、无published CDP；两次真实下载及断开恢复通过，另有覆盖策略实际生效对照。独立review尚待执行，不将底层可行性等同生产完整链路。

## 结论

- 第18.15底层 UDS 代理、真实下载和自动恢复：原型通过。不是正式统一 agent.sock RPC 契约或生产安全验收，该下载原型单独不足以证明AC-005；补充跨容器与恢复证据见下。
- 第18.16：真实独立 API/Supervisor 进程和 Docker CloakBrowser 正常退出恢复原型已由主控与独立 Gemini 重跑通过；仅证明下述单实例恢复检查点，不代表正式产品全部状态/异常退出验收。
- 第18.17 Linux x86_64 双容器：NOT_RUN。本机 OrbStack arm64；amd64 镜像模拟运行不等于原生 x86_64 验收。
- 第19章16 vCPU/32 GiB 性能和8小时压力：NOT_RUN，需独立基准环境。
- 独立 Gemini reviewer 已只读复核补强版代码与日志：原型可行性 PASS，完整第18.15生产验收 INCOMPLETE。此为静态审查与日志复核，不能证明长期稳定、无泄漏或并发安全。独立 Gemini 黑盒 agent 另开 session 重跑，退出码 0；独立检查两文件分别为 50/51 字节、覆盖目录为空、实验 Chrome PID 已退出。日志保存在主仓 `.scratch/v2_orchestration/review/.scratch/blackbox_cdp.log`；没有据此推断长期资源稳定性。

## 是否采纳

- 决定：是，仅采纳 UDS/CDP 下载自动恢复和单实例持久队列检查点恢复的技术可行性结论。
- 理由：真实浏览器、HTTP、UDS、CDP 事件与文件内容证据闭环，经主控独立重跑。
- 后续 task：t001
- 无需后续理由：不适用

## 关联 findings

- d002：UDS/CDP 真实下载与自动恢复原型可行，正式链路未验收。

- d001：改造前项目测试和运行基线。

- d006：真实 API/Supervisor/Browser 进程恢复检查点；不含并发文件队列安全或断电保证。

- 最新阶段裁决：跨容器下载补充已由独立Gemini两case重跑exit0；与本报告真实API/Supervisor/正常退出防误启动证据合并，覆盖t001 AC-005技术实验观察，已勾选。正式生产协议、Artifact持久化、并发重臂与异常退出退避不属于已通过结论，后续生产实现仍须完成。
