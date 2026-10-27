---
tid: "t002"
slug: "v2_backend_foundation"
title: "建立 v2 Profile 与运行状态持久化骨架"
status: "done"
branch: "t002_v2_backend_foundation"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "d3ca80b0141c19a715a90c71ba2f5862c1c79711"
depends_on: "t001"
conflicts_with: ""
note: ""
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 字段溯源与架构契约确认

1. **源配置字段对照（`src/backend/models.py`, `src/backend/database.py` 及计划 15.2）**：

    - 基础身份与元数据：`id` (UUID), `name`, `fingerprint_seed` (int, 随机生成非敏感整数), `user_data_dir` (规范值 `/data/profiles/{profileId}/profile`), `sort_order`, `created_at`, `updated_at`
    - 显示与环境：`screen_width` (int, 默认 1920), `screen_height` (int, 默认 1080), `gpu_family` (Literal['auto','nvidia','intel'], 默认 'auto'), `color_scheme` (Literal['light','dark','no-preference'] | None)
    - 隐私与网络：`proxy` (str | None), `timezone` (str | None), `locale` (str | None), `geoip` (bool, 默认 True), `transparent_proxy` (bool, 默认 False)
    - 浏览器行为与扩展：`launch_args` (list[str]), `extension_paths` (list[str]), `allow_3p_cookies` (bool, 默认 True), `set_google_default` (bool, 默认 True), `capture_preview` (bool, 默认 True), `restore_session` (bool, 默认 True), `portable_cookies` (bool, 默认 False), `clipboard_sync` (bool, 默认 True), `auto_launch` (bool, 默认 False)
    - 拟人化：`humanize` (bool, 默认 False), `human_preset` (Literal['default','careful'], 默认 'default')
    - 备注与标签：`notes` (str | None), `tags` (`tag`: str, `color`: str | None)
    - 运行时与查看模式映射：`runtime_mode` 统一为 'docker', `viewer_mode` 统一为 'webrtc'，废弃旧 native/vnc 链路但无损承载历史字段。

2. **数据库 8 张表规格（SQLAlchemy 2.0 + Alembic）**：

    - `profiles`：Profile 主表及当前配置字段
    - `profile_config_versions`：不可变配置快照版本表（`id`, `profile_id`, `version`, `snapshot`, `created_at`）
    - `profile_tags`：多对一关联标签表（`profile_id`, `tag`, `color`, 联合主键）
    - `profile_runtimes`：运行期状态表（`profile_id` PK/FK, `desired_state`, `observed_state`, `runtime_instance_id`, `config_version`, `failure_count`, `restart_blocked`, `last_exit_event_id`, `updated_at`）
    - `artifacts`：文件 Artifact 元数据表（`id`, `profile_id`, `name`, `size`, `kind`, `state`, `content_type`, `picker_name`, `created_at`）
    - `settings`：全局系统配置表（`key` PK, `value`, `updated_at`）
    - `runtime_events`：运行期事件持久化去重表（`event_id` PK, `profile_id`, `runtime_instance_id`, `event_type`, `exit_code`, `exit_reason`, `config_version`, `payload`, `created_at`），保留物理记录作为去重凭证与审计总账
    - `audit_events`：操作审计记录表（`id` PK, `entity_type`, `entity_id`, `action`, `actor`, `details`, `created_at`）

3. **运行时状态收敛与事件契约（计划 12.2 - 12.6, d006 事实）**：

    - 退出事件载荷契约：`profile_id`, `runtime_instance_id`, `event_id`, `exit_code`, `exit_reason`, `config_version`
    - 幂等性：基于 `event_id` 物理去重；重复事件返回已确认但不再二次推进状态机或增加失败计数。
    - 实例保护：事件 `runtime_instance_id` 与数据库当前 `runtime_instance_id` 严格比对；过期旧实例事件丢弃并不修改当前状态。
    - 状态收敛：
        - 正常退出（以 `exit_code == 0` 为准）：`desired_state = stopped`, `observed_state = stopped`, `runtime_instance_id = None`, `last_exit_event_id = event_id`。
        - 异常退出（`exit_code != 0`）：保留已有的 `desired_state`（若原本为 running 则仍为 running，严禁凭空把已停止的设为 running）；`observed_state = stopped`（或 error）；`failure_count += 1`；当 `failure_count >= 3` 时设置 `restart_blocked = True`；记录 `last_exit_event_id = event_id`。
    - Supervisor 控制接口：提供显式 Service/API 契约用于实例绑定（bind instance）与运行时状态/事件上报。

