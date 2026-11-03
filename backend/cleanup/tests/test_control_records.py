from copy import deepcopy
from pathlib import Path
import json,unittest

from cj_cleanup.core import Invalid,encode
from cj_cleanup.registry import freeze,freeze_controls

ROOT=Path(__file__).resolve().parents[3]
IDS={'cleanup-control/selected','cleanup-control/manifest','cleanup-control/execution',
     'cleanup-control/device','cleanup-control/account'}


class ClientControlRegistryChecks(unittest.TestCase):
    def setUp(self):
        actual=json.loads((ROOT/'backend/storage-registry.json').read_text())
        self.controls=next(store for store in actual['stores'] if store['id']=='cleanup-control')
        self.value=dict(version='controls-test',stores=[dict(id='content',cleanup_protocol='CLEANUP@1.1'),self.controls])

    def test_control_profile_does_not_fabricate_online_hooks_or_receipts(self):
        raw=encode(self.value)
        old=freeze(raw,('content',),versions=('CLEANUP@1.0','CLEANUP@1.1'))
        self.assertEqual(set(old.gaps),IDS)
        current=freeze_controls(raw,('content',))
        self.assertEqual(current.gaps,())
        self.assertEqual({e.registry_id for e in current.entries},{'content'})
        self.assertEqual({key for key,digest in current.retained_controls},IDS)
        self.assertEqual(current.inventory,('content',))
        self.assertIn('CLEANUP-CONTROL-RECORDS@1',current.versions)
        changed=deepcopy(self.value);changed['stores'][1]['objects'][0]['status']='finalization-still-pending'
        self.assertNotEqual(freeze_controls(encode(changed),('content',)).digest,current.digest)

    def test_missing_unknown_sdk_slot_or_wrong_retention_is_not_acknowledged(self):
        cases=[]
        missing=deepcopy(self.value);missing['stores'][1]['objects'].pop();cases.append(missing)
        duplicate=deepcopy(self.value);duplicate['stores'].append(deepcopy(self.controls));cases.append(duplicate)
        for objects in ([dict(id='unexpected-private-content',cleanup_protocol='CLEANUP@1.1',retention_category='user_content')],
                        ['unexpected-private-content'],[],self.controls['objects'][0]['objects']+['extra-private-copy']):
            value=deepcopy(self.value);value['stores'][1]['objects'][0]['objects']=objects;cases.append(value)
        for field,bad in (('slot_template','M1.Development.Active'),('service_template','other-account-service'),
                          ('retention_category','diagnostic_90d'),('cleanup_protocol','CLEANUP@1.1'),('owner_line','B')):
            value=deepcopy(self.value);value['stores'][1]['objects'][0][field]=bad;cases.append(value)
        for value in cases:
            with self.subTest(value=value['stores'][1]['objects'][0]),self.assertRaises(Invalid):
                freeze_controls(encode(value),('content',))

    def test_component_without_app_controls_and_unregistered_new_target(self):
        self.value['stores'].pop()
        self.assertEqual(freeze(encode(self.value),('content',),versions=('CLEANUP@1.1',)).gaps,())
        self.assertEqual(set(freeze_controls(encode(self.value),('content',)).gaps),IDS)
        self.value['stores'].append(dict(id='unregistered',cleanup_protocol='CLEANUP@1.1'))
        self.assertEqual(set(freeze_controls(encode(self.value),('content',)).gaps),IDS|{'unregistered'})


if __name__=='__main__':unittest.main()
