"""The three operator-approved text slots; never execution authority."""
from dataclasses import dataclass, replace
from hashlib import sha256
import re
from types import MappingProxyType

from cj_usage.authorization_budget import canonical
from .real_services import TOOLS

VERSION = 'G2C-runtime-adapter.1'
BASELINE = MappingProxyType({
    'prompt.answer_style': 'Be friendly and concise.',
    'tool.lookup.description': TOOLS[0]['function']['description'],
    'example.clarification': ('If useful, ask at most one optional question and never repeat a question already '
                              'answered.'),
})


@dataclass(frozen=True)
class Candidate:
    fragments: object
    digest: str

    @classmethod
    def parse(cls, value):
        if type(value) is not dict or value.keys() != BASELINE.keys():
            raise ValueError('only the three approved text slots are permitted')
        for text in value.values():
            if type(text) is not str or not text.strip() or '\0' in text:
                raise ValueError('nonempty candidate text required')
            try:
                if len(text.encode('utf-8')) > 4096:
                    raise ValueError('bounded candidate fragment required')
            except UnicodeError as error:
                raise ValueError('candidate text must be UTF-8') from error
        frozen = MappingProxyType(dict(value))
        return cls(frozen, sha256(canonical(dict(frozen))).hexdigest())

    def system(self, original):
        # Replace only literal existing text. Policy, extraction instructions and
        # all other system content retain their exact original bytes.
        slots={BASELINE[key]:key for key in ('prompt.answer_style','example.clarification')}
        pattern=re.compile('|'.join(re.escape(text) for text in slots))
        return pattern.sub(lambda match:self.fragments[slots[match[0]]],original)

    def apply(self, registration, argument):
        if registration == 'model.tool_turn':
            return replace(argument, system=self.system(argument.system),
                           lookup_description=self.fragments['tool.lookup.description'])
        if registration == 'model.answer':
            messages, system, provider = argument
            return messages, self.system(system), provider
        return argument
