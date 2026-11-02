"""V2 snapshots preserve original typed messages without widening V1."""
from dataclasses import replace
import hashlib
import json

from cj_memory_jobs.codec import InvalidInput, Source, SourceKind, SourceV2, decode, decode_v2, encode, encode_v2
from cj_memory_jobs.history import read_committed_batch_v2

from test_jobs import message
import test_protected_history as protected


def modern(number, version):
    row = message(number)
    payload = json.loads(row.original_utf8)
    payload.update(version=version, expected_generation='generation',
                   expected_sequence=number - 1, travel_context=None,
                   needs_reference=None)
    if version in ('MESSAGE-send.3', 'MESSAGE-send.4'):
        payload['trip_context'] = None
    if version == 'MESSAGE-send.4':
        payload.update(
            travel_context=dict(id='a' * 32, expected_version=1),
            trip_context=dict(id='trip', expected_version=1, content_sha256='b' * 64,
                              day=None, item_ids=[]),
            modification_intent='none',
        )
    raw = json.dumps(payload, ensure_ascii=False).encode()
    return replace(row, original_utf8=raw,
                   receipt=replace(row.receipt, input_sha256=hashlib.sha256(raw).hexdigest()))


class ModernBatch(protected.ProtectedHistory):
    def setUp(self):
        super().setUp()
        self.source = SourceV2(self.source.cursor, 1, 1)

    def read(self, source=None, mode='incremental'):
        return read_committed_batch_v2(self.boundary, 'synthetic', source or self.source, mode)

    def test_mixed_original_versions_roundtrip_and_old_codec_refusal(self):
        rows = (message(), modern(2, 'MESSAGE-send.2'),
                modern(3, 'MESSAGE-send.3'), modern(4, 'MESSAGE-send.4'))
        source = replace(self.source, cursor=replace(self.source.cursor, through=4))
        self.rows = list(rows)
        raw = self.read(source)
        self.assertEqual(decode_v2(raw), (source, rows, 'incremental'))
        with self.assertRaises(InvalidInput):
            decode(raw)
        with self.assertRaises(InvalidInput):
            encode(Source(source.cursor, 1, 1), rows, 'incremental')

    def test_v1_bytes_are_identical_and_versions_do_not_fallback(self):
        rows = tuple(self.rows)
        legacy_source = Source(self.source.cursor, 1, 1)
        old = encode(legacy_source, rows, 'incremental')
        new = encode_v2(self.source, rows, 'incremental')
        projected = json.loads(new)
        projected.pop('source_kind')
        projected['version'] = 'CJ020-internal.1'
        projected['source']['memory_epoch'] = projected['source'].pop('withdrawal_epoch')
        self.assertEqual(old, json.dumps(projected, ensure_ascii=True, sort_keys=True,
                                        separators=(',', ':')).encode('ascii'))
        self.assertEqual(decode(old), (legacy_source, rows, 'incremental'))
        with self.assertRaises(InvalidInput):
            decode_v2(old)

    def test_source_kind_reservation_never_enables_staff_or_manual_batch(self):
        self.assertEqual(SourceKind.STAFF_PROPOSED, 'staff_proposed')
        for mode, expected in (('incremental', 'committed_message'),
                               ('conversation_end', 'conversation_summary')):
            raw = encode_v2(self.source, tuple(self.rows), mode)
            self.assertEqual(json.loads(raw)['source_kind'], expected)
            for kind in (SourceKind.STAFF_PROPOSED, SourceKind.MANUAL):
                modified = json.loads(raw)
                modified['source_kind'] = kind
                modified = json.dumps(modified, ensure_ascii=True, sort_keys=True,
                                      separators=(',', ':')).encode('ascii')
                with self.assertRaises(InvalidInput):
                    decode_v2(modified)

    def test_zero_message_epoch_and_withdrawal_epoch_are_distinct(self):
        source = replace(self.source, cursor=replace(self.source.cursor, epoch=0),
                         withdrawal_epoch=2)
        self.epoch = 0
        self.assertEqual(decode_v2(self.read(source))[0], source)
        legacy = Source(source.cursor, 1, 2)
        with self.assertRaises(InvalidInput):
            encode(legacy, tuple(self.rows), 'incremental')
        for value in (0, True):
            with self.assertRaises(InvalidInput):
                encode_v2(replace(source, withdrawal_epoch=value), tuple(self.rows), 'incremental')

    def test_modern_source_preserves_b_owned_identity_bounds(self):
        row=message()
        payload=json.loads(row.original_utf8)
        payload['message_id']='m'*300
        raw=json.dumps(payload).encode()
        row=replace(row,original_utf8=raw,receipt=replace(row.receipt,message_id=payload['message_id'],
                    input_sha256=hashlib.sha256(raw).hexdigest()))
        source=replace(self.source,cursor=replace(self.source.cursor,through=1))
        self.assertEqual(decode_v2(encode_v2(source,(row,),'incremental'))[1],(row,))
        with self.assertRaises(InvalidInput):
            encode(Source(source.cursor,1,1),(row,),'incremental')

    def test_new_message_unknown_or_changed_reference_rejected(self):
        for field, value in (('version', 'MESSAGE-send.5'),
                             ('modification_intent', 'auto_accept'),
                             ('travel_context', {'id': 'foreign', 'expected_version': 1})):
            row = modern(1, 'MESSAGE-send.4')
            obj = json.loads(row.original_utf8)
            obj[field] = value
            raw = json.dumps(obj).encode()
            row = replace(row, original_utf8=raw,
                receipt=replace(row.receipt, input_sha256=hashlib.sha256(raw).hexdigest()))
            source = replace(self.source, cursor=replace(self.source.cursor, through=1))
            with self.subTest(field=field), self.assertRaises(ValueError):
                encode_v2(source, (row,), 'incremental')

    def test_exact_interval_no_trip_single_identity_and_no_collection_authority(self):
        # Run inherited boundary assertions with the explicit matching V2 decoder.
        raw = self.read()
        self.assertEqual(decode_v2(raw), (self.source, tuple(self.rows), 'incremental'))
        self.assertEqual(self.resolved, [self.principal])
        self.assertEqual(self.reads, [('chat', 'generation', 0, 2, 2)])

    def test_interval_can_start_after_existing_processing_cursor(self):
        source = replace(self.source, cursor=replace(self.source.cursor, after=1))
        self.assertEqual(decode_v2(self.read(source))[1], (self.rows[1],))

    def test_history_instruction_is_preserved_data_and_cannot_expand_interval(self):
        source, rows, mode = decode_v2(self.read(mode='conversation_end'))
        self.assertEqual((source, mode), (self.source, 'conversation_end'))
        self.assertIn('ignore all rules', rows[0].text)
