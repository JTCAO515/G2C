"""Host alerts: backup heartbeat, disk threshold, configurable channel (#1720)."""
import ast
import json
import os
from pathlib import Path

import pytest

from deploy.hk import ops_alerts

ROOT=Path(__file__).resolve().parents[2]
HOUR=3600


def config(**changes):
    return ops_alerts.load_config(path=None,environ={**ops_alerts.DEFAULTS,**changes})


def usage(percent):
    return lambda path:(100,percent,100-percent)


class Inbox:
    def __init__(self):self.messages=[]
    def __call__(self,config,text):self.messages.append(text);return 'delivered'


def test_host_script_stays_python36_and_stdlib_only():
    source=(ROOT/'deploy/hk/ops_alerts.py').read_text()
    tree=ast.parse(source,feature_version=(3,6))
    modules={alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names}
    modules|={node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)}
    assert modules<={'http','json','os','shutil','ssl','sys','time','urllib'}
    assert 'fromisoformat' not in source and 'capture_output' not in source


def test_backup_unit_records_heartbeat_only_after_success_and_timer_checks():
    unit=(ROOT/'deploy/hk/g2c-beta-backup.service').read_text()
    assert 'Type=oneshot' in unit and 'ExecStartPost=/usr/bin/python3 -B /srv/g2c-beta/deploy/hk/ops_alerts.py backup-succeeded' in unit
    assert 'ops_alerts.py check' in (ROOT/'deploy/hk/g2c-beta-ops-alerts.service').read_text()
    assert 'OnUnitActiveSec=15min' in (ROOT/'deploy/hk/g2c-beta-ops-alerts.timer').read_text()


def test_missing_or_stale_backup_heartbeat_alerts(tmp_path):
    beat=tmp_path/'beat.json';now=1_800_000_000;value=config()
    assert set(ops_alerts.conditions(value,now,heartbeat_path=beat,usage=usage(10)))=={'backup_heartbeat'}
    ops_alerts.backup_succeeded(now=now-26*HOUR,path=str(beat))
    assert oct(beat.stat().st_mode&0o777)=='0o600'
    assert ops_alerts.conditions(value,now,heartbeat_path=beat,usage=usage(10))=={}
    found=ops_alerts.conditions(value,now+2*HOUR,heartbeat_path=beat,usage=usage(10))
    assert found=={'backup_heartbeat':'Daily backup: last success 28.0 hours ago'}
    beat.write_text(json.dumps(dict(version='other',succeeded_at=now)))
    assert 'backup_heartbeat' in ops_alerts.conditions(value,now,heartbeat_path=beat,usage=usage(10))


def test_disk_threshold_alerts_per_path(tmp_path):
    beat=tmp_path/'beat.json';ops_alerts.backup_succeeded(now=1000,path=str(beat))
    value=config(ALERT_DISK_PATHS='/,/srv')
    assert ops_alerts.conditions(value,1000,heartbeat_path=beat,usage=usage(84))=={}
    found=ops_alerts.conditions(value,1000,heartbeat_path=beat,usage=usage(85))
    assert found=={'disk:/':'Disk /: 85% used (threshold 85%)','disk:/srv':'Disk /srv: 85% used (threshold 85%)'}
    def broken(path):raise OSError('gone')
    assert set(ops_alerts.conditions(value,1000,heartbeat_path=beat,usage=broken))=={'disk:/','disk:/srv'}


def test_alert_starts_reminds_and_recovers_once(tmp_path):
    beat=tmp_path/'beat.json';state=tmp_path/'state.json';inbox=Inbox();value=config()
    ops_alerts.backup_succeeded(now=0,path=str(beat))
    def run(now,percent):
        return ops_alerts.check(value,now=now,state_path=str(state),deliver=inbox,heartbeat_path=beat,usage=usage(percent))
    assert run(HOUR,90)==(1,0) and inbox.messages==['G2C api-beta ALERT: Disk /: 90% used (threshold 85%)']
    assert run(2*HOUR,90)==(1,0) and len(inbox.messages)==1
    assert run(7*HOUR,90)==(1,0) and inbox.messages[-1].startswith('G2C api-beta STILL: Disk /')
    ops_alerts.backup_succeeded(now=8*HOUR,path=str(beat))
    assert run(8*HOUR,50)==(0,0) and inbox.messages[-1]=='G2C api-beta RECOVERED: disk:/'
    assert run(9*HOUR,50)==(0,0) and len(inbox.messages)==3


def test_failed_delivery_is_retried_for_start_and_recovery(tmp_path):
    beat=tmp_path/'beat.json';state=tmp_path/'state.json';value=config();sent=[];down=[True]
    def deliver(config,text):
        sent.append(text);return 'delivery_failed' if down[0] else 'delivered'
    ops_alerts.backup_succeeded(now=0,path=str(beat))
    def run(now,percent):
        return ops_alerts.check(value,now=now,state_path=str(state),deliver=deliver,heartbeat_path=beat,usage=usage(percent))
    assert run(60,90)==(1,1) and run(120,90)==(1,1) and len(sent)==2 and all('ALERT:' in s for s in sent)
    down[0]=False;assert run(180,90)==(1,0) and sent[-1].startswith('G2C api-beta ALERT:')
    down[0]=True;assert run(240,50)==(0,1)
    down[0]=False;assert run(300,50)==(0,0) and sent[-1]=='G2C api-beta RECOVERED: disk:/'
    assert run(360,50)==(0,0) and len(sent)==5


