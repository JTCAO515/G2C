"""Synthetic only: no DB, AUTH authority, model, hook or physical deletion."""
from dataclasses import FrozenInstanceError, asdict, replace
from hashlib import sha256
import json
import unittest

from cj_cleanup import core
from cj_memory.domain import Conflict, InvalidInput, Receipt, Unavailable
from cj_memory_withdrawal.domain import (
    Action, OriginalAction, SourceReference, check_candidate_references,
    execute_withdrawal, public_factory,
)
from cj_memory_withdrawal.progress import CleanupLink, observe_cleanup, project


def raw(**changes):
    obj = dict(action_id='original-action', operation='withdraw', item_id='item',
               expected_version=3, source_id='current-source', expected_source_version=2)
    obj.update(changes)
    return json.dumps(obj, ensure_ascii=False).encode('utf-8')


def original():
    value = raw()
    return OriginalAction('synthetic-scope', value,
                          Receipt('original-action', 'item', 4, 'withdrawn', sha256(value).hexdigest()),
                          8, (SourceReference('old-source', 1, ('item',)),
                              SourceReference('current-source', 2, ('item',))))


def cleanup_fixture():
    # Original CJ024 metadata fixture. NOT a proposed single-item cleanup map.
    scope = core.Scope('synthetic', 'issuer', 'subject', 'audience')
    entry = core.Entry('fixture-store', 'a' * 64, True)
    manifest = core.Manifest('fixture-registry', 'b' * 64, (entry,), ())
    op = core.request(scope, 'original-cleanup', 'c' * 64, manifest,
                      core.BARRIERS + ('store:fixture-store',))
    return op, CleanupLink(scope, op.operation_id, op.confirmation_digest, manifest,
                           'synthetic-scope', raw())


def result(op, target, outcome):
    step = next(s for s in op.steps if s.target == target)
    data = dict(protocol=core.VERSION, scope_digest=core.digest(core.encode(asdict(op.scope))),
                operation_id=op.operation_id, target=target, version=step.version,
                invocation=step.invocation, outcome=outcome)
    return core.receipt(op, target, core.encode(data))


class CodecTests(unittest.TestCase):
    def test_exact_bytes_and_unicode_ids_preserved(self):
        value = raw(action_id=' 原动作 ', item_id='条目')
        parsed = Action.parse(value)
        self.assertIs(parsed.raw, value)
        self.assertEqual(parsed.action_id, ' 原动作 ')
        with self.assertRaises(FrozenInstanceError):
            parsed.item_id = 'other'

    def test_duplicate_extra_and_missing_fields_refused(self):
        for value in (raw()[:-1] + b',"item_id":"other"}', raw(owner='foreign'),
                      b'{}', b'[]', raw() + b' trailing'):
            with self.subTest(value=value), self.assertRaises(InvalidInput):
                Action.parse(value)

    def test_versions_not_bool_or_coerced(self):
        for key in ('expected_version', 'expected_source_version'):
            for value in (True, False, 0, -1, 1.0, '1', None):
                with self.subTest(key=key, value=value), self.assertRaises(InvalidInput):
                    Action.parse(raw(**{key: value}))

    def test_pause_resume_delete_not_withdrawal(self):
        for operation in ('pause', 'resume', 'delete', None):
            with self.assertRaises(InvalidInput):
                Action.parse(raw(operation=operation))

    def test_utf8_bytes_and_bounds(self):
        for value in (bytearray(raw()), raw().decode(), b'\xef\xbb\xbf' + raw(),
                      raw().decode().encode('utf-16'), b'\xff', b' ' * 32769,
                      raw(source_id='x' * 4097), raw(item_id='  ')):
            with self.subTest(kind=type(value)), self.assertRaises(InvalidInput):
                Action.parse(value)


class OriginalTests(unittest.TestCase):
    def test_original_recovery_is_historical_and_immutable(self):
        observation = original()
        self.assertIs(observation.recover('synthetic-scope', raw()), observation.receipt)
        self.assertEqual(observation.epoch, 8)
        with self.assertRaises(FrozenInstanceError):
            observation.epoch = 9

    def test_replay_changed_bytes_or_ids_conflict(self):
        for value in (raw() + b' ', raw(action_id='new-action'), raw(item_id='other'),
                      raw(expected_version=4), raw(source_id='old-source')):
            with self.assertRaises(Conflict):
                original().recover('synthetic-scope', value)

    def test_cross_scope_recovery_is_unavailable(self):
        with self.assertRaises(Unavailable):
            original().recover('other-scope', raw())

    def test_receipt_hash_cas_status_item_and_action_binding(self):
        observation = original()
        for changes in (dict(status='disabled'), dict(status='active'), dict(version=3),
                        dict(version=True), dict(item_id='other'), dict(operation_id='other'),
                        dict(input_sha256='d' * 64)):
            with self.subTest(changes=changes), self.assertRaises(Unavailable):
                replace(observation, receipt=replace(observation.receipt, **changes)).validate()

    def test_missing_shared_ambiguous_or_wrong_revision_history_refused(self):
        for history in ((), (SourceReference('current-source', 2, ()),),
                        (SourceReference('current-source', 2, ('item', 'other-item')),),
                        (SourceReference('current-source', 1, ('item',)),),
                        (SourceReference('current-source', 2, ('item',)),) * 2):
            with self.subTest(history=history), self.assertRaises((Unavailable, Conflict)):
                replace(original(), history=history).validate()

    def test_old_source_any_revision_and_same_item_cannot_reenter(self):
        for item_id, sources in (('item', ('new-source',)), ('summary', ('old-source',)),
                                 ('rebuilt-index', ('current-source',)),
                                 ('late-run', ('unrelated', 'old-source'))):
            with self.subTest(item=item_id), self.assertRaises(Conflict):
                check_candidate_references(original(), 'synthetic-scope', item_id=item_id,
                                           source_ids=sources, observed_epoch=8)

    def test_unknown_provenance_or_old_epoch_cannot_publish(self):
        for sources, epoch in (((), 8), (None, 8), (('unrelated',), 7), (('unrelated',), True)):
            with self.assertRaises((Conflict, Unavailable)):
                check_candidate_references(original(), 'synthetic-scope', item_id='other',
                                           source_ids=sources, observed_epoch=epoch)

    def test_unrelated_item_check_does_not_mutate_or_grant_permission(self):
        observation = original()
        self.assertIsNone(check_candidate_references(observation, 'synthetic-scope',
                          item_id='other', source_ids=('new-source',), observed_epoch=8))
        self.assertEqual(observation, original())
        with self.assertRaises(Unavailable):
            check_candidate_references(observation, 'other-scope', item_id='other',
                                       source_ids=('new-source',), observed_epoch=8)

    def test_no_writer_or_public_activation(self):
        for entry in (execute_withdrawal, public_factory):
            with self.assertRaises(Unavailable):
                entry(original_utf8=raw())


