"""Offline phase identity/replay checks; no services, credentials or real ledger."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import real_phase


# Independently recorded production digests, before the identity expansion.
# 936's actual canonical smoke was FAIL, with these same two core files.
LEGACY_PIN='ad3ace1d79f0bfd1f93b3cae643055d257c963c5145720edb0ebdfe0566ed691'
CORE_HASHES={
    'backend/agent/cj_agent/provider.py':'a302b1904a1de740b65076538207533061abf75ade6731b2ceb8cc6e4107abca',
    'backend/cj_api/real_services.py':'192d59ef6ed9e55df81791bd013d67303801d03ae13055749d3523a0c482e911',
}
OLD_FACT_PAIRS=(
    ('13ae82988ffeb4697d0ca65639aa29dd6c9686578439f3cf859865dd4c9eb81e',
     '66888f6ab5f7d2ceaad76a4588c644839744ced960211ab5c62a40d9baa93e54'),
    ('404f8e16d74607d60168e1a81a6a991603e545c6e232c66433a537ca0e113441',
     '038ba5177456c8544ecd063aaf1ee4cce509ceefda3d7012f3695bf5702aff2d'),
    ('e25b98a34debb3e59fb7bb4802b01406fa139e18fcb388ba3fb2b4c1cf09c0ae',
     '038ba5177456c8544ecd063aaf1ee4cce509ceefda3d7012f3695bf5702aff2d'),
)


def historical_hashes(pair):return dict(CORE_HASHES,**dict(zip(real_phase.FACT_SOURCES,pair)))


class PhaseIdentityChecks(unittest.TestCase):
    def sources(self,root):
        for path in (*real_phase.CORE_SOURCES,*real_phase.FACT_SOURCES):
            p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic '+path)

    def test_every_pre_expansion_fact_pair_keeps_original_two_file_key(self):
        for pair in OLD_FACT_PAIRS:
            identity=real_phase._identity(LEGACY_PIN,historical_hashes(pair))
            self.assertEqual((identity['version'],identity['pin']),(1,LEGACY_PIN))
            # Core repairs retain the legacy key scheme for legacy FACT code.
            self.assertEqual(real_phase._identity('a'*64,historical_hashes(pair))['pin'],'a'*64)

    def test_936_claim_result_and_incomplete_legacy_claim_stay_read_only(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(real_phase,'PHASES',Path(folder)):
            phase=Path(folder)/(LEGACY_PIN+'-smoke.json')
            result=phase.with_suffix('.result.json')
            original=b'{"candidate_id":"375f47aa2521fab5964ebb8e9d5c1858fda1332c","status":"FAIL"}'
            phase.write_bytes(b'{"phase":"smoke","adapter_pin":"'+LEGACY_PIN.encode()+b'"}')
            result.write_bytes(original);old=phase.read_bytes()
            for pair in OLD_FACT_PAIRS:
                identity=real_phase._identity(LEGACY_PIN,historical_hashes(pair))
                with patch.object(real_phase,'adapter_identity',return_value=identity):
                    self.assertEqual(real_phase.path_for('smoke'),phase)
                    self.assertTrue(real_phase.claimed('smoke'))
                    self.assertFalse(real_phase.claim('smoke',Path(folder)/'new-output','cosmetic-commit'))
                self.assertEqual(phase.read_bytes(),old);self.assertEqual(result.read_bytes(),original)
            phase.write_bytes(b'{')  # Original interrupted exclusive write is still a claim.
            with patch.object(real_phase,'adapter_identity',return_value=identity):
                self.assertFalse(real_phase.claim('smoke',Path(folder)/'another-output','new-nonce'))
            self.assertEqual(phase.read_bytes(),b'{');self.assertEqual(result.read_bytes(),original)

    def test_each_production_file_change_changes_expanded_identity(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(real_phase,'ROOT',Path(folder)):
            root=Path(folder);self.sources(root);original=real_phase.adapter_identity()
            self.assertEqual(original['version'],2)
            identities={original['pin']}
            for path in (*real_phase.CORE_SOURCES,*real_phase.FACT_SOURCES):
                p=root/path;before=p.read_bytes();p.write_bytes(before+b' production repair')
                changed=real_phase.adapter_identity();self.assertNotEqual(changed['pin'],original['pin'])
                self.assertEqual(changed['source_sha256'][path],sha256(p.read_bytes()).hexdigest())
                identities.add(changed['pin']);p.write_bytes(before)
            self.assertEqual(len(identities),5)
            self.assertEqual(real_phase.adapter_identity(),original)

    def test_fact_only_repair_gets_one_new_phase_without_changing_936_claim(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(real_phase,'PHASES',Path(folder)):
            old=Path(folder)/(LEGACY_PIN+'-smoke.json');old.write_bytes(b'original-936-claim')
            hashes=historical_hashes(OLD_FACT_PAIRS[1]);hashes[real_phase.FACT_SOURCES[1]]=sha256(b'bounded gzip repair').hexdigest()
            identity=real_phase._identity(LEGACY_PIN,hashes)
            self.assertEqual(identity['version'],2);self.assertNotEqual(identity['pin'],LEGACY_PIN)
            with patch.object(real_phase,'adapter_identity',return_value=identity):
                self.assertTrue(real_phase.claim('smoke',Path(folder)/'repair','real-backend-repair'))
                self.assertFalse(real_phase.claim('smoke',Path(folder)/'retry','different-output'))
                claim=json.loads(real_phase.path_for('smoke').read_bytes())
            self.assertEqual(claim['adapter_identity'],identity)
            self.assertEqual(claim['adapter_pin'],identity['pin'])
            self.assertEqual(old.read_bytes(),b'original-936-claim')

    def test_C_runner_reports_configuration_and_candidate_are_not_adapter_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'source';phases=Path(folder)/'phases';self.sources(root)
            with patch.object(real_phase,'ROOT',root),patch.object(real_phase,'PHASES',phases):
                pin=real_phase.adapter_pin()
                self.assertTrue(real_phase.claim('smoke',Path(folder)/'original','candidate1'))
                for path in ('eval/real_phase.py','eval/report.py','eval/config.json','eval/reports/report.json'):
                    p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('different C-only bytes')
                    self.assertEqual(real_phase.adapter_pin(),pin)
                    self.assertFalse(real_phase.claim('smoke',Path(folder)/path,'cosmetic2'))

    def test_missing_source_prevents_any_claim_creation(self):
        for missing in (*real_phase.CORE_SOURCES,*real_phase.FACT_SOURCES):
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder)/'source';phases=Path(folder)/'phases';self.sources(root);(root/missing).unlink()
                with patch.object(real_phase,'ROOT',root),patch.object(real_phase,'PHASES',phases):
                    with self.assertRaises(FileNotFoundError):real_phase.claim('smoke',Path(folder)/'output','candidate')
                self.assertFalse(phases.exists())

    def test_parallel_distinct_aliases_cannot_claim_more_than_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'source';phases=Path(folder)/'phases';self.sources(root)
            with patch.object(real_phase,'ROOT',root),patch.object(real_phase,'PHASES',phases):
                with ThreadPoolExecutor(max_workers=16) as pool:
                    results=list(pool.map(lambda i:real_phase.claim('smoke',Path(folder)/str(i),'candidate'+str(i)),range(32)))
                self.assertEqual(sum(results),1)
                files=list(phases.glob('*.json'));self.assertEqual(len(files),1)
                claim=json.loads(files[0].read_bytes())
                self.assertEqual(claim['adapter_identity'],real_phase.adapter_identity())

    def test_known_phase_restriction_stays_in_force(self):
        with self.assertRaisesRegex(ValueError,'known_round2_phase_required'):real_phase.path_for('smoke-alias')


if __name__=='__main__':unittest.main()
