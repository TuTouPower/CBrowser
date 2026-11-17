# Container CDP & UDS Proxy 独立技术评审报告

- **评审员角色**：独立 Gemini Reviewer / 真实黑盒审计
- **模型版本**：`cpa/gemini-3.8-flash`
- **审计范围**：当前 worktree 下 `.scratch/container_cdp_review/` 5 个源码文件及真实跨容器执行行为
- **时间戳**：2026-10-27T02:46:00+00:00

______________________________________________________________________

## 1. 真实黑盒执行记录与退出状态

本评审在宿主机严格执行，未对被测实现或断言做任何修改，仅操作指定的 `cbrowser-spike-cdp-uds-*` 资源。两次实验均在全新 Docker 命名卷（`runtime`、`artifacts`）与独立容器隔离环境下运行。

### 1.1 实验一：独立 External Override 控制对照 (`--case override_control`)

- **执行命令**：`python3 run_cross_container.py --case override_control`
- **真实进程 Exit Code**：`0`
- **Client 容器输出**：
    ```text
    Control proved external CDP override actually redirects a real download while connected

    Real isolated Browser and Supervisor containers: override_control passed
    ```
- **Browser 容器退出码（`docker wait`）**：`0`
- **网络与端口隔离验证**：
    - `HostConfig.NetworkMode`: `'none'`（通过 Docker inspect 验证）
    - `HostConfig.PortBindings`: `None` / 空字典，无任何 published port，客户端宿主无 TCP CDP 路由。
- **真实数据与对照验证**：
    - 外部 Client 通过 UDS 发送 `Browser.setDownloadBehavior(behavior='allow', downloadPath='/exchange/external')`。
    - 触发 `download-1.txt` 下载，文件落地于 `/exchange/external/download-1.txt`，字节数精确为 `50` 字节（内容：`b'REAL_CDP_DOWNLOAD_VERIFICATION_CONTENT_FIRST_11111'`）。
    - 严格正负对照：检查 `/exchange/default` 目录，文件列表长度为 `0`（完全为空）。
    - 退出路径：外部发送 `Browser.close` 之后，Browser 容器正常退出，exit code 精确为 `0`。

### 1.2 实验二：断开恢复与重臂对照 (`run_cross_container.py` 默认 `recovery`)

- **执行命令**：`python3 run_cross_container.py`
- **真实进程 Exit Code**：`0`
- **Client 容器输出**：
    ```text
    {"cross_container_uds": true, "first_bytes": 50, "second_bytes": 51, "external_directory_empty": true, "auto_rearmed": true}

    Real isolated Browser and Supervisor containers: recovery passed
    ```
- **Browser 容器退出码（`docker wait`）**：`0`
- **真实数据与对照验证**：
    - **第 1 次下载**：在初始默认配置下触发 `dl1`，落地 `/exchange/default/{guid1}`，大小 `50` 字节（内容：`b'REAL_CDP_DOWNLOAD_VERIFICATION_CONTENT_FIRST_11111'`）。
    - **外部干扰与断开**：外部连接通过 UDS 发送 `Browser.setDownloadBehavior` 将路径篡改为 `/exchange/external`，随后外部连接显式断开 (`close`)。
    - **自动 Rearm 响应**：代理捕获外部断开后自动触发 `rearm_download_capture()`，CDP 成功响应重设为 `/exchange/default`，`rearm_count` 从 1 自增为 2。
    - **第 2 次下载（恢复验证）**：触发 `dl2`，落地 `/exchange/default/{guid2}`，大小 `51` 字节（内容：`b'REAL_CDP_DOWNLOAD_VERIFICATION_CONTENT_SECOND_22222'`）。
    - **严格正负对照**：
        - 检查 `/exchange/external`：列表完全为空（`len(list(...)) == 0`），证明外部临时篡改在断开后未泄漏任何文件。
        - 检查 `/exchange/default`：列表恰好包含 2 个已命名文件（`len(list(...)) == 2`），且两个文件 GUID 不同，字节内容全部通过二进制比对校验。
    - 退出路径：Supervisor 发送 `Browser.close`，Browser 容器正常终止，退出码 `0`。

______________________________________________________________________

## 2. 源码静态审查与生命周期评估

### 2.1 断言覆盖率与失败非零保障（精准行号）

1. **客户端异常与退出码保障**：
    - `supervisor_client.py` 第 22-24 行：`command()` 函数严格检查 CDP 响应报文，若含有 `'error'` 或 `'exceptionDetails'`，立即抛出 `RuntimeError`，杜绝 CDP 失败时的“假绿”。
    - `supervisor_client.py` 第 37 行、第 65 行：事件超时或重臂超时抛出 `TimeoutError`，未被捕获吞掉，保证进程异常终止（exit code 1）。
    - `supervisor_client.py` 第 51, 70, 71, 72 行：二进制内容比对、外部目录为空断言、默认目录计数断言均为显式 `assert`，断言失败抛出 `AssertionError`（exit code 1）。
    - `supervisor_override_control.py` 第 23-24 行：对重定向落地文件内容及默认目录为空做硬断言，失败立即退出。
2. **Runner 编排器监控与退出码传递**：
    - `run_cross_container.py` 第 13 行：`docker()` 默认携带 `check=True`，任何 Docker 子命令非零退出均由 `subprocess.run` 抛出 `CalledProcessError`。
    - `run_cross_container.py` 第 46 行：Client 容器执行设置 `timeout=50`，有效防止死锁卡死。
    - `run_cross_container.py` 第 48-49 行：`docker wait` 取出容器真实退出码并做严格断言 `assert exit_code == '0'`。
    - `run_cross_container.py` 第 51-53 行：`finally` 块确保收集 browser 容器日志（写入 `cross_container_browser.log`），并无条件调用 `cleanup()` 清理容器与 volume，资源不残留。

