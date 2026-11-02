"""Strict JSON decoding shared by every domain boundary. Depends on nothing else here."""


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
