# bundle_local_specs_blueprint_docs

## responsibilities

- 系统顶层架构规范与长期蓝图（docs/blueprint/：架构、约定、决策、持久化、安全、测试等）
- 现行生效需求规约（docs/specs/，共 17 份已完成 task 累积规约）
- 已验证技术发现（docs/findings/，跨 task 事实记录）与待办总账（docs/pending/）
- UI 设计系统权威规范（DESIGN.md）与根文档（README.md, AGENTS.md, CHANGELOG.md, DOCKER_DEPLOYMENT.md）

## interfaces

- docs/specs_index.md 生效规约清单
- DESIGN.md 设计规范
- README.md / AGENTS.md 架构纲领

## dependencies

- Markdown / GitHub Flavored Markdown
- @google/design.md

## flows

- 规范驱动流：需求提出 -> 拆分 task -> 编写 spec 并在 task 收尾时累积写入 docs/specs/ -> 架构决策沉淀进入 decisions.md

## constraints

- 架构至上，拒绝妥协，零兼容负担
- 单一权威原则：规则与契约仅在一个权威位置完整定义
- 三态划分清晰：严禁未来冒充当前，过时内容须明确替代位置

## decisions

- ADR 001/007: 独立 Docker 双容器沙箱
- ADR 013: 彻底删除 coturn，采用同机直连
- ADR 022: Selkies 升级为 2.2.1
- ADR 023: 单 baseline Alembic 持久化重构
- ADR 024: 平台字体集与镜像解耦只读挂载
- ADR 026: 局域网访问模式

## evidence

- docs/blueprint/architecture.md:5,31
- docs/blueprint/conventions.md:9-13
- docs/blueprint/decisions.md:265-285
- docs/blueprint/security.md:8-19
- README.md:3
- AGENTS.md:3,8

## uncertainties

## Findings

- [Medium][95] README.md:3; AGENTS.md:3,8; docs/specs/v2_runtime_validation.md:17,71 — 核心根文档与生效需求规格遗留陈旧 Selkies 2.1.0 声明，与现行蓝图产生版本架构冲突

    - ID: f_docs_selkies_version_drift; verification: static
    - Evidence: README.md:3, AGENTS.md:3,8 与 docs/specs/v2_runtime_validation.md:17 依然写着 Selkies 2.1.0; docs/blueprint/decisions.md ADR 022 与 architecture.md 已明确声明在 t043 升级为 Selkies 2.2.1
    - Impact: 外部协作者与 Agent 阅读根文档时获取到已废弃的依赖版本，违反单一权威与 ADR 传播一致性
    - Fix: 将上述文件中的 Selkies 2.1.0 统一修正为 Selkies 2.2.1

- [Low][90] docs/blueprint/frontend.md:7,13 — frontend.md 中路由废弃声明与后续自动化页面规格描述存在局部自相矛盾

    - ID: f_docs_frontend_router_contradiction; verification: static
    - Evidence: frontend.md:7 声明 /automation/:profileId 直接删除，但第 13 行仍将 /automation/:profileId 列为自动化页; 代码实现已将其收敛为详情页 Tab 路由 profiles/:profileId/automation
    - Impact: 蓝图内部描述抵触，对前端路由入口形态造成认知歧义
    - Fix: 更正 frontend.md:13 路径为 /profiles/:profileId/automation

- [Low][90] docs/guides/supervisor_validation.md:21; browser_runtime_validation.md:40 — 验证指南中遗留陈旧的 Python 3.12+ 解释器版本要求，滞后于 Python 3.15+ 真实基线

    - ID: f_docs_guides_python_version_drift; verification: static
    - Evidence: 验证指南中描述使用 Python 3.12+，而 conventions.md 与 .mise.toml 强制基准为 Python 3.15+
    - Impact: 指导操作者测试时可能因使用低版本 Python 导致依赖检查失败
    - Fix: 统一更新指南中的解释器版本为 Python 3.15+

- [Low][85] docs/findings/d030_selkies_2_2_1_upgrade_contract.md; d009_turn_hmac_relay_transport.md:11 — docs/findings/ 事实记录状态元数据不规范且部分条目存在三态混淆

    - ID: f_docs_findings_metadata_drift; verification: static
    - Evidence: d030 与 d031 缺少 '- 现状：' 元数据行；d009, d010 等已被 ADR 013 废弃的条目元数据仍标记为有效
    - Impact: 自动化脚本解析元数据时会将已废弃技术事实（coturn）误判为现行有效
    - Fix: 补齐 d030/d031 现状元数据，并将 d009 等更正为已由 ADR 013 替代

- [Low][85] docs/pending/parked/p031_domain_learnings_site_skills.md:49 — 暂搁待办 p031 中引用了已闭环条目的失效相对路径，产生死链

    - ID: f_docs_parked_p031_dead_link; verification: static
    - Evidence: p031 链接了 ../todo/p030\_...，而 p030 等文件已完成并迁移到 docs/archive/pending/
    - Impact: 文档链接断裂，无法直接溯源已闭环的前置条目
    - Fix: 将链接修正为 ../../archive/pending/ 下对应的归档文件

