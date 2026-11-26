"""Host alerts for the HK synthetic beta: daily-backup heartbeat and disk (#1720).

Runs with the host's own python3 (Alibaba Cloud Linux ships 3.6), stdlib only,
so it keeps working when Docker or the application images do not.

    python3 deploy/hk/ops_alerts.py backup-succeeded   # ExecStartPost of the backup unit
    python3 deploy/hk/ops_alerts.py check              # every 15 minutes from its timer
    python3 deploy/hk/ops_alerts.py drill              # one explicit test notification
    python3 deploy/hk/ops_alerts.py probe-transition <outcome> <previous>   # GitHub probe job

The notification channel is configuration, not code: ``/srv/g2c-beta/ops/alert.env``
(root:0600) holds ``ALERT_CHANNEL`` (``none`` or ``webhook``), and for a webhook
``ALERT_WEBHOOK_URL`` (https only) and ``ALERT_WEBHOOK_FORMAT`` (``text``,
``wecom``, ``feishu`` or ``dingtalk``). Thresholds are optional overrides. With
``none`` (the default until JT picks a channel) alerts go to the journal as
``ALERT ...`` lines and ``check`` exits 1, so the unit shows as failed.

A condition notifies when it starts, every ``ALERT_REMIND_HOURS`` while it lasts,
and once when it clears. Messages carry only the condition and a number:
never URLs, keys, subjects or file contents.
"""
import http.client
import json
import os
import shutil
import ssl
import sys
import time
import urllib.request

ROOT = '/srv/g2c-beta'
OPS = os.path.join(ROOT, 'ops')
CONFIG = os.path.join(OPS, 'alert.env')
HEARTBEAT = os.path.join(OPS, 'backup-heartbeat.json')
STATE = os.path.join(OPS, 'alert-state.json')
HOST = 'api-beta'
FORMATS = ('text', 'wecom', 'feishu', 'dingtalk')
DEFAULTS = dict(ALERT_CHANNEL='none', ALERT_WEBHOOK_URL='', ALERT_WEBHOOK_FORMAT='text',
                ALERT_BACKUP_MAX_HOURS='27', ALERT_DISK_PERCENT='85', ALERT_DISK_PATHS='/',
                ALERT_REMIND_HOURS='6')
MAX_MESSAGE = 1000


class ConfigError(ValueError):
    pass


