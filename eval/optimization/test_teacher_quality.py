"""Independent controls at the D boundary, using the fixed public F source."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from .teacher_quality import sampling

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).with_name("teacher_quality.py")
PINS = json.loads(Path(__file__).with_name("teacher-input.v1.json").read_bytes())


class TeacherQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="g2c-d788-controls-")
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / "source"
        subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "--detach",
                str(cls.source),
                PINS["producer_commit"],
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        # No HTTP/model/provider is selected. Reuse F's documented public Fake generator.
        code = """import sys,pathlib
r=pathlib.Path(sys.argv[1]);sys.path[:0]=[str(r),str(r/'backend'),*[str(p) for p in sorted((r/'backend').iterdir()) if p.is_dir()]]
from tooling.datasets.teacher import main
raise SystemExit(main(sys.argv[2:]))"""
        for control in PINS["controls"]:
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    code,
                    str(cls.source),
                    "--mode",
                    "fake",
                    "--control",
                    control,
                    "--output",
                    str(cls.root / control),
                ],
                cwd=cls.source,
                capture_output=True,
            )
            if result.returncode != (0 if control == "smoke" else 2):
                raise AssertionError(result.stderr.decode())
        cls.addClassCleanup(cls.cleanup)

    @classmethod
    def cleanup(cls):
        subprocess.run(
            ["git", "worktree", "remove", str(cls.source)],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        cls.temp.cleanup()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=self.root, prefix="case-"))
        self.addCleanup(shutil.rmtree, self.folder)

    def run_checker(self, bundle, name="result", manifest_hash=None, source=None):
        if manifest_hash is None:
            manifest_hash = sha256((bundle / "handoff.json").read_bytes()).hexdigest()
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPT),
                "--bundle",
                str(bundle),
                "--source-root",
                str(source or self.source),
                "--manifest-sha256",
                manifest_hash,
                "--output",
                str(self.folder / (name + ".json")),
            ],
            cwd=ROOT,
            capture_output=True,
        )
        self.assertIn(result.returncode, (0, 2), result.stderr.decode())
        self.assertTrue((self.folder / (name + ".json")).exists(), result.stderr.decode())
        report = json.loads((self.folder / (name + ".json")).read_bytes())
        self.assertEqual(report["g_handoff"]["training_samples"], [])
        return report, result.returncode

    def mutated(self, mutator):
        bundle = self.folder / "bundle"
        shutil.copytree(self.root / "smoke", bundle)
        mutator(bundle)
        # Even producer-rehashed artifacts must fail independent checks, not just checksums.
        manifest = json.loads((bundle / "handoff.json").read_bytes())
        for name in manifest["artifacts"]:
            raw = (bundle / name).read_bytes()
            manifest["artifacts"][name] = {
                "bytes": len(raw),
                "sha256": sha256(raw).hexdigest(),
            }
        (bundle / "handoff.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        return bundle

    @staticmethod
    def edit_jsonl(bundle, name, fn):
        rows = [json.loads(line) for line in (bundle / name).read_text().splitlines()]
        fn(rows)
        (bundle / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))

    def test_good_complete_package_repeats_full_result_and_never_releases_training(
        self,
    ):
        a, exitcode = self.run_checker(self.root / "smoke", "first")
        b, _ = self.run_checker(self.root / "smoke", "second")
        self.assertEqual(a, b)
        self.assertEqual(exitcode, 0)
        self.assertEqual(a["status"], "PASS")
        self.assertFalse(a["training_allowed"])
        self.assertEqual(a["release_eligibility"], "fake_only_not_released")
        self.assertEqual(a["denominators"]["generation"]["planned"], 21)
        self.assertEqual(a["denominators"]["accepted"], 16)
        self.assertEqual(a["denominators"]["families"], 8)
        self.assertEqual(a["denominators"]["split_counts"], {"train": 12, "validation": 2, "test": 2})
        self.assertEqual(a["denominators"]["control_only"], 4)
        self.assertEqual(a["sampling_plan"]["planned_families"], 8)
        self.assertEqual(a["sampling_plan"]["actual_human_reviewed"], 0)
        for key in ("D_independent_sampling", "C_domain_review", "R_dataset_review"):
            self.assertEqual(a["sampling_plan"][key], "UNRUN")

    def test_original_bad_receipt_is_fail_even_when_F_preserves_unknown(self):
        r, c = self.run_checker(self.root / "bad-receipt")
        self.assertEqual((r["status"], c), ("FAIL", 2))
        self.assertTrue(any(x["status"] == "FAIL" and "receipt" in x["name"] for x in r["checks"]))
        self.assertFalse(r["g_handoff"]["training_allowed"])

    def test_unknown_partial_result_stops_and_cannot_train(self):
        r, c = self.run_checker(self.root / "unknown")
        self.assertEqual((r["status"], c), ("UNKNOWN", 2))
        self.assertEqual(r["denominators"]["generation"]["statuses"], {"UNKNOWN": 1, "UNRUN": 1})
        self.assertFalse(r["training_allowed"])

    def test_received_supplier_raw_bytes_are_checked_independently(self):
        def change(bundle):
            def mutate(rows):
                event = next(x for x in rows if x["execution"]["status"] == "received")
                import base64

                raw = json.loads(base64.b64decode(event["response_base64"]))
                raw["pois"][0]["name"] = "forged supplier name"
                event["response_base64"] = base64.b64encode(json.dumps(raw).encode()).decode()

            self.edit_jsonl(bundle, "tools.jsonl", mutate)

        r, _ = self.run_checker(self.mutated(change))
        failures = {x["reason"] for x in r["checks"] if x["status"] == "FAIL"}
        self.assertIn("supplier_bytes_disagree_with_result", failures)

    def test_rehashed_cross_purpose_family_leak_is_hard_rejected(self):
        def change(bundle):
            (bundle / "validation.jsonl").write_bytes(
                (bundle / "validation.jsonl").read_bytes()
                + (bundle / "train.jsonl").read_bytes().splitlines()[0]
                + b"\n"
            )

        r, _ = self.run_checker(self.mutated(change))
        self.assertTrue(any(x["name"] == "purpose/validation" and x["status"] == "FAIL" for x in r["checks"]))
        self.assertEqual(r["release_eligibility"], "rejected")

    def test_source_teacher_and_unapproved_text_cannot_be_laundered_as_fake(self):
        for kind in ("teacher", "real_user"):
            with self.subTest(kind=kind):
                bundle = self.mutated(
                    lambda b: self.edit_jsonl(
                        b,
                        "candidates.jsonl",
                        lambda rows: rows[0]["source"].update(kind=kind),
                    )
                )
                r, _ = self.run_checker(bundle, kind)
                self.assertTrue(
                    any(
                        x["name"].endswith("/F_schema_execution_source") and x["status"] == "FAIL"
                        for x in r["checks"]
                    )
                )
                shutil.rmtree(bundle)
        bundle = self.mutated(
            lambda b: self.edit_jsonl(
                b,
                "models.jsonl",
                lambda rows: rows[0]["input_messages"].append(
                    {"role": "user", "content": "UNAPPROVED_FINAL_OR_SECRET_CONTROL"}
                ),
            )
        )
        r, _ = self.run_checker(bundle, "contamination")
        self.assertTrue(
            any(x["name"] == "public_fixture_origin" and x["status"] == "FAIL" for x in r["checks"])
        )

    def test_original_model_input_and_request_counts_must_match(self):
        def change(bundle):
            self.edit_jsonl(
                bundle,
                "models.jsonl",
                lambda rows: rows[0].update(task_attempt_id="wrong-original-attempt"),
            )

        r, _ = self.run_checker(self.mutated(change))
        self.assertTrue(any(x["reason"] == "request_denominator_mismatch" for x in r["checks"]))

    def test_missing_received_provenance_and_null_result_produce_structured_rejection(self):
        for label, change in [
            (
                "missing_time",
                lambda b: self.edit_jsonl(b, "tools.jsonl", lambda rows: rows[0].pop("query_started_at")),
            ),
            (
                "null_result",
                lambda b: self.edit_jsonl(
                    b,
                    "candidates.jsonl",
                    lambda rows: next(
                        r for r in rows if r["executions"] and r["executions"][0]["status"] == "received"
                    )["executions"][0]["result"].update(value=None),
                ),
            ),
        ]:
            with self.subTest(label=label):
                bundle = self.mutated(change)
                r, code = self.run_checker(bundle, label)
                self.assertEqual(code, 2)
                self.assertFalse(r["training_allowed"])
                self.assertTrue(
                    any(x["reason"] in ("supplier_provenance_missing", "schema_invalid") for x in r["checks"])
                )
                shutil.rmtree(bundle)

    def test_no_results_truthful_completion_and_fabricated_hit_are_distinct(self):
        def change(bundle):
            def mutate(rows):
                row = next(r for r in rows if r["task_id"] == "f768-empty")
                row["messages"][-1]["content"] = "I found matching places."

            self.edit_jsonl(bundle, "candidates.jsonl", mutate)

        r, _ = self.run_checker(self.mutated(change))
        self.assertTrue(any(x["reason"] == "known_no_results_fabricated_hit" for x in r["checks"]))

    def test_unsettled_model_cannot_claim_completed_answer(self):
        def change(bundle):
            self.edit_jsonl(bundle, "models.jsonl", lambda rows: rows[0].update(state="unknown"))

        r, _ = self.run_checker(self.mutated(change))
        self.assertTrue(any(x["reason"] == "unsettled_model_claimed_complete" for x in r["checks"]))

    def test_missing_started_task_original_is_not_hidden_by_totals(self):
        def change(bundle):
            self.edit_jsonl(bundle, "raw-candidates.jsonl", lambda rows: rows.pop(0))

        r, _ = self.run_checker(self.mutated(change))
        self.assertTrue(any(x["reason"] == "missing_started_task_original" for x in r["checks"]))

    def test_missing_artifact_invalid_json_wrong_frozen_digest_fail_closed(self):
        for label, fn in [
            ("missing", lambda b: (b / "tools.jsonl").unlink()),
            (
                "duplicate_json",
                lambda b: (b / "tasks.json").write_text('[{"sample_id":"x","sample_id":"y"}]'),
            ),
        ]:
            bundle = self.folder / label
            shutil.copytree(self.root / "smoke", bundle)
            fn(bundle)
            r, c = self.run_checker(bundle, label)
            self.assertEqual((r["status"], c), ("UNKNOWN" if label == "missing" else "FAIL", 2))
        r, _ = self.run_checker(self.root / "smoke", "digest", manifest_hash="0" * 64)
        self.assertTrue(
            any(x["name"] == "frozen_input_manifest" and x["status"] == "FAIL" for x in r["checks"])
        )

    def test_artifact_path_escape_or_symlink_never_followed(self):
        bundle = self.folder / "escape"
        shutil.copytree(self.root / "smoke", bundle)
        p = bundle / "handoff.json"
        m = json.loads(p.read_bytes())
        m["artifacts"]["../private"] = {"sha256": "0" * 64, "bytes": 0}
        p.write_text(json.dumps(m))
        r, _ = self.run_checker(bundle, "escape")
        self.assertEqual(r["status"], "FAIL")
        bundle = self.folder / "symlink"
        shutil.copytree(self.root / "smoke", bundle)
        (bundle / "tools.jsonl").unlink()
        (bundle / "tools.jsonl").symlink_to(self.root / "smoke" / "tools.jsonl")
        r, _ = self.run_checker(bundle, "symlink")
        self.assertEqual(r["status"], "FAIL")

    def test_manifest_cannot_self_grant_training(self):
        def change(bundle):
            p = bundle / "handoff.json"
            m = json.loads(p.read_bytes())
            m.update(
                quality_status="PASS",
                release_eligibility="training_eligible",
                training_status="PASS",
            )
            p.write_text(json.dumps(m))

        r, _ = self.run_checker(self.mutated(change))
        self.assertEqual(r["status"], "FAIL")
        self.assertFalse(r["training_allowed"])

    def test_expansion_sampling_is_stable_and_covers_language_behavior_whole_groups(
        self,
    ):
        groups = {f"family-{i}": {} for i in range(25)}
        rows = [
            (
                {"language": "zh" if i % 2 else "en", "scenario": str(i % 7)},
                f"family-{i}",
            )
            for i in range(25)
        ]
        a = sampling(groups, rows)
        b = sampling(dict(reversed(list(groups.items()))), list(reversed(rows)))
        self.assertEqual(a, b)
        self.assertGreaterEqual(a["planned_families"], 5)
        selected = set(a["selected_families"])
        self.assertEqual(
            {r["language"] + "/" + r["scenario"] for r, g in rows},
            {r["language"] + "/" + r["scenario"] for r, g in rows if g in selected},
        )


if __name__ == "__main__":
    unittest.main()
