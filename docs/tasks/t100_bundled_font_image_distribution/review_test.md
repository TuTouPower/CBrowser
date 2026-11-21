# Task review t100（reviewer_focus: 测试）

- task：`t100_bundled_font_image_distribution`
- spec：`docs/tasks/t100_bundled_font_image_distribution/task.md`
- diff_anchor：`3555c8d12110748ecb42843a8d915eb23d6ca53f`
- target：`git diff 3555c8d12110748ecb42843a8d915eb23d6ca53f`
- round：1
- reviewed_at：2026-11-21T15:12:43+08:00

reviewed_scope: 179d54b814d818eb

## Findings

### t100_test_f001 - Browser Runtime 专项指南缺少字体构建上下文

- 严重度：important
- 锚点：行为缺陷。干净 checkout 按专项指南构建时无法取得 Browser 测试镜像，也无法执行后续 E2E 命令。
- 位置：`docs/guides/browser_runtime_validation.md:13`、`config/docker/browser_runtime/Dockerfile:144`、`scripts/build_images.sh:38`
- 问题：指南继续将精简 tar 管道喂给 `docker build`。新 Browser Dockerfile 从命名上下文 `font_assets` 取归档，并从构建根目录复制锁文件与导入脚本。旧命令既未声明命名上下文，又未将后两个文件打入 tar。构建器会将 `font_assets` 当作镜像引用解析。
- 建议：专项指南调用 `scripts/build_images.sh` 生成隔离的镜像清单，从清单读取 Browser 镜像 ID，与部署手册共用字体资产获取方式。

## 结论

- 改测方向复核：部署无需 Dockerfile 或宿主前端是契约变化。删除的固定 Dockerfile 调用、构建时机、宿主前端指纹、字体预检只告警均由新入口行为覆盖。Caddyfile 内容哈希及不匹配时回退拒绝仍由 `test_rollback_restores_target_port_not_current_port` 与 `test_rollback_refuses_on_caddyfile_sha_mismatch_without_touching_disk` 核对。外部 Docker 和下载替身用于可观察的 CLI 边界，实际字体导入由生产脚本及实机证据另行覆盖。未发现恒真断言、扩大超时、跳过新增路径或以状态赋值冒充 UI 交互。
- 本轮新发现：1 条。
- 未进表的提示：用户已要求停测。隔离端口门禁中的 E2E 第一阶段 44 通过、2 跳过，第二阶段 16 通过后中断。此前专项 Viewer 输入用例独立通过，双平台实机 Viewer 均有 WebRTC 帧；人工重连和键盘补验未完成。正式镜像验收证据的架构为 ARM64。
- 总体判断：现有证据可组合支持三条 AC，专项运行指南的镜像构建步骤需要修复。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。独立核对 `test_build_downloads_and_locks_all_images` 对锁中 URL、六镜像及 Browser 专属构建上下文的断言，以及 `.scratch/reject_font.log` 的错摘要拒绝和 `.scratch/t100_attempt2/build_acceptance.log` 的真实镜像内前端构建记录。
- AC-002：TICK-VALID，trust_prior。已有冷启动脚本和日志核对两平台 verified 字体、启动且绑定到平台字体 ID，以及 Viewer 实际解码帧；重复部署采用同一卷、重复导入保留两个既有 manifest，数据库和普通配置变更保留由现有回归用例覆盖，未重跑实机部署。
- AC-003：TICK-VALID，re_verified。独立核对六个 digest 的拉取调用、共用生产部署流程以及缺镜像、导入失败保持原 release 指针的断言；安装包归档检查及实际锁不一致拒绝与该证据一致。

coverage = 2 / 3

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 2 (2026-11-21T17:16:35+08:00)

reviewed_scope: 5589b7c87cd2551d

## 结论

- 前轮 finding 复核：`t100_test_f001` 已修。Browser 验证指南使用统一构建入口，明确从生成清单读取 Browser 镜像 ID。构建脚本为 Browser 配置了 `font_assets` 命名上下文，构建定义与白名单包含锁文件和导入脚本。
- 改测方向复核：单平台锁用例以与正确摘要一致的归档调用实际导入函数，断言缺平台报错、目标目录未创建；不安全 tar 路径用例改用有效的双平台锁，继续验证路径拒绝分支。Caddy 前端缺失用例通过 Docker CLI 边界注入失败，断言报错、发布指针和 Compose 启动次数不变。静态核对未见弱化断言或跳过。
- 本轮新发现：0 条。
- 未进表的提示：按用户指示本轮未运行测试，新增回归用例未经执行；完整 E2E 在已有 60 通过、2 跳过后中止，新标签页重连和键盘补验未完成。复审镜像重新构建完成，构建证据为 ARM64。
- 总体判断：专项指南已与当前入口一致，现有实测和当前代码的静态证据支持三条 AC。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。核对锁定 URL 的测试断言、已有错摘要拒绝日志，以及 `.scratch/t100_attempt2/build_reviewed.log` 的六镜像输出和 Caddy 内前端构建记录。
- AC-002：TICK-VALID，trust_prior。既有空卷部署、两平台 Profile 绑定及 Viewer 解码证据有效；重复导入已有通过记录，保留 Profile 绑定由既有部署/数据库回归和当前存储路径的静态核对支撑，未重跑实机。
- AC-003：TICK-VALID，re_verified。核对安装包引用六个 digest 及共用部署入口，既有缺镜像和字体导入失败断言保持原指针；新增缺前端和不完整字体锁用例只做静态复核。

coverage = 2 / 3

建议合并前人工抽查 trust_prior 项。

verdict: PASS
