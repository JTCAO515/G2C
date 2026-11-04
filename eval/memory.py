"""#503 executes original signed lifecycle/fence implementations, not source scans.

The existing fault programs assert PG and the actual FakeProvider input. Their
full output (including individual test names and UNKNOWN boundaries) is retained.
No second deletion, retrieval, or publication implementation is introduced here.
"""
from runtime import implementation_probe


EXPERIMENTS = [
    ('typed-context-lifecycle', lambda: implementation_probe('backend/memory/tests/typed_pg.py'),
     'Signed typed saves/edits/pause/resume, actual same/new chat/travel worker, fresh worker CLI, edit during model capture.',
     'Current eligible typed values only in actual provider input; stale/foreign/old-ABI refused; original receipt preserved.'),
    ('withdraw-inflight-context', lambda: implementation_probe('backend/memory_withdrawal/tests/erasure_stop_context_pg.py', '--complete'),
     'Original signed history producer/BG2/Meter/Fake; signed ERASURE1 while old work exists; next EN/CN provider input.',
     'Deleted preference absent, independent fact/Bob retained; actual B hook composition completes without old result publication.'),
    ('retained-chat-unprepared', lambda: implementation_probe('backend/memory_withdrawal/tests/manual_history_erasure_pg.py', '--phase', 'unprepared'),
     'Delete memory with retained chat and an unprepared old extraction; rebuild source/index and run old task.',
     'Old source cannot recreate memory; explicit new source can save anew; old payloads removed.'),
    ('retained-chat-prepared', lambda: implementation_probe('backend/memory_withdrawal/tests/manual_history_erasure_pg.py', '--phase', 'prepared'),
     'Prepare actual old model input before signed deletion, then execute/rebuild.',
     'Frozen old input cannot publish or revive deleted state; original operation remains recoverable.'),
    ('retained-chat-unknown', lambda: implementation_probe('backend/memory_withdrawal/tests/manual_history_erasure_pg.py', '--phase', 'unknown'),
     'Original background task becomes UNKNOWN before signed deletion; reconstruct original state.',
     'No redispatch or old memory revival; UNKNOWN original remains explicitly accounted for.'),
    ('shared-job-cache', lambda: implementation_probe('backend/memory_withdrawal/tests/shared_job_candidate_pg.py'),
     'One memory withdrawn from a real shared job/candidate; re-enable source and rebuild index.',
     'Unrelated discovery/candidate remains; erased text cannot be recached or canonically recreated.'),
    ('trip-inflight-erasure', lambda: implementation_probe('backend/memory_withdrawal/tests/trip_item_erasure_pg.py'),
     'Actual NEEDS source2/scoped Trip workers race signed memory erasure; actual derived result and pending draft cleanup.',
     'Late publication refused; actual payloads cleared; accepted formal Trip/current NEEDS and unrelated memory retained.'),
    ('account-foreground-inflight', lambda: implementation_probe('backend/cj_api/tests/account_inflight_pg.py'),
     'Hold real foreground worker after prefix; signed retirement, device ACK and original progress read; release worker.',
     'No late event; pending/UNKNOWN task and accounting retained; cleanup does not claim completion.'),
    ('account-background-inflight', lambda: implementation_probe('backend/cj_api/tests/background_inflight_pg.py'),
     'Hold real background physical lease during retirement and device continuation, then release late result.',
     'Cleanup cannot erase busy job; publication fenced; original UNKNOWN financial/data state retained.'),
    ('account-new-scope-race', lambda: implementation_probe('backend/memory_withdrawal/tests/account_hooks_pg.py'),
     'Signed retirement/C account hooks and competing first-scope creation at actual SQL locks.',
     'Confirmed C physical cleanup has no late raw owner record; Bob preserved; runtime cannot DELETE.'),
]
