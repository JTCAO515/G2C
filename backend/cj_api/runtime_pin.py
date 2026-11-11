"""Public C0 pin material derived from the actual installed worker code."""
from hashlib import sha256
from pathlib import Path

from cj_agent import provider,worker
from cj_agent.draft import DRAFT_SYSTEM
from cj_message.lio_context import PERSONA
from cj_usage import authorization_budget
from cj_usage.authorization_budget import canonical
from . import real_services,local_lio_planning,runtime_adapter,runtime_candidate,runtime_window,runtime_budget


def pin(config,source_commit):
 modules=(provider,worker,authorization_budget,real_services,local_lio_planning,
          runtime_adapter,runtime_candidate,runtime_window,runtime_budget)
 systems=dict(persona=PERSONA,tools=real_services.TOOL_SYSTEM,discussion=local_lio_planning.DISCUSSION_PROMPT,
              intake=local_lio_planning.SYSTEM,draft=DRAFT_SYSTEM)
 slots=dict(runtime_candidate.BASELINE)
 return dict(version='G2C-runtime-C0.1',code_commit=source_commit,adapter_version=runtime_adapter.VERSION,
  code_sha256={m.__name__:sha256(Path(m.__file__).read_bytes()).hexdigest() for m in modules},
  model=dict(id=config.model_id,endpoint=config.base_url,region='cn-beijing',enable_thinking=False,
             timeout_seconds=config.timeout_seconds,max_tokens_native=config.max_output_tokens,
             max_tokens_structured=min(1024,config.max_output_tokens),stream=True,include_usage=True,
             wire_request_max_bytes=32768),
  system_templates={k:dict(text=v,sha256=sha256(v.encode()).hexdigest()) for k,v in systems.items()},
  wire_system_recipe_sha256=sha256(Path(provider.__file__).read_bytes()).hexdigest(),
  slots={k:dict(text=v,sha256=sha256(v.encode()).hexdigest()) for k,v in slots.items()},
  C0=slots,C0_sha256=sha256(canonical(slots)).hexdigest(),
  tool_schema=real_services.TOOLS,tool_schema_sha256=sha256(canonical(real_services.TOOLS)).hexdigest(),
  tool_implementation_sha256=sha256(Path(real_services.__file__).read_bytes()).hexdigest(),
  dynamic_bindings='Original MESSAGE locale/Beijing question day and source-bound inputs remain per attempt; actual wire system/schema hashes and original M4 input SHA are recorded for every dispatch')
