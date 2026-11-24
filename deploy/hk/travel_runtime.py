"""Closed-by-default API composition for the two internal travel relays."""

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
from cj_api.variflight_tools import VariFlight, register_flights
from cj_strict_json import reject_duplicates

from .configuration import QWEATHER_KEY, VARIFLIGHT_MCP_KEY, authorization
from .plugin_roster import generate_plugin_subjects


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
    config = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate travel configuration'))
    if (type(config) is not dict or config.keys() - {'weather_host', 'flights_enabled'}
            or 'weather_host' in config and type(config['weather_host']) is not str
            or 'flights_enabled' in config and type(config['flights_enabled']) is not bool):
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
    routes = (
        ('weather', register_weather, lambda: QWeather(host, weather_key), bool(host and weather_key)),
        ('flights', register_flights, lambda: VariFlight(flights_key), config.get('flights_enabled') is True and bool(flights_key)),
    )
    roster = frozenset(generate_plugin_subjects())
    for name, register, create_service, enabled in routes:
        if enabled:
            try:
                calls = _state(state / (name + '.sqlite'))
                service = GuardedTravel(create_service(), state / (name + '.payment-hold'))
                checker = account_checker_for(auth, database, selected_subjects=roster)
            except (OSError, ValueError):
                LOGGER.warning('travel_provider_unavailable provider=%s', name)
            else:
                register(app, service=service, checker=checker, internal=roster, calls=calls)
                continue
        register(app)
