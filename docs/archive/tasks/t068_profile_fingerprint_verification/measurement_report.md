# t068 本地指纹基线与引擎升级回归门禁：测量报告

本文件是入库的可定位结论摘要。完整机器可读证据位于本 worktree 忽略目录
`.scratch/t068/evidence/`（`finish` 前已生成，流程清理前按先例复制到同级
`CBrowser_t068_evidence/.scratch/t068/` 保留）。

## 1. 环境与制品身份（AC-003）

- 宿主：MacBook Pro M1 Max / macOS / OrbStack Docker 29.4.0 `linux/arm64`。
- 唯一已获准 `linux-arm64` 引擎制品（ADR 021 锁定 `cloakbrowser[geoip]==0.6.4`）：
    `chromium-146.0.7680.177.3`，`chrome` SHA-256
    `3cf5231598c4fd44be1ed10c58cab4a1d59cd18b05a4800c73b946e0bfc4d34f`（另固定 14 个运行时文件，见
    `src/backend/cbrowser/engine_artifacts.py`）。
- 下载层信任根：`cloakbrowser==0.6.4` 内硬编码 Ed25519 公钥
    `MKFKwIhUcKWq5xTuNA0Ovg99njcDEcEJvmWYYhApvaU=` 对
    `chromium-v146.0.7680.177.3/SHA256SUMS` + `SHA256SUMS.sig` 验签，
    `version=` 绑定 + 压缩包 SHA-256 `8b71ce53…`（实测 `Ed25519 verified OK`）。
- 解压后完整性：上游无 per-file 签名，`ensure_binary()` 命中缓存即不校验；CBrowser 在
    `deploy.sh` / Supervisor `cache_init` / `BrowserRunner` 三处以仓库清单校验
    15 个文件 SHA-256 + ELF machine + `--version`，并强制
    `CLOAKBROWSER_AUTO_UPDATE=false`、拒绝 `CLOAKBROWSER_DOWNLOAD_URL` /
    `CLOAKBROWSER_SKIP_CHECKSUM` / `CLOAKBROWSER_LICENSE_KEY` / 自动更新 marker。
- 交付镜像（本 worktree 源码重建，不可变 ID）：
    `CBROWSER_RUNTIME_TEST_IMAGE=sha256:cf7a4dd7383e3c2c1aab2f2a0c38a437ba9bbbcf510a39ca077b4296fd46b1b4`，
    `CBROWSER_SUPERVISOR_TEST_IMAGE=sha256:197e57f79adcaf60cedaf5ef192fe7e998b5006c46f8b7d04d5ba2277d98a70a`，
    `CBROWSER_API_TEST_IMAGE=sha256:d1d62366eec2ae5efa98a92ca6ab5b57c5d3f0a09ee2fb9aaeab68f5f3e98751`。
- 探针版本：`cbrowser-fp-probe/v1`，报告 schema `cbrowser-fingerprint-report/v1`。

## 2. 测量方法（AC-001）

真实 Docker `browser_runtime` 容器内以生产 `BrowserRunner`（Xvfb + PulseAudio +
CloakBrowser SDK）启动 `chromium-146.0.7680.177.3`，访问同机 `127.0.0.1` 受控
HTTPS 服务（自签证书经浏览器级 CDP `Security.setIgnoreCertificateErrors` 建立安全
上下文），采集主文档 / 同源 iframe / dedicated Worker / ServiceWorker 四上下文的
18 项 API 与请求头，并在 TLS 层 `MSG_PEEK` 抓 `ClientHello` 计算 JA3 / JA4。
Profile `prof-e2e-01` / config version 1，windows 平台 + 已导入 windows 字体集
`71e2df2b…`（离线 `fc-list` Linux 字体命中 0）。

## 3. 跨上下文矩阵与噪声（AC-001 / AC-002）

|上下文|支持 `ok`|`unsupported_context`|
|---|---|---|
|main|18|0|
|iframe|18|0|
|worker|13|`webdriver` `pdfViewerEnabled` `screen` `audio` `webrtc`|
|service_worker|13|`webdriver` `pdfViewerEnabled` `screen` `audio` `webrtc`|

- `canvas2d` / `webgl` / `fonts` / `uaDataHigh` / `storageEstimate` 在 Worker/SW 通过
    `OffscreenCanvas` 等实测可用；缺测与不支持上下文分别以 `missing` /
    `unsupported_context` 标注，不当作无漂移。
- 请求头差异：`main`/`iframe`/`main-fetch` 带全套 `Sec-CH-UA*`；`worker_fetch` /
    `sw_fetch` 仅 `User-Agent` / `Accept-Language`。
- 重复采样分布（AC-002）：同 Profile 新目录重复 3 次 18 项 JS 指标全确定；
    `ja3` 因 BoringSSL 每次握手随机打乱扩展顺序而逐连接变化（2 样本 18 次握手 `ja3_raw` 18 个不同值），
    `ja4` 稳定收敛为 `{t13d1516h2_8daaf6152771_d8a2da3f94cd, t13d1517h2_8daaf6152771_b6f405a00624}`
    （首次握手 / TLS 1.3 PSK 复用），`ja3_sorted` 与 JA4 一致；`storageEstimate.usage`
    随 SW 注册状态变化，`webrtc` 候选含随机端口/ufrag。非确定字段以分布记录，
    未用未知阈值宣称一致。

