"""Code projections over protected profile facts; never model-written briefs."""
from dataclasses import dataclass

from .rich_source import FACTORS, STATES
from .structured import _text

LABELS_ZH = ('目的地','天数','季节','是否首次来华','同行','兴趣','节奏','住宿风格','饮食',
             '必去','避开','行动要求','到达','离开')
LABELS_EN = ('destination','days','season','first visit','party','interests','pace','lodging',
             'diet','must-see','avoid','mobility','arrival','departure')


@dataclass(frozen=True)
class ProfileFact:
    """display_value is the code-formatted value of an accepted native factor.

    The host must derive it from its protected typed profile, not from a model
    summary/public projection. This small value grants no collection or write.
    """
    key: str
    state: str
    display_value: str

    def __post_init__(self):
        if self.key not in FACTORS or self.state not in STATES:
            raise ValueError('declared factor and provenance state required')
        _text(self.display_value,500)


def filter_reasons(refs, facts):
    """Drop invalid/inferred/default/absent claims; retain stable unique order."""
    accepted={fact.key for fact in facts if fact.state in ('known','memory')}
    result=[];removed=[]
    for ref in refs:
        if ref in accepted and ref not in result:result.append(ref)
        else:removed.append(ref)
    return tuple(result),tuple(removed)


def filter_reason_text(note, refs, facts):
    """Project a proposed reason after wording, not just its factor-key list.

    Free prose has no reliable clause-to-factor mapping. If any declared basis
    is invalid, discard the whole associated sentence instead of leaving the
    unsupported claim behind a sanitized key list. This does not certify the
    semantic accuracy of surviving prose or grant factual/write authority.
    """
    kept, removed = filter_reasons(refs, facts)
    return None if removed else note, kept, removed


def brief(facts, *, locale, first_day_full=False):
    labels=dict(zip(FACTORS,LABELS_ZH if locale=='zh' else LABELS_EN))
    ordered={fact.key:fact for fact in facts}
    if len(ordered)!=len(facts):raise ValueError('one accepted value per factor required')
    parts=[]
    for state,zh,en in [('known','按你说的：','Based on what you said: '),
                         ('memory','按已保存的偏好：','From your saved preferences: '),
                         ('default','未提供的部分先按以下默认安排：','For unspecified details I used these defaults: ')]:
        values=[labels[key]+('：' if locale=='zh' else ': ')+ordered[key].display_value
                for key in FACTORS if key in ordered and ordered[key].state==state]
        if values:parts.append((zh if locale=='zh' else en)+('；' if locale=='zh' else '; ').join(values)+('。' if locale=='zh' else '.'))
    if first_day_full:
        parts.append('已按你的要求排满第一天，已知到达时间仍保留。' if locale=='zh' else
                     'I followed your request for a full first day while retaining the known arrival time.')
    return ''.join(parts) if locale=='zh' else ' '.join(parts)
