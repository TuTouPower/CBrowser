# bundle_followup_q_architecture_04

## Summary

怀疑（实现疏漏）不成立：克隆沿用源 fingerprint_seed 是仓内两处权威文档明文规定的产品定义，且实现与之完全一致。生效 spec（docs/specs/profile_management.md「复制与重置」节）明文写明配置复制『保留全部有效配置字段、标签与同一指纹种子』；blueprint（docs/blueprint/persistence.md）独立复述同一口径『配置复制只写数据库：新 Profile ID、配置版本、标签与同一指纹种子』。两份文档在紧邻条目中对 reset 给出相反口径（『更新指纹种子』），证明 duplicate 与 reset 的 seed 策略是被有意区分的：复制=保留同一指纹身份，重置=换新指纹身份。交付该功能的 t013 归档记录亦记载按此实现（配置复制保留种子、重置重新生成种子）。实现侧核对：profile_service.py 的 duplicate_profile 以 source.config.model_dump() 仅覆写 name 构建新配置（L524-530），seed 原样沿用，与 spec 一致；reset_profile（L608-617）则以 \_seed_for_operation(operation_id) 或 generate_fingerprint_seed() 生成新 seed 并 patch，与 spec 的 reset 口径一致。阴性检索：对 docs/specs 与 docs/blueprint 全量 grep『指纹种子/fingerprint_seed』，无任何条目要求克隆新发 seed；全仓 seed 规则只有三条——创建时未提供则随机生成（runtime_persistence.md:19）、复制保留同一 seed、重置重新生成。文档与实现无矛盾，不立 finding。

## Findings

No findings.

## evidence

```json
[
  "docs/specs/profile_management.md:30 配置复制明文：『保留全部有效配置字段、标签与同一指纹种子；不复制浏览器用户数据和 Artifact，源 Profile 不变』",
  "docs/specs/profile_management.md:32 紧邻条目对 reset 给出相反口径：『将用户数据目录移动到备份、更新指纹种子并生成新配置版本』——两条路径的 seed 策略在同一节内被有意区分",
  "docs/specs_index.md:14 profile_management 在生效清单内（来源 t007, t013, t017，更新 2026-11-03T05:15:00+08:00），按仓规『在表即生效』",
  "docs/blueprint/persistence.md:107 独立复述：『配置复制只写数据库：新 Profile ID、配置版本、标签与同一指纹种子』；:109 重置口径为『再更新指纹种子并生成新配置版本』",
  "src/backend/cbrowser/services/profile_service.py:524-530 duplicate_profile 以 {**source.config.model_dump(), 'name': clone_name} 构建 ProfileConfig，仅改名、seed 沿用，与 spec 一致",
  "src/backend/cbrowser/services/profile_service.py:608-617 reset_profile 以 _seed_for_operation(operation_id)（无 operation_id 时 generate_fingerprint_seed()）生成新 seed 并 patch_data={'fingerprint_seed': seed}，与 spec 的 reset 口径一致",
  "docs/archive/tasks/t013_v2_profile_copy_reset/note.md:27 交付记录：『实现配置复制（保留全部配置/标签/种子，不复制用户数据与 Artifact）……重置（……重新生成指纹种子并新增配置版本……）』，实现按 spec 落地",
  "阴性检索范围：grep『指纹种子|fingerprint_seed』覆盖 docs/specs 全部与 docs/blueprint 全部，仅得上述条目及 runtime_persistence.md:19（创建未提供 seed 时随机生成）、architecture.md:102/domain.md:9（字段定义，无 seed 策略），无任何『克隆应新发 seed』的表述"
]
```

## result

```json
"refuted"
```
