# Task review t100（reviewer_focus: 代码）

- task：`t100_bundled_font_image_distribution`
- spec：`docs/tasks/t100_bundled_font_image_distribution/task.md`
- diff_anchor：`3555c8d12110748ecb42843a8d915eb23d6ca53f`
- target：`git diff 3555c8d12110748ecb42843a8d915eb23d6ca53f`
- round：1
- reviewed_at：2026-11-21T15:12:24+08:00

reviewed_scope: 179d54b814d818eb

## Findings

### t100_code_f001 - 构建强制绕过构建机的 HTTP 代理

- 严重度：important
- 锚点：AC-001。开发机可通过已配置的 Docker HTTP 代理访问构建依赖，但不能直接访问镜像站时，源码构建会失败。
- 位置：`config/docker/browser_runtime/Dockerfile:4`、`config/docker/browser_runtime/Dockerfile:32`、`config/docker/caddy_runtime/Dockerfile:3`、`scripts/build_images.sh:39`
- 问题：Browser 与 Caddy 的 apt 配置对镜像站无条件写入 `DIRECT`。Stream 构建也把该站无条件加入两种 `NO_PROXY` 变量。即使运营方既未豁免此站又已配置可用代理，三类构建仍尝试直连，导致 apt 更新或下载超时。
- 建议：默认镜像站与代理策略解耦，移除构建中自动添加的 `DIRECT` 和 `NO_PROXY` 豁免，让操作者通过现有网络配置决定哪些地址直连。

### t100_code_f002 - 缺少应用前端的 Caddy 镜像仍可使发布通过

- 严重度：important
- 锚点：AC-003。正确摘要但缺少 cbrowser 前端的 Caddy 镜像可以激活发布。
- 位置：`scripts/deploy.sh:911`、`scripts/deploy.sh:716`、`scripts/deploy.sh:1088`、`config/docker/caddy_runtime/Dockerfile:47`、`compose.yaml:195`
- 问题：预构建清单把 Caddy 基础镜像的有效摘要误填为应用 Caddy 摘要时，拉取和镜像身份校验均可通过，基础 Caddy 可读取挂载的配置并启动。原宿主前端入口检查随挂载一起移除。内部服务 readiness 与字体接管没有校验 Caddy 镜像的 `/var/www/html/index.html`，没有待启动 Profile 的部署可移动发布指针并返回成功，但管理页无应用入口。
- 建议：用无网络、只读的一次性容器在变更数据库和启动服务前校验 Caddy 镜像内的前端入口，失败时保留当前发布。

### t100_code_f003 - 字体锁缺少一个平台时仍可激活发布

- 严重度：important
- 锚点：AC-003。只列一个平台的字体锁和匹配归档可以让安装成功，缺少平台的 Profile 不能创建。
- 位置：`scripts/font_bundle.py:38`、`scripts/font_bundle.py:90`、`scripts/deploy.sh:529`、`src/backend/cbrowser/font_sets/manifest.py:37`
- 问题：发行者误将新锁的 `sets` 写成仅含 `macos`，同时归档与摘要匹配时，镜像锁与部署锁一致，seed 只安装这一个平台，接管等待只检查锁中已有的键，脚本最后仍会激活发布。SHA-256 只能证明包与锁一致，无法保证所需两平台均被锁定。
- 建议：处理归档前要求 `sets` 的键精确为 Windows 和 macOS 平台，验证每个 set ID 是内容寻址的十六进制摘要，并复用同一校验范围判定接管。

### t100_code_f004 - 维护者生成安装包的命令无法直接执行

- 严重度：minor
- 锚点：行为缺陷。复制部署手册的代码块会触发输入输出重定向或 Bash 语法错误。
- 位置：`DOCKER_DEPLOYMENT.md:196`、`DOCKER_DEPLOYMENT.md:197`
- 问题：代码块中的 `<images.json>` 与 `<部署包文件名>` 使用 shell 重定向语法，不能作为文件名参数传递。
- 建议：使用具体的示例文件名或先赋值的 shell 变量，引用变量传给打包与摘要命令。

### t100_code_f005 - 当前字体规范同时规定字体进入和不进入镜像

- 严重度：minor
- 锚点：行为缺陷。按同一规范可得到相互矛盾的制品边界。
- 位置：`docs/specs/fingerprint_platform.md:8`、`docs/specs/fingerprint_platform.md:12`
- 问题：开头说明浏览器镜像携带字体，后续仍声明平台字体不进镜像。实现中运行时仍只读挂载所绑定字体，部署源已变为镜像内制品。
- 建议：在现行规范中统一表述源码仓、浏览器镜像与运行时字体卷的边界。

## 结论

