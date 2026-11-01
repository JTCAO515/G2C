import json
from pathlib import Path
import pytest,jsonschema
from referencing import Registry,Resource
from cj_message.edit_result_protocol import PUBLISHER_ABI,CONFIGURATION_ABI,PROFILE,KINDS
ROOT=Path(__file__).resolve().parents[3]/'contracts/message'


def test_result_descriptor_examples_and_explicit_versions():
    schema=json.loads((ROOT/'edit-result-schema.1.json').read_text());examples=json.loads((ROOT/'edit-result-examples.1.json').read_text())
    old=json.loads((ROOT/'edit-schema.1.json').read_text())
    registry=Registry().with_resources([(schema['$id'],Resource.from_contents(schema)),(old['$id'],Resource.from_contents(old))])
    jsonschema.Draft202012Validator.check_schema(schema)
    validator=jsonschema.Draft202012Validator(schema,registry=registry)
    for value in examples['positive']:validator.validate(value)
    for value in examples['negative']:
        with pytest.raises(jsonschema.ValidationError):validator.validate(value)
    for value in examples['read_positive']+examples['read_negative']:
        response=jsonschema.Draft202012Validator({'$ref':schema['$id']+'#/$defs/'+value['schema']},registry=registry)
        if value in examples['read_negative']:
            with pytest.raises(jsonschema.ValidationError):response.validate(value['value'])
        else:response.validate(value['value'])
    from cj_message.edit_protocol import PUBLISHER_ABI as OLD
    assert OLD!=PUBLISHER_ABI and CONFIGURATION_ABI=='CJ-MESSAGE-EDIT-RESULT@1'
    assert PROFILE=='message-edit-result.1' and KINDS=={'clarification_required','expansion_required'}
