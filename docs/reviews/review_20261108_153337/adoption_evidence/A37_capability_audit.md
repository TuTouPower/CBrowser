# A37 Supervisor 进程 capability 审计与收敛结论

- 工作树：分支 `adopt/w1-deploy`，base `main@3a15e7d`
- 决策来源：`docs/reviews/review_20261108_153337/adoption_decision.md` A37（625–638 行）、「实施组织与验证要求」（936–957 行）
- 结论类型：**交付「本 worktree 不具备可安全验收的收敛条件」结论 + 需求证据 + 运行测量 NOT_RUN**；不实施编排改动
- A37 **未记完成**。`compose.yaml`（supervisor 段）与 `config/docker/supervisor_runtime/Dockerfile` 均未修改；未新建服务。

> 行号以本 worktree 当前 `compose.yaml` 为准。采纳决策 A37 标注的 `compose.yaml:71-76` 是 A25 精确挂载改动前的位置，A25 在各服务增加挂载行后 supervisor 段整体下移 4 行。

## 1. 结论与依据

用户选择 A：保留 Supervisor 为唯一高信任 Docker 控制者并落实最小权限。本 worktree 完成「审计」，未进入「收敛」，依据如下：

1. 现有编排**已有显式权限约束**：`compose.yaml:78` `read_only: true`、`:79` `cap_add: [FOWNER, DAC_OVERRIDE]`、`:80-81` `tmpfs`、`:107` `/var/run/docker.sock:/var/run/docker.sock:ro`。不能描述为「没有显式权限约束」。
2. `cap_add` 只在 Docker 默认 bounding set 之上**追加**能力，不等于 `cap_drop: [ALL]` 后逐项授予。Supervisor 以 root 运行、默认集已含 FOWNER/DAC_OVERRIDE，故 `:79` 的两项 `cap_add` 是冗余声明，并未收敛常驻进程的实际 capability 集。
3. 收敛的验收强制要求「变更前后同镜像/编排下实际 capability 差异」「被删除能力的具体负例」「必要归属处理、缓存初始化、helper 调度、启动/停止/恢复全链通过」。本机 Docker daemon 可达（`docker version` server 29.4.0），但本 worktree 授权明确**禁止** `docker compose up`、构建完整镜像、真实部署（会写宿主状态），这些运行测量因而 **NOT_RUN**；原因是**授权边界，不是环境不可用**。
4. 静态审计进一步发现「实际所需能力集合」尚不能确定，尤其 `CAP_CHOWN`（见 §4）。在缺运行测量时把编排改成 `cap_drop: [ALL]` + 猜测的 `cap_add`，存在破坏归属处理的具体风险，属于「不能证明可安全收敛」。
5. 依据 A37 验收标准「若没有可安全收敛的能力，交付该结论和需求证据，不为保持『修复成果』另建服务或偷偷放回默认能力」：本 worktree 交付审计结论与需求证据，不改编排、不新建服务、原样保留既有 `cap_add` 行（保留原状，非偷偷放回默认能力）。

据此 A37 归类为 **「交付无可收敛结论」**。准确表述：能力层面存在可静态识别的非必要默认能力，但本 worktree 不具备证明「可安全收敛」的运行证据，故不实施、不宣称完成。未借 A25 凭据不可读、未借 A26 源码裁剪、未以静态 YAML 核验充当本项验收。

## 2. 现状事实（静态审计）

|项|事实|位置|
|---|---|---|
|Supervisor 编排|`read_only: true`、`cap_add: [FOWNER, DAC_OVERRIDE]`、`tmpfs: /tmp`、`docker.sock:ro`|`compose.yaml:75-81`、`:107`|
|归属开关|`CBROWSER_MANAGE_OWNERSHIP: "1"`（生产显式开启）|`compose.yaml:99`|
|镜像 User|`config/docker/supervisor_runtime/Dockerfile` 全文无 `USER` 指令，`ENTRYPOINT ["python3","-m","cbrowser.supervisor"]` → 以镜像默认用户 **root（UID 0）** 运行|该 Dockerfile 1–32 行|
|对比|api `USER 1000:1000`、gateway `USER 1000:1000`、stream `USER cbrowser:cbrowser`、browser `USER cbrowser`|各 runtime Dockerfile|
|启动端口|`--port 8005`（> 1024，不依赖 `CAP_NET_BIND_SERVICE`）|`compose.yaml:100`|

