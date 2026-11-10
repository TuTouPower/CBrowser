# 审阅结果决策

## 目录

docs/reviews/review_20261110_200842

## 报告来源

- 已读：review_intensive.md
- 缺失：无 `bundle_*.md`，以 review_intensive 为准（报告自述为单次穷尽审阅，逐项列全、不分级、不合并）。
- 合并说明：原始 137 个独立问题（编号 1–139，第 68、109、139 为指针条目）→ 64 个决策项（采纳 62、不采纳 2、待决定 0；D1、D2 经用户决策转为 A61、A62）。决策依据为 AGENTS.md「核心架构铁律」：不以改动量或开发难度作为不采纳或降级理由；不保留兼容分支；同一问题只给一个彻底方案，不提供权宜备选。按「同一根因 / 同一修复点 / 同一交付面」聚类，映射如下（`review_intensive.md:L<行>` 为原文行号）：
    - 第 1–23 项（L13–L35）→ A1–A13；
    - 第 24–40、43–54、59–62、102、113、114 项（L41–L57、L60–L71、L76–L79、L129、L145–L146）→ A61（用户选 C：网络配置回到部署期，相关问题随代码删除或改由部署期保证）；
    - 第 41、42 项（L58–L59）→ A14；第 55–58 项（L72–L75）→ A15；
    - 第 63–67、69–71、73、75–91 项（L85–L113）→ A16–A31，第 68 项（L90）为指针并入第 69 项（A19）；第 72 项 → R1，第 74 项 → A59；
    - 第 92–101、103–105 项（L119–L132）→ A32–A42，第 104 项尺寸部分 → A62；
    - 第 106–109 项（L138–L141）→ A60；第 110–112、115–131、133–138 项（L142–L170）→ A43–A58；第 132 项 → R2；第 139 项（L171）为指针并入 A50；
    - 「未证实疑点」（L175–L181）不计入问题数、不单独立项；其中色对对比度并入 A42，同 tick 双击并入 A23，`_preview_*` 去重状态只写不清并入 A33，其余保留为后续实施时的核查线索。
- 核实：决策前已在 HEAD 抽验第 1、41、50、128、133、134 项事实成立；并核对 `docs/blueprint/decisions.md` ADR 026 与 parked `p053`（用户已放弃原生 LAN，但设置页仍暴露 LAN 开关）。

## 统计

- 采纳：62 项
- 不采纳：2 项
- 待决定：0 项

## 待决定项（请先决策）

无（D1、D2 已由用户 2026-11-10 决策，转为 A61、A62）。

## 采纳项

### A1. 迁移连接 pragma 顺序与 session 不一致

- 来源：review_intensive
- 位置：`src/backend/cbrowser/adapters/database/migrations.py:81-82`
- 优先级：MEDIUM
- 详细判断理由：已抽验，迁移连接先执行 `journal_mode=WAL` 后设 `busy_timeout`，与 `session.py:57-58` 修复后的顺序相反；切 WAL 时遇到写锁会立即 BUSY，启动迁移可能失败。
- 修复说明：交换两行，先 `PRAGMA busy_timeout=5000` 再 `PRAGMA journal_mode=WAL`；补单测断言执行顺序（记录 pragma 调用序列）。

### A2. control renew-upgrade 在提交前 publish

- 来源：review_intensive
- 位置：`src/backend/cbrowser/services/control_service.py:240,261-264`
- 优先级：MEDIUM
- 详细判断理由：其余路径都在 commit 之后才 publish，唯独此分支在写事务内 publish：commit 失败时 SSE 已广播未持久化的 `agent_session_id`，且持有 BEGIN IMMEDIATE 写锁期间 await，延长锁占用。
- 修复说明：把 `_publish` 移到 `write_transaction` 块之外，在提交成功后执行；补测试：注入 commit 失败，断言没有事件发出。

### A3. 媒体子网分配跨实例竞争且锁内阻塞无超时

- 来源：review_intensive
- 位置：`src/backend/cbrowser/supervisor/docker_adapter.py:237,883-909`；`compose.yaml:5-7`
- 优先级：MEDIUM
- 详细判断理由：compose 明确支持第二实例共用同一 daemon，进程内锁挡不住跨进程选中同一子网；锁内 Docker 调用无超时，一次挂起就会堵住所有 Profile。
- 修复说明：根因是多个实例共用同一个分配池。deploy.sh 按实例 prefix 为每个实例分配互不重叠的 `media_subnet_pool`（写入实例 `.env`，部署时校验与同 daemon 上其它实例的池不相交），Supervisor 只在本实例池内分配，跨实例冲突从结构上消失；Docker 创建网络时若仍遇冲突，视为配置错误直接报错，不做重试掩盖。networks.list/get/create 加调用超时，超时转为 `DockerSandboxError`。补测试：两实例池不相交校验；创建冲突即报错。

### A4. policy helper 清理异常覆盖结果、安装失败不抓日志

- 来源：review_intensive
- 位置：`docker_adapter.py:1935-1937`、`:336-338,349-360`
- 优先级：MEDIUM
- 详细判断理由：finally 中的 `helper.remove` 抛错会覆盖返回值并以原始 Docker 异常逃逸，绕过调用方的收敛处理；安装失败时不回收 iptables 报错。两处修复都小且互补。
- 修复说明：`_run_policy_helper` 的 finally 中 remove 包 try，仅记 warning；`_install_network_policy` 失败分支在删除 helper 前抓取 `helper.logs()`（截断、脱敏）写入错误日志。补两处单测。

### A5. forget_instance_events 按 Profile 全删 native exit 记录

- 来源：review_intensive
- 位置：`src/backend/cbrowser/supervisor/core.py:1673-1677`
- 优先级：MEDIUM
- 详细判断理由：同一函数的其它结构都按 (profile_id, instance_id) 精确过滤，唯独此处按 profile 过滤，会误删新实例的权威 exit 分类。
- 修复说明：过滤条件改为 `key != (profile_id, instance_id)`；补测试：新实例 exit 先登记、旧实例收尾后，新实例记录仍在。

### A6. 媒体 attach 的 gateway 解析异常穿透、离线恢复静默空转

