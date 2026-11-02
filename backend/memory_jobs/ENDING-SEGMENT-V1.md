# Ending segment source artifact (internal V1)

For #411 preparation, this reads an actually ended conversation longer than one
100-message source interval. No table, job, cursor, model, Meter or authority is
created. Existing SOURCE@1 and CJ020-internal.2 bytes/semantics stay unchanged.

An EndingSegment contains a logical conversation_end SourceQuery of 1–100
messages plus the original EndQuery for its complete head. The segment's
conversation/generation/epoch must match and its through cannot exceed that head.

`read_ending_segment(boundary,token,segment,policy_for_context)` captures one
actual outer HistoryReadContext. It first consumes the public SOURCE@1 ending
reader at the final bounded tail, requiring the actual immutable B end signal.
After that holder/transaction closes, it consumes the contained range through the
public committed incremental-range reader, with a fresh C policy/consent holder.
It never nests a Boundary, MESSAGE lock or C Memory holder, or accesses B SQL.
Both phases use the same captured principal and original generation/epoch. The
ended conversation cannot append; a lifecycle change rejects the next read.

The result is bounded bytes tagged CJ020-ending-segment.1, containing the real end
fields and base64 of an ordinary exact CJ020-internal.2 conversation_summary batch.
The end ID belongs to the full ended head; a segment need not reach that head.
Original bytes/IDs are preserved. Repeating an original segment returns identical
data, and 100+1 segments retain one actual ending ID without truncating the tail.

These are private source artifacts, not Data2 model messages, consent, a queue
commit or permission for later dispatch/publication. Future queue/worker phases
must bind the original end and cursor, reenter current protected source checks,
and apply filtered model data. No inactivity signal or DTO can replace the real
end. Long-term collection does not require a formal Trip.

Actual signed API/runtime PG tests create 101 committed messages and verify the
real end prerequisite, exact 100+1 contents, stable replay/end ID, other-account
denial and withdrawal. End queue/Meter/summary composition remains #411 work;
this primitive alone does not close the ticket.
