# #936 / WP13 simulated users

The specification is [#922](https://github.com/JTCAO515/G2C/issues/922), including its
two dispatch/decision comments. This package measures G2 = zero repeated questions
about known, refused or inferable factors, and G3 = at least 80% correct factors at
the observed end of exploration. It does not change those thresholds.

## Frozen inputs and denominators

`profiles.v1.json` contains 20 synthetic single-city personas: ten Chinese and ten
English, paired across ten cities. Each has a natural opening, hidden answers and
behavior rules (brief, partial, full or proactive replies, incremental disclosure,
and a declared point at which this traveler asks for a plan). Every persona runs
three times: **60 trajectories**, 30 per language. All 14 keys from §3.1 count
separately, including `must_see` / `avoid` and `arrival` / `departure`: **840 factor
slots** overall, 420 per language. Missing attempts stay UNRUN in the denominator;
there is no best-of-three selection or pooling of candidates/evidence layers.

Each run binds the dataset's exact byte SHA. Revisions add a new dataset version;
they do not rewrite a failed original. The expected city remains one city even
when the opening has not yet disclosed it. Hidden answers are not automatically
known to Lio: G2 only uses facts in the actual released opening/replies. Refused
and inferred factors are explicitly annotated with an original quote. An
inference does not override a previous explicit answer. G3 compares observed
factor values, treating the three multi-value factors as unordered sets and
keeping booleans distinct from numbers.

## Simulator isolation

This borrows only the separation of a private user instruction and a public
dialogue from [τ-bench's original user simulator](https://github.com/sierra-research/tau-bench/blob/main/tau_bench/envs/user.py)
and [paper](https://arxiv.org/abs/2406.12045). It imports no τ-bench code, data,
dependencies, scoring policy or model choice.

`simulator_messages()` builds the **actor-only** messages. An approved model actor
selects factor answer keys plus `continue` / `direct`; `render_choice()` validates
the choices and renders the persona's natural answer wording. This constrains
simulator fidelity without asking the actor to judge its own behavior. Exact
wording permits independent disclosure checks; arbitrary paraphrases are not
silently assumed equivalent. Proactive replies may supply unasked facts; brief
and partial reply limits are part of the persona, not product limits.

`run_episode()` passes only ordinary reply text and locale into the DUT host.
Neither the hidden profile, scorer annotations nor actor system enters its call.
The model may choose which answers to reveal, but cannot alter hidden values.
The evaluator's finite bound is the declared user exit plus its response; reaching
it before an observed exploration end is UNKNOWN. It is **not** an exploration
round limit in Lio. A native host UNKNOWN stops that episode without resubmission;
the approved batch host must stop new dispatch on operational/financial UNKNOWN.
Expected G2/G3 baseline failures are measurements, not a reason to select only
successful personas.

## Observation boundary and host integration

The host interfaces are `DialogueHost.reply(text, locale, first=...)` and
`SimulatorHost.choose(actor_messages)`. They are injected by trusted project
composition; this library has no real exit, key handling, implicit host import,
teacher identity, sealed-Mac producer or arbitrary `--real` switch.

The DUT host returns an actual assistant turn with:

```python
dict(text=original_answer,
     questions=[dict(factor='pace', start=0, end=12)],
     questions_complete=True,
     question_evidence='native_structured',
     profile={'pace': dict(value='relaxed', state='known')},
     profile_complete=True,
     profile_evidence='accepted_context',
     exploration_complete=False,
     run_outcome='completed', observation_ref='native-original-reference')
```

Question offsets are Python Unicode character offsets into that exact answer,
not bytes or App UTF-16 positions. A complete question census must come from the
accepted structured reply or an explicit independently checked legacy annotation.
An incomplete census cannot prove G2 zero. `advisory` / `unavailable` origins
cannot claim completeness; checker `fixture` origins are confined to L0. A profile must be an actual accepted
end-of-exploration observation. Absent, partial or advisory projections do not
prove G3 correct. In particular, present LIO-message.2 public timelines have no
new `question_groups` / profile; `model.lio_intake.9` fields are advisory, not an
accepted WP3 profile. Unknown legacy metadata remains UNKNOWN, not an empty
accepted profile. NEEDS/Trip observations may support only their actual facts.

The host supplies `original_cost()` as three decimal strings or null:
`conservative_cny`, `token_estimate_cny`, `actual_paid_cny`. It must reconcile
**both actor and DUT** original attempts against the unique budget/Meter and
financial records, retaining full unknown/unpriced holds. Reuse `eval/fees.py`
for compatible original token receipts and the native budget projection for
conservative amounts. These are reporting values, never another ledger, fee
reservation or authority. Missing invoices stay null/UNKNOWN. Importing a trace
does not authenticate its receipts, source, observer or account.

The first DUT reply also carries `memory_observation` from the actual model-input
injection: `origin='accepted_injected'`, `complete`, original `text`, normalized
`facts` with state `from_memory`, and a native `ref`. An explicitly observed empty
injection has empty text/facts; absence of the observation is not proof of empty
memory and cannot certify G2 zero. Seed these accepted facts before applying the
traveler's current explicit disclosures. Do not reset an existing account's
memory or use the persona's hidden answers as a memory prefill. Fixture memory
observations are L0-only.

For WP4 regression, keep the same dataset/plan/metric entry and attach the actual
new deployed host. Its LIO-message.4 normalization must consume the frozen WP2
contract after delivery; this package does not invent that wire contract. Pin
the actual candidate, model/prompt/schema, original identities, native source,
capture, window, simulator/DUT roles and accounting references before dispatch.

## Commands and evidence levels

```sh
python -B -m unittest discover -s eval/lio_simulated_user/tests -v
python -B -m eval.lio_simulated_user plan --output .local/eval/c936-plan-r01
python -B -m eval.lio_simulated_user report --traces TRACE1.json TRACE2.json \
  --output .local/eval/c936-report-r01
```

Output directories must be new. The report includes all 60 rows, language groups,
per-run failures/unknown factors, and conservative / token-estimate / actual-paid
columns. G2/G3 checker positive/negative controls are L0, **not a baseline run**.
The suite is appended to `scripts/test.py`; its real-child nonzero propagation
control preserves existing checks and default-entry failure behavior.
L1 requires the actual signed local application/private PG combination. Real
model calls are L2 under ADR-0007 even where the child ticket labels the baseline
deliverable L1. Report these separately; a fixture cannot certify real model
quality, App timing or product release.

WP0 / PR940 was merged by JT on 2026-11-13 (commit `6790174865efba17237224cf400e446c27cde8f7`).
The approved current host still has no simulated-user registered exit (B's
[#936 receipt](https://github.com/JTCAO515/G2C/issues/936#issuecomment-6848352438)). Therefore the real
60-run baseline, local signed combination and WP4 regression remain UNRUN. The
all-UNRUN plan is readiness evidence only. Do not use the reflection exit or send
the hidden persona as a Lio user prompt. Live execution waits for WP0, the native
actor binding/source and ordinary current qualifications/window/capture, using
the existing C sublimit. No new account, budget or provider permission is granted
by these files. The authorization document alone does not implement the host or
prove that its actual limits, source and observation capabilities are ready.