- 来源：review_intensive
- 位置：`core.py:433,440-448`、`:866-890`
- 优先级：MEDIUM
- 详细判断理由：`_resolve_gateway_id` 是收口中唯一的穿透点；离线恢复丢弃返回值且不打日志，故障时不可见。
- 修复说明：`_ensure_media_attachment` 捕获 `DockerSandboxError`，转为 gateway_missing/failed 状态；`_recover_attachment_offline` 消费返回值，非成功状态写 warning 日志（按 profile 限频）。补单测覆盖扫描失败路径。

### A7. 恢复路径无健康证据即报 running，注册宽限被重置

- 来源：review_intensive
- 位置：`core.py:1284-1292,1478-1487`、`:1498-1500,631`
- 优先级：HIGH
- 详细判断理由：CDP 门禁只看 `observed_state==running`，恢复时 Agent 已死也会放行，与稳态口径不一致；宽限被同轮 pop 后重新 arm，使 90s 上限失效。
- 修复说明：恢复时 Agent 健康为 None 则预置 `starting`，由正常收敛升级为 running；RegistrationState 在 Gateway 不可达时保留 `lost_at`，不整表 pop，宽限从恢复时刻起算。补两条单测。

### A8. Browser 查找失败无日志、只报首个异实例、测试只在 lookup 层

- 来源：review_intensive
- 位置：`core.py:1823-1824,1835-1840,1871-1872`；`tests/unit/test_p058_browser_lookup.py`
- 优先级：LOW
- 详细判断理由：Docker 故障与「不存在」无法区分；多异实例时排障信息丢失；`NotFound` 分支疑似死代码，调用方语义无回归保护。
- 修复说明：非 NotFound 异常记录 warning（含 error_type、profile）；`observed_instance_id` 改为报告全部异实例 id；删除 list 路径下不可达的 NotFound 分支（docker-py list 以空列表表示缺失，由 missing 分支统一处理）；补调用方级测试：mismatch 返回 None、missing 报终态。

### A9. artifact 跨挂载换算缺宿主路径输入测试

- 来源：review_intensive
- 位置：`tests/unit/test_download_reconciler.py:84-131`；`supervisor/artifact_forwarder.py:247-257,273`
- 优先级：LOW
- 详细判断理由：现有用例只覆盖恒等输入，5dcb11d 修复的换算逻辑没有回归保护。
- 修复说明：新增用例：以宿主绝对路径为事件输入，并用嵌套子目录验证相对路径保留；越界路径拒绝。

### A10. CDP 关码透传读取时机错误，upstream.close 不在 try 内

- 来源：review_intensive
- 位置：`src/backend/cbrowser/api/v1/automation_router.py:236-252`
- 优先级：MEDIUM
- 详细判断理由：本地主动 close 后再读 close_code，可能给客户端贴错关码；close 抛错时跳过给客户端发 close 的逻辑，客户端收不到关码。
- 修复说明：在本地 close 之前读取并记录 upstream 已收到的对端 close_code（仅对端主动关闭时透传）；`upstream.close()` 包 try，异常只记日志，随后仍向客户端发送 close。补测试：客户端先断开时不透传对端码；close 抛错时客户端仍收到关码。

### A11. UDP mux 范围两套快照、runner 自解析 env

- 来源：review_intensive
- 位置：`supervisor/protocol.py:14`、`supervisor/network_policy.py:63`、`udp_mux.py:22-40`、`supervisor/runner.py:111-112`
- 优先级：MEDIUM
- 详细判断理由：同一 env 在不同消费者处语义不同，空字符串会导致 runner 启动崩溃而其它地方按默认值运行。
- 修复说明：进程启动时解析一次 `udp_mux_bounds()`，形成不可变配置对象注入 protocol 校验、policy 与分配器；runner 改用同一函数；非法 env 启动时 fail-closed 并给出明确错误。补测试：空 env 统一取默认；非法值启动报错。

### A12. socket slot 无属主校验即 unlink，root 长度不在启动时校验

- 来源：review_intensive
- 位置：`src/backend/cbrowser/runtime_agent/socket_root.py:32-41,97-103,118-131`
- 优先级：MEDIUM
- 详细判断理由：生产侧可直接 unlink 掉仍在服务的 socket；消费侧却有完整核验，两侧强度不对等；部署级配置错误应一次性 fail-closed。
- 修复说明：unlink 前校验属主 uid、类型为 socket 且不是活跃连接（connect 探测失败才清理），否则报冲突；`resolve_socket_root()` 按最长 slot 路径计算长度上限，超长则 Supervisor 启动失败。补单测。

### A13. runner 两个 watcher 的流生命周期耦合、container 竞态无测试

- 来源：review_intensive
- 位置：`supervisor/runner.py:307-321,348-359,387-394`；`tests/unit/test_t026_runner_network_events.py`
- 优先级：LOW
- 详细判断理由：network watcher 收尾会关闭 container 流；container 侧同类竞态未抽出、无测试。
- 修复说明：每个 watcher 只持有并关闭自己的流（`close_streams` 拆为按流关闭）；把 container 版竞态分支抽为与 network 版对称的函数，补「关停时关流且不 pump」测试。

### A14. 可信代理 CIDR 生产未接线，client_ip 解析器双副本

- 来源：review_intensive
- 位置：`api/app.py:199-201`、`gateway/server.py:191-193`、`compose.yaml`、`scripts/deploy.sh`、`.env.example`；`auth/client_ip.py`、`gateway/client_ip.py`
- 优先级：MEDIUM
- 详细判断理由：已抽验 compose / deploy / `.env.example` 中均无 `CBROWSER_TRUSTED_PROXY_CIDRS`，生产环境中所有请求的来源都是 Caddy 地址，登录、令牌与 viewer 限流按单一来源聚合，可被一个来源锁死所有人；鉴权链上的信任边界逻辑有两份副本。
- 修复说明：compose 的 edge 网络固定 IPAM 子网，由 deploy.sh 推导并注入 `CBROWSER_TRUSTED_PROXY_CIDRS` 到 API 与 Gateway；client_ip 解析器合并为一个共享模块，Gateway 镜像按文件白名单纳入；删除双导入防漂移测试，改为部署结构测试断言变量存在且与子网一致。

### A15. 错误契约残余不一致

