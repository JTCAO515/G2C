"""Actual factory/registry/cost/lifecycle/ref wiring; controlled native source.

The source custodian is a controlled port here. Its signed-PG implementation is
covered separately, not represented as a full native definition/use publisher.
"""
from contextlib import nullcontext
from datetime import datetime,timezone
from hashlib import sha256
from types import SimpleNamespace

import pytest

from cj_api.runtime_fixture_registry import VERSION
from cj_api.runtime_fixture_originals import FixtureOriginalReferences
from cj_api.runtime_worker_bindings import RuntimeWorkerBindings
from cj_api.runtime_preparation_cost import FrozenPreparationCost
from runtime_adapter import Binding,Invalid,Unavailable
from runtime_adapter.contract import encode,decode
from test_runtime_preparation_lifecycle import lifecycle


@pytest.fixture
def host(lifecycle,tmp_path,monkeypatch):
    producer=lifecycle.costs.binding;token='consumer-E'
    consumer=Binding('E-owner',sha256(token.encode()).hexdigest(),producer.ledger_id,producer.producer_id)
    pins=lifecycle.costs.pins;pins.raw=b'controlled-current-pins'
    state=dict(source=True,consumer=True,pins=pins.raw,source_reads=0)
    class Authority:
        def __init__(self,bound):self.bound=bound
        def require(self,**args):
            assert args['binding']==self.bound and args['pins_sha256']==pins.key
            if self.bound==producer and not lifecycle.state['allowed']:raise Unavailable('C_REVOKED')
            if self.bound==consumer and not state['consumer']:raise Unavailable('E_REVOKED')
        def pins(self):return state['pins']
    frame=dict(binding_sha256=producer.key,preparation=dict(message_id='prep-1'),
        trip=dict(trip_id_sha256='b'*64,version=1,content_sha256='c'*64))
    frame_file=tmp_path/'state.json';frame_file.write_bytes(encode(frame));frame_file.chmod(0o600)
    class Source:
        def __init__(self,*args,qualification_guard,**kwargs):self.guard=qualification_guard
        def with_current(self,expected,project,*,deadline):
            state['source_reads']+=1;self.guard(deadline)
            if not state['source']:raise Unavailable('C_SOURCE_CHANGED')
            assert expected==encode(frame)
            return project(frame,b'PRIVATE-C-TITLE-NEVER-PUBLISHED')
    monkeypatch.setattr('cj_api.runtime_fixture_boundary.FixtureSourceBoundary',Source)
    journal=lifecycle.build();journal.begin(deadline=100);lifecycle.prepare();closed=journal.close(deadline=100)
    def pinned(path):
        path.mkdir(mode=0o700,exist_ok=True);info=path.stat()
        return dict(path=str(path),device=info.st_dev,inode=info.st_ino)
    directories={name:pinned(tmp_path/name)for name in ('reservations_directory','references_directory','cost_directory')}
    directories['lifecycle_directory']=pinned(lifecycle.directory)
    FrozenPreparationCost(directories['cost_directory']['path'],lifecycle.costs).freeze(deadline=100)
    origin=dict(ref='original-'+'d'*64,sha256='e'*64)
    policy=dict(version=VERSION,registry_id='B-preapproved',fixture_id='fixture-native',fixture_revision=1,
        producer_binding_sha256=producer.key,consumer_binding_sha256=consumer.key,
        baseline=dict(trip_id_sha256='b'*64,trip_version=1,content_sha256='c'*64),
        consumer_pins_sha256=pins.key,consumer_registration_ref=origin,experiment_ref=origin,public_release_ref=origin,
        batch_ids=['batch'],candidate_ids=['C0'],languages=['zh','en'],valid_from='2020-01-01T00:00:00Z',
        valid_until='2100-01-01T00:00:00Z',maximum_uses=2)
    path=tmp_path/'policy.json';path.write_bytes(encode(policy));path.chmod(0o600)
    data=dict(version='G2C-fixture-preparation-host.1',
        purpose_approval_sha256='32dd0d098fde23b93b2625fc341afc34e561588ffb9f1e1128577648e08f194c',
        producer_binding_sha256=producer.key,consumer_binding_sha256=consumer.key,
        preparation_message_ids=['prep-1','prep-2'],preparation_message_id='prep-1',policy_file=str(path),
        release_control_directory=str(tmp_path/'release'),source_state_file=str(frame_file),**directories)
    instance=RuntimeWorkerBindings.__new__(RuntimeWorkerBindings)
    instance.clock=lambda:100;instance.wall_clock=lambda:datetime.now(timezone.utc)
    instance.pins=pins;instance.database=object();instance.release=object();instance._trip_boundary=lambda s:None
    c=dict(line='C',binding=producer,authority=Authority(producer),boundary=None,token=lambda:'producer-C',
        originals=lifecycle.costs.originals)
    e=dict(line='E',binding=consumer,authority=Authority(consumer),claims=SimpleNamespace(_admission=nullcontext),
        collector=SimpleNamespace(fixture_originals=None))
    instance.by_scope={producer.scope:c,consumer.scope:e}
    return SimpleNamespace(instance=instance,data=data,consumer=e,producer=c,token=token,
        state=state,lifecycle=lifecycle,closed=closed,frame_file=frame_file)


