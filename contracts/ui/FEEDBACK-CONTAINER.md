# CJ006 Answer and Memory feedback surfaces

Follows original [CJ023 / Issue15](https://github.com/JTCAO515/G2C/issues/15), read via official GitHub repository ID1428033587. The historical Issue planning state does not override Main's authorized container work; real I/account/App/submit acceptance remains separate.

Both the answer's problem-feedback button and Memory's general Feedback link embed the **same public FeedbackView/FeedbackPresentation module**. Each surface has its own trusted client/model lifetime; a shared client object across the two live hosts is rejected to prevent invalidating another surface's queued work. Problem/expectation start empty. No transcript, diagnostic, model/rule version, duration, cost, tool result or fabricated ID is copied from answer text. Memory is only the entry location; this does not write long-term memory.

## Original answer and entry lifetime

The trusted root supplies FeedbackClient, FeedbackBinding, canonical SessionLifecycle/original SessionOperation, ShellGeneration and the same trusted binding callback. For Answer it additionally supplies a real FeedbackContext(messageID, optional runID) and the **current ShellState.assistantContentRevision** after publishing the actual answer. That revision is a local UI token, not a message ID or permission. The shell cannot infer message/run IDs from plain assistantBody. Association remains a user opt-in in the public form; references alone do not prove ownership, which the server validates.

Every accepted ShellPresentation.apply retires the previous answer-feedback model and rotates assistantContentRevision before displaying the new presentation; the trusted root may then bind its actual references. This conservative fence also applies if a new presentation happens to have identical text. General feedback's model/draft is unaffected by answer updates. A stale apply rejected by ShellGeneration cannot clear a newer model. Real live answer/root wiring remains outside this source-only candidate.

The entry freezes a binding-instance token at the opening event. A sheet/route opened for A cannot silently display B's new form. New account/source/selection or background invalidation clears own host references, then the old canonical model; old objects are never rebound. Account cleanup runs both feedback surfaces before prior NEEDS/Trip/Memory/history/message cleanup with generation checks. Language changes preserve the model and voluntary text. Missing trusted configuration is explicit unavailable; no implicit default source is created.

General binding rejects any context or answerRevision, so a fresh general form has no chat association. If a user explicitly selects an existing linked pending feedback, the original immutable references must remain for recovery; the wrapper labels and displays them as **existing original references**. This is not a new general submission and does not copy the current chat. No original bytes are rewritten to force an empty association.

## Public work, submission and recovery

FeedbackView already prepares opaque submit/query/reload work synchronously before Task. The host only exposes the model for the captured current entry and invalidates it on its UI/session lifecycle. Canonical checks handle reentrant binding/key callbacks, original selection, one-use work and receipt validation. No alternate feedback wire or storage is implemented by CJShell.

Public FeedbackClient construction always disables POST, so Submit is visibly unavailable while voluntary text editing remains possible. No host boolean enables submission. Tests may prepare an internal synthetic submit only to demonstrate it is cancelled before persistence/outflow; the container performs no fixture or real POST. Recovery reads original encrypted pending and queries that same action; missing key/store, unknown, conflict and null never authorize a replacement ID or resend.

A valid receipt says only Feedback submitted. Linked source status/event progress is the server's **historical observation**, not a new RUN lookup or proof of successful tools. Model/rule versions, usage, duration and tool results are explicitly not provided. No fixed/trained promise, support workbench, external contact, automatic diagnostics or private-full-text logging is introduced. The canonical private Feedback pending namespace/key is root-supplied and lookup-only; retention/deletion/resource activation is not invented here.
