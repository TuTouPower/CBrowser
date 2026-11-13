# bundle_followup_q_evolution_04

## Summary

怀疑对主格式不成立，反证条件双命中；仅 ledger 一处为政策未覆盖的例外（已单独立 Low finding）。逐项核对如下：(1) task note.md front matter / workflow schema——成文政策与迁移实现俱在：.repo_template/docs/usage.md:104 明文『workflow schema 不做运行时兼容』，政策为 sync 时强制迁移而非运行时双轨解析：apply 强制更新存量 spec/task（旧 status: blocked 改为 active、补齐轮次上限字段），存在已登记 task worktree 时拒绝 apply，更新后工具链直接拒绝旧字段和旧状态。repo_sync.py 有对应实现：文件头注释（:23）声明 apply 时强制迁移 workflow schema；:302 起整节『Workflow schema migration (forced on apply)』，\_migrate_task_text（:417-476）删除旧字段 schedule_status、把 status: blocked 改写为 active、缺失时补 review_limit/verify_limit；\_inspect_workflow_task_dir（:512 起）处理旧版布局（spec.md 单文件）向 task.md+note.md 的迁移；force_migrate_workflow_tasks（:648-695）在有已登记 worktree 时以 SyncError 拒绝、无法安全迁移时整体拒绝（:675），覆盖范围经 \_collect_workflow_task_dirs（:496-509）含 docs/tasks 与 docs/archive/tasks；规范块未闭合时『拒绝猜测迁移』（:373）。运行时侧 repo_task/documents.py 的 parse_front_matter_text（:55-74）与 context.py 的 FRONT_MATTER_KEYS（:77-82，13 键）确实无 version 字段、无版本校验——但这正是成文政策『不做运行时兼容』的另一面：演进由 sync 期强制迁移收口，旧状态 blocked 不在 VALID_STATUSES（context.py:21）内、消费侧按枚举拒绝。故『默认新旧同构、旧格式行为未定义』对 front matter 不成立。(2) registry.json——无 version 字段、无迁移分支：skill_registry.py:14 直接取 ['skills']/['calls']，repo_sync.py:1018 状态侧 .get 容错、:1096 同步侧硬下标；但有显式结构拒绝（skill_registry.py:17-20 集合不一致或未知 role 即 ValueError），且 registry.json 是模板自有文件、随模板树硬同步整体覆盖（repo_sync.py:97），消费仓不存在自有旧格式长期存续的面。(3) dispatch ledger 行格式——三者中唯一例外：ledger.py 事件写入（:13-20）只加 ts、无 version 字段，读取（:23-58）逐行 json.loads、无版本识别；repo_sync.py 全文 grep 'ledger|dispatch' 零命中，强制迁移不覆盖 ledger。现行行为靠字段容忍定义：attempts.py project_attempts（:36-46）对缺 tid/attempt/execution_id 的行直接 skip、未知 event kind 不匹配任何分支即忽略，损坏行则 fail-closed 显式拒绝（ledger.py:40-46）——行为并非完全未定义，但无版本维度、格式演进时旧行被静默跳过而非迁移或报错，与 usage.md 的成文口径不一致，见 finding f_followup_q_evolution_04_01。另：architecture.md 经关键词（兼容/旧格式/格式版本/迁移/compat/migrat）检索无格式兼容政策条文，成文政策只在 usage.md。

## Findings

- [Low][90] .repo_template/scripts/repo_task/ledger.py:13-58；.repo_template/scripts/repo_task/attempts.py:36-46；.repo_template/scripts/repo_sync.py:496-509（强制迁移范围仅 task 目录） — dispatch ledger 行格式不在成文兼容政策与 sync 强制迁移覆盖内：无 version 字段、无迁移分支，旧格式行靠投影 skip 静默容忍，与 usage.md『不保留双轨解析、直接拒绝旧字段』口径不一致
    - ID: f_followup_q_evolution_04_01; verification: static
    - Evidence: ledger.py:13-20 事件写入（\_sanitize）只补 ts，不写任何 version/格式标识；ledger.py:23-58 读取逐行 json.loads，无版本识别与旧格式分支; attempts.py:36-46 project_attempts 对缺 execution_id 等关键身份字段的行直接 continue——execution_id 即是已经历过的一次格式演进（旧行无此字段），其处置是静默跳过而非迁移或显式拒绝; repo_sync.py 全文 grep 'ledger|dispatch' 零命中；force_migrate_workflow_tasks 的覆盖范围由 \_collect_workflow_task_dirs（:496-509）限定为 docs/tasks 与 docs/archive/tasks，docs/runtime/dispatch_ledger.jsonl 不在内; .repo_template/docs/usage.md:104 成文政策对 workflow schema 声明『更新后工具链直接拒绝旧字段和旧状态，不保留双轨解析』，ledger 的 skip 容忍与该口径不一致且无文档说明此例外
    - Impact: 若 ledger 行格式再演进（新增必填字段或事件类型重命名），消费仓存量旧行不会被迁移、不会报错，只会在 project_attempts 投影时被静默丢弃，attempt 历史与身份链出现无声缺口；与 front matter 侧『强制迁移 + 显式拒绝』的确定性处置相比，ledger 侧的失败模式是静默数据损失而非 fail-closed。
    - Fix: 二选一并成文：或把 ledger 纳入 sync 强制迁移/版本识别（如事件加 version 字段、project_attempts 对已知旧版本显式迁移、对未知版本显式拒绝），或在 usage.md:104 的政策段明确 ledger 例外及其 skip 容忍语义与风险接受。