class ProgressTests(unittest.TestCase):
    def test_absent_original_is_unknown_never_retry_permission(self):
        observed = project('synthetic-scope')
        self.assertEqual((observed.stop_use, observed.state), ('unknown', 'unknown'))
        self.assertTrue(observed.blockers)

    def test_withdrawn_observation_is_stopped_not_physical_complete(self):
        observed = project('synthetic-scope', original())
        self.assertEqual((observed.stop_use, observed.state), ('stopped', 'blocked'))
        self.assertIsNone(observed.cleanup)
        with self.assertRaises(Unavailable):
            project('foreign', original())

    def test_original_cleanup_states_and_unknown_reconcile(self):
        op, link = cleanup_fixture()
        self.assertEqual(observe_cleanup(op, link).state, op.status)
        op = core.intent(op, 'auth_revocation', 'original-invocation')
        op = result(op, 'auth_revocation', 'confirmed')
        self.assertEqual(observe_cleanup(op, link).state, 'in_progress')
        op = core.intent(op, 'tasks_stopped', 'original-task-invocation')
        op = core.restart(op)
        self.assertEqual(observe_cleanup(op, link).state, 'unknown')
        op = result(op, 'tasks_stopped', 'confirmed')
        self.assertEqual(observe_cleanup(op, link).state, 'in_progress')
        op = core.intent(op, 'restore_fence', 'original-restore-invocation')
        op = result(op, 'restore_fence', 'failed')
        self.assertEqual(observe_cleanup(op, link).state, 'failed')
        with self.assertRaises(core.Conflict):
            result(op, 'restore_fence', 'confirmed')

    def test_finite_completion_never_clears_cj021_blockers(self):
        op, link = cleanup_fixture()
        for step in op.steps:
            op = core.intent(op, step.target, 'invoke:' + step.target)
            op = result(op, step.target, 'confirmed')
        observed = project('synthetic-scope', original(), cleanup=op, link=link)
        self.assertEqual(observed.cleanup.state, 'limited_complete')
        self.assertEqual(observed.cleanup.manifest_digest, link.manifest.registry_digest)
        self.assertEqual(observed.state, 'blocked')
        self.assertEqual(len(observed.cleanup.steps), len(core.BARRIERS) + 1)

    def test_binding_drift_and_incomplete_target_set_refused(self):
        op, link = cleanup_fixture()
        for changes in (dict(operation_id='other'), dict(scope=replace(op.scope, subject='foreign')),
                        dict(confirmation_digest='d' * 64),
                        dict(manifest=replace(op.manifest, registry_digest='e' * 64)),
                        dict(steps=op.steps[1:])):
            with self.assertRaises(Unavailable):
                observe_cleanup(replace(op, **changes), link)
        with self.assertRaises(Unavailable):
            project('synthetic-scope', original(), cleanup=op)
        for changes in (dict(memory_scope='foreign'),
                        dict(withdrawal_original_input=raw(action_id='different')),
                        dict(withdrawal_original_input=raw(expected_version=4))):
            with self.assertRaises(Unavailable):
                project('synthetic-scope', original(), cleanup=op, link=replace(link, **changes))

    def test_missing_hooks_and_registry_drift_reuse_reducer(self):
        op, link = cleanup_fixture()
        blocked = core.request(op.scope, op.operation_id, op.confirmation_digest, op.manifest)
        self.assertEqual(observe_cleanup(blocked, link).state, 'blocked')
        drifted = core.audit_registry(op, replace(op.manifest, registry_digest='d' * 64))
        observed = observe_cleanup(drifted, link)
        self.assertEqual(observed.state, 'blocked')
        self.assertIn('registry_changed_requires_review', observed.gaps)

    def test_bare_confirmed_or_conflicting_original_receipt_refused(self):
        op, link = cleanup_fixture()
        op = core.intent(op, 'auth_revocation', 'original-invocation')
        forged = replace(op, steps=(replace(op.steps[0], state='confirmed'),) + op.steps[1:])
        with self.assertRaises(Unavailable):
            observe_cleanup(forged, link)
        op = result(op, 'auth_revocation', 'unknown')
        forged = replace(op, steps=(replace(op.steps[0], state='confirmed'),) + op.steps[1:])
        with self.assertRaises(Unavailable):
            observe_cleanup(forged, link)
        self.assertEqual(observe_cleanup(op, link).state, 'unknown')


if __name__ == '__main__':
    unittest.main(verbosity=2)
