---
pid: "p112"
slug: "t074_deploy_proxy_probe_e2e"
status: "closed"
resolution: "transferred"
reason: "用户裁决归档：AC-006 [deploy] 真实部署端到端仍 NOT_RUN/USER_WAIVED、本会话未验证、不冒充闭环"
---
# p112 t074 真实部署下的代理测速与设置弹窗端到端补验

- 来源：t074 遗留（AC-006 `[deploy]`）
- 内容：t074 已交付 settings API / 0010 迁移 / 轻量准确延迟 / 国家城市观测 / 代理列表与筛选持久化，并通过全量门禁、s023 真实代理出口 GeoIP 实测与 s024 真实 Docker 容器原型实测。AC-006 要求的「真实部署端到端」仍未验：需在宿主 Docker/OrbStack 重部署后，用真实可用与不可用代理实测单条及批量测速，核对毫秒级延迟、准确国家与城市、红色失败原因、刷新后持久化保留，并复验容器网络隔离与私有/保留地址阻断边界；同时人工核对新建/编辑表单与设置弹窗的宽大清晰布局，留存 API 响应与页面截图。本会话按 `docs/blueprint/testing.md` `verification_notes` 的 `NOT_RUN / USER_WAIVED` 口径顺延，不以本机门禁或 spike 原型冒充已验（与 t066 `[deploy]` 顺延 p093 同口径）。
- 处理：部署阶段现场验收（非本仓 task）；resolution=transferred；reason=用户裁决归档：AC-006 [deploy] 真实部署端到端仍 NOT_RUN/USER_WAIVED、本会话未验证、不冒充闭环；转入宿主真实部署现场验收，不再挂 todo
