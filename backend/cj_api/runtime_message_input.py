"""Canonical native Lio input from the claimed client operation, not a snapshot."""
from cj_message.demo_dialogue import LIO_VERSION_V2,_identity
from runtime_adapter.contract import digest,encode,Unavailable

REFLECTION_MESSAGE='Runtime reflection request.'


def lio_input(scope,request,language=None):
    if request['kind']=='reflection':
        return encode(dict(version=LIO_VERSION_V2,message_id=request['step_id'],
            text=REFLECTION_MESSAGE,locale='en',new_conversation=True))
    if request['kind'] not in ('message','new_conversation_message','start_controlled_generation'):
        raise Unavailable('RUNTIME_ORIGINAL_ACTION_HAS_NO_MESSAGE')
    selection=dict(new_conversation=True)
    if len(request['prior_step_ids'])>1 and request['kind']!='new_conversation_message':
        first='runtime-'+digest([scope,request['attempt_id'],1])
        selection=dict(conversation_id='lio-dialogue-'+_identity(scope,'lio-new:'+first))
    return encode(dict(version=LIO_VERSION_V2,message_id=request['step_id'],text=request['payload']['text'],
        locale=language,**selection))
