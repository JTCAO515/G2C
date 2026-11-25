"""Hotel search limits in the existing HK Gaode cash journal (M4 entry 12 item 3, #1511).

JT 2026-11-25 (#1508, #1523, revised in #1534): at most 50 hotel searches per account per day and at most
three Gaode calls per search. Like Nearby, hotel calls have their own count (at most 3000 Gaode calls), stay
out of entry 3's place allowance and share only the ¥500 tool cash total.
"""

import hashlib
from uuid import UUID
from zoneinfo import ZoneInfo

from .authorization_budget import (
    CNY_SCALE, LIMITS, TOOL_STOP_CNY, TOOL_TOTAL_CNY, authorization_usage, canonical,
)
from .metered_exit import BudgetUnknown
from .sublimits import scope_hash


SERVICE = 'amap-hotel.1'
ORIGIN = 'https://restapi.amap.com'
# One name per step, so a search's two around-searches never collide in the per-request deduplication.
OPERATIONS = {
    'geocode': '/v3/geocode/geo',
    'hotels_around': '/v5/place/around',
    'hotels_text': '/v5/place/text',
    'subway': '/v5/place/around',
}
DAILY_SEARCH_LIMIT = 50
CALLS_PER_SEARCH = 3
M4_OPERATION_LIMIT = 3000
SHANGHAI = ZoneInfo('Asia/Shanghai')


class HotelLimit(BudgetUnknown):
    """The approved hotel search or call count, or the shared cash limit, denied a call."""


class HotelDuplicate(BudgetUnknown):
    """The original step of this search already has an intent and cannot be repeated."""


class HotelBudget:
    def __init__(self, authorization):
        self.authorization = authorization

    def begin(self, scope, request_id: UUID, operation):
        if operation not in OPERATIONS:
            raise BudgetUnknown('unknown hotel search step')
        self.authorization.check_date()
        owner = scope_hash(scope)
        day = self.authorization.clock().astimezone(SHANGHAI).date().isoformat()
        request = f'{SERVICE}:{owner}:{request_id.hex}'
        identifier = f'{request}:{operation}:{day}'
        witness = dict(service=SERVICE, operation=operation, day=day, endpoint=ORIGIN+OPERATIONS[operation])
        raw = canonical(witness)
        with self.authorization.mutation() as db:
            steps = db.execute('SELECT id FROM attempt WHERE id GLOB ?', (f'{request}:*',)).fetchall()
            if any(row[0].split(':')[3] == operation for row in steps):
                raise HotelDuplicate('original hotel search step already recorded')
            if len(steps) >= CALLS_PER_SEARCH:
                raise HotelLimit('hotel search call count exhausted')
            if not steps:
                today = db.execute('SELECT id FROM attempt WHERE id GLOB ?',
                                   (f'{SERVICE}:{owner}:*:*:{day}',)).fetchall()
                if len({row[0].split(':')[2] for row in today}) >= DAILY_SEARCH_LIMIT:
                    raise HotelLimit('daily hotel search count exhausted')
            total = db.execute("SELECT count(*) FROM attempt WHERE kind='place' AND id GLOB ?",
                               (f'{SERVICE}:*',)).fetchone()[0]
            if total >= M4_OPERATION_LIMIT:
                raise HotelLimit('hotel search call count exhausted for M4')
            _, estimates, holds = authorization_usage(db)
            used = sum(estimates[kind]+holds[kind] for kind in LIMITS if kind != 'model')
            if used + LIMITS['place'][1]*CNY_SCALE > min(TOOL_STOP_CNY, TOOL_TOTAL_CNY)*CNY_SCALE:
                raise HotelLimit('original Gaode cash allowance exhausted')
            # Keep the original HK ledger's NULL receipt contract for unsettled attempts.
            db.execute("INSERT INTO attempt VALUES(?,?,?,'INTENT',NULL)",
                       (identifier, 'place', hashlib.sha256(raw).hexdigest()))
        return identifier, witness

    def finish(self, attempt, raw):
        identifier, witness = attempt
        self.authorization.finish(identifier, dict(witness, response_sha256=hashlib.sha256(raw).hexdigest()))
