"""Unsupported-frame resource order; genuine supported frames use native PG."""
from threading import current_thread

import pytest

from cj_message.travel_reference import MessageContextAuthority,MessageContextLease
from cj_needs.revision_lease import LeaseUnavailable
from cj_run.core import Binding


def test_unsupported_source_rejects_before_formal_refresh_or_new_message_io():
    principal=object();authority=MessageContextAuthority(None,lambda:principal)
    binding=Binding('owner','conversation','generation','message','run',1)
    # Controlled formal-frame state: no data/source reader is manufactured.
    # If either entry point refreshes first, the test fails at the IO boundary.
    lease=object.__new__(MessageContextLease)
    lease._authority=authority;lease._principal=principal;lease._binding=binding
    lease._active=True;lease._thread=current_thread();lease._source_reader=None
    def forbidden_refresh():raise AssertionError('unsupported formal source opened a reverse MESSAGE read')
    lease._refresh=forbidden_refresh
    token=authority._active.set(lease)
    try:
        with pytest.raises(LeaseUnavailable,match='reader unavailable'):
            lease.source_original('earlier')
        with pytest.raises(LeaseUnavailable,match='reader unavailable'):
            authority.active_source_original(binding,'earlier')
    finally:authority._active.reset(token)
