"""Metadata-only roadbook enrichment attempts in the original HK authorization journal.

M4 item 18 (JT 2026-11-25): each new place gets at most two flash calls (Chinese, then English);
per owner and Beijing day at most DAILY_PLACES new places in at most DAILY_BOOKS requests; a
¥300 sublimit inside the shared model stop line, with new calls refused (cache only) from 80%.
"""

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from uuid import UUID
from zoneinfo import ZoneInfo

from .authorization_budget import (
    CNY_SCALE, LIMITS, MODEL_INPUT_PRICE, MODEL_OUTPUT_PRICE, MODEL_STOP_CNY, MODEL_TOTAL_CNY, TOOL_STOP_CNY,
    TOOL_TOTAL_CNY, authorization_usage, canonical,
)
from .metered_exit import BudgetUnknown
from .sublimits import scope_hash


SERVICE = 'roadbook.1'
SUBLIMIT = 300 * CNY_SCALE
CACHE_ONLY_PERCENT = 80
DAILY_PLACES = 60
DAILY_BOOKS = 5
MAX_REQUEST_PLACES = 20
CALLS_PER_PLACE = 2
MODEL = 'qwen3.8-flash'
MAX_OUTPUT_TOKENS = 1000  # M4 item 18: one call writes at most 1000 tokens
BEIJING = ZoneInfo('Asia/Shanghai')

# Gaode facts for the same places (M4 item 18, JT 2026-11-25 「单独计次，上限 2000 次」): per place one
# identification (text search, or detail when the POI id is known) and one around search; counted
# separately from entry 3's place allowance, at most M4_AMAP_LIMIT calls, sharing only the ¥500 tool cash.
AMAP_SERVICE = 'amap-roadbook.1'
AMAP_ORIGIN = 'https://restapi.amap.com'
AMAP_OPERATIONS = {'text': '/v5/place/text', 'detail': '/v5/place/detail', 'around': '/v5/place/around'}
AMAP_SLOTS = {'text': 'identify', 'detail': 'identify', 'around': 'around'}
M4_AMAP_LIMIT = 2000
AMAP_DAILY_CALLS = DAILY_PLACES * 2


class RoadbookLimit(BudgetUnknown):
    """A known daily or monetary limit denied the call before dispatch."""


class RoadbookDuplicate(BudgetUnknown):
    """The original request or supplier call already has a durable intent."""


def roadbook_price(receipt):
    """List-price fixed-point charge from bounded supplier metadata, or None to keep the hold."""
    if (receipt.get('service') != SERVICE or receipt.get('region') != 'cn-beijing'
            or receipt.get('model_id') != MODEL):
        return None
    usage = receipt.get('usage')
    if type(usage) is not dict or set(usage) != {'input_tokens', 'output_tokens'}:
        return None
    source, output = usage['input_tokens'], usage['output_tokens']
    if (type(source) is not int or type(output) is not int
            or not 1 <= source <= 32_768 or not 0 <= output <= MAX_OUTPUT_TOKENS):
        return None
    return source * MODEL_INPUT_PRICE + output * MODEL_OUTPUT_PRICE


def cache_only_limit():
    return SUBLIMIT * CACHE_ONLY_PERCENT // 100


@dataclass(frozen=True)
class RoadbookOperation:
    owner: str
    request: UUID
    day: date
    places: int

    @property
    def prefix(self):
        return f'{SERVICE}:{self.owner}:{self.request.hex}:'

    def identifier(self, stage):
        return f'{self.prefix}{stage:02d}'

    def metadata(self, stage):
        return dict(service=SERVICE, region='cn-beijing', day=self.day.isoformat(),
                    places=self.places, stage=stage, model_id=MODEL)


def _charged(db):
    reserve = LIMITS['model'][1] * CNY_SCALE
    charged = 0
    for state, raw in db.execute("SELECT state,receipt FROM attempt WHERE id GLOB ?", (SERVICE + ':*',)):
        price = roadbook_price(json.loads(raw)) if state == 'RECEIVED' else None
        charged += reserve if price is None else price
    return charged


def _refusal(db):
    """Why one more reserved call would not fit, or None."""
    reserve = LIMITS['model'][1] * CNY_SCALE
    counts, estimates, holds = authorization_usage(db)
    if (counts['model'] >= LIMITS['model'][0]
            or estimates['model'] + holds['model'] + reserve > min(MODEL_STOP_CNY, MODEL_TOTAL_CNY) * CNY_SCALE):
        return 'shared model authorization ceiling'
    if _charged(db) + reserve > cache_only_limit():
        return 'roadbook authorization ceiling (cache only)'
    return None


