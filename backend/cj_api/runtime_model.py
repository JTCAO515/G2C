"""Observed model descriptor from original provider configuration/wire receipt.

No expected pin descriptor is passed to this reader. Captured HTTP body bytes
are authenticated against the original financial journal by RuntimeOriginals.
"""
from cj_agent.provider import (M4_NATIVE_TURN_BUFFERED,M4_NATIVE_TURN_PROFILE_V2,
                               M4_NATIVE_TURN_STREAM)
from runtime_adapter.contract import decode,Unavailable
from cj_draft.grouped_plan import GENERATION_PROFILES
from cj_draft.rich_schema import GENERATION_PROFILES as RICH_PROFILES
from cj_message.lio_exploration_schema import PROFILES as EXPLORATION_PROFILES,response_format,response_format_sha256


def configured_model(provider,native_turn_profile):
    config=provider.config
    return dict(endpoint=config.base_url,id=config.model_id,parameters=dict(stream=True,
        stream_options={'include_usage':True},enable_thinking=False,
        max_tokens_by_profile=dict(answer=config.max_output_tokens,intake=config.max_output_tokens,
                                   reflection=min(1024,config.max_output_tokens),
                                   **{profile:config.max_output_tokens if profile in RICH_PROFILES
                                      else min(1024,config.max_output_tokens)
                                      for profile in GENERATION_PROFILES}),
        native_turn_profile=native_turn_profile))


class RuntimeModel:
    def __init__(self,originals,provider,*,native_turn_profile):
        self.originals,self.provider=originals,provider
        self.native_turn_profile=native_turn_profile

    def __call__(self,token,message_id,operation_id):
        wire=decode(self.originals.artifact(token,message_id,operation_id,wire_input=True))
        body=decode(wire['wire_input_utf8'])
        logical=decode(self.originals.input(token,message_id,operation_id))
        config=self.provider.config
        structured=logical.get('structured_profile')
        if isinstance(structured,str) and structured.startswith('LIO-exploration-'):
            if (structured not in EXPLORATION_PROFILES or
                    logical.get('response_format_sha256')!=response_format_sha256(structured) or
                    body.get('response_format')!=response_format(structured)):
                raise Unavailable('ACTUAL_EXPLORATION_SCHEMA_CHANGED')
        profile=logical.get('native_turn_profile')
        if profile is not None and profile!=self.native_turn_profile:
            raise Unavailable('ACTUAL_NATIVE_MODEL_PROFILE_CHANGED')
        full_output=(profile in (M4_NATIVE_TURN_BUFFERED,M4_NATIVE_TURN_STREAM,M4_NATIVE_TURN_PROFILE_V2)
                     or logical.get('structured_profile') is not None
                     or logical.get('draft_profile') in RICH_PROFILES)
        maximum=config.max_output_tokens if full_output else min(1024,config.max_output_tokens)
        if (body['model']!=config.model_id or body['stream'] is not True or
                body['stream_options']!={'include_usage':True} or body['enable_thinking'] is not False or
                body['max_tokens']!=maximum):
            raise Unavailable('ACTUAL_MODEL_WIRE_PARAMETERS_CHANGED')
        return configured_model(self.provider,self.native_turn_profile)
