"""Formal codec adaptation is data evidence; no fixture grants a publication lease."""
import json
from dataclasses import replace
import unittest

from cj_needs.contract_v1 import encode_snapshot, encode_revision
from cj_needs.domain import InvalidInput
from cj_place.contract_v1 import encode_result
from cj_feasibility import formal_v1, v1
from cj_feasibility.validator import Candidate
from test_validator import history, known
from test_routes import fixture

BOUNDS = dict(max_revisions=8, max_input_bytes=1048576)


def envelopes(snapshot, revisions):
    return encode_snapshot(snapshot), tuple(encode_revision(r) for r in revisions)


class FormalInputsChecks(unittest.TestCase):
    def test_two_revisions_preserve_exact_evidence_and_unknown_budget(self):
        snapshot, revisions = history(dict(party_size=known(2),budget_paid={'state':'unknown'}),
                                      dict(pace={'state':'uncertain','note':'用户未定 / undecided'}))
        raw, chain = envelopes(snapshot, revisions)
        formal = formal_v1.check_constraints(raw, chain, **BOUNDS)
        original = v1.check_constraints(snapshot, revisions)
        self.assertEqual(formal.report, original.report)
        self.assertEqual(formal.version, 'FEASIBILITY@1.0')
        self.assertEqual(formal.input_profile, formal_v1.INPUT_PROFILE)
        self.assertEqual(formal.status, 'UNKNOWN')
        evidence = [e for check in formal.report.checks for e in check.evidence if e.path=='party_size']
        self.assertTrue(evidence)
        self.assertTrue(all(e.original_input==revisions[0].original_input for e in evidence))

    def test_missing_chain_wrong_version_duplicate_keys_or_bounds_refuse(self):
        snapshot, revisions = history(dict(party_size=known(2)),dict(pace=known('relaxed')))
        raw, chain = envelopes(snapshot, revisions)
        for candidate in (chain[:1], tuple(reversed(chain))):
            if len(candidate)!=len(chain):
                with self.assertRaises(InvalidInput):formal_v1.check_constraints(raw,candidate,**BOUNDS)
            else:self.assertEqual(formal_v1.check_constraints(raw,candidate,**BOUNDS).status,'INVALID')
        for bad in (raw.replace(b'NEEDS-snapshot.1',b'NEEDS-snapshot.2'),b'{"version":1,"version":1}'):
            with self.assertRaises(InvalidInput):formal_v1.check_constraints(bad,chain,**BOUNDS)
        with self.assertRaises(InvalidInput):formal_v1.check_constraints(raw,chain,max_revisions=1,max_input_bytes=1048576)
        with self.assertRaises(InvalidInput):formal_v1.check_constraints(raw,chain,max_revisions=8,max_input_bytes=1)

    def test_later_revision_codec_does_not_validate_retained_fields_by_itself(self):
        snapshot, revisions = history(dict(party_size=known(2)),dict(pace=known('relaxed')))
        altered=json.loads(snapshot.content);altered['party_size']=known(3)
        content=json.dumps(altered,ensure_ascii=False,separators=(',',':')).encode()
        # The codec validates the changed pace, while the canonical engine must
        # still refuse invented retained party_size using the full original chain.
        snapshot=replace(snapshot,content=content)
        revisions=(revisions[0],replace(revisions[1],content=content))
        raw,chain=envelopes(snapshot,revisions)
        self.assertEqual(formal_v1.check_constraints(raw,chain,**BOUNDS).status,'INVALID')

    def test_formal_place_route_reuses_protection_and_conditional_only_estimate(self):
        args=fixture()
        raw,chain=envelopes(args['before'],args['revisions'])
        result_raw=encode_result(args.pop('result'),evidence_kind='synthetic')
        args.pop('before');args.pop('revisions')
        candidate=args.pop('candidate');window=args.pop('window')
        result=formal_v1.check_route(raw,chain,candidate,window,result_raw,**args,**BOUNDS)
        self.assertEqual(result.status,'UNKNOWN')
        self.assertEqual(result.report.conditional_relation,'required_exceeds_gap')
        self.assertTrue(any(c.code=='ROUTE_EVIDENCE_UNVERIFIED' for c in result.report.checks))
        self.assertTrue(all(c.zh and c.en for c in result.report.checks))

    def test_formal_edit_uses_same_original_scope_protection(self):
        snapshot,revisions=history(dict(party_size=known(2)))
        raw,chain=envelopes(snapshot,revisions)
        candidate=Candidate(snapshot.needs_id,snapshot.version,snapshot.content)
        result=formal_v1.check_edit_scope(raw,chain,candidate,
            selected_fields=frozenset(),selected_item_ids=frozenset(),**BOUNDS)
        original=v1.check_edit_scope(snapshot,revisions,candidate,
            selected_fields=frozenset(),selected_item_ids=frozenset())
        self.assertEqual(result.report,original.report)

    def test_original_formal_evidence_label_and_recording_ref_not_promoted(self):
        for kind in ('recorded_replay','live_provider','unverified_bytes'):
            args=fixture()
            raw,chain=envelopes(args.pop('before'),args.pop('revisions'))
            value=json.loads(encode_result(args.pop('result'),evidence_kind='synthetic'))
            value['source']['evidence_kind']=kind
            value['source']['recording_ref']='synthetic-recording-1' if kind=='recorded_replay' else None
            result_raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
            candidate=args.pop('candidate');window=args.pop('window')
            result=formal_v1.check_route(raw,chain,candidate,window,result_raw,**args,**BOUNDS)
            self.assertEqual(result.status,'UNKNOWN')
            self.assertEqual(result.place_original,result_raw)
            self.assertEqual(result.report.result.source.evidence,'unverified_bytes')
            self.assertEqual(json.loads(result.place_original)['source']['evidence_kind'],kind)
            self.assertEqual(json.loads(result.place_original)['source']['recording_ref'],value['source']['recording_ref'])

    def test_formal_stale_or_wrong_request_source_never_becomes_zero_duration(self):
        for mutate in ('stale','wrong_binding'):
            args=fixture()
            raw,chain=envelopes(args.pop('before'),args.pop('revisions'))
            value=json.loads(encode_result(args.pop('result'),evidence_kind='synthetic'))
            if mutate=='wrong_binding':value['source']['binding_digest']='f'*64
            else:
                from datetime import timedelta
                args['as_of'] += timedelta(seconds=120)
            result_raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
            candidate=args.pop('candidate');window=args.pop('window')
            result=formal_v1.check_route(raw,chain,candidate,window,result_raw,**args,**BOUNDS)
            self.assertEqual(result.status,'UNKNOWN')
            self.assertIsNone(result.report.conditional_relation)
            code='ROUTE_SOURCE_STALE' if mutate=='stale' else 'ROUTE_SOURCE_BINDING_UNKNOWN'
            self.assertTrue(any(c.code==code for c in result.report.checks))
