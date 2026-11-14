"""Issued code checks for an actually held native4 undated calendar.

This first bridge does not collect dated weather/opening facts and cannot serve
a dated document. It never turns unknown/known provider data into a clear check.
The combined C source holder remains the authority for original/profile/provider
eligibility; these records are only the code-produced calendar result.
"""
from contextlib import contextmanager
from dataclasses import dataclass,InitVar
from hashlib import sha256
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
