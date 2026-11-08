# bundle_local_repo_template_toolchain

## responsibilities

- 提供模板工具链框架（task 生命周期流转、pending/findings/spikes 追踪、工作区整理与安全清理）
- 管理 Worktree 自动跟踪与状态栏钩子（track_worktree.py）
- 提供与 OpenCode / Claude Code 交互的命令扩展定义

## interfaces

- CLI task.py {new|start|finish|integrate|drop}
- CLI pending.py, findings.py, spikes.py, repo_cleanup.py, repo_hygiene.py
- .opencode/commands/\*.md

## dependencies

- Python 标准库
- Git (git rev-parse, git worktree, git merge)

## flows

- 任务生命周期：task.py new 分配全局编号 -> start 创建 worktree 分支 -> finish 校验 review 生成 handoff.json -> integrate 合并归档
- 工作区追踪流：Claude Code 执行 Bash 触发 PostToolUse 钩子 -> track_worktree.py 记录活跃 worktree

## constraints

- 所有状态与派生索引更新必须通过 atomic_write_text 原子写入
- 严禁执行破坏性 git reset --hard 或未经授权的 git checkout

## decisions

- 去中心化设计，以本地 git 树和文件系统为唯一权威
- 使用独立 Worktree 隔离并发任务

## evidence

- .repo_template/scripts/\_id_scan.py:34-36
- .repo_template/scripts/repo_task/documents.py:10-30
- .repo_template/scripts/track_worktree.py:140
- .repo_template/scripts/repo_cleanup.py:223-225
- .repo_template/scripts/template_sync/state.py:27-38

## uncertainties

## Findings

- [Medium][90] .repo_template/scripts/track_worktree.py:140 — track_worktree.py 参数提取正则缺少精确词法边界，存在参数吞噬与错配风险

    - ID: f_tool_track_worktree_regex_greedy; verification: static
    - Evidence: match = re.search(r'--tid[= ](%5CS+)', command) 使用 \\S+ 贪婪捕获，在复合 shell 命令中捕获分号或管道连带字符（如 t042;）
    - Impact: 导致 resolve_worktree 比对失败，使得工作树自动跟踪与状态记录失效
    - Fix: 将正则限定为严格的标识符字符集：r'--tid[= ](%5Ba-zA-Z0-9_-%5D+)'

- [Low][85] .repo_template/scripts/repo_cleanup.py:223-225 — repo_cleanup.py 在批量清理目录内容时对软链接缺乏解引阻断

    - ID: f_tool_repo_cleanup_symlink_traversal; verification: static
    - Evidence: 清理目录遍历使用 target.is_dir() 判断，若存在指向外部真实目录的符号链接，默认跟随并执行 shutil.rmtree(target)
    - Impact: 在 .scratch 下存在外部目录符号链接时，可能意外误删外部真实目录
    - Fix: 优先检查 target.is_symlink() 执行 unlink()，防止递归跟随

