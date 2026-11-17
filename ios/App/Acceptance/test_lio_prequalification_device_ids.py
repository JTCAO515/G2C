import unittest

from lio_basic_ui_driver import compact
import test_lio_prequalification_lease as fixtures


class DeviceIdentityTests(unittest.TestCase):
    def test_case_variants_of_one_uuid_cannot_qualify_two_devices(self):
        identifier = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        for chinese, english in ((identifier, identifier.upper()), (identifier.upper(), identifier)):
            with self.subTest(chinese=chinese):
                fixture = fixtures.ReadOnlyLeaseTests()
                fixture.setUp()
                devices = dict(zh=chinese, en=english)
                fixture.expected['simulator_udids'] = devices
                fixture.value['simulator_udids'] = devices
                with self.assertRaises(ValueError):
                    fixture.check()

    def test_distinct_devices_keep_the_original_signed_spelling(self):
        fixture = fixtures.ReadOnlyLeaseTests()
        fixture.setUp()
        devices = dict(zh='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
                       en='BBBBBBBB-BBBB-4BBB-8BBB-BBBBBBBBBBBB')
        fixture.expected['simulator_udids'] = devices
        fixture.value['simulator_udids'] = devices
        raw = compact(fixture.value, sort_keys=True)
        identities = fixture.check()
        self.assertEqual(set(identities), {'zh', 'en'})
        self.assertEqual(fixture.expected['simulator_udids'], devices)
        self.assertEqual(compact(fixture.value, sort_keys=True), raw)


if __name__ == '__main__':
    unittest.main()