- 来源：review_intensive
- 位置：`api/app.py:71-125,454-470`、`api/v1/auth_router.py:80-90`、`gateway/server.py` 各 handler、`supervisor/control_server.py`、`api/runtime_coordinator.py`（RPC 消费）
- 优先级：MEDIUM
- 详细判断理由：部分 handler 缺必填 `message`；dict 型 detail 与顶层字段重复嵌套；429 没有稳定错误码；Gateway / Supervisor 错误形态各异，Coordinator 丢弃响应体，运维无法区分失败原因。
- 修复说明：所有 handler 统一输出 `ErrorResponse`（error/message/retryable，可选结构化 `details`），去除 detail 整包嵌套；429 映射为 `rate_limited` 并带 `Retry-After`；Gateway 与 Supervisor 采用同一错误结构；Coordinator 解析并保留下游 `error` 与 `message`，写入 error_reason。同步前端断言与 OpenAPI 生成类型。

### A16. 新建环境无法选择字体集「无」，前后端默认集算法不一致

- 来源：review_intensive
- 位置：`src/frontend/src/features/profiles/ProfileForm.tsx:225-240`；`font_sets/manifest.py:376-397`
- 优先级：MEDIUM
- 详细判断理由：effect 会把用户选的「无」回填为默认集；前端按字符串排序取默认、不看完整性，会把能成功的提交变成 422。
- 修复说明：默认集只由后端按 `integrity_ok` 规则决定，前端删除自行推导逻辑。`GET /api/v1/font-sets` 返回每个平台的 `default_font_set_id`，创建表单以它预选；「无」是显式选项，提交显式 null，后端按显式 null 保存，不再套用默认。补组件测试与 API 测试。注：t053 同改 ProfileForm，实施时协调。

### A17. 代理改密污染无关 Profile 的新版快照

- 来源：review_intensive
- 位置：`src/backend/cbrowser/adapters/database/repository.py:1162-1195,1248-1310`
- 优先级：HIGH
- 详细判断理由：只被绑定版引用、当前版已改用其它代理的 Profile，会因无关改密被生成错误快照并永久无法启动，且没有提示指向真因。
- 修复说明：影响集按引用来源分别处理：当前配置引用 A 的才生成新版快照；仅绑定版（运行中）引用 A 的只发 runtime 事件（需重启生效），不建版；frozen revision 取快照实际引用代理的 revision。补测试：绑定版用 A、当前版用 B 时，A 改密不推进该 Profile 的版本。注：t052 重构代理模型，实施时合并考虑。

### A18. Runner 生成 fontconfig 失败时 fail-open

- 来源：review_intensive
- 位置：`src/backend/cbrowser/runtime_agent/fontconfig.py:66-103`、`runtime_agent/runner.py:498-500,583`
- 优先级：HIGH
- 详细判断理由：生成失败时回落系统 fontconfig，Linux 字体对指纹 Profile 重新可见，而状态仍按绑定集报告，指纹隔离可能静默失效；Supervisor 侧是 fail-closed，Runner 末端不一致。
- 修复说明：绑定了字体集时生成失败即启动失败，返回 `font_set_unavailable`，不再回落系统配置；未绑定时维持既有回退，并在状态中如实报告。补单测。注：t053 同改 fontconfig，实施时协调。

### A19. 字体集损坏无法通过导入修复，Coordinator 缓存永久「无缺失」

- 来源：review_intensive
- 位置：`font_sets/manifest.py:224-227`；`api/runtime_coordinator.py:318-335`
- 优先级：MEDIUM
- 详细判断理由：内容寻址目录已存在时直接返回，损坏集无法修复；缓存把「集不存在」记为无缺失且永不失效，导致展示面与启动面口径相反。
- 修复说明：导入时若目标目录 integrity 不通过，则以新内容原子替换（临时目录 + rename）；删除 Coordinator 的字体运行时缓存，每次按 Supervisor 同一校验函数实时读取，展示面与启动面同源。补测试：损坏集再导入后恢复；集缺失时报告缺失。

### A20. 字体集 used_by_count 跨平台串加、列表平台取目录名

- 来源：review_intensive
- 位置：`font_sets/manifest.py:143-155,347-375`；`repository.py:372-385`
- 优先级：LOW
- 详细判断理由：平台隔离在身份与计数层面不成立，会误导删除或改绑判断。
- 修复说明：引用计数按 (fingerprint_platform, font_set_id) 统计；list 路径校验 `manifest.platform == 目录名`，不一致标为 integrity 失败。补测试：两平台同 id 时计数各自独立。

### A21. display_number 可空列与领域模型不一致

- 来源：review_intensive
- 位置：`adapters/database/models.py:80`；`domain/models.py:204,224`；`repository.py:606-615,978-980,1025`
- 优先级：MEDIUM
- 详细判断理由：同一数据缺陷有三种表现；默认值 1 会静默冒充 #0001，造成容器身份错位。
- 修复说明：增量迁移把列改为 NOT NULL（无真实用户，存量均已回填）；领域模型去掉默认值，改为必填；读路径遇 NULL 统一抛明确错误。补测试。

### A22. 部署 prefix 无格式校验

- 来源：review_intensive
- 位置：`supervisor/container_spec.py:51-62`、`scripts/deploy.sh:48`、`supervisor/runner.py:537`
- 优先级：LOW
- 详细判断理由：prefix 直接拼入容器名和 compose project，非法值到 docker run 才以底层错误暴露。
- 修复说明：deploy.sh 与 Supervisor 启动时用同一规则校验（`^[a-z0-9][a-z0-9_]*$`，不含 `-`，避免与 `<prefix>-profiles`、`<prefix>-<NNNN>` 的命名空间重叠），非法即 fail-closed 并给出提示；补测试。

### A23. 分组/代理幂等键是死头，写表单缺防重

