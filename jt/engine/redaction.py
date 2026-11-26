"""Versioned, local redaction for a single conversation at a time."""

import re


REDACTION_VERSION = "1"

_HALFWIDTH = str.maketrans(
    {**{code: code - 0xFEE0 for code in range(0xFF01, 0xFF5F)}, 0x3000: " "}
)
_EXISTING_PLACEHOLDER = re.compile(r"<(?:EMAIL|PASSPORT|PHONE|LOCATION|NAME)_[1-9][0-9]*>")
_SPACE = r"[ \t]"
_VALUE_GAP = rf"{_SPACE}*(?:\r?\n{_SPACE}*)?"
_FIELD_SEPARATOR = rf"{_SPACE}*(?:[:#=]{_SPACE}*|{_SPACE})"
_END_ID = r"(?![A-Za-z0-9]|\.[0-9])"
_START_NUMBER = r"(?<![A-Za-z0-9.+@])"

_LETTER = r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ſ]"
_NAME_WORD = rf"{_LETTER}+(?:['’\-]{_LETTER}+)*"
_NAME_STOP = (
    r"(?i:\b(?:and|at|currently|email|from|here|i|in|is|my|n/a|name|none|not|now|"
    r"passport|phone|please|the|today|tomorrow|unknown|was|with)\b)"
)
_LATIN_NAME = rf"(?!{_NAME_STOP}){_NAME_WORD}(?:{_SPACE}+(?!{_NAME_STOP}){_NAME_WORD}){{0,4}}"
_HAN = r"[\u3400-\u9fff]"
_HAN_NAME = (
    rf"{_HAN}{{2,4}}?(?=我?(?:今天|明天|现在|現在|正在|刚才|剛才|迷路|走失|遇险|遇險|"
    rf"受伤|受傷|被困|需要|急需|救命|求救)|(?:和|跟|与|與)(?:朋友|同伴|家人|家属|家屬|同事))"
    rf"|{_HAN}{{2,4}}(?!{_HAN})|"
    rf"{_HAN}{{2,4}}?(?=在|住|的|请|請|我|他|她)"
)
_NAME_LABEL = (
    rf"(?i:\b(?:my name is|(?:travell?er |guest |full )?name{_SPACE}*[:=]))"
    rf"|(?:我的(?:姓名|名字)是|我叫(?![了过到好和])|(?:姓名|名字){_SPACE}*[:=])"
)

_CN_MOBILE = r"(?:\+?86[ -]?)?1[3-9][0-9](?:[ -]?[0-9]{4}){2}"
_CN_LANDLINE = r"(?:\(0[1-9][0-9]{1,2}\)[ -]?|0[1-9][0-9]{1,2}[ -])[1-9][0-9]{2,3}[ -]?[0-9]{4}"
_NORTH_AMERICAN_PHONE = r"(?:\+?1[ .-]?)?(?:\([2-9][0-9]{2}\)|[2-9][0-9]{2})[ .-]?[0-9]{3}[ .-]?[0-9]{4}"
_INTERNATIONAL_PHONE = r"\+(?:[0-9][ .()-]{0,2}){6,14}[0-9]"
_LABELED_PHONE = r"[0-9](?:[ .-]?[0-9]){6,14}"

_LATITUDE = r"[+-]?(?:[0-8]?[0-9]\.[0-9]{3,}|90\.0{3,})"
_LONGITUDE = r"[+-]?(?:(?:[0-9]{1,2}|1[0-7][0-9])\.[0-9]{3,}|180\.0{3,})"
_COMMA = rf"{_SPACE}*,{_SPACE}*"
_COORDINATES = rf"(?:{_LATITUDE}{_COMMA}{_LONGITUDE}|{_LONGITUDE}{_COMMA}{_LATITUDE})"
_CN_ADDRESS = (
    rf"{_HAN}{{1,28}}?(?:路|街|大道|道|巷|弄){_SPACE}*[0-9]{{1,6}}[号號]"
    rf"(?:{_SPACE}*(?:[0-9]{{1,6}}(?:栋|棟|幢|座|单元|單元|楼|樓|层|層|室|房)|[A-Za-z]座)){{0,5}}"
)
_CN_LOCATION_LABEL = (
    rf"(?:现址|地址|位置|定位){_FIELD_SEPARATOR}|(?:我在|我住在|住在|位于){_SPACE}*"
)
_STREET = (
    rf"[0-9]{{1,6}}{_SPACE}+(?:[A-Za-z0-9.'’-]+{_SPACE}+){{1,6}}"
    r"(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd|way)\b\.?"
)
_UNIT = rf"(?:room|suite|unit|apartment|apt\.?){_SPACE}*[:#]?{_SPACE}*[0-9]{{1,6}}[a-z]?\b"

