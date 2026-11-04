"""Read-only reconciliation of the first real collector's timing labels.

Never re-executes a scenario or changes a judge/threshold. Original files remain
byte-identical. A terminal failure is not a complete answer; retain that clock
as time_to_terminal_seconds and mark full_answer_seconds unavailable.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
from collections import Counter
import json
from pathlib import Path

from report import report, markdown


def reconcile(rows, evidence):
    corrected = deepcopy(rows)
    changes = []
    for row in corrected:
        raw = evidence[row['raw_evidence_ref']]
        observed = raw.get('observed')
        completed = observed is not None and observed['run_status'] == 'completed'
        complete_artifact = not raw.get('requested_candidate_missing', False)
        if row.get('full_answer_seconds') is not None and not (completed and complete_artifact):
            original = row['full_answer_seconds']
            row.update(full_answer_seconds=None, time_to_terminal_seconds=original,
                measurement_correction='Original collector measured terminal time; no complete answer/artifact was delivered')
            changes.append(dict(scenario_id=row['scenario_id'], language=row['language'],
                attempt=row['attempt'], field='full_answer_seconds', original=original, corrected=None,
                evidence_ref=row['raw_evidence_ref'], original_run_status=None if observed is None else observed['run_status']))
    return corrected, changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--publish-directory', type=Path)
    args = parser.parse_args()
    plan_raw = (args.batch / 'plan.json').read_bytes()
    observations_raw = (args.batch / 'observations.json').read_bytes()
    plan = json.loads(plan_raw)
    rows = json.loads(observations_raw)
    evidence = {row['raw_evidence_ref']: json.loads((args.batch / row['raw_evidence_ref']).read_bytes()) for row in rows}
    corrected, corrections = reconcile(rows, evidence)
    summary = report(plan, corrected)
    summary['measurement_reconciliation'] = dict(
        program='eval/real_report.py', original_plan_sha256=sha256(plan_raw).hexdigest(),
        original_observations_sha256=sha256(observations_raw).hexdigest(), corrections=corrections,
        unchanged='All original observations, inputs/holdout, raw evidence, judgments, thresholds, calls, fees and failures remain intact')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'observations.json').write_text(json.dumps(corrected, ensure_ascii=False, indent=2)+'\n')
    (args.output / 'report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    (args.output / 'report.md').write_text(markdown(summary))
    if args.publish_directory is not None:
        # A durable evaluation report, not a dump of HTTP/process logs or keys.
        # Original full evidence stays outside git; immutable hashes identify it.
        published = {k: summary[k] for k in ('schema_version','validation','release_decision',
            'release_blockers','independent_product_scenario_n','holdout_product_scenario_n',
            'holdout_fraction','observed_attempt_n','serious_errors','repeated_uses','quality_acceptance')}
        published['frozen_plan'] = {k: plan[k] for k in ('sample_set_id','sample_set_version','provenance',
            'collector_sha256','candidates','networks','attempts')}
        published['measurement_reconciliation'] = summary['measurement_reconciliation']
        audit = []
        receipts = []
        for row in corrected:
            raw_path = args.batch / row['raw_evidence_ref']
            original = evidence[row['raw_evidence_ref']]
            observed = original.get('observed') or {}
            audit.append(dict(scenario_id=row['scenario_id'], language=row['language'], attempt=row['attempt'],
                purpose=row['purpose'], status=row['status'], judgment=row['judgment'],
                observed_at=row['observed_at'], source_as_of=row['source_as_of'],
                independent_judgment=row.get('independent_judgment'), serious_errors=row['serious_errors'],
                raw_evidence_ref=row['raw_evidence_ref'], raw_evidence_sha256=sha256(raw_path.read_bytes()).hexdigest(),
                input_sha256=original['input_sha256'], run_id=(observed.get('message_receipt') or {}).get('run_id'),
                run_status=observed.get('run_status'), first_body_seconds=row.get('first_body_seconds'),
                full_answer_seconds=row.get('full_answer_seconds'),
                time_to_terminal_seconds=row.get('time_to_terminal_seconds'),
                model_calls=row['model_calls'], tool_calls=row['tool_calls'], memory_calls=row['memory_calls'],
                cost=row['cost'], requested_candidate_missing=original.get('requested_candidate_missing'),
                restart_scope=original.get('restart_scope')))
            receipts.extend(original['authorization_attempts'])
        published['attempt_audit'] = audit
        published['packages'] = json.loads((args.batch / 'packages.json').read_bytes())
        budgets = {}
        for label in ('before','after'):
            counts = Counter(v['kind'] for v in json.loads((args.batch / ('budget-'+label+'.json')).read_bytes()))
            budgets[label] = dict(counts=dict(counts), model_conservative_cny_including_M1=13+counts['model'],
                                 tool_conservative_cny=sum(counts[k] for k in ('place','route','weather')))
        published['shared_authorization_budget_snapshots'] = budgets
        published['usage'] = dict(
            authorization_attempts_by_kind={kind: sum(v['kind']==kind for v in receipts)
                for kind in ('model','place','route','weather','fact')},
            receipt_states_by_kind={kind: {state: sum(v['kind']==kind and v['state']==state for v in receipts)
                for state in ('INTENT','RECEIVED')} for kind in ('model','place','route','weather','fact')},
            model_tokens_from_complete_receipts={field: sum(v['receipt']['usage'][field] for v in receipts
                if v['kind']=='model' and v['receipt'] is not None)
                for field in ('prompt_tokens','completion_tokens','total_tokens')},
            original_receipt_manifest_sha256=sha256(json.dumps(receipts,sort_keys=True).encode()).hexdigest(),
            actual_billed_total='UNKNOWN', note='Counts are original authorization/call attempts, not vendor invoices or a claim that every uncertain intent was sent')
        args.publish_directory.mkdir(parents=True, exist_ok=False)
        (args.publish_directory / 'report.json').write_text(json.dumps(published, ensure_ascii=False, indent=2)+'\n')
        kinds = published['usage']['authorization_attempts_by_kind']
        states = published['usage']['receipt_states_by_kind']
        tokens = published['usage']['model_tokens_from_complete_receipts']
        completed = Counter(v['language'] for v in audit if v['run_status']=='completed')
        unknown_runs = sum(v['run_status']=='unknown' for v in audit)
        notes = ['# Real batch evidence and limits', '',
            'Conclusion: **FAIL — do not release this evaluated candidate.** Only synthetic data; original33 paired scenarios and11 fixed holdout, no prompt/judge/holdout tuning.', '',
            f'The quality numerator is independently certified PASS, not model self-scoring. RUN completion was zh{completed["zh"]}/33 and en{completed["en"]}/33; {unknown_runs} ended UNKNOWN. Completed answers have no full independent semantic/factual review and remain quality UNKNOWN. Even treating every completed answer as PASS could not reach90% in this batch.', '',
            'The frozen program retains one serious hard-state FAIL per language in accept-once: formal_write_count was0, expected1. The RUN had ended UNKNOWN before a proposal/confirmation was available; no accept action occurred. This is a failed required save, not evidence of an unauthorized write. No model or reviewer overrode that original classification.', '',
            f'{len(corrections)} original terminal clocks were mislabeled as full answers in the initial collector output. Read-only reconciliation retains them as time_to_terminal_seconds and sets unavailable full_answer_seconds to null; original files/hashes, failures, judgments, fees and attempts are unchanged. No paid scenario was rerun for this correction.', '',
            'Displayed p95 values with UNKNOWN are known-subset diagnostics, never full-population PASS. First/full clocks are actual TCP v2 protected-snapshot observations at200ms polling, including submission and waiting. Source-only links are excluded. The necessary candidate is included when delivered. The gate can prove full-population FAIL when enough known slow samples exceed the allowed tail; otherwise incomplete populations remain UNKNOWN.', '',
            f'Real outbound evidence:{kinds["model"]} model intents ({states["model"]["RECEIVED"]} complete receipts;{states["model"]["INTENT"]} UNKNOWN),{states["place"]["RECEIVED"]} place receipts,{states["weather"]["RECEIVED"]} weather receipts,{kinds["fact"]} fact intents ({states["fact"]["RECEIVED"]} complete); route{kinds["route"]}. Complete model receipts expose{tokens["prompt_tokens"]} input/{tokens["completion_tokens"]} output tokens. Counts do not assert that every uncertain intent reached a vendor. Actual invoiced fees are UNKNOWN; C conservative holds are model¥{kinds["model"]}/tools¥{sum(kinds[k] for k in ("place","route","weather"))}. Shared after-snapshot including M1 is model¥{budgets["after"]["model_conservative_cny_including_M1"]}/tools¥{budgets["after"]["tool_conservative_cny"]}; no budget reset.', '',
            'Development-Mac network only. The loopback API is real and external model/place/weather exits are real; geographic overseas/China target attribution is UNKNOWN. api-beta target testing is UNRUN pending B #30 readiness; fact access and route availability are not certified. Project-wide release prerequisites remain UNKNOWN.', '',
            'Raw HTTP/process logs and credentials are not committed. report.json is the durable per-attempt evaluation/audit report, including original-evidence hashes and timing corrections. Original receipt/run evidence is linked in the PR description; raw files remain in the batch output. B #523 owns the real UNKNOWN/no-body and external adapter defects; C does not modify B files.', '',
            'Historical preparation failures retained: missing CJ_ENV import guard; the first pre-RUN snapshot read; wrong confirmation Content-Type. The corrected offline fixture passed10 signed/PG/worker recipes. Delay0.6s and2.5s fixture controls passed; they did not establish the cause of the real UNKNOWN runs.', '', '---', '']
        (args.publish_directory / 'report.md').write_text('\n'.join(notes)+markdown(summary))


if __name__ == '__main__': main()
