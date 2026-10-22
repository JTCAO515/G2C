"""Version-1 ledger codec; corruption must never reset accounting state."""
from dataclasses import asdict
import json
import math
from .core import Attempt, Command, Config, Ledger, Receipt, Run, integer, label


class CorruptLedger(Exception):
    pass


def fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        raise CorruptLedger('invalid ledger shape')


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise CorruptLedger('invalid clock')


def decode(value):
    try:
        fields(value, 'config attempts runs last_clock')
        cfg = Config(**value['config'])
        if type(value['attempts']) is not dict or type(value['runs']) is not dict:
            raise CorruptLedger('invalid maps')
        clock = value['last_clock']
        if clock is not None:
            number(clock)
        runs = {}
        for key, r in value['runs'].items():
            label(key)
            fields(r, 'started steps tools cancelled')
            number(r['started']); integer(r['steps']); integer(r['tools'])
            if type(r['cancelled']) is not bool or clock is None or r['started'] > clock:
                raise CorruptLedger('invalid run')
            runs[key] = Run(**r)
        attempts, receipts = {}, set()
        for key, a in value['attempts'].items():
            fields(a, 'command state receipt cancelled exceeded')
            command = Command(**a['command'])
            receipt = Receipt(**a['receipt']) if a['receipt'] is not None else None
            if (key != command.attempt_id or command.run_id not in runs or
                    a['state'] not in ('reserved', 'unknown', 'released', 'settled') or
                    type(a['cancelled']) is not bool or type(a['exceeded']) is not bool):
                raise CorruptLedger('invalid attempt')
            if (a['state'] == 'settled') != (receipt is not None):
                raise CorruptLedger('invalid settlement')
            exceeded = bool(receipt and (receipt.actual > command.reserve or
                                         receipt.output > command.output_limit))
            run = runs[command.run_id]
            if a['exceeded'] != exceeded or (exceeded and not run.cancelled):
                raise CorruptLedger('invalid overrun')
            if a['cancelled'] and not run.cancelled:
                raise CorruptLedger('invalid cancellation')
            if a['state'] == 'released' and not a['cancelled']:
                raise CorruptLedger('invalid release')
            if receipt:
                if (receipt.attempt_id != key or receipt.unit != cfg.unit or
                        receipt.receipt_id in receipts):
                    raise CorruptLedger('invalid receipt binding')
                receipts.add(receipt.receipt_id)
            attempts[key] = Attempt(command, a['state'], receipt, a['cancelled'], exceeded)
        for key, run in runs.items():
            commands = [a.command for a in attempts.values() if a.command.run_id == key]
            if (run.steps != len(commands) or
                    run.tools != sum(c.kind == 'tool' for c in commands) or
                    not 1 <= run.steps <= cfg.max_steps or run.tools > cfg.max_tools):
                raise CorruptLedger('invalid run counters')
        if attempts and clock is None:
            raise CorruptLedger('missing clock')
        return Ledger(cfg, attempts, runs, clock)
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        raise CorruptLedger('invalid ledger') from None
    except Exception as exc:
        if isinstance(exc, CorruptLedger):
            raise
        raise CorruptLedger('invalid ledger') from None


def encode(ledger):
    data = asdict(ledger)
    decode(data)  # Validate before persistence as well as on read.
    return json.dumps(data, allow_nan=False, separators=(',', ':'))
