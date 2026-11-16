"""Issued code checks for an actually held native4 undated calendar.

This first bridge does not collect dated weather/opening facts and cannot serve
a dated document. It never turns unknown/known provider data into a clear check.
The combined C source holder remains the authority for original/profile/provider
eligibility; these records are only the code-produced calendar result.
"""
from contextlib import contextmanager
from dataclasses import dataclass,InitVar
from hashlib import sha256
from datetime import date,timedelta
import json
import threading

from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.domain import packed

_FACTORY=object()


@dataclass(frozen=True,slots=True,repr=False)
class UndatedChecksCapture:
    _source:object
    _calendar:bytes
    _checks:bytes
    _factory:InitVar[object]

    def __post_init__(self,_factory):
        if _factory is not _FACTORY:raise LeaseUnavailable('issued code checks required')

    @property
    def checks(self):return json.loads(self._checks)

    @property
    def records(self):
        return [dict(provider='checks',kind=row['kind'],reference='undated:'+sha256(self._calendar).hexdigest()+':'+row['kind'],
                     sha256=sha256(packed(row)).hexdigest(),payload=row)for row in self.checks]


def _calendar(document):
    return packed(dict(calendar=document['calendar'],days=[dict(day_index=day['day_index'],
        **({'date':day['date']}if'date'in day else{}))for day in document['days']]))


class RichUndatedChecks:
    def __init__(self,source):
        self.source=source
        self._issued=None

    def capture(self,binding,source_capture,document):
        """Compile inside the actual combined source frame, without new IO."""
        self.source.check(binding,source_capture)
        basis=source_capture.basis
        if (basis.start_date is not None or document['calendar']!={'state':'undated'}
                or [day['day_index']for day in document['days']]!=list(range(1,basis.day_count+1))
                or any('date'in day for day in document['days'])):
            raise LeaseUnavailable('code checks require the actual complete undated calendar')
        rows=[dict(kind=kind,state='not_checked',day_indices=list(range(1,basis.day_count+1)),item_ids=[],
                   reason='date_not_set',evidence_refs=[])for kind in ('weather','day_opening')]
        result=UndatedChecksCapture(source_capture,_calendar(document),packed(rows),_factory=_FACTORY)
        self._issued=result
        return result

    @contextmanager
    def hold(self,binding,capture,message):
        active=True;thread=threading.get_ident()
        def check(document):
            if not active or threading.get_ident()!=thread or capture is not self._issued:
                raise LeaseUnavailable('same active issued code checks required')
            message.check(binding)
            self.source.check(binding,capture._source)
            if _calendar(document)!=capture._calendar or packed(document['date_checks'])!=capture._checks:
                raise LeaseUnavailable('final candidate differs from captured code checks')
        try:yield check
        finally:active=False


def _plan_body(document):
    return packed({key:value for key,value in document.items()if key!='date_checks'})


@dataclass(frozen=True,slots=True,repr=False)
class UncollectedChecksCapture:
    _source:object
    _body:bytes
    _checks:bytes
    _factory:InitVar[object]

    def __post_init__(self,_factory):
        if _factory is not _FACTORY:raise LeaseUnavailable('issued code checks required')

    @property
    def checks(self):return json.loads(self._checks)

    @property
    def records(self):
        return [dict(provider='checks',kind=row['kind'],reference='uncollected:'+sha256(self._body).hexdigest()+':'+row['kind'],
            sha256=sha256(packed(row)).hexdigest(),payload=row)for row in self.checks]


class RichUncollectedChecks:
    """Explicit missing-evidence states, never a clear weather/opening verdict.

    This binds the complete actual candidate and its original calendar. It
    collects no H/weather facts; those consumers require their own qualified
    readers/holds. This component alone is not G9 or a production pipeline PASS.
    """
    def __init__(self,source):
        self.source=source
        self._issued=None

    def capture(self,binding,source_capture,document):
        self.source.check(binding,source_capture)
        basis=source_capture.basis
        indices=list(range(1,basis.day_count+1))
        if basis.start_date is None:
            calendar=dict(state='undated');days=[dict(day_index=day)for day in indices]
            state,reason='not_checked','date_not_set'
        else:
            first=date.fromisoformat(basis.start_date)
            calendar=dict(state='dated',start_date=basis.start_date)
            days=[dict(day_index=day,date=(first+timedelta(days=day-1)).isoformat())for day in indices]
            state,reason='unknown','date_evidence_not_collected'
        if _calendar(document)!=packed(dict(calendar=calendar,days=days)):
            raise LeaseUnavailable('code checks require the complete actual source calendar')
        rows=[dict(kind=kind,state=state,day_indices=indices,item_ids=[],reason=reason,evidence_refs=[])
            for kind in ('weather','day_opening')]
        result=UncollectedChecksCapture(source_capture,_plan_body(document),packed(rows),_factory=_FACTORY)
        self._issued=result
        return result

    @contextmanager
    def hold(self,binding,capture,message):
        active=True;thread=threading.get_ident()
        def check(document):
            if not active or threading.get_ident()!=thread or capture is not self._issued:
                raise LeaseUnavailable('same active issued plan checks required')
            message.check(binding)
            self.source.check(binding,capture._source)
            if _plan_body(document)!=capture._body or packed(document['date_checks'])!=capture._checks:
                raise LeaseUnavailable('final candidate differs from captured plan checks')
        try:yield check
        finally:active=False
