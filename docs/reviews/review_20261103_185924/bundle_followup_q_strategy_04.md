# bundle_followup_q_strategy_04

## Summary

核对范围：README.md、AGENTS.md、docs/blueprint 全部现行文档（含 decisions.md ADR 001–014 与 architecture.md）、docs/specs、docs/guides、DOCKER_DEPLOYMENT.md、docs/v2_architecture_plan.md、docs/tasks/t009_v2_full_acceptance/task.md，并对全仓 docs 做「多用户/多人/团队/tenant/并发数值/profile 总数」关键词检索。结论：怀疑成立。仓内不存在任何支撑五服务拓扑与约 40k 行测试投入的部署规模记录——没有 profile 总数、并发会话上限（作为需求）或使用者人数的成文数值；恰恰相反，仓内唯一的规模定性记录是 ADR 013 明文的「单机单人」包络，并明确把多主机场景定性为「未存在的场景」而拒绝为其付费。仓内仅有的规模数值是 t009/v2 计划的容量探边界目标（1/3/10 活跃流、10 个 Profile，在用户本机 Mac/OrbStack 实测找边界），属验收探针而非部署规模需求，且 t009 的 AC-001/AC-002 至今未勾选、未执行落定。附带观察：t009 引用的 docs/specs/v2_acceptance.md 在仓内不存在，容量验收的成文落点缺失。

## Findings

No findings.

## evidence

```json
[
  "docs/blueprint/decisions.md:120-127（ADR 013）：标题即「单机单人部署包络与同机直连媒体链路」；背景原文「CBrowser 的唯一目标是同一台 Mac 上的单一用户」；选项 1 把 coturn/TURN/ICE 接管定性为「继续为未存在的多主机场景付费」并被否决；结论明示公网、NAT 穿透不在需求范围",
  "AGENTS.md:3：项目定义原文「CBrowser 是面向隐私浏览器与多身份隔离的单机 Docker 管理系统」——无用户数、无并发规模表述",
  "docs/blueprint/architecture.md:5：「采用单机 Docker 架构」，全文无部署规模数值",
  "docs/blueprint/decisions.md:34-40（ADR 004）：SQLite 选型以单机为前提，「性能与并发满足单机高可用需求」，未给任何并发或数据量数值",
  "docs/tasks/t009_v2_full_acceptance/task.md:25（AC-001）：仓内唯一的规模数值——「按当前Mac/OrbStack实际配额逐级运行1/3/10活跃流及10Profile九后台一前台，记录真实硬件、成功容量和资源限制」，是容量边界探测而非规模需求；该 AC 与 AC-002（8 小时压力，:26）均仍为未勾选状态，未执行",
  "docs/v2_architecture_plan.md:1112,1127：同一容量口径原文——「测试1、3、10个活跃流，并测试10个Profile同时运行」「实际容量以当前Mac/OrbStack实测为准」，10 流场景明示「用于找容量边界」",
  "阴性检索结果：README.md（共 55 行）无任何规模/用户数/并发表述；对 README.md、AGENTS.md、DOCKER_DEPLOYMENT.md、docs/v2_architecture_plan.md、docs/blueprint/*.md、docs/guides/*.md 以「多用户|多人|团队|multi-user|tenant」检索零命中；对 docs/ 全量以「N 个 Profile/会话/并发数值」检索，除 t009/v2 计划的 10 Profile/10 流探针与归档 t005 的 3 路幂等用例外无其他规模数值",
  "docs/blueprint/artifacts.md:24 的 256 MiB/200 个/2 GiB 是单个 Profile 的 Artifact 资源配额，属单 Profile 上限而非部署规模记录，不构成规模前提",
  "附带观察：docs/tasks/t009_v2_full_acceptance/task.md:75 引用的 docs/specs/v2_acceptance.md（平台、容量与安全实证）在仓内全仓检索零命中、文件不存在，容量验收的成文落点缺失"
]
```

## result

```json
"confirmed"
```