4. **并发与事务控制契约（计划 12.1）**：

    - SQLite 强制启用 WAL 模式与 `busy_timeout=5000`。
    - 写入事务统一在连接层由 `BEGIN IMMEDIATE` 开启，确保读-改-写物理串行化执行，杜绝并发不相交字段更新时出现更新丢失。
    - 发生数据库锁争用（超 5000ms）时，API 抛出明确可重试的 HTTP 503 / 409 错误，并在锁释放后可成功回滚重试。
    - 数据操作在事务内保证原子性；约束/校验失败触发连接级回滚，杜绝半写数据。

5. **结构化诊断契约（`src/backend/diagnostics.py`）**：

    - 保留原有的崩溃捕获钩子、环境指纹、stderr tee 以及代理脱敏；
    - 扩展安全事件结构化 JSON 诊断日志（`emit_event_log`），仅输出白名单元数据（`event_id`, `profile_id`, `runtime_instance_id`, `event_type`, `exit_code`, `exit_reason`, `config_version`）；严禁泄露密码、Token、Cookie、剪贴板或用户输入。

### 缺陷复现与修复演进

1. **意图与观测彻底分离 (Defect 1 / Item D)**：

    - 退休原初版错误语义测试 `test_runtime_event_convergence_normal_and_abnormal`（原用例在 `set_desired_state(running)` 后断言 `observed_state=running`，将用户意图误作为真实容器状态）。
    - 新增 `test_desired_state_intent_does_not_invent_observed_runtime` 与 `test_stopping_intent_does_not_claim_observed_stopped_before_event`，确保 `desired_state=running` 时 `observed_state` 保持当前真实观测（`stopped`），停止意图亦不提前判定容器已停止或清除存活实例。
    - 新增显式 Supervisor 观测与绑定契约：`bind_runtime_instance` 与 `report_observed_state`。
    - 绑定防覆盖保护：当 Profile 存在处于 `running` 或 `starting` 状态的活跃实例时，禁止无 CAS `expected_current_instance` 校验的其他实例绑定覆盖；已被替代的历史实例 ID 不得重新绑定，返回 HTTP 409 Conflict。

2. **配置版本解耦与绑定快照严格匹配 (Defect 2 & 6 / Item C)**：

    - Profile 配置更新产生新快照并自增 `current_config_version`，但不修改 `profile_runtimes.config_version`（该字段严格表示当前运行容器实际绑定的快照版本）。
    - 配置快照完整持久化 `config` 字典与关联 `tags` 列表，防止快照丢失标签。
    - 观测上报与退出事件所声明的 `config_version` 必须与该实例实际绑定的 `config_version` 完全一致；若试图以上报未实际应用到容器的配置版本触发状态变更，API 识别为 `invalid_config_version` 并拒绝，不改变状态机。

3. **并发不相交 PATCH 更新原子合并 (Item A)**：

    - 路由层不再预读并合并全量配置，改为仅向仓储层传递显式传入的 Patch 字段字典。
    - 仓储层在 SQLite 连接层由 `BEGIN IMMEDIATE` 开启排他写入事务，在锁保护下读取最新物理行数据并就地合并字段与校验，消除并发不相交字段更新（如同时更新 name 与 notes）时的更新丢失。

4. **请求全维度指纹与并发事件物理去重 (Defect 4 / Item B & E)**：

    - 幂等性控制不仅记录载荷哈希，签名严格覆盖 `action` + `target`（Profile ID）+ `payload`。相同操作 ID 作用于不同 Profile、不同动作或不同载荷时，严格返回 HTTP 409 Conflict。
    - 重放旧的启动操作 ID（`desired_state=running`）保持幂等重放语义，不重置 `failure_count`；仅全新的操作请求才重置失败计数。
    - 运行时事件表主键冲突在并发插入时由数据库物理仲裁，对重复并发事件安全捕获并返回 `duplicate`，杜绝未捕获的 500 异常。

5. **诊断脱敏与安全日志体系修复 (Defect 5 / Item F)**：

    - 修复 Alembic 迁移脚本 `env.py` 中 `fileConfig` 未设置 `disable_existing_loggers=False` 导致应用日志器被注销的问题；
    - 移除 `sys.stderr.write` 底层绕过，所有结构化诊断事件严格通过 Python 标准日志组件（`cbrowser.events`）输出；
    - 对非标准 UUID / 规范格式的任意外部 ID 进行单向不可逆哈希转换（`id_hash_<sha256[:12]>`），既保持多行日志关联性，又防止将敏感 Token/Cookie 伪装为 ID 注入导致日志泄漏；
    - `exit_reason` 经安全白名单校验，未知或任意注入字串清洗为 `custom_reason`；422 验证错误响应体剔除原始输入回显；全局异常处理器安全捕获 `IntegrityError` 与 `DBAPIError`，防止带参数的 SQL 跟踪日志输出到物理服务日志。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