def load_config(path=CONFIG, environ=None):
    """Strict KEY=VALUE file; unknown keys and malformed values fail closed."""
    values = dict(DEFAULTS)
    if path is not None and os.path.lexists(path):
        info = os.lstat(path)
        if not os.path.isfile(path) or os.path.islink(path) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ConfigError('private_alert_config_required')
        with open(path, encoding='utf-8') as source:
            for number, line in enumerate(source, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                key, separator, value = line.partition('=')
                if not separator or key not in DEFAULTS:
                    raise ConfigError('unknown_alert_config_line_%d' % number)
                values[key] = value
    for key in DEFAULTS:
        if environ and key in environ:
            values[key] = environ[key]
    if values['ALERT_CHANNEL'] not in ('none', 'webhook'):
        raise ConfigError('alert_channel_must_be_none_or_webhook')
    if values['ALERT_CHANNEL'] == 'webhook':
        url = values['ALERT_WEBHOOK_URL']
        if not url.startswith('https://') or len(url) > 2048 or any(c.isspace() for c in url):
            raise ConfigError('https_webhook_url_required')
        if values['ALERT_WEBHOOK_FORMAT'] not in FORMATS:
            raise ConfigError('known_webhook_format_required')
    try:
        backup = float(values['ALERT_BACKUP_MAX_HOURS'])
        disk = float(values['ALERT_DISK_PERCENT'])
        remind = float(values['ALERT_REMIND_HOURS'])
    except ValueError:
        raise ConfigError('numeric_alert_thresholds_required') from None
    paths = [p for p in values['ALERT_DISK_PATHS'].split(',') if p]
    if not 1 <= backup <= 24 * 7 or not 50 <= disk <= 99 or not 1 <= remind <= 48 or not paths \
            or any(not p.startswith('/') for p in paths):
        raise ConfigError('bounded_alert_thresholds_required')
    values.update(backup_max_seconds=backup * 3600, disk_percent=disk, remind_seconds=remind * 3600, disk_paths=paths)
    return values


def payload(fmt, text):
    text = text[:MAX_MESSAGE]
    if fmt == 'wecom':
        return dict(msgtype='text', text=dict(content=text))
    if fmt == 'feishu':
        return dict(msg_type='text', content=dict(text=text))
    if fmt == 'dingtalk':
        return dict(msgtype='text', text=dict(content=text))
    return dict(text=text)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def send(config, text, opener=None):
    """Deliver one message; returns a short delivery label, never the URL."""
    if config['ALERT_CHANNEL'] == 'none':
        sys.stderr.write('ALERT ' + text.replace('\n', ' | ') + '\n')
        return 'journal_only'
    body = json.dumps(payload(config['ALERT_WEBHOOK_FORMAT'], text), ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(config['ALERT_WEBHOOK_URL'], data=body, method='POST',
                                     headers={'Content-Type': 'application/json; charset=utf-8'})
    opener = opener or urllib.request.build_opener(
        _NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(request, timeout=10) as response:
            response.read(4096)
            if not 200 <= response.status < 300:
                raise OSError('webhook_status')
    except (OSError, ValueError, http.client.HTTPException):
        sys.stderr.write('ALERT alert_delivery_failed ' + text.replace('\n', ' | ') + '\n')
        return 'delivery_failed'
    return 'delivered'


def _atomic_json(path, value):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    temporary = '%s.%d.tmp' % (path, os.getpid())
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        json.dump(value, output, sort_keys=True)
        output.flush()
        os.fsync(output.fileno())
    os.rename(temporary, path)


def _read_json(path):
    try:
        with open(path, encoding='utf-8') as source:
            value = json.load(source)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def backup_succeeded(now=None, path=HEARTBEAT):
    _atomic_json(path, dict(version='g2c-beta-backup-heartbeat.1', succeeded_at=int(now or time.time())))


def conditions(config, now, heartbeat_path=HEARTBEAT, usage=shutil.disk_usage):
    """Current alert conditions as {key: message}; an empty dict means all clear."""
    found = {}
    beat = _read_json(heartbeat_path)
    stamp = beat.get('succeeded_at') if beat and beat.get('version') == 'g2c-beta-backup-heartbeat.1' else None
    if not isinstance(stamp, int) or isinstance(stamp, bool):
        found['backup_heartbeat'] = 'Daily backup: no success heartbeat recorded'
    elif now - stamp > config['backup_max_seconds']:
        found['backup_heartbeat'] = 'Daily backup: last success %.1f hours ago' % ((now - stamp) / 3600)
    for path in config['disk_paths']:
        try:
            total, used, _ = usage(path)
        except OSError:
            found['disk:' + path] = 'Disk %s: usage unreadable' % path
            continue
        percent = 100.0 * used / total if total else 100.0
        if percent >= config['disk_percent']:
            found['disk:' + path] = 'Disk %s: %.0f%% used (threshold %.0f%%)' % (path, percent, config['disk_percent'])
    return found


def check(config, now=None, state_path=STATE, deliver=send, **probes):
    """Notify on start, on reminder interval and on clear.

    Returns (active alerts, failed deliveries). A failed delivery is not recorded
    as notified: the start or recovery message is retried on the next check.
    """
    now = int(now or time.time())
    active = conditions(config, now, **probes)
    previous = _read_json(state_path) or {}
    previous = previous.get('alerts') if isinstance(previous.get('alerts'), dict) else {}
    state = {}
    failed = 0
    for key, message in sorted(active.items()):
        last = previous.get(key)
        sent = last.get('notified_at') if isinstance(last, dict) else None
        sent = sent if isinstance(sent, int) and not isinstance(sent, bool) else None
        if sent is None or now - sent >= config['remind_seconds']:
            prefix = 'G2C %s ALERT' % HOST if sent is None else 'G2C %s STILL' % HOST
            if deliver(config, prefix + ': ' + message) == 'delivery_failed':
                failed += 1
            else:
                sent = now
        state[key] = dict(notified_at=sent)
    for key in sorted(set(previous) - set(active)):
        if deliver(config, 'G2C %s RECOVERED: %s' % (HOST, key)) == 'delivery_failed':
            failed += 1
            state[key] = dict(notified_at=None, recovered_pending=True)
    _atomic_json(state_path, dict(version='g2c-beta-alert-state.1', checked_at=now, alerts=state))
    return len(active), failed


def probe_transition(config, outcome, previous, deliver=send, drill=False):
    """External readiness probe: notify only when the public state flips.

    Cancelled runs are neither failures nor recoveries; a drill says so and is
    excluded from the previous-run lookup by the workflow.
    """
    if drill:
        return 'alerted' if deliver(config, 'G2C %s DRILL: readiness notification path test, no action needed' % HOST) != 'delivery_failed' else 'delivery_failed'
    if outcome not in ('success', 'failure'):
        return 'unchanged'
    failed = outcome == 'failure'
    was_failed = previous in ('failure', 'timed_out')
    if failed and not was_failed:
        deliver(config, 'G2C %s ALERT: public readiness probe failed (GitHub Actions)' % HOST)
        return 'alerted'
    if not failed and was_failed:
        deliver(config, 'G2C %s RECOVERED: public readiness probe' % HOST)
        return 'recovered'
    return 'unchanged'


def main(argv):
    if len(argv) in (3, 4) and argv[0] == 'probe-transition' and argv[3:] in ([], ['drill']):
        try:
            config = load_config(path=None, environ=os.environ)
        except ConfigError as error:
            sys.stderr.write('ALERT alert_config_invalid %s\n' % error)
            return 1
        print(json.dumps(dict(result=probe_transition(config, argv[1], argv[2], drill=argv[3:] == ['drill']))))
        return 0
    if argv == ['backup-succeeded']:
        backup_succeeded()
        return 0
    if argv not in (['check'], ['drill']):
        sys.stderr.write('usage: ops_alerts.py backup-succeeded|check|drill\n')
        return 2
    try:
        config = load_config()
    except ConfigError as error:
        sys.stderr.write('ALERT alert_config_invalid %s\n' % error)
        return 1
    if argv == ['drill']:
        result = send(config, 'G2C %s DRILL: notification path test, no action needed' % HOST)
        print(json.dumps(dict(result=result)))
        return 0 if result == 'delivered' else 1
    active, failed = check(config)
    print(json.dumps(dict(active_alerts=active, failed_deliveries=failed, channel=config['ALERT_CHANNEL'])))
    return 1 if failed or (active and config['ALERT_CHANNEL'] == 'none') else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
