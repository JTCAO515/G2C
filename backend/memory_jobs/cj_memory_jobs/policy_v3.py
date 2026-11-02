"""Explicit final-publication check, after filtered/source/auth tail work."""
from .policy_v2 import ResultSourcePolicyV2


class ResultSourcePolicyV3(ResultSourcePolicyV2):
    def __init__(self,*args,before_commit,**kwargs):
        if before_commit is None:raise ValueError('explicit final publication check required')
        super().__init__(*args,**kwargs)
        self.check_before_commit=before_commit

    def _before_commit(self):
        # No C query, render, authority or asynchronous work follows this check
        # before Repository.transaction attempts the canonical MEMORY COMMIT.
        self.check_before_commit()
