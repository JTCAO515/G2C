"""Read-only original base-profile capacity; reserve remains authoritative."""
import json
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


def encode_capacity_v2(ledger,run_id):
    """Original per-RUN profile snapshot; it does not reserve or authorize a call."""
    from .core import LedgerV2,run_limits,model_attempts,provider_attempts,NATIVE4_AMAP_CALLS
    from .read_status import ReadUnavailable
    if not isinstance(ledger,LedgerV2):
        raise ReadUnavailable('version-2 ledger required')
    run=ledger.runs.get(run_id);limits=run_limits(ledger,run_id)
    value=json.loads(encode_capacity(ledger,run_id))
    cancelled=run is not None and run.cancelled
    def remaining(maximum,used):return 0 if cancelled else max(0,maximum-used)
    value.update(version='G2C-original-run-capacity.2',run_profile=ledger.run_profiles.get(run_id),
        limits_source='original-run-profile.1'if run_id in ledger.run_profiles else'original-account-config.1',
        remaining_steps=remaining(limits.steps,0 if run is None else run.steps),
        remaining_tools=remaining(limits.tools,0 if run is None else run.tools),
        remaining_output=remaining(limits.output,Meter.output_exposure(ledger,run_id)),
        remaining_models=None if limits.models is None else remaining(limits.models,model_attempts(ledger,run_id)),
        remaining_amap_attempts=None if limits.models is None else remaining(NATIVE4_AMAP_CALLS,provider_attempts(ledger,run_id,'amap')),
        remaining_local_tools=remaining(ledger.config.max_tools,provider_attempts(ledger,run_id,'local'))if limits.models is not None else None)
    return compact(value,ensure_ascii=True,sort_keys=True)