- [Low][80] .repo_template/scripts/template_sync/state.py:27-38 — state.py 读取本地 sync_state.json 时对顶层非字典结构缺少类型防御

    - ID: f_tool_sync_state_json_type_check; verification: static
    - Evidence: 解析 JSON 后未做 isinstance(data, dict) 判断直接 .get()，若文件格式损坏为数组则抛出未受控 AttributeError
    - Impact: 缺少结构损坏时的友好异常报错与恢复指引
    - Fix: 增加类型断言校验并抛出结构清晰的 SyncError

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "agent_repo_template_toolchain"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "agent_repo_template_toolchain"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "agent_repo_template_toolchain"
  },
  "performance": {
    "status": "completed",
    "reviewer": "agent_repo_template_toolchain"
  },
  "design": {
    "status": "completed",
    "reviewer": "agent_repo_template_toolchain"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "agent_repo_template_toolchain"
  },
  "tests": {
    "status": "completed",
    "reviewer": "agent_repo_template_toolchain"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "agent_repo_template_toolchain"
  }
}
```

## files_reviewed

```json
[
  ".claude/settings.json",
  ".opencode/commands/bug-to-pending.md",
  ".opencode/commands/pending-fix.md",
  ".opencode/commands/pending-record.md",
  ".opencode/commands/repo-cleanup.md",
  ".opencode/commands/repo-hygiene.md",
  ".opencode/commands/repo-template-sync.md",
  ".opencode/commands/task-create.md",
  ".opencode/commands/task-from-pending.md",
  ".opencode/commands/task-merge.md",
  ".opencode/commands/task-preflight.md",
  ".opencode/commands/task-run.md",
  ".opencode/commands/task-schedule.md",
  ".opencode/commands/template-issue-report.md",
  ".repo_template/docs/architecture.md",
  ".repo_template/docs/recovery.md",
  ".repo_template/docs/review_prompts/code_prompt.txt",
  ".repo_template/docs/review_prompts/general_prompt.txt",
  ".repo_template/docs/review_prompts/share_prompt.txt",
  ".repo_template/docs/review_prompts/test_prompt.txt",
  ".repo_template/docs/spike_report_template.md",
  ".repo_template/docs/sync.md",
  ".repo_template/docs/task_template/progress.md",
  ".repo_template/docs/task_template/task.md",
  ".repo_template/docs/usage.md",
  ".repo_template/hooks/pre-commit",
  ".repo_template/scripts/_id_scan.py",
  ".repo_template/scripts/check_review_status.py",
  ".repo_template/scripts/export_template.py",
  ".repo_template/scripts/findings.py",
  ".repo_template/scripts/md_format.py",
  ".repo_template/scripts/package.json",
  ".repo_template/scripts/pending.py",
  ".repo_template/scripts/render_review_prompts.py",
  ".repo_template/scripts/repo_cleanup.py",
  ".repo_template/scripts/repo_hygiene.py",
  ".repo_template/scripts/repo_state.py",
  ".repo_template/scripts/repo_sync.py",
  ".repo_template/scripts/repo_task/__init__.py",
  ".repo_template/scripts/repo_task/attempts.py",
  ".repo_template/scripts/repo_task/cli.py",
  ".repo_template/scripts/repo_task/context.py",
  ".repo_template/scripts/repo_task/control.py",
  ".repo_template/scripts/repo_task/documents.py",
  ".repo_template/scripts/repo_task/file_transaction.py",
  ".repo_template/scripts/repo_task/finalization.py",
  ".repo_template/scripts/repo_task/git_ops.py",
  ".repo_template/scripts/repo_task/goal.py",
  ".repo_template/scripts/repo_task/graph.py",
  ".repo_template/scripts/repo_task/integration.py",
  ".repo_template/scripts/repo_task/ledger.py",
  ".repo_template/scripts/repo_task/lifecycle.py",
  ".repo_template/scripts/repo_task/locks.py",
  ".repo_template/scripts/repo_task/monitoring.py",
  ".repo_template/scripts/repo_task/plan.py",
  ".repo_template/scripts/repo_task/recovery.py",
  ".repo_template/scripts/repo_task/review.py",
  ".repo_template/scripts/repo_task/scheduling.py",
  ".repo_template/scripts/repo_task/specs_index.py",
  ".repo_template/scripts/repo_task/store.py",
  ".repo_template/scripts/repo_task/validation.py",
  ".repo_template/scripts/repo_task/view_server.py",
  ".repo_template/scripts/repo_task/view_static/board.css",
  ".repo_template/scripts/repo_task/view_static/board.html",
  ".repo_template/scripts/repo_task/view_static/board.js",
  ".repo_template/scripts/repo_task/view_static/chain_plan.js",
  ".repo_template/scripts/repo_task/worktrees.py",
  ".repo_template/scripts/skill_registry.py",
  ".repo_template/scripts/spikes.py",
  ".repo_template/scripts/task.py",
  ".repo_template/scripts/template_sync/__init__.py",
  ".repo_template/scripts/template_sync/agents_merge.py",
  ".repo_template/scripts/template_sync/apply.py",
  ".repo_template/scripts/template_sync/assets.py",
  ".repo_template/scripts/template_sync/cli.py",
  ".repo_template/scripts/template_sync/common.py",
  ".repo_template/scripts/template_sync/context.py",
  ".repo_template/scripts/template_sync/conventions_migration.py",
  ".repo_template/scripts/template_sync/gates.py",
  ".repo_template/scripts/template_sync/hooks.py",
  ".repo_template/scripts/template_sync/shared_files.py",
  ".repo_template/scripts/template_sync/skills_links.py",
  ".repo_template/scripts/template_sync/source.py",
  ".repo_template/scripts/template_sync/specs_index_migration.py",
  ".repo_template/scripts/template_sync/state.py",
  ".repo_template/scripts/template_sync/status_plan.py",
  ".repo_template/scripts/template_sync/transaction.py",
  ".repo_template/scripts/template_sync/workflow_migration.py",
  ".repo_template/scripts/track_worktree.py",
  ".repo_template/skills/bug-to-pending/SKILL.md",
  ".repo_template/skills/pending-fix/SKILL.md",
  ".repo_template/skills/pending-record/SKILL.md",
  ".repo_template/skills/registry.json",
  ".repo_template/skills/repo-cleanup/SKILL.md",
  ".repo_template/skills/repo-hygiene/SKILL.md",
  ".repo_template/skills/repo-template-sync-core/SKILL.md",
  ".repo_template/skills/repo-template-sync/SKILL.md",
  ".repo_template/skills/task-create/SKILL.md",
  ".repo_template/skills/task-from-pending/SKILL.md",
  ".repo_template/skills/task-integrate/SKILL.md",
  ".repo_template/skills/task-merge/SKILL.md",
  ".repo_template/skills/task-preflight/SKILL.md",
  ".repo_template/skills/task-run/SKILL.md",
  ".repo_template/skills/task-schedule/SKILL.md",
  ".repo_template/skills/task-work/SKILL.md",
  ".repo_template/skills/template-issue-report/SKILL.md",
  ".repo_template/sync_manifest.json",
  ".repo_template/tests/pytest.ini",
  ".repo_template/tests/review_support.py",
  ".repo_template/tests/test_check_review_status.py",
  ".repo_template/tests/test_contract_suite.py",
  ".repo_template/tests/test_plan.py",
  ".repo_template/tests/test_repo_cleanup.py",
  ".repo_template/tests/test_specs_index.py",
  ".repo_template/tests/test_task_archive_dir.py",
  ".repo_template/tests/test_task_document_validation.py",
  ".repo_template/tests/test_task_save.py",
  ".repo_template/tests/test_task_unverified.py",
  ".repo_template/tests/test_validation_policy.py",
  ".repo_template/tests/test_view_server.py"
]
```