- 来源：review_intensive
- 位置：`src/frontend/src/shared/api/client.ts`（groups.create、proxies.create）；`api/v1/groups_router.py`、`proxies_router.py`；`features/proxies/ProxyFormDialog.tsx`；`features/profiles/GroupManagerDialog.tsx`；`ProfileForm.tsx:209-210,291`、`ProfileCreateDialog.tsx`、`shared/api/action_key_mutation.ts`
- 优先级：MEDIUM
- 详细判断理由：前端发送的幂等键后端不认，造成「已幂等」的假象；代理与分组表单无防重；Profile 创建的锁基于 React 状态，弹窗在途时可关闭重开并再次提交。
- 修复说明：后端为 groups / proxies 的 create/update/delete 实现与 Profile 相同的 Idempotency-Key 语义（同键同参重放返回原结果，同键异参返回 409）；ProxyFormDialog、GroupManagerDialog 写入口按 `mutation.isPending` 禁用；创建锁改用同步 ref，actionKey 绑定到「本次打开弹窗」的草稿，关闭重开沿用同一 key 直到成功。补前后端测试。

### A24. Profile 编辑全量提交回滚并发修改、缓存写入被 invalidate 抵消、capture_preview 分类分歧

- 来源：review_intensive
- 位置：`ProfileForm.tsx:53-58`（METADATA_KEYS）、`ConfigTab.tsx:44-48,59-62`、`useProfilesQuery.ts:87-90`、`repository.py:116-120`
- 优先级：HIGH
- 详细判断理由：全量提交会把其它客户端的修改以旧值写回，并产生内容倒退的配置版本；前端分类比后端少一类，扩大了触发面；setQueryData 后立即 invalidate，旧 GET 可回填旧值。
- 修复说明：编辑只提交与初始值不同的字段（PATCH 增量），字段分类直接引用生成类型或后端导出的分类常量，与 `INSTANT_FIELDS` / metadata 对齐；onSuccess 先 cancelQueries(detail) 再 setQueryData(detail)，去掉对 detail 的 invalidate，只 invalidate 列表查询。补测试：只改 timezone 时请求体只含 timezone。

### A25. 会话错误文案与 stage 双权威，迟到帧信号推进已停止会话

- 来源：review_intensive
- 位置：`features/browser-session/useBrowserSession.ts:150-168`、`SessionPage.tsx`
- 优先级：MEDIUM
- 详细判断理由：A20 只统一了 stage，错误文案与 timer 仍可与展示态分岔；后端 stopped 时迟到的帧信号会启动音频管线。
- 修复说明：errorMessage 与 stage 一并由 runtimeQuery 派生，hook 不再自行 getRuntime 写错误；帧信号放行条件增加「后端 observed_state 非 stopped/error」。补 hook 测试。注：p064 前端界面改造不在本项范围。

### A26. get_last_error 是有副作用的读，收敛判定不看 config_version

- 来源：review_intensive
- 位置：`api/runtime_coordinator.py:266-279,737,1129`、`runtime_views.py:46`、`api/v1/router.py:173`
- 优先级：HIGH
- 详细判断理由：任意读路径都会消费掉错误；新版启动失败的错误可能被一次普通 GET 抹掉，界面显示「无错误」但新配置从未生效。
- 修复说明：读取不清除；错误在「同一 config_version 的实例成功达到 running」事件到来时由写路径清除；收敛判定需绑定版本 == 产生错误的目标版本。补测试：旧版 running + 新版失败时，多次 GET 仍返回错误。

### A27. ErrorBoundary 丢弃错误、无日志、无复位

- 来源：review_intensive
- 位置：`src/frontend/src/app/ErrorBoundary.tsx`、`main.tsx`、`AppErrorPage.tsx`
- 优先级：MEDIUM
- 详细判断理由：任一渲染异常都会导致全应用错误页并销毁 WebRTC 会话，且诊断信息被静默丢弃。
- 修复说明：增加 componentDidCatch，经前端日志通道记录（不打 console 调试输出）；在 Router 内为路由级内容加 boundary，并以 location.key 作为 resetKey，路由切换即复位；根部保留兜底。补组件测试。

### A28. group_id/proxy_id 无服务层校验，reorder 接受子集

- 来源：review_intensive
- 位置：`services/profile_service.py`、`repository.py:281-295,1130-1140`、`groups_router.py`
- 优先级：LOW
- 详细判断理由：不存在的引用返回通用 409 而非字段级 422；子集重排会产生重复 sort_order。
- 修复说明：服务层校验 group/proxy 存在性，不存在则返回 422 并指出字段；reorder 要求 ordered_ids 为全集，否则返回 422；补测试。

### A29. 迁移守卫对空 alembic_version 放行，注释与实现矛盾

- 来源：review_intensive
- 位置：`adapters/database/migrations.py` `run_database_migrations()` 与顶部注释；`scripts/deploy.sh:69-73`；`docs/blueprint/supervisor.md:3`
- 优先级：LOW
- 详细判断理由：stamp 中断时给出最难懂的错误；过期注释会诱导把代码「修」回原缺陷。
- 修复说明：库中已有业务表但 alembic_version 为空或缺行时，抛 `LegacySchemaError` 并给出重建指引；把两处注释改为「链成员判定」口径；删除 supervisor.md 第 3 行过时陈述。补测试。

### A30. missing_fonts 被展示为完整性损坏

- 来源：review_intensive
- 位置：`features/browser-session/SessionDetailsPanel.tsx:240-247`
- 优先级：LOW
- 详细判断理由：探测覆盖缺失与 hash 完整性是两个概念，混为一谈会误导用户。
- 修复说明：区分两种文案：完整性取 font-sets 的 integrity，missing_fonts 显示为「探测字体未覆盖：…」；补组件测试。

### A31. 分组/代理参考数据缺跨客户端实时传播

- 来源：review_intensive
- 位置：`groups_router.py`、`proxies_router.py`、`useProfilesQuery.ts`
- 优先级：LOW
- 详细判断理由：参考数据的一致性比 runtime 数据弱一个量级；删组后行仍挂旧组。
- 修复说明：写端点成功后经现有 SSE 通道发布 `groups_changed` / `proxies_changed` 事件，前端收到后 invalidate 对应查询与 Profile 列表；补测试。

### A32. record_preview_capture 不校验 enabled

- 来源：review_intensive
- 位置：`adapters/database/repository.py:723-746`
- 优先级：MEDIUM
- 详细判断理由：撤销只能依赖 epoch 副作用，与 docstring 及 spec「四环节都校验」不符。
- 修复说明：落盘时同时校验 `profile.capture_preview` 为真，否则丢弃；补测试：不 bump epoch 地关闭后通知被丢弃。

