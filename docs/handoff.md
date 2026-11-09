# 项目交接记录（最新）

## 2026-11-09T18:21:05+08:00 DS 复审轮复修合入主干：P0-A/P1-A~F 及 P2 批

### 状态与工作区

- branch `main`；交出时 head_commit `1ff4721`（本地领先 origin/main，未 push）。
- `docs/pending/todo/`：p054（DS 采纳清单，复审轮追加已合入）；`docs/pending/parked/`：p053（LAN 暂搁）。
- 主仓工作区干净，所有临时 worktree 已规范清理，无未暂存改动；`config/deploy/` 未跟踪、未动。

### 本轮结果（均已验证）

- **P0-A**：0004 幂等（inspector 查列）+ 1a6ec51 形态（0002 stamp + 四列已存在）回归测试 + data/v2 副本真实升级验证（stamp `c41f`→head，行保留）。
- **P1-A/B**：journal generation 纳入命令身份 + bump 后 txn 统一 + restore 失败→成功测试；持久 Caddyfile 原子写 + 属主；P2 恢复批（DB 异常重试、not_found 终局、fencing/超时、converge 回滚、TOCTOU 比 hash、whitelist 归一化、旧 hash 校验、回执真实语义）。
- **P1-C/D**：rollback 比对当前 DB stamp（target==stamp 否则拒绝，含跨代旧 release）+ compose_sha 混用拒绝 + 三文档同步；supervisor schema 重生成；router.test 两步确认；门禁 P2 批。
- **P2 预览**：chown 先于 replace、dispatch 失败保留 pending、request_id 成功后记、锁内写 policy、同值重试收敛、RPC 移出锁。
- **P1-E/F + 前端 P2**：可恢复 terminal 采样、starting 走 connecting、跨 Profile 重置、重试启动、确认框/错误态/i18n/裸 Link 批 + 新增 hook/对话框测试。
- **门禁状态**：完整门禁待复跑确认；openapi 描述漂移（app.py）已对齐 checked-in JSON。

### 下一步

1. 跑完整 `scripts/run_gates.sh` 确认全绿后再议 push。
2. push 前门槛（复审建议）：旧库副本升级 + 真实跨容器 apply + Caddy 重启后可用三类验证。
3. 遵守用户约束：禁止 push/force-push，不动 remote。
