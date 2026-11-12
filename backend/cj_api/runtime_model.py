"""Observed model descriptor from original provider configuration/wire receipt.

No expected pin descriptor is passed to this reader. Captured HTTP body bytes
are authenticated against the original financial journal by RuntimeOriginals.
"""
from cj_agent.provider import (M4_NATIVE_TURN_BUFFERED,M4_NATIVE_TURN_PROFILE_V2,
                               M4_NATIVE_TURN_STREAM)
from runtime_adapter.contract import decode,Unavailable


class RuntimeModel:
    def __init__(self,originals,provider,*,native_turn_profile):
        self.originals,self.provider=originals,provider
        self.native_turn_profile=native_turn_profile

    def __call__(self,token,message_id,operation_id):
        wire=decode(self.originals.artifact(token,message_id,operation_id,wire_input=True))
        body=decode(wire['wire_input_utf8'])
        logical=decode(self.originals.input(token,message_id,operation_id))
        config=self.provider.config
        profile=logical.get('native_turn_profile')
        if profile is not None and profile!=self.native_turn_profile:
            raise Unavailable('ACTUAL_NATIVE_MODEL_PROFILE_CHANGED')
        full_output=(profile in (M4_NATIVE_TURN_BUFFERED,M4_NATIVE_TURN_STREAM,M4_NATIVE_TURN_PROFILE_V2)
                     or logical.get('structured_profile') is not None)
        maximum=config.max_output_tokens if full_output else min(1024,config.max_output_tokens)
        if (body['model']!=config.model_id or body['stream'] is not True or
                body['stream_options']!={'include_usage':True} or body['enable_thinking'] is not False or
                body['max_tokens']!=maximum):
            raise Unavailable('ACTUAL_MODEL_WIRE_PARAMETERS_CHANGED')
        return dict(endpoint=config.base_url,id=body['model'],parameters=dict(stream=body['stream'],
            stream_options=body['stream_options'],enable_thinking=body['enable_thinking'],
            max_tokens_by_profile=dict(answer=config.max_output_tokens,intake=config.max_output_tokens,
                                       reflection=min(1024,config.max_output_tokens)),
            native_turn_profile=self.native_turn_profile))
