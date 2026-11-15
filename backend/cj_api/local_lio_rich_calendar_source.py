"""Explicit rich calendar compiler using the existing active MESSAGE frame."""
from contextlib import contextmanager
from datetime import date
import threading

from cj_draft.rich_calendar_source import RichCalendarBasis
from cj_message.demo_dialogue import LIO_VERSION_V4
from cj_message.lio_wire import exploration_original_protocol,original_protocol
from cj_needs.revision_lease import LeaseUnavailable
from cj_run.core import Binding
from cj_trip.domain import packed

from .local_lio_calendar_source import LioCalendarSource,Original,HeldCalendar


class RichCalendarSource(LioCalendarSource):
    sidecar_version='LIO-fixed-day-bindings.2'

    def _basis(self,day_count,start_date,sidecar):
        return RichCalendarBasis(day_count,start_date,sidecar)

    def _protocol(self,cursor,binding,stored):
        row=cursor.execute('SELECT lio_wire_protocol FROM cj_message_receipt WHERE scope=%s AND message_id=%s AND run_id=%s',
            (binding.scope,binding.message_id,binding.run_id)).fetchone()
        # This tag only selects a strict original-byte validator, not a grant.
        selected=exploration_original_protocol if row is not None and row[0]==LIO_VERSION_V4 else original_protocol
        return selected(cursor,binding,stored)

    def _source(self,binding,mid,message):
        message.check(binding)
        source=message.source_original(mid)
        stored=source.stored;r=stored.receipt
        actual=Binding(binding.scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
        with self.database.connect(binding.scope)as db:
            protocol=self._protocol(db.cursor(),actual,stored)
            row=db.execute('SELECT demo_question_day FROM cj_message_receipt WHERE scope=%s AND conversation_id=%s '
                'AND generation=%s AND message_id=%s AND run_id=%s AND sequence=%s',
                (actual.scope,actual.conversation_id,actual.generation,mid,actual.run_id,actual.message_sequence)).fetchone()
        if row is None or row[0]is None:raise LeaseUnavailable('original rich calendar clock unavailable')
        reference=source.reference.public_value()
        result={key:reference[key]for key in ('conversation_id','generation','message_id','run_id','sequence',
                                            'input_sha256','message_version')}
        result['lio_protocol']=protocol
        message.check(binding)
        return Original(actual,stored,packed(result),row[0])

    def _read(self,binding,mid):
        return self._source(binding,mid,self._capturing_message)

    def capture(self,binding,message,needs):
        # The base compiler reuses fixed/day/date rules. Only this explicit
        # reader uses root4/sidecar2; old codecs and consumers still refuse4.
        self._capturing_message=message
        try:return super().capture(binding,message,needs)
        finally:self._capturing_message=None

    @contextmanager
    def hold(self,binding,basis,message):
        captured=self.originals
        if basis is not self.basis:raise LeaseUnavailable('issued rich calendar basis required')
        active=True;thread=threading.get_ident()
        def check():
            if not active or threading.get_ident()!=thread or basis is not self.basis or self.originals is not captured:
                raise LeaseUnavailable('rich calendar source frame expired or changed')
            message.check(binding)
            for original in captured:
                if self._source(binding,original.binding.message_id,message)!=original:
                    raise LeaseUnavailable('captured rich calendar original changed')
            message.check(binding)
        held=_RichHeldCalendar(self,check)
        try:
            held.check();yield held;held.check()
        finally:active=False


class _RichHeldCalendar(HeldCalendar):
    def __init__(self,source,check):
        super().__init__(source,())
        self._check=check
    def check(self):self._check()
    def _original(self,reference):
        self.check()
        return super()._original(reference)
    def fixed_day_indices(self,item_id,reference,quote):
        self.check()
        return super().fixed_day_indices(item_id,reference,quote)
