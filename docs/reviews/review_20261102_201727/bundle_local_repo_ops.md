# bundle_local_repo_ops

## responsibilities

- ci.yml 是唯一的 PR/push 门禁：backend job（3 OS 矩阵，pip 安装 + pytest）与 frontend job（npm ci/test/build）
- release.yml 是发布流水线：v\* tag 或 workflow_dispatch 触发，产出 Windows 安装包、macOS universal .dmg、多架构 Docker 镜像（含 manifest 校验与 latest 提升），并创建 GitHub Release
- .gitignore 落实仓内规则：review \_meta/ 过程文件、.env 真值、运行数据（artifacts/、data/、.scratch/）、构建产物（src/frontend/dist/、dist_native/）不入库
- .gitattributes 为 .beads/issues.jsonl 声明 beads merge driver；.prettierignore 为 .repo_template 工具链（repo_sync.py / documents.py 经 grep 确认实际调用 prettier）声明格式化豁免路径

## interfaces

- workflow 对仓库布局的路径契约：ci.yml 引用 backend/、frontend/；release.yml 引用 packaging/ 脚本、根 Dockerfile（build-push-action 默认 {context}/Dockerfile）、CHANGELOG.md
- release.yml 对外部系统的接口：Docker Hub（secrets.DOCKERHUB_USERNAME / DOCKERHUB_TOKEN）、GitHub Releases（job 级 contents: write 的 github.token）
- compose.yaml:9 显式 dockerfile: config/docker/Dockerfile，是生产镜像构建入口的现行权威

## dependencies

- GitHub Actions 托管 runner（ubuntu/windows/macos-15/macos-15-intel/ubuntu-24.04-arm）
- release.yml 全部 action 以完整 SHA 钉版（含版本注释）；ci.yml 全部 action 仅以可变 tag 引用
- Docker Hub 仓库 tutoupower/cbrowser（release.yml env.REGISTRY_IMAGE）

## flows

- tag 推送：version 校验规范 SemVer → 三路构建并行 → docker-manifest 校验候选 manifest（恰 2 镜像 + 2 attestation、digest 格式/去重）→ 发布后逐字节比对已发布 manifest 与候选 → promote-docker-latest 串行化提升最新完整稳定版 → release job 汇总安装包 + SHA256SUMS 建 Release
- workflow_dispatch：仅构建验证（Docker 不推送、原生包不发布），设计意图为打 tag 前的绿灯检查

## constraints

- 顶层 permissions 为 contents: read，仅 release job 提升为 contents: write；Docker 登录步骤仅在 tag 推送时执行
- 原生安装包按项目既定决策不签名（Windows unsigned、macOS ad-hoc 重签），release notes 对用户明示并给出放行步骤
- docs/v2_architecture_plan.md:1054-1057 记载的重组计划：packaging/ 删除原生安装包构建流程、release.yml 只做多架构容器镜像构建发布、ci.yml 覆盖前后端 + Chrome E2E + Docker 集成测试

## decisions

- Docker 镜像按 digest 推送再拼 manifest，且发布后回读校验与候选逐项相等——防漂移设计完整，是 release.yml 的主要质量资产
- promote-docker-latest 以 concurrency group 串行化且每轮重算全部稳定 tag，注释明示中间 job 被取消无害

## evidence

- ci.yml:21-23,27-35 引用的 backend/requirements.txt、backend/tests、frontend/（working-directory）、frontend/package-lock.json 经逐一 stat 均不存在；现行路径为 src/backend/requirements.txt、src/backend/tests、src/frontend/package-lock.json，且根 pyproject.toml:22-28 的 testpaths 为 .repo_template/tests、src/backend/tests、tests 三处，ci.yml 一处都未覆盖
- find 全仓无 packaging/ 目录、无 build_windows.ps1/build_macos.sh/make_universal_app.sh 任何文件；仅 release.yml:64,93,122 与 v2 计划文档引用 packaging/
- 仓库根无 Dockerfile；Dockerfile 实际位于 config/docker/Dockerfile 等 5 处，release.yml:181,191 的 build-push-action 未设 file: 输入
- git ls-files -ci --exclude-standard 输出为空：无已跟踪却被忽略的文件；git ls-files 确认 src/frontend/tsconfig.tsbuildinfo 已跟踪（提交 524e34e 重组时带入），而 .gitignore 无 \*.tsbuildinfo 规则
- git ls-files --eol 显示全部已跟踪 .sh/.c 文件为 i/lf w/lf 且 attr/ 为空：行尾一致靠约定而非 .gitattributes 规则保障
- grep 全仓 merge.beads/driver 仅命中 .gitattributes:3 本行；.beads 目录未跟踪且被 .gitignore:51 整目录忽略

