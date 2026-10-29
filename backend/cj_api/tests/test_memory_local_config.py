"""Local MEMORY policy configuration boundary; synthetic statements only."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from cj_memory.local import LocalMemoryConfiguration, LocalMemoryConfigurationError, load_local_memory_configuration
from cj_memory.manual import parse_manual
from cj_memory.domain import Unavailable


def policy_value(*, expiry=None):
    return {'version': 'local-memory-policy.1',
            'expires_at': (expiry or datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            'profiles': {'alice': {'subjects': ['self'], 'extents': ['long_term', 'current'],
                'context_ids': ['chat-alice'], 'slots': {
                    'food.spice': {'kind': 'preference', 'collection_allowed': True, 'semantic_resolved': True},
                    'ambiguous': {'kind': 'fact', 'collection_allowed': True, 'semantic_resolved': False},
                    'blocked': {'kind': 'fact', 'collection_allowed': False, 'semantic_resolved': True}}}}}


def manual(**changes):
    value = dict(operation_id='op1', item_id='item1', subject='self', slot='food.spice',
                 kind='preference', text='Synthetic preference / 合成偏好', extent='long_term',
                 context_id=None, occurred_at='date unknown')
    value.update(changes)
    raw = json.dumps(value, ensure_ascii=False).encode()
    return parse_manual(raw), raw


class LocalMemoryConfigurationTests(unittest.TestCase):
    def test_explicit_profile_and_semantics_do_not_normalize_user_text(self):
        config = LocalMemoryConfiguration.from_bytes(json.dumps(policy_value()).encode())
        self.assertIsNone(config.profiles.get('bob'))
        policy = config.profiles['alice'].manual_policy()
        command, raw = manual()
        self.assertTrue(policy.evaluate(command, raw))
        self.assertEqual(command.text, 'Synthetic preference / 合成偏好')
        command, raw = manual(slot='ambiguous', kind='fact')
        self.assertFalse(policy.evaluate(command, raw))
        for changes in ({'slot':'blocked','kind':'fact'}, {'subject':'other'}, {'slot':'unapproved'},
                        {'kind':'experience'}, {'extent':'current','context_id':'foreign-chat'}):
            with self.subTest(changes=changes), self.assertRaises(Unavailable):
                policy.evaluate(*manual(**changes))
        with self.assertRaises(TypeError): config.profiles['alice'] = config.profiles['alice']

    def test_no_implicit_scope_deadline_or_approval_defaults(self):
        cases = []
        for field in ('expires_at', 'profiles'):
            value = policy_value(); del value[field]; cases.append(value)
        value = policy_value(); value['expires_at'] = '2026-12-01T00:00:00'; cases.append(value)
        value = policy_value(); value['profiles'] = {}; cases.append(value)
        for flag in ('collection_allowed', 'semantic_resolved'):
            value = policy_value(); del value['profiles']['alice']['slots']['food.spice'][flag]; cases.append(value)
            value = policy_value(); value['profiles']['alice']['slots']['food.spice'][flag] = 1; cases.append(value)
        value = policy_value(); value['profiles']['alice']['subjects'] = ['self', 'self']; cases.append(value)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(LocalMemoryConfigurationError):
                LocalMemoryConfiguration.from_bytes(json.dumps(value).encode())
        with self.assertRaises(LocalMemoryConfigurationError):
            LocalMemoryConfiguration.from_bytes(b'{"profiles":{},"profiles":{}}')
        with self.assertRaises(LocalMemoryConfigurationError):
            LocalMemoryConfiguration.from_bytes(b'x' * 262145)

    def test_expired_policy_never_authorizes_a_new_save(self):
        value = policy_value(expiry=datetime.now(timezone.utc)-timedelta(seconds=1))
        policy = LocalMemoryConfiguration.from_bytes(json.dumps(value).encode()).profiles['alice'].manual_policy()
        with self.assertRaises(Unavailable): policy.evaluate(*manual())

    def test_policy_file_is_explicit_private_regular_and_not_a_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'policy.json'
            with self.assertRaises(LocalMemoryConfigurationError): load_local_memory_configuration(path)
            path.write_text(json.dumps(policy_value())); path.chmod(0o600)
            self.assertIn('alice', load_local_memory_configuration(path).profiles)
            path.chmod(0o644)
            with self.assertRaises(LocalMemoryConfigurationError): load_local_memory_configuration(path)
            path.chmod(0o600)
            link = path.with_name('link.json'); link.symlink_to(path)
            with self.assertRaises(LocalMemoryConfigurationError): load_local_memory_configuration(link)
