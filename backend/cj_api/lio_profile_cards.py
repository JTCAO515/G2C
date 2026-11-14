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
    def __init__(self,epoch_reader):
        self.epoch_reader=epoch_reader

    def project(self,context,token,binding,state,locale):
        if state is None or state.status!='completed':return []
        values=[effect.removeprefix(CONTEXT) for effect in state.effects if effect.startswith(CONTEXT)]
        if not values:return []
        profile=decode_context(values[-1])
        if profile.memory_epoch is not None:
            if self.epoch_reader is None:raise Unavailable('current profile Memory reader unavailable')
            def encode(epoch):
                rows=(self._rows(context,binding,profile,locale) if epoch==profile.memory_epoch else [])
                return json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()
            # The C-owned reader holds the real active scope through encoding;
            # candidate history fences and consent are not prerequisites or made up.
            raw=self.epoch_reader.project(context,binding,encode,max_result_bytes=32768)
            return json.loads(raw)
        if any(factor.state=='memory' for factor in profile.factors):return []
        return self._rows(context,binding,profile,locale)

    def _rows(self,context,binding,profile,locale):
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
