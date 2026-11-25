"""Metro station surroundings limits in the existing HK Gaode cash journal (M4 entry 12 item 5, #1450).

JT 2026-11-25 (#1577): the area search around a bundled metro station, never the device's position. Counted
on its own: at most 40 Gaode calls per account per day and at most 2,000 in all; it stays out of Nearby's
100/3000 and shares only the ¥500 tool cash total. One search is one Gaode call.
"""

import hashlib
from uuid import UUID
from zoneinfo import ZoneInfo

from .authorization_budget import (
    CNY_SCALE, LIMITS, TOOL_STOP_CNY, TOOL_TOTAL_CNY, authorization_usage, canonical,
)
from .metered_exit import BudgetUnknown
from .sublimits import scope_hash


SERVICE = 'amap-metro-nearby.1'
ORIGIN = 'https://restapi.amap.com'
OPERATIONS = {'search': '/v5/place/around'}
DAILY_ACCOUNT_LIMIT = 40
M4_OPERATION_LIMIT = 2000
SHANGHAI = ZoneInfo('Asia/Shanghai')


class MetroNearbyLimit(BudgetUnknown):
    """The approved station surroundings count or the shared cash limit denied a call."""


class MetroNearbyDuplicate(BudgetUnknown):
    """The original search already has an intent and cannot be repeated."""


class MetroNearbyBudget:
    def __init__(self, authorization):
        self.authorization = authorization

    def begin(self, scope, request_id: UUID, operation):
        if operation not in OPERATIONS:
            raise BudgetUnknown('unknown station surroundings step')
        self.authorization.check_date()
        owner = scope_hash(scope)
        day = self.authorization.clock().astimezone(SHANGHAI).date().isoformat()
        request = f'{SERVICE}:{owner}:{request_id.hex}:{operation}'
        identifier = f'{request}:{day}'
        witness = dict(service=SERVICE, operation=operation, day=day, endpoint=ORIGIN+OPERATIONS[operation])
        raw = canonical(witness)
        with self.authorization.mutation() as db:
            if db.execute('SELECT 1 FROM attempt WHERE id GLOB ?', (f'{request}:*',)).fetchone():
                raise MetroNearbyDuplicate('original station surroundings attempt already recorded')
            total, daily = db.execute(
                """SELECT count(*), sum(CASE WHEN id GLOB ? THEN 1 ELSE 0 END)
                   FROM attempt WHERE kind='place' AND id GLOB ?""",
                (f'{SERVICE}:{owner}:*:*:{day}', f'{SERVICE}:*'),
            ).fetchone()
            if total >= M4_OPERATION_LIMIT:
                raise MetroNearbyLimit('station surroundings call count exhausted for M4')
            if (daily or 0) >= DAILY_ACCOUNT_LIMIT:
                raise MetroNearbyLimit('daily station surroundings call count exhausted')
            _, estimates, holds = authorization_usage(db)
            used = sum(estimates[kind]+holds[kind] for kind in LIMITS if kind != 'model')
            if used + LIMITS['place'][1]*CNY_SCALE > min(TOOL_STOP_CNY, TOOL_TOTAL_CNY)*CNY_SCALE:
                raise MetroNearbyLimit('original Gaode cash allowance exhausted')
            # Keep the original HK ledger's NULL receipt contract for unsettled attempts.
            db.execute("INSERT INTO attempt VALUES(?,?,?,'INTENT',NULL)",
                       (identifier, 'place', hashlib.sha256(raw).hexdigest()))
        return identifier, witness

    def finish(self, attempt, raw):
        identifier, witness = attempt
        self.authorization.finish(identifier, dict(witness, response_sha256=hashlib.sha256(raw).hexdigest()))
