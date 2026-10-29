"""#198 real runtime-role acceptance. Run: uv run --locked python -B backend/cj_api/tests/local_history_pg.py"""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

from fastapi.testclient import TestClient
import psycopg
from cj_api.local_app import app_from_environment, LocalDatabase, ISSUER, scope_for

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import dev_auth
import migrate
import pg_suites


def expect(response, status=200):
    assert response.status_code == status, (response.status_code, response.text)
    return response.json()


def exercise(auth, conninfo):
    dev_auth.init(auth, ['alice', 'bob'])
    headers = {s: {'Authorization': 'Bearer ' + dev_auth.token(auth, s, 30)} for s in ('alice', 'bob')}
    with patch.dict(os.environ, {'CJ_LOCAL_AUTH_DIR': str(auth), 'CJ_LOCAL_CONNINFO': str(conninfo)}):
        app = app_from_environment()
        db = LocalDatabase(conninfo)
        with db.connect(scope_for(ISSUER, 'alice')) as connection:
            assert connection.execute('SELECT current_user').fetchone()[0] == 'cj_m1_runtime'
        with TestClient(app) as client:
            generations = {}
            for cid in ('chat-a', 'chat-b'):
                generations[cid] = expect(client.put('/v1/conversations', params={'conversation_id': cid}, headers=headers['alice']))['generation']
            for index in range(2):
                head = expect(client.get('/v1/message-send-status', params={'conversation_id': 'chat-a'}, headers=headers['alice']))['head']
                raw = json.dumps(dict(version='MESSAGE-send.1', conversation_id='chat-a', message_id=f'm-{index}',
                    text=f'original {index}', trip_id=None, creation_intent='none', expected_generation=head['generation'],
                    expected_sequence=head['last_sequence'])).encode()
                expect(client.post('/v1/messages', content=raw, headers={**headers['alice'], 'Content-Type': 'application/octet-stream'}))
            first = expect(client.get('/v1/conversations', params={'limit': 1}, headers=headers['alice']))
            chat_cursor = first['next_cursor']
            assert chat_cursor and len(first['conversations']) == 1
            history = expect(client.get('/v1/message-history', params={'conversation_id': 'chat-a', 'limit': 1}, headers=headers['alice']))
            history_cursor = history['next_cursor']
            assert history_cursor and history['messages'][0]['text'] == 'original 0'
        # New factory instance loads the persisted key, not test-injected configuration.
        with TestClient(app_from_environment()) as client:
            second = expect(client.get('/v1/conversations', params={'limit': 1, 'cursor': chat_cursor}, headers=headers['alice']))
            assert len(second['conversations']) == 1 and second['next_cursor'] is None
            assert first['conversations'][0]['conversation_id'] != second['conversations'][0]['conversation_id']
            second_history = expect(client.get('/v1/message-history', params={'conversation_id': 'chat-a', 'limit': 1, 'cursor': history_cursor}, headers=headers['alice']))
            assert second_history['messages'][0]['text'] == 'original 1' and second_history['next_cursor'] is None
            for token, subject in ((chat_cursor, 'bob'), (history_cursor, 'alice'), (chat_cursor[:-8] + 'AAAAAAAA', 'alice')):
                expect(client.get('/v1/conversations', params={'limit': 1, 'cursor': token}, headers=headers[subject]), 409)
            with patch('cj_api.local_app.time.time', return_value=time.time() + 301):
                expect(client.get('/v1/conversations', params={'limit': 1, 'cursor': chat_cursor}, headers=headers['alice']), 409)
            params = {'conversation_id': 'chat-a', 'generation': generations['chat-a']}
            assert expect(client.get('/v1/message-drafts', params=params, headers=headers['alice']))['draft'] is None
            def put(subject, revision, raw):
                return client.put('/v1/message-drafts', params={**params, 'expected_revision': revision}, content=raw,
                    headers={**headers[subject], 'Content-Type': 'application/octet-stream'})
            assert expect(put('alice', 0, b'first'))['draft']['revision'] == 1
            assert expect(put('alice', 1, b'updated'))['draft']['revision'] == 2
            assert expect(put('alice', 1, b'stale'), 409)['error']['code'] == 'DRAFT_REVISION_CONFLICT'
            expect(put('bob', 2, b'foreign'), 503)
            expect(client.get('/v1/message-drafts', params=params, headers=headers['bob']), 503)
            saved = expect(client.get('/v1/message-drafts', params=params, headers=headers['alice']))['draft']
            assert saved['revision'] == 2 and base64.b64decode(saved['original_utf8_base64']) == b'updated'
            print('PASS runtime role, two-page conversations/messages, API rebuild, cursor negatives, draft CAS and cross-account rejection')


def main():
    with tempfile.TemporaryDirectory(prefix='g2c-history-') as temp, patch.dict(os.environ, pg_suites.clean_env(), clear=True):
        root = Path(temp)
        # Reuse the repository private cluster harness, but keep sockets short and isolated.
        with patch.object(pg_suites, 'WORK', root):
            with pg_suites.cluster('history', port=55481, role='cj_history_init') as config:
                with psycopg.connect(**config, autocommit=True) as connection:
                    migrate.up(connection, migrate.load(), migrate.load()[-1]['version'])
                conninfo = root / 'conn.json'
                conninfo.write_text(json.dumps(config))
                exercise(root / 'auth', conninfo)


if __name__ == '__main__':
    main()
