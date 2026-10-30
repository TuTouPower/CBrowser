import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def container_cpu_limit(host_config: Dict[str, Any]) -> int:
    """Return the tightest Docker CPU constraint in NanoCPU units."""
    limits = []
    nano = host_config.get("NanoCpus", 0)
    if nano > 0:
        limits.append(nano)
    quota = host_config.get("CpuQuota", 0)
    period = host_config.get("CpuPeriod", 0) or 100_000
    if quota > 0:
        limits.append(int(quota / period * 1_000_000_000))
    cpuset = host_config.get("CpusetCpus", "")
    if cpuset:
        cpus = set()
        for part in cpuset.split(","):
            bounds = [int(value) for value in part.split("-")]
            if len(bounds) == 1:
                cpus.add(bounds[0])
            else:
                cpus.update(range(bounds[0], bounds[1] + 1))
        if cpus:
            limits.append(len(cpus) * 1_000_000_000)
    return min(limits) if limits else 0


def calculate_cpu_percent(
    current_usage_ns: int,
    previous_usage_ns: int,
    current_system_ns: int,
    previous_system_ns: int,
    online_cpus: int,
    nano_cpus_limit: int = 0,
) -> float:
    """Calculate CPU usage percentage based on Docker API container stats.

    Preserves original mathematical contract:
    - If nano_cpus_limit > 0: percentage of container's allocated quota.
    - Without a limit: Docker CLI style; one fully busy core reports 100.0%.
    """
    cpu_delta = current_usage_ns - previous_usage_ns
    system_delta = current_system_ns - previous_system_ns

    if system_delta <= 0 or cpu_delta <= 0:
        return 0.0

    if online_cpus <= 0:
        online_cpus = 1

    if nano_cpus_limit > 0:
        allocated_fraction = float(nano_cpus_limit) / (
            float(online_cpus) * 1_000_000_000.0
        )
        if allocated_fraction <= 0.0:
            return 0.0
        pct = (float(cpu_delta) / float(system_delta)) / allocated_fraction * 100.0
    else:
        pct = (float(cpu_delta) / float(system_delta)) * float(online_cpus) * 100.0

    return max(0.0, pct)


def calculate_quota_normalized_percent(
    current_usage_ns: int,
    previous_usage_ns: int,
    current_system_ns: int,
    previous_system_ns: int,
    online_cpus: int,
    nano_cpus_limit: int = 0,
) -> Tuple[float, str]:
    """Calculate percentage of container quota or total host capacity.

    When nano_cpus_limit > 0:
        100% equals the container's allocated CPU budget.
        Scope: 'container_quota'
    When nano_cpus_limit == 0:
        100% equals all online host CPUs busy.
        Scope: 'docker_host_capacity'
    """
    cpu_delta = current_usage_ns - previous_usage_ns
    system_delta = current_system_ns - previous_system_ns

    if system_delta <= 0 or cpu_delta <= 0:
        scope = "container_quota" if nano_cpus_limit > 0 else "docker_host_capacity"
        return 0.0, scope

    if online_cpus <= 0:
        online_cpus = 1

    if nano_cpus_limit > 0:
        allocated_fraction = float(nano_cpus_limit) / (
            float(online_cpus) * 1_000_000_000.0
        )
        if allocated_fraction <= 0.0:
            return 0.0, "container_quota"
        pct = (float(cpu_delta) / float(system_delta)) / allocated_fraction * 100.0
        return max(0.0, pct), "container_quota"
    else:
        pct = (float(cpu_delta) / float(system_delta)) * 100.0
        return max(0.0, pct), "docker_host_capacity"


@dataclass(frozen=True)
class HostCpuSample:
    """Linux /proc/stat CPU ticks from Docker Host / OrbStack Linux VM."""

    total_ticks: int
    busy_ticks: int
    idle_ticks: int
    timestamp_monotonic: float
    user: int = 0
    nice: int = 0
    system: int = 0
    idle: int = 0
    iowait: int = 0
    irq: int = 0
    softirq: int = 0
    steal: int = 0


