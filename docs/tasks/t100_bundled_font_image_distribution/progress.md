---
tid: "t100"
slug: "bundled_font_image_distribution"
title: "源码构建与预构建镜像自动交付平台字体"
status: "done"
branch: "t100_bundled_font_image_distribution"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "3555c8d12110748ecb42843a8d915eb23d6ca53f"
spec_source_sha: "3555c8d12110748ecb42843a8d915eb23d6ca53f"
depends_on: ""
conflicts_with: ""
note: ""
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 实现本地镜像构建、digest 拉取、从固定 Git 树原子打包安装器、浏览器镜像字体导入与 Caddy 镜像托管前端。
- 使用真实压缩包通过空 Docker 卷导入，包括 Windows 143 个和 macOS 371 个字体文件，第二次导入复用现有集合。缓存基镜像组成的隔离部署打开管理页，API 报告两套字体 verified，新建 Profile 分别绑定对应字体。
- 生产 Dockerfile 实构建在 Docker Hub 取 Node 与 Python 底图时超时。隔离 Profile 启动先遇到冷引擎初始化超时，复用已校验缓存后进入容器创建，Stream 绑定 UDP 30000 与正在使用的既有实例冲突。已停止隔离实例。Viewer 未验。
- 字体锁含两套现有字体的摘要，URL 待确定获准公开访问的发布源。实际字体包、镜像和安装包未对公网发布。
- 独立只读预审已处理字体锁提前核对、安装包固定及原子写入、前端构建上下文包含 DESIGN.md。正式 review 待关键黑盒通过后执行。

### Attempt 2

- Browser 通过清华 Debian 与安全更新镜像完成构建。镜像内保留 Debian 签名、哈希校验。Caddy 从 Node.js 官方下载固定版本及 SHA-256 的二进制，绕开容器仓库限流。Stream 原 Debian 路径也出现 502，构建入口复用其现有镜像参数切到清华源。
- 六个正式 ARM64 镜像构建成功。隔离空卷由镜像导入 Windows 143 个、macOS 371 个字体文件并获 API 接管。引擎代理仅转交下载辅助容器，冷下载得到并验证 146.0.7680.177.3。两平台 Profile 运行、Google Chrome 通过 WebRTC 以 960×540 解码动态画面。证据在 `.scratch/t100_attempt2/`。
- 首轮全量 E2E 与现行实例占用 UDP 30000 冲突。改用隔离端口后，契约、后端单元/集成、前端测试和构建、设计检查、协议/依赖漂移检查、运行镜像依赖校验全部退出 0。E2E 第一阶段 44 通过、2 跳过，第二阶段 16 通过后按用户指示中止，整套 E2E 未完成。目标 Viewer 输入用例单独通过。
- 人工 Viewer 新标签页补验触发 Chrome 剪贴板权限提示；重连和键盘补验按用户指示停止。既有启动、画面和目标输入用例证据保留。
- 用户改为停止继续测试，完成部署手册、正式 review 后提交并发布。公网资产和镜像尚未上传。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-21T17:13:21+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t100_code_f001|important|已修|默认保留清华 Debian 源，允许换源，遵循 Docker 代理及显式 NO_PROXY|`scripts/build_images.sh`|
|t100_code_f002|important|已修|部署在变更数据及启动服务前检查 Caddy 镜像内的前端入口|`scripts/deploy.sh`|
|t100_code_f003|important|已修|要求锁覆盖两平台并验证两个内容 ID|`scripts/font_bundle.py`|
|t100_code_f004|minor|已修|打包命令使用可直接替换的变量和示例文件名|`DOCKER_DEPLOYMENT.md`|
|t100_code_f005|minor|已修|说明源码仓、镜像内压缩制品及运行时卷的边界|`docs/specs/fingerprint_platform.md`|
|t100_test_f001|important|已修|专项指南使用统一构建入口，并从清单取 Browser 镜像 ID|`docs/guides/browser_runtime_validation.md`|

### Round 2

Round 2 零 finding，R1 已修项均经复核。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：六个 ARM64 正式镜像构建及两平台 Profile 冷启动、Viewer 出画通过，正式 review 依据已有证据。
- 测试：隔离端口 E2E 的前置门禁全部通过；E2E 共记录 60 通过、2 跳过，第二阶段按用户指示中止。目标 Viewer 输入用例单独通过。
- 黑盒：本地锁定字体包正常构建。冷部署据安装记录自动导入两套字体，无缓存引擎从上游下载并校验，两台 Profile 的 Viewer 均收到 WebRTC 动态画面。已实际重复导入同一字体包，部署重复执行及数据库保留由既有回归用例核对；未重复运行实机部署。
- review：已处理 R1 findings，R2 代码与测试证据静态复审均 PASS。R1 后新增的回归用例未执行。按复审反馈校正引擎缓存卷说明。公网字体地址和 GHCR 下载路径将在实际发布时核对。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 部署手册提供源码构建、预构建部署、密码文件、引擎下载代理、升级、回退、停机和发布操作，随安装包交付。
- R1 修订后的六个 Linux ARM64 镜像已重新构建，清单及日志位于 `.scratch/t100_attempt2/reviewed_images.json` 和 `.scratch/t100_attempt2/build_reviewed.log`。

### 长期文档闭环

在 active spec 的 front matter `tasks` 清单中登记当前 tid（`task.py specs list --json`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
