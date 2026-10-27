# 测试

CBrowser 质量门禁与测试契约规范。章节名 `verification_policy` / `verification_notes` / `doctor_cmd` / `test_cmd` / `blackbox_verify` 是 preflight 与 skill 的机械锚点，不得改名；命令写在对应章节的代码块内，严格按 Bash 的 `-e -o pipefail` 执行。

## verification_policy

project_configured

## verification_notes

当前项目采用多层验证体系与专项技术探针机制：

1. **模板与工作流工具链契约**：通过运行 `.repo_template/tests`（带 `-m contract` 标记）验证 task 状态机、文档解析及仓库整洁度（当前169 passed；历史基线168 passed/1 skipped）；
2. **业务后端单元测试基线**：通过 `uv` 运行 `src/backend/tests`，涵盖现有 API 接口、鉴权、下载捕获、数据库及生命周期（384 passed）；
3. **前端测试基线与 Node 26 环境标记**：
    - 在 Node v26+ 环境下，运行前端测试因 Node 默认开启的实验性 WebStorage 会在 `localStorage.getItem` 处抛出异常（参见 d001，直接运行会导致 28 failed / 21 passed）；
    - 运行前端测试必须显式设置环境变量：`NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend`（49 passed，全部通过）；
    - 严格禁止在业务代码或测试中就地弱化断言，禁止引入隐式不可见的环境改动；
4. **容器黑盒与健康检查**：通过 curl 检查运行中的容器健康探针 `http://127.0.0.1:56661/api/health`，并支持通过 ego-browser 执行端到端网页交互自动化验证；
5. **专项运行时技术验证探针规范**：
    - 规则与前置：严禁就地修改或运行 `docs/archive/spikes/` 下的代码；必须将归档脚本复制到自身专属的 `.scratch/<probe_name>/` 目录下执行；
    - 命名冲突防御：运行容器必须使用专属防冲突前缀（如 `probe-t001-*`），探针执行结束后必须执行清理，彻底销毁临时容器、网络与独立卷；
    - 独立执行：无需也不能编写庞大的全量探针大一统运行脚本（No giant all-probes runner needed），各技术专题保持完全独立的测试入口；
6. **环境基准与豁免声明**：
    - 运行硬件基准：MacBook Pro M1 Max（10核 CPU，64 GiB 统一内存，macOS 26.5.2，arm64），OrbStack Docker 引擎（10 CPU，~15.66 GiB 内存配额，CPU 纯软件编码无 GPU 预算）；
    - 公网候选可达性与原生 Linux x86_64 环境验证正式记为 `NOT_RUN / USER_WAIVED`（用户明确指示豁免）；
    - 后续第 19 章 10 并发流容量、8 小时稳定性及 1000 次 IME/剪贴板压力测试属于后续任务验收范围，本文不做虚假的 P95 性能承诺。

## doctor_cmd

环境前置检查：契约测试可成功收集；另需 `md_kx` 在 PATH。

```bash
export TMPDIR="$HOME/kar/code/.scratch/cbrowser_t001_contract_tmp"
mkdir -p "$TMPDIR"
pytest .repo_template/tests -q --collect-only -m contract
command -v md_kx
```

## test_cmd

日常测试（红/绿）：模板契约测试与后端业务测试全部跑通。

```bash
export TMPDIR="$HOME/kar/code/.scratch/cbrowser_t001_contract_tmp"
mkdir -p "$TMPDIR"
pytest .repo_template/tests -q -m contract
PYTHONPATH=src uv run --with pytest --with pytest-asyncio --with fastapi --with pydantic --with httpx --with "cloakbrowser>=0.6.3" pytest src/backend/tests -q
```

## blackbox_verify

服务存活探针与任务状态自检：

```bash
curl -sf http://127.0.0.1:56661/api/health
uv run --no-project --python ">=3.12" python .repo_template/scripts/task.py list
uv run --no-project --python ">=3.12" python .repo_template/scripts/repo_sync.py status
```

