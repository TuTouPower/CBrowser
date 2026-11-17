# StreamGateway & StreamAgent 独立 Review 与真实黑盒审查报告

**审查记录时间**: `2026-10-27T10:28:52+08:00`（实测 `date -Iseconds` 获取）\
**测试临时目录隔离**: `TMPDIR=<repo>/.scratch/v2_orchestration/gateway_review/.scratch/gateway_media_probe/tmp`（确保 Playwright 临时文件及 Profile 限制在 worktree 内，不假定无宿主污染）\
**黑盒运行环境实测证据**:

- **操作系统平台**: macOS Darwin 24.3.0 (arm64)
- **宿主系统 Python**: `Python 3.9.6` (`python3 --version`)
- **uv 运行环境 Python**: `Python 3.14.7` (Clang 22.1.3, `uv run --no-project python -c "import sys; print(sys.version)"`)
- **Playwright 驱动的 Google Chrome 版本**: `Google Chrome 156.0.8078.48` (`Playwright browser.version` 及 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --version`)
- **Docker 容器内 CloakBrowser 可执行文件**: `/root/.cloakbrowser/chromium-146.0.7680.177.3/chrome` (Chromium 146.0.7680.177)
- **临时资源限制**: 仅限 `cbrowser-spike-gateway-media-*` 命名空间；网络端口 `127.0.0.1:18082`、`127.0.0.1:18083`、`UDP 30007`

**黑盒执行命令**: `TMPDIR=.../tmp uv run --no-project --with aiohttp --with playwright python run_verification.py`\
**黑盒真实 Exit Code**: `0` (ALL PASS)\
**自动生成测试报告**: `.scratch/gateway_media_probe/report.md`\
**历史对照保留**:

- 仅检测 launcher PID 的报告保留于 `review_launcher_only.md`
- cmdline 判定失败的报告保留于 `review_cmdline_failure.md`

______________________________________________________________________

## 一、主控最新修复审阅（行号级分析）

### 1. `get_browser_metadata` 排除逻辑修复

- **代码行号**：`run_verification.py` 第 58-70 行
    ```python
    58: async def get_browser_metadata():
    59:     rc, cid, _ = await run_cmd(f"docker inspect --format '{{{{.Id}}}}' {CONTAINER_BROWSER} 2>/dev/null || true")
    60:     rc, starttime, _ = await run_cmd(f"docker inspect --format '{{{{.State.StartedAt}}}}' {CONTAINER_BROWSER} 2>/dev/null || true")
    61:     probe = "import json, os\nfrom pathlib import Path\nfound = []\nfor item in Path('/proc').iterdir():\n    if not item.name.isdigit():\n        continue\n    try:\n        executable = os.readlink(item / 'exe')\n        command_line = (item / 'cmdline').read_bytes().replace(b'\\0', b' ')\n        if Path(executable).name != 'chrome' or b' --type=' in (b' ' + command_line):\n            continue\n        ticks = (item / 'stat').read_text().split(') ', 1)[1].split()[19]\n        found.append({'pid': int(item.name), 'start_ticks': ticks})\n    except (FileNotFoundError, ProcessLookupError, PermissionError):\n        continue\nif len(found) != 1:\n    raise RuntimeError('Expected exactly one actual Chrome main process')\nprint(json.dumps(found, sort_keys=True))\n"
    62:     rc, pid, err = await run_cmd(f"docker exec {CONTAINER_BROWSER} python3 -c {shlex.quote(probe)}")
    63:     if rc != 0 or not pid:
    64:         raise RuntimeError("Actual Chrome main process identity unavailable")
    65:     return {
    66:         "container_id": cid.strip(),
    67:         "started_at": starttime.strip(),
    68:         "pid": pid.strip().split("\n")[0] if pid.strip() else None
    69:     }
    ```
- **审阅评价**：
    - 第 61 行通过 `(item / 'cmdline').read_bytes().replace(b'\0', b' ')` 将可能混杂的 NUL 字节统一置换为空格；
    - 接着通过 `b' --type=' in (b' ' + command_line)` 成功过滤掉被重写为空格字符串的 zygote (`--type=zygote`)、gpu (`--type=gpu-process`)、utility (`--type=utility`) 及 renderer (`--type=renderer`) 等 Chrome 子进程；
    - 严格限制 `Path(executable).name == 'chrome'` 并强制断言 `len(found) == 1`；
    - 成功锁定了容器内真正的唯一 Chrome 浏览器主进程。

______________________________________________________________________

## 二、黑盒实测数据与重点核查证据

### 1. 真实 Chrome 主进程 PID 与 `start_ticks` 在 SIGKILL 前后严格不变

在黑盒运行中，测试在 Gateway 重启前后分别记录了容器元数据，获得真实证据如下：

- **Gateway 终止前 (Initial)**:
    - Container ID: `1e6730351f871be3061476886d45217d7318c9e0b5c6180278582724389e5fce`
    - StartedAt: `2026-10-27T02:28:14.424334174Z`
    - Chrome Main Process: `[{"pid": 49, "start_ticks": "78629999"}]`
- **Gateway 被 SIGKILL 且重启后 (After SIGKILL & Restart)**:
    - Container ID: `1e6730351f871be3061476886d45217d7318c9e0b5c6180278582724389e5fce`
    - StartedAt: `2026-10-27T02:28:14.424334174Z`
    - Chrome Main Process: `[{"pid": 49, "start_ticks": "78629999"}]`
- **核查结论**: **PASS**。证实不仅 Docker 容器及其启动器未变，容器内真正的 Chromium 主进程（PID 49）及其 Linux 时钟节拍 `start_ticks`（78629999）也完全未发生重启。

### 2. 双 Chrome 标签页独立解码与数据增长

- **实测时序数据**：
    - **Tab 1**:
        - TP1: `53 frames`, `180,054 bytes`
        - TP2: `234 frames`, `245,755 bytes`（增量：+181 帧，+65,701 字节）
    - **Tab 2**:
        - TP1: `53 frames`, `184,291 bytes`
        - TP2: `234 frames`, `250,035 bytes`（增量：+181 帧，+65,744 字节）
    - **Tab 1 关闭后 Tab 2 持续解码**：
        - Tab 2 解码帧数由 `234` 增长至 `474`（增量：+240 帧持续解码，未被影响）。
- **核查结论**: **PASS**。

### 3. WebRTC 传输严格绑定 UDP 30007 及反例校验

- **实测候选**：
    - Tab 1 Remote Candidate: `protocol == 'udp'`, `port == 30007`, `candidateType == 'host'`
    - Tab 2 Remote Candidate: `protocol == 'udp'`, `port == 30007`, `candidateType == 'prflx'` (TP1) -> `host` (TP2)
- **负例反体验证**：
    - `run_verification.py` 第 340-348 行验证：当设定错误预期端口 9999 时，校验逻辑返回失败，确保断言并非永远恒真的假阳性。
- **核查结论**: **PASS**。

### 4. 独立 Gateway 进程与 Agent 自动重注册

- `run_gateway_server.py` 与 `run_agent_client.py` 分别作为独立 OS 进程启动（PID 99767 为 Agent）。
- `gateway_proc.kill()` 执行 SIGKILL (`kill -9`)，Agent 进程保持运行；在 Gateway 重启后，Agent 在退避重试中自动重连注册（返回 HTTP 400 WS 期望）。
- **核查结论**: **PASS**。

### 5. Agent 双向 SDP/ICE 轨迹审计

- 审计文件共捕获 60 条独立信令事件（`agent_audit.jsonl`）。
- 涵盖双向流量：`agent->upstream`、`upstream->agent`、`gw->agent->upstream`、`upstream->agent->gw`。
- 信令报文具备独立 SHA256 哈希与字节大小（HELLO 384B、SESSION 14B、SESSION_OK 54B、SDP Offer ~13KB、SDP Answer ~7.7KB、ICE ~227-270B）。
- **核查结论**: **PASS**。

______________________________________________________________________

## 三、限制、边界与澄清（明确不超出证据范围）

1. **页面重连边界：属于“页面显式重建连接”，非自动重连/非 ICE Restart**
    - 恢复过程由 `run_verification.py` 第 412 行调用 `await page2.goto(...)` 显式重新导航完成，重新发起完整的 HTTP 静态文件加载和 WebSocket/WebRTC 重新协商。
    - 系统未实现现有 RTCPeerConnection 的断线自动恢复或 ICE restart，严禁使用“无缝/低延迟重连”等宣传词汇。
2. **敏感信息过滤范围：仅限外层 Envelope**
    - `gateway_core.py` 中的 `_sanitize_packet` 仅能剔除协议外层顶层的特定 key（`token`、`secret` 等）。
    - 转发的 opaque 信令 `data` 字符串（SDP/ICE 内容）未做内部解构与扫描，不代表内部无敏感泄漏。
3. **安全隔离项的状态区分**：
    - **Origin 403 检查**、**跨 Profile / 跨 Agent Session 越权拦截**、**Slow Viewer 满队列断开 (100 帧)**：在本次黑盒测试中均未注入对抗性攻击样本，属于**代码级静态审阅通过**，而非黑盒端到端攻防验证。
4. **音频流未覆盖 (Not Covered)**：
    - 测试指标采集脚本仅统计了 `stat.kind === 'video'`，未对音频 RTP 包做增长性或解码断言。当前原型仅验证了视频传输通路。

______________________________________________________________________

## 四、测试执行结论矩阵（12 项全部通过）

|序号|检查项 (Test Identifier)|状态|实测证据|
|---|---|---|---|
|1|`containers_sandbox_setup`|**PASS**|卷与容器启动正常，CloakBrowser 导出 1920x1080 DPR1 DOM 指标|
|2|`negative_viewer_rejected_when_no_agent`|**PASS**|无 Agent 时 Viewer 请求精准返回 HTTP 503|
|3|`independent_agent_registered`|**PASS**|独立 Agent 进程向 Gateway 完成 WebSocket 注册并建立隧道|
|4|`dual_tab_initial_decoding`|**PASS**|Tab 1 (53 帧) 与 Tab 2 (53 帧) 成功解码|
|5|`dual_tab_growth_two_timepoints`|**PASS**|双方在 TP2 均增长至 234 帧（数据量持续递增）|
|6|`strict_both_peers_udp30007`|**PASS**|双方 selected remote candidate 严格匹配 `udp:30007`|
|7|`negative_wrong_udp_port_fails_validator`|**PASS**|9999 端口反例校验拦截成功|
|8|`tab1_close_tab2_continues`|**PASS**|Tab 1 关闭后 Tab 2 继续解码至 474 帧|
|9|`gateway_sigkill_agent_auto_reconnects`|**PASS**|Gateway 被 kill -9 杀掉后，Agent 存活并在重启后自动恢复注册 (HTTP 400)|
|10|`page_recovers_decoding_after_gateway_restart`|**PASS**|显式重新导航后，WebRTC 重新协商成功并解码 13 帧|
|11|`browser_container_pid_starttime_invariant`|**PASS**|真实 Chrome 主进程 PID 49 及 `start_ticks` 78629999、容器 ID、StartedAt 严格一致|
|12|`agent_detailed_trajectory_verified`|**PASS**|捕获 60 条含 SHA256 与字节长度的双向 SDP/ICE 审计记录|

**套件最终裁决**: **ALL PASS** (Exit Code: 0，执行耗时约 35 秒，严格受 180s 总超时控制，现场资源均在 finally 中完整清理)。