### A33. Supervisor 预览观测「先记后验」，失败只打 debug

- 来源：review_intensive
- 位置：`supervisor/core.py:2014-2027,2040-2043`
- 优先级：LOW
- 详细判断理由：瞬时失败会永久丢帧，且运维不可见。
- 修复说明：校验与 POST 成功后才写入去重缓存；POST 非 200 记 warning（限频）；Profile 删除时清理 `_preview_captured_at` / `_preview_request_ids`。补测试。

### A34. 预览策略重发换新 request_id，pending 无条件 pop

- 来源：review_intensive
- 位置：`api/runtime_coordinator.py:796,813-822,830-838`；`supervisor/core.py:2121-2126,2206`
- 优先级：MEDIUM
- 详细判断理由：request_id 围栏在重试路径上空转；无条件 pop 会误删更新的待发策略，使策略不一致持续存在。
- 修复说明：pending 条目保存首次生成的 request_id，重发时复用；pop 改为比较后删除（只删除与自身 epoch/request_id 相同的条目）。补并发测试：epoch 7 失败、6 成功后，7 的 pending 仍在。

### A35. 预览提交两步写非原子、读端 TOCTOU、临时文件名只用 pid

- 来源：review_intensive
- 位置：`preview.py:45,136-137`；`api/v1/preview_router.py:51-77`
- 优先级：MEDIUM
- 详细判断理由：ETag 与返回字节可能不是同一帧；跨容器 pid 重合时 tmp 路径冲突，原子写前提不成立。
- 修复说明：帧文件按 captured_at 内容寻址命名，meta 原子指向当前帧文件，清理旧帧延后；读端先打开文件描述符再按该帧生成 ETag 并从 fd 输出；`_atomic_write` 临时名改为 uuid4 + O_EXCL。补测试。

### A36. 缩略图截取第一个 page 而非活动标签页

- 来源：review_intensive
- 位置：`runtime_agent/preview_capture.py:94-102`、`runtime_agent/agent.py:756-769`
- 优先级：MEDIUM
- 详细判断理由：多标签时会截到后台页，与 spec §3.1 不符，并扩大截图隐私面。
- 修复说明：Agent 以页面 `visibilityState` 判定活动标签（订阅 CDP `Target.targetInfoChanged` 维护 page 集合，逐 page 查询可见性），采集只针对活动 page；无法确定活动页时本轮跳过。补多 page E2E。

### A37. 生产采集无帧有效性校验，pixel-verified 声称不实

- 来源：review_intensive
- 位置：`runtime_agent/preview_capture.py:127-139`；对应 E2E 判据
- 优先级：MEDIUM
- 详细判断理由：已抽验，生产路径 b64decode 后直接落盘；损坏或截断的数据会被当成功帧。纯色帧可能是真实白页，不宜拒绝。
- 修复说明：落盘前校验 JPEG 魔数、可解码、尺寸与请求一致，不通过即丢弃并记录；E2E 改用带图案的测试页（判据为结构特征，非均值）；提交说明与文档不再使用 pixel-verified 表述。

### A38. 前端 preview SSE 无围栏

- 来源：review_intensive
- 位置：`features/profiles/useProfilesQuery.ts:451-460`
- 优先级：MEDIUM
- 详细判断理由：撤销后迟到的事件会复活缩略图，旧值还可能覆盖新值，与同文件 runtime 通道的围栏不一致。
- 修复说明：事件按 captured_at 单调比较后才写入，且只在当前缓存中 `capture_preview` 为真时写入；补测试。

### A39. checking_runtime 阶段的延迟 WS_CLOSE 不受守卫保护

- 来源：review_intensive
- 位置：`features/browser-session/useBrowserSession.ts:419-424,471-499`
- 优先级：LOW
- 详细判断理由：首检前的 1006 关闭会启动恢复轮询，之后覆盖已定版的诊断态。
- 修复说明：runtime 首检完成前收到的 WS_CLOSE 只记录、不启动恢复；首检定版为非 running 时取消同 generation 的轮询。补 hook 测试。

### A40. DESIGN.md 圆角双口径

- 来源：review_intensive
- 位置：`DESIGN.md`（components 与 Shapes 正文）；`EnvironmentCard.tsx`；`shared/ui/Dialog.tsx:30`；`scripts/design_tokens.mjs`
- 优先级：LOW
- 详细判断理由：设计权威内部自相矛盾，门禁没有断言。
- 修复说明：以实现与正文为准，把 components 中 card 改为 `rounded.lg`、modal 改为 `rounded.xl`；生成器把 components 引用导出为组件级变量，组件改用该变量，并断言正文中提到的组件 token 与 components 一致。

### A41. 颜色门禁扫描范围缺口

- 来源：review_intensive
- 位置：`src/frontend/scripts/design_tokens.mjs`（collectSources）；`public/logo.svg`、favicon、`index.html`、`public/theme_boot.js`
- 优先级：LOW
- 详细判断理由：public 资产与入口文件不在扫描范围内，「只用语义 token」的结论只在被扫子集内成立。
- 修复说明：扫描纳入 `public/**/*.{svg,html,js}` 与 `index.html`；品牌 logo 渐变在 DESIGN.md 中登记为品牌色 token，logo.svg 与 favicon 由生成器按 token 生成，不设 allowlist 例外；theme_boot 的颜色改为引用生成值。尺寸部分见 A62。

### A42. WCAG AA 声称无门禁背书

- 来源：review_intensive
- 位置：`src/frontend/scripts/design_tokens.mjs`；DESIGN.md Colors 节
- 优先级：MEDIUM
- 详细判断理由：声称不可复现，今后改色会静默失去保证；未证实疑点中已有色对疑似低于 4.5:1。
- 修复说明：生成器按 DESIGN.md 声明的前景/背景角色对计算对比度，正文文字 < 4.5、大字与图形 < 3.0 时失败；修正门禁发现的色对（含 dark on-surface-subtle、light warning）。补生成器测试。

### A43. deploy.sh 原子写无 fsync，发布指针两步写

