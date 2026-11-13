# 需求规范：引擎制品固定与本地指纹升级门禁 (engine_upgrade_fingerprint_gate)

累积 t068 交付的引擎升级工程回归门禁契约。完整实测数据见
`docs/tasks/t068_profile_fingerprint_verification/measurement_report.md`。

## 1. 目标与边界

为 `cloakbrowser==0.6.4`（ADR 021）锁定的引擎制品建立「固定可校验 + 本地指纹
基线 + 升级默认阻断」的封闭链路。不新增身份模型、Persona 工厂、预热爬虫或
自检 UI；不下载/构造违反 ADR 021 的未批准引擎版本。TLS/JA3/JA4 结论只在本地
受控握手可采集时给出，不可判定明确标注。

## 2. 引擎制品固定与完整性（AC-003）

- 唯一权威清单 `src/backend/cbrowser/engine_artifacts.py`：按
    `(platform_tag, engine_build)` 登记批准制品。当前 `linux-arm64` 固定
    `146.0.7680.177.3`，含 `chrome` 与 14 个运行时文件的 SHA-256、ELF machine、
    `--version` 期望值、压缩包 SHA-256 与信任来源。
- 信任来源分层：下载层为 `cloakbrowser==0.6.4` 内硬编码 Ed25519 公钥验签
    `SHA256SUMS.sig` + `version=` 绑定 + 压缩包 SHA-256；解压层为 CBrowser 仓库
    per-file SHA-256 清单（上游无解压产物签名，如实说明，不伪造 Ed25519 覆盖解压件）。
- `deploy.sh` 发布前校验引擎缓存（含 release manifest 的 `engine` 块与
    `CLOAKBROWSER_AUTO_UPDATE=false`）；Supervisor `cache_init` helper 在容器内
    `verify_wrapper_package` + `enforce_pinned_engine_env` + `ensure_binary` +
    `verify_extracted_engine_cache`；`BrowserRunner.resolve_engine_binary` 启动前
    再次全量校验。
- 强制拒绝：解压文件损坏/身份不符、未批准 `engine_build`、自动更新 marker
    （`latest_version*`）、`CLOAKBROWSER_AUTO_UPDATE != false`、
    `CLOAKBROWSER_DOWNLOAD_URL` / `CLOAKBROWSER_SKIP_CHECKSUM` /
    `CLOAKBROWSER_LICENSE_KEY` 绕过。自动更新不能绕开门禁。
- `linux-x64` 制品只登记压缩包 SHA-256（本机无解压实测），显式标注
    `TRUST_SOURCE_X64_ARCHIVE_ONLY`，不冒充已验。

## 3. 本地指纹基线与差异报告（AC-001）

- 探针 `cbrowser-fp-probe/v1`（`src/backend/cbrowser/fingerprint_verification/`）
    复用生产 `BrowserRunner` + 离线 CDP/字体探测，在真实 Docker 容器内访问同机
    受控 HTTPS 服务（TLS `MSG_PEEK` 抓 `ClientHello` 计算 JA3/JA4）。
- 报告记录 Profile id、config version/配置摘要、引擎制品、探针版本与采集上下文；
    覆盖主文档 / iframe / Worker / ServiceWorker 的 18 项 API 与请求头，
    每个 `(context, metric)` 标注 `ok` / `unsupported_context` / `missing` / `error`，
    缺测与不支持上下文明确区分，不归为无漂移。
- 确定性字段要求逐值一致；非确定字段（raw `ja3`、`storageEstimate.usage`、
    WebRTC 候选）记录重复采样分布，不用未知阈值宣称一致。
- 差异可定位到 `layer / context / field / classification` 并给出处置动作。

## 4. 升级默认阻断（AC-002）

- 任一未批准漂移、缺测（`missing`/`error`）、上下文支持翻转、
    未获批非确定方差或不确定结论一律 `upgrade_decision=blocked`。
- 同制品重复在严格默认下因 raw JA3 方差被阻断；只有在用户显式批准
    `tls_extension_shuffle_via_ja4` 归一化规则后，主体一致性（JA4 + `ja3_sorted`
    集合 + 确定性 JS/HTTP）通过才 `approved`。
- 真实跨版本升级放行须有第二套已获准制品的完整基线；本机只有一套 arm64
    制品，故跨版本真实放行未宣称通过，以「同制品重复 + 受控输入漂移 +
    制品损坏」验证门禁两条分支。

## 5. TLS / UA / Client Hints 一致性（AC-006）

- 结论绑定实际 `ClientHello`、HTTP 请求头、四上下文 JS 值，以及
    engine/config/probe 版本；无本地采集能力标 `inconclusive`，不引用厂商通过率。
- 本地实测结论：BoringSSL 每次握手随机打乱扩展顺序，`ja3` 逐连接变化，
    `ja4` 收敛为 `{首次握手, TLS1.3 PSK 复用}` 稳定对；windows/macos 共用同一
    Linux BoringSSL TLS 栈。windows UA `x64` 与 UA-CH `architecture=arm` 为
    `d032` / `p045` 已知暂搁项，如实记录。

## 6. 验收标准（摘要）

完整 AC 与可测试性声明见 `docs/tasks/t068_profile_fingerprint_verification/task.md`。

- [x] AC-001：同 Profile/config version 产出可定位 API/请求层差异报告，缺测与不支持上下文区分。
- [x] AC-002：未批准漂移/缺测/不确定结论默认阻断，四上下文完整矩阵，非确定指标用分布。
- [x] AC-003：发布与 cache_init 固定可校验制品，损坏/身份不符被拒，自动更新不能绕过；上游无解压签名如实说明。
- [x] AC-006：TLS/UA/Client Hints 一致性绑定实际证据与版本，无采集能力标不可判定。