正式 full Round2 code/test均PASS，reviewed_scope=bfeffb3d43a6d56d，0条finding，无需处置。Round1因审查越界中断，不冒充有效报告；原始执行记录保留。预审只采纳已复核问题，未当作正式PASS。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：实现与项目门禁已完成，六项 AC 根据主控真实测试暂判通过，待独立正式 review 复核；独立候选 Round3已8/8通过，最终 full Round2 code/test均PASS。
- 测试：主控按实际文档命令块运行，模板169、旧后端384、新单元19通过。第一次门禁因文档漏 jsonschema 依赖在集成收集失败，原日志保留；补齐依赖和显式缓存路径后完整门禁退出0。
- 黑盒：文档 blackbox_verify 的新独立 HTTP 集成5项、旧服务健康及控制面检查通过；独立候选 Round1失败已返修，候选 Round2为6/7通过、唯一失败为OpenAPI静态导出漂移；最新候选 Round3已冻结并派发。
- review：代码预审已结束并完成有效问题修复；最终 canonical full code/test review 待当前范围渲染后派发。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 新增版本化 Profile 数据服务与 API、8张业务表及空库迁移、原子配置更新/幂等/实例事件收敛、脱敏诊断与真实进程测试。旧入口与用户数据未切换。复用发现 d015，跨模块约束由后续 task 消费。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

## 主控验证与最终范围整理

- Verify Round1：真实独立 HTTP 候选黑盒失败；修正后同旧快照补验2/7通过、5/7失败，确认丢失更新、跨目标幂等、配置/实例代际、并发重复退出与日志泄漏，历史证据留在主仓control专属scratch。
- Verify Round2：源码冻结 manifest f3c76c2b0b266586b60746d87added4ed56824b443e278558e2117110b771118，独立进程7395已结束，产品6/7通过、FAIL；仅静态OpenAPI导出漂移，不能把agent退出0视为产品通过。正式轮次上限仍为5，未重置。
- 父流程修正文档漏列jsonschema的可执行命令，将新单元放test_cmd、真实HTTP集成放blackbox_verify，显式指定UV缓存及Git工作树外TMPDIR。完整命令块日志为本工作副本.scratch/t002_gates/project_gates_fixed.log；第一次失败另存project_gates.log。
- 新增d015记录真实SQL异常日志边界；specs_index已登记runtime_persistence关联t002。
- 固定候选后仅整理diagnostics.py多余EOF空行（AST等价）及初始migration的Revises说明行尾空格；不改运行逻辑/契约。原始冻结副本保持不可变，最终canonicalreview绑定实际交付范围。证据.scratch/t002_gates/diagnostics_eof_cleanup.json。

### 第三轮候选与正式派审准备

- lint实现session90433已完成（持久消息finish=stop）；CLI未退出且JSON为空，先保存t002_lint_final.json再仅中断残留CLI，返回-2，不计模型任务失败。未改全局配置。

- 14个新增Python文件Ruff check/format通过；diagnostics.py新增段落UP017已修，13项基线问题保留。服务仅捕获DBAPIError，领域异常自然透传；异步测试等待和具体异常断言完成修正。

- 主控在最新实际源码执行完整门禁：169契约、384旧后端、19单元、5独立HTTP通过，旧健康ok、task list与本工作副本repo_sync status退出0（未初始化）。日志.scratch/t002_gates/project_gates_candidate3.log；未把未初始化描述成配置成功。

- Verify Round3冻结manifest=3459bd7d3659e1d6528fc2f4c12d587a98c3124abd5d67bf6b764b85d5f6461f，独立8用例harness包含真实持写锁读取与两次进程重启；主控核验8/8通过，无finding；SQL隐私探针通过。持写锁GET约11ms且锁仍持有，长锁约5.22秒返回503；两次真实服务重启与完整字段/标签颜色/旧快照校验通过。报告worker收尾中。轮次仍为3/5，没有重置。