`root 是否可移除` 由实际文件归属需求决定，本项不预先承诺、不实施。

## 3. 静态 capability 推导（非实测 CapEff/CapBnd）

Docker 非 privileged 容器的默认 bounding set（静态知识，需 `/proc/<pid>/status` 实测确认，见 §9 NOT_RUN）：
`CHOWN, DAC_OVERRIDE, FSETID, FOWNER, MKNOD, NET_RAW, SETGID, SETUID, SETFCAP, SETPCAP, NET_BIND_SERVICE, SYS_CHROOT, KILL, AUDIT_WRITE`。

- **变更前（当前，静态推导）**：Supervisor 无 `cap_drop`，root 进程预期持有上述 14 项默认能力；`cap_add: [FOWNER, DAC_OVERRIDE]` 不改变该集合（已含）。
- **变更后（假设性收敛，未实施）**：若 `cap_drop: [ALL]` + `cap_add: [FOWNER, DAC_OVERRIDE]`，按编排意图 CapEff/CapBnd 预期仅剩 `FOWNER, DAC_OVERRIDE`。这是 YAML 语义推导，**不是实测 capability 差异**。
- 因此「变更前后实际 capability 差异」与「被删除能力的具体负例」在 §8 以**静态假设性推导**给出，明确标注非运行通过；运行负例 NOT_RUN。

## 4. Supervisor 常驻进程直接能力需求（核心不确定点）

`CBROWSER_MANAGE_OWNERSHIP` 语义：`runner.py:485-489` 默认 `os.getenv("CBROWSER_MANAGE_OWNERSHIP","auto")`；`auto` 经 `runner.py:527-531` 传 `None`，`runner.py:106-107` 解析为 `os.geteuid() == 0`。即**以 root 运行时（含默认 auto）归属处理自动为 True**；生产又显式设 `"1"`。

由此，Supervisor **常驻进程**直接执行以下文件归属/权限/缓存操作（不是经 Docker API 的间接操作）：

- `core.py:2036`、`:2075`：`os.chown(path, runtime_uid, runtime_gid)`（写代理凭据、运行时快照后改 owner）
- `core.py:2261`：`secret_dir.chmod(0o700)`
- `docker_adapter.py:224`：`gate.chmod(0o755)`
- `docker_adapter.py:555-580`：`_secure_cache` 遍历 `engine-cache`，`os.chown(..., runtime_uid, runtime_gid, follow_symlinks=False)` + `path.chmod(mode)`（缓存初始化）
- `docker_adapter.py:632-647`：`_secure_directory` **无条件** `os.chown(directory, 1000, 1000)` + `os.chmod(directory, mode)`（Profile 目录归属）
- `docker_adapter.py:1158-1159`：`os.chown(target_snap, runtime_uid, runtime_gid)`
- `file_storage.py:15`：`os.fchmod(...)`

`os.chown(path, 1000, 1000)` 把文件的 **owner UID 从 0 改为 1000**，Linux 上需要 `CAP_CHOWN`；`CAP_FOWNER`/`CAP_DAC_OVERRIDE` 解决的是「绕过所有权检查以 chmod / 改组」，不等于可改 owner UID。而既有 `cap_add: [FOWNER, DAC_OVERRIDE]` **不含 CHOWN**。

结论：**「实际所需集合」不能确定**。若照搬 `cap_drop: [ALL]` + `[FOWNER, DAC_OVERRIDE]`，会删除默认集中的 `CAP_CHOWN`，`_secure_directory` / `_secure_cache` / `_write_runtime_snapshot` / `_write_proxy_credentials` 的 chown 可能 EPERM 并抛 `DockerSandboxError`，直接破坏启动期的归属处理、缓存初始化与快照写入。这正是 A37 验收点「必要归属处理、缓存初始化、启动/停止/恢复全链通过」必须由运行测量确认、而本 worktree 无法确认的原因。

## 5. helper 能力边界（按各自容器验证，不加到常驻进程）

Supervisor 通过 Docker API 创建的 helper / 工作容器，其能力在**那个容器**上，已各自 `cap_drop: [ALL]` 后精确授予，不应加到 Supervisor 常驻进程：