# Each pattern captures only the sensitive value. Labels and unrelated text stay intact.
_RULES = (
    (
        "EMAIL",
        re.compile(
            r"(?<![A-Z0-9_.+%-])([A-Z0-9.!#$%&'*+/=?^_\x60{|}~-]+@"
            r"(?:[A-Z0-9-]+\.)+[A-Z]{2,63})(?![A-Z0-9-])",
            re.IGNORECASE,
        ),
    ),
    (
        "PASSPORT",
        re.compile(
            rf"(?:\bpassport(?:{_SPACE}+(?:number|no\.?|id))?|护照(?:号码|号|编号)?|護照(?:號碼|號|編號)?)"
            rf"{_SPACE}*(?:(?:\bis\b|是|为|為){_SPACE}*)?(?:#{_SPACE}*)?[:=]?{_VALUE_GAP}"
            r"((?=[A-Z0-9]{0,11}[0-9])[A-Z0-9]{6,12})(?![A-Z0-9])",
            re.IGNORECASE,
        ),
    ),
    (
        "PHONE",
        re.compile(
            rf"{_START_NUMBER}({_CN_MOBILE}|{_CN_LANDLINE}|{_NORTH_AMERICAN_PHONE}|"
            rf"{_INTERNATIONAL_PHONE}){_END_ID}"
        ),
    ),
    (
        "PHONE",
        re.compile(
            rf"(?:\b(?:phone(?:{_SPACE}+number)?|mobile|tel\.?)|手机(?:号码|号)|手機(?:號碼|號)"
            r"|电话(?:号码)?|電話(?:號碼)?)"
            rf"{_FIELD_SEPARATOR}({_LABELED_PHONE}){_END_ID}",
            re.IGNORECASE,
        ),
    ),
    (
        "LOCATION",
        re.compile(rf"(?<![0-9.+-])({_COORDINATES}){_END_ID}"),
    ),
    (
        "LOCATION",
        re.compile(
            rf"{_START_NUMBER}({_STREET}(?:{_SPACE}*,?{_SPACE}+{_UNIT})?)(?![A-Za-z0-9])",
            re.IGNORECASE,
        ),
    ),
    (
        "LOCATION",
        re.compile(rf"(?:{_CN_LOCATION_LABEL}|(?<!{_HAN}))({_CN_ADDRESS})", re.IGNORECASE),
    ),
    (
        "LOCATION",
        re.compile(
            rf"(\b{_UNIT}|(?:房间|房間|客房|房号|房號){_SPACE}*[:#]?{_SPACE}*[0-9]{{1,6}}(?:号|號|室)?)",
            re.IGNORECASE,
        ),
    ),
    (
        "NAME",
        re.compile(rf"(?:{_NAME_LABEL}){_VALUE_GAP}({_HAN_NAME}|{_LATIN_NAME})"),
    ),
)


def _sensitive_spans(
    text: str, placeholders: dict[str, dict[str, str]]
) -> list[tuple[int, int, str]]:
    matches = [
        (match.start(1), -match.end(1), kind)
        for kind, pattern in _RULES
        for match in pattern.finditer(text)
    ]
    # Once identified, a name or passport number can recur without a field label.
    for kind, boundary in (("NAME", _LETTER), ("PASSPORT", r"[A-Za-z0-9]")):
        values = set(placeholders.get(kind, ()))
        values.update(text[start:-end] for start, end, label in matches if label == kind)
        for value in values:
            literal = r"[ \t]+".join(map(re.escape, value.split()))
            for match in re.finditer(rf"(?<!{boundary}){literal}(?!{boundary})", text, re.IGNORECASE):
                matches.append((match.start(), -match.end(), kind))

    spans: list[tuple[int, int, str]] = []
    for start, negative_end, kind in sorted(matches):
        end = -negative_end
        if spans and start < spans[-1][1]:
            previous_start, previous_end, previous_kind = spans[-1]
            # Mask the union so an overlapping match cannot leave a sensitive suffix.
            spans[-1] = previous_start, max(previous_end, end), previous_kind
        else:
            spans.append((start, end, kind))
    return spans


class ConversationRedactor:
    """Reuse for the turns of one conversation, then discard with its in-memory state.

    Names and passport numbers require identifying context because their bare forms
    can also be ordinary words or unrelated references. This version recognizes
    common contact, street, room and decimal-coordinate formats in synthetic text.
    """

    def __init__(self) -> None:
        self._placeholders: dict[str, dict[str, str]] = {}

    def redact(self, text: str) -> str:
        # Width conversion preserves offsets and is only used for detection and keys.
        searchable = text.translate(_HALFWIDTH)
        searchable = _EXISTING_PLACEHOLDER.sub(lambda match: "_" * len(match[0]), searchable)
        output: list[str] = []
        cursor = 0
        for start, end, kind in _sensitive_spans(searchable, self._placeholders):
            value = searchable[start:end]
            if kind == "PHONE":
                key = re.sub(r"[^0-9]", "", value)
                if re.fullmatch(r"861[3-9][0-9]{9}", key):
                    key = key[2:]
                elif re.match(r"\+1|1[ .-]", value) and re.fullmatch(r"1[2-9][0-9]{9}", key):
                    key = key[1:]
            else:
                key = " ".join(value.casefold().split())
                if kind == "LOCATION":
                    key = re.sub(_COMMA, ",", key)
            placeholders = self._placeholders.setdefault(kind, {})
            if key not in placeholders:
                placeholders[key] = f"<{kind}_{len(placeholders) + 1}>"
            output.extend((text[cursor:start], placeholders[key]))
            cursor = end
        output.append(text[cursor:])
        return "".join(output)
