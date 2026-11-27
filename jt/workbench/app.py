"""FastAPI routes for the local, HTTPS-only workbench."""

import hmac
import re
from asyncio import to_thread
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import cast
from urllib.parse import parse_qsl, urlencode
from uuid import UUID

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from jt.common import CaseExecution, Severity
from jt.playbook.workflow import StaffAction
from jt.synthetic import generate_dataset

from . import case_pages, operations_pages, pages, queue_pages
from .auth import SESSION_LIFETIME, AccessDenied, AccountAction, Auth, AuthenticationRequired, InvalidAccount
from .cases import CaseWorkspace, workbench_audit
from .operations import DemoOperations, EvidenceRequired, OperationConflict, OperationMissing, OperationsSource
from .queue import MemoryQueue, QueueItem, QueueStore, Review, display_text
from .security import TOKEN, USERNAME, new_token
from .store import AuditAction, AuditEvent, AuditResult, CaseAuditDetail, OperationsAuditDetail, Role, Session


SESSION_COOKIE = "__Host-jt-session"
PRE_LOGIN_COOKIE = "__Host-jt-login"
FORM_LIMIT = 8192
LOGIN_FORM = ("username", "password", "csrf")
ACCOUNT_FORM = ("username", "role", "action", "csrf")
ACCOUNT_CREATE_FORM = ("username", "role", "password", "confirm", "csrf")
ACCOUNT_PASSWORD_FORM = ("username", "password", "confirm", "csrf")
PASSWORD_FIELDS = ("password", "confirm")
REVIEW_FORM = ("signal", "actual_severity", "false_positive", "missed", "note", "csrf")
SEVERITIES = ("P0", "P1", "P2", "P3", "P4")
CASE_REVISION = re.compile(r"0|[1-9][0-9]{0,18}")
CASE_FORM = ("action", "revision", "csrf")
REQUEST_FORM = ("target", "seq", "evidence", "amount", "csrf")
LEAD_FORM = ("target", "csrf")
COOKIE_POLICY = {"path": "/", "secure": True, "httponly": True, "samesite": "strict"}
HEALTH_HOST = "jt-workbench-health"


@dataclass(frozen=True)
class ProxyEntry:
    host: str
    check_ready: Callable[[], None]


async def read_form(request: Request, origin: str, names: tuple[str, ...]) -> dict[str, str]:
    if request.headers.get("origin") != origin:
        raise AccessDenied
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/x-www-form-urlencoded":
        raise HTTPException(415, "表单格式有误。")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > FORM_LIMIT:
            raise HTTPException(413, "表单过大。")
        body.extend(chunk)
    try:
        pairs = parse_qsl(body.decode(), keep_blank_values=True, strict_parsing=True,
                          max_num_fields=len(names), errors="strict")
    except ValueError:
        raise HTTPException(400, "表单有误。") from None
    fields = dict(pairs)
    if (len(pairs) != len(names) or set(fields) != set(names)
            or any("\0" in value for name, value in fields.items() if name not in PASSWORD_FIELDS)):
        raise HTTPException(400, "表单有误。")
    if len(fields.get("username", "")) > 32 or any(len(fields.get(name, "")) > 128 for name in PASSWORD_FIELDS):
        raise HTTPException(400, "表单有误。")
    return fields


def session_token(request: Request) -> str:
    return request.cookies.get(SESSION_COOKIE, "")


def pre_login_response(*, failed: bool = False) -> Response:
    csrf = new_token()
    result = pages.login_page(csrf, failed=failed)
    result.set_cookie(PRE_LOGIN_COOKIE, csrf, max_age=600, **COOKIE_POLICY)
    return result


def require_pre_login_csrf(request: Request, csrf: str) -> None:
    cookie = request.cookies.get(PRE_LOGIN_COOKIE, "")
    if not TOKEN.fullmatch(csrf) or not hmac.compare_digest(csrf.encode(), cookie.encode()):
        raise AccessDenied


def review_input(fields: dict[str, str], actor: str, timestamp: float) -> Review | None:
    severity = fields["actual_severity"]
    false_positive = fields["false_positive"]
    missed = fields["missed"]
    note = fields["note"].strip()
    if false_positive not in ("0", "1") or missed not in ("0", "1") or len(note) > 500:
        return None
    if false_positive == "1":
        if severity or missed == "1":
            return None
    elif severity not in SEVERITIES:
        return None
    return Review(cast(Severity | None, severity or None), false_positive == "1", missed == "1",
                  display_text(note), actor, datetime.fromtimestamp(timestamp, UTC))


