"""Explicit automatic host: extend the existing serialized metadata inspection."""
from .decision_service import DecisionCollectionService


class AutomaticDecisionCollectionService(DecisionCollectionService):
    def _invalid_serialized(self,context,token,principal,repository):
        # The existing public Trip/Message comparisons prove that these old
        # originals cannot publish. Keep their rows/IDs/UNKNOWN fees untouched.
        return self._invalid_originals(context,token,principal,repository)