- 来源：review_intensive
- 位置：`scripts/deploy.sh:228-234,318-327`
- 优先级：MEDIUM
- 详细判断理由：同一仓库有两套原子写标准；PREVIOUS / CURRENT 两步之间崩溃会导致 rollback 被拒。
- 修复说明：deploy.sh 的原子写改为调用 Python `atomic_write_text`（复用四要素实现）；把 current 与 previous 合并为一个指针文件（JSON），一次原子替换。补 fake 测试：模拟中途崩溃后指针自洽。

### A44. rollback 对读不到 stamp 时 fail-open

- 来源：review_intensive
- 位置：`scripts/deploy.sh:150-182,196-224,603-610`
- 优先级：MEDIUM
- 详细判断理由：DB 损坏时会先拉起目标栈再靠 readiness 兜底，与「变更前拒绝」目标不符。
- 修复说明：区分「库不存在」与「库存在但不可读」：后者在 deploy 和 rollback 中都拒绝并提示；注释写明两种语义。注：t051 把这段改为经容器访问 volume，实施时在 t051 中一并完成。

### A45. supervisor/gateway dockerignore 缺 pycache 排除，services 过度准入

- 来源：review_intensive
- 位置：`config/docker/supervisor_runtime/Dockerfile.dockerignore`、`config/docker/gateway_runtime/*.dockerignore`
- 优先级：LOW
- 详细判断理由：当前被白名单掩盖、尚不可达，但五镜像口径不统一，且上下文暴露面过大。
- 修复说明：两镜像补 `**/__pycache__`、`**/*.pyc`；supervisor 只准入 `services/__init__.py` 与 `services/tunnel_registry.py`；构建上下文测试覆盖全部五镜像。

### A46. check_node 的 `>` 语义与 verify_image_packages 对不可解析 marker fail-open

- 来源：review_intensive
- 位置：`src/frontend/scripts/check_node.mjs`；`scripts/verify_image_packages.py` normalise()
- 优先级：LOW
- 详细判断理由：实现与自述的 fail-closed 不符；目前未触发，但校验器语义必须与声明一致。
- 修复说明：`>` 按严格大于判定；marker 解析失败时抛错退出；TARGET_ENV 补齐 platform_machine 等键，取目标镜像平台值。补单测。

### A47. 门禁共享 venv 无锁，清理按静态前缀误删其它会话容器

- 来源：review_intensive
- 位置：`scripts/run_gates.sh:9-23,51-62,231`；`scripts/gate_container_cleanup.py:29-46,82-97`
- 优先级：HIGH
- 详细判断理由：多 worktree / 多会话并行跑门禁是本项目常态，双会话时必然触发，与 p051 同源，且归因未覆盖到门禁清理本身。
- 修复说明：venv 的检查、重建与安装全程持有 `flock`（锁文件放在 venv 父目录），pytest 运行期持共享锁；每次门禁运行生成 run_id，容器与网络都打 `com.cbrowser.gate-run=<run_id>` 标签，启动清理只删除标签对应运行已结束的资源（以 run_id 存活标记判定），网络同样要求标签归属，删除名称回退放行逻辑。补测试。

### A48. E2E/门禁断言强度缺口

- 来源：review_intensive
- 位置：`tests/fixtures/frontend_app_probe/harness.py:142-169`、`tests/e2e/test_runtime_coordinator_e2e.py:82-88,141-147`；`scripts/run_gates.sh:95-102,125-145,180-210,247`
- 优先级：HIGH
- 详细判断理由：停止断言存在单容器泄漏假绿；普通套件无用例数下限；image_packages 在未设变量时空转通过；protocol_drift_check 脱离 evidence 体系。
- 修复说明：探针分别返回 browser/stream 各自的存在状态，停止断言要求两者都不存在，Docker 异常单独报错；finish_evidence 为每个 suite 设最小用例数（写入 testing.md），低于下限即失败；image_packages 未设变量时记为 skipped 而非 passed（完整门禁中视为失败）；protocol_drift_check 作为首个 suite 纳入 evidence。

### A49. 真实引擎证据校验器生产路径不校验镜像身份

- 来源：review_intensive
- 位置：`scripts/automation_probe_evidence.py:73-100,127-145,246`
- 优先级：MEDIUM
- 详细判断理由：A38 声称的单一 verdict 只验证了「文件存在」，可用伪造的 image.json 得到 all_passed。
- 修复说明：main() 调用 `preflight_problems`；evaluate_evidence 校验 image id 格式及 os/arch 与本次运行一致；shell 侧预检改为调用同一函数。补测试。

### A50. 门禁接线测试多为子串存在性断言

- 来源：review_intensive
- 位置：`tests/unit/test_t044_gate_contract.py`、`test_a38_probe_evidence.py`、`test_a30_build_wiring_suite.py`
- 优先级：MEDIUM
- 详细判断理由：只能防整段被删，防不住位置或条件接错；内嵌的全量收集子进程拖慢 unit 套件。
- 修复说明：改为以 fake 命令（PATH 注入桩）执行脚本，断言调用顺序与条件；删除内嵌全量收集子进程用例，改为在门禁中以独立步骤校验收集数（与 A48 用例下限合并）。

### A51. E2E 前置封闭全有全无

- 来源：review_intensive
- 位置：`tests/e2e/conftest.py`
- 优先级：LOW
- 详细判断理由：方向正确（fail-closed），但粒度过粗，与同文件「scoped」原则矛盾，会诱导绕开 required 模式。
- 修复说明：各 E2E 模块用 marker 声明所需镜像，required 模式只校验被收集用例声明的镜像集合；未声明的用例按全集校验（仍 fail-closed）。补测试。

### A52. 隐私门禁当前为红：p063 含开发者家路径

- 来源：review_intensive
- 位置：`docs/archive/pending/p063_platform_font_sets_path_mismatch.md:20`（已由 18e343f 从 todo 迁入 archive）
- 优先级：HIGH
- 详细判断理由：已抽验仍含两处 `/Users/...` 原文，`test_repo_hygiene.py` 在 HEAD 必然失败。归档 pending 原则上只准新增，但隐私脱敏与 t049/t050 先例一致，属必要例外。
- 修复说明：把两处路径改写为 `<repo>/data/v2/fonts`、`<repo>/data/fonts`；运行 `test_repo_hygiene.py` 验证转绿。

### A53. 隐私豁免粒度为整文件，allowlist 失效条目累积，扫描器有形态缺口

