# Original preparation accounting

`PreparationCostInventory` reads the existing producer binding, original
financial ledger and protected native MESSAGE/RUN/Meter/fee sources. B supplies
a bounded, unique frozen MESSAGE selection. Only the original authenticated
session/ledger/producer can read it. No provider, reserve, settlement or refund
operation runs during collection.

Every original operation in those native inventories is included regardless of
RUN success, failure or cancellation. Fee reads precede Meter reads and do not
depend on a successful result or captured output artifact. Expected missing
financial/Meter originals become explicit gaps; AUTH, source corruption and
unexpected errors withhold rather than becoming an empty or free attempt.

Rows retain actual native source digests and original states. Known gross-price
estimates reuse the financial ledger's pricing function, in 10^-7 CNY units.
Unpriced/INTENT attempts retain that ledger's original full conservative hold;
an absent financial source has an unknown hold, not an inferred zero. Totals
label known subtotals and unpriced/unknown counts separately. Accounting
SETTLED means all declared attempts have original RECEIVED financial records
and settled native Meter receipts. It does not settle a supplier invoice, which
remains UNKNOWN, or prove the preparation saved a legal Trip.

The original accounting sources are read twice; a selected fee/Meter transition
withholds an inconsistent point result. The unique parent ledger's actual
before/after observation anchors may differ due to unrelated original activity;
that activity is neither charged to this preparation nor omitted from the
observed parent anchors. These are collection-time observations, **not** the
preparation workflow's original before/after cost anchors.

Unit evidence uses a real local financial journal with controlled protected
readers, including failed/unresolved attempts, missing first sources, current
AUTH/session checks, a real late original receipt and unrelated parent activity.
The existing signed native model-capture PG group adds actual protected
MESSAGE/RUN, native settled Meter and original financial sources, exact two-call
estimates and repeat-zero-new-model/fee checks. Its provider HTTP remains a
fixture; it does not represent supplier or Hong Kong acceptance.

Coverage is explicitly DECLARED_PREPARATION_MESSAGES_NOT_WHOLE_LIFECYCLE.
The final preparation controller must independently prove the list exhaustive,
retain all manual/native actions and its original lifecycle anchors, establish
purpose/allocation/window authority and freeze the real definition. This source
does not issue that authority, publish metadata, grant E access, create a fixture
or activate a paid task. Full X01–X12 remains separate and incomplete.
