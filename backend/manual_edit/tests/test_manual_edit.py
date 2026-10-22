"""Local synthetic tests using the actual CJ015 Trip/Proposal classes. No IO."""
from dataclasses import FrozenInstanceError, replace
import json
import unittest
from unittest.mock import patch

from cj_trip.domain import Proposal, Trip, packed
from cj_manual_edit import Draft, EditSession, SaveUnavailable, Unsupported, edit


def item(key, text, verified=True):
    return dict(id=key, text=text, verification='verified' if verified else 'pending',
                evidence=['source:' + key] if verified else [])


def trip():
    return Trip('trip-1', 7, packed(dict(title='行程 café', items=[
        item('a', 'café'), item('b', '固定事项'), item('c', '原内容') ])))


class ManualEditTests(unittest.TestCase):
    def setUp(self):
        self.original = trip()

    def edit(self, **kwargs):
        args = dict(expected_version=7, original_content=self.original.content,
                    selected_ids=('a', 'c'))
        args.update(kwargs)
        return edit(self.original, **args)

    def test_actual_proposal_and_exact_diff(self):
        draft = self.edit(text_updates=(('a', 'cafe\u0301'),))
        proposal = draft.to_proposal(proposal_id='p1', basis_version='needs-1',
                                     expires_at=12345, expected_version=7)
        self.assertIs(type(proposal), Proposal)
        self.assertEqual(proposal.content, draft.content)
        self.assertEqual(proposal.expected_version, 7)
        change, = draft.diff
        self.assertEqual(change.path, ('items', 'a'))
        self.assertEqual(json.loads(change.before)['text'], 'café')
        self.assertEqual(json.loads(change.after)['text'], 'cafe\u0301')
        self.assertEqual(json.loads(change.after)['verification'], 'pending')
        self.assertEqual(json.loads(change.after)['evidence'], [])
        self.assertEqual(self.original, trip())
        self.assertNotEqual('café'.encode(), 'cafe\u0301'.encode())

    def test_noop_is_exact_and_no_evidence_loss(self):
        draft = self.edit(text_updates=(('a', 'café'),))
        self.assertEqual(draft.content, self.original.content)
        self.assertEqual(draft.diff, ())

    def test_unselected_content_and_position_exact(self):
        draft = self.edit(order=('c', 'b', 'a'))
        before, after = json.loads(self.original.content), json.loads(draft.content)
        self.assertEqual(packed(before['items'][1]), packed(after['items'][1]))
        self.assertEqual(draft.diff[0].path, ('items', 'order'))
        with self.assertRaises(ValueError):
            self.edit(order=('c', 'a', 'b'))
        with self.assertRaises(ValueError):
            self.edit(text_updates=(('b', 'changed'),))

    def test_title_requires_explicit_selection(self):
        with self.assertRaises(ValueError):
            self.edit(title='New')
        draft = self.edit(selected_ids=(), title_selected=True, title=' New ')
        self.assertEqual(draft.diff[0].after, packed(' New '))
        with self.assertRaises(ValueError):
            self.edit(title_selected=True, title=' ')

    def test_trusted_protection_is_constraint_only(self):
        draft = self.edit(protected_ids=frozenset({'a'}))
        self.assertEqual(draft.protection_status, 'CONTEXT_ONLY')
        self.assertEqual(self.edit().protection_status, 'UNKNOWN')
        with self.assertRaises(ValueError):
            self.edit(protected_ids=frozenset({'a'}), text_updates=(('a', 'new'),))
        with self.assertRaises(ValueError):
            self.edit(protected_ids=frozenset({'a'}), order=('c', 'b', 'a'))
        with self.assertRaises(ValueError):
            self.edit(protected_ids=frozenset({'foreign'}))
        with self.assertRaises(ValueError):
            self.edit(protected_ids=set())

    def test_ids_scope_and_shape_rejected(self):
        for kwargs in [dict(selected_ids=('a', 'a')), dict(selected_ids=('foreign',)),
                       dict(order=('a', 'b', 'b')), dict(order=('a', 'b')),
                       dict(text_updates=(('a', 'x'), ('a', 'y'))),
                       dict(text_updates=(('a', ''),)), dict(selected_ids=['a'])]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.edit(**kwargs)
        doc = json.loads(self.original.content)
        doc['items'].append(doc['items'][0])
        with self.assertRaises(ValueError):
            edit(replace(self.original, content=packed(doc)), expected_version=7,
                 original_content=packed(doc), selected_ids=())

    def test_exact_original_required(self):
        for kwargs in [dict(expected_version=8), dict(expected_version=True),
                       dict(original_content=self.original.content + b' '),
                       dict(original_content=bytearray(self.original.content))]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.edit(**kwargs)
        with self.assertRaises(ValueError):
            edit(replace(self.original, version=0), expected_version=0,
                 original_content=self.original.content, selected_ids=())

    def test_no_unknown_schema_defaults(self):
        for field in ('time', 'day', 'place', 'locked'):
            doc = json.loads(self.original.content)
            doc['items'][0][field] = None
            with self.subTest(field=field), self.assertRaises(Unsupported):
                edit(replace(self.original, content=packed(doc)), expected_version=7,
                     original_content=packed(doc), selected_ids=('a',))
        with self.assertRaises(TypeError):
            self.edit(locked=True)

    def test_noncanonical_or_invalid_original(self):
        for content in [b'{"title":"x","title":"y","items":[]}', b'[]',
                        self.original.content + b' ', b'\xff', b'']:
            with self.subTest(content=content), self.assertRaises((ValueError, UnicodeError)):
                edit(replace(self.original, content=content), expected_version=7,
                     original_content=content, selected_ids=())

    def test_direct_draft_cannot_bypass_protection_or_fact_reset(self):
        for mutate in ('outside', 'evidence', 'renumber', 'delete', 'same-text-proof'):
            doc = json.loads(self.original.content)
            if mutate == 'outside': doc['items'][1]['text'] = 'bad'
            if mutate == 'evidence':
                doc['items'][0]['text'] = 'new'
                doc['items'][0]['evidence'] = doc['items'][2]['evidence']
            if mutate == 'renumber': doc['items'][0]['id'] = 'new'
            if mutate == 'delete': doc['items'].pop()
            if mutate == 'same-text-proof': doc['items'][0]['evidence'] = ['new-proof']
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                Draft(self.original, ('a', 'c'), False, None, packed(doc))

    def test_immutable_and_input_not_aliased(self):
        draft = self.edit(text_updates=(('a', '  用户 input  '),))
        with self.assertRaises(FrozenInstanceError):
            draft.content = b'bad'
        with self.assertRaises(FrozenInstanceError):
            draft.original.version = 8
        changes = draft.diff
        with self.assertRaises(FrozenInstanceError):
            changes[0].after = b'bad'

    def test_candidate_metadata_all_required_and_original_version(self):
        draft = self.edit()
        metadata = dict(proposal_id='p1', basis_version='needs-1', expires_at=12345,
                        expected_version=7)
        for key in metadata:
            args = dict(metadata)
            del args[key]
            with self.subTest(missing=key), self.assertRaises(TypeError):
                draft.to_proposal(**args)
        for key, value in [('proposal_id', None), ('basis_version', ''),
                           ('expires_at', None), ('expected_version', 8)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                draft.to_proposal(**(metadata | {key: value}))

    def test_actual_proposal_validator_is_used(self):
        with patch.object(Proposal, '__post_init__', side_effect=ValueError('sentinel')):
            with self.assertRaisesRegex(ValueError, 'sentinel'):
                self.edit().to_proposal(proposal_id='p1', basis_version='needs-1',
                                        expires_at=12345, expected_version=7)

    def test_conflict_unknown_preserve_exact_draft_and_version(self):
        draft = self.edit(text_updates=(('a', '用户未保存'),))
        session = EditSession(draft)
        current = replace(self.original, version=8)
        conflict = session.observe(current)
        self.assertEqual(conflict.status, 'CONFLICT')
        self.assertIs(conflict.draft, draft)
        self.assertEqual(conflict.draft.original.version, 7)
        self.assertEqual(conflict.observe(self.original).status, 'CONFLICT')
        unknown = conflict.observe(None)
        self.assertEqual(unknown.status, 'UNKNOWN')
        self.assertIs(unknown.draft, draft)
        self.assertEqual(unknown.observe(self.original).status, 'UNKNOWN')
        self.assertEqual(unknown.observe(current).status, 'UNKNOWN')
        self.assertEqual(unknown.draft.content, draft.content)
        self.assertFalse(unknown.can_save)
        with self.assertRaises(ValueError):
            unknown.observe(replace(self.original, trip_id='foreign'))
        doc = json.loads(self.original.content)
        doc['title'] = 'same version divergent'
        self.assertEqual(session.observe(replace(self.original, content=packed(doc))).status, 'CONFLICT')

    def test_save_unavailable_has_no_trip_write_calls(self):
        # Module imports only DTO/validator/serializer, not repository or Boundary.
        import cj_manual_edit.core as core
        self.assertFalse(hasattr(core, 'Repository'))
        self.assertFalse(hasattr(core, 'Boundary'))
        draft = self.edit()
        for target in (draft, EditSession(draft)):
            with self.assertRaises(SaveUnavailable):
                target.save()
        self.assertEqual(self.original, trip())


if __name__ == '__main__':
    unittest.main()
