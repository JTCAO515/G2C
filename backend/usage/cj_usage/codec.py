"""Explicit v1/v2 ledger codecs; neither corruption nor upgrade resets usage."""
from dataclasses import asdict
import json
import math
from .core import (Attempt, Command, Config, Ledger, LedgerV2, Receipt, Run,
                   integer, label, NATIVE4_PROFILE, run_limits, model_attempts,
                   NATIVE4_TOOL_OUTPUT, NATIVE4_MODEL_OUTPUT, NATIVE4_AMAP_CALLS,
                   provider_attempts)


class CorruptLedger(Exception):
    pass


def fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        raise CorruptLedger('invalid ledger shape')


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise CorruptLedger('invalid clock')


def decode_stored(version, value):
    if type(version) is not int or version not in (1,2):
        raise CorruptLedger('unsupported ledger version')
    return decode(value) if version == 1 else decode_v2(value)


def decode(value):
    return _decode(value, version=1)


def decode_v2(value):
    return _decode(value, version=2)


def _decode(value, *, version):
    try:
        fields(value, 'config attempts runs last_clock' + (' run_profiles attempt_providers' if version == 2 else ''))
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
        profiles = {} if version == 1 else value['run_profiles']
        if (type(profiles) is not dict or any(key not in runs or profile != NATIVE4_PROFILE
                for key, profile in profiles.items()) or (profiles and cfg.unit != 'provider_call')):
            raise CorruptLedger('invalid run profiles')
        providers = {} if version == 1 else value['attempt_providers']
        expected_providers = {key for key,a in attempts.items() if a.command.run_id in profiles}
        if (type(providers) is not dict or providers.keys() != expected_providers or any(
                provider not in (('amap', 'local') if attempts[key].command.kind == 'tool' else ('model',))
                for key,provider in providers.items())):
            raise CorruptLedger('invalid registered attempt providers')
        ledger = (Ledger(cfg, attempts, runs, clock) if version == 1 else
                  LedgerV2(cfg, attempts, runs, clock, dict(profiles), dict(providers)))
        for key, run in runs.items():
            limits = run_limits(ledger, key)
            commands = [a.command for a in attempts.values() if a.command.run_id == key]
            if (run.steps != len(commands) or
                    run.tools != sum(c.kind == 'tool' for c in commands) or
                    not 1 <= run.steps <= limits.steps or run.tools > limits.tools or
                    (limits.models is not None and model_attempts(ledger, key) > limits.models) or
                    (key in profiles and (provider_attempts(ledger, key, 'amap') > NATIVE4_AMAP_CALLS
                     or provider_attempts(ledger, key, 'local') > cfg.max_tools)) or
                    (key in profiles and any(c.output_limit > (NATIVE4_TOOL_OUTPUT if c.kind == 'tool' else NATIVE4_MODEL_OUTPUT) for c in commands))):
                raise CorruptLedger('invalid run counters')
        if attempts and clock is None:
            raise CorruptLedger('missing clock')
        return ledger
    except (TypeError, ValueError, KeyError, OverflowError):
        raise CorruptLedger('invalid ledger') from None
    except Exception as exc:
        if isinstance(exc, CorruptLedger):
            raise
        raise CorruptLedger('invalid ledger') from None


def encode(ledger):
    if isinstance(ledger, LedgerV2):
        raise CorruptLedger('version-2 run profile requires version-2 persistence')
    data = asdict(ledger)
    decode(data)  # Validate before persistence as well as on read.
    return json.dumps(data, allow_nan=False, separators=(',', ':'))


def encode_v2(ledger):
    if not isinstance(ledger, LedgerV2):
        raise CorruptLedger('version-2 ledger required')
    data = asdict(ledger)
    decode_v2(data)
    return json.dumps(data, allow_nan=False, separators=(',', ':'))