- 来源：review_intensive
- 位置：`tests/unit/test_repo_hygiene.py`（is_approved_snapshot、正则、tracked_files）、`tests/unit/review_privacy_allowlist.txt`、`docs/archive/handoff.md`、t047 的 `review_general.md` / `task.md`
- 优先级：MEDIUM
- 详细判断理由：整文件指纹豁免等于给泄漏内容发许可证，高频改动的 handoff.md 会让新泄漏随指纹刷新一并被豁免；21 条旧路径条目与 4 条失效指纹使审计语义失真；正则与扫描范围有漏检边界。
- 修复说明：把 `docs/archive/handoff.md`、t047 两文件及 allowlist 覆盖的全部文件中的家路径改写为 `<repo>` 等占位符，删除 `review_privacy_allowlist.txt` 与指纹豁免机制本身，泄漏一律改写、不豁免（与 A54 口径一致）；正则允许用户名后紧跟结尾或引号；扫描范围加入 `git ls-files -o --exclude-standard` 的未跟踪文件。

### A54. 声明脱敏口径（仅 tracked 树）

- 来源：review_intensive
- 位置：`docs/blueprint/security.md` 或 `docs/blueprint/conventions.md`
- 优先级：LOW
- 详细判断理由：仓库对同类泄漏有三种处理，却没有声明威胁模型，后续执行者只能靠猜。改写 git 历史会破坏所有已存在的 commit 引用（task、review、pending 均以 commit hash 溯源），不采纳；口径须显式声明。
- 修复说明：写明「隐私口径 = 当前 tracked 树与新提交不得含家路径与凭据；不改写 git 历史；处理方式统一为改写为占位符，不使用整文件豁免」。

### A55. v2 标识残留清理与守卫

- 来源：review_intensive
- 位置：`.env.example:1`、`docs/blueprint/gateway.md:3`、`persistence.md:5`、`security.md:3`、`docs/specs/browser_isolation.md:5`、`profile_management.md:3`、`src/backend/cbrowser/` 下 8 处 docstring
- 优先级：LOW
- 详细判断理由：已抽验 `.env.example` 首行仍为 `# CBrowser v2 deployment.`；清理靠逐文件名单，缺少守卫，同类残留会持续新增。
- 修复说明：删除上述现行面的 v2 自称；`deploy.sh` 默认数据根由 `data/v2` 改为无代际名（如 `data/instance`），不做旧路径兼容（本机旧目录改名保留，不迁移内容）；`0001_baseline_v2.py` 改文件名，revision id 不变（不改写已部署 revision 的结构身份）。增加 hygiene 测试，禁止现行文档、源码、脚本中出现产品代际标识，不设例外。注：t051 同改 deploy.sh 与数据挂载，实施时合并。

### A56. docs/handoff.md 过期

- 来源：review_intensive
- 位置：`docs/handoff.md`
- 优先级：MEDIUM
- 详细判断理由：已抽验仍停留在 2026-11-09 的 `1ff4721`，会误导按 handoff 恢复工作的会话。
- 修复说明：旧节迁入 `docs/archive/handoff.md`；新写一节，含当前 branch、head_commit、backlog t051–t053、pending 现状（todo p061/p064/p065）、门禁状态（隐私门禁红，A52 修复前不得声称全绿）。

### A57. p068 根因表述强于证据，p059 对 Browser 路径失实

- 来源：review_intensive
- 位置：`docs/tasks/t051_runtime_deploy_reliability/task.md`「背景」第 1、3 条
- 优先级：MEDIUM
- 详细判断理由：p068 当前只有日志文案，没有扩展错误码，「已定位 shm mmap」是推测。用户已裁决将 DB 移入 named volume（存储方案不重开），但 task 背景应如实表述证据强度，并把扩展错误码采集作为首要可观测项。p059 部分 t051 背景已按实际写明（Browser 主路径保留未脱敏的 `{e}`）。两份 pending 已归档，按 archive 只准新增的规则不改原文，只在现行 task 中修正。
- 修复说明：t051 背景第 1 条改为「高度疑似 WAL `-shm` 跨 VM bind mount 失稳（日志仅有 `disk I/O error`，未记录扩展错误码，尚未区分 IOERR_SHMMAP 与 IOERR_READ/WRITE）」，并注明迁移 named volume 依据为 SQLite WAL 同机共享内存要求与用户裁决；上下文区补一句「AC-007 的扩展错误码日志用于下一次故障时定性」。

### A58. redact_evidence 覆盖面弱于保证

- 来源：review_intensive
- 位置：`scripts/redact_evidence.py`
- 优先级：MEDIUM
- 详细判断理由：不处理 URL 内嵌凭据（代理 URL 是本项目日志的现实形态）、其它 cookie 名，含空格的值也只脱敏一半；t051 的 Docker 错误脱敏需要同一套规则。
- 修复说明：抽出共享脱敏模块（URL userinfo、Bearer、任意 cookie 值、敏感键值的完整引号值、家目录路径），redact_evidence 与 t051 的 Supervisor Docker 错误脱敏共用；补凭据形态矩阵测试。

### A59. 沙箱归属判定只凭可伪造标签

- 来源：review_intensive
- 位置：`scripts/deploy.sh:380-395`；`supervisor/container_spec.py`（沙箱标签）
- 优先级：LOW
- 详细判断理由：当前的归属判定以任何人都能写的标签作为证据，设计上不成立：伪造标签可以绕过冲突拒绝，标签缺失又会误报冲突。即使同一信任域内利用面有限，归属判定也应基于实例自身持有的身份，而不是可伪造的名字和标签。
- 修复说明：部署时为实例生成 `instance_id`，写入 release 状态；compose 服务与 Supervisor 创建的全部沙箱都带 `com.cbrowser.instance-id=<instance_id>`；deploy.sh 的冲突判定与 Supervisor 的扫描都以「标签值 == 本实例 instance_id」作为唯一归属依据，删除基于 project 名的豁免。补 fake Docker 测试：伪造 project 标签但 instance_id 不符时拒绝。

### A60. 迁移中的历史形态容错与 downgrade 删除

