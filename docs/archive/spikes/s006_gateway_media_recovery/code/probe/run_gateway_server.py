"""
Standalone Gateway Process.
Exposes:
- POST /agent/register (WebSocket)
- GET /stream/{profile_id}/signal (WebSocket)
- GET /* (HTTP static reverse-proxy to Selkies, with WebSocket rewrite injection for WebRTC signaling)
"""
import argparse
import asyncio
import logging
import os
import secrets
import sys
import aiohttp
from aiohttp import web, WSMsgType

from gateway_core import StreamGateway

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [gateway_proc]: %(message)s")
logger = logging.getLogger("gateway_proc")

def parse_args():
    parser = argparse.ArgumentParser(description="Standalone StreamGateway Process")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=18082, help="Bind port")
    parser.add_argument("--token-file", required=True, help="Path to file containing shared secret bearer token")
    parser.add_argument("--selkies-origin", default="http://127.0.0.1:18083", help="Upstream Selkies HTTP origin for static assets")
    return parser.parse_args()

async def main():
    args = parse_args()
    
    with open(args.token_file, "r") as f:
        agent_token = f.read().strip()

    gateway = StreamGateway(agent_token=agent_token)

    async def static_proxy(request: web.Request):
        url = f"{args.selkies_origin}{request.path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=request.query) as resp:
                    body = await resp.read()
                    headers = dict(resp.headers)
                    for h in ["Transfer-Encoding", "Content-Encoding", "Keep-Alive", "Proxy-Connection", "Content-Security-Policy"]:
                        headers.pop(h, None)
                    content_type = headers.get("Content-Type", "")
                    if "text/html" in content_type:
                        html = body.decode("utf-8")
                        inject = """<script>
                        (function() {
                            const origWS = window.WebSocket;
                            window.WebSocket = function(url, protocols) {
                                const u = new URL(url, window.location.href);
                                if (u.pathname.includes("/api/webrtc/signaling")) {
                                    u.pathname = "/stream/test-profile/signal";
                                }
                                console.log("[HOOK] Intercepted WebSocket:", url, "->", u.toString());
                                const ws = new origWS(u.toString(), protocols);
                                window.__last_ws = ws;
                                return ws;
                            };
                            window.WebSocket.prototype = origWS.prototype;
                            Object.assign(window.WebSocket, origWS);

                            const origPC = window.RTCPeerConnection;
                            window.RTCPeerConnection = function(...args) {
                                const pc = new origPC(...args);
                                window.pc = pc;
                                return pc;
                            };
                            window.RTCPeerConnection.prototype = origPC.prototype;
                            Object.assign(window.RTCPeerConnection, origPC);
                        })();
                        </script>"""
                        if "<head>" in html:
                            html = html.replace("<head>", f"<head>{inject}", 1)
                        else:
                            html = inject + html
                        body = html.encode("utf-8")
                        headers["Content-Length"] = str(len(body))
                    return web.Response(body=body, status=resp.status, headers=headers)
        except Exception as e:
            return web.Response(status=502, text=f"Bad Gateway: {e}")

    app = web.Application()
    app.router.add_get("/agent/register", gateway.handle_agent_register)
    app.router.add_get("/stream/{profile_id}/signal", gateway.handle_viewer_signal)
    app.router.add_get("/", static_proxy)
    app.router.add_get("/{path:.*}", static_proxy)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.host, args.port)
    await site.start()
    logger.info("StreamGateway listening on http://%s:%d", args.host, args.port)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Gateway shutting down...")
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
