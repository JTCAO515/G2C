"""Fresh-process Fake-only worker observation for the restart scenario."""
import argparse
import json
from pathlib import Path

from runtime import ROOT
from cases import ObservedProvider
from cj_api.local_app import LocalDatabase
from cj_api.local_run_context import load_run_context
from cj_memory.typed_runtime import TypedRuntimeConfiguration
import run_worker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('conninfo', type=Path)
    parser.add_argument('auth', type=Path)
    parser.add_argument('context', type=Path)
    parser.add_argument('memory_policy', type=Path)
    args = parser.parse_args()
    database = LocalDatabase(args.conninfo, run_context=load_run_context(args.context), travel_context=True)
    policy = TypedRuntimeConfiguration.from_bytes(args.memory_policy.read_bytes())
    model = ObservedProvider()
    outcomes = run_worker.run_once(database, model, args.auth, memory_configuration=policy)
    print(json.dumps(dict(outcomes=[dict(message_id=o.message_id, status=o.status) for o in outcomes],
                         model_calls=model.calls, provider_inputs=model.inputs), ensure_ascii=False))


if __name__ == '__main__':
    main()
