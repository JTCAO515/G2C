"""Nearby and reverse-geocoding limits in the existing HK Gaode cash journal."""

import hashlib
from uuid import UUID
from zoneinfo import ZoneInfo

from .authorization_budget import (
    CNY_SCALE, LIMITS, TOOL_STOP_CNY, TOOL_TOTAL_CNY, authorization_usage, canonical,
)
from .metered_exit import BudgetUnknown
from .sublimits import scope_hash


SERVICE = 'amap-nearby.1'
ORIGIN = 'https://restapi.amap.com'
OPERATIONS = {
    'convert': '/v3/assistant/coordinate/convert',
    'search': '/v5/place/around',
    'reverse': '/v3/geocode/regeo',
}
DAILY_ACCOUNT_LIMIT = 100
M4_OPERATION_LIMIT = 3000
SHANGHAI = ZoneInfo('Asia/Shanghai')


class NearbyLimit(BudgetUnknown):
    """An approved Nearby count or the original shared cash limit denied a call."""


class NearbyDuplicate(BudgetUnknown):
    """The original operation already has an intent and cannot be repeated."""


class NearbyBudget:
    def __init__(self, authorization):
        self.authorization = authorization

    def begin(self, scope, request_id: UUID, operation):
        self.authorization.check_date()
        owner = scope_hash(scope)
        day = self.authorization.clock().astimezone(SHANGHAI).date().isoformat()
        request = f'{SERVICE}:{owner}:{request_id.hex}:{operation}'
        identifier = f'{request}:{day}'
        witness = dict(service=SERVICE, operation=operation, day=day, endpoint=ORIGIN+OPERATIONS[operation])
        raw = canonical(witness)
        with self.authorization.mutation() as db:
            if db.execute('SELECT 1 FROM attempt WHERE id GLOB ?', (f'{request}:*',)).fetchone():
                raise NearbyDuplicate('original Nearby attempt already recorded')
            total, daily = db.execute(
                """SELECT count(*), sum(CASE WHEN id GLOB ? THEN 1 ELSE 0 END)
                   FROM attempt WHERE kind='place' AND id GLOB ?""",
                (f'{SERVICE}:{owner}:*:{operation}:{day}', f'{SERVICE}:*:{operation}:*'),
            ).fetchone()
            if total >= M4_OPERATION_LIMIT or (daily or 0) >= DAILY_ACCOUNT_LIMIT:
                raise NearbyLimit('Nearby operation count exhausted')
            _, estimates, holds = authorization_usage(db)
            used = sum(estimates[kind]+holds[kind] for kind in LIMITS if kind != 'model')
            if used + LIMITS['place'][1]*CNY_SCALE > min(TOOL_STOP_CNY, TOOL_TOTAL_CNY)*CNY_SCALE:
                raise NearbyLimit('original Gaode cash allowance exhausted')
            # Keep the original HK ledger's NULL receipt contract for unsettled attempts.
            db.execute("INSERT INTO attempt VALUES(?,?,?,'INTENT',NULL)",
                       (identifier, 'place', hashlib.sha256(raw).hexdigest()))
        return identifier, witness

    def finish(self, attempt, raw):
        identifier, witness = attempt
        self.authorization.finish(identifier, dict(witness, response_sha256=hashlib.sha256(raw).hexdigest()))
