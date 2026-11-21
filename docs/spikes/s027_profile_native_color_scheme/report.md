---
slug: "profile_native_color_scheme"
status: "completed"
sid: "s027"
---

# Spike report: 固定 CloakBrowser 原生配色与运行配置联动

## 问题

t099 需要把环境内单一配色设置应用到浏览器原生外壳和网页偏好。验证固定 CloakBrowser 在 Linux/X11 下是否读取启动前写入的原生配色，是否支持同一持久化 Profile 双向切换，以及 GTK 系统主题是否会覆盖原生配色。

## 成功判据

- 同一份持久化用户目录完成浅 → 深 → 浅。X11 截图中的标签栏、地址栏、工具栏和菜单均随之切换。
- 两个不同 Profile 同时运行时，一个保持浅色，一个保持深色。各自的网页媒体查询与环境配色一致。
- 用固定白底网页和 GTK 系统主题分别做对照，区分页面渲染、浏览器原生配色与系统主题优先级。

## 尝试

- 2026-11-21 本地 OrbStack arm64。Browser 镜像 `sha256:d99d095b33f9122711d8acd93e49b7d08d40c1102fddb4168964bbcb9d8c2e85`，固定引擎 `146.0.7680.177.3`，SDK `0.6.4`。真实 `BrowserRunner` 启动 Xvfb、Openbox 与 CloakBrowser，通过制品校验并使用正式 Windows 字体集。
- 容器使用 `--network none` 和独立临时用户目录。只读挂载现有引擎与字体 subpath。`code/probe.py` 在 Chrome 停止时向临时 Profile 的 `Preferences` 合并原生模式与 Linux 系统主题值，原样使用 BrowserRunner 读取环境的网页配色。运行期间使用两个本地页面和 X11 截图。
- `code/verify.py` 从截图采样标签栏、地址栏、工具栏和菜单区域。对照打开菜单前后画面，验证菜单实际绘制，并检查网页主体像素和 Playwright 读取的偏好值。

## 证据

|场景|标签栏 RGB|地址栏 RGB|工具栏 RGB|菜单 RGB|适配网页|
|---|---|---|---|---|---|
|原有行为，仅网页深色|211, 227, 253|237, 242, 250|255, 255, 255|255, 255, 255|深|
|同一 Profile，浅色|211, 227, 253|237, 242, 250|255, 255, 255|255, 255, 255|浅|
|同一 Profile，切深色|31, 32, 32|40, 40, 40|60, 60, 60|31, 31, 31|深|
|同一 Profile，切回浅色|211, 227, 253|237, 242, 250|255, 255, 255|255, 255, 255|浅|
|A 和 B 同时运行|A 浅，B 深|A 浅，B 深|A 浅，B 深|A 浅，B 深|A 浅，B 深|
|原生偏好深色，GTK 系统主题|221, 218, 214|255, 255, 255|246, 245, 244|255, 255, 255|深|
|同一 Profile 恢复 Chromium 自带主题|31, 32, 32|40, 40, 40|60, 60, 60|31, 31, 31|深|

深色原生主题下，固定白底对照页的主体像素仍为 `(255, 255, 255)`，截图中标签栏为 `(31, 32, 32)`。适配页浅、深主体分别为 `(244, 245, 246)` 和 `(32, 33, 36)`。Chrome 退出后，持久化原生偏好按 `1 → 2 → 1` 回读，GTK 对照的系统主题值为 `1`，恢复 Chromium 自带主题后为 `0`。

### 复现

在仓库根目录设置已有 Windows 字体集 ID `THEME_PROBE_FONT_SET_ID`、引擎卷 `THEME_PROBE_DATA_VOLUME` 和字体卷 `THEME_PROBE_FONTS_VOLUME`。输出只写临时目录。宿主使用项目虚拟环境的 Pillow 进行像素校验。

```bash
THEME_PROBE_RUN=$(mktemp -d .scratch/s027_theme_XXXXXX)
mkdir -m 0777 "$THEME_PROBE_RUN/evidence"
cp docs/spikes/s027_profile_native_color_scheme/code/*.py "$THEME_PROBE_RUN/"
THEME_PROBE_FONT_SUBPATH="windows/$THEME_PROBE_FONT_SET_ID"

docker run --rm --init --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --shm-size 512m \
  --tmpfs /tmp:rw,exec,nosuid,nodev,size=512m \
  --mount "type=bind,src=$PWD/$THEME_PROBE_RUN,dst=/probe,readonly" \
  --mount "type=bind,src=$PWD/$THEME_PROBE_RUN/evidence,dst=/evidence" \
  --mount "type=volume,src=$THEME_PROBE_DATA_VOLUME,dst=/data/engine-cache,volume-subpath=engine-cache,readonly" \
  --mount "type=volume,src=$THEME_PROBE_FONTS_VOLUME,dst=/run/cbrowser/fonts/$THEME_PROBE_FONT_SUBPATH,volume-subpath=$THEME_PROBE_FONT_SUBPATH,readonly" \
  --env "THEME_PROBE_FONT_SET_ID=$THEME_PROBE_FONT_SET_ID" --entrypoint python3 \
  sha256:d99d095b33f9122711d8acd93e49b7d08d40c1102fddb4168964bbcb9d8c2e85 /probe/probe.py

.venv/bin/python "$THEME_PROBE_RUN/verify.py" "$THEME_PROBE_RUN/evidence"
```

## 结论

固定 arm64 引擎支持在启动前设置 Profile 原生配色。`browser.theme.color_scheme2` 显式取 `1` 或 `2`，并令 `extensions.theme.system_theme = 0` 使用 Chromium 自带主题，实测可双向切换。保留环境到网页媒体偏好的现有传递即可支持网站按自身样式适配。[Chromium 配色枚举](https://github.com/chromium/chromium/blob/146.0.7680.177/chrome/browser/themes/theme_service.h#L62-L68) · [Linux 主题优先级](https://github.com/chromium/chromium/blob/146.0.7680.177/chrome/browser/themes/theme_service_aura_linux.cc#L160-L168)

验证范围为真实 BrowserRunner、引擎和原生 X11 绘制。远程 Viewer、表单说明及产品实现后的部署验收仍由 t099 完成。

## 是否采纳

- 决定：是。
- 理由：固定引擎实测配色双向控制、Profile 独立与网页语义均成立。写入点放在浏览器启动前，运行意图以 cbrowser 环境配置为准。
- 后续 task：t099。
- 无需后续理由：不适用。

## 关联 findings

- [d053 Chromium Profile 原生配色](../../findings/d053_chromium_profile_native_color_scheme.md)。