- 补齐testing.md的实际OpenAPI生成/校验命令，架构文档明确新增API基础与尚未切换的旧正式入口。任务可测试性仅需真实HTTP/SQLite，不虚设Docker/Chrome依赖。

- 正式full Round1独立审查已派发：code session ses_e813a6e91ffecjvQTYnIF2wNuY，test session ses_e813a3ddfffeo3WagRl7MAmvtg；完整canonical提示含实际reviewed_scope，源码/测试/长期文档冻结，待回收报告与finding处置。

### 正式审查执行异常与新诊断

- 首次新会话未显式--dir，OpenCode归属主仓，触发worktree只读命令权限拒绝。两会话已自然terminal0但无有效报告；保存完整消息，不能记PASS。改显式--dir后会话归属核验为登记worktree。
- 后续code审查违反只读边界，误运行未实现的export --check（实际写导出），继而执行禁止的git checkout --，将intent-to-add的OpenAPI文件替换为Git索引空blob。主控检测实际文件0字节，立即中断两路审查（子进程-2），保存完整消息；41文件manifest核验仅此文件变化，从不可变candidate3核验哈希后恢复原61401字节。由此产生的测试失败是审查污染，不能归产品漂移。原始记录不删除，下一轮编号Round2/5，不重置上限。
- 主控新真实HTTP诊断：重复tag=duplicate得到409，但重复tag=busy或locked得到503/retryabletrue。\_handle_db_error对包含用户SQL参数的异常字符串搜索busy/locked，错误分类可被配置文本影响；证据.scratch/t002_gates/root_error_classification_probe/。该缺陷未被第三轮8/8覆盖，不能finish，已派实现修复与真实回归。
- 后续审查增加单子进程权限白名单（只允许对应report和专属scratch写），拒绝checkout/reset/restore及导出命令，并由主控观察器核对交付文件哈希；不改全局配置，不允许审查者自行回退文件。正式报告尚无有效PASS。

### 错误分类修复与第四轮候选

- 实现64859因读取主仓外部证据被OpenCode拒绝后terminal0，无最终答复；不算已实施。复制证据到本task scratch后恢复9131，已terminal0且持久消息finish=stop，无重复writer。
- 保留原测试，新增4个真实HTTP参数化用例先红（均503）后绿（均409、constraint_violation、retryablefalse）。仅IntegrityError按类型转换约束错误，锁判断使用sqlite_errorcode低8位5/6及sqlite_errorname，不搜索SQL异常参数文本。
- 最新作者门禁169契约、384旧后端、19单元、9真实HTTP全部通过；Ruff两修改文件check/format通过，完整live/export测试继续通过，OpenAPI未改变。红绿完整消息保存在主仓t002_error_classification_tdd_trace.json，最终答复另存t002_error_classification_fix_local.final.json。
- Verify Round4/5已冻结manifest=c7e1228803978178adff71a7075f4de17226ea4bfa52c0a487600c07cd6c93ef；原8用例保持，加第9用例验证5类重复标签文本不影响错误分类、无半写和日志参数泄漏。独立复验进行中。
- 正式Round2将使用显式--dir、子进程权限白名单与交付文件哈希观察器。Round1污染记录保留；测试中的空schema失败已定位为审查者checkout造成，不能据此报告原始产品缺陷。此后源码、测试与长期文档冻结，禁止审查者生成或恢复交付文件。

### 最终收尾结果

- Verify Round4/5实际9/9 PASS，无finding；独立SQL隐私探针PASS，冻结manifest c7e1228803978178adff71a7075f4de17226ea4bfa52c0a487600c07cd6c93ef与当前源码一致。新增5类重复标签均409/retryablefalse，无半写或SQL参数日志；原8项WAL/并发/CAS/幂等/真实重启用例保持通过。
- 正式full Round2代码与测试报告均PASS，scope=bfeffb3d43a6d56d，0条finding；两位审查者均独立复验19单元+9真实HTTP，六项AC及七个正交视角全部披露。409文件哈希监控无越界变更。所有模型进程已终态；自然CLI退出0与持久finish=stop分别核验，不以单独CLI0当业务通过。
- 审查者已修正报告未来时间戳、补全七视角证据、限定日志结论边界并纠正依赖方向；仅报告过程文件变化，交付scope未变。最终机器门禁overall=PASS/review_scope=ok/round=2。
- 规范化当前task报告Markdown仅属机械排版，不改变finding、verdict或证据；最终格式与diff检查一并执行。未切换旧正式入口、未接触用户数据、未部署或push。t003仍未start。
