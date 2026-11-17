#!/usr/bin/env python3
"""In-netns AF_PACKET sniffer and iptables rule/counter inspector for s022."""

from __future__ import annotations

import argparse
import json
import socket
import struct
import subprocess
import time
from pathlib import Path
from typing import Any


def _parse_dns_qname(payload: bytes) -> str | None:
    if len(payload) < 13:
        return None
    offset = 12
    labels: list[str] = []
    while offset < len(payload):
        ln = payload[offset]
        offset += 1
        if ln == 0:
            break
        if ln >= 64 or offset + ln > len(payload):
            return None
        labels.append(payload[offset : offset + ln].decode("ascii", errors="replace"))
        offset += ln
    return ".".join(labels) if labels else None


def _decode_packet(frame: bytes) -> dict[str, Any] | None:
    if len(frame) < 14:
        return None
    eth_proto = struct.unpack("!H", frame[12:14])[0]
    if eth_proto == 0x0800 and len(frame) >= 34:  # IPv4
        ihl = (frame[14] & 0x0F) * 4
        if len(frame) < 14 + ihl:
            return None
        proto = frame[14 + 9]
        src_ip = socket.inet_ntoa(frame[14 + 12 : 14 + 16])
        dst_ip = socket.inet_ntoa(frame[14 + 16 : 14 + 20])
        l4 = frame[14 + ihl :]
        rec: dict[str, Any] = {
            "family": 4,
            "proto": proto,
            "src_ip": src_ip,
            "dst_ip": dst_ip,
        }
        if proto == 6 and len(l4) >= 4:  # TCP
            src_port, dst_port = struct.unpack("!HH", l4[:4])
            flags = l4[13] if len(l4) >= 14 else 0
            rec.update({"l4": "tcp", "src_port": src_port, "dst_port": dst_port, "syn": bool(flags & 0x02)})
            return rec
        if proto == 17 and len(l4) >= 8:  # UDP
            src_port, dst_port, _ulen = struct.unpack("!HHH", l4[:6])
            payload = l4[8:]
            rec.update({"l4": "udp", "src_port": src_port, "dst_port": dst_port, "payload_len": len(payload)})
            if dst_port == 53:
                rec["dns_qname"] = _parse_dns_qname(payload)
            if len(payload) >= 8 and struct.unpack("!I", payload[4:8])[0] == 0x2112A442:
                rec["is_stun"] = True
            return rec
        return rec
    if eth_proto == 0x86DD and len(frame) >= 54:  # IPv6
        proto = frame[14 + 6]
        src_ip = socket.inet_ntop(socket.AF_INET6, frame[14 + 8 : 14 + 24])
        dst_ip = socket.inet_ntop(socket.AF_INET6, frame[14 + 24 : 14 + 40])
        l4 = frame[54:]
        rec = {
            "family": 6,
            "proto": proto,
            "src_ip": src_ip,
            "dst_ip": dst_ip,
        }
        if proto == 6 and len(l4) >= 4:
            src_port, dst_port = struct.unpack("!HH", l4[:4])
            rec.update({"l4": "tcp", "src_port": src_port, "dst_port": dst_port})
        elif proto == 17 and len(l4) >= 8:
            src_port, dst_port, _ = struct.unpack("!HHH", l4[:6])
            rec.update({"l4": "udp", "src_port": src_port, "dst_port": dst_port, "payload_len": len(l4[8:])})
        return rec
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    cap = sub.add_parser("capture")
    cap.add_argument("--out", required=True)
    cap.add_argument("--stop-file", required=True)

    cnt = sub.add_parser("counters")
    cnt.add_argument("--out", required=True)

    pol = sub.add_parser("install-strict")
    pol.add_argument("--allowed-tcp", action="append", default=[])  # ip:port
    pol.add_argument("--allowed-udp", action="append", default=[])  # ip:port
    pol.add_argument("--tail", choices=("DROP", "ACCEPT"), default="DROP")

    args = parser.parse_args()

    if args.cmd == "capture":
        out_path = Path(args.out)
        stop_path = Path(args.stop_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("", encoding="utf-8")
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
        sock.settimeout(0.2)
        with out_path.open("a", encoding="utf-8") as fh:
            while not stop_path.exists():
                try:
                    raw, sa = sock.recvfrom(65535)
                except TimeoutError:
                    continue
                ifname = sa[0] if len(sa) > 0 else ""
                pkttype = sa[2] if len(sa) > 2 else -1
                if pkttype != socket.PACKET_OUTGOING:
                    continue
                decoded = _decode_packet(raw)
                if decoded is not None:
                    decoded["ifname"] = ifname
                    decoded["ts"] = round(time.time(), 4)
                    fh.write(json.dumps(decoded) + "\n")
                    fh.flush()
        sock.close()
        return

    if args.cmd == "counters":
        v4 = subprocess.check_output(["iptables", "-L", "OUTPUT", "-v", "-n"], text=True)
        v6 = subprocess.check_output(["ip6tables", "-L", "OUTPUT", "-v", "-n"], text=True)
        Path(args.out).write_text(
            json.dumps({"ipv4_output": v4, "ipv6_output": v6}, indent=2),
            encoding="utf-8",
        )
        return

    if args.cmd == "install-strict":
        from cbrowser.supervisor.network_policy import (
            BLOCKED_IPV4_RANGES,
            BLOCKED_IPV6_RANGES,
        )
        v4_lines = [
            "*filter",
            ":INPUT DROP [0:0]",
            ":FORWARD DROP [0:0]",
            ":OUTPUT DROP [0:0]",
            "-A INPUT -i lo -j ACCEPT",
            "-A OUTPUT -o lo -j ACCEPT",
            "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
            "-A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
        ]
        v6_lines = [
            "*filter",
            ":INPUT DROP [0:0]",
            ":FORWARD DROP [0:0]",
            ":OUTPUT DROP [0:0]",
            "-A INPUT -i lo -j ACCEPT",
            "-A OUTPUT -o lo -j ACCEPT",
            *[
                f"-A {c} -p ipv6-icmp --icmpv6-type {k} -m hl --hl-eq 255 -j ACCEPT"
                for c in ("INPUT", "OUTPUT")
                for k in (133, 134, 135, 136)
            ],
            "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
            "-A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
        ]
        for item in args.allowed_tcp:
            ip_s, port_s = item.rsplit(":", 1)
            if ":" in ip_s:
                v6_lines.append(f"-A OUTPUT -p tcp -d {ip_s.strip('[]')} --dport {port_s} -j ACCEPT")
            else:
                v4_lines.append(f"-A OUTPUT -p tcp -d {ip_s} --dport {port_s} -j ACCEPT")
        for item in args.allowed_udp:
            ip_s, port_s = item.rsplit(":", 1)
            if ":" in ip_s:
                v6_lines.append(f"-A OUTPUT -p udp -d {ip_s.strip('[]')} --dport {port_s} -j ACCEPT")
            else:
                v4_lines.append(f"-A OUTPUT -p udp -d {ip_s} --dport {port_s} -j ACCEPT")
        for net in BLOCKED_IPV4_RANGES:
            v4_lines.append(f"-A OUTPUT -d {net} -j DROP")
        for net in BLOCKED_IPV6_RANGES:
            v6_lines.append(f"-A OUTPUT -d {net} -j DROP")
        v4_lines.append(f"-A OUTPUT -j {args.tail}")
        v6_lines.append(f"-A OUTPUT -j {args.tail}")
        v4_lines.append("COMMIT\n")
        v6_lines.append("COMMIT\n")
        subprocess.run(["iptables-restore"], input="\n".join(v4_lines), text=True, check=True)
        subprocess.run(["ip6tables-restore"], input="\n".join(v6_lines), text=True, check=True)


if __name__ == "__main__":
    main()
