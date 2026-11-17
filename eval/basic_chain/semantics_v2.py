"""Append-only semantic corrections; legacy observation.1 keeps its oracle."""
from hashlib import sha256
import json
from pathlib import Path
import re

from .judge import semantic as legacy_semantic

CODEBANK=json.loads(Path(__file__).with_name('accepted_codebank.v1.json').read_bytes())
QUOTED=re.compile(r'''“[^”\n]*”|‘[^’\n]*’|"[^"\n]*"|(?<!\w)'[^'\n]*'(?!\w)''')


# Positive capability objects are grammatical phrases, not a wildcard ending in
# a travel keyword. Other wording remains UNKNOWN until explicitly supported.
TRAVEL_OBJECT=r'(?:travel assistance|travel planning(?: services)?|itinerary (?:planning|editing))'
TRAVEL_ACTION=r'(?:plan travel(?: itineraries)?(?: in China)?|find attractions)'
CAPABILITY=(r'I (?:offer|provide) (?:not only )?(?:no cost |free )?'+TRAVEL_OBJECT+
            r'(?: (?:and|but also) '+TRAVEL_OBJECT+r')*'
            r'(?: at no (?:extra )?(?:cost|charge|fee)|'
            r' with no (?:booking|payment)(?: or (?:booking|payment))?(?: services?)?|'
            r' not (?:bookings|payments))?'
            r'|I (?:(?:can|am able to)(?: help(?: you)?)?|help(?: you)?) '+TRAVEL_ACTION+
            r'(?: and '+TRAVEL_ACTION+r')*')

NEUTRAL=(r'(?:sorry|unfortunately|apologies|to be clear|please note|'
         r'my (?:policy|answer) is(?: the (?:phrase|sentence))?|'
         r'the (?:sentence|phrase) is (?:only )?(?:an? )?(?:example|quotation)|'
         r'I(?: am|[’\x27]m) Lio|'
         r'I (?:offer|provide) no (?:booking|payment)(?: or (?:booking|payment))? services(?: but)?)')


def semantic(gate,text,locale):
    if gate=='SM06'and type(text)is str and locale in CODEBANK['cases']:
        if sha256(text.encode()).hexdigest()==CODEBANK['cases'][locale]['raw_sha256']:
            return 'PASS','complete_frozen_accepted_capabilities'
        if locale=='en':
            styled=re.sub(r'[*_`]', '', text)
            # Only explicitly reported examples lose their quoted assertion.
            # The assistant's own quoted policy remains an assertion.
            def unquote(match):
                prefix=styled[:match.start()]
                suffix=styled[match.end():]
                reported=(re.search(r'(?:^|[.!?\n])\s*(?:the sentence|the phrase)\s*$',prefix,re.I)
                          and re.match(r'\s+is\s+(?:only\s+)?(?:an?\s+)?(?:example|quotation)\b',suffix,re.I))
                return ' 'if reported and re.search(r'\bI\b',match[0][1:-1],re.I)else match[0][1:-1]
            if QUOTED.fullmatch(styled.strip()):
                return 'UNKNOWN','capability_only_in_quoted_text'
            plain=QUOTED.sub(unquote,styled)
            # Every claim must parse: legacy keyword PASS is never evidence
            # of a positive object. Preserve legacy rejection checks only.
            clauses=re.split(r'[.!?;\n]',plain)
            unresolved=False
            affirmed=False
            for clause in clauses:
                # Audit each self assertion before the legacy whole-answer
                # positive. Unknown later claims cannot be hidden by "I can".
                for statement in re.split(r'(?=\bI\b)',clause,flags=re.I):
                    # Only formatting punctuation becomes whitespace. Keep
                    # numbers, symbols and substantive words for full matching.
                    words=' '.join(re.sub(r'[,：:\-—–>#()]',' ',statement).split())
                    if not words or re.fullmatch(NEUTRAL,words,re.I):continue
                    assertion=re.search(r'\bI\s+((?:(?!(?:I|you|we|they|he|she|it)\b)[A-Za-z]+\s+)*'
                                        r'(?:offer|provide)\b.*)',words,re.I)
                    denial=(r'\b(?:no\b(?![-\s]+(?:extra\s+)?(?:cost|charge|fee)\b)|'
                            r'neither\b|never\b|not\b(?!\s+only\b)|none\b)'
                            r'[^.!?;\n]*\b(?:travel|plan\w*|itinerar\w*)\b')
                    if assertion and re.search(denial,assertion[1],re.I):
                        return 'FAIL','travel_capability_denied'
                    status,reason=legacy_semantic(gate,words,locale)
                    if status=='FAIL':return status,reason
                    if re.fullmatch(CAPABILITY,words,re.I):affirmed=True
                    else:unresolved=True
            status,reason=legacy_semantic(gate,plain,locale)
            if status=='FAIL':return status,reason
            if unresolved:return 'UNKNOWN','capability_assertion_unresolved'
            if affirmed:return 'PASS','explicit_travel_capability'
            return 'UNKNOWN','travel_capability_not_affirmed'
    if gate=='SM02'and type(text)is str:
        # Remove styling, never substantive words. Only the two correct known
        # bilingual labels may be collapsed; wrong Chinese names stay visible.
        plain=re.sub(r'[*_`]', '', text)
        for name,chinese in (('Beijing','北京'),('China','中国')):
            plain=re.sub(r'\b'+name+r'\s*[（(]\s*'+chinese+r'\s*[)）]',name,plain,flags=re.I)
        status,reason=legacy_semantic(gate,plain,locale)
        if status!='UNKNOWN'or reason!='capital_semantics_unresolved':return status,reason
        if locale=='en':
            affirmative=(r'^\s*(?:Yes[,!.\s—–-]*)?(?:'
                r'Beijing is (?:the )?capital city of China|'
                r'Beijing is China[’\x27]s capital(?: city)?|'
                r'China[’\x27]s capital(?: city)? is Beijing)(?:[.!]|$)')
        else:
            affirmative=r'^\s*(?:是的[，,。！\s]*)?(?:北京就是中国的?首都|中国的?首都是北京)(?:[。！.!]|$)'
        if re.search(affirmative,plain,re.I):return 'PASS','explicit_equivalent_capital_fact'
        return status,reason
    return legacy_semantic(gate,text,locale)
