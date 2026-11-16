# p106 代理位置拆分为国家与城市、筛选拆分及 IP 国家城市查询服务接入

- 来源：用户提出
- 内容：在 `p104`/`p110` 基础上彻底重构代理地理位置与筛选架构（按开发铁律直接破坏性升级 Schema 与协议）：1) 代理列表与卡片将位置拆分为独立「国家」与「城市」两维信息；2) 工具栏废除单一 `region` 状态，拆分为独立的「国家筛选」与「城市筛选」并同步持久化到 URL 查询参数；3) 后端 `ProxyEgressObservationModel`、`EgressObservation`、`EgressProbeResponse` 与 `ProxyResponse` 直接新增 `country_name`、`city` 等持久化字段（增量 Alembic 迁移，零历史包袱）；4) 彻底解决当前 `egress.py` 已用 `GeoLite2-City.mmdb` 调用 `reader.city(ip)` 却丢弃 `city` 的缺陷，并按用户要求结合代理出口 HTTP GeoIP 网络服务（已预研免 Key HTTPS JSON 服务如 `https://ipwho.is/`、`https://api.ip.sb/geoip`、`https://freeipapi.com/api/json` 与本地 `GeoLite2-City.mmdb` 双层或主备判定），一次出口请求同时解析出口 IP、国家、城市并修订 ADR 029 / `docs/blueprint/security.md`。
- 处理：t074；resolution=transferred；reason=已合并转交 t074（设置持久化弹窗化与代理轻量测速/国家城市/列表交互全栈重构）