- 来源：review_intensive
- 位置：`migrations/versions/0003_network_transaction.py:37-52,88,134-140`、`0004_preview_backoff.py:42-69`、0005 downgrade；第 106–109 项
- 优先级：LOW
- 详细判断理由：这些缺陷都出在为「历史混合形态」写的容错分支和不可逆的 downgrade 上。零兼容原则下，这类分支本身就不应存在：容错会把定义错误的 schema 静默 stamp 到 head，downgrade 会破坏 generation 单调性。根因修正是删除这些分支，不是逐一补强。修改范围限于不影响 upgrade 产物结构的代码，符合「已部署 revision 不改结构身份」的约束。
- 修复说明：0004 删除「列已存在即跳过」分支，改为直接 `add_column`，形态不符即失败；0003 删除对 decision / 指针混合形态的修补分支；全部 revision 的 `downgrade()` 改为抛出明确的「不支持降级」错误，并在 persistence.md 声明迁移只前进、回退靠 release 回滚 + 数据目录重建。0003 相关表随 A61 的网络事务删除（新增增量迁移），本项只处理其余 revision。补测试：降级调用失败。

### A61. 网络配置回到部署期，删除运行时网络应用与 LAN（原 D1，覆盖 33 个问题）

- 来源：review_intensive
- 位置：`gateway/config.py`、`gateway/server.py`、`network_config.py`、`services/network_service.py`、`api/v1/network_router.py`、`supervisor/control_server.py`、`supervisor/core.py`（rebuild-edge / converge / fencing / `_get_applied_network_config`）、`supervisor/network_policy.py`、`supervisor/operation_journal.py`、`repository.py:1422-1440,1792-1801`、`scripts/deploy.sh`（指纹、rollback）、`compose.yaml:23,56`、`features/settings/SettingsPage.tsx`；问题第 24–40、43–54、59–62、102、113、114 项
- 优先级：HIGH
- 详细判断理由：33 项全部出在运行时修改网络配置（HTTPS 端口、LAN）的跨进程链路上：API / Gateway / Supervisor / 磁盘四方各持一份状态，没有统一的收敛证明，且 LAN 媒体面未接线。用户已在 p053 放弃原生 LAN，剩下的运行时需求只有改端口。根因修正是删除这条链路，把真相源收敛为部署产物，而不是逐点加固。
- 用户决策：C（2026-11-10）
- 修复说明：
    1. 删除 LAN：设置页 LAN 开关与 IP 输入、`lan_access_enabled` / `lan_advertised_ip` 模型字段与校验（`domain/models.py:840-871`、`network_config.py:25-40`）、`allow_lan_media` 与 LAN 媒体策略分支、Stream `bind_host` / `advertised_ip` 参数与标签、root-ca 下载端点与前端链接；Caddy 与 Stream UDP mux 固定绑定 `127.0.0.1`。
    2. 删除运行时网络应用：API 网络设置写接口与 apply / disconnect 预检、`NetworkService` 事务、Gateway publication 协议（authorize / ACK / revoke 与对应密钥用途）、Supervisor `rebuild-edge` / `converge-streams` 端点、restore fencing、operation journal 中的网络回执、已应用状态双文件；以增量迁移删除网络事务、pending / applied 配置表。
    3. 端口单一来源：`CBROWSER_HTTPS_PORT` 只由 `.env` 决定，deploy 时生效；默认端口收敛为一个常量（第 34 项），删除 `api/main.py`、`network_config.py`、前端中的重复字面量。
    4. Origin 白名单由部署配置确定性派生（本机 `127.0.0.1` / `localhost` + 端口），API 与 Gateway 从同一部署输入读取；Gateway 删除磁盘状态重读的死代码。
    5. 部署指纹改为哈希最终 Caddyfile 产物（第 32 项）；rollback 使用目标 release 记录的端口与 Caddyfile，不再存在运行时漂移（第 33 项）。
    6. 设置页保留只读网络信息（当前访问地址与端口），删除网络设置表单（第 102 项随之消失）。
    7. 新增 ADR：网络配置为部署期配置，替代 ADR 026 的运行时边缘重建部分，记录前提变化（p053 放弃 LAN）；更新 `docs/specs/access_control.md` 的 LAN 段、`docs/blueprint/gateway.md`、`supervisor.md`、`security.md`；p053 保持 parked，日后复活时按新需求重新设计。
    8. 测试：删除网络事务、publication、fencing、LAN 相关测试，并写明删除理由；新增结构测试，断言 compose 端口仅绑定 loopback、API 无网络写端点、Gateway 白名单来自部署输入。

### A62. 尺寸与间距工具类全部纳入设计 token 门禁（原 D2）

- 来源：review_intensive
- 位置：`src/frontend/scripts/design_tokens.mjs`、`DESIGN.md`（spacing、components）、`Popover`（`w-72`）、各组件 `h-9` / `py-0.5` 等数值类；问题第 104 项尺寸部分
- 优先级：LOW
- 详细判断理由：DESIGN.md 是间距与组件规格的唯一权威，散落的数值工具类构成了第二套事实源。
- 用户决策：A（2026-11-10）
- 修复说明：间距（padding / margin / gap / space）全部改用 spacing token；组件宽高（控件高度、浮层宽度、图标尺寸等）写入 DESIGN.md components 规格，由生成器导出组件级 CSS 变量，组件引用变量；门禁拦截全部数值型尺寸与间距工具类（含任意值 `[...]`），不设例外；补生成器测试与门禁负例测试。

## 不采纳项

### R1. t050 前创建的存量沙箱被孤儿化

- 来源：review_intensive
- 位置：`supervisor/docker_adapter.py:657-668,1695-1715,1998-2036`
- 优先级：MEDIUM
- 详细判断理由：项目无真实用户、明确不做兼容与数据迁移（memory no-legacy-data）；t050 已声明升级后重建一次沙箱，本机实例已完成重建。为旧命名容器写检测或兜底代码属于兼容包袱。

### R2. e9d247f 以「脱敏」标题夹带 pending 结案

- 来源：review_intensive
- 位置：提交 `e9d247f`
- 优先级：LOW
- 详细判断理由：事实成立，但已进入主干历史，修正需要改写 git 历史（破坏性，A54 已声明不改写历史）。p054/p056/p058 的结案依据仍可从各归档文件的「处理」行追溯。仅作为流程教训，不做代码或文档变更。
