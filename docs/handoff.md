# 项目交接记录（最新）

本文件只维护当前有效上下文，历史由 Git 保存。

## 2026-11-17T18:51:04+08:00 模板升级与消费仓对齐

- 当前焦点：模板已对齐 `452c075de2fb54d4d5e846ea84bce61d2c8d7f1f`，收口旧目录、独立评审勘误及门禁适配；全部保留为未提交 diff。
- branch：`main`。
- head_commit：`e0bc8d5faf88e915bb0d0d6055b870d66d02584e`；本轮未创建 commit、未 push，模板源未修改。
- 已完成：74 个 task、112 条 pending、24 个 spike 原位状态模型迁移；38 条 ADR 拆分；19 份 spec 使用 front matter；review 保留最近 5 组；ledger、goal 快照与 sync_state 迁入 Git common dir。独立勘误已并入所属 review 的 `adoption_decision.md`；退役空目录已移除。模板契约 388 passed / 1 skipped，相关项目测试 51 passed，契约计数基线已对齐 389。
- 部署上下文：t074 已合入 main（`012a230`），AC-006 真实部署补验见 `docs/archive/verification/t074_deploy_import_20261117.md`；本轮没有部署操作，未重新核验线上状态。
- 未完成：消费仓全量业务门禁和真实 Docker/Chrome 验证尚未重跑。
- 陷阱：同步事务保持 `applied`，备份在 Git common dir 的 `repo_template/sync_transaction/`；未提交状态不执行 `transaction accept`。旧 task、pending、spike、spec、review 不再归档，不能重建旧目录。部署记录中的回退限制与节点不可达情况未在本轮复验。
- 下一步：按用户明确指令处理现有 diff，不自动提交。8 条 parked pending 保持原位暂搁。