## uncertainties

- .beads 的 merge=beads 属性是否由外部 bd 工具在开发者本机另行配置 driver 并 force-add 文件，仓内无证据；按仓内事实该属性当前不作用于任何已跟踪文件
- release.yml 原生构建三 job 自 packaging/ 删除后是否曾真实跑过 tag 发布，仓内静态证据无法确认；仅能确认按当前 HEAD 触发必在构建步失败

## Findings

- [High][95] .github/workflows/ci.yml:8-39 — CI 两个 job 全部引用重组前路径（backend/、frontend/），在当前布局下必然失败，仓库实际无任何 CI 门禁

    - ID: f_repo_ops_01; verification: static
    - Evidence: ci.yml:21 cache-dependency-path: backend/requirements.txt、:22 pip install -r backend/requirements.txt、:23 pytest backend/tests；stat 确认 backend/ 目录不存在; ci.yml:27-29 frontend job working-directory: frontend、:35 cache-dependency-path: frontend/package-lock.json；frontend/ 目录不存在，job 在 checkout 后第一步即无处落脚; 现行布局为 src/backend/（含 requirements.txt 与 tests/）、src/frontend/（含 package-lock.json）；根 pyproject.toml:24-28 定义 testpaths 为 .repo_template/tests、src/backend/tests、tests 三处，即使只把 backend 改成 src/backend，根 tests/ 与模板测试仍不在 CI 覆盖内; docs/v2_architecture_plan.md:1056 记载 ci.yml 应覆盖前后端、Chrome E2E、Docker 集成测试，现文件连基础路径都未跟上重组
    - Impact: 每次 push/PR 两个 job 都在安装/起始步骤报错：CI 恒红或被当作噪音忽略，等同于没有门禁；与 AGENTS.md 声明的 TDD/门禁流程脱节，后端与前端回归只能靠本地自觉
    - Fix: 按现行布局改 ci.yml：后端以 src/backend/requirements.txt 安装、在仓根执行 python -m pytest（走 pyproject testpaths 覆盖三处测试根）；前端 working-directory 改 src/frontend、cache-dependency-path 改 src/frontend/package-lock.json；是否补 Chrome E2E/Docker 集成 job 按 v2 计划另行立项

- [High][95] .github/workflows/release.yml:50-155 — release.yml 原生安装包三 job 引用已被删除的 packaging/ 构建脚本，tag 发布永远走不到建 Release

    - ID: f_repo_ops_02; verification: static
    - Evidence: release.yml:64 调用 packaging\\build_windows.ps1、:93 调用 packaging/build_macos.sh、:122 调用 packaging/make_universal_app.sh; find 全仓确认 packaging/ 目录及三个脚本文件均不存在，仓内仅 release.yml 与 docs/v2_architecture_plan.md 引用 packaging/; docs/v2_architecture_plan.md:1054 明载重组决定：packaging/ 删除原生安装包构建流程，release.yml 改为多架构容器镜像构建和发布——脚本已删、工作流未同步清理; release job（:548 起）needs 依赖 build-windows 与 universal，两者必失败则 GitHub Release 永不创建
    - Impact: 推送任何 v\* tag：Windows/macOS job 在构建步报脚本不存在，universal 与 release 连带失败；发布只剩 Docker 镜像半程，与文件头注释宣称的三路产物不符；workflow_dispatch 的绿灯检查同样恒红，失去打 tag 前验证的意义
    - Fix: 二选一并落到文件：若按 v2 计划放弃原生安装包，删除 build-windows/build-mac/universal/release 中的安装包部分及文件头注释，仅保留 version/build-docker/docker-manifest/promote 链；若仍要发安装包，恢复 packaging/ 三脚本并纳入仓库。不得保留引用不存在脚本的现状

- [High][90] .github/workflows/release.yml:176-207 — Docker 构建未指定 Dockerfile 路径，默认根目录 Dockerfile 不存在，多架构镜像构建必然失败

    - ID: f_repo_ops_03; verification: static
    - Evidence: release.yml:181 与 :191 两处 docker/build-push-action 均只设 context: .，未设 file: 输入，buildx 默认取 {context}/Dockerfile; 仓库根目录无 Dockerfile（ls 与 find 均确认）；生产 Dockerfile 实际为 config/docker/Dockerfile; compose.yaml:7-9 的现行构建入口明确写 dockerfile: config/docker/Dockerfile，release.yml 未与之对齐; 该缺陷同时命中 workflow_dispatch 的验证构建步（:178-187）与 tag 推送的按 digest 推送步（:188-207），docker-manifest 与 promote-docker-latest 依赖 build-docker，连带不可达
    - Impact: release 流水线的 Docker 半程在构建第一步即失败；与 f_repo_ops_02 合并意味着按当前 HEAD 打 tag，release.yml 七个 job 中除 version 外全部或失败或被连带跳过，整条发布链不可用
    - Fix: 在两处 build-push-action 补 file: config/docker/Dockerfile；若未来以 v2 runtime 镜像（config/docker/\*\_runtime/Dockerfile）为发布物，按计划另行明确矩阵与镜像命名，不要默认根 Dockerfile

