"""Extra experiment ceilings over the one original M4 journal; no new balance."""
from dataclasses import dataclass

from cj_usage.authorization_budget import CNY_SCALE, LIMITS, authorization_usage
from cj_usage.metered_exit import BudgetUnknown


@dataclass(frozen=True)
class Ceilings:
    provider_calls: int
    tool_calls: int
    model_cny: int
    tool_cny: int
    model_calls: int = 400

    def __post_init__(self):
        for value, maximum in ((self.provider_calls,800),(self.tool_calls,400),(self.model_calls,400),
                               (self.model_cny,50),(self.tool_cny,5)):
            if type(value) is not int or not 1<=value<=maximum:
                raise ValueError('explicit approved experiment ceilings required')

    def check(self, journal, attempt_ids, prospective_kind):
        counts, estimates, holds=authorization_usage(journal,attempt_ids=attempt_ids,include_M1=False)
        # Called within AuthorizationBudget.begin's original SQLite transaction,
        # after its duplicate/global checks and before its one durable INTENT.
        counts[prospective_kind]+=1
        holds[prospective_kind]+=LIMITS[prospective_kind][1]*CNY_SCALE
        if (sum(counts.values())>self.provider_calls or counts['model']>self.model_calls
                or sum(counts[k] for k in LIMITS if k!='model')>self.tool_calls):
            raise BudgetUnknown('original experiment call ceiling reached')
        if estimates['model']+holds['model']>self.model_cny*CNY_SCALE:
            raise BudgetUnknown('original experiment model ceiling reached')
        if sum(estimates[k]+holds[k] for k in LIMITS if k!='model')>self.tool_cny*CNY_SCALE:
            raise BudgetUnknown('original experiment tool ceiling reached')