## 4. TLS / UA / Client Hints 一致性（AC-006）

`consistency=consistent`、`tls_status=verified`，结论绑定
`engine_build` / `binary_sha256` / `config_version` / `probe_version` 与实际
`ClientHello` + HTTP 头 + 四上下文 JS 值。windows UA `x64` 与 UA-CH `architecture=arm`
的差异为已知 `d032`/`p045` 暂搁项，如实记录。无本地 TLS 采集能力时
`verdict=inconclusive`，绝不引用厂商通过率。

## 5. 升级门禁四场景（AC-002 默认阻断）

|场景|baseline → candidate|决策|阻断原因|
|---|---|---|---|
|strict 默认|baseline ↔ 同制品重复|`blocked`|`non_deterministic_variance:tls.ja3_raw`（未获批方差）|
|显式批准 `tls_extension_shuffle_via_ja4`|baseline ↔ 同制品重复|`approved`|0 diffs|
|TLS 采集关闭|baseline ↔ HTTP-only|`blocked`|`inconclusive:tls_capture`|
|输入漂移（seed 290029→333333）|baseline ↔ 漂移|`blocked`|16 处 `unapproved_drift`：`main`/`iframe`/`worker`/`service_worker` 的 `canvas2d` `webgl` `audio` `fonts` `storageEstimate`|

另有制品负向（真实 `cache_init` helper 与 `verify_extracted_engine_cache`）：
损坏 `libGLESv2.so` → `corrupted_engine_file`；损坏 `chrome` → ELF/哈希拒绝；
`latest_version_*` marker → `auto_update_marker_present`；绕过环境变量 →
`auto_update_bypass_env`；均 fail-closed。

## 6. 未能验证项（逐项原因）

1. **真实跨版本引擎升级比对**：本机只有一套已获准 `linux-arm64` 制品
    （`146.0.7680.177.3`）；`146.0.7680.177.5` 为 `linux-x64` 且未在本地实测解压文件哈希。
    未下载/构造第二套未批准 arm64 引擎（遵守 ADR 021）。改用「同制品重复 +
    受控输入漂移 + 制品损坏」验证门禁两条分支，跨版本真实放行未宣称通过。
2. **`linux-x64` 制品解压完整性**：仓库清单只固定了压缩包 SHA-256，无该平台解压后
    per-file 哈希；显式标注 `TRUST_SOURCE_X64_ARCHIVE_ONLY`，不冒充已验。
3. **公网第三方 TLS/JA3/JA4 检测站、IP 视角一致性**：不在本地受控范围，
    按 task 口径不参与、不引用厂商通过率。
4. **JA3 厂商式"完全一致"结论**：本地实测证明 `ja3` 逐连接变化，故以 `ja3_sorted`
    - `ja4` 作为可复现身份，raw JA3 仅作分布记录；不宣称 raw JA3 跨连接一致。

## 7. 证据清单（`.scratch/t068/evidence/`，SHA-256）

|文件|SHA-256|
|---|---|
|baseline.json|`e8c45e5864c184b0631b5ef1b4cb0d875003d819f5613106b450b6275aac7f04`|
|candidate_same.json|`1db1b487c6a39c1b265720b39be084accf636702009b4e18143871ca2e509283`|
|candidate_no_tls.json|`ce16fa96cf01784fe42a57dfc85e1d7204c7293369a0d5a1425f4b6aec98d74a`|
|candidate_seed_drift.json|`2752284adc8b248b8cd93bcd7173f766ce06365ad8de4b78fa3f235fcb042852`|
|diff_strict.json|`1b6bc2538a577dea2e606ab5372a3feb488f99bdf3215d965b7af23fbed76bf7`|
|diff_approved.json|`0371ce660f322a47d6d02f124eb9996cf9ad4d5045f5ea09d6eebb73894620b9`|
|diff_no_tls.json|`b5656bb6af171ff8e4100b977771437a96874cbd3e6a0fd13b695fcc06651857`|
|diff_seed_drift.json|`4bed4dd609fa164d41fa5657e1f4b4752ed0833508a4e029919cd8b9c50bda90`|
|diff_strict.md|`fa3be18c18db3b36d24d06b8b656e39831942e3eaad395003a65b2e870d99980`|
|diff_approved.md|`3bc16831e829e7507301d5612428b8a47bd6d5a446e61b74d9cd8d9313d33fea`|
|diff_no_tls.md|`743f4d3915b94896190d4c976ef98540ae3bbb5e19a849995b7e2ce39ea40a07`|
|diff_seed_drift.md|`d2148ccc476494f502479043720493eea6fb2247fc2e42c72ab31e9bb6c33f78`|
|profile_config.json|`72dc49d154b9d0917d6425202873695bc7ef5973ccffa0a0749ce5362deb5637`|
|profile_config_drift.json|`3f057b6206c394076f130f182a525f12c689230489ac32a2258449a57e5f2cbe`|
