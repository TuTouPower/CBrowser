---
tid: "t003"
slug: "v2_browser_runtime"
title: "实现隔离 Browser Runtime 与受控 UDS Agent"
status: "done"
branch: "t003_v2_browser_runtime"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "226c8453097fb982835ccb254cea8a3f26d131b3"
depends_on: "t002"
conflicts_with: ""
note: ""
---

# Task 过程总账

front matter 只经 task.py 修改；本次保留原始 front matter。reviewer 只写对应 review 报告。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 执行身份与范围

- branch=t003_v2_browser_runtime，base/diff_anchor=226c8453097fb982835ccb254cea8a3f26d131b3；attempt=1，execution_id=57e21d93a87e4ab1baf4f96f652bca99，owner_id=root_v2_20261027。
- t001、t002 已集成；本 task 仅新增 Browser Runtime 镜像、Agent、协议与测试/文档，不修改正式 compose、旧入口、API/SQLite 或真实用户数据。无中间业务 commit。
- 用户明确要求 OpenCode cpa/gemini-3.8-flash 子进程与独立 review/黑盒，使用注册 t003 worktree 实施、独立 validation worktree 验证。所有生产 writer 已停止；当前源码由 Root 冻结。宿主只写 ~/kar/code，测试新数据、随机资源名、精确清理，不读/source .env。
- 公网与原生 Linux x86 执行为 NOT_RUN / USER_WAIVED；正式目标仍是当前 Mac OrbStack Docker 与同机 Chrome。后续容量/P95/8小时/1000次输入目标未在本 task 计为通过。

### 实现与关键决策

- 固定 CloakBrowser0.6.4/Playwright1.64.1，真实 persistent context 消费 t002 快照；Linux ELF 架构、精确 build 与实际 --version 校验，只读 /data/engine-cache，无镜像 debug fallback。可显式选择 -pro 缓存目录，实际 licensed Pro 未执行。
- tini + supervisord 分离 Runner 与 UDS Agent；只自动重启 Agent。Runner 保留 SDK driver 所有权，用真实 Chrome wait 观测退出。Chrome0 但 driver/Xvfb 丢失记 lifecycle/error，不冒充用户正常退出。d016 与归档 s010 保留机制证据；t005 消费生命周期错误且不得清除 running 意愿。
- 实例 journal、稳定终态事件 ID，事件先于状态，原子 tmp/fsync/replace/dirfsync，目录创建也 fsync。发现缓存 state.json 不能覆盖明确实例权威；坏 JSON、身份/版本错配、冲突终态失败关闭。
- Agent 预绑定 UDS，监听前设置0660/父目录0750；未知操作、shell/文件请求拒绝。CDP loopback，下载捕获 ACK、真实文件路径约束与断开自动恢复，隧道子任务完整回收，错误不记录私密协议负载。
- Google 首次设置使用现有 context，不另启浏览器；原子 marker 保留用户后续自选搜索引擎。真实 en-US/zh-CN 配置、Bing 跨实例保留与 PID/starttime 不变均有 Docker 测试。
- Xvfb/Openbox 固定完整 UI 尺寸和 DPR1；PulseAudio48000Hz。真实双音录制、同 Profile XShm 成功/跨 IPC BadAccess 与不同 UID 错凭据拒绝组成边界验证。

### TDD、失败归因与修正