## evidence

```json
[
  ".repo_template/docs/usage.md:104 ——成文政策原文：『workflow schema 不做运行时兼容。repo-template-sync 的 apply 会强制更新主仓 docs/tasks/ 中的存量 spec/task 模板块（包括把旧 status: blocked 改为 active、补齐轮次上限字段）；存在已登记 task worktree 时拒绝 apply……更新后工具链直接拒绝旧字段和旧状态，不保留双轨解析。』",
  ".repo_template/scripts/repo_sync.py:23 ——脚本头注释：『并在 apply 时强制迁移 active/backlog task 的 workflow schema』；:302 节标题『# Workflow schema migration (forced on apply)』",
  ".repo_template/scripts/repo_sync.py:417-476 ——_migrate_task_text 迁移分支：删除旧字段 schedule_status（:431-432）、status: blocked 改写为 status: \"active\"（:436-437）、缺失时在 front matter 闭合前插入 review_limit: \"5\" / verify_limit: \"5\"（:459-466）",
  ".repo_template/scripts/repo_sync.py:496-509 ——_collect_workflow_task_dirs 覆盖 docs/tasks 与 docs/archive/tasks 两个父目录；:512-603 _inspect_workflow_task_dir 含旧布局迁移（:548 注释『旧版布局向新版 (task.md 需求规格, note.md 过程总账) 迁移』、:572 旧 spec.md 迁移写入 task.md 并删除原文件）",
  ".repo_template/scripts/repo_sync.py:648-675 ——force_migrate_workflow_tasks：已登记 task worktree 存在时 SyncError 拒绝（:659-662），任一目录无法安全迁移时整体拒绝『workflow schema 无法安全迁移』（:674-675）；:373 规范块未闭合『拒绝猜测迁移』",
  ".repo_template/scripts/repo_task/documents.py:55-74 与 repo_task/context.py:77-82 ——运行时 parse_front_matter_text 为固定 13 键 FRONT_MATTER_KEYS 的键值解析，无 version 字段与版本校验（与『不做运行时兼容、靠 sync 强制迁移』的成文政策一致）；context.py:21 VALID_STATUSES 不含旧状态 blocked",
  ".repo_template/scripts/skill_registry.py:14-20 ——registry.json 无 version 字段，直接取 ['skills']/['calls']；结构显式拒绝：registry 与 canonical skills 集合不一致 raise ValueError（:17-18）、未知 role raise ValueError（:19-20）",
  ".repo_template/scripts/repo_sync.py:1016-1018 与 :1094-1096 ——repo_sync 两处 registry 解析（状态侧 roles.get 容错 / 同步侧 roles[name] 硬下标）均无版本识别或迁移；:97 registry.json 列入模板路径集，随模板树整体同步覆盖",
  ".repo_template/scripts/repo_task/ledger.py:13-20 与 :23-58 ——ledger 事件写入只加 ts、无 version 字段；读取逐行 json.loads，无版本识别、无迁移分支；:40-46 损坏行 fail-closed 抛 TaskDataError 显式拒绝",
  ".repo_template/scripts/repo_task/attempts.py:36-46 ——project_attempts 对缺 tid/attempt/execution_id 的 ledger 行直接 continue 跳过（旧格式行靠 skip 容忍，非迁移非报错）；repo_sync.py 全文 grep 'ledger|dispatch' 零命中，sync 强制迁移不覆盖 ledger",
  ".repo_template/docs/architecture.md ——经关键词检索（兼容/旧格式/格式版本/向后/compat/migrat）无格式兼容政策条文，成文政策仅见 usage.md:104"
]
```

## result

```json
"refuted"
```
