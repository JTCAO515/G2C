"""Fresh process for the frozen memory-restart scenario; original real RUN exit."""
import json
import os
from pathlib import Path
import sys

from runtime import ROOT
from real import keychain, STATE
from cj_agent.provider import DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL
from cj_api.local_app import LocalDatabase
from cj_api.local_run_context import load_run_context
from cj_api.real_services import RealServices, RealTools
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_usage.authorization_budget import AuthorizationBudget
import run_worker


def main():
    if os.environ.get('CJ_M4_SYNTHETIC_ONLY') != '1':
        raise ValueError('explicit authorized synthetic profile required')
    conninfo, auth, context_path, memory_path = map(Path, sys.argv[1:])
    context = load_run_context(context_path)
    model = MeteredDashScopeProvider(DashScopeConfig(M4_BASE, M4_MODEL,
        keychain('g2c-dashscope'), max_output_tokens=1024), AuthorizationBudget(STATE))
    services = RealServices(model, keychain('g2c-amap-web-key'),
        frozenset(json.loads((auth / 'invited.json').read_text())))
    memory = TypedRuntimeConfiguration.from_bytes(memory_path.read_bytes())
    database = LocalDatabase(conninfo, run_context=context, travel_context=True, needs_context=True)
    outcomes = run_worker.run_once(database, model, auth, memory_configuration=memory,
        tools_configuration=RealTools(services), real_services=services)
    print(json.dumps([o.__dict__ for o in outcomes]))


if __name__ == '__main__':
    main()
