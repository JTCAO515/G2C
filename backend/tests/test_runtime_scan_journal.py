"""Original reservation/request custody and scan-once failure interleavings."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cj_api.runtime_scan_journal import FixtureScanJournal
from cj_api.runtime_fixture_originals import FixtureOriginalReferences,SCAN_VERSION
from runtime_adapter import Invalid,Unavailable
from runtime_adapter.contract import decode,encode
from test_runtime_disclosure_scan import fixture as scanner_fixture
from test_runtime_fixture_registry import fixture as registry_fixture


@pytest.fixture
def journal(tmp_path,registry_fixture,scanner_fixture):
    token='local-E-scan-reference-token'
    registry_fixture.consumer=replace(registry_fixture.consumer,auth_session_id=sha256(token.encode()).hexdigest())
    registry_fixture.policy['consumer_binding_sha256']=registry_fixture.consumer.key
    registry_fixture.policy_file.write_bytes(encode(registry_fixture.policy))
    registry=registry_fixture.build(bound=registry_fixture.consumer)
    request=encode(dict(attempt_id='attempt1',step_id='step1',binding_sha256=registry.consumer.key,
        pins_sha256=registry.pins.key,kind='message'))
    use=decode(registry_fixture.request());use.update(binding_sha256=registry.consumer.key,
        request_sha256=sha256(request).hexdigest());use=encode(use)
    registry.reserve(use)
    directory=tmp_path/'scan-journal';directory.mkdir(mode=0o700)
    state=dict(request=request,scans=0)
    def read(step,*,deadline):
        assert step=='step1'and deadline==100
        return state['request']
    scanner=scanner_fixture.build();original=scanner.scan
    def scan(*args,**kwargs):
        state['scans']+=1
        return original(*args,**kwargs)
    scanner.scan=scan
    def build():return FixtureScanJournal(directory,registry,SimpleNamespace(read=read),scanner)
    return SimpleNamespace(build=build,directory=directory,use=use,state=state,scanner=scanner,
        native=scanner_fixture,registry=registry_fixture,store=registry,token=token)


def test_repeat_and_process_reconstruction_read_the_original_without_reclassification(journal):
    result=journal.build().scan_once(journal.use,deadline=100)
    assert journal.build().scan_once(journal.use,deadline=100)==result
    assert journal.build().read(journal.use,deadline=100)==result
    assert journal.state['scans']==1 and decode(result)['exact_status']=='PASS'
    assert len(list(journal.directory.iterdir()))==2
    assert all(p.stat().st_mode&0o777==0o600 for p in journal.directory.iterdir())
    assert all(journal.native.marker.encode()not in p.read_bytes()for p in journal.directory.iterdir())


def test_intent_ack_loss_never_restarts_classification(journal):
    with patch('cj_api.runtime_scan_journal.os.fsync',side_effect=OSError('synthetic ACK lost')):
        with pytest.raises(OSError):journal.build().scan_once(journal.use,deadline=100)
    with pytest.raises(Unavailable,match='UNRESOLVED_QUERY_ONLY'):
        journal.build().scan_once(journal.use,deadline=100)
    assert journal.state['scans']==0 and len(list(journal.directory.iterdir()))==1


def test_scan_failure_is_retained_unknown_not_an_invitation_to_rescan(journal):
    journal.native.state['allowed']=False
    with pytest.raises(Unavailable):journal.build().scan_once(journal.use,deadline=100)
    journal.native.state['allowed']=True
    with pytest.raises(Unavailable,match='UNRESOLVED_QUERY_ONLY'):
        journal.build().scan_once(journal.use,deadline=100)
    assert journal.state['scans']==1


def test_result_ack_loss_can_only_read_the_complete_original(journal):
    store=journal.build();write=store._write
    def lost(fd,name,raw):
        write(fd,name,raw)
        if name.endswith('.result'):raise OSError('synthetic result ACK lost')
    with patch.object(store,'_write',side_effect=lost):
        with pytest.raises(OSError):store.scan_once(journal.use,deadline=100)
    assert decode(journal.build().read(journal.use,deadline=100))['exact_status']=='PASS'
    assert journal.build().scan_once(journal.use,deadline=100)==journal.build().read(journal.use,deadline=100)
    assert journal.state['scans']==1


def test_late_native_output_change_withholds_retained_report_without_rescan(journal):
    journal.build().scan_once(journal.use,deadline=100)
    journal.native.state['data']+=b'late output'
    with pytest.raises(Unavailable,match='SURFACES_CHANGED'):journal.build().read(journal.use,deadline=100)
    assert journal.state['scans']==1


def test_known_failure_is_the_same_retained_failure_on_requery(journal):
    journal.native.state.update(data=journal.native.marker.encode(),status='UNKNOWN',missing=[{'field':'wire'}])
    result=journal.build().scan_once(journal.use,deadline=100)
    assert decode(result)['exact_status']=='FAIL'
    assert journal.build().scan_once(journal.use,deadline=100)==result
    assert journal.state['scans']==1


def test_new_source_or_marker_set_cannot_reclassify_the_same_original(journal):
    journal.build().scan_once(journal.use,deadline=100)
    journal.scanner.sentinel_sha256='d'*64
    with pytest.raises(Unavailable,match='BINDING_CHANGED'):
        journal.build().scan_once(journal.use,deadline=100)
    assert journal.state['scans']==1


def test_partial_result_is_not_repaired_or_reclassified(journal):
    journal.build().scan_once(journal.use,deadline=100)
    result,=journal.directory.glob('*.result');result.write_bytes(b'{')
    with pytest.raises(Invalid):journal.build().scan_once(journal.use,deadline=100)
    assert journal.state['scans']==1 and result.read_bytes()==b'{'


def test_result_with_changed_source_binding_is_rejected(journal):
    journal.build().scan_once(journal.use,deadline=100)
    path,=journal.directory.glob('*.result');result=decode(path.read_bytes())
    result['report']['message_id']='another-message';path.write_bytes(encode(result))
    with pytest.raises(Invalid,match='REPORT_BINDING'):journal.build().read(journal.use,deadline=100)
    assert journal.state['scans']==1


@pytest.mark.parametrize('kind',['source','consumer','request'])
def test_current_qualification_and_original_request_are_required_on_every_read(journal,kind):
    journal.build().scan_once(journal.use,deadline=100)
    if kind=='source':journal.native.state['allowed']=False
    elif kind=='consumer':journal.registry.state['consumer_allowed']=False
    else:journal.state['request']=encode({**decode(journal.state['request']),'attempt_id':'another-attempt'})
    with pytest.raises((Unavailable,Invalid)):journal.build().scan_once(journal.use,deadline=100)
    assert journal.state['scans']==1 and len(list(journal.directory.iterdir()))==2


def test_concurrent_reentry_does_not_start_second_scan(journal):
    started=Event();release=Event();scan=journal.scanner.scan
    def paused(*args,**kwargs):
        started.set();assert release.wait(timeout=10)
        return scan(*args,**kwargs)
    journal.scanner.scan=paused
    with ThreadPoolExecutor(max_workers=1)as executor:
        future=executor.submit(journal.build().scan_once,journal.use,deadline=100)
        assert started.wait(timeout=10)
        try:
            with pytest.raises(Unavailable,match='UNRESOLVED_QUERY_ONLY'):
                journal.build().scan_once(journal.use,deadline=100)
        finally:release.set()
        assert decode(future.result(timeout=10))['exact_status']=='PASS'
    assert journal.state['scans']==1


def test_scan_ref_resolves_retained_metadata_across_reader_reconstruction(journal,tmp_path):
    directory=tmp_path/'scan-refs';directory.mkdir(mode=0o700)
    report=journal.build().scan_once(journal.use,deadline=100)
    reader=FixtureOriginalReferences(directory,journal.store,journal.use,
        scan_journal=journal.build(),clock=lambda:70)
    ref=reader.issue(journal.token,'scan')
    assert ref['sha256']==sha256(report).hexdigest()
    descriptor=decode(next(directory.iterdir()).read_bytes())
    assert descriptor['source']['version']==SCAN_VERSION
    restored=FixtureOriginalReferences(directory,journal.store,scan_journal=journal.build(),clock=lambda:70)
    assert restored.contains(journal.token,ref['ref'])
    assert restored.resolve(journal.token,ref['ref'])==report and journal.state['scans']==1
    journal.native.state['allowed']=False
    with pytest.raises(Unavailable):restored.resolve(journal.token,ref['ref'])
    assert journal.state['scans']==1


def test_scan_reference_never_creates_a_missing_scan_or_uses_legacy_fallback(journal,tmp_path):
    directory=tmp_path/'scan-refs';directory.mkdir(mode=0o700)
    reader=FixtureOriginalReferences(directory,journal.store,journal.use,
        scan_journal=journal.build(),clock=lambda:70)
    with pytest.raises(Unavailable,match='QUERY_ONLY'):reader.issue(journal.token,'scan')
    assert not list(directory.iterdir())and not list(journal.directory.iterdir())
    journal.build().scan_once(journal.use,deadline=100)
    ref=reader.issue(journal.token,'scan')
    old=FixtureOriginalReferences(directory,journal.store,journal.use)
    with pytest.raises(Unavailable,match='NOT_CONNECTED'):old.resolve(journal.token,ref['ref'])
    with pytest.raises(Unavailable,match='SESSION_CHANGED'):reader.resolve('different-token',ref['ref'])
    assert journal.state['scans']==1
