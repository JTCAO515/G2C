"""Scoped private operator RPC inside the existing HK worker; no provider dispatch."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from cj_agent.provider import DashScopeConfig,M4_BASE,M4_MODEL,M4_REAL_OUTPUT_TOKENS
from cj_api.runtime_observation import collect
from cj_api.runtime_pin import pin
from cj_api.runtime_window import RuntimeWindow
from cj_usage.authorization_budget import HK_JOURNAL_ROOT
from cj_strict_json import reject_duplicates
from .configuration import Runtime,load_secret_environment
from .entrypoint import _runtime_gate


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('action',choices=('describe','submit','query'))
 parser.add_argument('manifest',type=Path)
 args=parser.parse_args();runtime=None
 try:
  raw=sys.stdin.buffer.read(262145)
  if len(raw)>262144:raise ValueError('bounded operator request required')
  value=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate operator field')) if raw else {}
  load_secret_environment('worker')
  with tempfile.TemporaryDirectory(prefix='runtime-rpc-') as root:
   runtime=Runtime.load(root,worker=True);database=runtime.database()
   _runtime_gate(database,runtime)
   window=RuntimeWindow.load(args.manifest,database,runtime.demo_subjects,allow_expired=args.action!='submit')
   source=os.environ.get('CJ_BETA_BUILD_SOURCE')
   if source!=window.value['source_commit']:raise ValueError('actual worker code source differs')
   if args.action=='describe':
    config=DashScopeConfig(M4_BASE,M4_MODEL,os.environ['CJ_MODEL_API_KEY'],max_output_tokens=M4_REAL_OUTPUT_TOKENS)
    response=dict(version='G2C-runtime-descriptor.1',window_id=window.value['window_id'],purpose=window.value['purpose'],
                  billing_prefix=window.value['billing_prefix'],pins=pin(config,source))
   elif args.action=='submit':response=window.submit(value)
   else:
    if type(value) is not dict or set(value)!={'attempt_id'} or type(value['attempt_id']) is not str:
     raise ValueError('original logical attempt required')
    response=collect(window,value['attempt_id'],HK_JOURNAL_ROOT/'m4-outflows.sqlite')
   print(json.dumps(response,ensure_ascii=False))
 except (OSError,ValueError) as error:
  print(json.dumps(dict(version='G2C-runtime-operator-error.1',state='UNKNOWN',error_type=type(error).__name__)))
  raise SystemExit(1) from None
 finally:
  if runtime is not None:runtime.close()


if __name__=='__main__':main()
