# 需求规范：Runtime 生命周期协调

本文描述 t005 实现行为，运行意愿协调由 t007 补充。入口鉴权、正式 Gateway、最终 Compose 与用户数据迁移仍由后续 task 交付；生效状态以 specs_index 和最终 task 验收为准。

## 权限与隔离

- API 是唯一 SQLite 写入者。Supervisor 经内部 Bearer RPC 获取不可变配置、绑定实例、上报观测和持久事件，不挂载数据库。只有 Supervisor 持有 Docker Socket。
- 每个 Profile 独立 Browser/Stream 容器、用户数据、Xauthority、Pulse 与网络；Stream 仅共享对应 Browser IPC，不挂用户数据或 Browser Agent Socket。挂载必须规范化并保持所属 Profile，路径穿越、链接逃逸和跨 Profile 别名被拒绝。
- Runtime 保持非 root、只读根、cap-drop ALL、restart policy no。启动前由临时 helper 在自有网络命名空间安装 IPv4/IPv6 策略，gate 确认实例、角色与 ready 标记后才执行业务入口。失败封闭，不修改宿主网络策略。
- Browser 公共目的地址可达，私有/保留地址默认拒绝，代理只按配置地址/端口例外；Stream 只允许实际 Gateway 端点、本实例 UDP mux 与显式白名单，并允许同机直连所需的已建立流量；私有/保留地址仍默认拒绝。独立 bridge 本身不构成隔离证明。

## 运行意愿协调

- 用户只经 `/api/v1` 设置运行意愿；API 持久化后经内部认证 RPC 驱动 Supervisor 真实启动/停止该 Profile 的 Browser/Stream，前端与测试不直调 Supervisor。
- Supervisor 不可达时运行意愿保留，错误经 API 响应与 SSE 显式报告；恢复后按退避重试收敛并清除错误。API 重启时对意愿与观测不一致的 Profile 重新收敛。
- 未配置 Supervisor 时 API 默认显式禁用协调并报告；`CBROWSER_REQUIRE_SUPERVISOR=1` 时缺失配置拒绝启动，生产部署必须启用。

## 生命周期与代际

- API 已记录 running 意愿后，Supervisor 读取指定不可变版本启动实例；配置失败不能猜默认值。Profile 锁串行生命周期请求，相同已运行实例启动返回现有会话。
- UDP mux 端口池为 30000–30991，Profile 独立分配且内外一致。耗尽返回明确错误；已绑定但尚未获得端口的实例通过稳定启动失败事件收敛，不释放其他 Profile 端口。
- Browser 就绪要求 Profile、实例、配置版本、真实 PID 和运行通道均匹配；Stream 必须完成 Gateway 注册后才报告 running。旧就绪文件不能让新实例提前成功。
- 停止携带 operation_id 和 runtime_instance_id。相同请求可重放，相同操作 ID 配不同请求冲突；旧代停止不终止新代。依次标记不可用、等待 Viewer 断开确认、停止 Stream、停止 Browser、删除所属网络，确认释放后回收端口。
- 重建 Browser 前先移除旧自有容器，再清理 Chromium singleton 锁链接。只移除已终止实例的临时入口，不跟随链接修改用户文件。

## 故障与恢复

- Native 事件按所属目录、Profile、实例与配置代际验证，落入持久 spool；API 按 event_id 去重和实例 fence 消费。正常退出清除运行意愿；异常退出保留意愿并累计实际失败数。
- 首次异常后按 2/10/30 秒各重试一次，三次重试均失败后 failure_count=4 并阻断。期限从 API 持久时间计算，Supervisor 重启不重新开始完整等待；失败计数和阻断仅以 API 为权威。
- 手动重试经 API 幂等事务解除阻断；旧手动操作重放不能绕过后来形成的新阻断。手动意愿变化可取消等待中的旧重试，不取消已经进入 Docker 创建的工作。
- API 离线、认证失败或 Docker 扫描失败时保留健康容器。Supervisor SIGKILL 重启后核对意愿、代际、策略 gate、实际端口与注册状态接管，正常停服不终止健康 Runtime。
- 已绑定实例但无对应 Browser 时，使用稳定 missing_runtime 事件收敛并进入正常退避；活跃 Profile 锁期间不合成退出。created/paused/restarting 不视为已退出。
- 已读取的 Native 退出事件即使首次上传失败，也优先于 Docker/missing 合成事件，防止正常退出被误记异常并重启。
- 启动独占锁内回收严格匹配归属的 cache-init/network-policy helper。周期扫描不回收临时 helper；网络清理遇未知端点失败，不强制断开其他对象。

## 资源策略

Supervisor 聚合实际主机与容器 CPU 窗口，按最紧 cgroup/cpuset 预算计算压力，结合真实前台可见性下发 Profile 级 FPS cap。缺失或失败样本不能当低负载，单个 Profile 采样或 RPC 失败不阻断其他 Profile；解除限制后由 Stream 活动策略决定恢复 8/30 FPS。全后台不误触发前台 cap，Viewer 心跳不建立控制租约。

## 验证边界

验证分为单元/真实 HTTP、独立 Supervisor 与 API 进程、完整 Docker 容器图、网络内核正负对照、CPU 采样和官方 Chrome 实际帧数。各层证据不互相替代。完整部署和容量/P95/8小时/1000次输入验收仍按架构计划后续阶段执行；公网与原生 Linux x86_64 仅两项记为 USER_WAIVED。
