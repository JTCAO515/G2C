"""Worker side of TRANSPORT.1 trains (#1520): one metered AMap cross-city transit call per search.

Runs only in the HK worker, which holds the AMap web key and the AMap cash journal (M4 entry 12 item 4).
The API process reaches it through the private relay (deploy/hk, S line) and gets `rail_items` back.
"""

from datetime import date
from uuid import UUID

from cj_usage.metered_exit import BudgetUnknown
from cj_usage.transit_budget import OPERATIONS, TransitDuplicate, TransitLimit

from .lio_transport import CITIES, DATE, rail_items
from .nearby_tools import GaodeNearby
from .plugin_tools import PluginError


def transit_provider(key, **options):
    """The bounded AMap transport of Nearby and hotel search, limited to the transit operation."""
    return GaodeNearby(key, operations=OPERATIONS, **options)


class TransitRailService:
    def __init__(self, provider, budget):
        self.provider = provider
        self.budget = budget

    def trains(self, scope, request_id, origin_id, destination_id, day, authorize):
        origin, destination = CITIES.get(origin_id), CITIES.get(destination_id)
        if type(request_id) is not str:
            raise PluginError(400, 'invalid_request')
        try:
            request = UUID(request_id)
            valid_day = type(day) is str and DATE.fullmatch(day) is not None and date.fromisoformat(day)
        except (TypeError, ValueError):
            raise PluginError(400, 'invalid_request') from None
        if origin is None or destination is None or origin == destination or not valid_day:
            raise PluginError(400, 'invalid_request')
        params = dict(origin='%.6f,%.6f' % origin.centre, destination='%.6f,%.6f' % destination.centre,
                      city=origin.name_zh, cityd=destination.name_zh, date=day, time='08:00',
                      strategy='0', nightflag='1', extensions='base')
        reservation = None

        def before_send():
            nonlocal reservation
            authorize()
            reservation = self.budget.begin(scope, request, 'transit')

        try:
            value, raw = self.provider.query('transit', params, before_send)
        except TransitLimit:
            raise PluginError(429, 'quota_exceeded') from None
        except TransitDuplicate:
            raise PluginError(409, 'request_already_used') from None
        except BudgetUnknown:
            raise PluginError(503, 'unavailable') from None
        self.budget.finish(reservation, raw)
        try:
            return rail_items(value)
        except (AttributeError, KeyError, TypeError, ValueError):
            raise PluginError(502, 'supplier_unavailable') from None