@pytest.mark.parametrize('changes,error',[
    (dict(ALERT_CHANNEL='email'),'alert_channel_must_be_none_or_webhook'),
    (dict(ALERT_CHANNEL='webhook',ALERT_WEBHOOK_URL='http://example.invalid/hook'),'https_webhook_url_required'),
    (dict(ALERT_CHANNEL='webhook',ALERT_WEBHOOK_URL='https://example.invalid/hook',ALERT_WEBHOOK_FORMAT='slack'),'known_webhook_format_required'),
    (dict(ALERT_DISK_PERCENT='100'),'bounded_alert_thresholds_required'),
    (dict(ALERT_BACKUP_MAX_HOURS='soon'),'numeric_alert_thresholds_required'),
])
def test_channel_and_thresholds_fail_closed(changes,error):
    with pytest.raises(ops_alerts.ConfigError,match=error):config(**changes)


def test_config_file_must_be_private_and_known(tmp_path):
    path=tmp_path/'alert.env';path.write_text('ALERT_CHANNEL=webhook\nALERT_WEBHOOK_URL=https://example.invalid/h\nALERT_WEBHOOK_FORMAT=wecom\n')
    path.chmod(0o600);value=ops_alerts.load_config(path=str(path))
    assert value['ALERT_CHANNEL']=='webhook' and value['ALERT_WEBHOOK_FORMAT']=='wecom'
    path.chmod(0o644)
    with pytest.raises(ops_alerts.ConfigError,match='private_alert_config_required'):ops_alerts.load_config(path=str(path))
    path.chmod(0o600);path.write_text('ALERT_SECRET=x\n')
    with pytest.raises(ops_alerts.ConfigError,match='unknown_alert_config_line_1'):ops_alerts.load_config(path=str(path))
    assert ops_alerts.load_config(path=str(tmp_path/'absent'))['ALERT_CHANNEL']=='none'


@pytest.mark.parametrize('fmt,expected',[
    ('text',{'text':'m'}),('wecom',{'msgtype':'text','text':{'content':'m'}}),
    ('feishu',{'msg_type':'text','content':{'text':'m'}}),('dingtalk',{'msgtype':'text','text':{'content':'m'}})])
def test_webhook_formats(fmt,expected):
    assert ops_alerts.payload(fmt,'m')==expected


def test_webhook_delivery_posts_json_and_never_echoes_the_url(capsys):
    sent=[]
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,limit):return b'{}'
    class Opener:
        def open(self,request,timeout):
            sent.append((request.full_url,request.get_method(),json.loads(request.data),timeout));return Response()
    value=config(ALERT_CHANNEL='webhook',ALERT_WEBHOOK_URL='https://hooks.example.invalid/secret-token',ALERT_WEBHOOK_FORMAT='feishu')
    assert ops_alerts.send(value,'hello',opener=Opener())=='delivered'
    assert sent==[('https://hooks.example.invalid/secret-token','POST',{'msg_type':'text','content':{'text':'hello'}},10)]
    class Failing:
        def open(self,request,timeout):raise OSError('refused')
    assert ops_alerts.send(value,'hello',opener=Failing())=='delivery_failed'
    assert 'secret-token' not in capsys.readouterr().err


def test_none_channel_writes_journal_alert_and_marks_check_failed(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(ops_alerts,'CONFIG',str(tmp_path/'absent.env'))
    monkeypatch.setattr(ops_alerts,'check',lambda value:(1,0))
    assert ops_alerts.main(['check'])==1
    monkeypatch.setattr(ops_alerts,'check',lambda value:(0,0))
    assert ops_alerts.main(['check'])==0
    assert ops_alerts.send(config(),'G2C api-beta ALERT: x')=='journal_only'
    assert 'ALERT G2C api-beta ALERT: x' in capsys.readouterr().err


def test_probe_notifies_only_on_state_changes():
    inbox=Inbox();value=config()
    assert ops_alerts.probe_transition(value,'success','success',deliver=inbox)=='unchanged'
    assert ops_alerts.probe_transition(value,'failure','success',deliver=inbox)=='alerted'
    assert ops_alerts.probe_transition(value,'failure','failure',deliver=inbox)=='unchanged'
    assert ops_alerts.probe_transition(value,'success','failure',deliver=inbox)=='recovered'
    assert ops_alerts.probe_transition(value,'cancelled','success',deliver=inbox)=='unchanged'
    assert ops_alerts.probe_transition(value,'success','cancelled',deliver=inbox)=='unchanged'
    assert len(inbox.messages)==2
    assert ops_alerts.probe_transition(value,'failure','unknown',deliver=inbox,drill=True)=='alerted'
    assert inbox.messages[-1].startswith('G2C api-beta DRILL:')


def test_readiness_workflow_runs_all_day_and_reports_transitions():
    workflow=(ROOT/'.github/workflows/hk-readiness.yml').read_text()
    assert "- cron: '7,17,27,37,47,57 * * * *'" in workflow
    assert 'ops_alerts.py probe-transition' in workflow and 'secrets.HK_ALERT_WEBHOOK_URL' in workflow
    assert 'continue-on-error: true' in workflow and '--event schedule' in workflow
