import json
from pathlib import Path
import jsonschema
from test_trip_context import raw,select
from cj_message.trip_reference import OriginalTripReference
from cj_message.trip_context import TripSelection

ROOT=Path(__file__).resolve().parents[3]
SCHEMA=json.loads((ROOT/'contracts/message/trip-schema.1.json').read_text())

def test_new_version_schema_and_original_reference():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    for selected in (None,select(),select(day=None,item_id=None)):
        jsonschema.validate(json.loads(raw(selected)),SCHEMA)
    import pytest
    for bad in (json.loads(raw(select(owner='client'))),json.loads(raw(select(),creation_intent='consider_trip'))):
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(bad,SCHEMA)
    reference=OriginalTripReference('internal','chat','g','m','r',1,'a'*64,'MESSAGE-send.3','trip','trip-a',1,1,
        TripSelection.parse(select()),'b'*64,b'synthetic source')
    jsonschema.validate(reference.public_value(),{'$ref':'#/$defs/MessageTripReference',**{k:v for k,v in SCHEMA.items() if k!='$id' and k!='oneOf'}})
