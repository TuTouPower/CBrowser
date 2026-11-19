---
tid: "t086"
slug: "disable_engine_fingerprint_noise"
title: "固定引擎默认关闭 Canvas、WebGL 与音频注入噪声"
status: "done"
branch: "t086_disable_engine_fingerprint_noise"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "ca50c816a1c8b35831040f2f533343486831f2ee"
spec_source_sha: "ca50c816a1c8b35831040f2f533343486831f2ee"
depends_on: ""
conflicts_with: ""
note: "来源 p144，真实引擎对照已证实关闭噪声保留种子和平台"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 先运行生产 Runner 的 SDK 参数回归用例，确认缺失受控噪声参数时失败。改动后相关套件 21 passed、2 skipped。
- 候选 Browser 镜像在无外网隔离容器内，使用固定引擎和只读官方字体。真实 Runner 两次共享同一测试 Profile 数据目录启动，Canvas 与离线音频两次都返回准确值，实际进程参数记录 `--fingerprint-noise=false` 正好一次，种子、平台、请求语言和东京时区均匹配。证据为主仓 `.scratch/runtime_identity_acceptance/t086_image_probe.jsonl`。
- 配置漂移、依赖、contract、unit、integration、设计检查、前端测试与前端构建均退出 0。完整 Docker E2E 额外暴露旧夹具字体绑定及命名卷子路径失败，非串行的 14 项失败以旧部署镜像逐个复跑，全部同样失败，跟踪 p145。
- 旧 t068 真实漂移测试以 seed 改变触发 Canvas 噪声，策略变更使这一旧场景失效。整体替换为真实时区输入漂移用例，保留跨上下文、覆盖率与 TLS 门禁验证，断言四种上下文的准确新旧时区值及阻断。候选镜像通过该 E2E。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1

Round 1 零 finding。

### Round 2

Round 2 零 finding，两个 AC 均已独立复验。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：专项 AC 均已验证，全量 Docker E2E 门禁待处理。
- 测试：契约、单元、集成、依赖、协议、设计及前端各套件退出 0。替换后的 t068 E2E 复跑通过。
- 黑盒：候选镜像生产 Runner 两次启动均返回准确像素和音频样本。全量 E2E 首批 14 项失败全部在旧部署镜像复现，已停止剩余串行复跑。夹具缺陷见 p145。
- review：Round 2 PASS，两个 AC 独立复验，零 finding。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 生产 Runner 固定噪声策略，保留种子和地区字段。与 t087 联合验证见主仓 `.scratch/runtime_identity_acceptance/combined_probe_r2.jsonl`。

### 长期文档闭环

- 更新 `docs/specs/engine_upgrade_fingerprint_gate.md` 与 `docs/blueprint/domain.md`。