def parse_linux_proc_stat_cpu(content: str) -> HostCpuSample:
    """Parse the first aggregate 'cpu ' line of Linux /proc/stat."""
    for line in content.splitlines():
        if line.startswith("cpu "):
            parts = [p for p in line.split() if p]
            if len(parts) >= 5:
                user = int(parts[1])
                nice = int(parts[2])
                system = int(parts[3])
                idle = int(parts[4])
                iowait = int(parts[5]) if len(parts) > 5 else 0
                irq = int(parts[6]) if len(parts) > 6 else 0
                softirq = int(parts[7]) if len(parts) > 7 else 0
                steal = int(parts[8]) if len(parts) > 8 else 0

                idle_all = idle + iowait
                busy_all = user + nice + system + irq + softirq + steal
                total_all = busy_all + idle_all

                return HostCpuSample(
                    total_ticks=total_all,
                    busy_ticks=busy_all,
                    idle_ticks=idle_all,
                    timestamp_monotonic=time.monotonic(),
                    user=user,
                    nice=nice,
                    system=system,
                    idle=idle,
                    iowait=iowait,
                    irq=irq,
                    softirq=softirq,
                    steal=steal,
                )
    raise ValueError("Invalid /proc/stat: missing aggregate cpu line")


def calculate_host_cpu_percent(
    current: HostCpuSample, previous: HostCpuSample
) -> float:
    """Calculate aggregate host busy percentage from Linux /proc/stat deltas."""
    total_delta = current.total_ticks - previous.total_ticks
    busy_delta = current.busy_ticks - previous.busy_ticks
    if total_delta <= 0 or busy_delta <= 0:
        return 0.0
    return max(0.0, min(100.0, (float(busy_delta) / float(total_delta)) * 100.0))


@dataclass(frozen=True)
class ContainerCpuSample:
    container_id: str
    timestamp: float
    timestamp_monotonic: float
    total_usage_ns: int
    system_cpu_usage_ns: int
    online_cpus: int
    nano_cpus_limit: int = 0


@dataclass(frozen=True)
class ProfileQuotaDecision:
    profile_id: str
    max_fps_cap: Optional[float]
    is_throttled: bool
    reason: str
    observed_cpu_pct: float
    measurement_window_sec: float
    sample_count: int
    timestamp: float
    observed_scope: str = "container"


@dataclass(frozen=True)
class ResourcePolicyConfig:
    overload_cpu_threshold_pct: float = 80.0
    recovery_cpu_threshold_pct: float = 50.0
    overload_window_samples: int = 2
    recovery_window_samples: int = 2
    throttled_fps_cap: float = 8.0
    min_measurement_interval_sec: float = 0.5
    host_ncpu: int = 10

    def __post_init__(self) -> None:
        for name, val in [
            ("overload_cpu_threshold_pct", self.overload_cpu_threshold_pct),
            ("recovery_cpu_threshold_pct", self.recovery_cpu_threshold_pct),
            ("throttled_fps_cap", self.throttled_fps_cap),
            ("min_measurement_interval_sec", self.min_measurement_interval_sec),
        ]:
            if not math.isfinite(val):
                raise ValueError(
                    f"Config field {name} cannot be NaN or Infinite: {val}"
                )

        if self.recovery_cpu_threshold_pct >= self.overload_cpu_threshold_pct:
            raise ValueError(
                f"recovery_cpu_threshold_pct ({self.recovery_cpu_threshold_pct}) "
                "must be strictly less than overload_cpu_threshold_pct "
                f"({self.overload_cpu_threshold_pct})"
            )

        if self.overload_window_samples < 1 or self.recovery_window_samples < 1:
            raise ValueError(
                "overload_window_samples and recovery_window_samples must be >= 1"
            )

        if self.throttled_fps_cap < 8.0 or self.throttled_fps_cap > 30.0:
            raise ValueError(
                "throttled_fps_cap must be between 8.0 and 30.0, "
                f"got {self.throttled_fps_cap}"
            )


