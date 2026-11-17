#!/usr/bin/env python3
"""
Test TURN REST HMAC-SHA1 short-term credentials with official Selkies ICE stack against real Coturn.
Scenarios:
1. Valid credentials -> Allocation successful, relayed candidate obtained.
2. Bad password/secret -> Allocation rejected (Unauthorized 401).
3. Expired credentials (timestamp in past) -> Allocation rejected (Unauthorized 401).
4. Direct UDP relay-to-relay communication between two clients via Coturn allocations with mutual channel binding.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path

# Setup paths
PROBE_DIR = Path("/probe") if Path("/probe").exists() else Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROBE_DIR / "selkies_src" / "src"))

import selkies.ice.stun as stun
import selkies.ice.turn as turn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("turn_auth_probe")

def generate_turn_credentials(secret: str, ttl_seconds: int, username_prefix: str = "user"):
    now = int(time.time())
    expiry = now + ttl_seconds
    username = f"{expiry}:{username_prefix}"
    mac = hmac.new(secret.encode("utf-8"), username.encode("utf-8"), hashlib.sha1).digest()
    password = base64.b64encode(mac).decode("utf-8")
    return username, password, expiry

async def test_single_allocation(turn_server: tuple[str, int], username: str, password: str, test_name: str):
    logger.info(f"--- Running {test_name} ---")
    try:
        turn_transport, protocol = await turn.create_turn_endpoint(
            lambda: asyncio.DatagramProtocol(),
            server_addr=turn_server,
            username=username,
            password=password,
            lifetime=60,
        )
        relayed_addr = turn_transport.get_extra_info("sockname")
        turn_transport.close()
        logger.info(f"{test_name}: SUCCESS - Allocated {relayed_addr}")
        return {"status": "SUCCESS", "relayed_addr": relayed_addr, "error": None}
    except Exception as e:
        err_msg = str(e)
        logger.info(f"{test_name}: FAILED - {type(e).__name__}: {err_msg}")
        return {"status": "FAILED", "relayed_addr": None, "error": f"{type(e).__name__}: {err_msg}"}

async def test_relay_to_relay_udp(turn_server: tuple[str, int], secret: str):
    logger.info("--- Running relay-to-relay UDP transport test ---")
    u1, p1, _ = generate_turn_credentials(secret, ttl_seconds=300, username_prefix="client_a")
    u2, p2, _ = generate_turn_credentials(secret, ttl_seconds=300, username_prefix="client_b")

    received_queue_b = asyncio.Queue()
    received_queue_a = asyncio.Queue()

    class RecvProtocolB(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            logger.info(f"Client B received {len(data)} bytes from {addr}")
            received_queue_b.put_nowait((data, addr))

    class RecvProtocolA(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            logger.info(f"Client A received {len(data)} bytes from {addr}")
            received_queue_a.put_nowait((data, addr))

    # Client A allocation
    t_a, p_a = await turn.create_turn_endpoint(
        RecvProtocolA,
        server_addr=turn_server,
        username=u1,
        password=p1,
        lifetime=60,
    )
    addr_a = t_a.get_extra_info("sockname")
    
    # Client B allocation
    t_b, p_b = await turn.create_turn_endpoint(
        RecvProtocolB,
        server_addr=turn_server,
        username=u2,
        password=p2,
        lifetime=60,
    )
    addr_b = t_b.get_extra_info("sockname")

    logger.info(f"Client A relay: {addr_a}, Client B relay: {addr_b}")

    # Explicit mutual channel bind on inner protocols
    now = time.time()
    inner_a = t_a._TurnTransport__inner_protocol
    inner_b = t_b._TurnTransport__inner_protocol

    chan_a = 0x4000
    await inner_a.channel_bind(chan_a, addr_b)
    inner_a.channel_refresh_at[chan_a] = now + 600
    inner_a.channel_to_peer[chan_a] = addr_b
    inner_a.peer_to_channel[addr_b] = chan_a

    chan_b = 0x4001
    await inner_b.channel_bind(chan_b, addr_a)
    inner_b.channel_refresh_at[chan_b] = now + 600
    inner_b.channel_to_peer[chan_b] = addr_a
    inner_b.peer_to_channel[addr_a] = chan_b

    try:
        # A sends to B's relay address
        test_payload_a2b = b"PING-RELAY-A-TO-B-" + secrets.token_bytes(16)
        t_a.sendto(test_payload_a2b, addr_b)

        data_b, from_addr_b = await asyncio.wait_for(received_queue_b.get(), timeout=5.0)
        match_b = (data_b == test_payload_a2b)
        logger.info(f"A -> B payload match: {match_b} (from {from_addr_b})")

        # B replies to A's relay address
        test_payload_b2a = b"PONG-RELAY-B-TO-A-" + secrets.token_bytes(16)
        t_b.sendto(test_payload_b2a, addr_a)

        data_a, from_addr_a = await asyncio.wait_for(received_queue_a.get(), timeout=5.0)
        match_a = (data_a == test_payload_b2a)
        logger.info(f"B -> A payload match: {match_a} (from {from_addr_a})")

        all_ok = match_b and match_a
        return {
            "status": "PASS" if all_ok else "FAIL",
            "client_a_relay": addr_a,
            "client_b_relay": addr_b,
            "a_to_b_matched": match_b,
            "b_to_a_matched": match_a,
        }
    finally:
        t_a.close()
        t_b.close()

async def main():
    if len(sys.argv) < 3:
        print("Usage: turn_auth_probe.py TURN_HOST:PORT SHARED_SECRET_FILE")
        sys.exit(1)

    host_port = sys.argv[1].split(":")
    turn_server = (host_port[0], int(host_port[1]))
    secret = Path(sys.argv[2]).read_text().strip()

    results = {}

    # 1. Valid credentials
    u_valid, p_valid, exp_valid = generate_turn_credentials(secret, ttl_seconds=300, username_prefix="valid_user")
    res_valid = await test_single_allocation(turn_server, u_valid, p_valid, "Test 1: Valid Credentials")
    results["valid_credentials"] = res_valid

    # 2. Bad password
    u_bad, _, _ = generate_turn_credentials(secret, ttl_seconds=300, username_prefix="bad_pw_user")
    p_bad = base64.b64encode(b"wrong_secret_bytes_12345").decode("utf-8")
    res_bad = await test_single_allocation(turn_server, u_bad, p_bad, "Test 2: Bad Password")
    results["bad_password"] = res_bad

    # 3. Expired credentials (expired 100 seconds ago)
    u_exp, p_exp, _ = generate_turn_credentials(secret, ttl_seconds=-100, username_prefix="expired_user")
    res_exp = await test_single_allocation(turn_server, u_exp, p_exp, "Test 3: Expired Credentials")
    results["expired_credentials"] = res_exp

    # 4. Relay-to-relay UDP transport
    res_relay = await test_relay_to_relay_udp(turn_server, secret)
    results["relay_to_relay_udp"] = res_relay

    # Summary
    all_pass = (
        results["valid_credentials"]["status"] == "SUCCESS"
        and results["bad_password"]["status"] == "FAILED"
        and results["expired_credentials"]["status"] == "FAILED"
        and results["relay_to_relay_udp"]["status"] == "PASS"
    )
    auth_denied = all("(401" in (results[key].get("error") or "") for key in ("bad_password", "expired_credentials"))
    results["negative_cases_explicit_401"] = auth_denied
    all_pass = all_pass and auth_denied
    results["all_pass"] = all_pass

    print("\n=== TURN POSITIVE/NEGATIVE SUITE RESULT ===")
    print(json.dumps(results, indent=2))

    out_file = PROBE_DIR / "probe_work" / "turn_auth_results.json"
    out_file.write_text(json.dumps(results, indent=2))

    sys.exit(0 if all_pass else 1)

if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), timeout=30))
