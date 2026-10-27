"""MESSAGE-SEND@1 reference checks (ADR-0008). Synthetic, stdlib only; not the service."""
import hashlib
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = json.load(open(os.path.join(HERE, 'send-permit-samples.json'), encoding='utf-8'))
FIELDS = {'version', 'conversation_id', 'message_id', 'text', 'trip_id', 'creation_intent',
          'expected_generation', 'expected_sequence'}


class Invalid(Exception):
    pass


class Conflict(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def parse(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise Invalid('duplicate key')
            out[k] = v
        return out
    try:
        obj = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
    except (ValueError, UnicodeError) as exc:
        raise Invalid('invalid json') from exc
    if not isinstance(obj, dict) or set(obj) != FIELDS:
        raise Invalid('fields')
    if obj['version'] != 'MESSAGE-send.1':
        raise Invalid('version')
    for k in ('conversation_id', 'message_id', 'text', 'expected_generation'):
        if not isinstance(obj[k], str) or not obj[k].strip():
            raise Invalid(k)
    seq = obj['expected_sequence']
    if type(seq) is not int or seq < 0:
        raise Invalid('expected_sequence')
    if obj['trip_id'] is not None or obj['creation_intent'] not in ('none', 'consider_trip'):
        raise Invalid('trip')
    return obj


def classify(expected, own_sha256, receipt_sha256, head):
    if receipt_sha256 is not None:
        return 'accepted' if receipt_sha256 == own_sha256 else 'integrity_error'
    if head is None or head[0] != expected[0] or head[1] > expected[1]:
        return 'not_accepted'
    return 'resubmit_original' if head[1] == expected[1] else 'resync_required'


class Server:
    """One scope; each call is one serialized transaction, like the scope row lock."""
    def __init__(self):
        self.chats = {}     # conversation_id -> [generation, last_sequence, active]
        self.receipts = {}  # message_id -> (raw, conversation_id, generation, sequence)

    def open(self, cid, generation):
        self.chats.setdefault(cid, [generation, 0, True])

    def submit(self, raw):
        obj = parse(raw)
        old = self.receipts.get(obj['message_id'])
        if old is not None:
            if old[0] != raw:
                raise Conflict('INPUT_CONFLICT')
            return old
        chat = self.chats.get(obj['conversation_id'])
        if chat is None or not chat[2]:
            raise Conflict('UNAVAILABLE')
        if (chat[0], chat[1]) != (obj['expected_generation'], obj['expected_sequence']):
            raise Conflict('SEQUENCE_CONFLICT')
        chat[1] += 1
        rec = (raw, obj['conversation_id'], chat[0], chat[1])
        self.receipts[obj['message_id']] = rec
        return rec

    def status(self, cid, mid):
        chat = self.chats.get(cid)
        head = (chat[0], chat[1]) if chat and chat[2] else None
        rec = self.receipts.get(mid)
        return (hashlib.sha256(rec[0]).hexdigest() if rec else None), head


def body(mid, gen='g1', seq=0, cid='c1'):
    return json.dumps({'version': 'MESSAGE-send.1', 'conversation_id': cid, 'message_id': mid,
                       'text': 'hi', 'trip_id': None, 'creation_intent': 'none',
                       'expected_generation': gen, 'expected_sequence': seq},
                      separators=(',', ':')).encode()


class SendPermitChecks(unittest.TestCase):
    def test_body_samples(self):
        for case in SAMPLES['bodies']['valid']:
            parse(case['raw'].encode('utf-8'))
        for case in SAMPLES['bodies']['invalid']:
            with self.assertRaises(Invalid, msg=case['name']):
                parse(case['raw'].encode('utf-8'))

    def test_classify_samples(self):
        for c in SAMPLES['classify']:
            head = tuple(c['head']) if c['head'] else None
            self.assertEqual(classify(tuple(c['expected']), c['own_sha256'], c['receipt_sha256'], head),
                             c['decision'], c['name'])

    def test_same_head_only_one_accepted(self):
        s = Server(); s.open('c1', 'g1')
        s.submit(body('a'))
        with self.assertRaises(Conflict) as cm:
            s.submit(body('b'))
        self.assertEqual(cm.exception.code, 'SEQUENCE_CONFLICT')

    def test_replay_returns_original_after_head_moved(self):
        s = Server(); s.open('c1', 'g1')
        first = s.submit(body('a'))
        s.submit(body('b', seq=1))
        self.assertEqual(s.submit(body('a')), first)
        with self.assertRaises(Conflict) as cm:
            s.submit(body('a', seq=1))
        self.assertEqual(cm.exception.code, 'INPUT_CONFLICT')

    def test_rolled_back_client_cannot_duplicate(self):
        s = Server(); s.open('c1', 'g1')
        lost = body('a')  # client forgot this after a snapshot rollback
        s.submit(lost)
        h, head = s.status('c1', 'fresh')
        self.assertEqual(head, ('g1', 1))
        with self.assertRaises(Conflict):
            s.submit(body('b', seq=0))  # stale cached head
        s.submit(body('b', seq=head[1]))
        self.assertEqual(sorted(r[3] for r in s.receipts.values()), [1, 2])

    def test_unknown_then_superseded_is_terminal(self):
        s = Server(); s.open('c1', 'g1')
        pending = body('a')  # never arrived
        s.submit(body('other'))
        h, head = s.status('c1', 'a')
        own = hashlib.sha256(pending).hexdigest()
        self.assertEqual(classify(('g1', 0), own, h, head), 'not_accepted')
        with self.assertRaises(Conflict):
            s.submit(pending)  # a late arrival can never be accepted

    def test_unknown_still_open_resubmits_original_once(self):
        s = Server(); s.open('c1', 'g1')
        pending = body('a')
        own = hashlib.sha256(pending).hexdigest()
        h, head = s.status('c1', 'a')
        self.assertEqual(classify(('g1', 0), own, h, head), 'resubmit_original')
        first = s.submit(pending)
        self.assertEqual(s.submit(pending), first)  # the delayed original arrives later
        h, head = s.status('c1', 'a')
        self.assertEqual(classify(('g1', 0), own, h, head), 'accepted')
        self.assertEqual(len(s.receipts), 1)

    def test_closed_conversation_is_terminal(self):
        s = Server(); s.open('c1', 'g1')
        s.chats['c1'][2] = False
        h, head = s.status('c1', 'a')
        self.assertEqual(classify(('g1', 0), 'x', h, head), 'not_accepted')
        with self.assertRaises(Conflict):
            s.submit(body('a'))


if __name__ == '__main__':
    unittest.main()
