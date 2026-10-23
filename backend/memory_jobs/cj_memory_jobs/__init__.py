"""Internal CJ020 candidate. No production source, model or MEMORY write factory."""


def production_queue(*args, **kwargs):
    raise RuntimeError('CJ020 source/dispatch/budget authority unavailable')