### 2.2 异步任务生命周期与关闭清理

1. **Client Handler 任务收尾**：
    - `container_cdp_probe.py` 第 141-143 行：客户端连接任务加入 `self.client_tasks`，并在完成时通过 `add_done_callback(self.client_tasks.discard)` 自动注销。
    - `container_cdp_probe.py` 第 165-170 行：双向转发流（`uds_to_ws` 与 `ws_to_uds`）通过 `asyncio.wait(..., return_when=FIRST_COMPLETED)` 协作，一方结束立即 `cancel()` 另一方。
    - `container_cdp_probe.py` 第 193-197 行：`close()` 时对所有存活的 `client_tasks` 执行 `t.cancel()` 并 `asyncio.gather(*self.client_tasks, return_exceptions=True)` 等待任务收敛退出。
2. **潜在生命周期缺陷与异常**：
    - **缺少 Task 引用与取消**：`container_cdp_probe.py` 第 83 行 `asyncio.create_task(self._listen_agent_events())` 创建后台监听任务，但未持有该 task 引用，也未在 `close()` 中主动取消，而是被动等待 WebSocket 连接关闭。
    - **连接关闭时的 Race Condition 日志**：`Browser.close` 执行后，Chrome 进程先于代理终止，导致 WebSocket 管道在收到 close frame 前即被操作系统重置。`_listen_agent_events` 在第 134 行捕获到异常时，`self.shutting_down` 尚未置位为 True，因而记录了一条无害但显眼的日志：
        ```text
        [2026-10-27T02:45:57+00:00] Agent event listener error: no close frame received or sent
        ```
        （见 `cross_container_browser.log` 第 26 行）。

______________________________________________________________________

## 3. 生产限制与架构定性（禁止过度夸大）

被测代码是一组针对“Docker 隔离环境中通过 UDS 安全穿透并代理 Chrome loopback CDP、并在外部连接断开时实施下载路径自动重臂（Rearm）”的**可运行验证原型（PoC / Spike）**。**严禁**将本实现描述为生产就绪或完全可靠的生产链路。

### 3.1 明确的技术限制

1. **`_download_events` 未持久化**：
    - 见 `container_cdp_probe.py` 第 75 行 `self.download_events = []`。
    - CDP 下载事件仅追加于进程内存列表。虽然 `browser_agent.py` 周期性将快照写入 `/run/test/status.json`，但一旦 Agent 进程或容器重启，历史下载事件及 GUID 映射将全部丢失，缺乏事务数据库、持久 WAL 或持久化消息队列支持。
2. **多客户端断开重臂存在并发竞态（Race Condition）**：
    - 见 `container_cdp_probe.py` 第 183-185 行：每个客户端断开时均无条件执行 `await self.rearm_download_capture()`。
    - 该重臂逻辑**没有互斥锁（`asyncio.Lock`）保护**，也未判断当前是否仍有其他活跃的外部客户端。若有多个外部客户端并发连接并交错断开，会触发多次并发重臂 CDP 请求。
    - 更严重的是：Chrome 的 `Browser.setDownloadBehavior` 是\*\*全局（Browser 级）\*\*配置，而非 Session 级。若客户端 A 正在下载，客户端 B 断开触发 Rearm，将直接修改全局下载路径，导致客户端 A 的后续下载行为被篡改。
3. **安全与授权真空**：
    - UDS 仅依赖 Linux 文件权限（本实验中挂载在容器 volume 下），缺乏任何身份认证、Token 机制、RBAC 授权或 CDP 命令白名单（例如允许外部调用 `Browser.close` 破坏运行时）。
4. **非正式生产链路**：
    - 本套原型**不是**正式的 FastAPI 控制网关、**不是**生产级 Supervisor 守护进程、也**不是**具备配额与生命周期管理的 Artifact 归档系统。其定位仅用于证明跨容器 UDS 代理和基于 CDP 连接事件的 Rearm 状态恢复在语义上成立。

______________________________________________________________________

## 4. 评审结论

|审查维度|预期契约|实际表现|判定|
|:---|:---|:---|:---|
|**Override Control 真实落地**|外部连接修改路径至 external，真实下载 50 字节，default 目录为空|`download-1.txt` 落地 external，内容精确一致，default 为空|**PASS**|
|**Recovery 真实自动重臂**|首次下载 50 字节 default；外部篡改并断开后自动 rearm；二次下载 51 字节回落 default；external 为空|两次下载精确匹配 50/51 字节，全部位于 default；external 保持 0 文件；rearm_count 正确递增|**PASS**|
|**Docker 容器隔离性**|真实双容器、network: none、无发布端口、UDS 跨卷连接|inspect 证实 network: none，无 port binding，纯 UDS 连通|**PASS**|
|**退出码与断言覆盖**|失败非零，成功 exit 0，Browser 正常终止 exit 0|两次实验 exit code 均为主控 0、Browser 0，断言覆盖完整|**PASS**|
|**代码与生命周期收尾**|Runner 50s 保护，finally 清理，无孤立资源泄漏|临时容器与 volume 在 finally 均被清理，仅写入 log|**PASS**|
|**生产准备度声明**|明确指出未持久化、并发争用等生产限制，不夸大|已在审计报告中详细列明 4 项核心生产限制|**PASS**|
