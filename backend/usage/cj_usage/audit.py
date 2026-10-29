"""Minimal original-call audit. No caller text or exception payloads."""
import json
import logging

LOGGER=logging.getLogger('cj_usage.audit')


class AuditUnavailable(Exception):
    pass


def audit_prepared(command,unit):
    # Before reserve and final admission: no log callback can sit in check-to-call.
    event={'run_id':command.run_id,'attempt_id':command.attempt_id,'kind':command.kind,
           'stage':'prepared','unit':unit,'confirmed_units':None,'monetary_cost':'UNKNOWN'}
    try:
        LOGGER.info(json.dumps(event,separators=(',',':')))
    except Exception:
        # A configured audit sink is an IO boundary. Fail before dispatch; never
        # wrap an existing provider/settlement exception or manufacture a receipt.
        raise AuditUnavailable('usage audit unavailable') from None
