# p089 ProfileMeta/State 二分、clone 两态与 reset 语义

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P2-18），借鉴 CloakBrowser-Manager `backend/models.py` / `main.py`
- 内容：元数据变更绝不隐式改状态；`include_browser_state` 开关 + 复制跳过 `SingletonLock`/`SingletonCookie`/`SingletonSocket` 与预览图 + 「目录填完才写 DB 行」+ 源容器 `hold_stopped()` 排他锁 + 取消/失败 `rmtree`；reset 只清状态并重 roll seed、保留 Bookmarks/Preferences/Secure Preferences/Web Data；文件「放 Profile 旁边而非里面」。本地实读 `profile_service.py:176` 只跳 `Singleton*`，克隆或 `--fingerprint-portable-cookies` 下可能把 `Local State` / OSCrypt 密钥复制到新 Profile，形成多 Profile 共享解密根（Chromium 本地数据加密以 `Local State` 中的密钥为根）。本次为只读调研，未授权改生产代码。
- 处理：t066；resolution=transferred；reason=已核实当前代码与有效 task，按同一交付面聚合转交 t066；过时描述与剩余范围见 task spec，归档仅表示转办
- 时间：2026-11-13T19:16:54+08:00
- 关联：p074（原子身份 bundle）、p080（备份/快照护栏）、p071（todo，控制面 legacy 兼容残留）、p043（parked，Chrome Profile 导入绑定）、p078（跨 Profile 泄漏面）

## 目标

1. 明确 ProfileMeta（配置/身份版本）与 ProfileState（userDataDir）二分，元数据 PATCH 不触碰状态目录。
2. clone 支持 include/exclude browser state 两态；复制排除 `Singleton*`、预览图与 `Local State` 的 OSCrypt 密钥，新 Profile 生成独立密钥根。
3. reset 只清状态并重 roll seed，保留书签与偏好；所有写操作「目录填完才写 DB 行」，失败可回滚且不残留半成品。

## 前置与风险

- 涉及 Profile 数据迁移，备份可恢复性验证见 p080；按零兼容性负担直接定稿契约，不留旧格式兼容层。
- 删除即擦除在 COW/SSD/TRIM 上不成立，不写成已保证。

## 验收

1. clone 出的两个 Profile 的 OSCrypt 解密根不同，跨 Profile 无法解密彼此 cookie。
2. include/exclude state 两种 clone 的 cookie/localStorage 行为符合预期，且源 Profile 不受影响。
3. 中途取消/失败后无半成品目录与孤立 DB 行；reset 后身份版本变化且书签保留。
