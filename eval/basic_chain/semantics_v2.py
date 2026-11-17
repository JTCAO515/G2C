"""Append-only semantic corrections; legacy observation.1 keeps its oracle."""
from hashlib import sha256
import json
from pathlib import Path
import re

from .judge import semantic as legacy_semantic

CODEBANK=json.loads(Path(__file__).with_name('accepted_codebank.v1.json').read_bytes())
QUOTED=re.compile(r'''“[^”\n]*”|‘[^’\n]*’|"[^"\n]*"|(?<!\w)'[^'\n]*'(?!\w)''')


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
                reported=re.search(r'\b(?:the sentence|the phrase)\s*$',prefix,re.I)
                return ' 'if reported and re.search(r'\bI\b',match[0][1:-1],re.I)else match[0][1:-1]
            if QUOTED.fullmatch(styled.strip()):
                return 'UNKNOWN','capability_only_in_quoted_text'
            plain=QUOTED.sub(unquote,styled)
            # A negated offer/provision in the same clause must never become
            # positive through the legacy wildcard. Contrastive clauses remain
            # separate, e.g. no booking services, but I can plan travel.
            clauses=re.split(r'[.!?;\n]|\bbut\b',plain,flags=re.I)
            for clause in clauses:
                assertion=re.search(r'\bI\s+(?:offer|provide)\b(.*)',clause,re.I)
                denial=(r'\b(?:no\b(?![-\s]+(?:extra\s+)?(?:cost|charge|fee)\b)|'
                        r'neither\b|not\b(?!\s+only\b)|none\b)'
                        r'[^.!?;\n]*\b(?:travel|plan\w*|itinerar\w*)\b')
                if assertion and re.search(denial,assertion[1],re.I):
                    return 'FAIL','travel_capability_denied'
            return legacy_semantic(gate,plain,locale)
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
