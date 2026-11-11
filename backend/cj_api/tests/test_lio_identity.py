"""Identity projections and original saved-memory authority, without real calls."""
from types import SimpleNamespace
from cj_message.lio_context import answer_prompt
from cj_api.lio_planning_grounding import standalone_question
from cj_message.lio_timeline import TimelineMessage
from cj_api.lio_dialogue_routes import _message


def complete(text):
    return SimpleNamespace(status='completed',text=text,draft_outcome=None,effects=(),budget_exhausted_stage='none')


def test_chinese_lio_identity_is_xingshi_and_user_identity_is_grounded():
    item=TimelineMessage('identity-zh','original-run',1,'你是谁','zh')
    reply=_message(item,complete('我是 Lio，一个武士造型的旅行助手。'))
    assert reply['answer']=='我是 Lio，一只醒狮，帮来中国的朋友规划和解答旅行问题'
    assert 'Use only saved memory' in answer_prompt('zh')
    assert '我还不了解你，愿意介绍一下自己吗' in answer_prompt('zh')
    assert standalone_question('我是谁')
    blocked=_message(item,complete('The RUN contains run_id.'))
    assert blocked['status']=='failed' and blocked['answer']==''


def test_english_lio_identity_and_user_identity_stay_distinct():
    item=TimelineMessage('identity-en','original-run',1,'Who are you?','en')
    reply=_message(item,complete('I am Lio, a warrior-themed travel assistant.'))
    assert reply['answer']=="I'm Lio, a Chinese lion-dance mascot. I help visitors to China plan trips and answer travel questions."
    assert 'Use only saved memory' in answer_prompt('en')
    assert "I don't know you yet. Would you like to introduce yourself?" in answer_prompt('en')
    assert standalone_question('Who am I?')
    user=TimelineMessage('user-en','original-run',1,'Who am I?','en')
    assert _message(user,complete('You have shared a preference for a slower pace.'))['answer']=='You have shared a preference for a slower pace.'
