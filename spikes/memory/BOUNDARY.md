# CJ-003 local component boundary, draft 1

Base: `13905e4587feb8611ebde5e3621024f3338532ae`. This is an isolated spike, not MEMORY@1.0 or a public API.

Only ReMe is being evaluated. Pin the published wheel and its hash; upstream main is reference material, not evidence for a different installed release. No model, embeddings provider, shared database, or real account is called. Synthetic users A/B and synthetic fact/experience/preference records are not personal facts about JT.

The CJ authoritative item must retain stable item identity, principal/account generation, source identity and revision, item revision, enabled/confirmed state, scope/expiry, and revocation generation. ReMe files/chunks/indexes are rebuildable projections. Per-workspace separation demonstrates component partitioning only; the API must derive the workspace from a verified principal, never from a caller-selected user_id/path.

Required application hooks: compare expected revision before committing; revalidate source and revocation generations before late extraction writes and before publishing context/results; commit a durable revocation fence before cleanup; register file/index/cache/checkpoint cleanup and preserve incomplete/failed cleanup state; replay revocations before rebuild/restore becomes readable. These are required semantics to test, not claims that ReMe supplies them.

Native behavior and guarded behavior must be reported separately. If an unguarded old write restores content, retain it as a failing native counterexample; do not relabel a CJ guard test as native capability. Semantic bilingual retrieval, actual LLM context, API authentication, product UI, provider retention, backups, and device behavior remain UNRUN in this local segment.
