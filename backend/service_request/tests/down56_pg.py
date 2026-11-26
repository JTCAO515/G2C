"""#1770 review: 0056 on its own refuses a down that would drop retained service requests.

Fresh cluster migrated only to 56 (no 0057 in front), one synthetic request, then down to 55.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

import psycopg

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import migrate  # noqa: E402


def main(config):
    migrations = migrate.load()
    with psycopg.connect(**config, autocommit=True) as conn:
        migrate.up(conn, migrations, 56)
        assert migrate.applied(conn)[-1] == 56
        conn.execute('INSERT INTO cj_service_request_scope(scope_digest) VALUES(%s)',
                     (hashlib.sha256(b'local:test:down56').hexdigest(),))
        conn.execute("INSERT INTO cj_service_request(scope,request_id,client_request_id,original_input,input_sha256,state,"
                     "details,human_service) VALUES('local:test:down56',%s,'c1',%s,%s,'submitted','{}','{}')",
                     ('sr_' + 'a' * 32, b'x', 'b' * 64))
        try:
            migrate.down(conn, migrations, 55)
        except psycopg.Error:
            pass
        else:
            raise AssertionError('0056 down dropped a retained service request')
        assert migrate.applied(conn)[-1] == 56
        assert conn.execute('SELECT count(*) FROM cj_service_request').fetchone()[0] == 1
        conn.execute('DELETE FROM cj_service_request')
        migrate.down(conn, migrations, 55)
        assert migrate.applied(conn)[-1] == 55
    print('PASS 0056 alone: down with a retained request refused and changes nothing; empty down to 55 succeeds')


if __name__ == '__main__':
    main(json.loads(Path(os.environ['CJ_E2E_CONNINFO']).read_text()))
