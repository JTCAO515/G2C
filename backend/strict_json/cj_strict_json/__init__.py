"""Strict JSON decoding and compact encoding shared by every domain. Depends on nothing else here."""
import json


def reject_duplicates(error, *args):
    """object_pairs_hook refusing a repeated key with the caller's own failure.

    json.loads otherwise keeps the last value silently, so two readers of the
    same bytes could disagree about a field.
    """
    def hook(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise error(*args)
            result[key] = value
        return result
    return hook


def compact(value, *, sort_keys=False, ensure_ascii=False, allow_nan=False):
    """UTF-8 bytes with no insignificant whitespace; the one compact JSON encoder.

    Stored and hashed bytes depend on the three options, so each caller states the
    ones its format fixed. Non-finite numbers are rejected unless allow_nan is set.
    """
    return json.dumps(value, ensure_ascii=ensure_ascii, sort_keys=sort_keys,
                      separators=(',', ':'), allow_nan=allow_nan).encode('utf-8')
