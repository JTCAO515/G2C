"""Additive structured.2 adapter to the original explicit-time checker."""
from cj_trip.structured_v2 import validate_document
from .trip_time import _evaluate

VERSION='FEASIBILITY-TRIP@2.0'


def evaluate(content):
    return _evaluate(content,validate_document,VERSION)
