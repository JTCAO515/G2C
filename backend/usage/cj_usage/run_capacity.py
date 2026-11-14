"""Read-only original base-profile capacity; reserve remains authoritative."""
from cj_strict_json import compact
from .core import Meter

VERSION='G2C-original-run-capacity.1'


def encode_capacity(ledger,run_id):
    run=ledger.runs.get(run_id)
    cancelled=run is not None and run.cancelled
    def remaining(maximum,used):return 0 if cancelled else max(0,maximum-used)
    value=dict(version=VERSION,limits_source='original-account-config.1',
        admission='NOT_GRANTED',unit=ledger.config.unit,output_unit='Python str characters',
        period_start=ledger.config.period_start,period_end=ledger.config.period_end,
        run_state='not_started'if run is None else'cancelled'if cancelled else'open',
        remaining_calls=max(0,ledger.config.budget-Meter.exposure(ledger)),
        remaining_steps=remaining(ledger.config.max_steps,0 if run is None else run.steps),
        remaining_tools=remaining(ledger.config.max_tools,0 if run is None else run.tools),
        remaining_output=remaining(ledger.config.max_output,Meter.output_exposure(ledger,run_id)))
    return compact(value,ensure_ascii=True,sort_keys=True)
