"""Profile8 binds clear first trip commands, without extracting their parameters."""
from hashlib import sha256
import json
from .lio_intake_facts_schema import response_format as facts_format,SYSTEM as FACTS_SYSTEM

PROFILE='LIO-planning-intake.8'
VERSION='LIO-planning-intake.6'


def response_format(source_index,required_intent):
    result=facts_format(source_index)
    result['json_schema']['name']='lio_request_bound_facts_v6'
    if required_intent=='plan':
        properties=result['json_schema']['schema']['properties']
        properties['intent']['const']='plan'
        properties['needs_tools']['const']=False
    return result


def response_format_sha256(source_index,required_intent):
    return sha256(json.dumps(response_format(source_index,required_intent),sort_keys=True,separators=(',',':')).encode()).hexdigest()


SYSTEM=FACTS_SYSTEM+(
    ' A direct trip command is planning even when its dates and party size are missing. '
    'Do not classify it as consultation merely because you need clarification. '
    'Missing planning facts stay null; the host asks for them before itinerary advice. '
    'needs_tools is not permission to replace a clarification with a hypothetical itinerary or assumed start date. '
    'Ordinary questions and explicit discussion/refusal remain non-executing and do not require planning dates.'
)
