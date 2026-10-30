"""Read-only original-source proof for manual-unbound; never a NEEDS lease.

All reads use the existing Trip transaction and installed canonical owner GUCs.
No B locks, source writes, fallback or permission changes belong here.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

from .domain import Action, Denied, Proposal, Trip

MAX_VERSIONS=128
MAX_BYTES=4_000_000


@dataclass(frozen=True,repr=False)
class ManualOrigin:
    message_scope: str
    trip_scope: str
    needs_scope: str | None

    def check(self,cur,trip):
        cur.execute("SELECT current_setting('cj.message_scope',true),current_setting('cj.trip_scope',true),current_setting('cj.needs_scope',true)")
        actual=cur.fetchone()
        if (actual[:2]!=(self.message_scope,self.trip_scope) or self.needs_scope is None
                or actual[2]!=self.needs_scope):
            raise Denied('original source configuration unavailable')
        current=trip;consumed=0
        for _ in range(MAX_VERSIONS):
            cur.execute('SELECT r.action_id,r.proposal_id,r.candidate_hash,r.original_input,p.trip_id,p.expected_version,p.basis_version,p.expires_at,p.content,p.candidate_hash,p.status '
                'FROM cj_trip_receipt r JOIN cj_trip_proposal p ON (p.scope,p.proposal_id)=(r.scope,r.proposal_id) '
                "WHERE r.scope=%s AND r.trip_id=%s AND r.committed_version=%s AND r.kind='accept'",
                (self.trip_scope,current.trip_id,current.version))
            rows=cur.fetchall()
            if len(rows)!=1:raise Denied('original Trip chain unavailable')
            row=rows[0];content=bytes(row[8]);original_action=bytes(row[3])
            consumed+=len(content)+len(original_action)
            if consumed>MAX_BYTES:raise Denied('original source bound exceeded')
            proposal=Proposal(row[1],row[4],row[5],row[6],row[7],content)
            digest=proposal.digest(self.trip_scope)
            if (row[10]!='accepted' or row[2]!=digest or row[9]!=digest
                    or proposal.trip_id!=current.trip_id or proposal.expected_version+1!=current.version
                    or content!=current.content):
                raise Denied('original Trip chain mismatch')
            try:action=Action(*json.loads(original_action))
            except (TypeError,ValueError):raise Denied('original action invalid') from None
            if (action.raw()!=original_action or action.action_id!=row[0] or action.kind!='accept'
                    or action.proposal_id!=proposal.proposal_id or action.candidate_hash!=digest):
                raise Denied('original action association mismatch')
            if proposal.basis_version.startswith('run-'):
                if proposal.expected_version!=0:raise Denied('original RUN version unavailable')
                self._run(cur,proposal)
                return
            from .manual import ManualEdit,ManualSave,prepare
            from .initialization import Initialization,InitializationSave,initialize,BASIS
            if proposal.basis_version=='manual-unbound.1':
                parse,build,parse_save=ManualEdit.parse,prepare,ManualSave.parse
            elif proposal.basis_version==BASIS:
                parse,build,parse_save=Initialization.parse,initialize,InitializationSave.parse
            else:raise Denied('original source kind unavailable')
            cur.execute('SELECT request_id,original_input,original_content,diff FROM cj_trip_manual_basis WHERE scope=%s AND proposal_id=%s',
                        (self.trip_scope,proposal.proposal_id))
            basis=cur.fetchone()
            if basis is None:raise Denied('original manual basis unavailable')
            raw,before,diff=map(bytes,basis[1:])
            consumed+=len(raw)+len(before)+len(diff)
            if consumed>MAX_BYTES:raise Denied('original source bound exceeded')
            edit=parse(raw)
            previous=Trip(current.trip_id,proposal.expected_version,before)
            candidate=build(previous,edit)
            if (edit.request_id!=basis[0] or proposal.proposal_id!='manual.'+sha256(raw).hexdigest()
                    or candidate.content!=content or candidate.diff!=diff):
                raise Denied('original manual basis mismatch')
            cur.execute('SELECT original_input,original_action,proposal_id FROM cj_trip_manual_intent WHERE scope=%s AND action_id=%s',
                        (self.trip_scope,action.action_id))
            intent=cur.fetchone()
            if intent is None or bytes(intent[1])!=original_action or intent[2]!=proposal.proposal_id:
                raise Denied('original manual intent unavailable')
            saved=parse_save(bytes(intent[0]))
            if (saved.action_id,saved.proposal_id,saved.candidate_hash)!=(action.action_id,proposal.proposal_id,digest):
                raise Denied('original manual intent mismatch')
            current=previous
        raise Denied('original version chain bound exceeded')

    def _run(self,cur,proposal):
        run_id=proposal.basis_version[4:]
        from cj_agent.draft import proposal_id_for
        if proposal.proposal_id!=proposal_id_for(run_id) or proposal.trip_id!='trip-'+run_id:
            raise Denied('original RUN proposal association unavailable')
        cur.execute('SELECT r.message_id,r.conversation_id,r.generation,r.message_sequence,m.raw_input,m.input_sha256 '
            'FROM cj_run_record r JOIN cj_message_receipt m ON '
            '(m.scope,m.run_id,m.message_id,m.conversation_id,m.generation,m.sequence)='
            '(r.scope,r.run_id,r.message_id,r.conversation_id,r.generation,r.message_sequence) '
            'WHERE r.scope=%s AND r.run_id=%s',(self.message_scope,run_id))
        row=cur.fetchone()
        if row is None:raise Denied('original RUN message unavailable')
        raw=bytes(row[4])
        if sha256(raw).hexdigest()!=row[5]:raise Denied('original message integrity unavailable')
        from cj_message.domain import Command
        document=json.loads(raw)
        command=Command.parse_v2(raw) if document.get('version')=='MESSAGE-send.2' else Command.parse_stored(raw)
        if (command.message_id!=row[0] or command.conversation_id!=row[1]
                or document['creation_intent']!='consider_trip'
                or command.expected_generation is not None and
                   (command.expected_generation!=row[2] or command.expected_sequence!=row[3]-1)):
            raise Denied('original planning message mismatch')
        if command.needs_reference is not None:
            raise Denied('NEEDS-bound manual publication not configured')
        cur.execute("SELECT value FROM cj_run_event WHERE scope=%s AND run_id=%s AND kind='effect_committed'",
                    (self.message_scope,run_id))
        if cur.fetchall()!=[('trip_proposal:'+proposal.proposal_id,)]:raise Denied('original publication effect unavailable')
        # Current protected/registered profiles require their genuine NEEDS
        # producer/lease. Absence of a hidden or incomplete binding is no fallback.
        for table in ('cj_message_needs_binding','cj_local_run_protection'):
            if table=='cj_message_needs_binding':
                cur.execute('SELECT 1 FROM cj_message_needs_binding WHERE message_scope=%s',
                            (self.message_scope,))
            else:cur.execute('SELECT 1 FROM cj_local_run_protection WHERE scope=%s',(self.message_scope,))
            if cur.fetchone() is not None:raise Denied('protected NEEDS source unavailable for manual-unbound')
