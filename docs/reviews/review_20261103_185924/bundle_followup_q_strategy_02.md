# bundle_followup_q_strategy_02

## Summary

核对范围：docs/blueprint/decisions.md（ADR 001–014 全文）、docs/blueprint/architecture.md（§1 演进状态、§3 拓扑、§4 职责表、§6 安全矩阵、§7 部署基准）、docs/blueprint/security.md（秘密来源、服务间与媒体凭证、威胁模型一节），并对 architecture/decisions/security/supervisor/gateway 五文件以「成本/进程数/运维/复杂度」做关键词检索。结论：怀疑不成立——五服务（及每 Profile 双容器、双 Agent）拆分的成文理由存在且对应具体威胁模型，恰中反证条件：ADR 001 以单容器共享导致环境污染、端口竞争、指纹泄露与崩溃连锁反应为背景确立每 Profile 独立容器；ADR 007 冻结 v2 时明文「API 为唯一 SQLite 写入者，Supervisor 为唯一 Docker Socket 持有者」，双容器以 shareable IPC 切断媒体容器对浏览器用户数据的直接挂载；architecture.md §4/§6 把边界写成硬约束（API 严格禁止挂载 Docker Socket、Supervisor 仅响应内部受限认证 RPC 且禁止读写 SQLite、Gateway 进程异常重启不影响底层浏览器进程即崩溃域隔离）；security.md 设有成文威胁模型（阻止跨 Profile 访问、阻止 Browser 读取 Agent/Selkies 凭证），ADR 010 另载 Gateway 无状态、实例真相只在 API 的拆分理由。单机单人包络本身亦成文（ADR 013 开篇与 architecture.md §7.1），拆分是在该包络内以最小权限与隔离为据作出的。一处如实记录的残余：成文理由全部在收益/威胁侧，没有任何文档把常驻进程数（Caddy+API+Supervisor+Gateway+每 Profile 双容器与双 Agent）或服务间令牌面（security.md:8 列明至少 4 个服务间令牌文件，另加管理员口令文件、每 Profile 派生 agent_secret 与 Selkies master/controller token）作为长期成本项盘点或权衡，ADR 013 对 TURN 的「不为未存在场景付费」成本测试未见施于控制面拆分本身，也无 ADR 记录曾考虑并否决合并控制面进程的方案；但该缺口属理由文档的成本侧未展开，不构成「拆分无成文理由」，故按反证条件判 refuted。

## Findings

No findings.

## evidence

```json
[
  "docs/blueprint/decisions.md ADR 001（第 3–11 行）：背景明文单进程/单容器共享 X 显示易出现「环境污染、端口竞争、指纹泄露及崩溃连锁反应」，结论为每 Profile 独立 Docker 容器沙箱、独立数据目录",
  "docs/blueprint/decisions.md ADR 007（第 70 行）：冻结 v2 的选项原文含「API 为唯一 SQLite 写入者，Supervisor 为唯一 Docker Socket 持有者，经受控 UDS 隔离代理 CDP 与事件」，同条另载双容器 shareable IPC「彻底切断媒体容器对浏览器用户数据的直接挂载」",
  "docs/blueprint/architecture.md:89-91（§4 职责表）：Control API「严格禁止挂载 Docker Socket」；Supervisor「宿主机唯一持有 Docker Socket 的服务。仅响应内部受限认证 RPC……严格禁止读写或挂载 SQLite」；Stream Gateway「进程异常重启不影响底层浏览器进程运行」（崩溃域隔离成文）",
  "docs/blueprint/architecture.md:158-159（§6 安全矩阵）：API→Supervisor 为「内部受限认证 RPC」，「API 绝不持有 Docker Socket」；Supervisor→Docker Engine 为宿主唯一持 socket 服务",
  "docs/blueprint/security.md:36（威胁模型一节）：成文威胁模型假设与目标——阻止跨 Profile 访问、阻止 Browser 读取 Agent/Selkies 凭证、阻止未受策略保护的沙箱长期运行",
  "docs/blueprint/decisions.md ADR 010：Gateway 不持久化状态、不访问数据库，注册时查询 API 持久绑定判定实例，「实例真相只有 API 一处」——Gateway 与 API 分离的成文理由",
  "docs/blueprint/decisions.md:122,124（ADR 013）与 architecture.md §7.1：单机单人包络成文（「CBrowser 的唯一目标是同一台 Mac 上的单一用户」，部署基准定案为开发者个人电脑），且 ADR 013 曾以「继续为未存在的多主机场景付费」为由删除 TURN 全套机制并收缩 Gateway 职责——成本意识在媒体面有实际执行记录",
  "成本侧缺口（定点检索实测）：对 architecture.md、decisions.md、security.md、supervisor.md、gateway.md 检索「成本|进程数|运维|复杂度」，仅命中 decisions.md:18（RFB 维护负担，与本拆分无关）与 decisions.md:40（ADR 004 选 SQLite 的「极简运维」）；无任何条目盘点常驻进程数或服务间令牌清单的长期维护成本",
  "docs/blueprint/security.md:8：令牌面规模本身有据可查——CBROWSER_SUPERVISOR_TOKEN_FILE、CBROWSER_GATEWAY_TOKEN_FILE、CBROWSER_GATEWAY_API_TOKEN_FILE、CBROWSER_AGENT_KEY_FILE 四个服务间凭证文件（用途单一不可互换），其存在与隔离规则成文，但其长期成本未被任何文档权衡"
]
```

## result

```json
"refuted"
```