- [Low][100] .github/workflows/release.yml:3-6 — 文件头注释宣称 macOS 包 signed + notarized，与同文件实现（明确不签名、不公证）直接矛盾

    - ID: f_repo_ops_04; verification: static
    - Evidence: release.yml:5 头注释：macOS -> ONE universal .dmg, signed + notarized; release.yml:127-133 universal job 内注释明言 We ship UNSIGNED (no Developer ID, no notarization)，实际只做 ad-hoc 重签（codesign --sign -）; release job 生成的用户 release notes 同样写明 not notarized yet 并给出 xattr 放行步骤——头注释是三处表述中唯一与实现不符者
    - Impact: 维护者仅读文件头会误判发布物已具备 Developer ID 签名与公证，对外沟通或排障时给出错误预期；属文档三态/一致性问题，不影响构建行为本身
    - Fix: 将头注释改为与实现一致的表述（如 universal .dmg, ad-hoc signed, not notarized），待真正接入 Developer ID 后再同步改回

- [Low][90] .github/workflows/ci.yml:16-33 — ci.yml 的 action 全部用可变 tag 引用，与 release.yml 全量 SHA 钉版的仓内标准不一致

    - ID: f_repo_ops_05; verification: static
    - Evidence: ci.yml:16 actions/checkout@v4、:17 actions/setup-python@v5、:28 actions/checkout@v4、:29 actions/setup-node@v4，均为可变 tag; release.yml 全部 action 均以 40 位完整 SHA 钉版并附版本注释（如 checkout@11d5960a… # v4），证明仓内既定标准是 SHA 钉版; 两个 workflow 同仓并存两种标准，ci.yml 一侧的 tag 被上游重打即可静默改变 CI 行为
    - Impact: 供应链面：CI 中运行的第三方 action 可被 tag 移动替换，与 release 流水线的防护等级不对齐；实际风险受限于所用均为官方 action，但标准不一致本身会在后续新增 workflow 时被复制放大
    - Fix: 将 ci.yml 四处 action 改为与 release.yml 相同的完整 SHA + 版本注释写法，后续可用 Dependabot/Renovate 统一抬版

- [Low][85] .gitattributes:1-3 — .beads/issues.jsonl 的 merge=beads 属性悬空：仓内无 driver 定义，且 .beads 被 .gitignore 整目录忽略、文件未跟踪

    - ID: f_repo_ops_06; verification: static
    - Evidence: .gitattributes:3 声明 .beads/issues.jsonl merge=beads；grep 全仓 merge.beads/driver 仅命中该行本身，无任何脚本、文档或配置定义 merge.beads.driver; .gitignore:51 将 .beads 整目录列为项目专属临时项；git ls-files 确认 .beads 下无任何已跟踪文件，git check-attr 显示属性只作用于一个不存在于版本库的文件; 两个同单元文件对同一路径给出相反处置：一个为其配置合并策略，一个将其整体排除出版本库
    - Impact: 当前无实际作用（文件不入库）；若有人 force-add 该文件，合并时 git 会因 beads driver 未定义而报错中断，且团队成员各自本机配置不一致会产生不可复现的合并行为
    - Fix: 二选一：若 beads 数据确定不入库，删除 .gitattributes 该行；若要入库，从 .gitignore 移除 .beads 并在仓内提供 driver 配置的安装说明/脚本（如写入 repo 引导文档），使属性有定义可依