- [Low][80] assets/skills/cbrowser-agent/SKILL.md:22 — Skill 公共执行器规约文档残留内部 task 编号标识符

    - ID: f_docs_skill_task_id_leak; verification: static
    - Evidence: 文档出现 '交 t031 handOff'，直接引用了内部临时 task 编号
    - Impact: 破坏公共 Skill 文档的抽象封装
    - Fix: 更正为指向领域语义 '交由系统真人优先控制权规约处理（见 docs/specs/human_agent_control.md）'

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "agent_specs_blueprint_docs"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "agent_specs_blueprint_docs"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "agent_specs_blueprint_docs"
  },
  "performance": {
    "status": "completed",
    "reviewer": "agent_specs_blueprint_docs"
  },
  "design": {
    "status": "completed",
    "reviewer": "agent_specs_blueprint_docs"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "agent_specs_blueprint_docs"
  },
  "tests": {
    "status": "completed",
    "reviewer": "agent_specs_blueprint_docs"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "agent_specs_blueprint_docs"
  }
}
```

## files_reviewed

```json
[
  "AGENTS.md",
  "CHANGELOG.md",
  "DESIGN.md",
  "DOCKER_DEPLOYMENT.md",
  "README.md",
  "assets/skills/cbrowser-agent/SKILL.md",
  "docs/blueprint/architecture.md",
  "docs/blueprint/artifacts.md",
  "docs/blueprint/automation.md",
  "docs/blueprint/browser_runtime.md",
  "docs/blueprint/conventions.md",
  "docs/blueprint/decisions.md",
  "docs/blueprint/domain.md",
  "docs/blueprint/frontend.md",
  "docs/blueprint/gateway.md",
  "docs/blueprint/persistence.md",
  "docs/blueprint/security.md",
  "docs/blueprint/stream_runtime.md",
  "docs/blueprint/supervisor.md",
  "docs/blueprint/testing.md",
  "docs/findings/d001_v2_validation_baseline.md",
  "docs/findings/d002_cdp_uds_download_recovery.md",
  "docs/findings/d003_selkies_ice_restart_gap.md",
  "docs/findings/d004_docker_shareable_ipc_contract.md",
  "docs/findings/d005_encoded_fps_is_not_motion.md",
  "docs/findings/d006_runtime_event_recovery_checkpoint.md",
  "docs/findings/d007_multi_viewer_media_identity.md",
  "docs/findings/d008_gateway_process_media_recovery.md",
  "docs/findings/d009_turn_hmac_relay_transport.md",
  "docs/findings/d010_ice_generation_continuity.md",
  "docs/findings/d011_profile_ipc_audio_boundary.md",
  "docs/findings/d012_turn_generation_media_commit.md",
  "docs/findings/d013_capture_visibility_arbiter.md",
  "docs/findings/d014_native_ime_commit_path.md",
  "docs/findings/d015_sql_error_log_boundary.md",
  "docs/findings/d016_sdk_owner_lifecycle_boundary.md",
  "docs/findings/d017_native_xkb_named_spares.md",
  "docs/findings/d018_selkies_native_peer_entry.md",
  "docs/findings/d019_turn_loopback_mapping.md",
  "docs/findings/d020_orbstack_bridge_reachability.md",
  "docs/findings/d021_selkies_ice_restart_commit_is_async.md",
  "docs/findings/d022_selkies_rtc_config_url_contract.md",
  "docs/findings/d023_headless_chrome_visibility_static.md",
  "docs/findings/d024_selkies_token_secure_mode.md",
  "docs/findings/d025_selkies_resume_grace.md",
  "docs/findings/d026_direct_media_local_only.md",
  "docs/findings/d027_af_unix_sun_path_length_limit.md",
  "docs/findings/d028_iframe_focus_shortcut_isolation.md",
  "docs/findings/d029_docker_fixed_endpoint_ip_range_reservation.md",
  "docs/findings/d030_selkies_2_2_1_upgrade_contract.md",
  "docs/findings/d031_authenticated_socks5_supported.md",
  "docs/findings/d032_ua_ch_architecture_no_engine_switch.md",
  "docs/findings/d033_platform_font_sets_isolation.md",
  "docs/findings/d034_design_system_toolchain_versions.md",
  "docs/findings/d035_cdp_active_tab_capture_screenshot.md",
  "docs/findings/d036_lan_access_and_edge_rebuild.md",
  "docs/guides/browser_isolation_analysis.md",
  "docs/guides/browser_runtime_validation.md",
  "docs/guides/stream_runtime_validation.md",
  "docs/guides/supervisor_validation.md",
  "docs/handoff.md",
  "docs/pending/parked/p031_domain_learnings_site_skills.md",
  "docs/pending/parked/p038_builtin_mihomo_proxy_nodes.md",
  "docs/pending/parked/p039_split_screen_multi_session_grid.md",
  "docs/pending/parked/p040_proxy_connectivity_exit_ip_check.md",
  "docs/pending/parked/p041_standalone_desktop_app.md",
  "docs/pending/parked/p043_chrome_profile_import_binding.md",
  "docs/pending/parked/p045_windows_ua_ch_architecture_alignment.md",
  "docs/plan_20261105_ui_redesign.md",
  "docs/plan_v2_architecture_.md",
  "docs/specs/access_control.md",
  "docs/specs/agent_executor.md",
  "docs/specs/automation_compatibility.md",
  "docs/specs/browser_isolation.md",
  "docs/specs/fingerprint_platform.md",
  "docs/specs/gate_verification.md",
  "docs/specs/human_agent_control.md",
  "docs/specs/profile_management.md",
  "docs/specs/profile_preview.md",
  "docs/specs/proxy_management.md",
  "docs/specs/release_deployment.md",
  "docs/specs/runtime_lifecycle.md",
  "docs/specs/runtime_persistence.md",
  "docs/specs/storage_and_artifacts.md",
  "docs/specs/ui_design_system.md",
  "docs/specs/v2_runtime_validation.md",
  "docs/specs/webrtc_remote_display.md",
  "docs/specs_index.md",
  "docs/tasks_index.json"
]
```
