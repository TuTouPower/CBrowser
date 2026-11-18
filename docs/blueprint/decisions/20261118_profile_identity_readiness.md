# ADR 040：Profile 运行身份统一与字体真实就绪（t075）

日期：2026-11-18。状态：已采纳，随 t075 实施。

## 背景

t041/t053/t081 累积的身份契约在四个点上自相矛盾（p116/p124/p125）：

1. 字体集名义上由用户在表单手选（含显式「无」），但默认选择逻辑散在
    前端推导、后端 A16「未提供才套用」与目录默认三处，同一 Profile 的
    绑定来源不可追溯；`font_set_id = null` 时运行时回退暴露镜像内 Linux
    基础字体，与「可见字体只来自绑定集」的隔离契约直接冲突，状态只能
    靠 `missing_fonts` 里的文字标记区分。
2. CJK 暴露由 `locale` 在 fontconfig 生成时隐式决定，语言与字体是两
    个独立可变字段，联动规则只存在于前端表单，后端改语言不改字体、
    改字体不看语言，克隆/直连 API 路径全部绕过。
3. `gpu_family` 提供 auto/nvidia/intel 手选，但 s026 实证 SDK 无 GPU
    选择面（d051）：所谓选择只是把一个 Chromium flag 透传给引擎，不
    校验平台与种子，macOS×NVIDIA 等组合无真实硬件对应——契约在卖不
    存在的能力。
4. 字体「就绪」没有单一事实：目录记静态结论、Agent 每次健康检查重
    扫、Supervisor 启动校验各说各话；挂载源不存在时 Docker daemon 会
    把 volume subpath 建成空目录，实例能以零字体启动成功。

## 决策

1. **字体绑定后端托管**：`font_set_id` 不再是用户可写字段。服务在创
    建、克隆与切换平台时按资产目录默认规则（verified 集按最近验证时
    间胜出，ADR 030）解析并写定绑定；字体根已配置时（一切真实部署，
    deploy 恒设 `CBROWSER_FONTS_DIR`）平台无可用集则创建/切换在写入
    前失败，生产数据库中不再产生无绑定的新 Profile。未配置字体根的
    进程（字体子系统不在其职责内，典型为门禁刻意 unset 字体根的
    unit/integration harness）创建可暂无绑定——该状态在真实部署不
    可达，且 Supervisor/Runner 对无绑定一律失败封闭、永不报告就
    绪，安全性质不依赖创建期拦截。`font_set_id` 为 null 还可能出现
    在迁移前的旧快照里，运行时同样按失败封闭处理。
2. **CJK 暴露显式开关**：新增运行配置 `include_cjk_fonts`。创建未显
    式给出时由 API 按语言派生（`zh-CN` 开、其余关，与
    `domain/profile_locale.default_include_cjk_fonts` 单一实现为准）；
    fontconfig 的中文 reject 规则只看开关、不再看 `locale`。表单在用
    户未手动切换前让开关随语言联动，手动切换后保持。
3. **GPU 身份取消手选**：删除 `gpu_family` 字段、Runner 的
    `--fingerprint-gpu-vendor` 拼接与前端 GPU 下拉。GPU 身份由引擎按
    指纹种子+平台自动派生（d051）；受支持矩阵只有（windows，自动派
    生）与（macos，自动派生）。旧 `nvidia`/`intel` 取值无等价映射。
4. **配色收敛二值**：`color_scheme` 只允许 `light`/`dark`，默认
    `light`。依据 p124 实测：固定引擎上旧 `null` 与 `no-preference`
    都渲染为浅色，映射有据；后台主题设置不改写 Profile 提交值。
5. **一次性迁移 0013**：存量行与 `profile_config_versions` 快照同步
    改写到新形状（删 GPU 键、配色映射、CJK 按旧有效暴露派生——旧
    fontconfig 仅对 `en-US` 拒绝 CJK，故 `en-US` 派生关、其余开——、
    未绑定行补平台默认集）。不可等价映射（GPU 为 nvidia/intel、绑定
    悬空、无集可绑）在任何写入前整体失败并列出阻塞清单；迁移幂等；
    恢复口径为部署前 DB 文件级备份整体还原，downgrade 按家规拒绝。
6. **字体就绪单一结论**：Runner 在启动浏览器前对实际挂载目录生成
    一次验证结论（`runtime_agent/font_verification.py`）：manifest 可
    解析、平台一致、逐文件 sha256 内容哈希相符（manifest 不含文件
    大小字段，故本层不做大小比对），并以该实例 fontconfig 跑真实
    `fc-list` 枚举有效字体——CJK 开时必须有中文覆盖字体面、关时
    必须零泄漏、过滤后为空即失败；可选探测字体的覆盖缺口单独记
    `missing_optional`，不判失败。结论随 `runner_info.font_verification`
    持久化，Agent 健康以其门禁 `ready`，API/SSE 只读结论，无任何逐请
    求重扫。Supervisor 构造字体挂载（`volume_spec.font_set_mount`）时
    先校验源目录真实存在，缺失即失败，杜绝空目录零字体启动。

## 被替代的旧契约

- t053 A16「显式 null 保持无绑定」与表单字体包选择整体废止；其测试
    改写为托管绑定语义（`test_t053_font_sets_chain.py`），表单侧五个字
    体选择用例整体删除（理由记于 `ProfileForm.test.tsx`）。
- t041 AC-006「null 回退基础字体可见、正常启动」废止：未绑定失败封
    闭，基础字体目录永不进入 Profile 白名单；`test_t053_fontconfig_locale.py`
    （按语言裁剪语义）整体删除，由 `test_t075_fontconfig.py` 的开关语
    义覆盖。
- Agent 按请求重扫字体（`_font_runtime` 逐请求哈希）删除，健康口径
    改读 Runner 结论。

## 后果

- 身份字段的写入者收敛为服务层一处：绑定、开关、配色在创建/克隆/
    重启后可逐字段对账（AC-002 的 round-trip 由 unit 锁定）。
- 迁移阻塞是显式运维动作：存量含 nvidia/intel 或无集平台的环境升
    级前必须先处置，部署 spec 已记此口径；阻塞清单即处置清单。
- 云端不可验的部分（真实容器编排下双平台隔离与渲染、GPU 动态实
    值）按 2026-11-18 裁定顺延本地补验 p137，本 ADR 的动态结论以
    p137 结果为准，推翻须修订 s026 与本 ADR。
