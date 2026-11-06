# p048 门禁被中止时残留 E2E 容器污染下一轮

- 来源：t037 门禁 v6→v7 退化暴露的门禁基础设施缺陷（技术债自查，需从根因修）。
- 内容：`scripts/run_gates.sh` 的 E2E 拓扑由各测试 fixture 创建容器/网络（前缀 `t007-*` / `t006-*` / `t005-*` / `cbrowser-t003-*` 等）。当门禁被 SIGTERM 中止（如 v6 因 integration stub 未同步而被主动停止）时，pytest fixture 的 teardown 不执行，整套 E2E 容器仍 Up 并占用宿主 UDP 30000 等端口；下一轮门禁（v7）启动时 `POST /supervisor/v1/profiles/start` 全部报 `Bind for 127.0.0.1:30000 failed: port is already allocated`，导致 19 failures + 4 errors、白跑一轮 25 分钟。t044 AC-003「suite 结束无残留」只覆盖正常收尾，未覆盖中断路径。
- 已知证据：t037 v7 门禁 `.scratch/t037_evidence_v7/logs/e2e.log` 多处 `Bind for 127.0.0.1:30000 failed: port is already allocated`；`docker ps -a` 显示 v6 残留 `t007-fe-e2e-615f6240-*` 一整套容器 Up 29 分钟；人工按测试前缀清理 7 容器 4 网络后端口释放。主仓部署 `cbrowser-supervisor/gateway/api/caddy` 4 容器必须保留，不得误删；其它会话的容器也不得触碰。
- 要求修复（收尾阶段用户裁决后）：
    1. 门禁**启动时**检测并清理上一轮遗留的测试前缀容器与网络（按明确前缀白名单，精确匹配，绝不污染生产部署或其它会话资源）。
    2. 对 SIGTERM/SIGINT/EXIT 做 trap 清理，保证中断时也执行同一套前缀清理。
    3. 清理逻辑复用现有 `cleanup_prefixed_resources` 之类 helper（若有），并补一条单测覆盖「残留容器存在时门禁启动清理」「非测试前缀容器不被删除」。
- 处理：待收尾阶段从根因修；本轮 t037 只在门禁前人工清理残留以保证 v8 证据干净。
