"""Metadata-only public health probe; never authenticates or sends business work."""
from datetime import datetime, timedelta, timezone
import http.client
import json
import ssl
import sys
import time

HOST = 'api-beta.go2china.space'
ROUTES = (('/health/live', 'alive'), ('/health/ready', 'ready'))
MAX_BODY = 4096
ENDS_AT = datetime(2027, 1, 1, tzinfo=timezone(timedelta(hours=8)))


class ProbeFailure(Exception):
    """A safe failure category, without response text or transport exception text."""


def validate_response(status, content_type, body, expected):
    if status != 200:
        raise ProbeFailure('http_status')
    if content_type.split(';', 1)[0].strip().lower() != 'application/json':
        raise ProbeFailure('content_type')
    if len(body) > MAX_BODY:
        raise ProbeFailure('response_too_large')
    try:
        value = json.loads(body)
    except ValueError:
        raise ProbeFailure('invalid_json') from None
    if type(value) is not dict or value.get('status') != expected:
        raise ProbeFailure('health_state')


def get(route, expected):
    connection = http.client.HTTPSConnection(
        HOST, timeout=10, context=ssl.create_default_context())
    started = time.monotonic()
    try:
        connection.request('GET', route, headers={
            'Accept': 'application/json', 'User-Agent': 'G2C-readiness-monitor/1'})
        response = connection.getresponse()
        validate_response(response.status, response.getheader('Content-Type', ''),
                          response.read(MAX_BODY + 1), expected)
    except (OSError, http.client.HTTPException):
        raise ProbeFailure('transport') from None
    finally:
        connection.close()
    return dict(route=route, status=200,
                duration_ms=round((time.monotonic() - started) * 1000, 3))


def utcnow():
    return datetime.now(timezone.utc)


def inactive_state(now):
    local = now.astimezone(timezone(timedelta(hours=8)))
    if local >= ENDS_AT:
        return 'SKIPPED_EXPIRED'
    return None


def run(clock=utcnow, fetch=get, *, notification_drill=False):
    """Recheck authorization expiry immediately before every new GET."""
    now = clock()
    result = dict(version='G2C-public-readiness-observation.1',
                  observed_at=now.isoformat(), observations=[],
                  provider_calls=0, business_requests=0)
    inactive = inactive_state(now)
    if inactive:
        return dict(result, state=inactive), 0
    if notification_drill:
        return dict(result, state='ALERT_TRANSPORT_DRILL_NO_SERVER_REQUEST'), 1
    for route, expected in ROUTES:
        current = clock()
        inactive = inactive_state(current)
        if inactive:
            return dict(result, state=inactive, stopped_at=current.isoformat()), 0
        try:
            result['observations'].append(fetch(route, expected))
        except ProbeFailure as error:
            return dict(result, state='HEALTH_PROBE_FAILED', route=route,
                        category=str(error)), 1
    return dict(result, state='PUBLIC_HEALTH_OBSERVED'), 0


def main():
    if sys.argv[1:] not in ([], ['--notification-drill']):
        raise SystemExit('only --notification-drill is supported')
    result, code = run(notification_drill='--notification-drill' in sys.argv)
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
