"""Source2 planning consumes the actual explicitly accepted current Trip context."""
from copy import deepcopy
from hashlib import sha256
import json
from cj_trip.domain import packed,Denied
from cj_trip.planning_context import read_current,current_in_tx,protect_model
from cj_trip.needs_source import NeedsSourceAuthority
from cj_trip.needs_plan import build as build_original,parse_model,_build
from .needs_publisher import NeedsDraftPublisher


class ContextSource(NeedsSourceAuthority):
    def __init__(self,*args,trip_repository,**kwargs):
        super().__init__(*args,**kwargs);self.trip_repository=trip_repository;self.contexts={}
    def capture(self,binding):
        source=super().capture(binding);value=json.loads(source.raw)
        self.contexts[binding]=read_current(self.trip_repository,value['needs_scope'],value['needs_id'])
        return source


class ContextPublisher(NeedsDraftPublisher):
    def model_messages(self,binding,text,capture,messages):
        before,_=capture.records();context=self.source.contexts.get(binding)
        return list(messages)+[dict(role='system',content=json.dumps(dict(version='TRIP-source-input.2',
            needs_id=before.needs_id,revision=before.version,fields=before.fields,
            current_trip=None if context is None else dict(trip_id=context.trip.trip_id,version=context.trip.version,
                content=json.loads(context.trip.content),proposed_fields=json.loads(context.proposed))),ensure_ascii=False,separators=(',',':')))]
    def build_plan(self,raw,capture):
        context=self.source.contexts.get(capture.binding)
        if context is None:return build_original(raw,capture)
        value=parse_model(raw);document=dict(content_version='structured.2',title=value['title'],items=value['items'],sources=[])
        protect_model(context.trip,document)
        before,_=capture.records();source_items={item['item_id']:item for item in before.fields.get('fixed_items',[])}
        # Local Trip fixed intent is checked above and retained in Trip content;
        # it is not silently written back into canonical NEEDS declarations.
        current_items={item['id']:item for item in json.loads(context.trip.content)['items']}
        prior_fields=json.loads(context.proposed)
        adopted={item['item_id']:item for item in prior_fields.get('fixed_items',[]) if item['item_id'] not in source_items}
        projection=deepcopy(value)
        for item in projection['items']:
            original=current_items.get(item['id'])
            source=source_items.get(item['id'])
            expected=(original['source_category'] if original is not None and original['text']==item['text']
                      else 'user_provided' if source is not None and source['description']==item['text'] else 'unknown')
            if item['source_category']!=expected:raise Denied('model changed current source classification')
            if source is not None:
                item['fixed']=deepcopy(source['locked'])
                item['source_category']='user_provided' if item['text']==source['description'] else 'unknown'
            elif item['id'] in adopted:
                item['fixed']=deepcopy(adopted[item['id']]['locked'])
        original_content,candidate,report=_build(packed(projection),capture,adopted)
        return packed(document),candidate,report
    def check_trip_context(self,cur,binding,capture):
        value=json.loads(capture.raw)
        current=current_in_tx(cur,self.repository,value['needs_scope'],value['needs_id'])
        if current!=self.source.contexts.get(binding):raise Denied('captured current Trip changed before publication')
    def retain_trip_context(self,cur,proposal,binding,capture):
        context=self.source.contexts.get(binding)
        expected=(None,None,None) if context is None else (context.trip.trip_id,context.trip.version,context.trip.content)
        cur.execute('SELECT trip_id,trip_version,original_content FROM cj_trip_needs_plan_context WHERE scope=%s AND proposal_id=%s',
            (self.repository.scope,proposal.proposal_id))
        prior=cur.fetchone()
        if prior is not None:
            retained=(prior[0],prior[1],None if prior[2] is None else bytes(prior[2]))
            if retained!=expected:raise Denied('original immutable Trip planning context changed')
            return
        cur.execute('INSERT INTO cj_trip_needs_plan_context(scope,proposal_id,trip_id,trip_version,original_content) VALUES(%s,%s,%s,%s,%s)',
            (self.repository.scope,proposal.proposal_id,*expected))


def publisher(database,checker,message_context,token_supplier,scope):
    import os
    from cj_api.composition import CompositionUnavailable
    from cj_api.local_app import ISSUER,AUDIENCE,scope_for
    from cj_api.local_needs import protected_reader
    from cj_needs.revision_lease import RevisionLease
    from cj_message.needs_binding import needs_scope_for
    from cj_trip.postgres import Repository
    from cj_agent.draft import trip_scope_for
    if os.environ.get('CJ_ENV')!='local':raise CompositionUnavailable('explicit local context publisher required')
    def resolve(principal):
        owner=scope_for(principal.issuer,principal.subject)
        return lambda:database.connect(owner),owner,needs_scope_for(owner)
    repository=Repository(lambda:database.connect(scope),trip_scope_for(scope),structured=True)
    source=ContextSource(protected_reader(database,checker),message_context,
        RevisionLease(checker,resolve,environment='local',issuer=ISSUER,audience=AUDIENCE),
        token_supplier,max_revisions=128,max_bytes=4000000,trip_repository=repository)
    return ContextPublisher(repository,source)
