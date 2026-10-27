import asyncio
import json
from pathlib import Path


def status():
    return json.loads(Path('/run/test/status.json').read_text())


async def command(reader, writer, method, params, command_id, session=None):
    packet = {'id': command_id, 'method': method, 'params': params}
    if session:
        packet['sessionId'] = session
    writer.write((json.dumps(packet) + '\n').encode())
    await writer.drain()
    while True:
        line = await asyncio.wait_for(reader.readline(), timeout=5)
        if not line:
            raise EOFError('Agent closed UDS before command response')
        message = json.loads(line)
        if message.get('id') == command_id:
            if 'error' in message or 'exceptionDetails' in message.get('result', {}):
                raise RuntimeError(f'CDP command {method} failed')
            return message.get('result', {})


async def completed_download(previous_guids):
    for _ in range(100):
        events = status()['download_events']
        for event in events:
            params = event.get('params', {})
            if event.get('method') == 'Browser.downloadProgress' and params.get('state') == 'completed':
                guid = params['guid']
                if guid not in previous_guids:
                    return guid
        await asyncio.sleep(0.1)
    raise TimeoutError('Actual download completion event missing')


async def main():
    reader, writer = await asyncio.open_unix_connection('/run/test/agent.sock')
    try:
        targets = await command(reader, writer, 'Target.getTargets', {}, 1)
        page, = [target for target in targets['targetInfos'] if target['type'] == 'page']
        attachment = await command(reader, writer, 'Target.attachToTarget',
                                   {'targetId': page['targetId'], 'flatten': True}, 2)
        session = attachment['sessionId']
        await command(reader, writer, 'Runtime.evaluate',
                      {'expression': "document.getElementById('dl1').click()"}, 3, session)
        first = await completed_download(set())
        assert Path('/exchange/default', first).read_bytes() == b'REAL_CDP_DOWNLOAD_VERIFICATION_CONTENT_FIRST_11111'

        external_reader, external_writer = await asyncio.open_unix_connection('/run/test/agent.sock')
        try:
            await command(external_reader, external_writer, 'Browser.setDownloadBehavior',
                          {'behavior': 'allow', 'downloadPath': '/exchange/external', 'eventsEnabled': False}, 4)
        finally:
            external_writer.close()
            await external_writer.wait_closed()
        for _ in range(50):
            if status()['rearm_count'] >= 2:
                break
            await asyncio.sleep(0.1)
        else:
            raise TimeoutError('Automatic agent rearm missing after external UDS disconnect')

        await command(reader, writer, 'Runtime.evaluate',
                      {'expression': "document.getElementById('dl2').click()"}, 5, session)
        second = await completed_download({first})
        assert Path('/exchange/default', second).read_bytes() == b'REAL_CDP_DOWNLOAD_VERIFICATION_CONTENT_SECOND_22222'
        assert not list(Path('/exchange/external').iterdir())
        assert len(list(Path('/exchange/default').iterdir())) == 2
        print(json.dumps({'cross_container_uds': True, 'first_bytes': 50, 'second_bytes': 51,
                          'external_directory_empty': True, 'auto_rearmed': True}), flush=True)
        await command(reader, writer, 'Browser.close', {}, 6)
    finally:
        writer.close()
        await writer.wait_closed()


if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(main(), timeout=40))
