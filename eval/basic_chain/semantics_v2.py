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
            # Reported first-person clauses are not the assistant's assertion.
            # Quoted topic names remain words; contractions are not quote starts.
            plain=QUOTED.sub(lambda m:' 'if re.search(r'\bI\b',m[0][1:-1],re.I)else m[0][1:-1],styled)
            denial=r'\bI\s+(?:offer|provide)\s+no\s+travel\s+(?:assistance|planning\s+services?)\b'
            if re.search(denial,plain,re.I):return 'FAIL','travel_capability_denied'
            if not plain.strip()and styled.strip():return 'UNKNOWN','capability_only_in_quoted_text'
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
