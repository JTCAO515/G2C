# Evidence

Since ADR-0004 (2026-10-27) the repository holds no run evidence. Verification results live in:

- **CI** — `.github/workflows/ci.yml` jobs and their logs/artifacts are the source of green.
- **PR descriptions** — each PR lists its checks as PASS / FAIL / UNRUN / UNKNOWN with exact base/head.

## Historical evidence archive

All evidence directories that existed before ADR-0004 (1836 files, about 48 MB: reports,
process records, logs, archives, screenshots, pin manifests) are preserved in Git at the tag
[`evidence-archive-2026-10-27`](https://github.com/JTCAO515/G2C/tree/evidence-archive-2026-10-27),
which points to `87120f9d7f2246579fff9f0cf196363f63127994` (main after P0).

```bash
git fetch origin tag evidence-archive-2026-10-27
git show evidence-archive-2026-10-27:backend/trip/evidence/database.txt
git archive evidence-archive-2026-10-27 backend/trip/evidence | tar -x -C /path/outside/repo
```

Evidence files referenced from older reports, ADRs or Issues resolve against that tag.
Scripts that still write into an `evidence/` directory now write into a git-ignored path.
