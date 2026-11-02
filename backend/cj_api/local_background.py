"""Explicit local background host, injected into the original run_once only."""
from pathlib import Path
import os
from cj_auth.interfaces import AdmissionStatus
from cj_run.background import BackgroundJobs
from .composition import CompositionUnavailable


class FilteredCollectionAdapter:
    """Explicit C DATA/EXTRACT@2 bindings; old unfiltered methods never fallback."""
    def __init__(self,collection):
        from cj_memory_jobs.model_v2 import NoEligibleSource
        self.processing_policy=collection.processing_policy_v2
        self.publication_policy=collection.publication_policy_v2
        self.query_publication_in_context=collection.query_publication_v2_in_context
        self.transition_original_in_context=collection.transition_original_in_context
        self.no_eligible_error=NoEligibleSource


class LocalBackgroundHost:
    def __init__(self,jobs:BackgroundJobs,auth_dir):
        if os.environ.get('CJ_ENV')!='local':raise CompositionUnavailable('local background host required')
        self.jobs,self.auth_dir=jobs,Path(auth_dir)

    def run_once(self,provider):
        # Same explicit synthetic-local invitation/signing source as MESSAGE's
        # existing worker. No second identity, provider or quota engine.
        import dev_auth
        from run_worker import invited_subjects
        results=[]
        for subject in sorted(invited_subjects(self.auth_dir)):
            token=dev_auth.token(self.auth_dir,subject,5)
            decision=self.jobs.boundary.checker.check(token)
            if decision.status is AdmissionStatus.DENIED:continue
            if decision.status is not AdmissionStatus.ALLOWED:raise CompositionUnavailable('background admission unknown')
            results.extend(self.jobs.run_once(token,provider))
        return results
