"""Intercity train limits in the existing HK Gaode cash journal (M4 entry 12 item 4, #1520).

JT 2026-11-25 (#1518): AMap cross-city transit planning for the Tools tab's intercity search, at most 30
searches per account per day and at most 1500 AMap calls in all, one call per search. Recorded as entry 3's
`route` kind (that is what transit planning is), but like Nearby and hotel search counted separately: it never
uses the Lio route allowance and shares only the ¥500 tool cash total.
"""

import hashlib
from uuid import UUID
from zoneinfo import ZoneInfo

from .authorization_budget import (
    CNY_SCALE, LIMITS, TOOL_STOP_CNY, TOOL_TOTAL_CNY, authorization_usage, canonical,
)
from .metered_exit import BudgetUnknown
from .sublimits import scope_hash


SERVICE = 'amap-transit.1'
KIND = 'route'
ORIGIN = 'https://restapi.amap.com'
OPERATIONS = {'transit': '/v3/direction/transit/integrated'}
DAILY_SEARCH_LIMIT = 30
M4_OPERATION_LIMIT = 1500
SHANGHAI = ZoneInfo('Asia/Shanghai')


class TransitLimit(BudgetUnknown):
    """The approved daily or M4 train search count, or the shared cash limit, denied a call."""


class TransitDuplicate(BudgetUnknown):
    """This search already has an intent and cannot be repeated."""


class TransitBudget:
    def __init__(self, authorization):
        self.authorization = authorization

    def begin(self, scope, request_id: UUID, operation):
        if operation not in OPERATIONS:
            raise BudgetUnknown('unknown train search step')
        self.authorization.check_date()
        owner = scope_hash(scope)
        day = self.authorization.clock().astimezone(SHANGHAI).date().isoformat()
        request = f'{SERVICE}:{owner}:{request_id.hex}'
        identifier = f'{request}:{operation}:{day}'
        witness = dict(service=SERVICE, operation=operation, day=day, endpoint=ORIGIN + OPERATIONS[operation])
        raw = canonical(witness)
        with self.authorization.mutation() as db:
            if db.execute('SELECT 1 FROM attempt WHERE id GLOB ?', (f'{request}:*',)).fetchone():
                raise TransitDuplicate('original train search already recorded')
            today = db.execute('SELECT count(*) FROM attempt WHERE id GLOB ?',
                               (f'{SERVICE}:{owner}:*:*:{day}',)).fetchone()[0]
            if today >= DAILY_SEARCH_LIMIT:
                raise TransitLimit('daily train search count exhausted')
            total = db.execute('SELECT count(*) FROM attempt WHERE kind=? AND id GLOB ?',
                               (KIND, f'{SERVICE}:*')).fetchone()[0]
            if total >= M4_OPERATION_LIMIT:
                raise TransitLimit('train search call count exhausted for M4')
            _, estimates, holds = authorization_usage(db)
            used = sum(estimates[kind] + holds[kind] for kind in LIMITS if kind != 'model')
            if used + LIMITS[KIND][1] * CNY_SCALE > min(TOOL_STOP_CNY, TOOL_TOTAL_CNY) * CNY_SCALE:
                raise TransitLimit('original Gaode cash allowance exhausted')
            # Keep the original HK ledger's NULL receipt contract for unsettled attempts.
            db.execute("INSERT INTO attempt VALUES(?,?,?,'INTENT',NULL)",
                       (identifier, KIND, hashlib.sha256(raw).hexdigest()))
        return identifier, witness

    def finish(self, attempt, raw):
        identifier, witness = attempt
        self.authorization.finish(identifier, dict(witness, response_sha256=hashlib.sha256(raw).hexdigest()))
