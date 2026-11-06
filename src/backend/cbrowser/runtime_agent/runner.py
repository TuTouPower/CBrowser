"""Browser Runner managing display, audio, CloakBrowser process and exit observation."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import re
import signal
import subprocess
import time
import urllib.request
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any
from urllib.parse import quote

from cbrowser.domain.models import ConfigVersionSnapshot, ProfileConfig
from cbrowser.domain.runtime_policy import ExitReason
from cloakbrowser import launch_persistent_context_async
from cloakbrowser.browser import seed_widevine_hint
from cloakbrowser.config import PLATFORM_CHROMIUM_VERSIONS

from .event_storage import EventStorage, atomic_write_json
from .fontconfig import (
    profile_font_dirs,
    prepare_profile_fontconfig,
)
from .profile_defaults import (
    SEARCH_DEFAULTS_RETRY_FILE,
    run_search_defaults_initialization,
)
from .protocol import RuntimeEventRecord, RuntimeStateRecord
from cbrowser.launch_args import validate_launch_args

from .security import validate_runtime_id

logger = logging.getLogger("cbrowser.runtime_agent.runner")


PROXY_CREDENTIALS_FILENAME = "proxy_credentials.json"
PROXY_CREDENTIALS_CHANGED = "proxy_credentials_changed"
_PROXY_SCHEMES = frozenset({"http", "https", "socks5"})


class ProxyCredentialsChangedError(RuntimeError):
    """Fail closed when runtime proxy credentials are missing or stale.

    The message is a fixed, non-sensitive reason string: the password is
    never embedded in an exception, log line, or reported runtime state.
    """

    def __init__(self) -> None:
        super().__init__(PROXY_CREDENTIALS_CHANGED)


def build_proxy_server_arg(credentials: dict[str, Any]) -> str:
    """Build ``--proxy-server=...`` from validated proxy credentials.

    Chromium accepts inline credentials in the proxy URL (verified for
    authenticated SOCKS5 in finding d031). Credentials are percent-encoded so
    special characters cannot break URL parsing. The secret is only ever used
    inside the returned launch argument, never in an error or log message.
    """
    if not isinstance(credentials, dict):
        raise ProxyCredentialsChangedError()
    scheme = credentials.get("scheme")
    host = credentials.get("host")
    port = credentials.get("port")
    if scheme not in _PROXY_SCHEMES or not isinstance(host, str) or not host:
        raise ProxyCredentialsChangedError()
    if type(port) is not int or not 1 <= port <= 65535:
        raise ProxyCredentialsChangedError()
    username = credentials.get("username")
    password = credentials.get("password")
    if username is not None and not isinstance(username, str):
        raise ProxyCredentialsChangedError()
    if password is not None and not isinstance(password, str):
        raise ProxyCredentialsChangedError()
    if username is None and password is not None:
        raise ProxyCredentialsChangedError()
    userinfo = ""
    if username is not None:
        encoded_user = quote(username, safe="")
        if password is not None:
            userinfo = f"{encoded_user}:{quote(password, safe='')}@"
        else:
            userinfo = f"{encoded_user}@"
    netloc_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"--proxy-server={scheme}://{userinfo}{netloc_host}:{port}"


def resolve_proxy_server_arg(
    config: ProfileConfig,
    snapshot: ConfigVersionSnapshot,
    credentials_path: Path,
) -> str | None:
    """Return the proxy launch arg, or fail closed on missing/stale credentials.

    A profile without a proxy id gets no proxy argument. Otherwise the mounted
    credentials file must exist and its revision must match the frozen revision
    in the bound config snapshot; any drift is a fail-closed
    ``proxy_credentials_changed`` error.
    """
    if not config.proxy_id:
        return None
    try:
        credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ProxyCredentialsChangedError() from None
    if not isinstance(credentials, dict):
        raise ProxyCredentialsChangedError()
    if credentials.get("credential_revision") != snapshot.proxy_credential_revision:
        raise ProxyCredentialsChangedError()
    return build_proxy_server_arg(credentials)


def load_config_snapshot(
    profile_id: str,
    config_snapshot_path: Path,
) -> tuple[ConfigVersionSnapshot, ProfileConfig]:
    """Validate the frozen config before creating runtime paths or processes."""
    validate_runtime_id(profile_id)
    if not config_snapshot_path.is_file():
        raise ValueError("Config snapshot file not found")
    try:
        snapshot = ConfigVersionSnapshot.model_validate(
            json.loads(config_snapshot_path.read_text(encoding="utf-8"))
        )
    except Exception as exc:  # noqa: BLE001 - corrupted config snapshot file wrapped into ValueError
        logger.error("Failed to parse config snapshot (%s)", type(exc).__name__)
        raise ValueError("Invalid config snapshot format") from None
    validate_runtime_id(snapshot.profile_id)
    if snapshot.version < 1:
        raise ValueError("Invalid config snapshot version")
    if snapshot.profile_id != profile_id:
        raise ValueError("profile_id mismatch")
    try:
        config = ProfileConfig.model_validate(snapshot.config)
    except Exception as exc:  # noqa: BLE001 - config schema validation error wrapped into ValueError
        logger.error("Invalid ProfileConfig (%s)", type(exc).__name__)
        raise ValueError("ProfileConfig validation failed") from None
    return snapshot, config


class BrowserRunner:
    """Manages the full lifecycle of Xvfb, Openbox, PulseAudio, and CloakBrowser."""

    def __init__(
        self,
        profile_id: str,
        runtime_instance_id: str,
        config_snapshot_path: Path | str,
        run_dir: Path | str,
        user_data_dir: Path | str,
        events_dir: Path | str | None = None,
        engine_cache_dir: Path | str = "/data/engine-cache",
        display: str = ":99",
        engine_build: str | None = None,
    ) -> None:
        self.profile_id = validate_runtime_id(profile_id)
        self.runtime_instance_id = validate_runtime_id(runtime_instance_id)
        self.config_snapshot_path = Path(config_snapshot_path)
        self.run_dir = Path(run_dir)
        self.user_data_dir = Path(user_data_dir)
        self.events_dir = Path(events_dir) if events_dir else self.run_dir
        self.engine_cache_dir = Path(engine_cache_dir)
        self.display = display
        if engine_build is not None and (
            not isinstance(engine_build, str)
            or not re.fullmatch(r"\d+\.\d+\.\d+\.\d+(?:\.\d+)?(?:-pro)?", engine_build)
        ):
            raise ValueError("Invalid initialized engine build")
        self.engine_build = engine_build

        # 1. Strictly validate immutable configuration snapshot before starting
        self.snapshot, self.profile_config = load_config_snapshot(
            self.profile_id, self.config_snapshot_path
        )
        self.config_version = self.snapshot.version

        self.event_storage = EventStorage(self.events_dir)
        self.pulse_dir = self.run_dir / "pulse"
        self.openbox_dir = self.run_dir / "openbox"
        self.x11_dir = Path("/tmp/.X11-unix")
        self.x11_config_dir = self.run_dir / "x11-config"
        self.xauth_path = self.run_dir / "Xauthority"
        self.runner_info_file = self.run_dir / "runner_info.json"

        self.fontconfig_path: Path | None = None
        self.xvfb_proc: subprocess.Popen[Any] | None = None
        self.openbox_proc: subprocess.Popen[Any] | None = None
        self.chrome_pid: int | None = None
        self.cdp_port: int | None = None
        self.browser_ws_url: str | None = None
        self.browser_context: Any = None
        self.browser_version: str | None = None
        self.is_running = False
        self.exit_task: asyncio.Task[None] | None = None
        self._search_defaults_retry_task: asyncio.Task[None] | None = None
        # Bounded dedupe window for retry request ids (review
        # t022_code_f015): only the most recent ids are remembered.
        self._search_defaults_processed_requests: OrderedDict[str, None] = (
            OrderedDict()
        )

    def resolve_engine_binary(self) -> Path:
        """Use the SDK's exact Linux build and reject an incompatible cache."""
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            target, elf_machine = "linux-arm64", 183
        elif machine in ("x86_64", "amd64"):
            target, elf_machine = "linux-x64", 62
        else:
            raise RuntimeError("Unsupported runtime engine architecture")

        build = self.engine_build or PLATFORM_CHROMIUM_VERSIONS[target]
        version = build.removesuffix("-pro")
        cache = self.engine_cache_dir.resolve()
        candidate = cache / f"chromium-{build}" / "chrome"
        try:
            binary = candidate.resolve(strict=True)
            binary.relative_to(cache)
            if binary.parent.name != f"chromium-{build}" or binary.name != "chrome":
                raise ValueError("Unexpected engine cache target")
            if not binary.is_file() or not os.access(binary, os.X_OK):
                raise ValueError("Engine is not executable")
            with binary.open("rb") as source:
                header = source.read(64)
            if (
                len(header) < 64
                or header[:7] != b"\x7fELF\x02\x01\x01"
                or int.from_bytes(header[18:20], "little") != elf_machine
            ):
                raise ValueError("Engine ELF architecture mismatch")
            result = subprocess.run(
                [str(binary), "--version"],
                env=dict(os.environ),
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            chromium_version = ".".join(version.split(".")[:4])
            if chromium_version not in re.findall(
                r"\b\d+\.\d+\.\d+\.\d+\b", result.stdout
            ):
                raise ValueError("Engine Chromium version mismatch")
        except (OSError, ValueError, subprocess.SubprocessError):
            raise RuntimeError("Missing or incompatible unified engine cache") from None

        self.browser_version = version
        return binary

    def setup_pulse(self) -> tuple[Path, Path]:
        """Configure and start PulseAudio daemon with 48000Hz null sink."""
        self.pulse_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.pulse_dir.chmod(0o700)
        cookie_path = self.pulse_dir / "pulse.cookie"
        sock_path = self.pulse_dir / "pulse.sock"

        if not cookie_path.exists() or cookie_path.stat().st_size != 256:
            cookie_path.write_bytes(os.urandom(256))
        cookie_path.chmod(0o600)

        config_dir = self.pulse_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        config_dir.chmod(0o700)
        daemon_conf = config_dir / "daemon.conf"
        daemon_conf.write_text(
            "default-sample-rate = 48000\n"
            "alternate-sample-rate = 48000\n"
            # The virtual sink is the Agent's audio readiness anchor; the
            # default 20s idle timeout makes the daemon (and its socket)
            # disappear whenever Chrome is not actively playing audio.
            "exit-idle-time = -1\n",
            encoding="utf-8",
        )
        daemon_conf.chmod(0o600)

        pulse_pa = self.pulse_dir / "pulse.pa"
        pulse_pa.write_text(
            f"load-module module-native-protocol-unix auth-anonymous=0 "
            f"auth-cookie={cookie_path} socket={sock_path}\n"
            f"load-module module-null-sink sink_name=cbrowser_sink rate=48000 "
            f'format=s16le channels=2 sink_properties=device.description="Virtual"\n'
            f"set-default-sink cbrowser_sink\n",
            encoding="utf-8",
        )
        pulse_pa.chmod(0o600)

        env = dict(os.environ)
        env["PULSE_CONFIG_PATH"] = str(config_dir)
        env["PULSE_COOKIE"] = str(cookie_path)

        proc = subprocess.run(
            [
                "pulseaudio",
                "--system=false",
                "--daemonize=yes",
                "--fail=yes",
                f"--file={pulse_pa}",
                "-n",
            ],
            env=env,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0 and not sock_path.exists():
            err = proc.stderr.decode().strip()
            logger.error("Failed to start PulseAudio daemon: %s", err)
            raise RuntimeError(f"PulseAudio start failed: {err}")

        logger.info("PulseAudio initialized at 48000Hz (socket=%s)", sock_path)
        return sock_path, cookie_path

    @staticmethod
    def _clear_stale_x11_state(lock_path: Path, sock_path: Path) -> None:
        """Drop X11 leftovers only when staleness is actually proven.

        Proven means one of: the lock names a PID that no longer exists,
        or — with no lock at all — the socket refuses connections. A
        missing lock alone proves nothing about the socket: a live X
        server whose lock was removed externally keeps its socket
        (review t022_code_f012).
        """
        if lock_path.exists():
            try:
                holder = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                # An unreadable or corrupt lock cannot prove the display is
                # stale; keep the lock and its socket untouched.
                raise RuntimeError(
                    "X display lock cannot be verified as stale; refusing to remove it"
                ) from None
            try:
                os.kill(holder, 0)
            except ProcessLookupError:
                pass
            except PermissionError:
                raise RuntimeError("X display is held by another process") from None
            else:
                raise RuntimeError("X display is already in use")
            lock_path.unlink(missing_ok=True)
            sock_path.unlink(missing_ok=True)
            return
        if not sock_path.exists():
            return
        import socket as _socket

        probe = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        try:
            probe.settimeout(1.0)
            probe.connect(str(sock_path))
        except (ConnectionRefusedError, FileNotFoundError):
            sock_path.unlink(missing_ok=True)
        except OSError:
            raise RuntimeError(
                "X display socket cannot be verified as stale; refusing to remove it"
            ) from None
        else:
            raise RuntimeError("X display is already in use") from None
        finally:
            probe.close()

    def setup_display(self, width: int = 1920, height: int = 1080) -> Path:
        """Configure Xauthority, start Xvfb, and launch Openbox."""
        self.x11_dir.mkdir(parents=True, exist_ok=True)
        self.x11_config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.x11_config_dir.chmod(0o700)
        cookie_file = self.x11_config_dir / "cookie.hex"
        mcookie = os.urandom(16).hex()
        cookie_file.write_text(mcookie, encoding="utf-8")
        cookie_file.chmod(0o600)

        self.xauth_path.touch(mode=0o600, exist_ok=True)
        subprocess.run(
            [
                "xauth",
                "-q",
                "-f",
                str(self.xauth_path),
                "add",
                self.display,
                ".",
                mcookie,
            ],
            env=dict(os.environ),
            check=True,
        )
        self.xauth_path.chmod(0o600)

        xvfb_cmd = [
            "Xvfb",
            self.display,
            "-auth",
            str(self.xauth_path),
            "-screen",
            "0",
            f"{width}x{height}x24",
            "-dpi",
            "96",
            "+extension",
            "MIT-SHM",
            "+extension",
            "XTEST",
            "+extension",
            "XFIXES",
            "-nolisten",
            "tcp",
        ]
        display_num = self.display.lstrip(":")
        sock_path = self.x11_dir / f"X{display_num}"
        lock_path = Path(f"/tmp/.X{display_num}-lock")

        # Remove only a stale lock whose owner is gone; a live display is an error.
        self._clear_stale_x11_state(lock_path, sock_path)

        self.xvfb_proc = subprocess.Popen(
            xvfb_cmd,
            env=dict(os.environ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        logger.info("Started Xvfb on %s (pid %d)", self.display, self.xvfb_proc.pid)

        display_num = self.display.lstrip(":")
        sock_path = self.x11_dir / f"X{display_num}"
        for _ in range(50):
            if sock_path.exists():
                break
            time.sleep(0.05)

        if not sock_path.exists():
            xvfb_err = (
                self.xvfb_proc.stderr.read().decode() if self.xvfb_proc.stderr else ""
            )
            logger.error("Xvfb failed: %s", xvfb_err)
            raise RuntimeError(
                f"Xvfb failed to create X11 socket at {sock_path}: {xvfb_err}"
            )

        self.openbox_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.openbox_dir.chmod(0o700)
        rc_file = self.openbox_dir / "rc.xml"
        rc_file.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<openbox_config xmlns="http://openbox.org/3.4/rc">\n'
            "  <applications>\n"
            '    <application class="*">\n'
            "      <maximized>yes</maximized>\n"
            "      <decor>no</decor>\n"
            "    </application>\n"
            "  </applications>\n"
            "</openbox_config>\n",
            encoding="utf-8",
        )
        rc_file.chmod(0o600)
        env = dict(os.environ)
        env["DISPLAY"] = self.display
        env["XAUTHORITY"] = str(self.xauth_path)
        self.openbox_proc = subprocess.Popen(
            ["openbox", "--config-file", str(rc_file)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(
            "Started Openbox on %s (pid %d)", self.display, self.openbox_proc.pid
        )
        return self.xauth_path

    def _browser_environment(
        self,
        pulse_sock: Path,
        pulse_cookie: Path,
        wrapper_path: Path,
        fontconfig_path: Path | None = None,
    ) -> dict[str, str]:
        """Build an explicit child environment instead of mutating ``os.environ``."""
        env = dict(os.environ)
        env.update(
            {
                "DISPLAY": self.display,
                "XAUTHORITY": str(self.xauth_path),
                "PULSE_SERVER": f"unix:{pulse_sock}",
                "PULSE_COOKIE": str(pulse_cookie),
                "CLOAKBROWSER_BINARY_PATH": str(wrapper_path),
                "CLOAKBROWSER_CACHE_DIR": str(self.engine_cache_dir),
            }
        )
        # A profile only sees its CJK bundle when a generated fontconfig file
        # was prepared for it; otherwise the variable must not leak in from
        # the runner's own environment.
        env.pop("FONTCONFIG_FILE", None)
        if fontconfig_path is not None:
            env["FONTCONFIG_FILE"] = str(fontconfig_path)
        return env

    @staticmethod
    def validate_launch_arguments(args: list[str] | None) -> list[str]:
        """Second launch-argument gate applied immediately before launch."""
        return validate_launch_args(args)

    async def _resolve_browser_version(self) -> tuple[str | None, str | None]:
        """Read CDP ``Browser.getVersion`` product and userAgent (AC-010).

        Once the persistent context is up, a Playwright CDP session can issue
        the browser-level command. This is observational only: any failure
        leaves both fields unset instead of blocking browser readiness.
        """
        try:
            context = self.browser_context
            pages = list(context.pages)
            page = pages[0] if pages else await context.new_page()
            session = await context.new_cdp_session(page)
            try:
                info = await session.send("Browser.getVersion")
            finally:
                await session.detach()
            product = info.get("product")
            user_agent = info.get("userAgent")
            return (
                product if isinstance(product, str) else None,
                user_agent if isinstance(user_agent, str) else None,
            )
        except Exception as exc:  # noqa: BLE001 - version observation is best-effort
            logger.warning(
                "Browser.getVersion unavailable (%s)", type(exc).__name__
            )
            return None, None

    async def start(self) -> None:
        """Initialize all subsystems and launch CloakBrowser."""
        cfg = self.profile_config
        width = cfg.screen_width
        height = cfg.screen_height

        # A generation is never relaunched: terminal journals recover independently
        # of a stale last-written cache, and incomplete generations require a new ID.
        if self.is_running:
            return
        prev_state = self.event_storage.get_instance_state(
            self.profile_id,
            self.runtime_instance_id,
            recover_terminal=True,
        )
        if prev_state is not None:
            if prev_state.state in ("stopped", "error"):
                logger.info("Terminal runtime launch suppressed")
                return
            raise RuntimeError("Runtime instance is already initialized")

        # Resolve proxy credentials before starting any subsystem. A missing
        # file or a stale credential revision fails closed without launching
        # the browser (AC-007 / AC-008).
        proxy_arg = resolve_proxy_server_arg(
            cfg,
            self.snapshot,
            self.config_snapshot_path.parent / PROXY_CREDENTIALS_FILENAME,
        )

        chrome_bin = self.resolve_engine_binary()
        self.event_storage.save_state(
            RuntimeStateRecord(
                profile_id=self.profile_id,
                runtime_instance_id=self.runtime_instance_id,
                config_version=self.config_version,
                state="starting",
            )
        )
        pulse_sock, pulse_cookie = self.setup_pulse()
        self.setup_display(width, height)

        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        font_dirs = profile_font_dirs(
            cfg.fingerprint_platform, cfg.font_set_id
        )
        self.fontconfig_path = prepare_profile_fontconfig(self.run_dir, font_dirs)
        # SDK capability/proxy selection uses the real build version. Seed CDM
        # metadata with the real binary before the process-observation wrapper
        # changes the SDK executable path. The SDK remains the only launch path.
        seed_widevine_hint(self.user_data_dir, chrome_bin)

        # Create wrapper to capture true Chrome process PID and exit code
        wrapper_path = self.run_dir / "chrome_wrapper.sh"
        pid_file = self.run_dir / "chrome.pid"
        exit_code_file = self.run_dir / "chrome.exit_code"
        pid_file.unlink(missing_ok=True)
        exit_code_file.unlink(missing_ok=True)

        wrapper_script = (
            f"#!/bin/bash\n"
            f'"{chrome_bin}" "$@" &\n'
            f"CPID=$!\n"
            f'echo "$CPID" > "{pid_file}"\n'
            f"wait $CPID\n"
            f"STATUS=$?\n"
            f'echo "$STATUS" > "{exit_code_file}"\n'
            f"exit $STATUS\n"
        )
        wrapper_path.write_text(wrapper_script, encoding="utf-8")
        wrapper_path.chmod(0o755)

        browser_env = self._browser_environment(
            pulse_sock, pulse_cookie, wrapper_path, self.fontconfig_path
        )

        # Second validation gate: the API already rejects non-whitelisted args.
        safe_user_args = validate_launch_args(cfg.launch_args)

        extra_args: list[str] = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-position=0,0",
            f"--window-size={width},{height}",
            "--force-device-scale-factor=1",
            "--remote-debugging-port=0",
            "--remote-debugging-address=127.0.0.1",
            "--autoplay-policy=no-user-gesture-required",
            f"--fingerprint-platform={cfg.fingerprint_platform}",
            f"--fingerprint-screen-width={width}",
            f"--fingerprint-screen-height={height}",
            # GTK is present only for the file chooser; its IME reads a stale
            # keymap after Selkies remaps keycodes for composed text.
            "--disable-gtk-ime",
        ]
        if cfg.fingerprint_seed:
            extra_args.append(f"--fingerprint={cfg.fingerprint_seed}")

        # Translate domain config options matching CloakBrowser and legacy semantics
        if cfg.gpu_family == "nvidia":
            extra_args.append("--fingerprint-gpu-vendor=NVIDIA")
        elif cfg.gpu_family == "intel":
            extra_args.append("--fingerprint-gpu-vendor=Intel")

        if cfg.allow_3p_cookies:
            extra_args.append("--fingerprint-allow-3p-cookies")
        if cfg.transparent_proxy:
            extra_args.append("--fingerprint-transparent-proxy")
        if cfg.portable_cookies:
            extra_args.append("--fingerprint-portable-cookies")
        if cfg.restore_session:
            extra_args.append("--restore-last-session")

        extra_args.extend(safe_user_args)
        if proxy_arg is not None:
            extra_args.append(proxy_arg)

        logger.info(
            "Launching CloakBrowser (profile=%s, instance=%s)...",
            self.profile_id,
            self.runtime_instance_id,
        )

        # CloakBrowser resolves the binary/cache from process environment before
        # spawning Playwright. Scope the mutation to this launch and restore it,
        # so no other subsystem observes runner-specific paths.
        previous_binary = os.environ.get("CLOAKBROWSER_BINARY_PATH")
        previous_cache = os.environ.get("CLOAKBROWSER_CACHE_DIR")
        os.environ["CLOAKBROWSER_BINARY_PATH"] = str(wrapper_path)
        os.environ["CLOAKBROWSER_CACHE_DIR"] = str(self.engine_cache_dir)
        try:
            self.browser_context = await launch_persistent_context_async(
                user_data_dir=str(self.user_data_dir),
                headless=False,
                args=extra_args,
                timezone=cfg.timezone,
                locale=cfg.locale,
                humanize=cfg.humanize,
                human_preset=cfg.human_preset,
                geoip=cfg.geoip,
                color_scheme=cfg.color_scheme,
                extension_paths=cfg.extension_paths or None,
                no_viewport=True,
                browser_version=self.browser_version,
                env=browser_env,
            )
        finally:
            if previous_binary is None:
                os.environ.pop("CLOAKBROWSER_BINARY_PATH", None)
            else:
                os.environ["CLOAKBROWSER_BINARY_PATH"] = previous_binary
            if previous_cache is None:
                os.environ.pop("CLOAKBROWSER_CACHE_DIR", None)
            else:
                os.environ["CLOAKBROWSER_CACHE_DIR"] = previous_cache
        logger.info("CloakBrowser persistent context initialized")

        # Discover true Chrome PID from wrapper
        for _ in range(50):
            if pid_file.exists():
                try:
                    self.chrome_pid = int(pid_file.read_text().strip())
                    break
                except (OSError, ValueError):
                    pass
            await asyncio.sleep(0.1)

        if not self.chrome_pid:
            raise RuntimeError("Failed to resolve Chrome PID from wrapper")

        # Discover CDP port from user_data_dir / DevToolsActivePort
        active_port_file = self.user_data_dir / "DevToolsActivePort"
        for _ in range(100):
            if active_port_file.exists():
                try:
                    lines = active_port_file.read_text().splitlines()
                    if lines:
                        self.cdp_port = int(lines[0])
                        break
                except (OSError, ValueError, IndexError):
                    pass
            await asyncio.sleep(0.1)

        if not self.cdp_port:
            raise RuntimeError(f"Failed to resolve CDP port from {active_port_file}")

        # Discover webSocketDebuggerUrl
        url = f"http://127.0.0.1:{self.cdp_port}/json/version"

        def _get_ws_url() -> str | None:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                data = json.loads(resp.read().decode())
                return data.get("webSocketDebuggerUrl")

        for _ in range(50):
            try:
                self.browser_ws_url = await asyncio.to_thread(_get_ws_url)
                if self.browser_ws_url:
                    break
            except Exception:  # noqa: BLE001 - CDP HTTP discovery poll catches connection error until ready
                await asyncio.sleep(0.1)

        if not self.browser_ws_url:
            raise RuntimeError("Failed to obtain webSocketDebuggerUrl from Chrome")

        browser_product, browser_user_agent = await self._resolve_browser_version()

        await self._configure_window(width, height)
        # Default-search setup is best-effort (D1=B): a failure or timeout is
        # recorded as an independent status and never blocks browser startup.
        await run_search_defaults_initialization(
            self.browser_context,
            self.user_data_dir,
            self.run_dir,
            set_google_default=cfg.set_google_default,
            runtime_instance_id=self.runtime_instance_id,
        )
        self.is_running = True

        # Write runner_info.json for the independent Agent process to consume
        runner_info = {
            "profile_id": self.profile_id,
            "runtime_instance_id": self.runtime_instance_id,
            "config_version": self.config_version,
            "cdp_port": self.cdp_port,
            "browser_ws_url": self.browser_ws_url,
            "display": self.display,
            "pulse_sock": str(pulse_sock),
            "pulse_cookie": str(pulse_cookie),
            "xauth_path": str(self.xauth_path),
            "browser_pid": self.chrome_pid,
            "runner_pid": os.getpid(),
            "engine_build": self.engine_build or self.browser_version,
            "browser_product": browser_product,
            "browser_user_agent": browser_user_agent,
        }
        self.event_storage.save_state(
            RuntimeStateRecord(
                profile_id=self.profile_id,
                runtime_instance_id=self.runtime_instance_id,
                config_version=self.config_version,
                state="running",
                browser_pid=self.chrome_pid,
            )
        )
        atomic_write_json(self.runner_info_file, runner_info)
        logger.info("Runner ready (browser_pid=%d)", self.chrome_pid)

        # Monitor Chrome process exit in background
        self.exit_task = asyncio.create_task(self._wait_for_chrome_exit(exit_code_file))
        self._search_defaults_retry_task = asyncio.create_task(
            self._watch_search_defaults_retries()
        )

    async def _process_search_defaults_retry(self) -> bool:
        """Consume one fenced retry request against the live browser context.

        Returns True when a request file was consumed. Requests naming another
        profile or a stale instance are rejected; a repeated request_id is an
        idempotent no-op. The browser is never restarted and existing tabs are
        untouched (initialization only opens and closes its own page).
        """
        request_path = self.run_dir / SEARCH_DEFAULTS_RETRY_FILE
        if not request_path.exists():
            return False
        try:
            request = json.loads(request_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            request_path.unlink(missing_ok=True)
            return True
        request_path.unlink(missing_ok=True)
        if (
            not isinstance(request, dict)
            or request.get("profile_id") != self.profile_id
            or request.get("runtime_instance_id") != self.runtime_instance_id
            or not isinstance(request.get("request_id"), str)
            or not request["request_id"]
        ):
            logger.warning("Search defaults retry rejected: identity mismatch")
            return True
        request_id = request["request_id"]
        if request_id in self._search_defaults_processed_requests:
            self._search_defaults_processed_requests.move_to_end(request_id)
            return True
        self._search_defaults_processed_requests[request_id] = None
        while len(self._search_defaults_processed_requests) > 64:
            self._search_defaults_processed_requests.popitem(last=False)
        await run_search_defaults_initialization(
            self.browser_context,
            self.user_data_dir,
            self.run_dir,
            set_google_default=self.profile_config.set_google_default,
            runtime_instance_id=self.runtime_instance_id,
            request_id=request_id,
        )
        return True

    async def _watch_search_defaults_retries(self) -> None:
        while True:
            try:
                await self._process_search_defaults_retry()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - watcher must survive bad requests
                logger.warning(
                    "Search defaults retry processing failed (%s)",
                    type(exc).__name__,
                )
            await asyncio.sleep(0.5)

    async def _configure_window(self, width: int, height: int) -> None:
        """Resize the actual Chrome window before publishing readiness."""
        env = dict(
            os.environ,
            DISPLAY=self.display,
            XAUTHORITY=str(self.xauth_path),
        )

        def _do_configure() -> bool:
            result = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--pid", str(self.chrome_pid)],
                env=env,
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            windows = result.stdout.splitlines()
            if result.returncode == 0 and windows:
                for window in windows:
                    subprocess.run(
                        ["xdotool", "windowsize", window, str(width), str(height)],
                        env=env,
                        capture_output=True,
                        check=True,
                        timeout=2,
                    )
                    subprocess.run(
                        ["xdotool", "windowmove", window, "0", "0"],
                        env=env,
                        capture_output=True,
                        check=True,
                        timeout=2,
                    )
                return True
            return False

        for _ in range(30):
            if await asyncio.to_thread(_do_configure):
                return
            await asyncio.sleep(0.2)
        raise RuntimeError("Chrome window did not become available")

    async def _wait_for_chrome_exit(self, exit_code_file: Path) -> None:
        """Poll for Chrome exit from wrapper and persist terminal state."""
        exit_code = None
        exit_reason = None
        while self.is_running:
            if exit_code_file.exists():
                try:
                    exit_code = int(exit_code_file.read_text().strip())
                    exit_reason = (
                        ExitReason.NORMAL.value
                        if exit_code == 0
                        else ExitReason.ABNORMAL.value
                    )
                    break
                except (OSError, ValueError):
                    pass
            # Also check if chrome_pid is alive
            if self.chrome_pid:
                try:
                    os.kill(self.chrome_pid, 0)
                except OSError:
                    # Allow the wrapper to finish recording its real wait status.
                    for _ in range(10):
                        await asyncio.sleep(0.1)
                        if exit_code_file.exists():
                            try:
                                exit_code = int(exit_code_file.read_text().strip())
                                exit_reason = (
                                    ExitReason.NORMAL.value
                                    if exit_code == 0
                                    else ExitReason.ABNORMAL.value
                                )
                                break
                            except (OSError, ValueError):
                                pass
                    if exit_code is None:
                        # Missing status is an observation failure.
                        logger.warning(
                            "Chrome process disappeared without exit code from wrapper"
                        )
                        exit_code = None
                        exit_reason = ExitReason.ABNORMAL_LOST.value
                    break
            await asyncio.sleep(0.2)

        if exit_code is None and exit_reason is None:
            exit_reason = ExitReason.ABNORMAL_LOST.value

        # The pinned SDK owns a Playwright driver process. Losing that control
        # pipe can make Chrome exit zero (d016); zero alone is not a user close.
        infrastructure_failure = exit_code is None or (
            exit_code == 0
            and (
                not self._sdk_driver_alive()
                or (self.xvfb_proc is not None and self.xvfb_proc.poll() is not None)
            )
        )
        if infrastructure_failure:
            exit_reason = ExitReason.PROCESS_OBSERVATION_LOST.value

        logger.info(
            "Chrome process terminated with exit code %s (reason=%s)",
            exit_code,
            exit_reason,
        )

        event = RuntimeEventRecord(
            event_id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"cbrowser/{self.profile_id}/{self.runtime_instance_id}/exit",
                )
            ),
            profile_id=self.profile_id,
            runtime_instance_id=self.runtime_instance_id,
            event_type="lifecycle" if infrastructure_failure else "exit",
            exit_code=None if infrastructure_failure else exit_code,
            exit_reason=exit_reason,
            config_version=self.config_version,
            payload={"exit_code": exit_code, "exit_reason": exit_reason},
        )
        self.event_storage.save_runtime_event(event)

        state = RuntimeStateRecord(
            profile_id=self.profile_id,
            runtime_instance_id=self.runtime_instance_id,
            config_version=self.config_version,
            state="error" if infrastructure_failure else "stopped",
            exit_code=exit_code,
            exit_reason=exit_reason,
            browser_pid=self.chrome_pid,
        )
        self.event_storage.save_state(state)

        # Acknowledge termination only after both durable writes succeed.
        self.is_running = False
        logger.info("Exit event and terminal state persisted. No restart.")
        if infrastructure_failure:
            raise RuntimeError("Browser process observation failed")

    def _sdk_driver_alive(self) -> bool:
        """Observe the pinned Playwright transport, rather than infer from CDP."""
        try:
            process = self.browser_context._impl_obj._connection._transport._proc
            if process is None or process.returncode is not None:
                return False
            process_stat = Path(f"/proc/{process.pid}/stat").read_text()
            return process_stat.rsplit(")", 1)[1].split()[0] not in ("Z", "X")
        except (AttributeError, OSError, IndexError):
            return False

    async def stop(self) -> None:
        """Gracefully stop browser context, Xvfb and Openbox."""
        if (
            self._search_defaults_retry_task is not None
            and not self._search_defaults_retry_task.done()
        ):
            self._search_defaults_retry_task.cancel()
            try:
                await self._search_defaults_retry_task
            except asyncio.CancelledError:
                pass
        if self.exit_task is not None and not self.exit_task.done():
            self.exit_task.cancel()
            try:
                await self.exit_task
            except asyncio.CancelledError:
                pass
        if self.browser_context:
            try:
                await self.browser_context.close()
            except Exception as exc:  # noqa: BLE001 - browser context cleanup failure logged without masking teardown
                logger.debug(
                    "Browser context close failed during stop: %s",
                    type(exc).__name__,
                )

        if self.openbox_proc and self.openbox_proc.poll() is None:
            self.openbox_proc.terminate()
            try:
                self.openbox_proc.wait(timeout=1)
            except Exception as exc:  # noqa: BLE001 - openbox process wait timeout during stop logged
                logger.debug(
                    "Openbox wait failed during stop: %s", type(exc).__name__
                )

        if self.xvfb_proc and self.xvfb_proc.poll() is None:
            self.xvfb_proc.terminate()
            try:
                self.xvfb_proc.wait(timeout=1)
            except Exception as exc:  # noqa: BLE001 - xvfb process wait timeout during stop logged
                logger.debug(
                    "Xvfb wait failed during stop: %s", type(exc).__name__
                )
        self.is_running = False
        logger.info("Runner stopped cleanly")


def main() -> None:
    """Command-line entrypoint for independent Browser Runner process."""
    import argparse

    parser = argparse.ArgumentParser(description="Browser Runner")
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--config-snapshot", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--user-data-dir", required=True)
    parser.add_argument("--events-dir")
    parser.add_argument("--engine-cache-dir", default="/data/engine-cache")
    parser.add_argument("--display", default=":99")
    parser.add_argument(
        "--engine-build",
        help="Initialized SDK cache build, including -pro when applicable",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] runner: %(message)s"
    )
    runner = BrowserRunner(
        profile_id=args.profile_id,
        runtime_instance_id=args.runtime_instance_id,
        config_snapshot_path=args.config_snapshot,
        run_dir=args.run_dir,
        user_data_dir=args.user_data_dir,
        events_dir=args.events_dir,
        engine_cache_dir=args.engine_cache_dir,
        display=args.display,
        engine_build=args.engine_build,
    )

    async def run():
        loop = asyncio.get_running_loop()
        stopping = asyncio.Event()
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(signum, stopping.set)
        stop_task = asyncio.create_task(stopping.wait())
        try:
            await runner.start()
            if runner.exit_task is not None:
                done, _ = await asyncio.wait(
                    [runner.exit_task, stop_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if runner.exit_task in done:
                    await runner.exit_task
        finally:
            stop_task.cancel()
            await asyncio.gather(stop_task, return_exceptions=True)
            await runner.stop()
            for signum in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(signum)

    asyncio.run(run())


if __name__ == "__main__":
    try:
        main()
    except ProxyCredentialsChangedError:
        logger.error("Browser Runner refused to launch: proxy_credentials_changed")
        raise SystemExit(1) from None
    except Exception as exc:  # noqa: BLE001 - CLI top-level exception handler redacts credentials and exits status 1
        # SDK exceptions can embed launch arguments and proxy credentials.
        logger.error("Browser Runner failed (%s)", type(exc).__name__)
        raise SystemExit(1) from None
