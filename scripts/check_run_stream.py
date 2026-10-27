"""Real loopback Swift SSE reads on a disposable local PostgreSQL database.

Run with uv, CJ_PG_BINDIR and DEVELOPER_DIR explicitly set. Uses FakeProvider only;
no cloud, real account, Keychain, paid model or device. Temporary development tokens
are passed to the child process environment, never printed or saved in the repo.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import uuid

import psycopg
import uvicorn
from fastapi.testclient import TestClient

import dev_auth
import migrate
from pg_suites import ROOT, cluster
from cj_api.local_app import create_local_app, LocalDatabase, ISSUER, scope_for
from cj_agent.provider import FakeProvider
from cj_agent.worker import RunWorker
from cj_message.domain import Service as MessageService
from cj_run.core import Service as RunService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch-path', required=True)
    args = parser.parse_args()
    if not os.environ.get('DEVELOPER_DIR') or not os.environ.get('CJ_PG_BINDIR'):
        raise SystemExit('Explicit DEVELOPER_DIR and CJ_PG_BINDIR are required')
    os.environ['CJ_ENV'] = 'local'
    with tempfile.TemporaryDirectory(prefix='g2c-stream-') as temp:
        root = Path(temp)
        with cluster('stream', port=55489, role='cj_stream', root=root / 'pg') as config:
            with psycopg.connect(**config, autocommit=True) as conn:
                versions = migrate.load()
                migrate.up(conn, versions, versions[-1]['version'])
            connection = root / 'conn.json'
            connection.write_text(json.dumps(config))
            auth = root / 'auth'
            dev_auth.init(auth, ['stream-owner', 'foreign-owner'])
            owner_token = dev_auth.token(auth, 'stream-owner', 10)
            foreign_token = dev_auth.token(auth, 'foreign-owner', 10)
            app = create_local_app(conninfo_path=connection, auth_dir=auth)
            database = LocalDatabase(connection)
            cases = []
            with TestClient(app) as client:
                headers = {'Authorization': 'Bearer ' + owner_token}
                for text in ('北京三日游', 'Three days in Beijing'):
                    conversation = uuid.uuid4().hex
                    opened = client.put('/v1/conversations', params={'conversation_id': conversation}, headers=headers)
                    if opened.status_code != 200:
                        raise RuntimeError('local conversation setup failed')
                    mid = 'm/+%中文-' + uuid.uuid4().hex
                    body = json.dumps(dict(version='MESSAGE-draft.1', conversation_id=conversation,
                        message_id=mid, text=text, trip_id=None, creation_intent='none'), ensure_ascii=False).encode()
                    response = client.post('/v1/messages', content=body,
                        headers={**headers, 'Content-Type': 'application/octet-stream'})
                    if response.status_code != 200:
                        raise RuntimeError('local message setup failed')
                    scope = scope_for(ISSUER, 'stream-owner')
                    messages = MessageService(database.message_repository(scope), new_run_id=lambda: None)
                    runs = RunService(database.run_repository(scope), valid=lambda b: messages.query(b.message_id) is not None)
                    RunWorker(scope=scope, messages=messages, runs=runs, provider=FakeProvider()).process()
                    snapshot = client.get('/v1/run-display', params={'message_id': mid}, headers=headers)
                    if snapshot.status_code != 200 or snapshot.json()['snapshot']['status'] != 'completed':
                        raise RuntimeError('local worker did not complete')
                    cases.append(dict(receipt=response.json()['receipt'], text=snapshot.json()['snapshot']['text']))
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                server = uvicorn.Server(uvicorn.Config(app, log_level='warning', access_log=False))
                thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
                thread.start()
                try:
                    deadline = time.monotonic() + 10
                    while not server.started and thread.is_alive() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    if not server.started:
                        raise RuntimeError('loopback server did not start')
                    env = dict(os.environ, CJ_RUN_STREAM_TEST_URL=f'http://127.0.0.1:{sock.getsockname()[1]}',
                        CJ_RUN_STREAM_TEST_TOKEN=owner_token, CJ_RUN_STREAM_TEST_FOREIGN_TOKEN=foreign_token,
                        CJ_RUN_STREAM_TEST_CASES=json.dumps(cases, ensure_ascii=False))
                    result = subprocess.run(['swift', 'test', '--package-path', str(ROOT / 'ios/Modules/CJRunClient'),
                        '--scratch-path', args.scratch_path, '--disable-sandbox', '--skip-update',
                        '--filter', 'RunEventStreamTests/liveLoopback'], env=env)
                    if result.returncode:
                        raise SystemExit(result.returncode)
                    print('PASS: real Swift HTTP + local API + private PG; zh/en reads and foreign-owner refusal; FakeProvider only')
                finally:
                    server.should_exit = True
                    thread.join(timeout=10)
                    if thread.is_alive():
                        raise RuntimeError('loopback server did not stop')


if __name__ == '__main__':
    main()
