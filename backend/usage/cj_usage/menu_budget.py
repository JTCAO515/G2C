"""Metadata-only menu explanation attempts in the original HK authorization journal.

M4 item 19 (JT 2026-11-25): one menu gets at most two flash calls that explain its dishes; per owner and
Beijing day at most DAILY_MENUS explained menus; a ¥100 sublimit inside the shared model stop line, with new
calls refused (cache only) from 80%. Reading the photo is entry 9's image recognition and is recorded by
`translation_budget` (at most 50 images per owner and day), not here. Nothing about the menu or the user is
stored: only the owner hash, the day, the stage and the supplier's token counts.
"""

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from uuid import UUID
from zoneinfo import ZoneInfo

from .authorization_budget import (
    CNY_SCALE, LIMITS, MODEL_INPUT_PRICE, MODEL_OUTPUT_PRICE, MODEL_STOP_CNY, MODEL_TOTAL_CNY,
    authorization_usage, canonical,
)
from .metered_exit import BudgetUnknown
from .sublimits import scope_hash


SERVICE = 'menu.1'
SUBLIMIT = 100 * CNY_SCALE
CACHE_ONLY_PERCENT = 80
DAILY_MENUS = 10
CALLS_PER_MENU = 2
MODEL = 'qwen3.8-flash'
MAX_OUTPUT_TOKENS = 4000
BEIJING = ZoneInfo('Asia/Shanghai')


class MenuLimit(BudgetUnknown):
    """A known daily or monetary limit denied the call before dispatch."""


class MenuDuplicate(BudgetUnknown):
    """The original request or supplier call already has a durable intent."""


def menu_price(receipt):
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
class MenuOperation:
    owner: str
    request: UUID
    day: date
    calls: int

    @property
    def prefix(self):
        return f'{SERVICE}:{self.owner}:{self.request.hex}:'

    def identifier(self, stage):
        return f'{self.prefix}{stage:02d}'

    def metadata(self, stage):
        return dict(service=SERVICE, region='cn-beijing', day=self.day.isoformat(),
                    calls=self.calls, stage=stage, model_id=MODEL)


def _charged(db):
    reserve = LIMITS['model'][1] * CNY_SCALE
    charged = 0
    for state, raw in db.execute("SELECT state,receipt FROM attempt WHERE id GLOB ?", (SERVICE + ':*',)):
        price = menu_price(json.loads(raw)) if state == 'RECEIVED' else None
        charged += reserve if price is None else price
    return charged


def _daily(db, operation):
    """Menus (stage 00 rows) this owner has had explained today."""
    return db.execute(
        "SELECT count(*) FROM attempt WHERE id GLOB ? AND json_extract(receipt,'$.day')=?",
        (f'{SERVICE}:{operation.owner}:*:00', operation.day.isoformat()),
    ).fetchone()[0]


def _refusal(db):
    """Why one more reserved call would not fit, or None."""
    reserve = LIMITS['model'][1] * CNY_SCALE
    counts, estimates, holds = authorization_usage(db)
    if (counts['model'] >= LIMITS['model'][0]
            or estimates['model'] + holds['model'] + reserve > min(MODEL_STOP_CNY, MODEL_TOTAL_CNY) * CNY_SCALE):
        return 'shared model authorization ceiling'
    if _charged(db) + reserve > cache_only_limit():
        return 'menu authorization ceiling (cache only)'
    return None


class MenuBudget:
    def __init__(self, authorization):
        self.authorization = authorization

    def operation(self, scope, request, calls):
        """One menu whose uncached lines need `calls` flash calls (cached lines cost nothing)."""
        self.authorization.check_date()
        if type(calls) is not int or not 1 <= calls <= CALLS_PER_MENU:
            raise BudgetUnknown('invalid menu request size')
        now = self.authorization.clock().astimezone(BEIJING)
        return MenuOperation(scope_hash(scope), request, now.date(), calls)

    def admits(self, scope):
        """Read-only look before the photo is read: could one more menu be explained today?

        `begin` checks again under the ledger lock; this only avoids paying to read a menu that cannot be
        explained. Callers treat any exception here as not admitted."""
        self.authorization.check_date()
        owner = scope_hash(scope)
        day = self.authorization.clock().astimezone(BEIJING).date()
        with self.authorization.connect() as db:
            db.execute('BEGIN')
            self.authorization.require_producer(db)
            if _refusal(db) is not None:
                return False
            return _daily(db, MenuOperation(owner, UUID(int=0), day, 1)) < DAILY_MENUS

    def begin(self, operation, stage):
        """Reserve exactly one upstream call, using the parent ledger lock."""
        self.authorization.check_date()
        if type(stage) is not int or not 0 <= stage < operation.calls:
            raise BudgetUnknown('invalid menu stage')
        attempt = operation.identifier(stage)
        metadata = operation.metadata(stage)
        with self.authorization.mutation() as db:
            if db.execute('SELECT 1 FROM attempt WHERE id=?', (attempt,)).fetchone():
                raise MenuDuplicate('original menu call already reserved')
            if stage == 0:
                if _daily(db, operation) >= DAILY_MENUS:
                    raise MenuLimit('daily menu allowance exhausted')
            elif not db.execute(
                "SELECT 1 FROM attempt WHERE id=? AND state='RECEIVED'",
                (operation.identifier(stage - 1),),
            ).fetchone():
                raise BudgetUnknown('original menu stage not settled')
            refusal = _refusal(db)
            if refusal is not None:
                raise MenuLimit(refusal)
            record = canonical(metadata)
            db.execute("INSERT INTO attempt VALUES(?,?,?,'INTENT',?)",
                       (attempt, 'model', hashlib.sha256(record).hexdigest(), record.decode()))

    def finish(self, operation, stage, supplier_id, usage):
        receipt = dict(operation.metadata(stage),
                       receipt_sha256=hashlib.sha256(f'{MODEL}:{supplier_id}'.encode()).hexdigest(),
                       usage=usage)
        if menu_price(receipt) is None:
            raise BudgetUnknown('menu billing receipt unavailable')
        self.authorization.finish(operation.identifier(stage), receipt)