## 专项技术验证探针

代码为不可变归档快照，先完整复制到专属scratch再运行；下表列出入口和依赖，具体正负例与清理契约见各spike报告。固定前缀/端口同一时刻只能运行一份，不能只改容器名忽略脚本内部引用。归档历史报告里的旧docs/spikes路径按docs/archive/spikes读取。

|专题|归档代码目录|入口与宿主依赖|资源范围|
|---|---|---|---|
|跨容器UDS/下载|s003_selkies_control/code/container_uds|python3 run_cross_container.py --case override_control，再无参数运行；宿主标准库|cbrowser-spike-cdp-uds|
|进程恢复|s003_selkies_control/code/recovery_probe|test_orchestration.py；依赖以report/recovery_review为准|独立API/Supervisor/Browser夹具|
|多页面媒体/输入|s004_media_connections/code|start_containers.sh → uv run --no-project --with playwright python media_e2e_probe.py → stop_containers.sh|HTTP18081/UDP30006|
|捕获/真实visibility|s005_capture_policy/code|只复制当前六文件（包括html和sh），Core用playwright+websockets，Native用websockets；不运行revision_03旧用例|HTTP18084/UDP30008|
|Gateway恢复|s006_gateway_media_recovery/code|完整复制probe及media_fixture，uv run --no-project --with aiohttp --with playwright python probe/run_verification.py|HTTP18082/18083、UDP30007|
|IPC/认证/真实音频|s007_profile_isolation/code|完整复制含fixture，python3 run_isolation_probe.py|cbrowser-spike-isolation；finally清理|
|独立RTC/ICE换代|s008_turn_generation_media/code|先start_coturn.sh和stage2_containers.sh；正常探针exit0、单侧失效探针预期exit1且fresh JSON必须证明拒绝|HTTP18091/18092、UDP30016；coturn13478及40000–40020|
|IME/clipboard哨兵|s009_native_ime_input/code|start_containers.sh → uv run --no-project --with playwright python ime_native_probe.py及verify_extra_harness.py → stop_containers.sh|HTTP18095/UDP30018|

这些探针需要s001构建的cbrowser-spike-runtime-browser:test和cbrowser-spike-runtime-stream:test镜像（身份见s001/image_manifest.json）；清理放finally/trap，不能因负例预期非零而漏清理。合成音频仅可用于测量器校准，不能充当真实浏览器媒体证明。公网和原生x86环境没有执行，不计实测PASS。

模板测试临时目录不能放在已登记Git worktree内：现有fake_repo测试会受真实worktree发现逻辑影响，出现两个.env隔离误报。上面的TMPDIR采用允许写域内、独立于Git仓库的目录，保持原测试与断言不改。归档保留原始源码/报告字节（含历史行尾空格），活跃变更执行git diff --check -- . ':(exclude)docs/archive/\*\*'；完整检查结果及归档例外在task笔记披露，不通过改历史快照掩盖问题。

## Schema / codegen 验证

项目涉及 OpenAPI 导出及前端类型。

- 触发路径：`src/backend/api/`
- 生成命令：无
- 验证命令：无
- 合并后动作：无
- migration 窗口：无

## 门禁类别清单

|类别|必须覆盖|常见盲区|
|---|---|---|
|**单元测试**|pytest 后端业务测试（384 tests）与前端 Vitest（`NODE_OPTIONS=--no-experimental-webstorage`，49 tests）|mock 掉真实逻辑、在业务代码中弱化测试断言|
|**契约测试**|pytest 模板轻量契约测试（当前169项，`-m contract`）|路径或状态机格式不匹配、specs_index 缺失条目|
|**文档格式**|`python3 .repo_template/scripts/md_format.py --check`|Markdown 表格未 compact 或标题语法错误|
|**容器黑盒**|容器健康检查探针与本地技术验证专项探针|只看进程存活、未验证实际双向媒体与数据完整性|
