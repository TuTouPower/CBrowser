# p038 内置 mihomo 作为 Profile 代理节点来源

- 来源：用户提出
- 内容：内置 mihomo，用户上传自有配置或导入订阅链接，由 mihomo 向 CBrowser 提供多个代理端口，供各 Profile 使用。现有能力为 `Profile.proxy` 单 URL 字段，外部自建 mihomo 填 `socks5://host:port` 大概率已可用（未验证）；内置价值在协议桥接、SOCKS5 认证转换与节点管理体验。
- 处理：不办

## 分析基线

- 分析时间：2026-11-04T23:47:58+08:00。
- CBrowser 基线：main@ec02e2b0ea9d2b6840a68733a015b4480a6051dd。
- 证据范围：源码与现行 blueprint 静态核对；未运行测试、未部署 mihomo、未验证外部 mihomo 经网络策略例外的可达性。
- 以下方案均为分析建议，决策待定。

## 现状依据

- `Profile.proxy` 为 URL 字符串，max_length 512（`src/backend/cbrowser/domain/models.py`），启动时传 cloakbrowser SDK（`src/backend/cbrowser/runtime_agent/runner.py`）。
- Browser 网络策略默认拒绝私有与保留地址，配置代理按明确解析的地址和端口例外放行（`docs/blueprint/supervisor.md`「网络策略与启动门禁」）。

## 内置价值

1. 协议桥接：Chrome 仅支持 http/https/socks4/socks5；订阅常见 vless/vmess/trojan/hysteria2/tuic 节点须经 mihomo 转换才能使用。
2. SOCKS5 认证：Chromium 不支持带账密 SOCKS5；mihomo 可将带认证上游转为本地无认证 listener，访问控制交给网络策略。
3. 节点管理：Profile 选节点、测延迟、查出口 IP。

## 设计约束（候选）

1. 用户配置与订阅只作数据源：仅提取 `proxies`（或 proxy-providers 解析结果），丢弃 `external-controller`、`tun`、`dns`、rules、远程 rule-providers 等；运行配置由 CBrowser 生成。
2. listener 只绑定单个具体节点，禁止绑定 url-test/fallback/select 等策略组，避免会话中途出口 IP 变化导致身份关联。
3. 每 Profile 一个专属 listener 端口；网络策略只放行本 Profile 端口，防止跨 Profile 借用出口。
4. fail-closed：mihomo 不可用或订阅刷新后节点消失时 Profile 拒绝启动，禁止回退直连。
5. 订阅 URL 与节点凭证按代理账密同级处理：不入日志；存储方式待定。
6. 节点更换导致出口变化时提示用户，`geoip` 推导的时区/语言随之重算。
7. external-controller 仅内网开放并带 secret，仅供后端测延迟与查状态。

## 候选形态

- 单个常驻 mihomo 容器，由 Supervisor 管理（保持 Supervisor 为唯一 Docker Socket 持有者），或作为 compose 服务。
- 节点来源：上传 YAML / 订阅 URL（可定时刷新）。
- Profile 代理新增“节点引用”类型，与直填 URL 并列；启动时解析为 `socks5://mihomo:<专属端口>`。
- 不推荐每 Profile 一个 mihomo：容器数从双容器升为三容器；TUN 需 NET_ADMIN，与 Browser `cap-drop ALL` 冲突。

## 待用户决策

1. 主要代理来源：机场订阅（必须内置）或住宅静态 IP（价值主要在 SOCKS5 认证转换，优先级可降）。
2. 是否需要订阅自动刷新；是否接受“节点消失 Profile 拒绝启动”。
3. 已知局限：机场节点 IP 多用户共享、多为数据中心 ASN，对多身份隔离帮助有限，属使用层取舍。

- 暂搁：用户指定暂搁，待确认代理来源与优先级后再评估
