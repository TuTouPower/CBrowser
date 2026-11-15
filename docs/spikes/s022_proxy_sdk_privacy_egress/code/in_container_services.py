#!/usr/bin/env python3
"""Controlled isolated spike services for s022 proxy & privacy verification.

Runs inside a dedicated container in the isolated Docker network.
Provides:
- Spike CA + leaf TLS certificates (including SANs for controlled echo/DNS tests)
- Controlled HTTP/HTTPS echo target & WebRTC ICE test page
- Controlled HTTP proxy & TLS-wrapped HTTPS proxy (no-auth and 407 Basic auth)
- Controlled SOCKS5 proxy (no-auth, RFC1929 auth, CONNECT, UDP ASSOCIATE modes)
- Controlled STUN UDP/TCP server
- Controlled UDP/QUIC probe listener
- Controlled DNS UDP/TCP server
"""

from __future__ import annotations

import argparse
import base64
import datetime
import ipaddress
import json
import os
import select
import socket
import ssl
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


class EventLog:
    """Thread-safe JSONL event recorder (never logs passwords)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("", encoding="utf-8")

    def emit(self, kind: str, **fields: Any) -> None:
        record = {"ts": round(time.time(), 4), "kind": kind, **fields}
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


def generate_spike_certs(
    cert_dir: Path,
    own_ip: str,
    extra_ips: list[str],
    extra_dns: list[str],
) -> tuple[Path, Path, Path]:
    """Generate a spike-only CA and leaf cert covering test IPs and hostnames."""
    cert_dir.mkdir(parents=True, exist_ok=True)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "s022-spike-ca")])
    ca_pub = ca_key.public_key()
    ca_ski = x509.SubjectKeyIdentifier.from_public_key(ca_pub)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_pub)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(hours=1))
        .not_valid_after(now + datetime.timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(ca_ski, critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ca_ski), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, own_ip)])
    san_items: list[x509.GeneralName] = []
    for ip_str in [own_ip, *extra_ips]:
        if ip_str:
            san_items.append(x509.IPAddress(ipaddress.ip_address(ip_str)))
    for host in ["localhost", "api.ipify.org", "checkip.amazonaws.com", "ifconfig.me", *extra_dns]:
        san_items.append(x509.DNSName(host))

    leaf_cert = (
        x509.CertificateBuilder()
        .subject_name(leaf_name)
        .issuer_name(ca_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(hours=1))
        .not_valid_after(now + datetime.timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(san_items), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ca_ski), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    ca_path = cert_dir / "ca.crt"
    cert_path = cert_dir / "server.crt"
    key_path = cert_dir / "server.key"
    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(leaf_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        leaf_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return ca_path, cert_path, key_path


def _pipe_sockets(a: socket.socket, b: socket.socket) -> None:
    try:
        while True:
            r, _, _ = select.select([a, b], [], [], 10.0)
            if not r:
                continue
            for sock in r:
                data = sock.recv(65536)
                if not data:
                    return
                dst = b if sock is a else a
                dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (a, b):
            try:
                sock.close()
            except OSError:
                pass


def _resolve_target_host(
    host: str, override_map: dict[str, str]
) -> str:
    return override_map.get(host, host)


class ControlledHTTPProxy:
    """HTTP / HTTPS-wrapped forward + CONNECT proxy with optional 407 Basic auth."""

    def __init__(
        self,
        name: str,
        bind_ip: str,
        port: int,
        events: EventLog,
        *,
        auth_user: str | None = None,
        auth_pass: str | None = None,
        tls_context: ssl.SSLContext | None = None,
        host_overrides: dict[str, str] | None = None,
        echo_ip_override: str | None = None,
    ) -> None:
        self.name = name
        self.bind_ip = bind_ip
        self.port = port
        self.events = events
        self.auth_user = auth_user
        self.auth_pass = auth_pass
        self.tls_context = tls_context
        self.host_overrides = host_overrides or {}
        self.echo_ip_override = echo_ip_override

    def start(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.bind_ip, self.port))
        srv.listen(64)
        threading.Thread(target=self._accept_loop, args=(srv,), daemon=True).start()
        self.events.emit("proxy_ready", proxy=self.name, bind=f"{self.bind_ip}:{self.port}")

    def _accept_loop(self, srv: socket.socket) -> None:
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()

    def _check_auth(self, headers: dict[str, str]) -> str:
        if self.auth_user is None:
            return "not_required"
        raw = headers.get("proxy-authorization")
        if not raw:
            return "missing"
        parts = raw.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "basic":
            return "bad_scheme"
        try:
            decoded = base64.b64decode(parts[1].strip()).decode("utf-8")
        except Exception:
            return "bad_encoding"
        expected = f"{self.auth_user}:{self.auth_pass or ''}"
        return "ok" if decoded == expected else "wrong"

    def _handle_client(self, raw_conn: socket.socket, addr: tuple[str, int]) -> None:
        conn: socket.socket = raw_conn
        try:
            if self.tls_context is not None:
                try:
                    conn = self.tls_context.wrap_socket(raw_conn, server_side=True)
                except ssl.SSLError as exc:
                    self.events.emit(
                        "proxy_tls_error",
                        proxy=self.name,
                        client_ip=addr[0],
                        error=type(exc).__name__,
                    )
                    raw_conn.close()
                    return
            buf = b""
            while b"\r\n\r\n" not in buf and len(buf) < 65536:
                chunk = conn.recv(4096)
                if not chunk:
                    conn.close()
                    return
                buf += chunk
            head, rest = buf.split(b"\r\n\r\n", 1)
            lines = head.decode("latin-1").split("\r\n")
            if not lines or " " not in lines[0]:
                conn.close()
                return
            method, target, proto = (lines[0].split(" ", 2) + ["HTTP/1.1"])[:3]
            headers: dict[str, str] = {}
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            auth_state = self._check_auth(headers)
            self.events.emit(
                "http_proxy_request",
                proxy=self.name,
                client_ip=addr[0],
                method=method,
                target=target,
                auth_state=auth_state,
            )
            if self.auth_user is not None and auth_state != "ok":
                conn.sendall(
                    b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                    b'Proxy-Authenticate: Basic realm="s022"\r\n'
                    b"Content-Length: 0\r\n"
                    b"Connection: close\r\n\r\n"
                )
                conn.close()
                return

            if method.upper() == "CONNECT":
                host, _, port_str = target.rpartition(":")
                host = host.strip("[]")
                dst_port = int(port_str)
                dst_host = _resolve_target_host(host, self.host_overrides)
                if host in self.host_overrides and self.echo_ip_override and dst_port == 443:
                    # Route api.ipify.org etc. to controlled HTTPS echo server on 8443
                    dst_port = 8443
                upstream = socket.create_connection((dst_host, dst_port), timeout=5.0)
                conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                if rest:
                    upstream.sendall(rest)
                _pipe_sockets(conn, upstream)
                return

            parsed = urlparse(target)
            host = parsed.hostname or headers.get("host", "").split(":")[0]
            dst_port = parsed.port or (443 if parsed.scheme == "https" else 80)
            dst_host = _resolve_target_host(host, self.host_overrides)
            if self.echo_ip_override and host in ("api.ipify.org", "checkip.amazonaws.com", "ifconfig.me"):
                body = self.echo_ip_override.encode("utf-8")
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                    + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode("ascii")
                    + body
                )
                conn.close()
                return

            path = parsed.path or "/"
            if parsed.query:
                path += f"?{parsed.query}"
            out_headers = [f"{method} {path} {proto}"]
            for line in lines[1:]:
                k = line.split(":", 1)[0].strip().lower()
                if k in ("proxy-authorization", "proxy-connection"):
                    continue
                out_headers.append(line)
            upstream = socket.create_connection((dst_host, dst_port), timeout=5.0)
            upstream.sendall(("\r\n".join(out_headers) + "\r\n\r\n").encode("latin-1") + rest)
            _pipe_sockets(conn, upstream)
        except Exception as exc:
            self.events.emit("http_proxy_error", proxy=self.name, error=f"{type(exc).__name__}: {exc}")
            try:
                conn.close()
            except OSError:
                pass


class ControlledSOCKS5Proxy:
    """SOCKS5 proxy supporting no-auth, RFC1929 auth, CONNECT, and UDP ASSOCIATE."""

    def __init__(
        self,
        name: str,
        bind_ip: str,
        port: int,
        events: EventLog,
        *,
        auth_user: str | None = None,
        auth_pass: str | None = None,
        udp_mode: str = "relay",  # "relay" | "reject" | "drop"
        relay_advertise_ip: str | None = None,
        host_overrides: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.bind_ip = bind_ip
        self.port = port
        self.events = events
        self.auth_user = auth_user
        self.auth_pass = auth_pass
        self.udp_mode = udp_mode
        self.relay_advertise_ip = relay_advertise_ip or bind_ip
        self.host_overrides = host_overrides or {}

    def start(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.bind_ip, self.port))
        srv.listen(64)
        threading.Thread(target=self._accept_loop, args=(srv,), daemon=True).start()
        self.events.emit("proxy_ready", proxy=self.name, bind=f"{self.bind_ip}:{self.port}")

    def _accept_loop(self, srv: socket.socket) -> None:
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()

    @staticmethod
    def _recv_exact(conn: socket.socket, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            chunk = conn.recv(n - len(out))
            if not chunk:
                raise EOFError("unexpected EOF")
            out.extend(chunk)
        return bytes(out)

    def _handle_client(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        try:
            ver, nmethods = self._recv_exact(conn, 2)
            if ver != 5:
                conn.close()
                return
            methods = list(self._recv_exact(conn, nmethods))
            required_method = 0x02 if self.auth_user is not None else 0x00
            if required_method not in methods:
                conn.sendall(b"\x05\xff")
                self.events.emit(
                    "socks5_greeting_rejected",
                    proxy=self.name,
                    client_ip=addr[0],
                    methods=methods,
                )
                conn.close()
                return
            conn.sendall(bytes([5, required_method]))

            if required_method == 0x02:
                sub_ver, ulen = self._recv_exact(conn, 2)
                uname = self._recv_exact(conn, ulen).decode("utf-8", errors="replace")
                plen = self._recv_exact(conn, 1)[0]
                passwd = self._recv_exact(conn, plen).decode("utf-8", errors="replace")
                ok = (
                    sub_ver == 1
                    and uname == self.auth_user
                    and passwd == (self.auth_pass or "")
                )
                self.events.emit(
                    "socks5_auth",
                    proxy=self.name,
                    client_ip=addr[0],
                    ok=ok,
                )
                conn.sendall(b"\x01\x00" if ok else b"\x01\x01")
                if not ok:
                    conn.close()
                    return

            ver, cmd, _rsv, atyp = self._recv_exact(conn, 4)
            if ver != 5:
                conn.close()
                return
            if atyp == 1:
                dst_host = socket.inet_ntoa(self._recv_exact(conn, 4))
                atyp_name = "ipv4"
            elif atyp == 3:
                dlen = self._recv_exact(conn, 1)[0]
                dst_host = self._recv_exact(conn, dlen).decode("utf-8", errors="replace")
                atyp_name = "domain"
            elif atyp == 4:
                dst_host = socket.inet_ntop(socket.AF_INET6, self._recv_exact(conn, 16))
                atyp_name = "ipv6"
            else:
                conn.sendall(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
                conn.close()
                return
            dst_port = struct.unpack("!H", self._recv_exact(conn, 2))[0]
            self.events.emit(
                "socks5_request",
                proxy=self.name,
                client_ip=addr[0],
                cmd=cmd,
                atyp=atyp_name,
                dst_host=dst_host,
                dst_port=dst_port,
            )

            if cmd == 1:  # CONNECT
                mapped_host = _resolve_target_host(dst_host, self.host_overrides)
                mapped_port = 8443 if (dst_host in self.host_overrides and dst_port == 443) else dst_port
                upstream = socket.create_connection((mapped_host, mapped_port), timeout=5.0)
                bind_ip, bind_port = upstream.getsockname()[:2]
                conn.sendall(
                    b"\x05\x00\x00\x01"
                    + socket.inet_aton(bind_ip if ":" not in bind_ip else "0.0.0.0")
                    + struct.pack("!H", bind_port)
                )
                _pipe_sockets(conn, upstream)
                return

            if cmd == 3:  # UDP ASSOCIATE
                if self.udp_mode == "reject":
                    conn.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
                    conn.close()
                    return
                udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp_sock.bind((self.bind_ip, 0))
                relay_port = udp_sock.getsockname()[1]
                self.events.emit(
                    "socks5_udp_associate",
                    proxy=self.name,
                    client_ip=addr[0],
                    relay_ip=self.relay_advertise_ip,
                    relay_port=relay_port,
                    udp_mode=self.udp_mode,
                )
                conn.sendall(
                    b"\x05\x00\x00\x01"
                    + socket.inet_aton(self.relay_advertise_ip)
                    + struct.pack("!H", relay_port)
                )
                self._run_udp_relay(conn, udp_sock, addr[0])
                return

            conn.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
            conn.close()
        except Exception as exc:
            self.events.emit("socks5_error", proxy=self.name, error=f"{type(exc).__name__}: {exc}")
            try:
                conn.close()
            except OSError:
                pass

    def _run_udp_relay(
        self, tcp_conn: socket.socket, udp_sock: socket.socket, client_ip: str
    ) -> None:
        """Relay SOCKS5 UDP datagrams while TCP control socket stays open."""
        target_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_udp_addr: tuple[str, int] | None = None
        tcp_conn.setblocking(False)
        try:
            while True:
                r, _, _ = select.select([tcp_conn, udp_sock, target_sock], [], [], 2.0)
                if tcp_conn in r:
                    data = tcp_conn.recv(16)
                    if not data:
                        break
                if udp_sock in r:
                    pkt, src = udp_sock.recvfrom(65535)
                    if src[0] != client_ip:
                        continue
                    client_udp_addr = src
                    if len(pkt) < 10 or pkt[2] != 0:
                        continue
                    atyp = pkt[3]
                    if atyp == 1:
                        dst_ip = socket.inet_ntoa(pkt[4:8])
                        dst_port = struct.unpack("!H", pkt[8:10])[0]
                        payload = pkt[10:]
                    elif atyp == 3:
                        dlen = pkt[4]
                        dst_host = pkt[5 : 5 + dlen].decode("utf-8", errors="replace")
                        dst_port = struct.unpack("!H", pkt[5 + dlen : 7 + dlen])[0]
                        dst_ip = _resolve_target_host(dst_host, self.host_overrides)
                        payload = pkt[7 + dlen :]
                    else:
                        continue
                    self.events.emit(
                        "socks5_udp_datagram",
                        proxy=self.name,
                        src=f"{src[0]}:{src[1]}",
                        dst=f"{dst_ip}:{dst_port}",
                        size=len(payload),
                        udp_mode=self.udp_mode,
                    )
                    if self.udp_mode == "relay":
                        target_sock.sendto(payload, (dst_ip, dst_port))
                if target_sock in r and client_udp_addr is not None:
                    resp, rsrc = target_sock.recvfrom(65535)
                    hdr = (
                        b"\x00\x00\x00\x01"
                        + socket.inet_aton(rsrc[0])
                        + struct.pack("!H", rsrc[1])
                    )
                    udp_sock.sendto(hdr + resp, client_udp_addr)
        except OSError:
            pass
        finally:
            for s in (tcp_conn, udp_sock, target_sock):
                try:
                    s.close()
                except OSError:
                    pass


class ControlledSTUNServer:
    """Minimal RFC 5389 STUN Binding server on UDP & TCP."""

    MAGIC = 0x2112A442

    def __init__(self, bind_ip: str, port: int, events: EventLog) -> None:
        self.bind_ip = bind_ip
        self.port = port
        self.events = events

    def start(self) -> None:
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind((self.bind_ip, self.port))
        threading.Thread(target=self._udp_loop, args=(udp,), daemon=True).start()

        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.bind((self.bind_ip, self.port))
        tcp.listen(32)
        threading.Thread(target=self._tcp_loop, args=(tcp,), daemon=True).start()
        self.events.emit("stun_ready", bind=f"{self.bind_ip}:{self.port}")

    @classmethod
    def _build_binding_response(cls, req: bytes, addr: tuple[str, int]) -> bytes | None:
        if len(req) < 20:
            return None
        msg_type, _msg_len, magic = struct.unpack("!HHI", req[:8])
        if msg_type != 0x0001 or magic != cls.MAGIC:
            return None
        txn_id = req[8:20]
        ip_bytes = socket.inet_aton(addr[0])
        xport = addr[1] ^ (cls.MAGIC >> 16)
        xip = struct.unpack("!I", ip_bytes)[0] ^ cls.MAGIC
        attr = struct.pack("!HHBBHI", 0x0020, 8, 0, 1, xport, xip)
        return struct.pack("!HHI", 0x0101, len(attr), cls.MAGIC) + txn_id + attr

    def _udp_loop(self, sock: socket.socket) -> None:
        while True:
            pkt, addr = sock.recvfrom(4096)
            resp = self._build_binding_response(pkt, addr)
            self.events.emit(
                "stun_packet",
                transport="udp",
                src_ip=addr[0],
                src_port=addr[1],
                valid_binding=resp is not None,
                size=len(pkt),
            )
            if resp:
                sock.sendto(resp, addr)

    def _tcp_loop(self, srv: socket.socket) -> None:
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=self._tcp_client, args=(conn, addr), daemon=True).start()

    def _tcp_client(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        try:
            data = conn.recv(4096)
            resp = self._build_binding_response(data, addr)
            self.events.emit(
                "stun_packet",
                transport="tcp",
                src_ip=addr[0],
                src_port=addr[1],
                valid_binding=resp is not None,
                size=len(data),
            )
            if resp:
                conn.sendall(resp)
        except OSError:
            pass
        finally:
            conn.close()


class ControlledDNSServer:
    """Minimal authoritative DNS responder logging every query."""

    def __init__(self, bind_ip: str, port: int, answer_ip: str, events: EventLog) -> None:
        self.bind_ip = bind_ip
        self.port = port
        self.answer_ip = answer_ip
        self.events = events

    def start(self) -> None:
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind((self.bind_ip, self.port))
        threading.Thread(target=self._udp_loop, args=(udp,), daemon=True).start()
        self.events.emit("dns_ready", bind=f"{self.bind_ip}:{self.port}")

    @staticmethod
    def _parse_qname(pkt: bytes, offset: int) -> tuple[str, int]:
        labels = []
        while offset < len(pkt):
            ln = pkt[offset]
            offset += 1
            if ln == 0:
                break
            labels.append(pkt[offset : offset + ln].decode("ascii", errors="replace"))
            offset += ln
        return ".".join(labels), offset

    def _udp_loop(self, sock: socket.socket) -> None:
        while True:
            pkt, addr = sock.recvfrom(4096)
            if len(pkt) < 12:
                continue
            tid, flags, qdcount = struct.unpack("!HHH", pkt[:6])
            qname, off = self._parse_qname(pkt, 12)
            qtype, qclass = struct.unpack("!HH", pkt[off : off + 4]) if off + 4 <= len(pkt) else (0, 0)
            self.events.emit(
                "dns_query",
                src_ip=addr[0],
                qname=qname,
                qtype=qtype,
                qclass=qclass,
            )
            if qdcount < 1:
                continue
            question = pkt[12 : off + 4]
            if qtype == 1:  # A
                ans = (
                    b"\xc0\x0c"
                    + struct.pack("!HHIH", 1, 1, 60, 4)
                    + socket.inet_aton(self.answer_ip)
                )
                resp = struct.pack("!HHHHHH", tid, 0x8180, 1, 1, 0, 0) + question + ans
            else:
                resp = struct.pack("!HHHHHH", tid, 0x8180, 1, 0, 0, 0) + question
            sock.sendto(resp, addr)


def start_udp_quic_probe_listener(bind_ip: str, port: int, events: EventLog) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((bind_ip, port))

    def _loop() -> None:
        while True:
            pkt, addr = sock.recvfrom(65535)
            events.emit(
                "udp_8443_packet",
                src_ip=addr[0],
                src_port=addr[1],
                size=len(pkt),
                head_hex=pkt[:8].hex(),
            )

    threading.Thread(target=_loop, daemon=True).start()
    events.emit("udp_quic_probe_ready", bind=f"{bind_ip}:{port}")


def start_http_targets(
    bind_ip: str,
    http_port: int,
    https_port: int,
    cert_path: Path,
    key_path: Path,
    events: EventLog,
    echo_ip_override: str,
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            host_hdr = self.headers.get("Host", "")
            client_ip = self.client_address[0]
            events.emit(
                "target_http_hit",
                scheme="https" if isinstance(self.connection, ssl.SSLSocket) else "http",
                client_ip=client_ip,
                host=host_hdr,
                path=self.path,
            )
            if host_hdr.split(":")[0] in ("api.ipify.org", "checkip.amazonaws.com", "ifconfig.me"):
                body = echo_ip_override.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path.startswith("/webrtc"):
                html = _WEBRTC_PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return

            payload = json.dumps(
                {
                    "marker": "S022_TARGET_OK",
                    "client_ip": client_ip,
                    "host": host_hdr,
                    "path": self.path,
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Alt-Svc", f'h3=":{https_port}"; ma=86400')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    http_srv = ThreadingHTTPServer((bind_ip, http_port), Handler)
    threading.Thread(target=http_srv.serve_forever, daemon=True).start()

    https_srv = ThreadingHTTPServer((bind_ip, https_port), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    https_srv.socket = ctx.wrap_socket(https_srv.socket, server_side=True)
    threading.Thread(target=https_srv.serve_forever, daemon=True).start()
    events.emit("targets_ready", http=f"{bind_ip}:{http_port}", https=f"{bind_ip}:{https_port}")


_WEBRTC_PAGE = """<!doctype html>
<html>
<head><meta charset="utf-8"><title>s022-webrtc</title></head>
<body>
<script>
window.runWebRTCProbe = async function(iceServers) {
  const pc = new RTCPeerConnection({ iceServers });
  const candidates = [];
  pc.createDataChannel("s022");
  const done = new Promise((resolve) => {
    const timer = setTimeout(() => resolve({ timedOut: true, candidates }), 4000);
    pc.onicecandidate = (ev) => {
      if (ev.candidate) {
        candidates.push({
          candidate: ev.candidate.candidate,
          type: ev.candidate.type,
          protocol: ev.candidate.protocol,
          address: ev.candidate.address,
          port: ev.candidate.port
        });
      } else {
        clearTimeout(timer);
        resolve({ timedOut: false, candidates });
      }
    };
  });
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  const res = await done;
  pc.close();
  return res;
};
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind-ip", required=True)
    parser.add_argument("--role", choices=("all", "target", "proxy"), default="all")
    parser.add_argument("--target-ip", default="")
    parser.add_argument("--extra-ip", action="append", default=[])
    parser.add_argument("--reuse-certs", action="store_true")
    parser.add_argument("--log-file", required=True)
    parser.add_argument("--cert-dir", required=True)
    parser.add_argument("--auth-user", default="probeuser")
    parser.add_argument("--auth-pass", default="p@ss:w=rd%1!/#?")
    parser.add_argument("--echo-ip", default="8.8.8.8")
    parser.add_argument("--dns-port", type=int, default=5353)
    args = parser.parse_args()

    target_ip = args.target_ip or args.bind_ip
    events = EventLog(Path(args.log_file))
    cert_dir = Path(args.cert_dir)
    if args.reuse_certs:
        ca_path = cert_dir / "ca.crt"
        cert_path = cert_dir / "server.crt"
        key_path = cert_dir / "server.key"
        deadline = time.time() + 15.0
        while time.time() < deadline and not (cert_path.is_file() and key_path.is_file()):
            time.sleep(0.1)
    else:
        ca_path, cert_path, key_path = generate_spike_certs(
            cert_dir,
            args.bind_ip,
            extra_ips=([target_ip] if target_ip != args.bind_ip else []) + list(args.extra_ip),
            extra_dns=["dns-test.s022.invalid", "stun-host.s022.invalid"],
        )
    host_overrides = {
        "api.ipify.org": target_ip,
        "checkip.amazonaws.com": target_ip,
        "ifconfig.me": target_ip,
        "dns-test.s022.invalid": target_ip,
        "stun-host.s022.invalid": target_ip,
    }

    if args.role in ("all", "target"):
        start_http_targets(
            args.bind_ip, 8080, 8443, cert_path, key_path, events, args.echo_ip
        )
        start_udp_quic_probe_listener(args.bind_ip, 8443, events)
        ControlledSTUNServer(args.bind_ip, 3478, events).start()
        ControlledDNSServer(args.bind_ip, args.dns_port, args.bind_ip, events).start()

    if args.role in ("all", "proxy"):
        # HTTP proxies: no-auth (18080), auth (18081)
        ControlledHTTPProxy(
            "http_noauth", args.bind_ip, 18080, events,
            host_overrides=host_overrides, echo_ip_override=args.echo_ip,
        ).start()
        ControlledHTTPProxy(
            "http_auth", args.bind_ip, 18081, events,
            auth_user=args.auth_user, auth_pass=args.auth_pass,
            host_overrides=host_overrides, echo_ip_override=args.echo_ip,
        ).start()

        # HTTPS (TLS-to-proxy) proxies: no-auth (18443), auth (18444)
        proxy_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        proxy_tls.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
        ControlledHTTPProxy(
            "https_noauth", args.bind_ip, 18443, events,
            tls_context=proxy_tls, host_overrides=host_overrides, echo_ip_override=args.echo_ip,
        ).start()
        ControlledHTTPProxy(
            "https_auth", args.bind_ip, 18444, events,
            auth_user=args.auth_user, auth_pass=args.auth_pass,
            tls_context=proxy_tls, host_overrides=host_overrides, echo_ip_override=args.echo_ip,
        ).start()

        # SOCKS5 proxies:
        # 11080: noauth + UDP relay
        # 11081: auth + UDP relay
        # 11082: noauth + UDP reject (0x07)
        # 11083: noauth + UDP drop
        ControlledSOCKS5Proxy(
            "socks5_noauth_udp", args.bind_ip, 11080, events,
            udp_mode="relay", host_overrides=host_overrides,
        ).start()
        ControlledSOCKS5Proxy(
            "socks5_auth_udp", args.bind_ip, 11081, events,
            auth_user=args.auth_user, auth_pass=args.auth_pass,
            udp_mode="relay", host_overrides=host_overrides,
        ).start()
        ControlledSOCKS5Proxy(
            "socks5_noauth_udpreject", args.bind_ip, 11082, events,
            udp_mode="reject", host_overrides=host_overrides,
        ).start()
        ControlledSOCKS5Proxy(
            "socks5_noauth_udpdrop", args.bind_ip, 11083, events,
            udp_mode="drop", host_overrides=host_overrides,
        ).start()

    events.emit("all_services_ready", role=args.role, bind_ip=args.bind_ip, ca_cert=str(ca_path))
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
