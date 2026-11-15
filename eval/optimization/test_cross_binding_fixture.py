"""Schema/fixture-shape conformance only. E protected runtime checks remain UNRUN."""

from copy import deepcopy
from pathlib import Path
import json
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from runtime_adapter.contract import decode, digest

HERE = Path(__file__).with_name("fixtures")
SCHEMA = decode((HERE / "cross-binding-fixture.v1.schema.json").read_bytes())
EXAMPLES = decode((HERE / "cross-binding-fixture.examples.v1.json").read_bytes())
VECTORS = decode((HERE / "cross-binding-fixture.conformance.v1.json").read_bytes())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


class CrossBindingFixtureSpecTests(unittest.TestCase):
    def test_schema_and_both_public_structural_controls(self):
        Draft202012Validator.check_schema(SCHEMA)
        for kind in ("definition", "use"):
            with self.subTest(kind=kind):
                VALIDATOR.validate(EXAMPLES[kind])
        self.assertEqual(EXAMPLES["runtime_eligibility"], "UNRUN")
        self.assertEqual(EXAMPLES["use"]["definition_ref"]["sha256"], digest(EXAMPLES["definition"]))
        self.assertEqual(EXAMPLES["definition_wire_sha256"], digest(EXAMPLES["definition"]))
        self.assertEqual(EXAMPLES["use_wire_sha256"], digest(EXAMPLES["use"]))
        self.assertEqual(EXAMPLES["use"]["coverage"]["foreign_write_interface"], "UNRUN")
        self.assertEqual(EXAMPLES["use"]["coverage"]["semantic_disclosure_review"], "UNKNOWN")
        self.assertEqual(
            EXAMPLES["use"]["observer"]["binding"], EXAMPLES["definition"]["producer"]["binding"]
        )

    def test_wrong_version_extra_private_body_and_credentials_rejected(self):
        for field, value in [
            ("version", "G2C-cross-binding-fixture.2"),
            ("token", "synthetic-not-a-credential"),
            ("private_trip_body", "synthetic-private-body"),
            ("sentinel", "synthetic-private-sentinel"),
        ]:
            row = deepcopy(EXAMPLES["use"])
            row[field] = value
            with self.subTest(field=field):
                self.assertFalse(VALIDATOR.is_valid(row))

    def test_non_opaque_references_and_invalid_dates_are_rejected(self):
        for bad in ("https://example.test/original", "../private", "/private/file", "original-not-a-hash"):
            row = deepcopy(EXAMPLES["use"])
            row["definition_ref"]["ref"] = bad
            self.assertFalse(VALIDATOR.is_valid(row))
        row = deepcopy(EXAMPLES["definition"])
        row["frozen_at"] = "2026-11-13T12:00:00"
        self.assertFalse(VALIDATOR.is_valid(row))

    def test_declared_pass_requires_present_evidence_zero_observations_and_all_checks(self):
        for mutate in (
            lambda r: r.update(observer=None),
            lambda r: r["observer"].update(private_visible_hits=1),
            lambda r: r["consumer"].update(inventory_ref=None),
            lambda r: r["checks"]["cost_accounting"].update(status="UNKNOWN"),
            lambda r: r["checks"].pop("private_disclosure_scan"),
        ):
            row = deepcopy(EXAMPLES["use"])
            mutate(row)
            self.assertFalse(VALIDATOR.is_valid(row))
        row = deepcopy(EXAMPLES["definition"])
        row["producer"]["fee_inventory_ref"] = None
        self.assertFalse(VALIDATOR.is_valid(row))

    def test_unknown_explicitly_does_not_manufacture_zero_or_authority(self):
        row = deepcopy(EXAMPLES["use"])
        row.update(evidence_status="UNKNOWN", observer=None)
        for check in row["checks"].values():
            check.update(status="UNKNOWN", reason="MISSING_ORIGINAL", evidence_refs=[])
        VALIDATOR.validate(row)
        row["observer"] = deepcopy(EXAMPLES["use"]["observer"])
        row["observer"].update(foreign_read_rows=None, foreign_mutations=None, private_visible_hits=None)
        VALIDATOR.validate(row)
        row["evidence_status"] = "PASS"
        self.assertFalse(VALIDATOR.is_valid(row))

    def test_known_check_or_coverage_failure_dominates_root_status(self):
        for group in ("checks", "coverage"):
            for field in EXAMPLES["use"][group]:
                with self.subTest(group=group, field=field):
                    row = deepcopy(EXAMPLES["use"])
                    if group == "checks":
                        row[group][field].update(status="FAIL", reason="ASSOCIATION_MISMATCH")
                    else:
                        row[group][field] = "FAIL"
                    for root_status in ("PASS", "UNKNOWN"):
                        row["evidence_status"] = root_status
                        self.assertFalse(VALIDATOR.is_valid(row))
                    row["evidence_status"] = "FAIL"
                    VALIDATOR.validate(row)

    def test_unrun_is_unstarted_not_fabricated_probe(self):
        row = deepcopy(EXAMPLES["use"])
        row.update(evidence_status="UNRUN", stage="NOT_STARTED", observer=None)
        row["consumer"].update(probes=[], task_terminal_at=None)
        for check in row["checks"].values():
            check.update(status="UNRUN", reason="NOT_STARTED", evidence_refs=[])
        VALIDATOR.validate(row)
        row["consumer"]["probes"] = EXAMPLES["use"]["consumer"]["probes"]
        self.assertFalse(VALIDATOR.is_valid(row))

    def test_implementation_vectors_are_complete_but_not_runtime_results(self):
        self.assertEqual(VECTORS["E_runtime_execution"], "UNRUN")
        ids = [v["id"] for v in VECTORS["vectors"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({v["expected"] for v in VECTORS["vectors"]}, {"PASS", "FAIL", "UNKNOWN", "UNRUN"})
        rules = {rule for v in VECTORS["vectors"] for rule in v["rule_ids"]}
        self.assertEqual(rules, {"X" + str(i).zfill(2) for i in range(1, 13)})
        normative = (HERE / "CROSS-BINDING-FIXTURE-v1.md").read_text()
        for rule in rules:
            self.assertIn("**" + rule, normative)
        self.assertIn("same-owner-new-session", ids)
        self.assertIn("hash-cycle", ids)
        self.assertIn("consumer-revoked-before-publication", ids)
        self.assertIn("duplicate-preparation-charge", ids)
        self.assertIn("session-rotation-no-v1-bridge", ids)
        self.assertIn("no-isolation-fence", ids)


if __name__ == "__main__":
    unittest.main()
