"""Read-only source C0 manifest. Activation pins must come from B, never guesses."""
from hashlib import sha256
from pathlib import Path
from importlib import import_module

from .contract import VERSION, Pins, decode, digest, encode, require
from .profiles import C0, REFLECTION_SYSTEM, structural_tools_sha256

ROOT = Path(__file__).resolve().parents[2]
PREREGISTRATION_SHA256 = '285500035df89e848ef20f9c34fc8f53887b3050cdf7b69e33d818334c7ea91f'


def source_c0(*,resource_root=None):
    # B deployment configuration only; not candidate/task/HTTP input. Missing
    # public files fail at their exact path, without another dataset/root fallback.
    root=ROOT if resource_root is None else Path(resource_root)
    from cj_agent.provider import M4_BASE, M4_MODEL, M4_REAL_OUTPUT_TOKENS, M4_NATIVE_TURN_BUFFERED
    from cj_api.real_services import NATIONAL_TOOLS, TOOL_SYSTEM
    from cj_api.local_lio_planning import DISCUSSION_PROMPT,NATIONAL_GROUPED_DRAFT,RICH_FIRST_DRAFT
    from cj_message.lio_context import PERSONA
    from cj_draft.lio_plan import INITIAL_SYSTEM, REPLAN_SYSTEM
    from cj_draft.grouped_plan import system_for,GENERATION_PROFILES
    from cj_draft.rich_first import rich_system_for
    from cj_draft.rich_schema import PROFILES,GENERATION_PROFILES as RICH_PROFILES
    from cj_api.local_lio_exploration import UNDERSTANDING_SYSTEM,RESPONSE_SYSTEM,PRACTICAL_SYSTEM
    from cj_api.lio_exploration_profile import POLICY as EXPLORATION_DEFAULT_POLICY
    from cj_message.lio_exploration_schema import PROFILES as EXPLORATION_PROFILES,response_format,response_format_sha256
    from cj_api.lio_pipeline_model import SKELETON_SYSTEM,WORDING_SYSTEM
    policy_files = ('backend/agent/cj_agent/provider.py', 'backend/agent/cj_agent/worker.py', 'backend/cj_api/real_services.py',
             'backend/cj_api/local_lio_planning.py', 'backend/cj_api/local_lio_national.py',
             'backend/cj_api/lio_scene.py',
             'backend/fact/cj_fact/visitor.py',
             'backend/cj_api/lio_national_intake.py', 'backend/agent/cj_agent/lio_intake_schema.py',
             'backend/agent/cj_agent/lio_intake_current_schema.py',
             'backend/agent/cj_agent/lio_intake_modes_schema.py', 'backend/cj_api/tool_evidence.py',
             'backend/agent/cj_agent/lio_intake_start_schema.py',
             'backend/agent/cj_agent/lio_intake_flat_schema.py',
             'backend/agent/cj_agent/lio_intake_facts_schema.py',
             'backend/agent/cj_agent/lio_intake_flow_schema.py',
             'backend/agent/cj_agent/lio_intake_optional_schema.py', 'backend/cj_api/lio_flow_intake.py',
             'backend/cj_api/lio_flat_intake.py', 'backend/cj_api/lio_sourced_intake.py',
             'backend/message/cj_message/lio_context.py',
             'backend/message/cj_message/demo_dialogue.py',
             'backend/message/cj_message/lio_wire.py',
             'backend/cj_api/local_lio_calendar.py',
             'backend/cj_api/local_lio_calendar_source.py',
             'backend/cj_api/local_lio_calendar_edit.py',
             'backend/cj_api/lio_calendar_edit.py',
             'backend/cj_api/lio_calendar_ordinals.py',
             'backend/cj_api/lio_planning_grounding.py',
             'backend/cj_api/local_memory_history.py',
             'backend/cj_api/local_app.py',
             'backend/draft/cj_draft/lio_plan.py', 'backend/draft/cj_draft/grouped_plan.py',
             'backend/draft/cj_draft/rich_first.py',
             'backend/draft/cj_draft/rich_schema.py',
             'backend/cj_api/lio_plan_pace.py',
             'backend/cj_api/lio_exploration_factors.py',
             'backend/cj_api/lio_exploration_profile.py',
             'backend/cj_api/local_lio_exploration_profile.py',
             'backend/cj_api/local_lio_exploration.py',
             'backend/cj_api/lio_exploration_policy.py',
             'backend/cj_api/lio_profile_cards.py',
             'backend/cj_api/lio_positive_trip.py',
             'backend/cj_api/lio_city.py',
             'backend/cj_api/lio_exploration_routes.py',
             'backend/message/cj_message/lio_exploration_schema.py',
             'backend/cj_api/local_lio_rich_source.py',
             'backend/cj_api/local_lio_rich_calendar_source.py',
             'backend/cj_api/local_lio_provider_sources.py',
             'backend/cj_api/local_lio_rich_checks.py',
             'backend/cj_api/lio_poi2_tool.py',
             'backend/cj_api/lio_pipeline_skeleton.py',
             'backend/cj_api/lio_pipeline_document.py',
             'backend/cj_api/lio_pipeline_model.py',
             'backend/message/cj_message/lio_pipeline_schema.py',
             'backend/place/cj_place/gaode_v2.py',
             'backend/place/cj_place/https_transport.py',
             'backend/draft/cj_draft/rich_calendar_source.py',
             'backend/draft/cj_draft/rich_provider_source.py',
             'backend/trip/cj_trip/local_rich_read.py',
             'backend/message/cj_message/travel_reference.py',
             'backend/memory/cj_memory/epoch_projection.py')
    files = (*policy_files,
             'eval/optimization/cases.v2.json',
             'eval/optimization/score_v2.py', 'tooling/optimization/uv.lock')
    for name in policy_files:
        module='.'.join(Path(name).parts[-2:])[:-3]
        actual=Path(import_module(module).__file__).read_bytes()
        require((root/name).read_bytes()==actual,'PUBLIC_POLICY_BUNDLE_SOURCE_MISMATCH')
    adapter_files = {'backend/runtime_adapter/'+path.name: sha256(path.read_bytes()).hexdigest()
                     for path in sorted(Path(__file__).parent.glob('*.py'))}
    policies = dict(tool_system=TOOL_SYSTEM, persona=PERSONA, discussion=DISCUSSION_PROMPT,
                    initial=INITIAL_SYSTEM, replan=REPLAN_SYSTEM, reflection=REFLECTION_SYSTEM,
                    national_grouped_guidance=NATIONAL_GROUPED_DRAFT,
                    national_dated_initial=system_for(retained=False,ordinal=False,guidance=NATIONAL_GROUPED_DRAFT),
                    national_dated_replan=system_for(retained=True,ordinal=False,guidance=NATIONAL_GROUPED_DRAFT),
                    national_ordinal_initial=system_for(retained=False,ordinal=True),
                    national_ordinal_replan=system_for(retained=True,ordinal=True),
                    national_rich_guidance=RICH_FIRST_DRAFT,
                    national_rich_first={profile:rich_system_for(ordinal=ordinal,pace=pace,
                        guidance='' if ordinal else RICH_FIRST_DRAFT)
                        for (ordinal,pace),profile in PROFILES.items()},
                    exploration_understanding=UNDERSTANDING_SYSTEM,
                    exploration_response=RESPONSE_SYSTEM,
                    exploration_practical=PRACTICAL_SYSTEM,
                    pipeline_skeleton=SKELETON_SYSTEM,
                    pipeline_wording=WORDING_SYSTEM,
                    exploration_schemas={profile:dict(response_format=response_format(profile),
                        response_format_sha256=response_format_sha256(profile)) for profile in EXPLORATION_PROFILES},
                    exploration_default_policy=EXPLORATION_DEFAULT_POLICY,
                    exploration_rollback=dict(variable='CJ_LIO_EXPLORATION_ENABLED',source_default='1',legal_values=['0','1']),
                    policy_source_sha256={name:sha256((root/name).read_bytes()).hexdigest() for name in policy_files})
    return dict(version=VERSION, configuration='C0-source-national.1', activation_status='UNRUN',
        source_hashes={name: sha256((root/name).read_bytes()).hexdigest() for name in files},
        adapter_files=adapter_files, adapter_sha256=digest(adapter_files),
        c0=C0, candidate_id=digest(C0),
        fragment_sha256={name: sha256(text.encode()).hexdigest() for name,text in C0.items()},
        slot_host_status=dict.fromkeys(C0, 'UNRUN'),
        national_clarification_hook='NOT_CONNECTED_NO_BASELINE_ANCHOR',
        system_prompt_sha256=digest(policies),
        model=dict(endpoint=M4_BASE,id=M4_MODEL,parameters=dict(stream=True,
            stream_options={'include_usage':True},enable_thinking=False,
            max_tokens_by_profile=dict(answer=M4_REAL_OUTPUT_TOKENS,intake=M4_REAL_OUTPUT_TOKENS,
                                       reflection=min(1024,M4_REAL_OUTPUT_TOKENS),
                                       **{profile:M4_REAL_OUTPUT_TOKENS if profile in RICH_PROFILES
                                          else min(1024,M4_REAL_OUTPUT_TOKENS)
                                          for profile in GENERATION_PROFILES}),
            native_turn_profile=M4_NATIVE_TURN_BUFFERED)),
        tool_schema_sha256=structural_tools_sha256(NATIONAL_TOOLS),
        full_c0_tools_sha256=digest(NATIONAL_TOOLS),
        tool_implementation_sha256=sha256((root/'backend/cj_api/real_services.py').read_bytes()).hexdigest(),
        task_version='G2C-dialogue-cases.2', task_sha256=sha256((root/'eval/optimization/cases.v2.json').read_bytes()).hexdigest(),
        score_version='G2C-dialogue-score.2',score_sha256=sha256((root/'eval/optimization/score_v2.py').read_bytes()).hexdigest(),
        preregistration_sha256=PREREGISTRATION_SHA256,
        required_from_B=['actual_runtime_code_sha','actual_runtime_image_digest',
                         'same-original-auth-session-and-ledger-binding',
                         'registered-reflection-and-three-slot-host-composition',
                         'protected-exhaustive-original-collector',
                         'canonical-fresh-original-claim-and-one-use-dispatch',
                         'all-task-legal-setup','window-and-shared-ledger-sublimit'])


def freeze_pins(runtime_card,*,resource_root=None):
    """B supplies observed code/image and model parameters; no endpoint/key lookup.
    A source-only C0 is deliberately not accepted as an activation card.
    """
    require(type(runtime_card) is dict and set(runtime_card) == {'code_sha','image_digest','model'},
            'B_ACTUAL_RUNTIME_CARD_REQUIRED')
    source = source_c0(resource_root=resource_root)
    require(encode(runtime_card['model']) == encode(source['model']), 'B_MODEL_PROFILE_REQUIRES_EXPLICIT_REVISION')
    names = ('version','adapter_sha256','system_prompt_sha256','tool_schema_sha256',
             'tool_implementation_sha256','c0','task_version','task_sha256','score_version',
             'score_sha256','preregistration_sha256')
    return Pins.from_dict({**{name:source[name] for name in names}, **decode(encode(runtime_card))})


if __name__ == '__main__':
    print(encode(source_c0()).decode())
