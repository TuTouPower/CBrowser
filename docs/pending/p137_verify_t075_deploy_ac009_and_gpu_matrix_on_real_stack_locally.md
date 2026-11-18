---
pid: "p137"
slug: "verify_t075_deploy_ac009_and_gpu_matrix_on_real_stack_locally"
status: "todo"
---
# p137 本地真实栈补验 t075 AC-009（双平台字体集隔离 Browser 中英文渲染）与 s026 GPU 能力矩阵实测

- 来源：t075 遗留（云端无 Docker/真实引擎，[deploy] AC-009 与 GPU 动态实测按用户 2026-11-18 裁定延期本地统一补验）
- 内容：在本地真实容器化栈（流程同 p126/p128 补验：主仓 FF 到含 t075 的 main → 前端重建 → scripts/deploy.sh deploy）执行：
    1. t075 AC-009：经真实容器化编排启动分别绑定 Windows 与 macOS 字体集的隔离 Browser，断言两平台地址栏及受控网页中英文可读；错误挂载对照（空目录/错平台集）不可就绪；正确挂载无字体渲染崩溃（无 Skia FATAL、无 .dmp 新增）。
    2. CJK 开关实测：英文 Profile 关闭中文字体时容器内 fc-list 无 zh 覆盖字体、开启时真实平台中文正确渲染（文本成形截图对照，不以非零像素或缺字框充数）；中文 Profile 默认含中文字体。
    3. s026 GPU 矩阵动态实测：两平台各取 ≥2 个 seed，读取 WebGL unmasked vendor/renderer 与可用时 WebGPU adapter 信息，同 seed 重启前后一致、跨实例一致；记录实值回填 s026 报告。若实测推翻「引擎按 seed+平台自动派生且自洽」结论，升级回 t075/spike 处理，不得直接改判通过。
    4. 配色实测：light/dark 两值在初始页、新增页、导航与重启后媒体查询与网页 CSS 与所选一致；后台主题切换不改写网页配色。
    5. 身份迁移演练（隔离副本）：对含旧形状配置（gpu_family=nvidia、color_scheme=null/no-preference、font_set_id=null）的备份 DB 副本先跑迁移计划核对阻塞清单，再执行迁移与恢复演练，核对 seed、绑定、版本与浏览器数据完整。
        全程只用隔离实例/备份副本，不操作生产数据；结论逐项记录实测证据（镜像 ID、fc-list 输出、截图、探针 JSON）。
- 处理：未开
