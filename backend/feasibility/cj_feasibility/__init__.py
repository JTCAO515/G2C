"""Read-only deterministic checks over explicitly supplied NEEDS revisions."""
from .validator import Candidate, Check, Evidence, Report, evaluate, protect

__all__ = ['Candidate', 'Check', 'Evidence', 'Report', 'evaluate', 'protect']
