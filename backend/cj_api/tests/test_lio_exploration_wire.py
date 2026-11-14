from types import SimpleNamespace
import unittest

from cj_agent.provider import DashScopeConfig,M4_BASE,M4_MODEL,M4_NATIVE_TURN_BUFFERED
from cj_api.runtime_model import RuntimeModel,configured_model
from cj_message.lio_exploration_schema import PROFILES,response_format,response_format_sha256
from runtime_adapter.contract import Unavailable,encode


def observer(profile,limit,*,logical_change=None,wire_change=None):
    model=SimpleNamespace(config=DashScopeConfig(M4_BASE,M4_MODEL,'offline-only',max_output_tokens=limit))
    logical=dict(structured_profile=profile,response_format_sha256=response_format_sha256(profile))
    wire=dict(model=M4_MODEL,stream=True,stream_options={'include_usage':True},enable_thinking=False,
              max_tokens=limit,response_format=response_format(profile))
    logical.update(logical_change or {});wire.update(wire_change or {})
    original=SimpleNamespace(input=lambda *a,**kw:encode(logical),artifact=lambda *a,**kw:encode(dict(wire_input_utf8=encode(wire).decode())))
    return RuntimeModel(original,model,native_turn_profile=M4_NATIVE_TURN_BUFFERED),model


class ExplorationWireTests(unittest.TestCase):
    def test_two_profiles_observe_actual_schema_and_lower_config_without_new_numeric_cap(self):
        for profile in PROFILES:
            for limit in (768,1536):
                with self.subTest(profile=profile,limit=limit):
                    read,model=observer(profile,limit)
                    self.assertEqual(read('token','mid','op'),configured_model(model,M4_NATIVE_TURN_BUFFERED))
                    for wrong in (limit-1,limit+1):
                        read,_=observer(profile,limit,wire_change=dict(max_tokens=wrong))
                        with self.assertRaisesRegex(Unavailable,'ACTUAL_MODEL_WIRE_PARAMETERS_CHANGED'):read('token','mid','op')

    def test_declared_schema_and_actual_wire_schema_must_both_match_the_fixed_profile(self):
        for profile in PROFILES:
            for changed in (
                dict(logical_change=dict(response_format_sha256='0'*64)),
                dict(logical_change=dict(structured_profile='LIO-exploration-unknown.1')),
                dict(wire_change=dict(response_format=response_format(next(p for p in PROFILES if p!=profile))))):
                with self.subTest(profile=profile,changed=changed):
                    read,_=observer(profile,1536,**changed)
                    with self.assertRaisesRegex(Unavailable,'ACTUAL_EXPLORATION_SCHEMA_CHANGED'):read('token','mid','op')

    def test_other_original_model_parameter_checks_are_not_relaxed(self):
        for changed in (dict(model='other'),dict(stream=False),dict(stream_options={}),dict(enable_thinking=True)):
            read,_=observer(PROFILES[0],1536,wire_change=changed)
            with self.subTest(changed=changed),self.assertRaisesRegex(Unavailable,'ACTUAL_MODEL_WIRE_PARAMETERS_CHANGED'):
                read('token','mid','op')


if __name__=='__main__':unittest.main()