class RoadbookBudget:
    def __init__(self, authorization):
        self.authorization = authorization

    def operation(self, scope, request, places):
        """One request that enriches `places` uncached places (cached places cost nothing)."""
        self.authorization.check_date()
        if type(places) is not int or not 1 <= places <= MAX_REQUEST_PLACES:
            raise BudgetUnknown('invalid roadbook request size')
        now = self.authorization.clock().astimezone(BEIJING)
        return RoadbookOperation(scope_hash(scope), request, now.date(), places)

    def cache_only(self):
        """True when one more call would not fit: 80% of the sublimit, or the shared model stop line.

        A read-only look at one journal snapshot (no write lock, no control-file write), like
        `sublimits.read`. Callers treat any exception here as cache only; `begin` checks again
        under the ledger lock."""
        self.authorization.check_date()
        with self.authorization.connect() as db:
            db.execute('BEGIN')
            self.authorization.require_producer(db)
            return _refusal(db) is not None

    def begin(self, operation, stage):
        """Reserve exactly one upstream call, using the parent ledger lock."""
        self.authorization.check_date()
        if type(stage) is not int or not 0 <= stage < operation.places * CALLS_PER_PLACE:
            raise BudgetUnknown('invalid roadbook stage')
        attempt = operation.identifier(stage)
        metadata = operation.metadata(stage)
        with self.authorization.mutation() as db:
            if db.execute('SELECT 1 FROM attempt WHERE id=?', (attempt,)).fetchone():
                raise RoadbookDuplicate('original roadbook call already reserved')
            if stage == 0:
                books, places = db.execute(
                    """SELECT count(*),COALESCE(sum(json_extract(receipt,'$.places')),0) FROM attempt
                    WHERE id GLOB ? AND json_extract(receipt,'$.day')=?""",
                    (f'{SERVICE}:{operation.owner}:*:00', operation.day.isoformat()),
                ).fetchone()
                if books >= DAILY_BOOKS or places + operation.places > DAILY_PLACES:
                    raise RoadbookLimit('daily roadbook allowance exhausted')
            elif not db.execute(
                "SELECT 1 FROM attempt WHERE id=? AND state='RECEIVED'",
                (operation.identifier(stage - 1),),
            ).fetchone():
                raise BudgetUnknown('original roadbook stage not settled')
            refusal = _refusal(db)
            if refusal is not None:
                raise RoadbookLimit(refusal)
            record = canonical(metadata)
            db.execute("INSERT INTO attempt VALUES(?,?,?,'INTENT',?)",
                       (attempt, 'model', hashlib.sha256(record).hexdigest(), record.decode()))

    def finish(self, operation, stage, supplier_id, usage):
        receipt = dict(operation.metadata(stage),
                       receipt_sha256=hashlib.sha256(f'{MODEL}:{supplier_id}'.encode()).hexdigest(),
                       usage=usage)
        if roadbook_price(receipt) is None:
            raise BudgetUnknown('roadbook billing receipt unavailable')
        self.authorization.finish(operation.identifier(stage), receipt)


class RoadbookPlaceBudget:
    """Gaode calls for roadbook places in the original HK journal, like Nearby and hotel search."""

    def __init__(self, authorization):
        self.authorization = authorization

    def begin(self, scope, request_id: UUID, index, operation):
        if (operation not in AMAP_OPERATIONS or type(index) is not int
                or not 0 <= index < MAX_REQUEST_PLACES):
            raise BudgetUnknown('unknown roadbook place step')
        self.authorization.check_date()
        owner = scope_hash(scope)
        day = self.authorization.clock().astimezone(BEIJING).date().isoformat()
        place = f'{AMAP_SERVICE}:{owner}:{request_id.hex}:{index:02d}'
        identifier = f'{place}:{operation}:{day}'
        witness = dict(service=AMAP_SERVICE, operation=operation, day=day,
                       endpoint=AMAP_ORIGIN + AMAP_OPERATIONS[operation])
        raw = canonical(witness)
        with self.authorization.mutation() as db:
            steps = db.execute('SELECT id FROM attempt WHERE id GLOB ?', (f'{place}:*',)).fetchall()
            if any(AMAP_SLOTS.get(row[0].split(':')[4]) == AMAP_SLOTS[operation] for row in steps):
                raise RoadbookDuplicate('original roadbook place step already recorded')
            total, daily = db.execute(
                """SELECT count(*), sum(CASE WHEN id GLOB ? THEN 1 ELSE 0 END)
                   FROM attempt WHERE kind='place' AND id GLOB ?""",
                (f'{AMAP_SERVICE}:{owner}:*:*:*:{day}', f'{AMAP_SERVICE}:*'),
            ).fetchone()
            if total >= M4_AMAP_LIMIT:
                raise RoadbookLimit('roadbook Gaode call count exhausted for M4')
            if (daily or 0) >= AMAP_DAILY_CALLS:
                raise RoadbookLimit('daily roadbook Gaode call count exhausted')
            _, estimates, holds = authorization_usage(db)
            used = sum(estimates[kind] + holds[kind] for kind in LIMITS if kind != 'model')
            if used + LIMITS['place'][1] * CNY_SCALE > min(TOOL_STOP_CNY, TOOL_TOTAL_CNY) * CNY_SCALE:
                raise RoadbookLimit('original Gaode cash allowance exhausted')
            # Keep the original HK ledger's NULL receipt contract for unsettled attempts.
            db.execute("INSERT INTO attempt VALUES(?,?,?,'INTENT',NULL)",
                       (identifier, 'place', hashlib.sha256(raw).hexdigest()))
        return identifier, witness

    def finish(self, attempt, raw):
        identifier, witness = attempt
        self.authorization.finish(identifier, dict(witness, response_sha256=hashlib.sha256(raw).hexdigest()))
