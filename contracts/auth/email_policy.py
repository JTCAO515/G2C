"""Synthetic email-policy extension; no SDK, passwords, links or production imports."""
from model import server_decision


def email_business_decision(authority, owners, caller_owner=None):
    """Email status is a trusted synthetic server result, never a client flag."""
    decision = server_decision(authority, owners, caller_owner)
    if decision in ('identity_unknown', 'identity_denied', 'session_denied'):
        return decision
    status = authority.get('email_status', 'unknown')
    if status == 'unverified':
        return 'email_verification_required'
    if status != 'verified':
        return 'email_verification_unknown'
    return decision  # verified email does not bypass invitation or resource checks


def flow_outcome(flow, event):
    """Semantic samples only: events require trusted SDK/host attribution later.

    No event here authorizes model use. Cancellation closes this local flow; the
    actual host must invalidate its callback binding, not revoke unrelated sessions.
    """
    allowed = {
        'registration': {'accepted': 'verification_pending'},
        'verification': {'confirmed': 'reauthentication_required',
                         'link_invalid': 'verification_link_invalid'},
        'login': {'unverified': 'email_verification_required',
                  'rejected': 'login_rejected', 'session_invalid': 'session_invalid'},
        'recovery_request': {'accepted': 'recovery_request_acknowledged'},
        'password_reset': {'confirmed': 'password_changed_reauthenticate',
                           'link_invalid': 'recovery_link_invalid'},
    }
    if flow not in allowed:
        raise ValueError('unsupported synthetic flow')
    if event == 'network_unknown':
        return 'outcome_unknown'
    if event == 'user_cancelled':
        return 'cancelled_locally'
    try:
        return allowed[flow][event]
    except KeyError:
        raise ValueError('unsupported synthetic event') from None