- Root 初始核心红灯9失败/5通过；额外2个 ELF/version 红灯、CLI 入口红灯、3个 marker 红灯、Agent 4个异常/3个边界红灯、4个实例 journal 红灯均先保留后修正。路径见 .scratch/t003_root_checks/*red*.log；最终项目单元71通过。
- 下载列表包含 begin 与 completed 两条不可变事实。最初测试按文件名排序选首条，错误把 begin 要求为 completed；实际物理日志已有 completed，故修正新测试量具按真实 GUID 关联终态并校验文件内容/字节数，保留失败日志，不将预期改为 in_progress。
- 完整镜像02暴露 Bash 重复 ID 正则拒绝合法 Profile ID；删除错误重复校验，统一由 Python 在创建目录前验证身份/快照。03 完整镜像前三项已通过；未以源码覆盖旧镜像冒充当前生产镜像验证。
- 独立预审中的「同步 fsync 之间协程抢占」因无 await 撤回；「缺 C fixture」来自审查快照遗漏，正式构建包含该源且成功；「未 export 实例身份」与 entrypoint 实际 export 冲突，不采纳。测试命令从项目根执行，独立预审脚本相对路径错位不当生产缺陷。
- 原预审脚本曾写宿主 /tmp/.X11-unix/X88，已向用户报告并停止该脚本；文件保留，不擅自删除。后续固定 Linux 路径探针只在隔离容器执行。旧 cbrowser:latest 误启容器均按具体 ID 检查后移除；正式服务未切换。以上失败不计 PASS。

## 验证记录

- preflight --require-verified --owner-id root_v2_20261027：PASS。
- 项目 doctor/test 声明命令：169 contract、384 旧后端、71 当前单元 PASS，doctor exit0；日志 .scratch/t003_root_checks/project_doctor_test_03.log。
- Ruff E/F/W/I 和 format：PASS；新代码无警告。活跃改动 git diff --check PASS；s010 不可变归档保留历史字节，不格式化归档。
- 当前完整镜像：sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346，Linux arm64；构建源 manifest 为 .scratch/t003_root_checks/diagnostic_build_03/manifest.json。源码未挂载覆盖，缓存只读。
- Gemini 新生命周期定向4项 PASS：真实 Chrome SIGKILL137、SDK Node driver loss、运行中/终态 Agent 自动重启及 XShm/Pulse 授权。日志 .scratch/t003_e2e_lifecycle/targeted_proof.log。
- 独立初次诊断6项 PASS，144.36秒，原失败及量具修正逐次保留于 validation/.scratch/t003_blackbox/artifacts/diagnostic_run_20261028_123106。量具原 AC002 高度范围/根窗口匹配不足，且顺序杀进程不证明三个独立故障，Root 要求正式轮次改为真实顶层窗口1920×1080及每种故障全新实例；原诊断不当正式 Verify PASS。
- 项目声明完整黑盒 exit0：9项真实 HTTP 集成与13项 Runtime Docker E2E PASS（164.31秒），旧服务健康ok、task list正常；工作副本 repo_sync 未初始化不计配置成功。日志 .scratch/t003_root_checks/project_blackbox_03_final.log。正式独立 Verify Round1 进行中。

## Verify Round1

正式独立候选：上述不可变完整镜像03。独立 Gemini 在 validation worktree 自有 scratch 执行，要求精确 UI 尺寸、三子系统独立失败、Mac 宿主/同网段实际 CDP 隔离、下载完整性和生命周期重放。状态 FAIL：完整六项为4 PASS/2 FAIL，另一次针对2项修正复验仍1 PASS/1 FAIL。原始日志位于 validation/.scratch/t003_blackbox/artifacts/formal_round1_20261028_170554。AC002量具新Profile仍引用profile_geom快照并并发复用同一用户数据目录，触发身份拒绝/Singleton锁；AC005第三实例Socket/数据复用导致缺Socket。Root已按实际源码确认量具问题，生产镜像未变。12497/PID86091在无活动容器时由Root SIGINT退出-2，保留失败，不改标诊断。

## Verify Round2

已派发67930/PID90053，同独立Gemini会话，仅修自有黑盒量具。每种故障必须独立Profile数据、匹配快照、独立事件/Socket和实例，启动失败保留日志/inspect后清理；复验全六项，不放宽1920×1080或真实退出断言。状态 PASS：正式完整六项6 PASS、178.67秒。原始日志及summary位于 validation/.scratch/t003_blackbox/artifacts/formal_round2_20261028_172243。实际Chrome窗口1920×1080、三类故障独立Profile/快照/实例及事件重放均通过。作者90053已持久finishstop并自然退出0；未进入第三轮，limit5不变。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

Full Round1 两路PASS但报告含事实偏差，Root要求纠正并修蓝图Pulse挂载说明。最终 Full Round2 code/test PASS，scope=e934e9a6bcba7ff4，Round2零finding；代码七视角有明确源码锚点。测试 reviewer 实际复验覆盖披露5/6、AC001 trust_prior；全部六项另有独立正式黑盒通过。两路各自独立80测试PASS，未假称独立执行Docker。报告附同轮勘误：新增Runtime52单元+既有19=71，13E2E=8core+5Google，精确测试名、不同UID Pulse边界、条件skip、非物理断电、模式非深度等价和真实时间戳均已纠正。源码/测试/镜像自03保持不变。

## 收尾报告

### 验收与验证

- task：[task.md](task.md)
- 结果：六项AC全部满足；公网/原生x86执行仅两项USER_WAIVED，后续性能/8h/1000输入验收仍必做，不额外豁免。
- 测试：169契约、384旧后端、71当前单元（新增Runtime52、既有19）、9真实HTTP、13真实Docker E2E均PASS；两路review各独立80单元/HTTP PASS。Ruff E/F/W/I+format、Markdown格式、活跃git diff检查及strict preflight通过。
- 黑盒：正式独立Round2/5六项PASS178.67秒，首轮4PASS/2FAIL量具错误与有界修正失败日志保留。实际整镜像03无源码覆盖。
- 附加宿主边界：Root全新实例实测Mac宿主直接HTTP夹具成功，浏览器真实内网CDP端口连接ECONNREFUSED/errno61，容器内部同端口CDP正常且内核仅监听127.0.0.1。证据 .scratch/t003_root_checks/host_boundary/8309a609e5/result.json；前一次仅Python动态导入量具错误，未进入Docker启动，失败日志保留。
- review：Full Round2 code/test PASS，scope=e934e9a6bcba7ff4，零finding，前轮及报告勘误保留；checker overall=PASS/review_scope=ok/round=2。
- AC判定：task.md六项均勾选；specs_index已累计browser_isolation / t003，蓝图/指南同步当前行为。

### 结果摘要

- Browser Runtime独立镜像、受控Agent、真实浏览器生命周期、下载与持久化边界完成。后续t004连接只读Xauthority/X11/Pulse子目录；t005负责容器/缓存初始化与lifecycle/error消费，t008消费下载事实。实际Pro许可、GeoIP外部查询/代理/humanize等全组合与后续媒体性能未在本task宣称实测。
- SDK GeoIP默认路径在统一cache/geoip；t005初始化角色须同时准备/更新需要的GeoIP资产，Runtime只读消费。当前离线E2E显式geoip=False，不能据此宣称GeoIP外部路径通过。
- 精确缓存已复制到主仓 .scratch/v2_orchestration/t003_engine_cache，671文件逐一SHA相等，可供cleanup后集成验证。只含测试引擎，无Profile数据。raw证据备份到主仓 .scratch/v2_orchestration/t003_evidence_before_cleanup.tar.gz；后续finish/单执行commit/exact cleanup/localmain集成按脚本，禁止push/正式部署。t004未start。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

- 累计 spec：browser_isolation。s010 已归档并有 d016，采纳真实退出观察边界；t005 对接 lifecycle/error，不修改本 task API/SQLite。没有其他正式 spike 未闭环。
