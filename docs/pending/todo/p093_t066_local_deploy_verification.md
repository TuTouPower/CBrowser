# p093 t066 合入后本地真实部署补验（[deploy] AC 切片）

- 来源：t066 遗留（云端无 Docker，[deploy] AC 的真实部署切片无法执行；云端可验部分已由单测、恢复点工具故障注入测试与真实引擎 spike 验足）
- 内容：t066 在云端 finish 后，下列事项只能在带 Docker 的本地环境（Mac）随终局合入补跑并留证：
    1. AC-001 [deploy]：隔离实例中给运行过的 Profile 预置 Cookie/localStorage/IndexedDB/书签，逐项修改代理、分辨率、时区、语言、指纹参数并保存、重启，验证状态目录内容不变、身份参数与实际引擎一致。
    2. AC-003 [deploy]：真实引擎两态 clone 往返——仅配置 clone 无状态可用、带状态 clone 的 Cookie/登录态在新 Profile 实际打开站点可用，源 Profile 不受影响（云端 spike 已证引擎无 OSCrypt 密钥根锚定，本地复核同一结论）。
    3. AC-004 [deploy]：真实 Profile 确认 reset 后书签/历史/偏好/Cookie/登录态/存储/缓存全清、配置与独立 Artifact 保留；人为注入目录替换失败时旧目录与配置成套恢复。
    4. AC-005 [deploy]：启动与 clone/reset/备份恢复交错的真实拓扑验证（含残留 runtime 实例绑定时拒绝、viewer 连接不触发停止或清理）。
    5. AC-011 [deploy]：隔离实例执行 `deploy.sh env-backup` → 改状态 → `deploy.sh env-restore` 完整往返，验证配置、登录态恢复到恢复点，凭据前提清单所列文件齐备时服务正常启动；确认指南命令能从 named volume 取得并恢复 DB。
    6. findings 补录：findings.py 在 main 上因既存 d037/d038 编号重复拒绝分配新号（工具链缺陷，与 t068 报告同源）；编号冲突解决后，把 t066 task.md 已回填的两条 spike 结论（引擎 Cookie 密钥根、db_restore 无校验直覆）正式登记为 findings 条目。
- 处理：未开
