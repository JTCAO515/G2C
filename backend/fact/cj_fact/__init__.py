"""CJ FACT internal candidate; not registered as an HTTP route or an agent tool."""
from .model import (VERSION, Assessment, DateRange, Declared, Document, Evidence,
                    Excerpt, Explanation, Query, Result, Status, evaluate)
from .policy import FactFailure, SourcePolicy
from .acquisition import InjectedResponse, PinnedTarget, RestrictedAcquisition, parse_document
from .structured import extract_structured_evidence

__all__ = [
    'VERSION', 'Assessment', 'DateRange', 'Declared', 'Document', 'Evidence',
    'Excerpt', 'Explanation', 'Query', 'Result', 'Status', 'evaluate',
    'FactFailure', 'SourcePolicy', 'InjectedResponse', 'PinnedTarget',
    'RestrictedAcquisition', 'parse_document', 'extract_structured_evidence',
]
