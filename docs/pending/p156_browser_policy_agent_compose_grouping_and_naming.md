---
pid: "p156"
slug: "browser_policy_agent_compose_grouping_and_naming"
status: "closed"
resolution: "transferred"
reason: "已核实 Stream 策略与容器分组根因，转交同一 task 验证媒体网络隔离、裁撤 Stream Policy Agent 并按 Profile 归组 Browser Policy Agent"
fix_ref: "t097"
---
# p156 将 Browser Policy Agent 纳入 cbrowser-profiles 分组并规范容器与服务命名

- 来源：用户 2026-11-21 质询与指认。用户对比了 Docker/OrbStack 界面截图：
    - 图 1（外层根列表）：各个 Policy Agent 容器以 `cbrowser-policy-agent-<slot_hash>`（如 `cbrowser-policy-agent-5a5eb283ccff1f7aa543`）游离在最外层，杂乱且无法辨认所属 Profile；
    - 图 2（Compose 项目列表）：Profile 沙箱整齐收敛在 `cbrowser-profiles` 分组下，展开显示为 `0084-browser`、`0084-stream` 等清晰的服务名。
        用户要求：将有用的 Browser Policy Agent 挪入对应的 `cbrowser-profiles` 分组中，且容器名与服务名遵循统一规范格式。
- 内容：
    1. **现状与根因分析**：
        - **缺失 Compose 伪项目标签**：在 `src/backend/cbrowser/supervisor/container_spec.py` 中，`browser` 和 `stream` 容器均打了 `sandbox_compose_labels`（即 `com.docker.compose.project: <prefix>-profiles` 和 `com.docker.compose.service: <NNNN>-<role>`）。而 `policy_agent_labels(...)` 只注入了内部运行时标签（`managed-by`、`role=network-policy-agent`、`profile-id`、`runtime-instance-id`），**完全遗漏了 `com.docker.compose.project` 和 `com.docker.compose.service`**。导致 OrbStack、Docker Desktop 等管理工具无法识别其归属，直接将其散落在外层根容器列表。
        - **容器命名风格脱节**：`docker_adapter.py` 的 `_policy_agent_name` 将容器硬编码命名为 `f"{self.resource_prefix}-policy-agent-{slot}"`（`slot` 为 20 位随机散列摘要，如 `cbrowser-policy-agent-41725af80a92708f1e35`），与 Profile 沙箱的标准命名格式（`cbrowser-<NNNN>-browser`）完全脱节，用户在 CLI 和 GUI 中无法根据名字直接看出是哪一个 Profile 的伴随容器。
    2. **解决方案（规范化与归入分组）**：
        - **容器名称规范化**：
            - 容器命名对齐 Profile 序号标准：由 `cbrowser-policy-agent-<hash>` 改为 `f"{prefix}-{profile_number:04d}-policy-agent"`（或与 Browser 绑定的 `f"{prefix}-{profile_number:04d}-browser-policy"`）。
            - 内部仍可保留 slot 作为 UDS 目录划分以防并发冲突，但 Docker 容器名必须带零填充的 Profile 编号（`<NNNN>`）。
        - **注入 Compose 标签纳入 `cbrowser-profiles`**：
            - 在 `policy_agent_labels` 中补全 Compose 伪项目标签：
                ```python
                "com.docker.compose.project": f"{prefix}-profiles",
                "com.docker.compose.service": f"{profile_number:04d}-policy-agent",
                "com.cbrowser.profile-number": f"{profile_number:04d}",
                ```
            - 使得 OrbStack 与 Docker Desktop 在 `cbrowser-profiles` 下自动将其作为同组 Service 呈现，用户在展开 `cbrowser-profiles` 时能看到：
                - `0086-browser`
                - `0086-stream`
                - `0086-policy-agent`
        - **Supervisor 适配器与孤儿清理同步**：
            - `docker_adapter.py` / `runner.py` 的 Agent 查找、认领、重启接管及孤儿扫描逻辑，同步适配新的容器名称格式与标签体系。
        - **测试缺口补齐**：
            - 在 `tests/unit/test_t050_sandbox_grouping.py` 与 `test_t082_adapter_policy_agents.py` 中补充对 Agent 容器 `com.docker.compose.project`、`com.docker.compose.service` 及 `profile-number` 的断言。
    3. **与 p154 的协同**：
        - p154 负责彻底删除 Stream 推流容器无意义的 Policy Agent；
        - 本条（p156）负责将保留下来的 Browser Policy Agent 规范化命名并归入 `cbrowser-profiles` 分组。
        - 实施后，外层根列表将不再有任何零散游离的 `cbrowser-policy-agent-*` 容器，Docker 界面彻底恢复清晰与整洁。
- 处理：t097；resolution=transferred；reason=已核实 Stream 策略与容器分组根因，转交同一 task 验证媒体网络隔离、裁撤 Stream Policy Agent 并按 Profile 归组 Browser Policy Agent
