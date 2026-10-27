"""
Standalone StreamAgent Process.
Exposes:
- Active WebSocket connection to Gateway (/agent/register)
- Per-viewer upstream WebSocket tunnel to Selkies (/api/webrtc/signaling)
- Auto-reconnect with backoff on Gateway disconnect/SIGKILL
- Detailed trajectory audit log (conn_id, direction, msg_type, payload size, sha256 hash)
"""
import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from aiohttp import ClientSession, WSMsgType, WSCloseCode

from gateway_core import StreamAgent, MAX_FRAME_SIZE, IO_TIMEOUT, HEARTBEAT_INTERVAL, QUEUE_MAX_SIZE, _sanitize_packet, _check_payload_limit

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [agent_proc]: %(message)s")
logger = logging.getLogger("agent_proc")

def parse_args():
    parser = argparse.ArgumentParser(description="Standalone StreamAgent Process")
    parser.add_argument("--gateway-url", default="http://127.0.0.1:18082/agent/register", help="Gateway register URL")
    parser.add_argument("--profile-id", required=True, help="Profile ID")
    parser.add_argument("--token-file", required=True, help="Path to token file")
    parser.add_argument("--upstream-url", default="http://127.0.0.1:18083/api/webrtc/signaling", help="Selkies signaling URL")
    parser.add_argument("--audit-log", default="agent_audit.jsonl", help="Trajectory audit log path")
    return parser.parse_args()

