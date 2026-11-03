import json,unittest
from cj_memory_withdrawal.erasure_command import ErasureCommand,VERSION
from cj_memory.domain import InvalidInput


class ErasureCommandTests(unittest.TestCase):
    def test_exact_private_ids_bytes_and_original_operation(self):
        value=dict(version=VERSION,action_id='原操作-é',item_id='原条目-e\u0301',expected_version=2,derived_range='owned_trip_derived_scope')
        raw=json.dumps(value,ensure_ascii=False,indent=2).encode()+b'\n';command=ErasureCommand.parse(raw)
        self.assertEqual(command.raw,raw);self.assertEqual(command.item_id,value['item_id'])
        self.assertEqual(command.operation_id('scope'),command.operation_id('scope'))
        self.assertNotEqual(command.operation_id('scope'),command.operation_id('other'))
        self.assertNotEqual(command.operation_id('scope'),ErasureCommand.parse(raw+b' ').operation_id('scope'))

    def test_no_actor_or_account_or_implicit_confirmation(self):
        value=dict(version=VERSION,action_id='action',item_id='item',expected_version=1,derived_range='owned_trip_derived_scope')
        for extra in ('owner','account','confirmed','source_id'):
            with self.subTest(extra=extra),self.assertRaises(InvalidInput):ErasureCommand.parse(json.dumps(dict(value,**{extra:True})).encode())
        for bad in (True,0,-1,2**63,'1'):
            with self.subTest(version=bad),self.assertRaises(InvalidInput):ErasureCommand.parse(json.dumps(dict(value,expected_version=bad)).encode())
        raw=json.dumps(value).encode()
        with self.assertRaises(InvalidInput):ErasureCommand.parse(raw[:-1]+b',"item_id":"other"}')
        with self.assertRaises(InvalidInput):ErasureCommand.parse(json.dumps(dict(value,item_id='item\0')).encode())


if __name__=='__main__':unittest.main()
