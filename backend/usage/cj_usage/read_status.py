"""Minimal historical status; internal values, not an HTTP schema."""
from dataclasses import dataclass, asdict
import json
from .core import Attempt, Config

class ReadUnavailable(Exception):
    pass

COPY = {
    'reserved': ('Usage is reserved; no execution is confirmed.', '已预留用量，尚未确认执行。'),
    'unknown': ('Usage is awaiting reconciliation. Do not resend.', '用量待核对，请勿重新发送。'),
    'released': ('Unstarted work was cancelled; its reservation was released.', '未开始的任务已取消，预留用量已释放。'),
    'settled': ('Usage was recorded from the original receipt.', '已根据原回执记录用量。'),
}

@dataclass(frozen=True)
class AttemptStatus:
    attempt_id: str
    operation_id: str
    run_id: str
    status: str
    unit: str
    reserved_units: int
    confirmed_units: int | None
    confirmed_output: int | None
    receipt_id: str | None
    cancelled: bool
    exceeded: bool
    message_en: str
    message_zh: str

def status_of(attempt, config):
    if type(attempt) is not Attempt or type(config) is not Config or attempt.state not in COPY:
        raise ReadUnavailable('invalid status source')
    c, receipt = attempt.command, attempt.receipt
    en, zh = COPY[attempt.state]
    return AttemptStatus(c.attempt_id, c.operation_id, c.run_id, attempt.state,
        config.unit, c.reserve, receipt.actual if receipt is not None else None,
        receipt.output if receipt is not None else None,
        receipt.receipt_id if receipt is not None else None,
        attempt.cancelled, attempt.exceeded, en, zh)

def encode_status(status):
    if type(status) is not AttemptStatus:
        raise ReadUnavailable('invalid status projection')
    return json.dumps(asdict(status), ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')
