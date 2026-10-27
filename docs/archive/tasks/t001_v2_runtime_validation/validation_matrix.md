# v2.3 第一阶段验证矩阵

来源：`docs/v2_architecture_plan.md` 第18章。这里只记录证据强度；局部通过不等于完整条款通过，AC 仍由 task.md 行内状态决定。当前修订后六项AC按本地技术实验/报告范围满足，公网及原生Linux执行为用户豁免而非通过；生产完整验收仍在后续阶段，不因实验通过而取消。按用户最新执行调整，本次可在本地有效项完成并单列豁免后推进；迁移与旧链路删除仍等后续完整验收。

|项|要求|当前证据与边界|完整条款状态|
|---|---|---|---|
|01|单 Profile CloakBrowser 在 Browser Runtime 运行|s007最终非root/只读/Xauthority/独立Pulse卷，实际CloakBrowser UI/DOM/音频；九源独立19.0秒exit0。正式生命周期/数据API由后续任务实现|技术观察通过|
|02|同 Profile IPC/X11 跨容器捕获|s007非root Browser/Stream实际共享IPC，pixelflux捕获1920×1080多帧/PNG；独立重跑通过|技术观察通过|
|03|MIT-SHM 正常使用|s007低层XShmGetImage正例及pixelflux明确XShm；跨IPC BadAccess负例；不把IPC当普通XGetImage防窥边界|技术观察通过|
|04|虚拟音频输出和 Selkies 音频捕获|s007最终浏览器WebAudio经48000 Pulse到Stream监视源，1%音高/错误采样率必跑负例；s004独立双Chrome页音频bytes/energy与mute/close首页连续性。非第19章长压|技术观察通过|
|05|固定分辨率和真实内部 UI|主控原图核对真实Chrome标签栏/地址栏；s004两个decoder固定1920×1080，外部viewport800×600后不变，独立重跑通过|原型通过|
|06|两个不同 client_tab_id 同时连接|s004同Chrome Context双tab、不同ID、1080p真实解码与字节增长，独立重跑通过|原型通过|
|07|刷新、复制页和关闭首页面|s004刷新保ID、WebLocks冲突重映射、close首tab后次页视频/音频持续；Debugger.pause对照不等于实际Page lifecycle冻结|原型通过；冻结边界未证明|
|08|两页面同时输入|s004双页真实DOM121212（各3次，总6）及单页111负例；s009独立原生IME提交、主控标点/取消/Emoji精确检查，不证明1000次IME|技术观察通过|
|09|后台页面不压低前台编码帧率|s005 R4六源一致，独立Core9/Native7最终exit0、主控Native7再跑exit0；真实hidden/visible/最小化，前台+60帧后台0，恢复实际set8→resume→motion30；首次握手失败保留，非P95验收|技术观察通过|
|10|持续视频不因无键鼠而降帧|s005 R4实际damage对照：静止target8、持续Canvas decoded约29–31且无输入不降8、慢闪回8；输入/IDR/join/协议尺寸守卫经独立复核|技术观察通过|
|11|信令通过 Gateway 动态 Agent 隧道|s006最终三独立进程/双容器/双Chrome实测，12项exit0；实际Chrome main PID/start_ticks与容器身份在Gateway SIGKILL前后相同，Agent自动注册，页面显式重建连接恢复视频。非ICErestart，未测重启后音频|本机原型通过；完整链路未完成|
|12|UDP mux 端口映射|s004独立重跑两selected remote candidate均UDP30006并实际解码；s006最终独立12项exit0，包含Gateway30007严格失败分支和恢复验证|本机30006映射通过|
|13|公网候选地址|本地映射不能证明公网；用户明确豁免公网环境验证，不使用现有低配生产主机试错，不能宣称公网可达|NOT_RUN / USER_WAIVED|
|14|TURN 凭证、刷新和 relay-only|s008最终分离配置九源与独立快照一致：宿主/内网不同URL及不同凭证，正常两轮新代接管媒体exit0，单侧失效矩阵exit1；PC/track引用===。仅本地短TTL，公网/正式调度未测|本地技术观察通过，公网NOT_RUN/USER_WAIVED|
|15|CDP UDS 与下载捕获|原宿主Chrome两下载/自动恢复已独立复验；新增真实CloakBrowser/独立Supervisor容器在networknone经共享UDS完成两下载恢复，另有覆盖实际生效对照，两case主控与独立Gemini均exit0，五文件快照一致；正式持久Artifact/并发重臂仍缺|跨容器机制通过，生产链路未完成|
|16|Supervisor/API 重启及正常浏览器退出|真实独立进程、Docker CloakBrowser、API离线退出、Supervisor落盘后SIGKILL、API恢复、防误自启、新实例迟到事件由主控与独立Gemini重跑exit0；缺observed running、异常退出退避和多事件队列互斥，不是正式链路|技术实验通过；生产恢复策略待实现|
|17|macOS OrbStack arm64 与 Linux x86_64 Docker|本机arm64实际运行；原生Linux x86_64执行经用户豁免；不以模拟架构、本机或低配结果代替对应平台/容量证明|NOT_RUN / USER_WAIVED|

## 可追溯证据

- `docs/archive/spikes/s001_selkies_runtime/`：IPC、显示、音频原型与原始报告退回 review；主控原始重跑日志在主仓 `.scratch/v2_orchestration/root_runtime_verify.log`。

- `docs/archive/spikes/s002_selkies_protocol/`：固定源码约束与真实UDP重复start实验；主控Gateway Echo重跑日志在主仓 `.scratch/v2_orchestration/root_gateway_verify.log`。

- `docs/archive/spikes/s003_selkies_control/`：UDS/CDP下载与自动恢复，含独立review和黑盒报告。最新自动端口版主控日志在当前task worktree `.scratch/cdp_probe/verify.log`。

- d001–d014：测试基线、UDS下载可行性、ICE restart缺口、shareable IPC供体契约。

- `docs/archive/spikes/s004_media_connections/`：1080p双页面与输入/音频/身份实验；五文件冻结快照独立重跑exit0，边界见report。

- `s003/recovery_review.md`：独立进程恢复检查点黑盒与生产差距。

- s007/d011：最终非root/只读/IPC/Xauth与真实浏览器音频；R5纯代码错误采样率校准必跑。

- s008/d012：最终独立RTC配置和新代媒体接管、单侧失效拒绝；非公网。

- s009/d014：原生composition/XTest输入与剪贴板不变技术证据；非OS候选窗/1000次。

## 持续约束

- 不采纳“凭证仅对新连接生效”作为原计划 ICE restart 的替代通过条件；等待明确产品决策或实现真正重协商。
- 不以媒体端口发送成功、HTTP200、对象构造或截图推断 WebRTC 双向媒体通过。
- 不把 root/匿名音频/无Xauthority 的技术原型当作正式沙箱安全验收。
- 第19章性能、8小时压力、1000次组合输入/剪贴板与正式迁移备份不因本矩阵局部通过而取消，后续仍须逐项验收。
