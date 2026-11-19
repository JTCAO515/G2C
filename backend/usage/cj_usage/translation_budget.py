"""Metadata-only translation attempts in the original HK authorization journal."""

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from uuid import UUID
from zoneinfo import ZoneInfo

from .authorization_budget import (
    CNY_SCALE, LIMITS, MODEL_STOP_CNY, MODEL_TOTAL_CNY, authorization_usage, canonical,
)
from .metered_exit import BudgetUnknown
from .sublimits import scope_hash


SERVICE = 'translation.1'
SUBLIMIT = 300 * CNY_SCALE
DAILY_LIMITS = {'text': 300, 'speech': 1800, 'image': 50}
TEXT_MODEL = 'qwen-mt-flash'
SPEECH_MODEL = 'qwen3-asr-flash'
IMAGE_MODEL = 'qwen-vl-ocr'
FIRST_MODEL = {'text': TEXT_MODEL, 'speech': SPEECH_MODEL, 'image': IMAGE_MODEL}
BEIJING = ZoneInfo('Asia/Shanghai')


class TranslationLimit(BudgetUnknown):
    """A known daily or monetary limit denied the call before dispatch."""


class TranslationDuplicate(BudgetUnknown):
    """The original request or supplier call already has a durable intent."""


def translation_price(receipt):
    """Derive list-price fixed-point charges from bounded supplier metadata."""
    if receipt.get('service') != SERVICE or receipt.get('region') != 'cn-beijing':
        return None
    model = receipt.get('model_id')
    usage = receipt.get('usage')
    if type(usage) is not dict:
        return None
    if model == SPEECH_MODEL:
        seconds = usage.get('seconds')
        if set(usage) != {'seconds'} or type(seconds) is not int or not 1 <= seconds <= 60:
            return None
        return 2200 * seconds
    if model not in (TEXT_MODEL, IMAGE_MODEL) or set(usage) != {'input_tokens', 'output_tokens'}:
        return None
    source, output = usage['input_tokens'], usage['output_tokens']
    if (type(source) is not int or type(output) is not int
            or not 1 <= source <= 32_768 or not 0 <= output <= 4096):
        return None
    if model == TEXT_MODEL:
        return 7 * source + (39 * output + 1) // 2
    return 3 * source + 5 * output


@dataclass(frozen=True)
class TranslationOperation:
    owner: str
    request: UUID
    day: date
    modality: str
    units: int

    @property
    def prefix(self):
        return f'{SERVICE}:{self.owner}:{self.request.hex}:'

    def identifier(self, stage):
        return f'{self.prefix}{stage:02d}'

    def metadata(self, stage, model):
        return dict(service=SERVICE, region='cn-beijing', day=self.day.isoformat(),
                    modality=self.modality, units=self.units, stage=stage, model_id=model)


class TranslationBudget:
    def __init__(self, authorization):
        self.authorization = authorization

    def operation(self, scope, request, modality, units):
        self.authorization.check_date()
        now = self.authorization.clock().astimezone(BEIJING)
        return TranslationOperation(scope_hash(scope), request, now.date(), modality, units)

    def begin(self, operation, stage, model):
        """Reserve exactly one upstream call, using the parent ledger lock."""
        self.authorization.check_date()
        if (not 0 <= stage <= 24 or operation.modality not in DAILY_LIMITS
                or not 1 <= operation.units <= DAILY_LIMITS[operation.modality]
                or (model != (FIRST_MODEL[operation.modality] if stage == 0 else TEXT_MODEL))
                or (stage and operation.modality == 'text')):
            raise BudgetUnknown('invalid translation stage')
        attempt = operation.identifier(stage)
        metadata = operation.metadata(stage, model)
        reserve = LIMITS['model'][1] * CNY_SCALE
        with self.authorization.mutation() as db:
            if db.execute('SELECT 1 FROM attempt WHERE id=?', (attempt,)).fetchone():
                raise TranslationDuplicate('original translation already reserved')
            if stage == 0:
                used = db.execute(
                    """SELECT COALESCE(sum(json_extract(receipt,'$.units')),0) FROM attempt
                    WHERE id GLOB ? AND json_extract(receipt,'$.day')=?
                    AND json_extract(receipt,'$.modality')=?""",
                    (f'{SERVICE}:{operation.owner}:*:00', operation.day.isoformat(), operation.modality),
                ).fetchone()[0]
                if used + operation.units > DAILY_LIMITS[operation.modality]:
                    raise TranslationLimit('daily translation allowance exhausted')
            elif not db.execute(
                "SELECT 1 FROM attempt WHERE id=? AND state='RECEIVED'",
                (operation.identifier(stage - 1),),
            ).fetchone():
                raise BudgetUnknown('original translation stage not settled')
            counts, estimates, holds = authorization_usage(db)
            if (counts['model'] >= LIMITS['model'][0]
                    or estimates['model'] + holds['model'] + reserve > min(MODEL_STOP_CNY, MODEL_TOTAL_CNY) * CNY_SCALE):
                raise TranslationLimit('shared model authorization ceiling')
            charged = 0
            for state, raw in db.execute("SELECT state,receipt FROM attempt WHERE id GLOB ?", (SERVICE + ':*',)):
                price = translation_price(json.loads(raw)) if state == 'RECEIVED' else None
                charged += reserve if price is None else price
            if charged + reserve > SUBLIMIT:
                raise TranslationLimit('translation authorization ceiling')
            record = canonical(metadata)
            db.execute("INSERT INTO attempt VALUES(?,?,?,'INTENT',?)",
                       (attempt, 'model', hashlib.sha256(record).hexdigest(), record.decode()))

    def finish(self, operation, stage, model, supplier_id, usage):
        receipt = dict(operation.metadata(stage, model),
                       receipt_sha256=hashlib.sha256(f'{model}:{supplier_id}'.encode()).hexdigest(),
                       usage=usage)
        if translation_price(receipt) is None:
            raise BudgetUnknown('translation billing receipt unavailable')
        self.authorization.finish(operation.identifier(stage), receipt)
