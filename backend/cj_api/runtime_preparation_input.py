"""Fixed legal preference input for the public deleted-recall setup only."""
from runtime_adapter.contract import Unavailable

MEMORY_TASK='val-deleted-recall'
MEMORY_SLOTS=('quiet.entrance','travel.pace')
MEMORY_QUOTES={
    'zh':('我喜欢安静的入口。','我喜欢慢节奏旅行。'),
    'en':('I usually prefer quiet entrances.','I prefer fewer stops in a day.'),
}


def preparation_text(task_id,language):
    if task_id!=MEMORY_TASK:raise Unavailable('NATIVE_PREPARATION_TASK_NOT_CONNECTED')
    return ' '.join(MEMORY_QUOTES[language])


def preparatory_message(request):
    return request['kind']=='task_setup' and request['payload']['task_id']==MEMORY_TASK