|helper|能力|位置|
|---|---|---|
|network policy / verify|`cap_drop=["ALL"]`, `cap_add=["NET_ADMIN"]`|`docker_adapter.py:285-286`、`:1680-1681`|
|存储/归属|`cap_drop=["ALL"]`, `cap_add=["DAC_OVERRIDE","FOWNER"]`|`docker_adapter.py:521-522`|
|X11 权限|`cap_drop=["ALL"]`, `cap_add=["FOWNER"]`, `user="0:0"`, `no-new-privileges:true`, `read_only`|`docker_adapter.py:649-675`|
|其它|`cap_drop=["ALL"]`（无 cap_add）|`docker_adapter.py:1228`、`:1431`|

既有回归 `tests/unit/test_supervisor_docker_boundaries.py:125-146` 断言 X11 helper 的 `cap_drop`/`cap_add`/`read_only`/`no-new-privileges`。这些是既有事实，非本项新增改动；A37 不重复计功。

## 6. 既有 recovery probe 事实与局限

`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:499-516` 用**同一 supervisor 镜像**（`sha256:` 固定 ID）以 `read_only=True, cap_drop=["ALL"], cap_add=["FOWNER","DAC_OVERRIDE"], security_opt=["no-new-privileges:true"]` 启动容器。这证明项目曾把该能力集当作候选基线，但**不能作为生产编排的运行验收证据**：

- `:485-496` 的 `container_env` 未设 `CBROWSER_MANAGE_OWNERSHIP`，容器以 root 运行 → 按 §4 的 `auto` 语义仍会进入 chown 归属路径；该集合（无 CAP_CHOWN）是否覆盖 chown 换 owner 缺运行确认。
- 配套单测 `tests/unit/test_baseline_fixture_regressions.py:372-428` 使用 `MagicMock` docker client，只断言 `containers.run` 的 kwargs，不执行容器内 `os.chown`、不采集 CapEff/CapBnd。
- 该 fixture 是独立编排（自建挂载/网络/命令），非 `compose.yaml` 的 supervisor 服务；「同镜像/编排」的运行差异比较未做。

## 7. cap_drop / 非 root 与 Docker 信任边界

`compose.yaml:107` 把 `/var/run/docker.sock` 挂入 Supervisor（`:ro` 仅限制挂载点写入，不限制 Docker API 语义）。Supervisor 经 Docker API 创建 browser / stream / helper 容器时，可给这些容器 `cap_add: [NET_ADMIN]` 等任意 HostConfig（§5）。

**非 root 或 `cap_drop` 只作用于 Supervisor 常驻进程自身的 Linux capabilities，不会限制它经 Docker API 创建高权限容器的权能。** 因此 A37 不改善「完整 Docker socket 等同宿主控制权」的信任边界；不得声称本项阻止 Supervisor 受损后经 Docker 越权。若目标变为真正限制 Docker 控制权，须另选可校验资源/挂载/HostConfig 的执行边界或隔离 daemon，不在用户已选 A 范围内。

## 8. 被删除能力的具体负例（静态假设性推导，非实测）

仅在「若实施 `cap_drop: [ALL]` + `[FOWNER, DAC_OVERRIDE]`」的前提下，静态推导的差异与负例如下；**运行负例 NOT_RUN，不写成运行通过**：

|默认能力|收敛后（假设）|常驻进程需求|负例（静态推导）|
|---|---|---|---|
|`NET_RAW`|删除|无 raw socket|`socket(AF_INET, SOCK_RAW, ...)` 应 EPERM|
|`SYS_ADMIN`|删除|无 mount/命名空间操作|`mount(2)` 应 EPERM|
|`MKNOD`|删除|无设备节点创建|`mknod(2)` 应 EPERM|
|`SYS_CHROOT`|删除|无 chroot|`chroot(2)` 应 EPERM|
|`NET_BIND_SERVICE`|删除|端口 8005 > 1024|绑定 \<1024 端口应 EPERM|
|`AUDIT_WRITE` / `SETFCAP` / `SETPCAP` / `KILL` / `FSETID` / `SETUID` / `SETGID`|删除|无对应直接需求|相应系统调用应 EPERM|
|**`CHOWN`**|**删除（有风险）**|**§4：`os.chown(...,1000,1000)` 需要**|**负例不成立：收敛会破坏归属处理**|

