"""Independent, read-only QA of the frozen F794 public Fake handoff.

CLI runs in a fresh interpreter. It imports the original F/C validators only
from the verified source checkout; it never generates replies or dispatches tools.
"""

import argparse
import base64
from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
import subprocess
import sys

RULE_PATH = Path(__file__).with_name("teacher-rules.v1.json")
RULES = json.loads(RULE_PATH.read_bytes())
VERSION = RULES["score_version"]
SEED = RULES["seed"]
PIN_PATH = Path(__file__).with_name("teacher-input.v1.json")


def digest(raw):
    return sha256(raw).hexdigest()


def same(a, b):
    # Explicit JSON representation keeps false distinct from 0.
    options = dict(sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
    return json.dumps(a, **options) == json.dumps(b, **options)


class Invalid(ValueError):
    pass


def require(value, reason):
    if not value:
        raise Invalid(reason)


class MissingEvidence(Invalid):
    pass


class Checks:
    def __init__(self):
        self.items = []
        self.external_errors = (ValueError, UnicodeError)
        self.rejections = (Invalid,)

    def add(self, name, ok, ref, reason):
        self.items.append(
            dict(
                name=name,
                status="PASS" if ok else "FAIL",
                evidence_ref=ref,
                reason=None if ok else reason,
            )
        )

    def run(self, name, ref, operation):
        try:
            operation()
        except MissingEvidence as error:
            self.items.append(dict(name=name, status="UNKNOWN", evidence_ref=ref, reason=str(error)))
        except self.external_errors as error:
            # External malformed records are diagnostics; programming errors propagate.
            self.add(
                name,
                False,
                ref,
                (str(error) if isinstance(error, self.rejections) else "invalid_external_value"),
            )
        else:
            self.add(name, True, ref, None)


def sampling(groups, rows):
    order = sorted(groups, key=lambda group: (digest((SEED + "\0" + group).encode()), group))
    if len(order) <= RULES["pilot_max_families"]:
        selected = set(order)
        rule = "pilot_all_complete_families"
    else:
        selected = set(order[: ceil(len(order) * RULES["expansion_minimum_fraction"])])
        rule = "ceil_20_percent_plus_language_behavior_coverage"
        strata = {}
        for row, group in rows:
            strata.setdefault(row["language"] + "/" + row["scenario"], set()).add(group)
        for layer in sorted(strata):
            eligible = strata[layer]
            if len(eligible) == 1:
                selected.update(eligible)
            elif not selected & eligible:
                selected.add(next(group for group in order if group in eligible))
    chosen = [group for group in order if group in selected]
    raw = json.dumps(chosen, ensure_ascii=False, indent=2).encode()
    return dict(
        version=SEED,
        unit="connected_complete_family",
        rule=rule,
        total_families=len(order),
        planned_families=len(chosen),
        selected_families=chosen,
        list_sha256=digest(raw),
        actual_human_reviewed=0,
        D_independent_sampling="UNRUN",
        C_domain_review="UNRUN",
        R_dataset_review="UNRUN",
    )


def finish(checks, manifest_hash, pins, mode=None, counts=None, selection=None, unknown=False):
    statuses = Counter(item["status"] for item in checks.items)
    state = "FAIL" if statuses["FAIL"] else "UNKNOWN" if unknown or statuses["UNKNOWN"] else "PASS"
    eligibility = (
        "rejected"
        if state == "FAIL"
        else "blocked_unknown" if state == "UNKNOWN" else "fake_only_not_released"
    )
    return dict(
        version=VERSION,
        scope="independent_frozen_fake_checks_only",
        input_manifest_sha256=manifest_hash,
        input_contract=pins["version"],
        producer_commit=pins["producer_commit"],
        control=mode,
        status=state,
        checker_sha256=digest(Path(__file__).read_bytes()),
        input_pin_sha256=digest(PIN_PATH.read_bytes()),
        rules_version=RULES["version"],
        rules_sha256=digest(RULE_PATH.read_bytes()),
        checks=checks.items,
        check_counts={key: statuses[key] for key in ("PASS", "FAIL", "UNKNOWN", "UNRUN")},
        denominators=counts,
        sampling_plan=selection,
        semantic_quality="UNKNOWN",
        real_teacher_quality="UNRUN",
        release_eligibility=eligibility,
        training_allowed=False,
        g_handoff=dict(
            version="G2C-quality-handoff.1",
            input_manifest_sha256=manifest_hash,
            checker_version=VERSION,
            usage="public_fake_interface_control_only",
            release_eligibility=eligibility,
            training_allowed=False,
            real_teacher_admission="UNRUN",
            C_domain_review="UNRUN",
            R_dataset_review="UNRUN",
        ),
    )


def audit(bundle, source_root, expected_manifest_hash):
    pins = json.loads(PIN_PATH.read_bytes())  # Reviewed D configuration, not producer input.
    checks = Checks()

    def source_check():
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source_root, text=True).strip()
        require(revision == pins["producer_commit"], "wrong_frozen_source_commit")
        require(
            not subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=normal"],
                cwd=source_root,
            ),
            "dirty_frozen_source_checkout",
        )
        for name, expected in pins["source_hashes"].items():
            require(
                digest((source_root / name).read_bytes()) == expected,
                "frozen_source_hash_mismatch",
            )

    try:
        checks.run("frozen_F_C_source", "producer_commit/source_hashes", source_check)
    except (OSError, subprocess.CalledProcessError):
        checks.items.append(
            dict(
                name="frozen_F_C_source",
                status="UNKNOWN",
                evidence_ref="producer_commit/source_hashes",
                reason="source_unavailable",
            )
        )
    if checks.items[-1]["status"] != "PASS":
        return finish(checks, expected_manifest_hash, pins)
    # The CLI is a fresh process: select the fixed F/C tree before any domain imports.
    sys.path[:0] = [
        str(source_root),
        str(source_root / "backend"),
        *[str(path) for path in sorted((source_root / "backend").iterdir()) if path.is_dir()],
    ]
    from tooling.datasets import convert as F
    from tooling.datasets import teacher as T

    require(F.ROOT.resolve() == source_root.resolve(), "mixed_F_environment")
    checks.external_errors += (F.ProviderUnknown, F.FactFailure)
    checks.rejections += (F.Rejected,)
    names = set(pins["controls"]["smoke"]["artifacts"])
    try:
        require(not (bundle / "handoff.json").is_symlink(), "symlink_manifest")
        raw_manifest = (bundle / "handoff.json").read_bytes()
        manifest = F.load(raw_manifest)
        require(type(manifest) is dict, "manifest_object_required")
        checks.add(
            "frozen_input_manifest",
            digest(raw_manifest) == expected_manifest_hash,
            "handoff.json",
            "input_manifest_digest_mismatch",
        )
        require(
            type(manifest.get("artifacts")) is dict and set(manifest["artifacts"]) == names,
            "exact_artifact_inventory_required",
        )
        require(
            not ({p.name for p in bundle.iterdir()} - names - {"handoff.json"}),
            "unexpected_bundle_file",
        )
        files = {}
        raw_files = {}
        for name in sorted(names):
            path = bundle / name
            require(not path.is_symlink(), "artifact_symlink")
            if not path.is_file():
                raise MissingEvidence("artifact_missing")
            raw = path.read_bytes()
            checks.add(
                "artifact/" + name,
                same(
                    manifest["artifacts"][name],
                    dict(bytes=len(raw), sha256=digest(raw)),
                ),
                name,
                "artifact_hash_or_size_mismatch",
            )
            raw_files[name] = raw
            files[name] = (
                [F.load(line) for line in raw.splitlines()] if name.endswith(".jsonl") else F.load(raw)
            )
            F.canonical(files[name]).encode("utf8")
        require(
            all(
                type(files[name]) is list
                for name in names
                if name.endswith(".jsonl") or name in ("tasks.json", "planned-cases.json", "lineage.json")
            ),
            "invalid_record_container",
        )
        require(
            all(
                type(row) is dict
                for name in (
                    "tasks.json",
                    "planned-cases.json",
                    "lineage.json",
                    "candidates.jsonl",
                    "raw-candidates.jsonl",
                    "models.jsonl",
                    "tools.jsonl",
                )
                for row in files[name]
            ),
            "invalid_record_object",
        )
        manifest_hash = digest(raw_manifest)
    except (MissingEvidence, FileNotFoundError) as error:
        checks.items.append(
            dict(
                name="bundle_boundary",
                status="UNKNOWN",
                evidence_ref="handoff.json/artifacts",
                reason="required_artifact_unavailable",
            )
        )
        return finish(checks, expected_manifest_hash, pins)
    except (OSError, ValueError, UnicodeError) as error:
        checks.add(
            "bundle_boundary",
            False,
            "handoff.json/artifacts",
            str(error) if isinstance(error, Invalid) else "invalid_bundle",
        )
        return finish(checks, expected_manifest_hash, pins)
    mode = None
    for control in pins["controls"]:
        plan = T.cases(control)
        expected_plan = [
            dict(
                sample_id=c.name,
                task_id=c.template["task_id"],
                trip_family=c.template["trip_family"],
                rewrite_family=c.template["rewrite_family"],
                language=c.template["language"],
                scenario=c.template["scenario"],
                fake_fault=c.fault,
                source_fixture_sha256=F.digest(c.template),
            )
            for c in plan
        ]
        if same(files["planned-cases.json"], expected_plan):
            mode = control
            break
    checks.add(
        "public_fake_plan",
        mode is not None,
        "planned-cases.json",
        "unknown_or_contaminated_task_plan",
    )
    if mode is None:
        return finish(checks, manifest_hash, pins)
    checks.add(
        "frozen_F_handoff_identity",
        manifest_hash == pins["controls"][mode]["manifest_sha256"],
        "handoff.json",
        "unapproved_handoff_digest",
    )
    # This version only accepts the published public Fake controls. No heuristic
    # claims that arbitrary text is secret-free or free of final-question leakage.
    checks.add(
        "public_fixture_origin",
        same(manifest["artifacts"], pins["controls"][mode]["artifacts"]),
        "frozen_public_artifact_hashes",
        "unapproved_or_contaminated_fake_payload",
    )
    expected_meta = dict(
        version="G2C-teacher-handoff.1",
        mode="fake",
        batch_id=pins["batch_id"],
        candidate_version="F789-fake.1",
        parent_issue=767,
        producer_issue=789,
        independent_quality_issue=788,
        record_schema="G2C-dataset.1",
        tools_sha256=F.TOOLS_HASH,
        source_hashes=pins["source_hashes"],
        reference_manifest_sha256=pins["reference_manifest_sha256"],
        quality_status="UNRUN",
        release_eligibility="fake_only_not_released",
        training_status="UNRUN",
        live_adapter_status="UNRUN",
        live_authorization_checked=False,
        semantic_quality="UNKNOWN",
        original_cost_evidence=dict(status="UNRUN", reason="fake_has_no_original_meter", ledger_ref=None),
    )
    checks.add(
        "source_versions_and_usage",
        same({k: manifest.get(k) for k in expected_meta}, expected_meta),
        "handoff.json",
        "source_version_or_usage_mismatch",
    )
    checks.add(
        "producer_revision",
        manifest.get("repository_revision") == pins["producer_commit"],
        "handoff.json",
        "unapproved_producer_revision",
    )

    def sidecar_shape():
        required = {
            "tasks.json": {
                "sample_id": str,
                "task_id": str,
                "trip_family": str,
                "rewrite_family": str,
                "language": str,
                "scenario": str,
                "processing_status": str,
                "reason": (str, type(None)),
                "model_requests": int,
                "tool_requests": int,
            },
            "raw-candidates.jsonl": {
                "sample_id": str,
                "processing_status": str,
                "row": dict,
            },
            "models.jsonl": {
                "attempt_id": str,
                "task_attempt_id": str,
                "input_messages": list,
                "response_base64": (str, type(None)),
                "state": str,
            },
            "tools.jsonl": {
                "call": dict,
                "requested_execution": dict,
                "execution": (dict, type(None)),
                "response_state": str,
                "response_base64": (str, type(None)),
            },
        }
        for name, fields in required.items():
            for item in files[name]:
                require(
                    all(
                        key in item and type(item[key]) in (kind if type(kind) is tuple else (kind,))
                        for key, kind in fields.items()
                    ),
                    "invalid_sidecar_shape/" + name,
                )
        require(
            all(type(files[name]) is dict for name in ("report.json", "rejected.json", "known-bad.json")),
            "invalid_report_shape",
        )
        require(
            type(files["rejected.json"].get("admission")) is list,
            "invalid_rejection_shape",
        )
        ids = {row.get("sample_id") for row in files["candidates.jsonl"]}
        for entry in files["raw-candidates.jsonl"]:
            errors = list(F.VALIDATOR.iter_errors(entry["row"]))
            diagnostic = entry["processing_status"] == "FAIL" and entry["sample_id"] not in ids
            require(
                all(
                    diagnostic and list(error.absolute_path) == ["messages"] and error.validator == "minItems"
                    for error in errors
                ),
                "invalid_raw_record_shape",
            )
        execution_schema = F.SCHEMA["properties"]["executions"]["items"]
        for event in files["tools.jsonl"]:
            require(
                F.VALIDATOR.evolve(schema=execution_schema).is_valid(event["requested_execution"]),
                "invalid_requested_execution_shape",
            )
            require(
                event["execution"] is None
                or F.VALIDATOR.evolve(schema=execution_schema).is_valid(event["execution"]),
                "invalid_actual_execution_shape",
            )

    checks.run("sidecar_boundary", "tasks/raw/models/tools/report/rejected", sidecar_shape)
    if checks.items[-1]["status"] != "PASS":
        return finish(checks, manifest_hash, pins, mode)
    tasks = files["tasks.json"]
    planned = files["planned-cases.json"]
    raw_rows = files["raw-candidates.jsonl"]
    candidates = files["candidates.jsonl"]
    models = files["models.jsonl"]
    tools = files["tools.jsonl"]
    checks.add(
        "planned_task_identity",
        same(
            [
                {
                    k: t.get(k)
                    for k in (
                        "sample_id",
                        "task_id",
                        "trip_family",
                        "rewrite_family",
                        "language",
                        "scenario",
                    )
                }
                for t in tasks
            ],
            [
                {
                    k: t[k]
                    for k in (
                        "sample_id",
                        "task_id",
                        "trip_family",
                        "rewrite_family",
                        "language",
                        "scenario",
                    )
                }
                for t in planned
            ],
        ),
        "tasks.json/planned-cases.json",
        "missing_duplicated_or_changed_task",
    )
    candidate_ids = [r.get("sample_id") for r in candidates]
    checks.add(
        "candidate_identity_unique",
        len(set(candidate_ids)) == len(candidate_ids),
        "candidates.jsonl",
        "duplicate_sample_id",
    )
    for index, row in enumerate(candidates):
        checks.run(
            f"row/{index}/F_schema_execution_source",
            "candidates.jsonl#" + str(index + 1),
            lambda row=row: F.validate(row),
        )
        if any(F.VALIDATOR.iter_errors(row)):
            continue
        checks.add(
            f"row/{index}/known_bad_reply",
            not any(F.digest(m) in T.registry() for m in row["messages"] if m["role"] == "assistant"),
            "candidates.jsonl#" + row["sample_id"],
            "known_unverified_write_claim",
        )
        if row["task_id"] == "f768-empty":
            checks.add(
                f"row/{index}/known_no_results_meaning",
                row["messages"][-1].get("content") == RULES["known_no_results_replies"][row["language"]],
                "candidates.jsonl#" + row["sample_id"],
                "known_no_results_fabricated_hit",
            )
    for index, event in enumerate(tools):

        def actual_tool(event=event):
            from cj_place import (
                ORIGIN,
                Config,
                Response,
                Search,
                prepare,
                parse_response,
            )
            from cj_place.contract_v1 import decode_query, encode_result

            e = event["execution"]
            stub = event["requested_execution"]
            if e is None:
                raise MissingEvidence("tool_receipt_missing")
            require(
                stub["status"] == "not_started" and stub["evidence"]["status"] == "not_started",
                "dispatch_stub_not_original",
            )
            require(
                all(e[k] == stub[k] for k in ("attempt_id", "run_id", "operation_id", "tool_call_id")),
                "wrong_original_tool_identity",
            )
            require(
                all(
                    e["evidence"][k] == e[k]
                    for k in (
                        "attempt_id",
                        "run_id",
                        "operation_id",
                        "tool_call_id",
                        "status",
                    )
                ),
                "wrong_receipt",
            )
            original_calls = [
                call
                for entry in raw_rows
                for message in entry["row"]["messages"]
                for call in message.get("tool_calls", [])
                if call["id"] == e["tool_call_id"] and entry["row"]["run"]["attempt_id"] == e["attempt_id"]
            ]
            require(
                len(original_calls) == 1 and same(event["call"], original_calls[0]),
                "wrong_tool_call",
            )
            if e["status"] != "received":
                require(
                    event["response_state"] == "unknown" and event["response_base64"] is None,
                    "unreceived_supplier_success",
                )
                if e["status"] == "unknown":
                    raise MissingEvidence("supplier_outcome_unknown")
                return
            if event["response_base64"] is None:
                raise MissingEvidence("supplier_bytes_missing")
            kind, raw_query = F.canonical_tool(
                event["call"]["function"]["name"],
                event["call"]["function"]["arguments"],
            )
            query = decode_query(raw_query)
            require(kind == "place" and type(query) is Search, "unsupported_actual_codec")
            at = datetime.fromisoformat(event["query_started_at"])
            received = datetime.fromisoformat(event["received_at"])
            config = Config(ORIGIN, 8192, 65536, 20, 60)
            request = prepare(config, query, e["operation_id"], at, basic=True)
            require(
                event["binding_digest"] == request.binding_digest
                and event["request_ref"] == request.request_ref,
                "wrong_supplier_binding",
            )
            response = Response(
                request.binding_digest,
                request.origin,
                request.path,
                200,
                base64.b64decode(event["response_base64"], validate=True),
                received,
            )
            actual = parse_response(
                config,
                request,
                response,
                now=received,
                evidence="synthetic",
                basic=True,
            )
            require(
                e["result"]["state"] == "present"
                and e["result"]["value"] == encode_result(actual, evidence_kind="synthetic").decode(),
                "supplier_bytes_disagree_with_result",
            )

        checks.run(
            f"tool/{index}/actual_supplier_receipt_codec",
            "tools.jsonl#" + str(index + 1),
            actual_tool,
        )

    def original_inventory():
        require(
            all({"sample_id", "row", "processing_status"} <= r.keys() for r in raw_rows),
            "raw_task_fields_missing",
        )
        require(
            len({r["sample_id"] for r in raw_rows}) == len(raw_rows),
            "duplicate_raw_task",
        )
        require(
            {r["sample_id"] for r in raw_rows} == {t["sample_id"] for t in tasks if t["model_requests"] > 0},
            "missing_started_task_original",
        )
        for row in candidates:
            original = [entry for entry in raw_rows if entry["sample_id"] == row.get("sample_id")]
            require(
                len(original) == 1 and same(original[0]["row"], row),
                "candidate_not_original_record",
            )
        model_ids = [e.get("attempt_id") for e in models]
        require(
            len(set(model_ids)) == len(model_ids),
            "model_original_duplicate_or_missing",
        )
        if any(event["execution"] is None for event in tools):
            raise MissingEvidence("tool_receipt_missing")
        require(
            sum(t["model_requests"] for t in tasks) == len(models)
            and sum(t["tool_requests"] for t in tasks) == len(tools),
            "orphan_original",
        )

    checks.run("original_inventory", "raw-candidates/models/tools/tasks", original_inventory)

    def transcript_original(entry):
        row = entry["row"]
        sample = entry["sample_id"]
        task = next((t for t in tasks if t["sample_id"] == sample), None)
        require(
            task is not None and task["processing_status"] == entry["processing_status"],
            "raw_task_status_mismatch",
        )
        require(
            row["sample_id"] == sample
            and all(
                row[k] == task[k]
                for k in (
                    "task_id",
                    "trip_family",
                    "rewrite_family",
                    "language",
                    "scenario",
                )
            ),
            "raw_task_identity_mismatch",
        )
        run = row["run"]
        expected_attempt = "fake-task/" + pins["batch_id"] + "/" + sample
        require(
            run["attempt_id"] == expected_attempt
            and run["run_id"] == "fake-run/" + pins["batch_id"] + "/" + sample,
            "wrong_task_run",
        )
        require(
            row["source"]
            == dict(
                kind="synthetic_fixture",
                revision="F789-fake.1",
                source_id="fake/" + pins["batch_id"] + "/" + sample,
            ),
            "wrong_original_source",
        )
        events = [e for e in models if e["task_attempt_id"] == expected_attempt]
        dispatched = [e for e in tools if e["requested_execution"]["attempt_id"] == expected_attempt]
        require(
            len(events) == task["model_requests"] and len(dispatched) == task["tool_requests"],
            "request_denominator_mismatch",
        )
        cursor = 0
        for i, event in enumerate(events):
            require(
                event["state"] in ("received", "failed", "unknown"),
                "invalid_model_outcome",
            )
            if event["state"] != "received":
                require(
                    i == len(events) - 1 and row["run"]["status"] == event["state"],
                    "unsettled_model_claimed_complete",
                )
            require(
                event["attempt_id"] == expected_attempt + "/model/" + str(i),
                "wrong_model_attempt",
            )
            require(
                event.get("model_version") == "FakeTeacher.1"
                and event.get("prompt_version") == "F768-public-scripts.1"
                and event.get("adapter_version") == "F789-fake.1"
                and event.get("tools_sha256") == F.TOOLS_HASH,
                "wrong_model_versions",
            )
            positions = [
                j for j in range(cursor, len(row["messages"])) if row["messages"][j]["role"] == "assistant"
            ]
            stop = positions[0] if positions else len(row["messages"])
            require(
                same(event["input_messages"], row["messages"][:stop]),
                "wrong_model_visible_input",
            )
            if event["response_base64"] is None:
                require(
                    event["state"] in ("unknown", "failed"),
                    "received_model_bytes_missing",
                )
                continue
            raw = base64.b64decode(event["response_base64"], validate=True)
            try:
                message = T.decode_reply(raw, T.registry())
            except F.Rejected:
                require(
                    task["processing_status"] == "FAIL" and sample not in candidate_ids,
                    "bad_proposal_not_quarantined",
                )
                continue
            require(
                positions and same(message, row["messages"][stop]),
                "assistant_not_from_original_bytes",
            )
            cursor = stop + 1
        require(
            not any(m["role"] == "assistant" for m in row["messages"][cursor:]),
            "assistant_without_model_original",
        )
        for execution in row["executions"]:
            original = [
                e for e in dispatched if e["requested_execution"]["operation_id"] == execution["operation_id"]
            ]
            if any(event["execution"] is None for event in original):
                raise MissingEvidence("tool_receipt_missing")
            if execution["status"] == "not_started":
                require(not original, "dispatch_after_cancel_or_stop")
            else:
                require(
                    len(original) == 1 and same(original[0]["execution"], execution),
                    "execution_not_from_tool_original",
                )

    for entry in raw_rows:
        checks.run(
            "task/" + entry["sample_id"] + "/model_tool_originals",
            "raw-candidates.jsonl#" + entry["sample_id"],
            lambda entry=entry: transcript_original(entry),
        )

    def full_task_stop():
        stopped = False
        for t in tasks:
            require(
                t.get("processing_status") in ("PASS", "FAIL", "UNKNOWN", "UNRUN"),
                "unknown_task_status",
            )
            if stopped:
                require(
                    t["processing_status"] == "UNRUN"
                    and t["model_requests"] == 0
                    and t["tool_requests"] == 0,
                    "dispatch_after_unknown",
                )
            if t["processing_status"] in ("UNKNOWN", "UNRUN") or t.get("reason") == "model_outcome_failed":
                stopped = True

    checks.run("complete_task_and_unknown_stop", "tasks.json", full_task_stop)
    converted, lineage, rejected, groups, admission = F.convert(raw_files["candidates.jsonl"])
    checks.add(
        "dedup_groups_and_lineage",
        same(lineage, files["lineage.json"])
        and same(groups, manifest.get("groups"))
        and same(rejected, files["rejected.json"].get("admission")),
        "lineage/rejected/handoff",
        "family_or_lineage_mismatch",
    )
    for split in F.SPLITS:
        checks.add(
            "purpose/" + split,
            same(converted[split], files[split + ".jsonl"]),
            split + ".jsonl",
            "family_usage_leak_or_wrong_rows",
        )
    checks.add(
        "admission_denominator",
        same(admission, files["report.json"].get("admission")),
        "report.json",
        "wrong_accept_reject_denominator",
    )
    generation = dict(
        planned=len(planned),
        attempted=sum(t.get("model_requests", 0) > 0 for t in tasks),
        statuses=dict(Counter(t.get("processing_status") for t in tasks)),
        model_requests=len(models),
        tool_requests=len(tools),
        real_model_requests=0,
        real_tool_requests=0,
    )
    checks.add(
        "complete_attempt_denominators",
        same(generation, manifest.get("generation"))
        and same(generation, files["report.json"].get("generation")),
        "tasks/models/tools/report/handoff",
        "lost_attempt_or_wrong_count",
    )
    retained = [row for split in F.SPLITS for row in converted[split]]
    strata = dict(
        planned_language_behavior=dict(Counter(t["language"] + "/" + t["scenario"] for t in planned)),
        admitted_language_behavior=dict(Counter(r["language"] + "/" + r["scenario"] for r in retained)),
        admitted_run_states=dict(Counter(r["run"]["status"] for r in retained)),
    )
    checks.add(
        "language_behavior_denominators",
        same(strata, manifest.get("denominators")) and same(strata, files["report.json"].get("denominators")),
        "handoff/report",
        "lost_language_or_behavior",
    )
    controls = T.known_bad_report(T.registry())
    checks.add(
        "known_negative_controls",
        same(controls, files["known-bad.json"]) and controls["status"] == "PASS",
        "known-bad.json",
        "known_bad_not_rejected",
    )
    counts = dict(
        generation=generation,
        accepted=len(retained),
        families=len(groups),
        nominal_planned_trip_families=len({row["trip_family"] for row in planned}),
        duplicates=admission["duplicates"],
        rejected_generation=sum(t["processing_status"] == "FAIL" for t in tasks),
        strata=strata,
        split_counts={split: len(converted[split]) for split in F.SPLITS},
        control_only=sum(
            r["run"]["status"] != "completed" or r["run"]["answer_state"] != "complete" for r in retained
        ),
    )
    group_by_sample = {entry["sample_id"]: entry["group_id"] for entry in lineage}
    selected = sampling(groups, [(row, group_by_sample[row["sample_id"]]) for row in retained])
    selected["scope"] = "admitted_fake_components_demo_not_real_pilot"
    report = finish(
        checks,
        manifest_hash,
        pins,
        mode,
        counts,
        selected,
        unknown=any(t["processing_status"] in ("UNKNOWN", "UNRUN") for t in tasks),
    )
    report["records"] = [
        dict(
            sample_id=row["sample_id"],
            group_id=group_by_sample[row["sample_id"]],
            split=next(entry["split"] for entry in lineage if entry["sample_id"] == row["sample_id"]),
            row_sha256=F.digest(row),
            run_status=row["run"]["status"],
            answer_state=row["run"]["answer_state"],
            usage=(
                "control_only"
                if row["run"]["status"] != "completed" or row["run"]["answer_state"] != "complete"
                else "fake_interface_only"
            ),
            training_allowed=False,
        )
        for row in retained
    ]
    by_task = {entry["sample_id"]: entry for entry in raw_rows}
    report["tasks"] = [
        dict(
            sample_id=task["sample_id"],
            producer_processing_status=task["processing_status"],
            independent_evidence_status=next(
                (
                    item["status"]
                    for item in checks.items
                    if item["name"] == "task/" + task["sample_id"] + "/model_tool_originals"
                ),
                "UNRUN",
            ),
            reason=(
                task["reason"]
                if task["sample_id"] not in by_task
                else next(
                    (
                        item["reason"]
                        for item in checks.items
                        if item["name"] == "task/" + task["sample_id"] + "/model_tool_originals"
                    ),
                    None,
                )
            ),
            model_requests=task["model_requests"],
            tool_requests=task["tool_requests"],
        )
        for task in tasks
    ]
    report["g_handoff"]["training_samples"] = []
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.bundle.resolve(), args.source_root.resolve(), args.manifest_sha256)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(
            report,
            stream,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        stream.write("\n")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
