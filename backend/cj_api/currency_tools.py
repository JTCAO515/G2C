"""Read and cache the ECB's published euro reference rates for internal testers."""

from contextlib import closing
from datetime import datetime, timedelta
from decimal import Decimal
from http.client import HTTPException, HTTPSConnection
import json
import re
import sqlite3
from typing import Literal
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from .plugin_tools import PluginError, register_plugin
from .taxi_tools import WireModel


VERSION = 'CURRENCY.1'
ROUTE = '/v1/tools/currency/rates'
ECB_HOST = 'www.ecb.europa.eu'
ECB_DAILY = '/stats/eurofxref/eurofxref-daily.xml'
ECB_ZONE = ZoneInfo('Europe/Berlin')
ECB_XML = '{http://www.ecb.int/vocabulary/2002-08-01/eurofxref}Cube'
MAX_RESPONSE = 65536
CURRENCY = re.compile('[A-Z]{3}')
RATE = re.compile(r'[0-9]{1,9}(?:\.[0-9]{1,12})?')


class CurrencyRequest(WireModel):
    version: Literal['CURRENCY.1']


def read_ecb():
    try:
        with closing(HTTPSConnection(ECB_HOST, timeout=8)) as connection:
            connection.request('GET', ECB_DAILY, headers={'Accept': 'application/xml'})
            with closing(connection.getresponse()) as response:
                if response.status != 200:
                    raise PluginError(502, 'supplier_unavailable')
                return response.read(MAX_RESPONSE + 1)
    except TimeoutError:
        raise PluginError(504, 'supplier_timeout') from None
    except (OSError, HTTPException):
        raise PluginError(502, 'supplier_unavailable') from None


def ecb_snapshot(raw, today):
    try:
        if len(raw) > MAX_RESPONSE or b'<!' in raw:
            raise ValueError('unsafe ECB document')
        entry, = ElementTree.fromstring(raw).findall(f'./{ECB_XML}/{ECB_XML}')
        published = datetime.strptime(entry.attrib['time'], '%Y-%m-%d').date()
        if published > today:
            raise ValueError('future ECB reference date')
        rates = {'EUR': '1'}
        for row in entry:
            code, rate = row.attrib['currency'], row.attrib['rate']
            if (row.tag != ECB_XML or code in rates or not CURRENCY.fullmatch(code)
                    or not RATE.fullmatch(rate) or Decimal(rate) <= 0):
                raise ValueError('invalid ECB reference rate')
            rates[code] = rate
        if 'CNY' not in rates:
            raise ValueError('ECB reference rates omit CNY')
    except (ElementTree.ParseError, KeyError, ValueError):
        raise PluginError(502, 'supplier_unavailable') from None
    return dict(version=VERSION, source='ECB', base='EUR', date=published.isoformat(), rates=rates)


class CurrencyRates:
    def __init__(self, state_path, *, fetch=read_ecb, clock=lambda: datetime.now(ECB_ZONE)):
        self.state_uri = state_path.absolute().as_uri() + '?mode=rw'
        self.fetch = fetch
        self.clock = clock

    def rates(self, _request, reserve):
        now = self.clock().astimezone(ECB_ZONE)
        window = (now - timedelta(hours=17)).date().isoformat()
        try:
            with closing(sqlite3.connect(self.state_uri, uri=True)) as db:
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS ecb_rates (window TEXT PRIMARY KEY, snapshot TEXT)')
                    fresh = db.execute('INSERT OR IGNORE INTO ecb_rates VALUES (?,NULL)', (window,)).rowcount
                if not fresh:
                    stored, = db.execute('SELECT snapshot FROM ecb_rates WHERE window=?', (window,)).fetchone()
                    if stored is None:
                        raise PluginError(503, 'unavailable')
                    return json.loads(stored)

                reserve('ecb:daily_reference', None)
                result = ecb_snapshot(self.fetch(), now.date())
                with db:
                    db.execute('UPDATE ecb_rates SET snapshot=? WHERE window=? AND snapshot IS NULL',
                               (json.dumps(result), window))
                return result
        except (sqlite3.Error, json.JSONDecodeError):
            raise PluginError(503, 'unavailable') from None


def register_currency_route(app, *, currency=None, checker=None, internal=frozenset(), calls=None):
    register_plugin(app, ROUTE, CurrencyRequest, currency.rates if currency else None, enabled=currency is not None,
                    checker=checker, internal=internal, calls=calls, limit=None, count_provider_calls=True)
