# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-02T08:30:13+08:00 基线改动已合入main，工作区已清理，下一步t008

### 最新用户指令与执行边界

- 用户要求整理全部 worktree/diff：有用改动合入main，无用副本删除；停止过度测试，做好t008开工准备。
- 随后明确“两项失败不用管，现在收尾更新handoff”。两处测试清理失败保留事实，暂不处理、不阻塞t008；不得继续修夹具、复跑全库或扩大lint范围。
- 这不是最终验收通过，也没有豁免t008四项AC。实现阶段只做与当前改动直接相关的必要验证；整体验收、容量/P95、8小时、1000次IME/clipboard仍属t009。
- 完整目标此前已暂停；本轮只完成清理和交接，未恢复任务队列、未start t008。未push、未部署、未改生产数据或secret。

### 当前权威状态

- branch main；head_commit `28f630cd1f7fc844ddbf1e4e61e00a3fea692865`（本文单独提交）。
- 基线执行提交 `18f1d6d`：137文件，采用已审查汇总候选R8；合并提交 `28f630c`。采纳文件在合并时逐字节核对一致，无冲突；本轮只做diff/静态一致性核对，没有重跑测试。
- 仅main分支、主worktree；以下七个worktree均已规范remove/prune：baseline_core_review、baseline_fix、baseline_fixture_review、baseline_fixtures、baseline_validation、normal_exit_fix、visibility_ports_fix。三个临时fix分支已删除。
- t001–t007 done/integrated；冻结后续顺序 t008 → t013 → t014 → t009 → t010 → t011 → t012 不变。当前t008 backlog，无attempt、无执行身份；task.py ps无在飞task。
- main是唯一开发基线。留档旧diff仅供追溯，禁止整包重新应用、恢复旧worktree或重复采纳adoption。

### 清理与证据位置

- 统一留档：`.scratch/pre_t008_archive_20261102/`，约8.1MB。含七个完整binary patch、inventory.json、清理回执、worktree_evidence.tar.gz（121份文件）、baseline_test_evidence.tar.gz（336份测试证据）。
- 未采用末轮两个测试文件的清理修补：未完成独立验证，且新引用控制器变量存在早期失败路径风险；原始内容保留在normal_exit_fix整包diff及报告中，不代表待自动采纳。
- 七工作区scratch先迁移备份，提取有效证据后删除再生缓存/临时副本；本轮基线84组生成目录已删除。`.scratch/v2_baseline_20261101/`从约79GB降至774MB，保留原始日志、镜像清单、审计、调度记录及可复用OpenCode runtime。
- 用户点名的 `/Users/karson/kar/code/.scratch` 中八个CBrowser临时目录已全部删除，父目录已移除。其它项目、正式data和用户凭据未动。
- 主仓 `.scratch/v2_orchestration/` 的编排工具、已初始化Linux engine/GeoIP缓存，以及 `.scratch/project_gates/` 的依赖缓存继续保留，供t008使用；不再次复制出多套缓存。
- 当前按com.cbrowser.prefix标签查询无测试容器残留。没有新启动任何测试进程。

### 已有测试事实与两处暂不处理失败

- 最新完整门禁记录 `.scratch/v2_baseline_20261101/final_round1/results.json`：66步中65步通过。六镜像构建、四入口import、契约169、unit445、integration66、legacy384、Vitest112、前端build/vendor/verify、schema/codegen零漂移、完整Ruff、文档格式及健康检查通过；42个E2E模块中41个模块通过。
- 失败一：runtime_coordinator E2E所有业务断言完成后，finally与仍活着的Supervisor并发删除Browser/Stream，真实Docker返回409 removal already in progress。透明调用证据在focused_runtime_coordinator_probe_r1/docker_calls.jsonl；最终无容器残留。
- 失败二：后续R8容器图复跑业务断言完成，finally报network_not_empty，留下一个本profile Browser及其网络。清理时控制器尚活，存在恢复/清理竞争；具体是否在枚举后重建属于推断，未声称完整事件时序已证明。两对象已核对归属、保存证据后精确清除。记录focused_container_graph_r8/。
- 用户明确要求两项暂不处理，后续不得因此再启动补修长循环。不得把完整门禁写成全绿。
- unit曾有一条Python3.14 asyncio析构警告；debug及警告转错误复跑40/445均通过，未复现。保留记录，不宣称已定位或修复。

### t008开工准备与入口

- `task.py preflight t008 --allow-backlog` 本轮只读PASS，带一项通用UNVERIFIED-SPIKE提示；无外部账号、密钥或平台缺口。它是执行期契约核对项，不是再次补跑全局门禁的理由。
- 首先读取现有 `docs/tasks/t008_v2_artifacts_automation/task.md`、note.md及本节，再按现有task流程登记执行身份与隔离worktree；不新建task、不改冻结队列。
- d002已验证真实CDP-over-UDS、下载与外部客户端断开后恢复的可行性。先复用 `docs/findings/d002_cdp_uds_download_recovery.md` 及现有实现核对通用SPIKE提示，仅补正式接入缺口，不重复全套原型研究。
- AC-001：Artifact上传/下载/删除、文件名/MIME/配额/磁盘与路径隔离，返回`/exchange/...`容器路径，完成files页面。
- AC-002：独立automation token认证入口 → Supervisor → Agent UDS → loopback CDP双向代理；断开恢复下载捕获，完成automation页面。
- AC-003：显式关闭Selkies会话内文件传输，验证不能绕过Artifact Service。
- AC-004：Agent启动/CDP重建时下载目录对账，排除临时文件并按路径/校验和去重。
- 可复用入口：domain/models.py的Artifact、adapters/database/models.py的ArtifactModel；auth/service.py的authorize_automation与既有token管理；runtime_agent/agent.py的`/cdp`、`/events/downloads`和cdp_proxy.py；Supervisor已有UDS健康访问路径。
- 待接通：Artifact Service/Repository/API、下载事件正式入库、Supervisor CDP转发、两个前端placeholder。旧src/backend/artifacts.py、downloads.py仅参考已有文件/下载规则，不恢复旧浏览器生命周期。
- 前端入口：`src/frontend/src/features/artifacts/ProfileFilesPlaceholder.tsx`、`features/automation/ProfileAutomationPlaceholder.tsx`、`app/router.tsx`；API契约变更按现有schema/codegen链同步。
- artifacts.md、automation.md两个blueprint尚不存在，实施时按实际完成行为新增。现有task finalization段落残留剪贴板/复制重置文案，实施时纠正归属：t008不承担t013/t014范围。
- 下一步就是既有t008开工，不再开基线补修、全库lint或无关测试工程。
