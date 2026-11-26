"""LIO_ lines kept in a separate host-mounted store across cutovers (#1828)."""
import io
import json
import logging

import pytest

from deploy.hk import lio_log


def store_dir(tmp_path):
    directory = tmp_path / 'lio-log'
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    return directory


def test_only_lio_lines_are_kept_without_content_or_user_identifiers():
    assert lio_log.sanitize('M4_DB_CHECKOUT_SUMMARY pooled=true count=3') is None
    assert lio_log.sanitize('Some LIO_ text') is None
    line = lio_log.sanitize('LIO_PIPELINE_REFUSED run_id=4fb238dc-1 stage=generation error=ValueError '
                            'subject=m4-synthetic-demo-abc scope=local:x text=北京三日游 detail=free-form '
                            'reason=missing_field field=days.0.items')
    assert line.startswith('LIO_PIPELINE_REFUSED run_id=') and 'stage=generation error=ValueError' in line
    assert 'reason=missing_field field=days.0.items' in line
    for leaked in ('4fb238dc-1', 'm4-synthetic', 'local:x', '北京', 'free-form', 'subject=', 'scope=', 'text=', 'detail='):
        assert leaked not in line
    timing = lio_log.sanitize('LIO_TIMING message_key=abc123 run_id=r1 picked_up_ms=10 started_ms=12 '
                              'first_progress_ms=- first_text_ms=900 terminal_ms=2000 terminal=completed status=done')
    assert 'first_text_ms=900' in timing and 'message_key=abc123' in timing and 'run_id=r1' not in timing
    assert lio_log.sanitize('LIO_X value=has"quote<>') == 'LIO_X value=redacted'


def test_store_writes_daily_role_files_and_survives_a_new_process(tmp_path):
    directory = store_dir(tmp_path)
    clock = lambda: 1_800_000_000.0
    first = lio_log.Store('worker', directory, clock=clock)
    first.write('LIO_PIPELINE_REFUSED stage=generation')
    # A later container (new process, new Store) appends to the same host file.
    second = lio_log.Store('worker', directory, clock=clock)
    second.write('LIO_TIMING first_text_ms=900')
    files = sorted(p.name for p in directory.iterdir())
    assert files == ['lio-worker-2027-01-15.jsonl']
    path = directory / files[0]
    assert oct(path.stat().st_mode & 0o777) == '0o600'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row['line'] for row in rows] == ['LIO_PIPELINE_REFUSED stage=generation', 'LIO_TIMING first_text_ms=900']
    assert rows[0]['version'] == 'G2C-HK-lio-log.1' and rows[0]['role'] == 'worker' and rows[0]['at'].endswith('Z')
    out = io.StringIO()
    lio_log.query(directory, '2027-01-15', 'LIO_TIMING', out)
    assert json.loads(out.getvalue())['line'] == 'LIO_TIMING first_text_ms=900'


def test_retention_cap_and_other_roles(tmp_path, capsys):
    directory = store_dir(tmp_path)
    for name in ('lio-worker-2026-01-01.jsonl', 'lio-api-2026-01-01.jsonl', 'unrelated.txt'):
        (directory / name).write_text('{}\n')
    store = lio_log.Store('worker', directory, clock=lambda: 1_800_000_000.0, daily_cap=200)
    store.write('LIO_A x=1')
    store.write('LIO_B ' + 'y=' + 'z' * 150)
    names = sorted(p.name for p in directory.iterdir())
    assert names == ['lio-api-2026-01-01.jsonl', 'lio-worker-2027-01-15.jsonl', 'unrelated.txt']
    assert len((directory / 'lio-worker-2027-01-15.jsonl').read_text().splitlines()) == 1
    assert 'ALERT lio_log_daily_cap_reached_2027-01-15' in capsys.readouterr().err


@pytest.mark.parametrize('make', ['absent', 'open_mode', 'symlink'])
def test_unqualified_directory_disables_the_store_without_raising(tmp_path, capsys, make):
    directory = tmp_path / 'lio-log'
    if make == 'open_mode':
        directory.mkdir(); directory.chmod(0o755)
    elif make == 'symlink':
        real = store_dir(tmp_path / 'real') if (tmp_path / 'real').mkdir() is None else None
        directory.symlink_to(real)
    store = lio_log.Store('api', directory)
    assert not store.enabled
    store.write('LIO_A x=1')
    assert 'ALERT lio_log_directory_' in capsys.readouterr().err


def test_handler_copies_only_lio_lines_and_never_breaks_logging(tmp_path):
    directory = store_dir(tmp_path)
    logger = logging.getLogger('test-lio-log-handler')
    logger.setLevel(logging.INFO); logger.propagate = False
    handler = lio_log.Handler(lio_log.Store('api', directory, clock=lambda: 1_800_000_000.0))
    logger.addHandler(handler)
    try:
        logger.info('M4_DB_CHECKOUT_SUMMARY pooled=true count=%d', 3)
        logger.info('LIO_TIMING_ACCEPTED message_key=%s accepted_ms=%d', 'k1', 5)
        logger.info('LIO_BAD %s', object())  # odd formatting still never raises
    finally:
        logger.removeHandler(handler)
    lines = [json.loads(l)['line'] for l in (directory / 'lio-api-2027-01-15.jsonl').read_text().splitlines()]
    assert lines[0] == 'LIO_TIMING_ACCEPTED message_key=k1 accepted_ms=5' and len(lines) == 2


def test_role_is_explicit(tmp_path):
    with pytest.raises(ValueError):
        lio_log.Store('migrate', store_dir(tmp_path))


def test_compose_mounts_the_store_for_api_and_worker_only():
    from pathlib import Path
    compose = (Path(__file__).resolve().parents[2] / 'deploy/hk/compose.yaml').read_text()
    assert compose.count('/srv/g2c-beta/lio-log:/lio-log') == 2


def test_real_refusal_lines_keep_their_schema_locations():
    # Format of backend/cj_api/local_lio_pipeline_generation.py _log_refusal: '*' marks a location
    # outside the schema, and up to 8 items are joined.
    locations=','.join(f'days.{i}.items.*.extra:extra_forbidden' for i in range(8))
    line=lio_log.sanitize('LIO_PIPELINE_REFUSED run_id=r stage=generation error=ValidationError '
                          'message_sha256=abc123 cause=ValidationError cause_errors='+locations+' cause_error_count=8')
    assert 'cause_errors='+locations in line and 'cause_error_count=8' in line and len(locations)>200
    assert 'redacted' not in line
