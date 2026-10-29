"""Explicit operator-owned local quota profiles. No provisioning or production defaults."""
from dataclasses import dataclass
import json
import time
from pathlib import Path
from types import MappingProxyType
from cj_usage.core import Config, Blocked


class LocalContextUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class RunProfile:
    meter: Config
    output_limits: object


@dataclass(frozen=True)
class LocalRunContext:
    current: RunProfile
    history: tuple[RunProfile, ...]
    version: str

    @property
    def profiles(self): return (self.current,*self.history)


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise LocalContextUnavailable('duplicate context field')
        result[key]=value
    return result


def _profile(value, version):
    if type(value) is not dict or set(value)!={'meter','output_limits'}:
        raise LocalContextUnavailable('explicit meter and output limits required')
    config=Config(**value['meter'])
    limits=value['output_limits']
    expected={'answer','draft'} if version=='CJ-LOCAL-RUN@1' else {'model','tool','memory'}
    if (config.unit!='provider_call' or type(limits) is not dict or set(limits)!=expected
            or any(type(v) is not int or not 1<=v<=config.max_output for v in limits.values())):
        raise LocalContextUnavailable('local provider_call profile required')
    return RunProfile(config,MappingProxyType(dict(limits)))


def load_run_context(path, *, clock=time.time, require_active=True):
    try:
        if not str(path).strip(): raise LocalContextUnavailable('explicit context path required')
        with Path(path).open('rb') as source: raw=source.read(1_048_577)
        if len(raw)>1_048_576: raise LocalContextUnavailable('context file too large')
        value=json.loads(raw,object_pairs_hook=_unique)
        if (type(value) is not dict or set(value)!={'version','current','history'}
                or value['version'] not in ('CJ-LOCAL-RUN@1','CJ-LOCAL-RUN@2') or type(value['history']) is not list):
            raise LocalContextUnavailable('explicit versioned local context required')
        current=_profile(value['current'],value['version'])
        history=tuple(_profile(item,value['version']) for item in value['history'])
        periods=sorted((p.meter.period_start,p.meter.period_end) for p in (current,*history))
        if any(a[1]>b[0] for a,b in zip(periods,periods[1:])):
            raise LocalContextUnavailable('overlapping or duplicate quota periods')
        if any(p.meter.period_end>current.meter.period_start for p in history):
            raise LocalContextUnavailable('history must precede current period')
        if require_active and not current.meter.period_start<=clock()<current.meter.period_end:
            raise LocalContextUnavailable('current quota period is not active')
        return LocalRunContext(current,history,value['version'])
    except (OSError,ValueError,TypeError,KeyError,Blocked,UnicodeError,RecursionError):
        raise LocalContextUnavailable('local run context unavailable or invalid') from None
