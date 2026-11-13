# p080 Profile 状态备份、快照护栏与双层配额

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P1-7），借鉴 Chromium User Data、Browserbase Contexts、Steel Profiles、SealSkin `quota.py`
- 内容：本地实读 `README.md:33-36` 运行中 `tar -czf data/instance` 未先停容器，可能命中 SQLite WAL torn snapshot；Profile 快照与配额缺护栏。目标：备份改「先优雅停止 → SQLite Online Backup（或 `VACUUM INTO`）→ stage-then-swap（`.staged-*` 两次 rename）→ 恢复时校验」；Profile 快照 = 完整 userDataDir，显式 `persist` 才写回、写回在 session close 且需等待同步、**禁止同一 Profile 多会话并发写**；快照设大小上限与闲置过期；双层配额（单 Profile 与总量，switch 取最严、limit 取最小）覆盖 session/storage/time。本次为只读调研，未授权改生产代码；涉及持久化契约与数据迁移，需备份验证可恢复后由专项 task 实施。
- 处理：t066；resolution=transferred；reason=已核实当前代码与有效 task，按同一交付面聚合转交 t066；过时描述与剩余范围见 task spec，归档仅表示转办
- 时间：2026-11-13T19:16:54+08:00
- 关联：p016（archive，配额 E2E）、p054（archive，备份/回执时序）、p071（todo，控制面 legacy 兼容残留）、p074（原子身份 bundle 与快照版本绑定）、p089（clone/reset 语义）

## 前置与风险

- 破坏性变更：迁移前验证备份可恢复、回退路径可用；按零兼容性负担直接定稿契约，不留旧格式兼容层。
- 删除即擦除在 COW/SSD/TRIM 上不成立，不要写成已保证。
- 单 Profile 多会话并发写会破坏快照一致性，须由控制面显式拒绝。

## 验收

1. 运行中备份改为停机一致性快照；恢复后 Profile cookie/localStorage/登录态完整且可校验。
2. stage-then-swap 中途失败不留下半写状态，旧版本可回退。
3. 单/总双层配额生效，超限会话被拒且有可观测归因。
