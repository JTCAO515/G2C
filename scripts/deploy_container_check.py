"""Exercise an explicit running local Compose stack; synthetic identities only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

os.environ['CJ_ENV'] = 'local'
import httpx
import dev_auth


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    values = dict(line.split('=', 1) for line in (args.root / 'compose.env').read_text().splitlines())
    base = 'http://127.0.0.1:' + values['CJ_DEPLOY_PORT']
    compose = ['docker', 'compose', '--env-file', str(args.root / 'compose.env'), '-f', 'deploy/compose.yaml']

    def command(*tail):
        return subprocess.run([*compose, *tail], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    def wait_ready(client):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                response=client.get('/health/ready')
            except httpx.TransportError:
                # Read-only startup probe: the listener can be between bind and
                # readiness while Compose recreates it. No write is retried.
                response=None
            if response is not None and response.status_code == 200:return
            time.sleep(0.5)
        raise AssertionError('deployment did not recover readiness')

    headers = {'Authorization': 'Bearer ' + dev_auth.token(args.root / 'config/auth', 'synthetic-alice', 30),
               'Content-Type': 'application/octet-stream'}
    with httpx.Client(base_url=base, trust_env=False, timeout=5) as client:
        wait_ready(client)
        assert client.get('/health/live').status_code == 200
        assert client.get('/v1/trips').status_code == 401
        cid = 'container-' + uuid.uuid4().hex
        response = client.put('/v1/conversations', params={'conversation_id': cid}, headers=headers)
        assert response.status_code == 200, response.status_code
        head = response.json()
        body = dict(version='MESSAGE-send.1', conversation_id=cid, message_id=cid,
                    text='SYNTHETIC container English reply', trip_id=None, creation_intent='none',
                    expected_generation=head['generation'], expected_sequence=0)
        invalid = client.post('/v1/messages', content=json.dumps(dict(body, version='MESSAGE-send.0')), headers=headers)
        assert invalid.status_code == 400, invalid.status_code
        sent = client.post('/v1/messages', content=json.dumps(body), headers=headers)
        assert sent.status_code == 200, sent.status_code
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            display = client.get('/v1/run-display', params={'message_id': cid}, headers=headers)
            if display.status_code == 503:
                time.sleep(0.5)
                continue
            assert display.status_code == 200, (display.status_code, display.text)
            if display.json()['snapshot']['status'] == 'completed':
                break
            time.sleep(0.5)
        else:
            raise AssertionError('actual container worker did not complete')
        command('stop', 'worker')
        time.sleep(16)
        assert client.get('/health/live').status_code == 200
        response = client.get('/health/ready')
        assert response.status_code == 503 and response.json()['component'] == 'worker_heartbeat_stale'
        assert client.get('/v1/trips', headers=headers).status_code == 503
        command('start', 'worker')
        wait_ready(client)
        command('stop', 'worker')
        fault = command('run','-d','--no-deps','-e','CJ_DEPLOY_PROVIDER=fake-unavailable','worker').decode().strip()
        try:
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                response=client.get('/health/ready')
                if response.status_code==503 and response.json()['component']=='model_unavailable':break
                time.sleep(0.5)
            else:raise AssertionError('model fault was not located')
            logs=subprocess.check_output(['docker','logs',fault],stderr=subprocess.STDOUT)
            assert b'ALERT model_unavailable' in logs
        finally:
            subprocess.run(['docker','stop','--time','5',fault],check=True,stdout=subprocess.PIPE)
            command('start','worker')
        wait_ready(client)
        command('stop', 'database')
        response = client.get('/health/ready')
        assert response.status_code == 503 and response.json()['component'] == 'database_unavailable'
        assert client.get('/health/live').status_code == 200
        command('start', 'database')
        wait_ready(client)
    print('PASS local Linux containers: signed API -> real PG/worker/FakeProvider; legacy compatible/unknown version rejected; '
          'worker stop, synthetic model fault and database loss with live=200/ready=503, located alert, business closed, restart recovery')


if __name__ == '__main__':
    main()