- 本轮新发现：5 条。
- 未进表的提示：按物理行数检查，`src/backend/cbrowser/supervisor/docker_adapter.py` 为 2997 行，本次净增一行。构建/部署已有大文件但未净增，生成物、vendor 及锁文件不计入。按 shell 分支近似计量，`cmd_deploy` 和 `load_release_images` 进入约 10 的提示区。完成安全、正确性、契约、性能、架构、健壮性和文档静态核对。原始字体下载无已发布制品和完整 E2E 在用户停止时中断，均未记为复验成功。
- 总体判断：已核实六镜像清单与双平台冷启动证据，构建代理、前端镜像与两平台锁定验证仍存在可观测缺口。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VOID，re_verified。静态核实构建入口校验摘要并生成六镜像清单，已有 `.scratch/t100_attempt2/build_acceptance.log` 支撑实构建，但 `f001` 仍让配置了可用代理、直连被禁的构建机失败。
- AC-002：TICK-VALID，trust_prior。既有 `.scratch/t100_attempt2/cold_profiles.log`、`deploy_cold.log` 与 `viewer_live.log` 支撑空卷、两套 verified 字体和 Windows、macOS Viewer 解码实际画面，重跑保留绑定由字体按集合寻址、部署不改 Profile 绑定及既有幂等/部署证据支撑，未重新部署。
- AC-003：TICK-VOID，re_verified。静态核实安装包和镜像清单共用部署入口，`f002` 与 `f003` 仍能让前端缺失或平台字体缺失的发布被激活。

coverage = 2 / 3

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 2 (2026-11-21T17:16:30+08:00)

reviewed_scope: 5589b7c87cd2551d

## 结论

- 前轮 finding 复核：
    - `t100_code_f001` 已消除。Browser 和 Caddy 的 apt 配置仅替换镜像站，无强制直连。构建入口仅传递操作者显式设置的代理豁免，无自动追加的站点。见 `config/docker/browser_runtime/Dockerfile:4`、`config/docker/browser_runtime/Dockerfile:32`、`config/docker/caddy_runtime/Dockerfile:3`、`scripts/build_images.sh:35`。
    - `t100_code_f002` 已消除。部署在数据库检查与 Compose 启动前，以无网络、只读根文件系统的一次性容器校验 Caddy 镜像内的前端入口。校验失败立即返回。见 `scripts/deploy.sh:1063`。
    - `t100_code_f003` 已消除。字体锁对照受支持平台清单，要求精确覆盖 Windows 和 macOS，且 ID 均为 64 位十六进制摘要。目录输入校验失败会使导入退出，接管和激活都不会执行。见 `scripts/font_bundle.py:40`、`scripts/font_bundle.py:100`、`scripts/deploy.sh:1077`、`scripts/deploy.sh:1095`。
    - `t100_code_f004` 已消除。发布示例使用具体输入文件名和引用的输出变量，打包成功后才生成校验文件。回退示例使用已赋值的版本变量。见 `DOCKER_DEPLOYMENT.md:85`、`DOCKER_DEPLOYMENT.md:199`。
    - `t100_code_f005` 已消除。现行字体规范区分源码仓锁文件、Browser 镜像压缩制品与运行时只读字体集绑定。见 `docs/specs/fingerprint_platform.md:12` 与 2.6 节。
- 本轮新发现：0 条。
- 未进表的提示：`src/backend/cbrowser/supervisor/docker_adapter.py` 为 2997 行，本次净增一行。构建和部署分发函数复杂度提示沿用 R1，生成物、vendor、锁文件等不计量。本轮做静态复审，使用已产出的构建和实机证据，未运行新增回归测试。完整 E2E 中断未作为通过证据。
- 总体判断：前轮三个阻塞及两个文档问题已消除，未发现新阻塞。安装包从已提交版本取得部署文件及手册，产物生成完毕才原子发布。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。静态核对锁定来源、摘要失败退出、六镜像写入与 Caddy 前端封装，既有 `.scratch/t100_attempt2/build_reviewed.log` 与 `reviewed_images.json` 对应修订后的成功构建。
- AC-002：TICK-VALID，trust_prior。既有 `.scratch/t100_attempt2/cold_profiles.log`、`deploy_cold.log` 与 `viewer_live.log` 支撑空卷接管、两套 verified 字体和两个 Profile 的 Viewer 解码，代码按相同内容 ID 复用已有字体且不更新 Profile 绑定，本轮未重新部署。
- AC-003：TICK-VALID，re_verified。静态核对安装包与共享部署入口、六镜像不可变引用处理，以及缺前端、字体锁不一致或缺平台时在激活发布前退出的控制流。本轮未运行新增回归测试或公网发布。

coverage = 2 / 3

建议合并前人工抽查 trust_prior 项。

verdict: PASS
