import asyncio
import glob
import json
import os
from pathlib import Path
import socketserver
import subprocess
import threading
import urllib.request

from container_cdp_probe import DownloadHttpHandler, RealCdpAgentUdsProxy


def write_status(data):
    target = Path('/run/test/status.json')
    temporary = target.with_suffix('.tmp')
    with temporary.open('w') as handle:
        json.dump(data, handle)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(target)


async def main():
    for name in ('default', 'external'):
        Path('/exchange', name).mkdir(parents=True, exist_ok=True)
    httpd = socketserver.TCPServer(('127.0.0.1', 0), DownloadHttpHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    profile = Path('/tmp/cdp_profile')
    profile.mkdir()
    binary, = glob.glob('/root/.cloakbrowser/chromium-*/chrome')
    chrome = subprocess.Popen([
        binary, '--headless=new', '--no-sandbox', '--disable-gpu',
        '--no-first-run', '--no-default-browser-check',
        '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
        f'--user-data-dir={profile}', f'http://127.0.0.1:{httpd.server_address[1]}/',
    ])
    proxy = None
    try:
        for _ in range(100):
            if chrome.poll() is not None:
                raise RuntimeError('CloakBrowser exited before CDP was ready')
            active_port = profile / 'DevToolsActivePort'
            if active_port.exists():
                break
            await asyncio.sleep(0.1)
        port = int(active_port.read_text().splitlines()[0])
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=2) as response:
            browser = json.load(response)
        proxy = RealCdpAgentUdsProxy(browser['webSocketDebuggerUrl'], '/run/test/agent.sock', '/exchange/default')
        await proxy.start()
        while chrome.poll() is None:
            write_status({'ready': True, 'browser_pid': chrome.pid, 'rearm_count': proxy.rearm_count,
                          'download_events': proxy.download_events, 'cdp_port': port})
            await asyncio.sleep(0.05)
        write_status({'ready': False, 'browser_exit_code': chrome.returncode,
                      'rearm_count': proxy.rearm_count, 'download_events': proxy.download_events})
        if chrome.returncode != 0:
            raise RuntimeError(f'CloakBrowser exited with {chrome.returncode}')
    finally:
        if proxy:
            await proxy.close()
        if chrome.poll() is None:
            chrome.terminate()
            try:
                chrome.wait(timeout=3)
            except subprocess.TimeoutExpired:
                chrome.kill()
                chrome.wait(timeout=3)
        httpd.shutdown()


if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(main(), timeout=75))