最后一行是**不实施收敛**的决定性依据：无法把 `CAP_CHOWN` 证明为「非必要默认能力」，删除它的负例与安全收敛相反。差异表本身是 YAML 语义推导，未经 `docker inspect` / `capsh` / `/proc/<pid>/status` 实测确认。

## 9. 运行测量 NOT_RUN 清单及原因

本机 daemon 可达（server 29.4.0），但本 worktree 授权禁止 `docker compose up`、构建完整镜像、真实部署；未启动任何容器、未写宿主状态。以下项 **NOT_RUN**，不以静态 YAML 核验或 A25 凭据不可读代替：

- 变更前同镜像/编排下 Supervisor 进程 `User` / `CapEff` / `CapPrm` / `CapBnd` 实测（`/proc/1/status`、`docker inspect .HostConfig`）：NOT_RUN
- 变更后同镜像/编排实测 capability 差异：NOT_RUN（未实施收敛，无「变更后」）
- 被删除能力的具体运行负例（capsh / EPERM 系统调用）：NOT_RUN
- `CBROWSER_MANAGE_OWNERSHIP=1` 下归属处理、engine-cache/geoip 缓存初始化、Profile 目录 chown/chmod：NOT_RUN
- helper 调度（NET_ADMIN / FOWNER 在各自容器）、启动 / 停止 / 恢复全链：NOT_RUN
- `docker compose -f compose.yaml config --quiet` 仅做插值解析（A25/A26 验证已执行），**不计入本项运行测量**

## 10. 实施收敛的先决条件（deferred，需具备 Docker 运行授权的集成阶段）

1. 用**同一 supervisor 镜像 + 当前 compose** 启动，采集变更前 `/proc/1/status` 的 CapEff/CapBnd/CapPrm 与 `docker inspect` HostConfig 作为基线。
2. 候选 `cap_drop: [ALL]` + `cap_add` 集合必须**显式判定 `CAP_CHOWN`**：在 `CBROWSER_MANAGE_OWNERSHIP=1` 下验证 `_secure_directory` / `_secure_cache` / `_write_runtime_snapshot` / `_write_proxy_credentials` 的 `os.chown(...,1000,1000)` 是否成功；失败则候选集必须包含 `CAP_CHOWN`。不得照搬 §6 fixture 的 `[FOWNER, DAC_OVERRIDE]` 而不验证。
3. 验证缓存初始化（engine-cache / geoip）、Profile 目录归属、快照/凭据写入、helper 调度、启动 / 停止 / 恢复全链在该能力集下通过。
4. 提供变更后同镜像/编排 CapEff/CapBnd 差异与被删能力的**运行**负例（EPERM）。
5. 只有上述全绿，才把 `cap_drop` 写入 `compose.yaml` 并记 A37 完成；`root` 是否移除需另行基于 bind mount 归属与 docker.sock 组权限决策，不预先承诺。

## 11. 验收标准对照

|A37 验收要求|状态|说明|
|---|---|---|
|审计现有 User / CapEff / CapBnd 与 chown/chmod/缓存需求|已满足（静态层）|§2、§4；CapEff/CapBnd 实测 NOT_RUN|
|变更前后同镜像/编排实际 capability 差异|**NOT_RUN / 未满足**|§3 仅静态推导，未实施收敛、未实测|
|被删除能力的具体负例|**NOT_RUN / 未满足**|§8 仅假设性静态推导，含 CAP_CHOWN 反例|
|必要归属处理、缓存初始化、helper 调度、启动/停止/恢复全链|**NOT_RUN / 未满足**|§9|
|不宣称削弱 Docker 控制权 / 明确信任边界|已满足|§7|
|不借 A25 凭据不可读或 YAML 文本记完成|已满足|本项明确未记完成|
|无可安全收敛点时交付结论与需求证据、不另建服务、不偷偷放回默认能力|已满足|§1、§10|
|运行测量标 NOT_RUN 及原因、不把静态核验写成运行通过|已满足|§9（原因：worktree 授权禁止启容器/构建/部署）|
