"""L0 new contract only: old fixtures/schemas remain unchanged."""
import json
from pathlib import Path
import jsonschema
import pytest
from cj_message.edit_protocol import EDIT_ABI,MEMORY_ABI,PUBLISHER_ABI,PROFILE

ROOT=Path(__file__).resolve().parents[3]/'contracts/message'
SCHEMA=json.loads((ROOT/'edit-schema.1.json').read_text())
EXAMPLES=json.loads((ROOT/'edit-examples.1.json').read_text())


def test_edit_contract_examples():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    for value in EXAMPLES['positive']:jsonschema.validate(value,SCHEMA)
    for case in EXAMPLES['negative']:
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(case['input'],SCHEMA)


def test_new_profile_and_interfaces_are_distinct():
    assert PROFILE=='message-trip.2'
    assert len({EDIT_ABI,MEMORY_ABI,PUBLISHER_ABI})==3
    old=json.loads((ROOT/'trip-schema.1.json').read_text())
    for value in EXAMPLES['positive']:
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(value,old)
