# CJ-017 immutable manual edit candidate

Local Python logic only; no dependencies beyond the existing CJ015 domain and Python
3.12–3.14. Fixed integration base `8deb696f8149b4f5aa70c767be6c3a263b036227`.
TRIP source `5fd115fc97e542bc8776a445d8245fd272000e56`; consumed
`backend/trip/cj_trip/domain.py` is unchanged at this base. No shared files change.

Run the synthetic tests from repository root:

```sh
PYTHONPATH=backend/manual_edit:backend/trip /opt/homebrew/bin/python3.14 -m unittest discover -s backend/manual_edit/tests -v
```

The interpreter path records this machine's verified Python 3.14; another supported
Python installation can replace it. No network, PostgreSQL, provider, HTTP server or
install is required. `tests/test_manual_edit.py` contains executable positive and
negative examples with the actual CJ015 `Trip`/`Proposal` types.

Consumer surface and safety boundaries: [contract](../../contracts/manual-edit/README.md).
Author verification: [evidence](evidence/REPORT.md). These are not independent Review
or Testing, nor Issue22 UI/save/transaction/fixed-state-persistence acceptance.
