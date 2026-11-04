"""Publish round2 evidence, keeping smoke gating separate from product quality.

Reads immutable batch evidence. Does not send requests, tune judges, or turn a
tool-source applicability UNKNOWN into either RUN failure or factual certainty.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from smoke import summarize
from report import report, markdown
from gates import POLICY
from fees import token_estimate


def read(path):return json.loads(path.read_bytes())


def audit_batch(directory, rows):
    audit=[];attempts=[]
    for row in rows:
        raw=(directory/row['raw_evidence_ref']).read_bytes();e=json.loads(raw)
        observed=e.get('observed') or {};receipt=observed.get('message_receipt') or {}
        audit.append(dict(row,run_id=receipt.get('run_id'),run_status=observed.get('run_status'),
            raw_evidence_sha256=sha256(raw).hexdigest(),input_sha256=e['input_sha256'],
            time_to_terminal_seconds=e.get('time_to_terminal_seconds'),
            delivered_answer_chars=len(e.get('answer','')),delivered_answer_sha256=sha256(e.get('answer','').encode()).hexdigest(),
            provider_receipted_substeps=dict(Counter(v['kind'] for v in e['authorization_attempts'] if v['state']=='RECEIVED'))))
        attempts.extend(e['authorization_attempts'])
    return audit,attempts


def usage(attempts):
    kinds=Counter(v['kind'] for v in attempts)
    tokens=Counter()
    for v in attempts:
        if v['kind']=='model' and v['state']=='RECEIVED':tokens.update(v['receipt']['usage'])
    return dict(call_attempts_by_kind=dict(kinds),complete_receipts=dict(Counter(v['kind'] for v in attempts if v['state']=='RECEIVED')),
        unknown_intents=dict(Counter(v['kind'] for v in attempts if v['state']=='INTENT')),
        model_tokens_from_complete_receipts=dict(tokens),conservative_hold_cny=dict(model=kinds['model'],tool=sum(kinds[k] for k in ('place','route','weather'))),
        token_price_estimate=token_estimate(attempts),
        actual_billed_cny='UNKNOWN',note='Original intents/call attempts; not a claim that every uncertain request reached the vendor. No invoice supplied.')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',type=Path,required=True)
    parser.add_argument('--full',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    smoke_plan=read(args.smoke/'plan.json');smoke_rows=read(args.smoke/'observations.json')
    smoke_summary=summarize(smoke_plan,smoke_rows,args.smoke)
    smoke_audit,attempts=audit_batch(args.smoke,smoke_rows)
    result=dict(schema_version=1,smoke=smoke_summary,smoke_audit=smoke_audit,
        smoke_plan=smoke_plan,preflight_estimate=read(args.smoke/'estimate.json'),packages=read(args.smoke/'packages.json'),
        full_product_quality='UNRUN',full66=dict(planned_n=66,executed_n=0),
        full_unrun_criteria_by_language={language:dict(planned_n=33,executed_n=0,
            completion_rate=dict(status='UNRUN',value=None,minimum=POLICY['completion_rate_minimum']),
            serious_errors=dict(status='UNRUN',observed_n=None,maximum=POLICY['serious_errors_maximum']),
            first_body_p95=dict(status='UNRUN',value=None,maximum_seconds=POLICY['first_body_p95_maximum_seconds']),
            full_answer_p95=dict(status='UNRUN',value=None,maximum_seconds=POLICY['full_answer_p95_maximum_seconds']))
            for language in ('zh','en')},
        disposition='FAIL' if smoke_summary['status']=='FAIL' else 'UNKNOWN',
        history=dict(first_round='PR531 / candidate9ba2d4df',original_FAIL_retained=True,
            product_quality_disposition='Original60 RUN UNKNOWN were caused by adapter continuation defect, fixed by PR532; not used as product quality or averaged into this candidate'),
        target_networks=dict(overseas_pretrip='UNRUN',china_travel='UNRUN',reason='B #30 has not notified api-beta readiness; no target or geography claim'),
        authorization='PR540: model total500/stop400 includingM1; tools total200/stop160;1200/600/200/240;expires2026-11-30;synthetic only')
    extra=[]
    last=args.smoke
    if args.full is not None:
        if smoke_summary['status']!='PASS':raise ValueError('cannot_publish_full_after_failed_smoke')
        plan=read(args.full/'plan.json');rows=read(args.full/'observations.json')
        if any(c['id']!=smoke_plan['candidate_id'] for c in plan['candidates']):
            raise ValueError('smoke_and_full_candidate_mismatch')
        full=report(plan,rows);audit,more=audit_batch(args.full,rows);attempts.extend(more)
        result.pop('full_unrun_criteria_by_language')
        # Formal per-attempt report and constraints, not raw HTTP/process logs.
        result.update(full_product_quality=full['quality_acceptance']['evaluation_release_decision'],
            full66=dict(planned_n=66,executed_n=len(rows)),full_quality_acceptance=full['quality_acceptance'],
            full_plan=plan,full_audit=audit,full_serious_errors=full['serious_errors'],
            disposition=full['quality_acceptance']['evaluation_release_decision'])
        extra=['',markdown(full)];last=args.full
    result['usage']=usage(attempts)
    result['original_attempt_manifest']=[dict(attempt_id=v['attempt_id'],kind=v['kind'],state=v['state'],receipt=v['receipt']) for v in attempts]
    result['budget_snapshots']={}
    for label,p in (('before',args.smoke/'budget-before.json'),('after',last/'budget-after.json')):
        entries=read(p);counts=Counter(v['kind'] for v in entries)
        result['budget_snapshots'][label]=dict(counts=dict(counts),model_hold_including_M1_cny=13+counts['model'],
            tool_hold_cny=sum(counts[k] for k in ('place','route','weather')),raw_snapshot_sha256=sha256(p.read_bytes()).hexdigest())
    md=['# M4 real rerun after PR532/540','',f'Release disposition: **{result["disposition"]}**. Product quality: **{result["full_product_quality"]}**.',
        '',f'Smoke candidate: `{smoke_plan["candidate_id"]}`. Fixed6 prerequisite cases: zh3/en3, place+route/weather/fact. Product corpus remains33 paired/11 fixed holdout.',
        '', 'First-round PR531 FAIL and original IDs/unknown fees remain intact. Per JT, its60 adapter-induced RUN UNKNOWN are not a product-quality conclusion. No old action was redispatched and no candidate/attempt was averaged away.',
        '', '| Case | Language | Prerequisite | Original RUN | Reasons |','|---|---|---|---|---|']
    for row in smoke_summary['outcomes']:
        md.append('| '+' | '.join(str(row.get(k,'')) for k in ('case_id','language','status','run_id','reasons'))+' |')
    md.extend(['',f'Full product batch: {result["full66"]["executed_n"]}/66 executed. Missing full tasks are UNRUN, not product FAIL or quality PASS.',
        '', 'A smoke PASS requires actual specified tool receipts, a later complete Beijing model receipt and protected same-message/run complete nonempty body. Model-only text or Source links cannot pass. FACT date/region/eligibility UNKNOWN is by design after successful source fetch; actual excerpts are separately required.',
        '', 'Actual billed currency remains UNKNOWN. Conservative holds and complete-receipt token counts do not settle invoices or release unknown reservations.',
        '', '```json',json.dumps(result['usage'],ensure_ascii=False,indent=2),'```','',
        'Shared budget end snapshot (includes earlier M1/B/C, not all attributed to this rerun):','',
        '```json',json.dumps(result['budget_snapshots']['after'],ensure_ascii=False,indent=2),'```','',
        'Only development-Mac TCP protected snapshots at200ms polling were measured. api-beta overseas/China target-network phases remain UNRUN until B #30 readiness. Source links are excluded from first-body time; failures are not full answers. No real-user content, extra service, cloud operation, or authorization-file edit by C.',
        '', 'Engineering test/fixture PASS is separate from real smoke and product quality. Original raw HTTP/process files remain outside git; formal audit retains every executed attempt, request hash, receipt state and timing. Unexecuted planned cells are explicit UNRUN.'])
    if args.full is None:
        md.extend(['','| Product language | Completion ≥90% | Serious errors 0 | First body p95 ≤5s | Full answer p95 ≤90s |',
            '|---|---|---|---|---|','| zh | UNRUN | UNRUN | UNRUN | UNRUN |','| en | UNRUN | UNRUN | UNRUN | UNRUN |'])
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (args.output/'report.md').write_text('\n'.join(md+extra)+'\n')


if __name__=='__main__':main()
