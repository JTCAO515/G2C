"""Closed-by-default API composition for the internal travel relays (weather, flights, transport)."""

from pathlib import Path
from threading import Lock
import json
import logging
import os
import stat

from cj_api.local_account_admission_v2 import account_checker_for
from cj_api.plugin_tools import PluginCalls, PluginError
from cj_api.qweather_tools import QWeather, register_weather
from cj_api.travel_provider import SupplierPaymentRequired
from cj_api.lio_transport import TransportService, register_transport
from cj_api.variflight_tools import VariFlight, register_flights
from cj_strict_json import reject_duplicates

from .configuration import QWEATHER_KEY, VARIFLIGHT_MCP_KEY, authorization
from .plugin_roster import generate_plugin_subjects
from .transit_relay import TransitRelayClient


CONFIG = Path('/control/travel-providers.json')
STATE = Path('/plugin-state')
LOGGER = logging.getLogger(__name__)


def _config(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('root-owned travel config required')
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError('unbounded travel configuration')
    return _validated(json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate travel configuration')))


def _validated(config):
    if (type(config) is not dict or config.keys() - {'weather_host', 'flights_enabled', 'transport_enabled'}
            or 'weather_host' in config and type(config['weather_host']) is not str
            or any(key in config and type(config[key]) is not bool for key in ('flights_enabled', 'transport_enabled'))):
        raise ValueError('invalid travel configuration')
    return config


def _state(path):
    directory, entry = path.parent.lstat(), path.lstat()
    if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid()
            or stat.S_IMODE(directory.st_mode) != 0o700
            or not stat.S_ISREG(entry.st_mode) or entry.st_uid != os.getuid()
            or stat.S_IMODE(entry.st_mode) != 0o600 or entry.st_nlink != 1):
        raise ValueError('private travel count state required')
    return PluginCalls(path, require_existing=True)


class GuardedTravel:
    def __init__(self, service, hold):
        self.service, self.hold = service, hold
        self.stopped = os.path.lexists(hold)
        self.lock = Lock()

    def query(self, request, reserve):
        with self.lock:
            if self.stopped or os.path.lexists(self.hold):
                raise PluginError(503, 'not_enabled')
            try:
                authorization()
            except (OSError, ValueError):
                raise PluginError(503, 'not_enabled') from None
            try:
                return self.service.query(request, reserve)
            except SupplierPaymentRequired:
                self.stopped = True
                try:
                    descriptor = os.open(self.hold, os.O_WRONLY | os.O_NOFOLLOW | os.O_CREAT | os.O_EXCL, 0o600)
                    os.close(descriptor)
                    directory = os.open(self.hold.parent, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                except FileExistsError:
                    pass
                except OSError:
                    LOGGER.error('travel_payment_hold_persistence_failed')
                LOGGER.warning('travel_provider_payment_hold provider=%s', self.hold.stem)
                raise


def register_runtime_travel(app, auth, database, *, config_path=CONFIG, state=STATE):
    try:
        config = _config(config_path)
    except FileNotFoundError:
        config = {}
    except (OSError, ValueError, RecursionError):
        LOGGER.warning('travel_provider_configuration_unavailable')
        config = {}

    host = config.get('weather_host')
    weather_key = os.environ.get(QWEATHER_KEY)
    flights_key = os.environ.get(VARIFLIGHT_MCP_KEY)
    roster = frozenset(generate_plugin_subjects())
    checker = None

    def admitted():
        nonlocal checker
        if checker is None:
            checker = account_checker_for(auth, database, selected_subjects=roster)
        return checker

    if host and weather_key:
        try:
            calls = _state(state / 'weather.sqlite')
            service = GuardedTravel(QWeather(host, weather_key), state / 'weather.payment-hold')
            register_weather(app, service=service, checker=admitted(), internal=roster, calls=calls)
        except (OSError, ValueError):
            LOGGER.warning('travel_provider_unavailable provider=%s', 'weather')
            register_weather(app)
    else:
        register_weather(app)

    # Flights and the transport route's flight mode share one VariFlight client, one per-account counter
    # (`flights.sqlite`, the FLIGHTS.1 operation name: 50 a day together, M4 item 14) and one payment hold:
    # a 402 on either stops both.
    flights = flight_calls = None
    if flights_key and (config.get('flights_enabled') is True or config.get('transport_enabled') is True):
        try:
            flight_calls = _state(state / 'flights.sqlite')
            flights = GuardedTravel(VariFlight(flights_key), state / 'flights.payment-hold')
        except (OSError, ValueError):
            LOGGER.warning('travel_provider_unavailable provider=%s', 'flights')
            flights = flight_calls = None
    if config.get('flights_enabled') is True and flights is not None:
        register_flights(app, service=flights, checker=admitted(), internal=roster, calls=flight_calls)
    else:
        register_flights(app)

    if config.get('transport_enabled') is True:
        try:
            calls = flight_calls if flight_calls is not None else _state(state / 'flights.sqlite')
        except (OSError, ValueError):
            LOGGER.warning('travel_provider_unavailable provider=%s', 'transport')
            register_transport(app)
        else:
            # Trains go through the worker's metered AMap relay with the caller's own bearer; the worker
            # answers not_enabled until its transit roster is configured.
            service = TransportService(rail=TransitRelayClient(), flights=flights)
            register_transport(app, service=service, checker=admitted(), internal=roster, calls=calls)
    else:
        register_transport(app)
