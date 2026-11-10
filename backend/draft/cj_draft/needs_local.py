"""Explicit local source-bound publisher composition, using B frozen authority."""
import os
from cj_api.composition import CompositionUnavailable
from cj_api.local_needs import protected_reader
from cj_api.local_app import ISSUER,AUDIENCE,needs_lease_resolver
from cj_needs.revision_lease import RevisionLease
from cj_trip.needs_source import NeedsSourceAuthority
from cj_trip.postgres import Repository
from cj_agent.draft import trip_scope_for
from .needs_publisher import NeedsDraftPublisher


def publisher(database,checker,message_context,token_supplier,scope):
    if os.environ.get('CJ_ENV')!='local':raise CompositionUnavailable('explicit local source-bound publisher required')
    resolve=needs_lease_resolver(database)
    source=NeedsSourceAuthority(protected_reader(database,checker),message_context,
        RevisionLease(checker,resolve,environment='local',issuer=ISSUER,audience=AUDIENCE),
        token_supplier,max_revisions=128,max_bytes=4_000_000)
    repository=Repository(lambda:database.connect(scope),trip_scope_for(scope),structured=True)
    return NeedsDraftPublisher(repository,source)
