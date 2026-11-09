# p054 DS 审阅采纳意见汇总（个人单机版：无安全加固、无兼容包袱）

- 来源：DeepSeek V4.1 Flash 审阅报告（63 commits 未 push）+ 独立评审裁决；用户约束：个人用、无安全需求，架构铁律（根因重构、破坏性变更可、零兼容）。
- 内容：本条为采纳项总清单，按此实施。不在清单的即不办：P1-4/P1-5（LAN，见 parked p053）、全部安全纵深项（P2-3.1-8、P2-3.2-1、P2-3.2-2、P1-10(b) symlink 加固、D-1 端口白名单、D-4 会话粒度）、P2-3.1-9 grace 变更（接受现状）、P1-7(a) 兼容方案（跨代回退已确认删除，见下）。
- 处理：已落地（main b034b44；P0/P1 分 6 路 worktree 并发实施逐点合入，P2 分 2 路合入，receipt 测试 fix-forward 补齐；LAN 见 parked p053；跨代回退已删）

## P0（必修）

- **P0-1 网络 apply 跨容器路径不一致**：协议改只传逻辑资源名（如 `Caddyfile.staging.<op>`），Supervisor 按自身 `data_root/"network"` 解析 + basename/包含校验；API 不再传容器绝对路径。破坏性改协议，无双版本兼容。同时解决补偿删健康 Caddy。证据：`compose.yaml:26 vs :103`、`api/app.py:254`、`network_service.py:379-387`、`control_server.py:604-627`、`docker_adapter.py:2059-2061`。
- **P0-2 0001 被就地加列**：恢复 0001 不可变，新增 0004 用 `batch_alter_table` 补 4 列（`capture_preview_epoch` NOT NULL 需 default 回填）；加"0002 → head"升级测试（现有只测空库 `test_control_migration.py:79-86`）。

## P1 网络/部署（必修）

- **P1-1 Caddy 未重建仍提交**：`core.py:2969-2974` 显式校验 `rebuilt is True` 方可 commit；`restore_edge_proxy` 同理校验；测试替身补 `rebuilt:false/restore_old_entry` 形状（`test_network_apply_operations.py:42`、`test_a35_recovery.py:46-52`）。
- **P1-2 成功后绑定 staging**：成功 apply 后 Caddy 必须挂持久 `network/Caddyfile`（首次即挂持久路径或 finalize 后二次 rebuild）；`_finalize_commit`（`network_service.py:456-473`）不得只写盘不重指。
- **P1-3 启动恢复过早**：恢复移到 Gateway/Supervisor 就绪后（后台重试），失败不清永久 409（`repository.py:1554-1569` 的 `recovery_complete=False` 死锁须有出路）。
- **P1-6 443 Origin 自锁**：白名单生成归一化默认端口（`network_config.py:49-57`），一行。
- **P1-8 baseline 断言**：`deploy_v2.sh:159-196` 改与 revision 链/祖先比较；与 P0-2 同批。跨代回退：预检显式拒绝（目标 head 与当前 DB 跨代 → 报错重建数据目录），文档写明不支持，不做 `ALLOWED_ORIGINS` 兼容。

## P1 预览（只修功能）

- **P1-9 协议错位 + 0600**：Supervisor → Agent 改包 `{"action":"preview_policy","params":{enabled,epoch,…}}`（破坏性改，无兼容）；写 policy 后 chown uid 1000。证据：`core.py:2030-2036`、`protocol.py:59-71`、`agent.py:517-520`、`preview.py:41-49`。
- **P1-10(a) 读侧 DB 权威**：`preview_router.py:39-42` 采用 `policy_row[0]`（enabled），DB 关闭即 404，不再只信文件 `policy.enabled`。(b) symlink `O_NOFOLLOW`/移目录不做。

## P1 前端（必修）

- **P1-11**：runtime 从非 running 进入 running 时推进 stage/触发 reload；terminal 守卫不拦 `hasFrames` 恢复；Apply/Stop 后主动 reconnect。
- **P1-12**：保存成功先用 mutation 返回值写缓存再 `formKey+1` remount。
- **P1-13**：创建成 + 启动败必须提示已创建 id；按钮加 pending 禁用防双击重复创建。

## P1-14 门禁（精简修）

- `run_gates.sh`：`uv venv --clear`、证据模式逐 suite TSV 存在性校验（缺失即 fail，不 fail-open）、Selkies wheel 缓存纳入前置、`run_automation_probe.sh` bash3.2 空数组修复。cleanup 跨会话误删不做（无并发门禁）。

## P2 顺手小项（低优先级，可同批）

- TOCTOU 版本比对（`network_service.py:226-276` + `repository.py:1541-1586`）、generation 种子随 applied 重建、`PortAllocationBlockedError` → 503 映射、`converge` 失败阻断 commit、回执落盘时序（`docker_verified` 语义）、`lan_advertised_ip` validator 内 strip、预览 tmp 清理（`preview.py:41-49` finally）、并发 PATCH 同 epoch 窗口（profile 锁内写）、回退祖先比较（随 P1-8）、Root CA/热重载/指纹/handoff/编号文档批、前端 P2（空状态、确认框、裸 `<a>`、选中集、pending）批、测试批（xdist 非法值、exit-5 非零路径、E2E guard 补 `0.0.0.0:`/单占位）。

## 验证门槛（push 前）

真实跨容器 apply E2E（现有全 mock）、旧 DB（0001/0002）升级测试、Caddy 重启后可用验证。
