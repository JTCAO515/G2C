"""Explicit local source-bound publisher composition, using B frozen authority."""
from cj_api.local_needs import protected_reader
from cj_api.local_app import ISSUER,AUDIENCE,scope_for
from cj_message.needs_binding import needs_scope_for
from cj_needs.revision_lease import RevisionLease
from cj_trip.needs_source import NeedsSourceAuthority
from cj_trip.postgres import Repository
from cj_agent.draft import trip_scope_for
from .needs_publisher import NeedsDraftPublisher


def publisher(database,checker,message_context,token_supplier,scope):
    def resolve(principal):
        owner=scope_for(principal.issuer,principal.subject)
        return lambda:database.connect(owner),owner,needs_scope_for(owner)
    source=NeedsSourceAuthority(protected_reader(database,checker),message_context,
        RevisionLease(checker,resolve,environment='local',issuer=ISSUER,audience=AUDIENCE),
        token_supplier,max_revisions=128,max_bytes=4_000_000)
    repository=Repository(lambda:database.connect(scope),trip_scope_for(scope),structured=True)
    return NeedsDraftPublisher(repository,source)
