# p021 Spike：验证 Playwright CDP 兼容性、指纹保持度与 XTEST 路径

- 来源：借鉴 ego-lite 技术调研 / 用户提出
- 内容：开展前置技术探路（Spike），验证三项关键契约：1. Playwright 通过 `connectOverCDP` 经 API/Supervisor `cbat_` 隧道双向通信及弹窗/下载的连通性；2. 外部客户端建立 CDP 长连接并启用相关域（如 Runtime/Page）时，CloakBrowser 隐私指纹在 BrowserLeaks/CreepJS/Pixelscan 下是否发生衰退或留下自动化探测痕迹；3. 在 Browser 容器 Xvfb 环境内通过 XTEST 注入键鼠事件的可行性及窗口坐标换算精度。
- 处理：未开
