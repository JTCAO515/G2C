# WP14 offline voice layer · #937 / #844

JT's 2026-11-14 evening Goal authorizes this offline work now. The detailed
JT-approved voice text is now on main: PR894 merged on 2026-11-15
(final PR head `45a8451303cb500c525abcbb1f9ee50137ba3061`). The old readiness v1
retains its original pre-merge snapshot; current readiness is appended in v2.
For native4, #922 is the unique behavior authority: exploration has 3–4 question
groups and per-segment limits, practical answers have no exploration questions.
The retained30-case PERSONA prose comparison below is a separate, explicitly
legacy-prose cohort, not a scorer for a merged native4 timeline. Never apply the
one-closing-question check to question-group/exit/UI text or use this cohort to
claim G6/G7/G8 or the formal60/16/66 gates passed.

# Lio answer experience evaluation · #844

Scope: `docs/lio-voice.md` §§3–7, 9. Only **model-written prose** is assessed.
Fixed #839 identity/capability text, Trip cards, memory controls, errors and quota UI
are excluded. This public synthetic set is separate from national16, formal66 and
the encrypted final set; it never substitutes for their denominators or gates.

## Dataset and checks

`lio_voice_cases.v1.json`: 30 natural visitor questions, 15 Chinese and 15 English,
covering all eight scenarios in each language. Every question has a scenario and
expected length band. Context describes evidence requirements, not instructions
smuggled into visitor wording. An authenticated saved-trip scenario must use the
registered runner's real synthetic state; this file does not create a Trip or imply
that a fixture was deployed.

`lio_voice.py` checks:

- Length: short30/20, default80/50, expanded150/90 (zh visible characters/en words),
  unlimited emergency; includes the final question. Chinese counts visible characters
  including punctuation/numerals after Markdown emphasis removal. English Chinese
  names are excluded; adjacent pinyin that matches the Chinese pronunciation
  is excluded, with or without tones. Accented ordinary words are not exempt.
  Unmarked pinyin comes from frozen case/source annotations, **not** model-supplied
  exemptions. English names still count as English words. Hyphenated words and
  contractions count once. No output is truncated to satisfy a length limit.
- One final question; explicit farewell and emergency are the only exceptions.
- Known, mentioned place/dish aliases require their associated Chinese name; an
  unrelated Chinese word cannot cover them. This is a **surface check**, not general
  entity recognition or proof of correct translation. Unknown names and omissions
  require grounded review. Never invent a Chinese label for an uncommon place.
- No Markdown/HTML tables or headings, raw URLs/Markdown links; at most3 list items
  in a whole answer (short replies have none).
- A versioned in-code system-language/「您」lexicon, with a negative control for
  「交通工具」. This offline lexicon does not replace B's production filter.
- Code redline signals: internal identifiers, paired coordinates, provider endpoints,
  and an emergency first sentence without110/120. An empty signal list **does not**
  prove zero severe errors: factual accuracy, unsupported booking/payment/save/memory
  claims and invented identity still require original state/source evidence and review.

No dependencies, production code, authorization, old evaluator, frozen contract,
quota/hold, provider route or publishing is changed by the checker. The existing
default test entry gains this module's controls; no existing check is removed or relaxed.

## Human/model calibration

Three separate binary prompts are in `lio_voice_judge_prompts.md` (items1/4/6).
The 20 synthetic mixed-quality examples are in `lio_voice_calibration.v1.json`;
the ready-to-fill worksheet is [lio_voice_jt_review.md](lio_voice_jt_review.md).
JT has now read all20 written examples and delivered qualitative product feedback
on2026-11-16. The original user messages, conditions and per-case summaries are in
`lio_voice_jt_feedback.20261116.json`; this is completed human review, not pending
App testing. JT did not provide60 binary A/B/C labels, and C must not infer them.
The original sample file and blank binary labels remain unchanged.

Current **binary agreement is not computable from this qualitative review**: the
value is null, not0%,100% or20/20. Actual model review remains UNRUN. Do not ask JT
to mechanically re-read the examples or fill60 boxes. The retained binary-v1
calculator applies only if a separately attributed binary gold set exists; it is
not a converter from qualitative opinions. Its historical entry is:

```sh
python -B -m eval.lio_voice calibrate model-judgments.json
```

Report exact-match agreement per criterion, known/planned/missing counts and
disagreements. Partial labels are INCOMPLETE. Model calibration never substitutes
for JT's formal66 review or grounded severe-error review.

The historical binary preparation remains separate from JT's delivered review and
from future actual model results. `lio_voice_quality_rubric.v2.md` proposes reasoned
grades for task progress, practical specificity and follow-up value, preserving
the original binary prompts and all old records. It is report-only, not a new
passing threshold or an implemented model comparison. New model/scorer admission
and original outputs are required before reporting model results.

JT also confirmed that colleague/human help with information gathering is an
existing service. Offering this help is valid; actual handoff, acceptance,
in-progress and completed claims require their corresponding evidence. Missing
API evidence does not establish that the service is nonexistent. Neither this
confirmation nor JT's general approval of examples08/20 proves a ticket booked,
a hotel called, payment made or pickup arranged. Emergency action comes first.

## Old/new comparison (L2, qualified runtime pending)

The explicit preparation pins are in `lio_voice_prompt_comparison.v1.json`.
Old is the immediate pre-#842 base `dbc39d17`; the earlier candidate `037dccab`
is retained as history. #842 is now actually merged (`3f34dcd0`); the new
accepted PERSONA is frozen from main `49ed8a27`, including later accepted voice
changes. Full text/source hashes are retained. These are source pins only:
registered old/new runtime admission and original outputs are still UNRUN.

