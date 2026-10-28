# Spike report

## 问题

CloakBrowser SDK经Playwright间接启动Chrome。验证能否保留SDK调用路径并观测真实Chrome退出状态，以及SDK owner异常消失时Chrome退出码是否仍可能为0。

## 成功判据

- 重复executable_path参数必须出现确切冲突原因；FD关闭负例必须定位Chrome调试pipe描述符缺失，不能任意异常算通过。
- 实际/proc/exe、PID与starttime匹配真实Chrome；正常关闭raw wait=0，SIGKILL raw wait=-9且规范化137。
- 独立owner被SIGKILL后，记录清理之前5秒时间线；不预设Chrome存活或终止，不把清理造成的退出当结果。
- 汇总要求恰好5项均符合各自观察判据。该成功仅指机制实验，非正式Runtime六AC通过。

## 尝试

- 独立Gemini先完成原型，再按主控反馈收紧异常匹配、PID/starttime/exe、预期键集合与owner-loss观察；原首稿宽泛负例判据/完整等价声明不作为最终证明。
- 通过公开CLOAKBROWSER_BINARY_PATH测试受控launcher，透传Playwright使用的FD3/4并等待实际Chrome子进程；不是唯一可能实现的结论。
- 主控独立重跑原修正版通过；将正式code/probe.py去行尾空白并格式化后，再逐字节冻结、以同一固定镜像独立重跑通过。源码SHA256：ef1bee2847c96e30ff4542ddf3f888bce332c414774086a08a272462dda36d5c。

## 证据

- 实验镜像固定ID：sha256:b4d2c5b7f6f49153deb57f4a3da617b4b4554feed532f2b293c61f81785e4e6e；Linux arm64、CloakBrowser0.6.4、Chromium146.0.7680.177.3，headless机制实验。
- 主控最终运行完成时间：2026-10-28T04:37:36+08:00；exit0，5项检查通过；日志主仓.scratch/v2_orchestration/t003_sdk_exit_official_replay/stdout.log，命令与源码哈希单独保存。
- 正常关闭：真实Chrome PID/starttime及exe匹配，raw wait=0；SIGKILL：raw wait=-9、规范化137、signal9。
- owner-loss：仅向独立Python owner发SIGKILL，清理之前0.5秒已见Chrome消失、wrapper记录raw wait=0；保持观察到5秒仍为0。证明基础设施owner丢失也可能导致Chrome以0退出。
- 重跑先复制归档源码到自有scratch，禁止在归档目录生成产物；以下命令不启动默认镜像entrypoint、不发布端口、不挂用户数据：

```bash
mkdir -p "$PWD/.scratch/s010_exit_replay"
cp docs/archive/spikes/s010_cloakbrowser_exit_observation/code/probe.py "$PWD/.scratch/s010_exit_replay/probe.py"
docker run --rm --name cbrowser-t003-sdk-s010-replay \
  --label cbrowser.task=t003 --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges --shm-size 1g \
  --tmpfs /tmp:rw,exec,mode=1777 --entrypoint python3 \
  --mount "type=bind,src=$PWD/.scratch/s010_exit_replay,dst=/scratch,readonly" \
  sha256:b4d2c5b7f6f49153deb57f4a3da617b4b4554feed532f2b293c61f81785e4e6e \
  /scratch/probe.py
```

固定重跑容器名不可并发使用；确认原执行已终态再使用，不按模糊前缀清理他人容器。脚本/tmp路径均在一次性容器内，禁止在宿主直接执行。

## 结论

- 已验证一种SDK透明调用基础路径及真实子进程观测方式；Chrome退出0不足以独自判定用户正常关闭，UDS Agent与SDK owner/Chrome监控须有明确生命周期边界。
- wrapper可能影响SDK依赖binary_path的能力识别、版本或Widevine目录等行为，生产须核对并验证。未证明全部代理认证、扩展、DRM、humanize选项完全等价。
- 原型状态文件tmp+replace没有file/dir fsync，不证明掉电durability或正式事件队列可靠；未测完整UI、XShm、音频、Agent恢复、Mac bind-root UID和新生产镜像。不得将5项机制检查当六AC验收。

## 是否采纳

- 决定：是
- 理由：采纳真实退出状态与owner生命周期边界；不冻结某个launcher为唯一架构，也不复制原型debug路径或弱持久化进生产。
- 后续 task：t003、t005
- 无需后续理由：不适用

## 关联 findings

- d016：SDK owner消失可能使Chrome以0级联退出。
