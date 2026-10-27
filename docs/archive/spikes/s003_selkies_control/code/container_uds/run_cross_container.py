import argparse
import json
from pathlib import Path
import subprocess
import time

PREFIX = 'cbrowser-spike-cdp-uds'
IMAGE = 'cbrowser-spike-runtime-browser:test'
HERE = Path(__file__).resolve().parent


def docker(*args, check=True, timeout=20):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=check, timeout=timeout)


def cleanup():
    docker('rm', '-f', '-v', f'{PREFIX}-browser', f'{PREFIX}-client', check=False)
    for suffix in ('runtime', 'artifacts'):
        docker('volume', 'rm', f'{PREFIX}-{suffix}', check=False)


def main(case='recovery'):
    cleanup()
    try:
        for suffix in ('runtime', 'artifacts'):
            docker('volume', 'create', f'{PREFIX}-{suffix}')
        docker('run', '-d', '--name', f'{PREFIX}-browser', '--network', 'none',
               '--mount', f'type=bind,src={HERE},dst=/probe,readonly',
               '-v', f'{PREFIX}-runtime:/run/test', '-v', f'{PREFIX}-artifacts:/exchange',
               '--entrypoint', 'python3', IMAGE, '/probe/browser_agent.py')
        for _ in range(60):
            ready = docker('exec', f'{PREFIX}-browser', 'test', '-S', '/run/test/agent.sock', check=False)
            if ready.returncode == 0:
                break
            time.sleep(0.2)
        else:
            raise TimeoutError('Browser Agent UDS was not created')
        inspected = json.loads(docker('inspect', f'{PREFIX}-browser').stdout)[0]
        assert not inspected['HostConfig']['PortBindings'], 'Browser published a TCP port'
        assert inspected['HostConfig']['NetworkMode'] == 'none'
        client_script = {'recovery': 'supervisor_client.py',
                         'override_control': 'supervisor_override_control.py'}[case]
        result = docker('run', '--name', f'{PREFIX}-client', '--network', 'none',
                        '--mount', f'type=bind,src={HERE},dst=/probe,readonly',
                        '-v', f'{PREFIX}-runtime:/run/test:ro', '-v', f'{PREFIX}-artifacts:/exchange:ro',
                        '--entrypoint', 'python3', IMAGE, f'/probe/{client_script}', timeout=50)
        print(result.stdout, flush=True)
        exit_code = docker('wait', f'{PREFIX}-browser', timeout=10).stdout.strip()
        assert exit_code == '0', f'Browser Agent container exit: {exit_code}'
        print(f'Real isolated Browser and Supervisor containers: {case} passed', flush=True)
    finally:
        (HERE / 'cross_container_browser.log').write_text(docker('logs', f'{PREFIX}-browser', check=False).stdout)
        cleanup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=('recovery', 'override_control'), default='recovery')
    main(parser.parse_args().case)