def evaluation_sample(item: QueueItem, review: Review) -> dict:
    signal = item.signal
    return {
        "case_id": item.case_id,
        "signal_type": signal.signal_type,
        "detected_severity": signal.severity,
        "detected_at": signal.detected_at.isoformat(),
        "redacted_fragments": [display_text(fragment) for fragment in signal.redacted_fragments],
        "rule_hits": [display_text(hit) for hit in signal.rule_hits],
        "signal_schema_version": signal.schema_version,
        "rules_version": display_text(signal.rules_version),
        "redaction_version": display_text(signal.redaction_version),
        "model_outputs": [{"model_version": display_text(observation.model_version),
                           "output": observation.output.model_dump(mode="json")}
                          for observation in signal.model_outputs],
        "review": {"actual_severity": review.actual_severity, "false_positive": review.false_positive,
                   "missed": review.missed, "note": review.note, "recorded_at": review.recorded_at.isoformat()},
    }


def create_app(
    auth: Auth, *, port: int = 8443, queue: QueueStore | None = None, proxy: ProxyEntry | None = None,
    cases: CaseWorkspace | None = None, operations: OperationsSource | None = None,
) -> FastAPI:
    host = proxy.host if proxy else f"127.0.0.1:{port}"
    origin = f"https://{host}"
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    signals = generate_dataset().signals
    work_queue = MemoryQueue(signals) if queue is None else queue
    workspace = CaseWorkspace.from_signals(signals) if cases is None else cases
    ops = DemoOperations() if operations is None else operations

    @app.middleware("http")
    async def apply_security(request: Request, call_next) -> Response:
        hosts = request.headers.getlist("host")
        scheme = request.scope["scheme"]
        forwarded = request.headers.getlist("x-forwarded-proto")
        via_socket = request.scope.get("client") is None and scheme == "http"
        if proxy and via_socket and hosts == [HEALTH_HOST] and not forwarded and (
            request.method == "GET" and request.scope["path"] == "/healthz"
        ):
            try:
                await to_thread(proxy.check_ready)
            except (psycopg.Error, RuntimeError):
                response = Response(status_code=503)
            else:
                response = Response(status_code=200)
        elif hosts == [host] and (
            via_socket and forwarded == ["https"] if proxy else scheme == "https"
        ):
            if proxy:
                request.scope["scheme"] = "https"
            response = await call_next(request)
        else:
            response = Response(status_code=400)
        response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault("Content-Security-Policy", pages.CSP)
        # Native form POSTs need their same-origin Origin header for CSRF validation.
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if proxy:
            response.headers["X-Robots-Tag"] = "noindex"
            if via_socket and hosts == [host] and forwarded == ["https"]:
                response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.exception_handler(psycopg.Error)
    async def database_unavailable(_request: Request, _error: psycopg.Error) -> Response:
        return pages.page("工作台暂不可用", "<h1>工作台暂不可用</h1><p>请稍后重试。</p>", status=503)

    @app.exception_handler(AuthenticationRequired)
    async def no_session(request: Request, _error: AuthenticationRequired) -> Response:
        if proxy and request.scope["path"] != "/queue/alerts":
            response = RedirectResponse("/login", status_code=303)
        else:
            response = pages.denied_page()
        response.delete_cookie(SESSION_COOKIE, **COOKIE_POLICY)
        return response

    @app.exception_handler(AccessDenied)
    async def no_access(_request: Request, _error: AccessDenied) -> Response:
        return pages.denied_page(logged_in=True)

    @app.get("/login")
    def login() -> Response:
        return pre_login_response()

    @app.post("/login")
    async def enter(request: Request) -> Response:
        fields = await read_form(request, origin, LOGIN_FORM)
        require_pre_login_csrf(request, fields["csrf"])
        token = await to_thread(auth.login, fields["username"], fields["password"],
                                previous_token=session_token(request))
        if token is None:
            return pre_login_response(failed=True)
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(PRE_LOGIN_COOKIE, **COOKIE_POLICY)
        response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_LIFETIME, **COOKIE_POLICY)
        return response

    @app.get("/")
    def home(request: Request) -> Response:
        return pages.home_page(auth.require_session(session_token(request)))

    @app.post("/logout")
    async def leave(request: Request) -> Response:
        fields = await read_form(request, origin, ("csrf",))
        await to_thread(auth.logout, session_token(request), fields["csrf"])
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, **COOKIE_POLICY)
        return response

    @app.get("/admin/accounts")
    def accounts(request: Request) -> Response:
        return pages.accounts_page(*auth.inspect_accounts(session_token(request)))

    async def change_account(
        request: Request, names: tuple[str, ...], action: Callable[[dict[str, str]], AccountAction],
    ) -> Response:
        fields = await read_form(request, origin, names)
        token = session_token(request)
        try:
            chosen = action(fields)
            # A mistyped confirmation is a rejected request, audited like any other refusal.
            password = fields.get("password", "") if fields.get("password") == fields.get("confirm", "") else ""
            await to_thread(auth.manage_account, token, fields["csrf"], chosen, fields["username"],
                            fields.get("role", ""), password)
        except InvalidAccount:
            return pages.accounts_page(*await to_thread(auth.inspect_accounts, token), rejected=True)
        try:
            return pages.accounts_page(*await to_thread(auth.inspect_accounts, token), saved=True)
        except AuthenticationRequired:
            # The administrator reset the own password: every session of the account just ended.
            response = RedirectResponse("/login", status_code=303)
            response.delete_cookie(SESSION_COOKIE, **COOKIE_POLICY)
            return response

    def listed_action(fields: dict[str, str]) -> AccountAction:
        try:
            chosen = AccountAction(fields["action"])
        except ValueError:
            raise HTTPException(400, "操作有误。") from None
        if chosen in (AccountAction.CREATE, AccountAction.RESET_PASSWORD):
            raise HTTPException(400, "操作有误。")
        return chosen

    @app.post("/admin/accounts")
    async def manage_account(request: Request) -> Response:
        return await change_account(request, ACCOUNT_FORM, listed_action)

    @app.post("/admin/accounts/create")
    async def create_account(request: Request) -> Response:
        return await change_account(request, ACCOUNT_CREATE_FORM, lambda _fields: AccountAction.CREATE)

    @app.post("/admin/accounts/password")
    async def reset_password(request: Request) -> Response:
        return await change_account(request, ACCOUNT_PASSWORD_FORM, lambda _fields: AccountAction.RESET_PASSWORD)

    @app.get("/admin/audit")
    def audit(request: Request) -> Response:
        filters = {name: request.query_params.get(name, "") for name in ("start", "end", "actor", "action", "result")}
        try:
            start = date.fromisoformat(filters["start"]) if filters["start"] else date.min
            end = date.fromisoformat(filters["end"]) if filters["end"] else date.max
            action = AuditAction(filters["action"]) if filters["action"] else None
            result = AuditResult(filters["result"]) if filters["result"] else None
        except ValueError:
            raise HTTPException(400, "审计筛选条件有误。") from None
        actor = filters["actor"]
        if start > end or (actor and not USERNAME.fullmatch(actor)):
            raise HTTPException(400, "审计筛选条件有误。")
        session, events = auth.inspect_audit(session_token(request))
        selected = tuple(event for event in events if (
            start <= datetime.fromtimestamp(event.timestamp, UTC).date() <= end
            and (not actor or event.actor == actor)
            and (action is None or event.action == action)
            and (result is None or event.result == result)
        ))
        return pages.audit_page(session, selected, filters)

    def queue_session(request: Request, *, touch: bool = True) -> Session:
        session = auth.require_session(session_token(request), touch=touch)
        if session.role not in (Role.OPERATOR, Role.REVIEWER):
            raise AccessDenied
        return session

    def selected_item(reference: str) -> QueueItem:
        selected = work_queue.item(reference) if TOKEN.fullmatch(reference) else None
        if selected is None:
            raise HTTPException(404, "找不到该信号。")
        return selected

    def with_demo_case(item: QueueItem) -> QueueItem:
        case_id = workspace.case_for_signal(item.signal.signal_id)
        return replace(item, case_id=case_id) if case_id and item.case_id is None else item

    @app.get("/queue")
    def queue_view(request: Request) -> Response:
        with workspace.lock, auth.store.locked():
            session = queue_session(request)
            signal_type = request.query_params.get("type", "")
            status = request.query_params.get("status", "")
            if (signal_type and signal_type not in queue_pages.TYPE_LABELS) or (status and status not in queue_pages.STATUS_LABELS):
                raise HTTPException(400, "筛选条件有误。")
            reference = request.query_params.get("signal", "")
            selected = with_demo_case(selected_item(reference)) if reference else None
            items = tuple(with_demo_case(item) for item in work_queue.snapshot()
                          if (not signal_type or item.signal.signal_type == signal_type)
                          and (not status or item.status == status))
            alerts = work_queue.alerts()
            case_access = None
            if (selected and session.role == Role.OPERATOR and not workspace.failed
                    and selected.case_id == workspace.case_for_signal(selected.signal.signal_id)
                    and selected.case_id is not None):
                identifier = UUID(selected.case_id)
                if workspace.owned(identifier, session.username) is not None:
                    case_access = "owned"
                elif workspace.unclaimed(identifier) is not None:
                    case_access = "unclaimed"
            auth.store.append_audit(AuditEvent(auth.clock(), AuditAction.VIEW, session.username,
                                              selected.case_id if selected else None,
                                              signal_reference=selected.reference if selected else None))
        return queue_pages.queue_page(session, items, selected, signal_type=signal_type, status=status,
                                      alerts=alerts, case_access=case_access)

    @app.get("/queue/alerts")
    def queue_alerts(request: Request) -> Response:
        with auth.store.locked():
            queue_session(request, touch=False)
            pending, revision = work_queue.alerts()
        return JSONResponse({"pending": pending, "revision": revision})

    @app.post("/queue/review")
    async def add_review(request: Request) -> Response:
        fields = await read_form(request, origin, REVIEW_FORM)
        return await to_thread(record_review, session_token(request), fields)

    def record_review(token: str, fields: dict[str, str]) -> Response:
        with auth.store.locked():
            session = auth.require_session(token, role=Role.REVIEWER, csrf=fields["csrf"])
            item = selected_item(fields["signal"])
            timestamp = auth.clock()
            review = review_input(fields, session.username, timestamp)
            event = AuditEvent(timestamp, AuditAction.ANNOTATE, session.username, item.case_id,
                               AuditResult.SUCCESS if review else AuditResult.DENIED,
                               signal_reference=item.reference)
            if review is not None:
                work_queue.append_review(item, review)
            auth.store.append_audit(event)
            if review is None:
                items, alerts = work_queue.snapshot(), work_queue.alerts()
        if review is None:
            return queue_pages.queue_page(session, items, item, signal_type="", status="", alerts=alerts,
                                          invalid_review=True)
        return RedirectResponse(f"/queue?{urlencode({'signal': item.reference})}", status_code=303)

    @app.get("/queue/export")
    def queue_export(request: Request) -> Response:
        with auth.store.locked():
            session = auth.require_session(session_token(request), role=Role.REVIEWER)
            items = work_queue.snapshot()
            auth.store.append_audit(AuditEvent(auth.clock(), AuditAction.EXPORT, session.username))
        return JSONResponse(
            {"schema_version": "jt-workbench-review-export.v1",
             "samples": [evaluation_sample(item, item.reviews[-1]) for item in items if item.reviews]},
            headers={"Content-Disposition": 'attachment; filename="jt-review-samples.json"'},
        )

    def case_identifier(value: str) -> UUID:
        try:
            parsed = UUID(value)
        except ValueError:
            raise HTTPException(404, "找不到该案件。") from None
        if parsed.version != 4 or str(parsed) != value:
            raise HTTPException(404, "找不到该案件。")
        return parsed

    def case_session(token: str, csrf: str | None = None) -> Session:
        session = auth.require_session(token, role=Role.OPERATOR, csrf=csrf)
        if workspace.failed:
            raise HTTPException(503, "演练案件暂不可用。")
        return session

    def owned_case(case_id: UUID, session: Session) -> CaseExecution:
        execution = workspace.owned(case_id, session.username)
        if execution is None:
            raise HTTPException(404, "找不到该案件。")
        return execution

    @app.get("/cases")
    def list_cases(request: Request) -> Response:
        with workspace.lock, auth.store.locked():
            session = case_session(session_token(request))
            entries = workspace.listing(session.username)
            auth.store.append_audit(AuditEvent(auth.clock(), AuditAction.VIEW, session.username))
        return case_pages.case_list(session, entries)

    @app.get("/cases/{case_id}")
    def show_case(request: Request, case_id: str) -> Response:
        with workspace.lock, auth.store.locked():
            session = case_session(session_token(request))
            identifier = case_identifier(case_id)
            execution = owned_case(identifier, session)
            auth.store.append_audit(AuditEvent(auth.clock(), AuditAction.VIEW, session.username, str(identifier)))
        return case_pages.case_detail(session, execution)

    @app.post("/cases/{case_id}/claim")
    async def claim_case(request: Request, case_id: str) -> Response:
        fields = await read_form(request, origin, ("csrf",))
        return await to_thread(record_claim, session_token(request), case_id, fields["csrf"])

    def record_claim(token: str, case_id: str, csrf: str) -> Response:
        with workspace.lock:
            with auth.store.locked():
                session = case_session(token, csrf)
                identifier = case_identifier(case_id)
                execution = workspace.unclaimed(identifier)
                if execution is None:
                    raise HTTPException(404, "找不到可认领的案件。")
                auth.store.append_audit(AuditEvent(
                    auth.clock(), AuditAction.DECIDE, session.username, str(identifier),
                    case_detail=CaseAuditDetail("claim", revision=execution.revision),
                ))
            workspace.assign(identifier, session.username)
        return RedirectResponse(f"/cases/{identifier}", status_code=303)

    @app.post("/cases/{case_id}/action")
    async def act_on_case(request: Request, case_id: str) -> Response:
        fields = await read_form(request, origin, CASE_FORM)
        return await to_thread(record_case_action, session_token(request), case_id, fields)

    def record_case_action(token: str, case_id: str, fields: dict[str, str]) -> Response:
        changed = False
        with workspace.lock:
            try:
                with auth.store.locked():
                    session = case_session(token, fields["csrf"])
                    identifier = case_identifier(case_id)
                    owned_case(identifier, session)
                    action, revision = fields["action"], fields["revision"]
                    if action not in ("advance", "confirm", "reject") or not CASE_REVISION.fullmatch(revision):
                        raise HTTPException(400, "案件操作有误。")
                    result = workspace.act(identifier, session.username, cast(StaffAction, action), int(revision))
                    changed = result.audit.outcome == "applied"
                    auth.store.append_audit(workbench_audit(result.audit))
            except Exception:
                # JT1's synthetic state is in-process. Never serve an applied but unaudited change.
                if changed:
                    workspace.failed = True
                raise
        if result.audit.reason is not None:
            return case_pages.case_detail(session, cast(CaseExecution, result.execution), reason=result.audit.reason)
        return RedirectResponse(f"/cases/{identifier}", status_code=303)

    def record_operations(token: str, csrf: str, detail: OperationsAuditDetail) -> None:
        with auth.store.locked():
            session = auth.require_session(token, role=Role.OPERATOR, csrf=csrf)
            auth.store.append_audit(AuditEvent(auth.clock(), AuditAction.DECIDE, session.username,
                                              operations_detail=detail))

    @app.get("/operations")
    def list_requests(request: Request) -> Response:
        session = auth.require_session(session_token(request), role=Role.OPERATOR)
        return operations_pages.request_list(session, ops.requests())

    @app.get("/operations/requests/{request_id}")
    def show_request(request: Request, request_id: str) -> Response:
        session = auth.require_session(session_token(request), role=Role.OPERATOR)
        item = ops.request(request_id)
        if item is None:
            raise HTTPException(404, "找不到演示请求。")
        return operations_pages.request_detail(session, item)

    @app.get("/operations/leads")
    def list_leads(request: Request) -> Response:
        session = auth.require_session(session_token(request), role=Role.OPERATOR)
        return operations_pages.lead_list(session, ops.leads())

    def apply_request(token: str, request_id: str, fields: dict[str, str]) -> Response:
        auth.require_session(token, role=Role.OPERATOR, csrf=fields["csrf"], touch=False)
        if not CASE_REVISION.fullmatch(fields["seq"]):
            raise HTTPException(400, "演示请求版本有误。")
        try:
            ops.change_request(request_id, fields["target"], int(fields["seq"]), fields["evidence"], fields["amount"],
                               lambda detail: record_operations(token, fields["csrf"], detail))
        except OperationMissing:
            raise HTTPException(404, "找不到演示请求。") from None
        except OperationConflict:
            raise HTTPException(409, "演示状态已更新或不允许此操作。") from None
        except EvidenceRequired:
            raise HTTPException(400, "请填写演示凭据，并在报价时提供有效金额。") from None
        return RedirectResponse(f"/operations/requests/{request_id}", status_code=303)

    @app.post("/operations/requests/{request_id}")
    async def change_request(request: Request, request_id: str) -> Response:
        fields = await read_form(request, origin, REQUEST_FORM)
        return await to_thread(apply_request, session_token(request), request_id, fields)

    def apply_lead(token: str, client_request_id: str, fields: dict[str, str]) -> Response:
        auth.require_session(token, role=Role.OPERATOR, csrf=fields["csrf"], touch=False)
        try:
            ops.change_lead(client_request_id, fields["target"],
                            lambda detail: record_operations(token, fields["csrf"], detail))
        except OperationMissing:
            raise HTTPException(404, "找不到演示线索。") from None
        except OperationConflict:
            raise HTTPException(409, "演示线索状态已更新或不允许此操作。") from None
        return RedirectResponse("/operations/leads", status_code=303)

    @app.post("/operations/leads/{client_request_id}")
    async def change_lead(request: Request, client_request_id: str) -> Response:
        fields = await read_form(request, origin, LEAD_FORM)
        return await to_thread(apply_lead, session_token(request), client_request_id, fields)

    return app
