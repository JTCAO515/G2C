"""Uncollected date checks stay unknown and bind the whole candidate, not just days."""
from copy import copy,deepcopy
from types import SimpleNamespace
import unittest

from cj_api.local_lio_rich_checks import RichUncollectedChecks
from cj_needs.revision_lease import LeaseUnavailable
from test_lio_pipeline_document import build


class Source:
    def __init__(self,start):self.capture=SimpleNamespace(basis=SimpleNamespace(day_count=3,start_date=start))
    def check(self,binding,capture):
        if binding!='current' or capture is not self.capture:raise LeaseUnavailable('current original only')


class UncollectedPlanChecks(unittest.TestCase):
    def case(self,start=None):
        source=Source(start);reader=RichUncollectedChecks(source)
        document,_,_,_=build(3,start)
        capture=reader.capture('current',source.capture,document)
        return reader,source,document,capture

    def test_dated_and_undated_use_only_their_explicit_uncollected_states(self):
        for start,state,reason in ((None,'not_checked','date_not_set'),
                                   ('2026-12-01','unknown','date_evidence_not_collected')):
            reader,source,document,capture=self.case(start)
            self.assertTrue(all(row['state']==state and row['reason']==reason and not row['evidence_refs']
                for row in capture.checks))
            self.assertEqual(document['date_checks'],capture.checks)
            with reader.hold('current',capture,SimpleNamespace(check=lambda _:None))as check:check(document)

    def test_code_checks_bind_places_clocks_and_full_candidate_after_assembly(self):
        reader,source,document,capture=self.case('2026-12-01')
        for mutate in (lambda d:d['items'][0]['schedule']['start']['time'].update(value='10:00'),
                       lambda d:d['items'][0]['place'].update(name_zh='另一个地点'),
                       lambda d:d.update(title='Another plan'),
                       lambda d:d['date_checks'][0].update(state='clear')):
            altered=deepcopy(document);mutate(altered)
            with reader.hold('current',capture,SimpleNamespace(check=lambda _:None))as check:
                with self.assertRaises(LeaseUnavailable):check(altered)
        with reader.hold('current',capture,SimpleNamespace(check=lambda _:None))as check:check(document)

    def test_unissued_copied_and_superseded_checks_do_not_authorize_a_candidate(self):
        reader,source,document,capture=self.case()
        with reader.hold('current',copy(capture),SimpleNamespace(check=lambda _:None))as check:
            with self.assertRaises(LeaseUnavailable):check(document)
        reader.capture('current',source.capture,document)
        with reader.hold('current',capture,SimpleNamespace(check=lambda _:None))as check:
            with self.assertRaises(LeaseUnavailable):check(document)

    def test_calendar_must_equal_the_actual_source_basis_without_date_defaults(self):
        reader,source,document,capture=self.case('2026-12-01')
        for mutate in (lambda d:d['calendar'].update(start_date='2026-12-02'),
                       lambda d:d['days'][1].update(date='2026-12-30')):
            altered=deepcopy(document);mutate(altered)
            with self.assertRaises(LeaseUnavailable):reader.capture('current',source.capture,altered)
        source=Source(None)
        with self.assertRaises(LeaseUnavailable):RichUncollectedChecks(source).capture('current',source.capture,document)

    def test_closed_or_withdrawn_original_frame_is_not_recovered_by_equal_data(self):
        reader,source,document,capture=self.case()
        with reader.hold('current',capture,SimpleNamespace(check=lambda _:None))as check:check(document)
        with self.assertRaises(LeaseUnavailable):check(document)
        source.capture=copy(source.capture)
        with reader.hold('current',capture,SimpleNamespace(check=lambda _:None))as check:
            with self.assertRaises(LeaseUnavailable):check(document)


if __name__=='__main__':unittest.main()
