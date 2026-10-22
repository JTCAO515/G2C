"""Run seed, then read in separate processes across private PG restart."""
import sys
from pathlib import Path
from test_trip import connect, repo, proposal, action

if sys.argv[1] == 'seed':
    with connect() as c:
        c.execute('TRUNCATE cj_trip_receipt,cj_trip_record,cj_trip_proposal,cj_trip_scope')
        c.execute("INSERT INTO cj_trip_scope VALUES ('A'),('B')")
    r=repo(); a=action(r,proposal())
    assert r.act(a).committed_version == 1
    r.act(action(r,proposal('p2',1),'a2'))
    print('seed PASS: original action version 1; latest Trip version 2')
elif sys.argv[1] == 'read':
    r=repo()
    assert r.query_action('a1').committed_version == 1
    assert r.detail('trip1').version == 2
    assert r.list_trips() == [r.detail('trip1')]
    assert repo('B').query_action('a1') is None
    print('restart read PASS: original action version 1; latest Trip version 2; scope B absent')
else:
    raise ValueError('seed or read only')