- [Low][80] .gitattributes:1-3 — .gitattributes 无任何 text/eol 规则，在 Linux 容器内执行的 shell 入口脚本行尾仅靠约定保持 LF

    - ID: f_repo_ops_07; verification: suspected
    - Evidence: .gitattributes 全文仅 beads merge 一行，无 * text=auto 或 *.sh text eol=lf 类规则; git ls-files --eol 显示全部已跟踪 .sh 文件当前为 i/lf w/lf、attr/ 为空——一致性来自贡献者环境而非仓库规则; config/docker/entrypoint.sh 及 config/docker/*\_runtime/entrypoint.sh 在 Linux 容器内作为入口执行，CRLF 会导致 bad interpreter 类启动失败；ci.yml:11 矩阵包含 windows-latest，Windows 侧 Git 默认 autocrlf 环境真实存在于协作面
    - Impact: 未来任一 Windows 环境贡献者提交 .sh/.ps1 或 C 探针文件时，CRLF 可能被带入仓库，容器入口脚本与 e2e 探针会在运行时才暴露故障，定位成本高
    - Fix: 在 .gitattributes 补最小规则集：\* text=auto、*.sh text eol=lf、*.ps1 text eol=crlf（或按维护者实际编辑环境定）、Dockerfile 与 \*.c 视需要补 eol=lf，并一次性用 git add --renormalize 校准存量

- [Low][100] .gitignore:14-17 — 生成的 src/frontend/tsconfig.tsbuildinfo 已被跟踪入库，.gitignore 无 \*.tsbuildinfo 规则

    - ID: f_repo_ops_08; verification: static
    - Evidence: git ls-files 确认 src/frontend/tsconfig.tsbuildinfo 在库，git log 显示由重组提交 524e34e 带入; .gitignore Node 段仅有 node_modules/、src/frontend/dist/、src/frontend/public/selkies/，无 \*.tsbuildinfo 模式; 该文件是 tsc 增量构建状态（兄弟单元 frontend_shell 已核实其内容仍为重组前文件集），属生成产物而非源码
    - Impact: 生成状态文件随每次本地构建变化产生无意义 diff 与潜在合并冲突，且其内容过期会误导后续审阅者对前端文件集的判断
    - Fix: .gitignore 补 \*.tsbuildinfo 并 git rm --cached src/frontend/tsconfig.tsbuildinfo

- [Info][90] .prettierignore:1-13 — .prettierignore 多条豁免路径已不存在，属过期条目（无害但误导）

    - ID: f_repo_ops_09; verification: static
    - Evidence: 逐一 stat：.repo_template/sync_manifest.json、.repo_template/sync_policy.json、.opencode/package.json、.opencode/package-lock.json 均不存在；.repo_template/sync_state.json 当前亦不存在（属运行态文件，与 .gitignore:38 对应，可保留）; 其余条目（.repo_template/scripts/package.json、skills/registry.json、docs/tasks_index.json 等）均存在且与 .repo_template 工具链实际调用 prettier 的事实相符
    - Impact: ignore 文件容忍不存在路径，不影响格式化行为；但过期条目会让维护者误以为对应文件仍在仓内，排查模板同步问题时多走弯路
    - Fix: 下次模板同步维护时删除已不存在的四条豁免，或在行尾注释标注其为预留条目

- [Info][100] .github/workflows/release.yml:563-595 — 安装包完整性仅靠同源未签名 SHA256SUMS，release notes 的验签指引只能防损坏不能防替换

    - ID: f_repo_ops_10; verification: static
    - Evidence: release.yml:570 在 release job 内对 dist 中安装包生成 SHA256SUMS，随安装包一同附加到同一 GitHub Release，无 GPG/cosign 等独立签名; release notes 指引用户 shasum -a 256 -c SHA256SUMS 验证下载——校验文件与被校验文件同源同权限，发布账号或流水线被攻破时可一并替换; 对照之下 Docker 镜像侧有 buildx provenance: mode=min attestation 且 manifest job 强制校验每镜像一份 attestation，两条分发链的来源保证等级不对称；安装包不签名本身是 :127-133 已声明的既定决策，此处仅记录校验机制的实际保证边界
    - Impact: 用户按指引验证通过也只能排除传输损坏，不能证明安装包未被替换；对隐私浏览器类软件的分发而言，这是已知且已声明的接受项，但文档不应让校验动作显得强于其实际保证
    - Fix: 维持现状时可在 release notes 注明 SHA256SUMS 仅供完整性校验；若未来接入 Developer ID/签名体系，将校验文件一并纳入签名范围

## views

```json
{
  "contracts": {
    "reviewer": "6c81466e-16ff-4616-9dee-b00bc542a08c",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "6c81466e-16ff-4616-9dee-b00bc542a08c",
    "status": "completed"
  },
  "design": {
    "reviewer": "6c81466e-16ff-4616-9dee-b00bc542a08c",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "6c81466e-16ff-4616-9dee-b00bc542a08c",
    "status": "completed"
  },
  "performance": {
    "reviewer": "6c81466e-16ff-4616-9dee-b00bc542a08c",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "6c81466e-16ff-4616-9dee-b00bc542a08c",
    "status": "completed"
  },
  "security": {
    "reviewer": "6c81466e-16ff-4616-9dee-b00bc542a08c",
    "status": "completed"
  },
  "tests": {
    "reviewer": "6c81466e-16ff-4616-9dee-b00bc542a08c",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  ".gitattributes",
  ".github/workflows/ci.yml",
  ".github/workflows/release.yml",
  ".gitignore",
  ".prettierignore"
]
```