class ContainerTrackedState:
    """Keep counters and pressure windows separate for each container."""

    def __init__(self, container_id: str) -> None:
        self.container_id = container_id
        self.samples: List[ContainerCpuSample] = []
        self.last_monotonic: float = 0.0
        self.last_total_usage_ns: int = -1
        self.is_throttled = False
        self.consecutive_overload_count = 0
        self.consecutive_recovery_count = 0
        self.last_decision: Optional[ProfileQuotaDecision] = None


class ProfileResourceState:
    """Maintains sliding sample windows, hysteresis state, and container aggregation."""

    def __init__(self, profile_id: str) -> None:
        self.profile_id = profile_id
        self.containers: Dict[str, ContainerTrackedState] = {}
        self.is_throttled: bool = False
        self.consecutive_overload_count: int = 0
        self.consecutive_recovery_count: int = 0
        self.last_decision: Optional[ProfileQuotaDecision] = None
        self.last_observed_scope: str = "container"
        self.foreground_viewers = True


class ResourcePolicyService:
    """Compose host/container CPU pressure into a Profile FPS cap."""

    def __init__(
        self,
        docker_client: Any = None,
        config: Optional[ResourcePolicyConfig] = None,
        host_stat_reader: Optional[Callable[[], str]] = None,
    ) -> None:
        self.docker_client = docker_client
        self.config = config or ResourcePolicyConfig()
        self.host_stat_reader = host_stat_reader
        self._profiles: Dict[str, ProfileResourceState] = {}
        self._host_samples: List[HostCpuSample] = []
        self._host_overload_consecutive: int = 0
        self._host_recovery_consecutive: int = 0
        self._host_is_throttled: bool = False
        self._last_host_pct: float = 0.0

    def get_profile_state(self, profile_id: str) -> ProfileResourceState:
        if profile_id not in self._profiles:
            self._profiles[profile_id] = ProfileResourceState(profile_id)
        return self._profiles[profile_id]

    def record_host_sample(
        self, sample: HostCpuSample
    ) -> Dict[str, ProfileQuotaDecision]:
        """Advance host pressure only for a new, sufficiently separated window."""
        if self._host_samples:
            previous = self._host_samples[-1]
            interval = sample.timestamp_monotonic - previous.timestamp_monotonic
            if (
                interval < self.config.min_measurement_interval_sec
                or sample.total_ticks == previous.total_ticks
            ):
                return {pid: self.evaluate_profile(pid) for pid in self._profiles}
            if (
                sample.total_ticks < previous.total_ticks
                or sample.busy_ticks < previous.busy_ticks
                or sample.idle_ticks < previous.idle_ticks
            ):
                self._host_samples = [sample]
                self._host_overload_consecutive = 0
                self._host_recovery_consecutive = 0
                return {pid: self.evaluate_profile(pid) for pid in self._profiles}
        self._host_samples.append(sample)
        self._host_samples = self._host_samples[-10:]
        if len(self._host_samples) >= 2:
            host_pct = calculate_host_cpu_percent(sample, self._host_samples[-2])
            self._last_host_pct = host_pct
            if host_pct >= self.config.overload_cpu_threshold_pct:
                self._host_overload_consecutive += 1
                self._host_recovery_consecutive = 0
                if (
                    self._host_overload_consecutive
                    >= self.config.overload_window_samples
                ):
                    self._host_is_throttled = True
            elif host_pct <= self.config.recovery_cpu_threshold_pct:
                self._host_recovery_consecutive += 1
                self._host_overload_consecutive = 0
                if (
                    self._host_recovery_consecutive
                    >= self.config.recovery_window_samples
                ):
                    self._host_is_throttled = False
            else:
                self._host_overload_consecutive = 0
                self._host_recovery_consecutive = 0
        return {pid: self.evaluate_profile(pid) for pid in self._profiles}

    def record_stats(
        self,
        profile_id: str,
        container_id: str,
        stats: Dict[str, Any],
        nano_cpus_limit: int = 0,
        has_foreground_viewers: bool = True,
        current_monotonic: Optional[float] = None,
    ) -> ProfileQuotaDecision:
        """Process Docker container stats dict and evaluate quota decision."""
        profile_state = self.get_profile_state(profile_id)
        profile_state.foreground_viewers = has_foreground_viewers
        if container_id not in profile_state.containers:
            profile_state.containers[container_id] = ContainerTrackedState(container_id)
        c_state = profile_state.containers[container_id]
        state = c_state

        now_mono = (
            current_monotonic if current_monotonic is not None else time.monotonic()
        )
        now_wall = time.time()

        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})
        cur_usage = cpu_stats.get("cpu_usage", {}).get("total_usage")
        cur_sys = cpu_stats.get("system_cpu_usage")

        if (
            not stats
            or type(cur_usage) is not int
            or cur_usage < 0
            or type(cur_sys) is not int
            or cur_sys <= 0
        ):
            last = state.last_decision
            is_throttled = state.is_throttled
            cap = self.config.throttled_fps_cap if is_throttled else None
            dec = ProfileQuotaDecision(
                profile_id=profile_id,
                max_fps_cap=cap,
                is_throttled=is_throttled,
                reason="invalid_stats_retained_previous_state",
                observed_cpu_pct=last.observed_cpu_pct if last else 0.0,
                measurement_window_sec=last.measurement_window_sec if last else 0.0,
                sample_count=len(c_state.samples),
                timestamp=now_wall,
                observed_scope="invalid_stats",
            )
            state.last_decision = dec
            return self.evaluate_profile(profile_id)

        # Enforce min_measurement_interval_sec
        if c_state.samples:
            dt = now_mono - c_state.last_monotonic
            if dt < self.config.min_measurement_interval_sec:
                if state.last_decision:
                    return self.evaluate_profile(profile_id)

        if c_state.samples:
            previous = c_state.samples[-1]
            if (
                cur_sys == previous.system_cpu_usage_ns
                and cur_usage == previous.total_usage_ns
            ):
                return self.evaluate_profile(profile_id)
            if (
                cur_sys <= previous.system_cpu_usage_ns
                or cur_usage < previous.total_usage_ns
            ):
                # A daemon/container counter reset supplies a new baseline,
                # never evidence that an overloaded workload became idle.
                c_state.samples = [
                    ContainerCpuSample(
                        container_id,
                        now_wall,
                        now_mono,
                        cur_usage,
                        cur_sys,
                        cpu_stats.get("online_cpus") or self.config.host_ncpu,
                        nano_cpus_limit,
                    )
                ]
                c_state.last_monotonic = now_mono
                c_state.consecutive_overload_count = 0
                c_state.consecutive_recovery_count = 0
                return self.evaluate_profile(profile_id)
        online_cpus = cpu_stats.get("online_cpus") or self.config.host_ncpu
        pre_usage = precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        pre_sys = precpu_stats.get("system_cpu_usage", 0)

        sample = ContainerCpuSample(
            container_id=container_id,
            timestamp=now_wall,
            timestamp_monotonic=now_mono,
            total_usage_ns=cur_usage,
            system_cpu_usage_ns=cur_sys,
            online_cpus=online_cpus,
            nano_cpus_limit=nano_cpus_limit,
        )

        c_state.samples.append(sample)
        c_state.last_monotonic = now_mono
        c_state.last_total_usage_ns = cur_usage
        if len(c_state.samples) > 10:
            c_state.samples.pop(0)

        cpu_pct = 0.0
        scope = "container_quota" if nano_cpus_limit > 0 else "docker_host_capacity"

        # Determine calculation strategy:
        # Streaming responses have usable previous CPU/system counters.
        # Otherwise, calculate from our own container sample history (one_shot style)
        if pre_usage > 0 and pre_sys > 0 and cur_sys > pre_sys:
            cpu_pct, scope = calculate_quota_normalized_percent(
                current_usage_ns=cur_usage,
                previous_usage_ns=pre_usage,
                current_system_ns=cur_sys,
                previous_system_ns=pre_sys,
                online_cpus=online_cpus,
                nano_cpus_limit=nano_cpus_limit,
            )
        elif len(c_state.samples) >= 2:
            prev = c_state.samples[-2]
            cpu_pct, scope = calculate_quota_normalized_percent(
                current_usage_ns=sample.total_usage_ns,
                previous_usage_ns=prev.total_usage_ns,
                current_system_ns=sample.system_cpu_usage_ns,
                previous_system_ns=prev.system_cpu_usage_ns,
                online_cpus=online_cpus,
                nano_cpus_limit=nano_cpus_limit,
            )

        window_duration = 0.0
        if len(c_state.samples) >= 2:
            window_duration = max(
                0.0,
                c_state.samples[-1].timestamp_monotonic
                - c_state.samples[0].timestamp_monotonic,
            )

        if not has_foreground_viewers:
            state.consecutive_overload_count = 0
            state.consecutive_recovery_count = 0
            state.is_throttled = False
            decision = ProfileQuotaDecision(
                profile_id=profile_id,
                max_fps_cap=None,
                is_throttled=False,
                reason="nominal_background",
                observed_cpu_pct=cpu_pct,
                measurement_window_sec=window_duration,
                sample_count=len(c_state.samples),
                timestamp=now_wall,
                observed_scope=scope,
            )
            state.last_decision = decision
            return self.evaluate_profile(profile_id)

        if cpu_pct >= self.config.overload_cpu_threshold_pct:
            state.consecutive_overload_count += 1
            state.consecutive_recovery_count = 0
            if state.consecutive_overload_count >= self.config.overload_window_samples:
                state.is_throttled = True
                if nano_cpus_limit > 0:
                    reason = (
                        f"container_quota_overload_cpu_{cpu_pct:.1f}_pct_exceeded_"
                        f"{self.config.overload_cpu_threshold_pct:.1f}"
                    )
                else:
                    reason = (
                        f"overload_cpu_{cpu_pct:.1f}_pct_exceeded_"
                        f"{self.config.overload_cpu_threshold_pct:.1f}"
                    )
            else:
                reason = (
                    f"pending_overload_sample_{state.consecutive_overload_count}_of_"
                    f"{self.config.overload_window_samples}"
                )
        elif cpu_pct <= self.config.recovery_cpu_threshold_pct:
            state.consecutive_recovery_count += 1
            state.consecutive_overload_count = 0
            if state.is_throttled:
                if (
                    state.consecutive_recovery_count
                    >= self.config.recovery_window_samples
                ):
                    state.is_throttled = False
                    reason = (
                        f"recovered_cpu_{cpu_pct:.1f}_pct_below_"
                        f"{self.config.recovery_cpu_threshold_pct:.1f}"
                    )
                else:
                    reason = (
                        f"pending_recovery_sample_{state.consecutive_recovery_count}_of_"
                        f"{self.config.recovery_window_samples}"
                    )
            else:
                reason = f"nominal_cpu_{cpu_pct:.1f}_pct"
        else:
            state.consecutive_overload_count = 0
            state.consecutive_recovery_count = 0
            if state.is_throttled:
                reason = (
                    f"hysteresis_deadband_cpu_{cpu_pct:.1f}_pct_maintaining_throttle"
                )
            else:
                reason = f"nominal_cpu_{cpu_pct:.1f}_pct"

        cap = self.config.throttled_fps_cap if state.is_throttled else None
        decision = ProfileQuotaDecision(
            profile_id=profile_id,
            max_fps_cap=cap,
            is_throttled=state.is_throttled,
            reason=reason,
            observed_cpu_pct=cpu_pct,
            measurement_window_sec=window_duration,
            sample_count=len(c_state.samples),
            timestamp=now_wall,
            observed_scope=scope,
        )
        state.last_decision = decision
        return self.evaluate_profile(profile_id)

    def evaluate_profile(
        self,
        profile_id: str,
        has_foreground_viewers: Optional[bool] = None,
    ) -> ProfileQuotaDecision:
        """Compose independent container/host pressure using current visibility."""
        state = self.get_profile_state(profile_id)
        if has_foreground_viewers is not None:
            state.foreground_viewers = has_foreground_viewers
        now_wall = time.time()
        if not state.foreground_viewers:
            decision = ProfileQuotaDecision(
                profile_id,
                None,
                False,
                "nominal_background",
                0.0,
                0.0,
                0,
                now_wall,
                "background",
            )
        elif self._host_is_throttled:
            duration = (
                self._host_samples[-1].timestamp_monotonic
                - self._host_samples[0].timestamp_monotonic
            )
            decision = ProfileQuotaDecision(
                profile_id,
                self.config.throttled_fps_cap,
                True,
                f"host_cpu_overload_{self._last_host_pct:.1f}_pct",
                self._last_host_pct,
                duration,
                len(self._host_samples),
                now_wall,
                "docker_host_linux",
            )
        else:
            candidates = [
                container.last_decision
                for container in state.containers.values()
                if container.last_decision is not None
            ]
            if candidates:
                decision = max(
                    candidates,
                    key=lambda item: (item.is_throttled, item.observed_cpu_pct),
                )
            else:
                decision = ProfileQuotaDecision(
                    profile_id,
                    None,
                    False,
                    "initial_nominal",
                    0.0,
                    0.0,
                    0,
                    now_wall,
                    "initial",
                )
        state.last_decision = decision
        state.is_throttled = decision.is_throttled
        return decision

    def sample_container_stats(
        self,
        profile_id: str,
        container_id: str,
        nano_cpus_limit: int = 0,
        has_foreground_viewers: bool = True,
    ) -> Optional[ProfileQuotaDecision]:
        """Query and evaluate real Docker stats with one_shot=True."""
        if not self.docker_client:
            raise RuntimeError(
                "docker_client must be injected to sample container stats"
            )

        try:
            container = self.docker_client.containers.get(container_id)
            actual_limit = container_cpu_limit(container.attrs.get("HostConfig", {}))
            if actual_limit > 0:
                nano_cpus_limit = (
                    min(actual_limit, nano_cpus_limit)
                    if nano_cpus_limit > 0
                    else actual_limit
                )
            stats = container.stats(stream=False, one_shot=True)
            return self.record_stats(
                profile_id=profile_id,
                container_id=container_id,
                stats=stats,
                nano_cpus_limit=nano_cpus_limit,
                has_foreground_viewers=has_foreground_viewers,
            )
        except Exception as exc:
            logger.error(
                "Failed to query Docker stats for container: error_type=%s",
                type(exc).__name__,
            )
            return None

    def sample_host_proc_stat(self) -> Optional[Dict[str, ProfileQuotaDecision]]:
        """Sample host /proc/stat using injected reader."""
        if not self.host_stat_reader:
            return None
        try:
            content = self.host_stat_reader()
            sample = parse_linux_proc_stat_cpu(content)
            return self.record_host_sample(sample)
        except Exception as exc:
            logger.error(
                "Failed to sample host /proc/stat: error_type=%s", type(exc).__name__
            )
            return None

    def get_decision(self, profile_id: str) -> Optional[ProfileQuotaDecision]:
        state = self._profiles.get(profile_id)
        return state.last_decision if state else None

    def reset_profile(self, profile_id: str) -> None:
        self._profiles.pop(profile_id, None)
