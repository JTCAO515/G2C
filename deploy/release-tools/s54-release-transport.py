"""Current application release inputs over the previously reviewed GitHub relay."""

from hashlib import sha256
import os
from pathlib import Path
import sys
from types import SimpleNamespace


CODE = Path(__file__).resolve().parent
# Private state (gates, evidence, logs, tokens) stays outside the repository; see README.md.
STATE = Path(os.environ.get('G2C_RELEASE_STATE', '~/.local/share/g2c/b-server-smoke-20261118')).expanduser()
RELAY = CODE / 's54-release-relay.py'
ROLLBACK = '23ab01c66ca59555758d4049148df2b67d3de9b1'
ROLLBACK_DRIVER = 'app-release-idle55-compat3-gatebytes-20261117.py'
ROLLBACK_DRIVER_SHA = '76cf6f129f502f9acc0f71773a1338e6dd4bf47e4fa898e86575d8ca909d107b'
ADAPTER = '/srv/g2c-beta/probes/b-archive-detach-1d5d538b-45db9e23/next-release-readonly-journal.py'
ADAPTER_SHA = 'dacb83c0709131ed6f112e871fa6e1e65e44ffb16e9bee1f066cf57a7baef62e'
HOST_ANCHOR = "main=runpy.run_path(str(driver))['main']\n"


def read_pinned(path, expected):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError('exact reviewed source bytes required')
    return raw


def load_pinned(path, expected):
    scope = dict(__name__='release_pinned_file', __file__=str(path))
    exec(compile(read_pinned(path, expected), str(path), 'exec'), scope)
    return scope


def configured_relay(host, root):
    if host.count(HOST_ANCHOR) != 1:
        raise ValueError('approved launcher anchor required')
    before_driver = (
        'from stat import S_ISREG, S_ISDIR, S_IMODE\n'
        'from types import ModuleType\n'
        "if mode=='forward':\n"
        '    root_info=driver.parent.lstat()\n'
        '    assert S_ISDIR(root_info.st_mode) and root_info.st_uid==0 and S_IMODE(root_info.st_mode)==0o700\n'
        "    helper=driver.with_name('application_release.py')\n"
        '    helper_raw=helper.read_bytes()\n'
        '    assert hashlib.sha256(helper_raw).hexdigest()==helper_hash\n'
        "    verified_helper=ModuleType('application_release')\n"
        '    verified_helper.__file__=str(helper)\n'
        "    exec(compile(helper_raw,str(helper),'exec'),verified_helper.__dict__)\n"
        "    sys.modules['application_release']=verified_helper\n"
        'else:\n'
        '    assert driver_hash=='+repr(ROLLBACK_DRIVER_SHA)+'\n'
    )
    after_driver = (
        'journal=Path('+repr(ADAPTER)+')\n'
        'info=journal.lstat()\n'
        'assert S_ISREG(info.st_mode) and info.st_uid==0 and S_IMODE(info.st_mode)==0o600\n'
        'journal_raw=journal.read_bytes()\n'
        'assert hashlib.sha256(journal_raw).hexdigest()=='+repr(ADAPTER_SHA)+'\n'
        "journal_scope=dict(__name__='reviewed_journal_mount',__file__=str(journal))\n"
        "exec(compile(journal_raw,str(journal),'exec'),journal_scope)\n"
        "journal_scope['install_on_verified_driver'](main)\n"
    )

    def release_operator(path):
        expected = root/'hk-operator.py'
        if Path(path).resolve() != expected.resolve():
            raise ValueError('approved release operator required')
        values = load_pinned(expected, sha256(expected.read_bytes()).hexdigest())
        read_pinned(values['PREVIOUS']/ROLLBACK_DRIVER, ROLLBACK_DRIVER_SHA)
        values['OLD'] = ROLLBACK
        return values

    return host.replace(HOST_ANCHOR, before_driver + HOST_ANCHOR + after_driver), release_operator


def main():
    phase,source,launcher_hash,run=sys.argv[1:]
    if not sys.flags.isolated or not __debug__:
        raise ValueError('isolated non-optimized launcher required')
    if sha256(Path(__file__).read_bytes()).hexdigest()!=launcher_hash:
        raise ValueError('exact reviewed launcher required')
    # The relay is reviewed with this repository; pin the bytes read here for the rest of the run.
    relay_sha=sha256(RELAY.read_bytes()).hexdigest()
    relay=load_pinned(RELAY,relay_sha)
    launch=relay['main']
    g=launch.__globals__
    host,operator=configured_relay(g['HOST'],CODE)
    g.update(HOST=host,runpy=SimpleNamespace(run_path=operator))
    # The base relay retains all phase checks including the rollback verdict,
    # candidate checkout, fixed drivers, request allowlist and gate hash.
    sys.argv=[str(RELAY),phase,source,relay_sha,run]
    raise SystemExit(launch())


if __name__=='__main__':
    main()
