# p073 跨服务共享代码收拢与包边界穿透重构

- 来源：2026-11-13 开发铁律审阅（技术债自查）
- 内容：跨服务共享的纯代码（端点值对象、Agent 凭证、原子写、per-profile 锁、origin 归一化、协议 DTO）没有中立归属，被塞进 `gateway/`、`supervisor/` 包，导致 Supervisor↔Gateway 编译期双向 import、5 个镜像靠 Dockerfile 逐文件白名单 COPY 打补丁、10+ 份原子写与 3 份锁等重复实现，以及多个 1000–3200 行 God class。按「架构至上」应把共享代码收拢到中立包，随之删掉跨包 COPY 与重复实现，而非继续补兼容分支。当前未开：只读审阅，未授权改生产代码；牵涉全部镜像打包与跨服务契约，需专项 task。
- 处理：t062；resolution=transferred；reason=已核实当前代码与有效 task，按同一交付面聚合转交 t062；过时描述与剩余范围见 task spec，归档仅表示转办
- 时间：2026-11-13T18:57:05+08:00

## 违反点与证据（一条因果链）

1. 共享值对象放错包 → 双向耦合：
    - `src/backend/cbrowser/supervisor/core.py:38`、`docker_adapter.py:28`、`runner.py:19` import `cbrowser.gateway.endpoint`。
    - `src/backend/cbrowser/gateway/server.py:32` import `cbrowser.supervisor.agent_credentials`。
    - `src/backend/cbrowser/gateway/endpoint.py:1,46` 自认 "Single source for Gateway endpoint and browser Origin normalization" / "shared by Supervisor and Stream startup"；`auth/service.py:27`、`auth/dependencies.py:11` 亦依赖。
    - 架构文档（`architecture.md` 4/6 节）声明「独立服务经内部认证 RPC」，实际是编译期互 import 对方包；项目已有 `shared/` 与 `schemas/` 未使用。
2. 打包靠手工白名单打补丁：
    - `config/docker/gateway_runtime/Dockerfile:27-29` 为上述 import 逐文件补 COPY `supervisor/__init__.py`、`agent_credentials.py`、`file_storage.py`。
    - `config/docker/supervisor_runtime/Dockerfile:27` 整包 `COPY .../gateway`。
    - `config/docker/api_runtime/Dockerfile:16` 全量 `COPY src/backend`（把 Supervisor/Gateway/Runtime 全打进 API 镜像）。
    - 其余镜像逐文件白名单；新增一个 import 漏补即运行时 ImportError。
3. 重复实现（优先复用缺失）：
    - 原子写 `flush+fsync+os.replace` 10+ 份：`supervisor/file_storage.py:8` 已有 helper，`preview.py:67-76`、`runtime_agent/fontconfig.py:150-156`、`runtime_agent/event_storage.py:65-67`、`adapters/filesystem/artifact_store.py:239-240`、`agent_executor/state.py:107`、`font_sets/manifest.py:280-289`、`supervisor/event_forwarder.py:193`、`supervisor/core.py:1596` 各自手写；`conventions.md:47-49` 规定「公共 helper 单一来源」。
    - per-profile 锁 3 份：`services/profile_service.py:150`、`services/control_service.py:149-156`、`supervisor/core.py:282,337-340`。
    - origin 归一化 2 份：`gateway/endpoint.py:13-28` 与 `network_config.py:25-34`，后者注释 "Keeps parity with request-side normalize_origin" 靠人工维持一致。
    - fence 规则 2 份：`api/v1/runtime_views.py:16-40` 自认 "the coordinator's live publish path applies the same rule via its own fenced accessor"，对照 `runtime_coordinator.py:475,657`。
    - 投递状态分类 2 份：`supervisor/event_forwarder.py:37-43` 定义 `classify_delivery_status()`，`artifact_forwarder.py:293` 自行判断。
    - 端口/路径字面量散落：`control_client.py:32` 默认 `8091` 与 `compose.yaml:34,132` 实际 `8005` 冲突；容器内固定路径 8+ 处重复。
4. God class 职责混杂：`supervisor/core.py` 3228 行、`docker_adapter.py` 2614 行、`api/runtime_coordinator.py` 1301 行、`services/profile_service.py` 1192 行、`gateway/server.py` 996 行。
5. 分层穿透：`api/v1/router.py:8,157` 用 ORM `SessionModel` 作 HTTP 类型、`:79` 直接访问 `service._locks`；`domain/egress_observation.py:30` 把 httpx/文件 I/O 放进 domain（`conventions.md` 2 节规定 domain 只放数据契约）；`api/v1/deps.py:1` 注释 "to avoid router import cycles"。
6. 文档自认权宜：`docs/blueprint/supervisor.md:74`「沿用 Browser/Stream 各自内联写法的既有模式，未抽统一构造函数」。

## 目标

1. 把跨服务/跨镜像共享的纯代码收拢到中立包（`shared/` 或 `schemas/` 对应契约），Gateway/Supervisor/API/部署 CLI 只依赖中立包，消除双向 import。
2. 统一镜像打包策略，删除 Dockerfile 的跨包 COPY 白名单行。
3. 原子写、锁、origin 归一化、fence 规则、投递分类、端口/路径常量各收口为单一来源，删除重复实现。
4. 按职责拆分 God class；`api` 层不再用 ORM 实体作 HTTP 类型、不访问 services 私有属性；`domain` 不再含基础设施 I/O。
5. 同步修订 `conventions.md` 2/5 节、`architecture.md` 4 节、`supervisor.md`、`gateway.md`，新增 ADR 记录破坏性重构。

## 非目标

- 不改变宏观权限边界：API 唯一 SQLite 写入者、Supervisor 唯一 Docker Socket、Gateway 无 SQLAlchemy ORM，该层已有代码证据，符合架构。
- 不做兼容层或渐进迁移，按零兼容性负担直接替换。
- 不在本 pending 内实施、建 task 或改生产代码。

## 验收

1. `supervisor/` 与 `gateway/` 互 import 零命中；跨服务 import 只指向中立包。
2. 全部 Dockerfile 无跨服务包 COPY 白名单；新增共享模块不需改多个 Dockerfile。
3. 原子写 helper、per-profile 锁、origin 归一化各唯一，由门禁测试守护。
4. 全量门禁 + 真实 Docker 部署演练（六镜像构建、启动、readiness）通过。
