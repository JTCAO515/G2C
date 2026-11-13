"""Trusted composition for context.2, opt-in by the new exploration consumer.

No old Lio factory installs this component. WP4 supplies the selected native4
consumer and its ordinary-text extraction; this stage grants no Trip/Memory write.
"""
from hashlib import sha256
from dataclasses import dataclass
import json

from cj_message.domain import Command
from cj_memory.runtime import RuntimeDenied
from cj_agent.provider import ProviderUnknown
from cj_needs.domain import InvalidInput

from .lio_exploration_profile import (CONTEXT, Original, merge, parse_updates,default_proposals,
    decode_context, restore_context, memory_prefill, snapshot)


@dataclass(frozen=True)
class ProfileView:
    originals:tuple
    references:tuple
    profile:dict
    signature:str


class ProfileContext:
    def __init__(self, database):
        self.database = database

    def capture(self, binding):
        with self.database.connect(binding.scope) as db:
            previous = db.execute('SELECT e.value FROM cj_run_event e '
                'JOIN cj_message_receipt m USING(scope,run_id) JOIN cj_run_record r USING(scope,run_id) '
                "WHERE m.scope=%s AND m.conversation_id=%s AND m.generation=%s AND m.sequence<%s "
                "AND r.status='completed' AND e.kind='effect_committed' AND e.value LIKE %s "
                'ORDER BY m.sequence DESC,e.sequence DESC LIMIT 1',
                (binding.scope,binding.conversation_id,binding.generation,binding.message_sequence,CONTEXT+'%')).fetchone()
            try:
                stored = None if previous is None else decode_context(previous[0].removeprefix(CONTEXT))
            except InvalidInput as error:
                raise RuntimeDenied('stored profile context unavailable') from error
            # The event is stored data. Restore validates its complete shape and
            # source evidence below; only use bounded identifiers to fetch anchors.
            mids = set()
            if stored is not None:
                mids = {source.message_id for fact in stored.factors
                        if fact.state in ('known','not_needed','inferred') for source in fact.sources
                        if source.kind == 'message'}
            rows = db.execute('SELECT message_id,sequence,raw_input,input_sha256,run_id '
                'FROM cj_message_receipt WHERE scope=%s AND conversation_id=%s AND generation=%s '
                'AND sequence<=%s AND (sequence>%s OR message_id=ANY(%s)) ORDER BY sequence',
                (binding.scope,binding.conversation_id,binding.generation,binding.message_sequence,
                 binding.message_sequence-8,list(mids))).fetchall()
        originals=[];refs=[]
        for mid,sequence,original,digest,run_id in rows:
            if original is None or sha256(bytes(original)).hexdigest() != digest:
                raise RuntimeDenied('original profile message unavailable')
            command = Command.parse_original(bytes(original))
            if command.message_id != mid or command.conversation_id != binding.conversation_id:
                raise RuntimeDenied('profile original binding changed')
            if mid == binding.message_id and (sequence,run_id) != (binding.message_sequence,binding.run_id):
                raise RuntimeDenied('profile current RUN binding changed')
            originals.append(Original(mid,sequence,json.loads(command.raw)['text']))
            refs.append(dict(conversation_id=binding.conversation_id,generation=binding.generation,
                             message_id=mid,sequence=sequence,input_sha256=digest))
        if not originals or originals[-1].message_id != binding.message_id or not mids <= {o.message_id for o in originals}:
            raise RuntimeDenied('protected original profile source unavailable')
        return tuple(originals),tuple(refs),stored

    def read(self,worker,binding):
        originals,refs,previous=self.capture(binding)
        try:profile={} if previous is None else restore_context(previous,originals,worker.memory_run)
        except InvalidInput as error:raise RuntimeDenied('stored profile source unavailable') from error
        profile=merge(profile,(),memory_prefill(worker.memory_run))
        encoded=json.dumps(dict(refs=refs,profile=snapshot(profile)),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
        return ProfileView(originals,refs,profile,sha256(encoded).hexdigest())

    def accept(self, worker, binding, state, raw_updates,*,expected=None,plan_now=False):
        """Accept one extraction, under original RUN/Memory/reference fences.

        This uses the existing effect transaction and its actual Memory hold;
        source rechecks execute inside that same transaction before the RUN event
        commits. An UNKNOWN is reconciled by the original worker, not replayed.
        """
        view=self.read(worker,binding)
        if expected is not None and expected.signature!=view.signature:
            raise RuntimeDenied('profile source changed during model preparation')
        originals,refs,profile=view.originals,view.references,view.profile
        if worker.memory_run is not None:
            # Retain erasure fences for every genuine original referenced by the
            # profile, including anchors older than the recent-message window.
            worker.memory_run = worker.history_adapter.before_model(binding,worker.memory_run,
                [dict(role='user',content=o.text) for o in originals],
                'Sourced internal planning profile data; no publication authority.',message_refs=refs)
        try:
            updates = parse_updates(raw_updates,originals)
        except InvalidInput as error:
            raise ProviderUnknown('sourced profile extraction unavailable') from error
        profile = merge(profile,updates,memory_prefill(worker.memory_run))
        if plan_now:
            profile.update({fact.key:fact for fact in default_proposals(profile,originals[-1])})

        def check_sources(cursor):
            # This is a boundary check on mutable persisted originals, not an
            # internal type recheck. The existing RUN/Memory/reference locks are
            # held by _event until this effect commits.
            for ref in refs:
                cursor.execute('SELECT raw_input,input_sha256 FROM cj_message_receipt '
                    'WHERE scope=%s AND conversation_id=%s AND generation=%s AND message_id=%s '
                    'AND sequence=%s FOR SHARE', (binding.scope,ref['conversation_id'],ref['generation'],
                    ref['message_id'],ref['sequence']))
                current = cursor.fetchone()
                if (current is None or current[0] is None or current[1] != ref['input_sha256'] or
                        sha256(bytes(current[0])).hexdigest() != ref['input_sha256']):
                    raise RuntimeDenied('profile original source changed before publication')
        epoch=None if worker.memory_run is None else worker.memory_run.snapshot.epoch
        event = CONTEXT+json.dumps(snapshot(profile,memory_epoch=epoch),ensure_ascii=False,separators=(',',':'))
        state = worker._event(binding,state,'effect_committed',event,mutation=check_sources)
        return state,profile
