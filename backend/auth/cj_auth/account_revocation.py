"""ACCOUNT-REVOCATION@1. Additive #27 local account/session invalidation boundary."""
from .interfaces import Fact
from dataclasses import replace


class AccountRevocationAccess:
    """Compose the canonical access facts with a fresh local retirement fence.

    A retired account is no longer a CJ member; other actual facts are preserved,
    never fabricated to turn an unknown provider result into success.
    """
    def __init__(self,base,revocations):self.base,self.revocations=base,revocations

    def evaluate(self,principal):
        facts=self.base.evaluate(principal)
        retired=self.revocations(principal)
        if retired is Fact.NO:return facts
        return replace(facts,member=Fact.NO if retired is Fact.YES else Fact.UNKNOWN)
