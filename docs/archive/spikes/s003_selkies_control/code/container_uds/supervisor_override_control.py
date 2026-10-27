import asyncio
from pathlib import Path

from supervisor_client import command


async def main():
    reader, writer = await asyncio.open_unix_connection('/run/test/agent.sock')
    try:
        targets = await command(reader, writer, 'Target.getTargets', {}, 1)
        page, = [target for target in targets['targetInfos'] if target['type'] == 'page']
        attachment = await command(reader, writer, 'Target.attachToTarget',
                                   {'targetId': page['targetId'], 'flatten': True}, 2)
        await command(reader, writer, 'Browser.setDownloadBehavior',
                      {'behavior': 'allow', 'downloadPath': '/exchange/external', 'eventsEnabled': False}, 3)
        await command(reader, writer, 'Runtime.evaluate',
                      {'expression': "document.getElementById('dl1').click()"}, 4, attachment['sessionId'])
        destination = Path('/exchange/external/download-1.txt')
        for _ in range(100):
            if destination.exists():
                break
            await asyncio.sleep(0.1)
        assert destination.read_bytes() == b'REAL_CDP_DOWNLOAD_VERIFICATION_CONTENT_FIRST_11111'
        assert not list(Path('/exchange/default').iterdir())
        print('Control proved external CDP override actually redirects a real download while connected', flush=True)
        await command(reader, writer, 'Browser.close', {}, 5)
    finally:
        writer.close()
        await writer.wait_closed()


if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(main(), timeout=30))