class AuditedStreamAgent(StreamAgent):
    def __init__(self, gateway_url: str, profile_id: str, agent_token: str, upstream_url: str, audit_log: str):
        super().__init__(gateway_url, profile_id, agent_token, upstream_url)
        self.audit_log = audit_log

    def _record_audit(self, conn_id: str, direction: str, msg_type: str, raw_data: str = None, extra: dict = None):
        entry = {
            "timestamp": time.time(),
            "conn_id": conn_id,
            "direction": direction,
            "msg_type": msg_type,
        }
        if raw_data is not None:
            entry["size_bytes"] = len(raw_data.encode("utf-8"))
            entry["sha256"] = hashlib.sha256(raw_data.encode("utf-8")).hexdigest()[:16]
            # Identify message structure without dumping sensitive/huge content
            if raw_data.startswith("HELLO"):
                entry["category"] = "HELLO"
            elif raw_data.startswith("SESSION"):
                entry["category"] = raw_data.split(" ")[0]
            elif '"sdp"' in raw_data:
                entry["category"] = "SDP"
            elif '"ice"' in raw_data:
                entry["category"] = "ICE"
            else:
                entry["category"] = "OTHER"
        if extra:
            entry.update(extra)
        
        try:
            with open(self.audit_log, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error("Failed to write audit log: %s", e)

    async def _viewer_upstream_worker(self, session: ClientSession, gw_ws, conn_id: str, queue: asyncio.Queue):
        upstream_ws = None
        upstream_reader_task = None
        try:
            logger.info("Worker starting upstream connection for %s -> %s", conn_id, self.upstream_url)
            self._record_audit(conn_id, "agent->upstream", "upstream_connect_init")
            upstream_ws = await session.ws_connect(self.upstream_url, max_msg_size=MAX_FRAME_SIZE, timeout=IO_TIMEOUT, heartbeat=HEARTBEAT_INTERVAL)
            self._record_audit(conn_id, "upstream->agent", "upstream_connect_success")
            upstream_reader_task = asyncio.create_task(self._upstream_reader(gw_ws, conn_id, upstream_ws))

            while True:
                packet = await queue.get()
                pkt_type = packet.get("type")
                if pkt_type == "msg":
                    data = packet.get("data", "")
                    self._record_audit(conn_id, "gw->agent->upstream", "tunnel_msg_outbound", raw_data=data)
                    if not _check_payload_limit(data):
                        logger.warning("Viewer %s outbound payload exceeded limit, closing", conn_id)
                        if not upstream_ws.closed:
                            await asyncio.wait_for(upstream_ws.close(code=WSCloseCode.MESSAGE_TOO_BIG, message=b"Payload too large"), timeout=IO_TIMEOUT)
                        if not gw_ws.closed:
                            await asyncio.wait_for(gw_ws.send_json(_sanitize_packet({
                                "type": "close",
                                "conn_id": conn_id,
                                "code": 1009,
                                "reason": "Payload too large"
                            })), timeout=IO_TIMEOUT)
                        break
                    if not upstream_ws.closed:
                        await asyncio.wait_for(upstream_ws.send_str(data), timeout=IO_TIMEOUT)
                elif pkt_type == "close":
                    self._record_audit(conn_id, "gw->agent->upstream", "tunnel_close_outbound")
                    break
        except Exception as e:
            logger.warning("Upstream worker error for %s: %s", conn_id, e)
            self._record_audit(conn_id, "agent", "upstream_worker_error", extra={"error": str(e)})
            if not gw_ws.closed:
                try:
                    await asyncio.wait_for(gw_ws.send_json(_sanitize_packet({"type": "close", "conn_id": conn_id, "code": 1011, "reason": "Upstream failure"})), timeout=IO_TIMEOUT)
                except Exception:
                    pass
        finally:
            if upstream_reader_task:
                upstream_reader_task.cancel()
            if upstream_ws and not upstream_ws.closed:
                try:
                    await upstream_ws.close()
                except Exception:
                    pass
            self.viewer_queues.pop(conn_id, None)
            self.viewer_tasks.pop(conn_id, None)
            logger.info("Worker finished for %s", conn_id)
            self._record_audit(conn_id, "agent", "upstream_worker_finished")

    async def _upstream_reader(self, gw_ws, conn_id: str, upstream_ws):
        try:
            async for msg in upstream_ws:
                if msg.type == WSMsgType.TEXT:
                    self._record_audit(conn_id, "upstream->agent->gw", "tunnel_msg_inbound", raw_data=msg.data)
                    if not _check_payload_limit(msg.data):
                        logger.warning("Upstream sent oversized payload for %s, closing", conn_id)
                        if not upstream_ws.closed:
                            await asyncio.wait_for(upstream_ws.close(code=WSCloseCode.MESSAGE_TOO_BIG, message=b"Payload too large"), timeout=IO_TIMEOUT)
                        if not gw_ws.closed:
                            await asyncio.wait_for(gw_ws.send_json(_sanitize_packet({
                                "type": "close",
                                "conn_id": conn_id,
                                "code": 1009,
                                "reason": "Payload too large"
                            })), timeout=IO_TIMEOUT)
                        break

                    if not gw_ws.closed:
                        await asyncio.wait_for(gw_ws.send_json(_sanitize_packet({
                            "type": "msg",
                            "conn_id": conn_id,
                            "data": msg.data
                        })), timeout=IO_TIMEOUT)
                elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        except Exception as e:
            logger.warning("Upstream reader error for %s: %s", conn_id, e)
            self._record_audit(conn_id, "agent", "upstream_reader_error", extra={"error": str(e)})
        finally:
            if not gw_ws.closed:
                try:
                    await asyncio.wait_for(gw_ws.send_json(_sanitize_packet({
                        "type": "close",
                        "conn_id": conn_id,
                        "code": 1000,
                        "reason": "Upstream closed"
                    })), timeout=IO_TIMEOUT)
                except Exception:
                    pass

async def main():
    args = parse_args()
    with open(args.token_file, "r") as f:
        token = f.read().strip()

    agent = AuditedStreamAgent(
        gateway_url=args.gateway_url,
        profile_id=args.profile_id,
        agent_token=token,
        upstream_url=args.upstream_url,
        audit_log=args.audit_log
    )
    logger.info("StreamAgent running for profile %s, pointing upstream to %s", args.profile_id, args.upstream_url)
    try:
        await agent.run()
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Agent shutting down...")
        agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