PR857 changes both PERSONA and display filtering. Report original model prose and
rendered user prose separately, retaining the raw artifacts and actual wire status.
Run the same offline report on separate raw/rendered bundles; if raw output cannot
be read, its comparison stays UNRUN. A display-withheld/failed answer stays failed or
missing, not a short model PASS. A prompt-only causal comparison requires the same
display policy, context and tools with admitted old/new prompt pins. Otherwise label
the result an end-to-end version comparison and disclose the changed filter; do not
attribute all differences to PERSONA. No runtime control or dispatch right is granted
by the preparation manifest.

**UNRUN** until an authorized registered runtime can run both
prompt pins. Do not send a client-selected system prompt, bypass the original
provider/Meter, invent new identities or use another lane's budget. Preserve each
original attempt, failures/UNKNOWN and actual fees. No credential is read by this
offline module. Real dispatch uses the existing approved runner and an exclusive B
window; national16/A priority is not interrupted.

B has confirmed that the current RuntimeAdapter has only three text slots and
no named PERSONA dual-arm admission. A text slot is not a system-prompt override.
The actual comparison is therefore registered as
[UNRUN → L2 #32](https://github.com/JTCAO515/G2C/issues/32#issuecomment-6880988716),
with the missing compliant actor/source entry explicit. No >=90% product score,
length/timing result or paid-cost result is inferred from this offline delivery.

Freeze this dataset SHA, the actual old/new prompt SHA, source/image, model/tool
profiles, source/context fixtures, sample order and original window IDs **before**
dispatch. Each arm runs all30 once; do not selectively rerun failures, reuse outputs
from prior evaluations or infer a prompt pin from a friendly label. Old/new must have
the same declared context and tools. An ordinary backend transport failure or absent
body stays missing/failed in the planned denominator, never a perfect short answer.

Collect original question/answer, RUN/attempts and raw source/state evidence, status,
first **paragraph** time and clock definition, prompt hash and all paid internal model
and tool calls. Existing `first_body_seconds` can only stand in when the observed
body event really exposes the first paragraph; a terminal-only body cannot establish
an earlier streaming paragraph time. Missing timing remains null.

The offline comparison input is a JSON object with `dataset_sha256` and `arms.old` /
`arms.new`. Each arm has actual runtime `source_commit` (40 hex),
`prompt_source_commit` and `prompt_sha256` matching the frozen old/new source pins,
`model_profile`, `window_id`
and `evidence_kind=fixture|real_service`, plus `observations` keyed by frozen case ID.
Fixture/unqualified controls report separately and cannot return a product
`stage1_gate=PASS`; a synthetic/fixture reference is rejected for a real-service arm.
A completed observation contains `status`,
`answer`, `run_id`, `operation_id`, `attempt_id`, `answer_view=raw|rendered`,
`evidence_ref`, `first_paragraph_seconds` (or null), and `original` described below.
Each operation/attempt pair occurs only once across all cases and both arms;
identical answer text from genuinely separate attempts is allowed. Independent
grounded `redline_review={outcome:PASS|FAIL,kind:human|program,independent:true,run_id:...,
answer_sha256:...,scope_sha256:...,ref:...}` binds the exact answer and original scope.
A stale same-RUN review of another answer/state cannot certify a PASS.
A model-only PASS cannot establish zero severe errors. Optional `model_review` contains `run_id`,
`answer_sha256`, `prompt_sha256` (of `lio_voice_judge_prompts.md`), `reviewer`, `ref`,
`scope_sha256` and `verdicts` keyed by the three criterion IDs. Missing reviews stay
UNRUN; a review of a different scope/answer/RUN/prompt is rejected. Failed/missing
observations do not receive artificial answers. Run:

```sh
python -B -m eval.lio_voice compare old-new-observations.json
```

The qualified runner's `original` export has `version=LIO-voice-original.1`, the
same RUN/operation/attempt/view, frozen `question_utf8`, plus `input_utf8`,
`answer_utf8`, `context_evidence_utf8`, `state_evidence_utf8` and the SHA256 of
each corresponding UTF-8 byte string. The original logical input is JSON with
`system` and `messages`: the last user message must be the frozen question, and
the system input must begin with the exact frozen PERSONA. Keep all actual
context/source/state artifacts; do not generate replacements to satisfy an import.
`scope_sha256` hashes the whole original object serialized as UTF-8 JSON with sorted
keys, no extra whitespace (`separators=(',', ':')`) and `ensure_ascii=False`.
Duplicate JSON fields are rejected. These cross-checks establish association only:
hashes and this offline file format never issue runner/source/AUTH qualification,
prove a real dispatch, or authorize a synthetic export to be called real evidence.
The approved runtime/window and original artifact reference must still be verified.

Report both languages separately: every check's pass/planned rate, per-answer units
and band distribution, first-paragraph known/missing counts and p50/p95/max. Each
code-check rate must be≥90%; **any** redline signal or grounded severe-error failure
fails the arm, and absent complete grounded redline review prevents PASS. Cite actual
severe-error evidence; model opinion alone does not prove save/booking/identity facts.
Retain conservative / token+public-tool estimate / actual-paid costs separately, with
UNKNOWN where payment evidence is absent. No financial hold is released by a reference
estimate. If approved old/new dispatch cannot be provided, record UNRUN → L2 #32
with a backlink to #844; do not infer a new spending authorization from this plan.

The current report has no real old/new observations: every check's product rate,
length distribution, first-paragraph time and conservative/token-estimate/paid
cost remains UNRUN. The >=90% and zero-redline gates are unchanged. A controlled
unit-test pass rate is not this product pass rate. The prepared JT rich-output
review worksheet is [lio-rich-jt-review-draft.md](lio-rich-jt-review-draft.md).
