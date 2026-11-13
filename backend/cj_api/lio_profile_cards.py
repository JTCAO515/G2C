"""Current, sourced profile labels inside the original guarded Lio read frame."""
import json

from cj_message.domain import Unavailable

from .lio_exploration_factors import LABELS,BY_KEY
from .lio_exploration_profile import CONTEXT,decode_context
from cj_message.lio_context import display_answer


def _value(key,value,locale):
    for option in BY_KEY[key].options:
        if str(value).casefold() in (option.key.casefold(),option.zh.casefold(),option.en.casefold()):
            return option.zh if locale=='zh' else option.en
    return str(value)


class LioProfileCards:
    def __init__(self,memory_cards):
        self.memory_cards=memory_cards

    def project(self,context,token,binding,state,locale):
        if state is None or state.status!='completed':return []
        values=[effect.removeprefix(CONTEXT) for effect in state.effects if effect.startswith(CONTEXT)]
        if not values:return []
        profile=decode_context(values[-1])
        # The existing C projection checks the current Memory scope/identity
        # under this same canonical M frame. It exposes a current epoch without
        # granting a processing permit or a raw C repository to this reader.
        if profile.memory_epoch is not None:
            if self.memory_cards is None:raise Unavailable('current profile Memory reader unavailable')
            current=self.memory_cards.read_current(context,token,binding.message_id,binding.run_id)
            if current is None or json.loads(current)['memory_epoch']!=profile.memory_epoch:
                # Any Memory revision can invalidate a retained source. Hide the
                # historical profile until a new admitted producer rebinds it;
                # do not selectively revive apparently unchanged cached facts.
                return []
        elif any(factor.state=='memory' for factor in profile.factors):
            return []
        rows=[]
        for factor in profile.factors:
            for source in factor.sources:
                if source.kind not in ('message','default'):continue
                stored=context.query_lio_message(source.message_id)
                if stored is None or (stored.receipt.conversation_id,stored.receipt.generation)!=(binding.conversation_id,binding.generation):
                    raise Unavailable('profile original source unavailable')
                if source.kind=='message':
                    text=json.loads(stored.raw)['text']
                    if (stored.receipt.sequence!=source.sequence or
                            text[source.offset:source.offset+len(source.quote)]!=source.quote):
                        raise Unavailable('profile original source differs')
            label=LABELS[factor.factor_key][0 if locale=='zh' else 1]
            value=factor.value
            if factor.state=='not_needed':display='不需要' if locale=='zh' else 'No preference'
            elif value is None:display='未定' if locale=='zh' else 'Not settled'
            elif isinstance(value,list):display=('、' if locale=='zh' else ', ').join(_value(factor.factor_key,item,locale) for item in value)
            elif isinstance(value,bool):display=('是' if value else '否') if locale=='zh' else ('Yes' if value else 'No')
            else:display=_value(factor.factor_key,value,locale)
            safe=display_answer(label+': '+display,locale)
            if safe is not None:
                # Presentation only; retain the complete value and provenance
                # in context.2. An ellipsis never becomes an editable authority.
                if len(safe)>500:safe=safe[:499]+'…'
                rows.append(dict(factor_key=factor.factor_key,display_text=safe,state=factor.state))
        return rows
