"""Read timing evidence from the workbench audit without manufacturing staff events."""

from datetime import UTC, datetime
from uuid import UUID

from jt.workbench.store import AuditAction, AuditResult

from .runner import DRILL_SEED, Drill


def _iso(value: float | None) -> str | None:
    return None if value is None else datetime.fromtimestamp(value, UTC).isoformat()


def _duration(start: float | None, end: float | None, unit: float) -> float | None:
    return None if start is None or end is None or end < start else round((end - start) / unit, 3)


def make_report(drill: Drill) -> dict:
    with drill.workspace.lock, drill.store.locked():
        audit = drill.store.audit_events()
        items = {item.signal.signal_id: item for item in drill.queue.snapshot()}
        rows = []
        for arrival in drill.arrivals:
            signal = arrival.signal
            injected = drill.injected.get(arrival.reference)
            item = items.get(signal.signal_id)
            case_id = drill.workspace.case_for_signal(signal.signal_id)
            execution = drill.workspace.workflow.get(UUID(case_id)) if case_id else None
            relevant = tuple(event for event in audit if (
                (case_id is not None and event.case_id == case_id)
                or (item is not None and event.signal_reference == item.reference)
            ))
            successful = tuple(event for event in relevant if event.result == AuditResult.SUCCESS)
            viewed = min((event.timestamp for event in successful if event.action == AuditAction.VIEW), default=None)
            if execution is None:
                started = finished = min((event.timestamp for event in successful
                                          if event.action == AuditAction.ANNOTATE), default=None)
            else:
                decisions = tuple(event for event in successful
                                  if event.action == AuditAction.DECIDE and event.case_detail is not None)
                started = min((event.timestamp for event in decisions if event.case_detail.action == "claim"),
                              default=None)
                finished = min((event.timestamp for event in decisions
                                if execution.case.status == "closed"
                                and event.case_detail.revision == execution.revision
                                and event.case_detail.action in ("advance", "confirm")), default=None)
            denied = []
            for event in relevant:
                if event.result != AuditResult.DENIED:
                    continue
                detail = event.case_detail
                if detail and detail.reason:
                    denied.append(f"{detail.step_id or detail.action}/{detail.reason}")
                elif event.action == AuditAction.ANNOTATE:
                    denied.append("review_denied")
            blockers = list(dict.fromkeys(denied))
            for timestamp, reason in ((injected, "not_injected"), (viewed, "not_viewed"), (finished, "not_completed")):
                if timestamp is None:
                    blockers.append(reason)
            if signal.severity == "P0" and injected is not None and started is None:
                blockers.append("not_processed")
            staff_minutes = _duration(viewed, finished, 60)
            p0_seconds = _duration(injected, started, 1) if signal.severity == "P0" else None
            if viewed is not None and finished is not None and staff_minutes is None:
                blockers.append("completion_before_view")
            if injected is not None and viewed is not None and viewed < injected:
                blockers.append("view_before_injection")
                staff_minutes = None
            if injected is not None and started is not None and started < injected:
                blockers.append("processing_before_injection")
            rows.append({
                "reference": arrival.reference,
                "severity": signal.severity,
                "signal_type": signal.signal_type,
                "playbook": execution.case.playbook_id if execution else None,
                "planned_offset_seconds": arrival.offset_seconds,
                "injected_at": _iso(injected),
                "first_viewed_at": _iso(viewed),
                "first_processed_at": _iso(started),
                "completed_at": _iso(finished),
                "staff_minutes": staff_minutes,
                "p0_alert_to_first_processing_seconds": p0_seconds,
                "blockers": blockers,
            })
        return {
            "mode": "synthetic_local",
            "seed": DRILL_SEED,
            "status": "COMPLETE" if all(
                row["injected_at"] is not None and row["staff_minutes"] is not None
                and (row["severity"] != "P0" or row["p0_alert_to_first_processing_seconds"] is not None)
                for row in rows
            ) else "INCOMPLETE",
            "staff_minutes_basis": "elapsed time from first audited view to completion, including waiting",
            "p0_alert_basis": "local queue acceptance to first successful audited claim",
            "cases": rows,
        }