def test_factory_attaches_real_original_readers_without_dispatch_or_reserving(host):
    fees=host.lifecycle.budget.inspect()
    host.instance._attach_fixture_preparation(host.data)
    reader=host.consumer['collector'].fixture_originals
    assert isinstance(reader,FixtureOriginalReferences)
    for kind in ('preparation_policy','preparation_cost','preparation_lifecycle'):
        ref=reader.issue(host.token,kind);raw=reader.resolve(host.token,ref['ref'])
        assert b'PRIVATE-C-TITLE'not in raw and b'producer-C'not in raw and b'consumer-E'not in raw
    assert reader.resolve(host.token,reader.issue(host.token,'preparation_lifecycle')['ref'])==host.closed
    registry=host.consumer['fixture_preparation']['registry']
    request=encode(dict(binding_sha256=registry.consumer.key,pins_sha256=host.instance.pins.key,batch_id='batch',
        candidate_id='C0',task_id='val-owner',language='en',attempt_id='new',step_id='step',request_sha256='f'*64))
    with pytest.raises(Unavailable,match='DEFINITION_PUBLISHER_NOT_CONNECTED'):registry.reserve(request)
    assert host.lifecycle.budget.inspect()==fees


@pytest.mark.parametrize('what',['source','consumer','producer','pins','state_file'])
def test_factory_saved_original_is_withheld_after_qualification_drift(host,what):
    host.instance._attach_fixture_preparation(host.data);reader=host.consumer['collector'].fixture_originals
    ref=reader.issue(host.token,'preparation_cost')
    if what in ('source','consumer'):host.state[what]=False
    elif what=='producer':host.lifecycle.state['allowed']=False
    elif what=='pins':host.state['pins']=b'new-source'
    else:host.frame_file.write_bytes(encode({'replacement':True}))
    with pytest.raises(Unavailable):reader.resolve(host.token,ref['ref'])


@pytest.mark.parametrize('what',['purpose','binding','baseline'])
def test_wrong_host_registration_never_attaches_a_reader(host,what):
    if what=='purpose':host.data['purpose_approval_sha256']='0'*64
    elif what=='binding':host.data['producer_binding_sha256']=host.consumer['binding'].key
    elif what=='baseline':
        frame=decode(host.frame_file.read_bytes());frame['trip']['version']=2;host.frame_file.write_bytes(encode(frame))
    with pytest.raises((Invalid,Unavailable)):host.instance._attach_fixture_preparation(host.data)
    assert host.consumer['collector'].fixture_originals is None


def test_inactive_original_source_disables_only_fixture_metadata(host):
    del host.instance.by_scope[host.producer['binding'].scope]
    host.instance._attach_fixture_preparation(host.data)
    assert host.instance.fixture_preparation_status=='FIXTURE_ORIGINAL_SESSIONS_NOT_CONNECTED'
    assert host.consumer['collector'].fixture_originals is None
