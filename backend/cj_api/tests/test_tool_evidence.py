from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cj_agent.provider import DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL
from cj_api.local_app import ISSUER, scope_for
from cj_api.real_services import RealServices, RealTools, canonical_tool, _lio_tool_result
from cj_api.tool_evidence import ToolEvidence
from cj_run.operation_usage import RegisteredOperation
from cj_run.usage_binding import UsageBinding
from cj_usage.authorization_budget import AuthorizationBudget, canonical
from cj_usage.core import Command
from cj_usage.metered_exit import BudgetUnknown


NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)
SUBJECT = 'm4-synthetic-evidence'
KEY = 'synthetic-evidence-key-not-live'


class ToolEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / 'results'
        self.directory.mkdir(mode=0o700)
        self.manifest = self.root / 'window.json'
        self.data = dict(version='G2C-tool-evidence-window.1', directory=str(self.directory),
            messages=[dict(subject=SUBJECT, message_id='original')],
            expires_at=(NOW + timedelta(hours=1)).isoformat(), source_commit='a' * 40)
        self.write_manifest()

    def write_manifest(self):
        self.manifest.write_bytes(canonical(self.data))
        self.manifest.chmod(0o600)

    def load(self):
        return ToolEvidence.load(self.manifest, frozenset({SUBJECT}), clock=lambda: NOW.timestamp())

    def operation(self, raw, *, message='original'):
        binding = SimpleNamespace(scope=scope_for(ISSUER, SUBJECT), message_id=message, run_id='original-run')
        command = Command('original-attempt', 'original-operation', binding.run_id, 'tool',
                          sha256(raw).hexdigest(), 1, 48000)
        return RegisteredOperation(binding, 'tool.0.0', 'tool.weather', 'original-ledger', (1, 2),
                                   UsageBinding.from_command(command, raw))

    def test_capture_binds_exact_input_result_and_original_receipt(self):
        evidence = self.load()
        raw = canonical(dict(private_projection_field='retained synthetic original', status='ok'))
        operation = self.operation(b'original registered input')
        receipt = dict(response_sha256=sha256(raw).hexdigest(), result_status='ok')
        evidence.record(operation, 'weather', raw, receipt)
        path, = self.directory.iterdir()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        record = json.loads(path.read_bytes())
        self.assertEqual(record['attempt_id'], operation.command.attempt_id)
        self.assertEqual(record['run_id'], operation.binding.run_id)
        self.assertEqual(record['operation_key'], operation.operation_key)
        self.assertEqual(record['input_sha256'], sha256(record['input_utf8'].encode()).hexdigest())
        self.assertEqual(record['response_sha256'], sha256(record['result_utf8'].encode()).hexdigest())
        self.assertEqual(json.loads(record['result_utf8'])['private_projection_field'], 'retained synthetic original')
        self.assertEqual(record['receipt'], receipt)
        self.assertNotIn('Authorization', path.read_text())
        before = path.read_bytes()
        with self.assertRaises(BudgetUnknown):
            evidence.record(operation, 'weather', raw, receipt)
        self.assertEqual(path.read_bytes(), before)

    def test_unselected_message_and_owner_are_not_collected(self):
        evidence = self.load()
        operation = self.operation(b'input', message='other-message')
        evidence.record(operation, 'weather', b'{}', dict(response_sha256='b' * 64))
        operation.binding.message_id = 'original'
        operation.binding.scope = scope_for(ISSUER, 'm4-synthetic-other')
        evidence.record(operation, 'weather', b'{}', dict(response_sha256='b' * 64))
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_expired_selected_capture_stops_without_a_replacement(self):
        evidence = replace(self.load(), clock=lambda: (NOW + timedelta(hours=2)).timestamp())
        with self.assertRaises(BudgetUnknown):
            evidence.record(self.operation(b'input'), 'weather', b'{}', dict(response_sha256='b' * 64))
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_manifest_requires_current_invited_roster_and_unique_messages(self):
        for change in (
            dict(messages=[dict(subject='m4-synthetic-uninvited', message_id='original')]),
            dict(messages=self.data['messages'] * 2),
            dict(expires_at=NOW.isoformat()),
            dict(expires_at=(NOW + timedelta(days=2)).isoformat()),
            dict(expires_at='2026-11-11T00:30:00'),
            dict(expires_at=42),
            dict(source_commit='unfixed'),
        ):
            with self.subTest(change=change):
                original = self.data
                self.data = {**original, **change}
                self.write_manifest()
                with self.assertRaises(ValueError):
                    self.load()
                self.data = original

    def test_private_owned_paths_and_duplicate_json_are_required(self):
        self.manifest.chmod(0o644)
        with self.assertRaises(ValueError):
            self.load()
        self.write_manifest()
        self.directory.chmod(0o755)
        with self.assertRaises(ValueError):
            self.load()
        self.directory.chmod(0o700)
        self.manifest.write_text('{"version":1,"version":2}')
        with self.assertRaises(ValueError):
            self.load()
        self.write_manifest()
        link = self.root / 'link.json'
        link.symlink_to(self.manifest)
        with self.assertRaises(OSError):
            ToolEvidence.load(link, frozenset({SUBJECT}))
        with patch('cj_api.tool_evidence.os.getuid', return_value=os.getuid() + 1):
            with self.assertRaises(ValueError):
                self.load()

    def test_failed_durable_capture_is_unknown(self):
        evidence = self.load()
        with patch('cj_api.tool_evidence.os.fsync', side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(BudgetUnknown):
                evidence.record(self.operation(b'input'), 'weather', b'{}', dict(response_sha256='b' * 64))

    def test_real_tool_producer_is_observed_once_before_lio_projection(self):
        budget = AuthorizationBudget(self.root / 'journal', clock=lambda: NOW)
        provider = MeteredDashScopeProvider(DashScopeConfig(M4_BASE, M4_MODEL, KEY), budget)
        services = RealServices(provider, KEY, frozenset({SUBJECT}))
        tools = RealTools(services, tool_evidence=self.load())
        name, query = canonical_tool('weather', json.dumps(dict(start_date='2026-11-11', end_date='2026-11-11')))
        prepared = tools._tool_input(name, (query, 'original-reference'))
        operation = self.operation(prepared.original_bytes)
        result = dict(status='observed', forecasts=[], source_url='https://restapi.amap.com/v3/weather/weatherInfo',
                      retrieved_at=NOW.isoformat(), provider_reporttime='UNKNOWN',
                      opaque_original='synthetic field removed by Lio projection')
        with patch('cj_api.real_services.weather', return_value=result) as external:
            raw = ''.join(prepared.bind_operation(operation, lambda: True)())
        external.assert_called_once()
        self.assertEqual(json.loads(raw), result)
        path, = self.directory.iterdir()
        captured = json.loads(path.read_bytes())
        self.assertEqual(captured['result_utf8'], raw)
        self.assertEqual(captured['input_utf8'].encode(), prepared.original_bytes)
        receipt = budget.inspect()[0]['receipt']
        self.assertEqual(receipt['response_sha256'], sha256(raw.encode()).hexdigest())
        self.assertEqual(captured['response_sha256'], receipt['response_sha256'])
        projected = _lio_tool_result(name, result, dict(title='Weather', url=None, observed_at=NOW.isoformat()),
                                    False, query)
        self.assertNotIn('opaque_original', projected)
        self.assertEqual(budget.inspect()[0]['state'], 'RECEIVED')
