"""Synthetic canonical records only; no AUTH, DB, model or provider claims."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from zoneinfo import ZoneInfo

from cj_trip.domain import Proposal, packed
from cj_needs.domain import Revision, Snapshot
from cj_memory.domain import Command, Context, Item
from cj_draft.review import (InvalidInput, SourceLink, Unavailable, production_factory,
                            request, review)


def needs(changes=None, *, source_text='synthetic manual declaration'):
    fields = changes or {'pace': {'state': 'unknown'}}
    raw = packed(dict(action_id='n-action', needs_id='needs-1', expected_version=0,
                      source=dict(kind='manual', text=source_text), changes=fields))
    snapshot = Snapshot('needs-1', 1, packed(fields))
    return snapshot, (Revision('needs-1', 1, 'n-action', raw, snapshot.content),)


def memory():
    raw = packed(dict(operation_id='m-action', item_id='memory-1', subject='self', slot='pace',
                      kind='preference', text='synthetic preference', extent='long_term',
                      context_id=None, source_id='original-source', source_version=1,
                      occurred_at='approximate date supplied by fixture'))
    return Context((Item(Command.parse(raw), 1, 'active', datetime(2026, 1, 1, tzinfo=timezone.utc)),), 1)


def proposal(items=None):
    return Proposal('proposal-1', 'trip-1', 0, 'basis-1', 200,
                    packed(dict(title='合成草稿 / Synthetic draft', items=items or [
                        dict(id='item-1', text='未定日期 / Date undecided', verification='pending',
                             evidence=['original-needs', 'original-memory'])])))


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.snapshot, self.revisions = needs()
        self.memory = memory()
        self.proposal = proposal()
        self.request = request(self.proposal, self.snapshot, self.revisions, self.memory,
                               subject='self', context_id='trip-1')
        self.links = (SourceLink('item-1', 'original-needs', self.revisions[0]),
                      SourceLink('item-1', 'original-memory', self.memory.items[0]))

    def run_review(self, **overrides):
        args = dict(request=self.request, snapshot=self.snapshot, revisions=self.revisions,
                    memory=self.memory, subject='self', context_id='trip-1', links=self.links,
                    cancelled=False, as_of=100)
        args.update(overrides)
        return review(**args)

    def test_exact_original_and_sources_retained_bilingual_single_candidate(self):
        result = self.run_review()
        self.assertEqual(result.status, 'UNKNOWN')
        self.assertIs(result.candidate, self.proposal)
        self.assertIs(result.links[0].source, self.revisions[0])
        self.assertIs(result.links[1].source, self.memory.items[0])
        self.assertEqual(result.missing, ())
        self.assertFalse(result.can_publish)
        self.assertEqual(result.needs_report.status, 'UNKNOWN')

    def test_same_candidate_keeps_exact_bytes_and_hash(self):
        first, second = self.run_review(), self.run_review()
        self.assertEqual(first.content_sha256, second.content_sha256)
        self.assertEqual(first.candidate.content, self.proposal.content)
        with self.assertRaises(AttributeError):
            first.candidate.content = b'changed'

    def test_unbound_references_remain_missing_without_dropping_original_bytes(self):
        result = self.run_review(links=())
        self.assertEqual(result.missing, (('item-1', 'original-needs'), ('item-1', 'original-memory')))
        self.assertIs(result.candidate, self.proposal)

    def test_no_evidence_is_unknown(self):
        p = proposal([dict(id='item-1', text='synthetic estimate', verification='pending', evidence=[])])
        r = request(p, self.snapshot, self.revisions, self.memory, subject='self', context_id='trip-1')
        self.assertEqual(self.run_review(request=r, links=()).missing,
                         (('item-1', 'SOURCE_NOT_PROVIDED'),))

    def test_cancelled_discards_without_inspecting_dependency_or_leaking_result(self):
        result = self.run_review(cancelled=True, snapshot=None, memory=None)
        self.assertEqual(result.reasons, ('CANCELLED',))
        self.assertIsNone(result.candidate)
        self.assertIsNone(result.content_sha256)
        self.assertEqual(result.links, ())

    def test_expired_discards(self):
        self.assertEqual(self.run_review(as_of=200).reasons, ('EXPIRED',))

    def test_same_needs_version_different_source_bytes_discards(self):
        snapshot, revisions = needs(source_text='different original source at same version')
        self.assertEqual(self.run_review(snapshot=snapshot, revisions=revisions).reasons,
                         ('INPUT_BINDING_CHANGED',))

    def test_memory_epoch_change_discards(self):
        self.assertIsNone(self.run_review(memory=replace(self.memory, epoch=2)).candidate)

    def test_new_needs_revision_discards_instead_of_rebasing(self):
        fields = dict(pace=dict(state='known', value='explicit synthetic correction'))
        raw = packed(dict(action_id='n-correction', needs_id='needs-1', expected_version=1,
                          source=dict(kind='manual', text='synthetic correction'), changes=fields))
        snapshot = Snapshot('needs-1', 2, packed(fields))
        revisions = self.revisions + (Revision('needs-1', 2, 'n-correction', raw, snapshot.content),)
        self.assertIsNone(self.run_review(snapshot=snapshot, revisions=revisions).candidate)

    def test_removed_memory_and_changed_context_discard(self):
        self.assertIsNone(self.run_review(memory=replace(self.memory, items=())).candidate)
        self.assertIsNone(self.run_review(context_id='another-trip').candidate)

    def test_memory_content_changed_at_same_version_and_epoch_discards(self):
        item = self.memory.items[0]
        cmd = Command.parse(item.command.raw.replace(b'synthetic preference', b'corrected preference'))
        changed = replace(self.memory, items=(replace(item, command=cmd),))
        self.assertEqual(self.run_review(memory=changed).reasons, ('INPUT_BINDING_CHANGED',))

    def test_missing_history_rejected(self):
        with self.assertRaises(InvalidInput): self.run_review(revisions=())

    def test_revision_mismatch_rejected(self):
        with self.assertRaises(InvalidInput):
            self.run_review(revisions=(replace(self.revisions[0], action_id='other'),))

    def test_cross_subject_and_previous_trip_memory_rejected(self):
        with self.assertRaises(InvalidInput): self.run_review(subject='companion:other')
        item = self.memory.items[0]
        raw = item.command.raw.replace(b'"long_term"', b'"current"').replace(b'"context_id":null', b'"context_id":"old-trip"')
        wrong = replace(self.memory, items=(replace(item, command=Command.parse(raw)),))
        with self.assertRaises(InvalidInput): self.run_review(memory=wrong)

    def test_disabled_and_inference_memory_rejected(self):
        item = self.memory.items[0]
        with self.assertRaises(InvalidInput):
            self.run_review(memory=replace(self.memory, items=(replace(item, status='disabled'),)))
        cmd = Command.parse(item.command.raw.replace(b'"preference"', b'"inference"'))
        with self.assertRaises(InvalidInput):
            self.run_review(memory=replace(self.memory, items=(replace(item, command=cmd),)))

    def test_reference_cannot_attach_to_other_item_or_nonoriginal_source(self):
        for link in (replace(self.links[0], item_id='other-item'),
                     replace(self.links[0], evidence_ref='other-ref'),
                     replace(self.links[0], source=replace(self.revisions[0], action_id='other'))):
            with self.subTest(link=link), self.assertRaises(InvalidInput):
                self.run_review(links=(link,))

    def test_duplicate_links_and_conflicting_reference_rejected(self):
        with self.assertRaises(InvalidInput): self.run_review(links=self.links + self.links)
        p = proposal([dict(id=i, text='synthetic', verification='pending', evidence=['shared'])
                      for i in ('a', 'b')])
        r = request(p, self.snapshot, self.revisions, self.memory, subject='self', context_id='trip-1')
        with self.assertRaises(InvalidInput):
            self.run_review(request=r, links=(SourceLink('a', 'shared', self.revisions[0]),
                                              SourceLink('b', 'shared', self.memory.items[0])))

    def test_verified_claim_rejected_even_with_matching_reference(self):
        p = proposal([dict(id='item-1', text='synthetic truth claim', verification='verified',
                           evidence=['original-needs'])])
        r = request(p, self.snapshot, self.revisions, self.memory, subject='self', context_id='trip-1')
        with self.assertRaises(InvalidInput): self.run_review(request=r, links=self.links[:1])

    def test_trip_owner_rejects_duplicate_id_and_uncontracted_date(self):
        item = dict(id='same', text='synthetic', verification='pending', evidence=[])
        with self.assertRaises(ValueError): proposal([item, item])
        with self.assertRaises(ValueError): proposal([dict(item, date='2026-10-23')])

    def test_canonical_original_bytes_required(self):
        with self.assertRaises(ValueError): replace(self.proposal, content=self.proposal.content + b' ')

    def test_feas_conflict_retains_original_evidence(self):
        def event(at):
            return {k: dict(state='known', value=v) for k, v in
                    dict(date='2026-10-23', time=at, timezone='Asia/Shanghai', place='synthetic').items()}
        fields = dict(arrival=event('12:00'), departure=event('11:00'))
        snapshot, revisions = needs(fields)
        r = request(self.proposal, snapshot, revisions, self.memory, subject='self', context_id='trip-1')
        result = self.run_review(request=r, snapshot=snapshot, revisions=revisions, links=())
        self.assertEqual(result.status, 'CONFLICT')
        check = next(c for c in result.needs_report.checks if c.code == 'ARRIVAL_DEPARTURE_ORDER')
        self.assertEqual(check.evidence[0].original_input, revisions[0].original_input)
        self.assertFalse(result.can_publish)

    def test_missing_dependencies_and_implicit_control_values_refused(self):
        for kwargs in (dict(memory=None), dict(snapshot=None), dict(cancelled=None), dict(as_of=True)):
            with self.subTest(kwargs=kwargs), self.assertRaises(InvalidInput): self.run_review(**kwargs)

    def test_production_factory_closed(self):
        with self.assertRaises(Unavailable): production_factory()

    def test_dst_fold_source_is_not_original_despite_dataclass_equality(self):
        at = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo('America/New_York'), fold=0)
        original = replace(self.memory.items[0], recorded_at=at)
        other = replace(original, recorded_at=at.replace(fold=1))
        self.assertEqual(original, other)  # The original bug: equality hides fold.
        self.assertNotEqual(at.timestamp(), other.recorded_at.timestamp())
        self.memory = replace(self.memory, items=(original,))
        self.request = request(self.proposal, self.snapshot, self.revisions, self.memory,
                               subject='self', context_id='trip-1')
        with self.assertRaises(InvalidInput):
            self.run_review(links=(replace(self.links[1], source=other),))
        self.assertIs(self.run_review(links=(replace(self.links[1], source=original),)).links[0].source,
                      original)

    def test_same_instant_different_offset_or_zone_representation_is_not_original(self):
        original = self.memory.items[0]
        variants = (original.recorded_at.astimezone(timezone(timedelta(hours=8))),
                    original.recorded_at.replace(tzinfo=ZoneInfo('UTC')),
                    original.recorded_at.replace(tzinfo=timezone(timedelta(0), 'original-other-name')))
        for at in variants:
            self.assertEqual(at, original.recorded_at)
            with self.subTest(at=repr(at)), self.assertRaises(InvalidInput):
                self.run_review(links=(replace(self.links[1], source=replace(original, recorded_at=at)),))

    def test_same_offset_fold_change_discards_bound_inputs(self):
        original = self.memory.items[0]
        other = replace(original, recorded_at=original.recorded_at.replace(fold=1))
        self.assertEqual(original, other)
        self.assertEqual(original.recorded_at.isoformat(), other.recorded_at.isoformat())
        self.assertEqual(self.run_review(memory=replace(self.memory, items=(other,))).reasons,
                         ('INPUT_BINDING_CHANGED',))

    def test_offset_representation_change_discards_bound_inputs(self):
        original = self.memory.items[0]
        at = original.recorded_at.astimezone(timezone(timedelta(hours=8)))
        self.assertEqual(self.run_review(memory=replace(self.memory, items=(
            replace(original, recorded_at=at),))).reasons, ('INPUT_BINDING_CHANGED',))

    def test_utf8_source_spelling_cannot_be_reconstructed_or_relabelled(self):
        original = self.memory.items[0]
        # Identical parsed text but different original JSON UTF8 bytes.
        raw = original.command.raw.replace(b'synthetic preference', b'synthetic pref\\u0065rence')
        alternative = replace(original, command=Command.parse(raw))
        self.assertEqual(original.command.text, alternative.command.text)
        with self.assertRaises(InvalidInput):
            self.run_review(links=(replace(self.links[1], source=alternative),))
        with self.assertRaises(InvalidInput):
            self.run_review(links=(replace(self.links[1], source=replace(original,
                command=replace(original.command, text='changed without changing original bytes'))),))

    def test_adjacent_expiry_does_not_change_original_source(self):
        self.assertIs(self.run_review(as_of=199).candidate, self.proposal)
        result = self.run_review(as_of=201)
        self.assertEqual(result.reasons, ('EXPIRED',))
        self.assertEqual(result.links, ())


if __name__ == '__main__': unittest.main()
