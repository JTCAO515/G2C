from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import time
import pytest

from cj_trip.confirmation import ConfirmationSigner
from cj_trip.domain import Conflict, Denied
from test_trip import empty, repo, proposal


def prepared(kind='accept', signer=None):
    signer = signer or ConfirmationSigner(b'synthetic-dedicated-key-32-bytes!!')
    r = repo(confirm=signer); p = proposal(); digest = r.publish(p)
    action = signer.issue('A', r.proposal_detail(p.proposal_id), action_id='confirmed-a1',
                          kind=kind, candidate_hash=digest).action
    return signer, r, p, action


def test_issue_is_read_only_and_concurrent_original_commits_once():
    signer, r, p, action = prepared()
    assert r.detail(p.trip_id) is None and r.query_action(action.action_id) is None
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: repo(confirm=signer).act(action), range(2)))
    assert receipts[0] == receipts[1]
    assert r.detail(p.trip_id).version == 1
    # Receipt replay survives issuer rotation; fresh use of old proof does not.
    rotated = repo(confirm=ConfirmationSigner(b'new-synthetic-key-at-least-32-bytes'))
    assert rotated.act(action) == receipts[0]
    with pytest.raises(Conflict): rotated.act(replace(action, kind='reject'))


def test_tampering_denied_and_reject_has_no_formal_trip():
    signer, r, p, action = prepared(kind='reject')
    with pytest.raises(Denied): r.act(replace(action, kind='accept'))
    with pytest.raises(Denied): r.act(replace(action, action_id='replacement'))
    assert r.query_action(action.action_id) is None
    receipt = r.act(action)
    assert receipt.kind == 'reject' and receipt.committed_version is None
    assert r.detail(p.trip_id) is None


def test_expiry_after_last_auth_guard_rolls_back_before_commit():
    signer = ConfirmationSigner(b'x' * 32, lifetime_seconds=3)
    signer, r, p, action = prepared(signer=signer)
    deadline = int(action.confirmation_ref.split('.')[1])
    reached_commit = []
    def guard(stage):
        if stage == 'commit':
            reached_commit.append(True)
            time.sleep(max(0, deadline - time.time()) + 0.02)
    with pytest.raises(Denied): repo(confirm=signer, guard=guard).act(action)
    assert reached_commit  # verified initially; expiry happened during the final guard
    assert r.query_action(action.action_id) is None and r.detail(p.trip_id) is None
    assert r.proposal_detail(p.proposal_id).status == 'pending'
