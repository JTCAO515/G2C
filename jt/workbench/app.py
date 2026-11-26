"""FastAPI routes for the local, HTTPS-only workbench."""

import hmac
from asyncio import to_thread
from datetime import UTC, date, datetime
from typing import cast
from urllib.parse import parse_qsl, urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from jt.common import Severity
from jt.synthetic import generate_dataset

from . import pages, queue_pages
from .auth import SESSION_LIFETIME, AccessDenied, AccountAction, Auth, AuthenticationRequired, InvalidAccount
from .queue import MemoryQueue, QueueItem, QueueStore, Review, display_text
from .security import TOKEN, USERNAME, new_token
from .store import AuditAction, AuditEvent, AuditResult, Role, Session


SESSION_COOKIE = "__Host-jt-session"
PRE_LOGIN_COOKIE = "__Host-jt-login"
FORM_LIMIT = 8192
LOGIN_FORM = ("username", "password", "code", "csrf")
SETUP_FORM = ("username", "setup_code", "password", "seed", "code", "csrf")
ACCOUNT_FORM = ("username", "role", "action", "csrf")
REVIEW_FORM = ("signal", "actual_severity", "false_positive", "missed", "note", "csrf")
SEVERITIES = ("P0", "P1", "P2", "P3", "P4")
COOKIE_POLICY = {"path": "/", "secure": True, "httponly": True, "samesite": "strict"}


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
            or any("\0" in value for value in fields.values())):
        raise HTTPException(400, "表单有误。")
    if (len(fields.get("username", "")) > 32 or len(fields.get("password", "")) > 128
            or len(fields.get("code", "")) > 6 or len(fields.get("seed", "")) > 40):
        raise HTTPException(400, "表单有误。")
    return fields


def session_token(request: Request) -> str:
    return request.cookies.get(SESSION_COOKIE, "")


def pre_login_response(*, setup: bool = False, failed: bool = False) -> Response:
    csrf = new_token()
    render = pages.setup_page if setup else pages.login_page
    result = render(csrf, failed=failed)
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


def create_app(auth: Auth, *, port: int, queue: QueueStore | None = None) -> FastAPI:
    host = f"127.0.0.1:{port}"
    origin = f"https://{host}"
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    work_queue = MemoryQueue(generate_dataset().signals) if queue is None else queue

    @app.middleware("http")
    async def apply_security(request: Request, call_next) -> Response:
        if request.url.scheme != "https" or request.headers.get("host") != host:
            response = Response(status_code=400)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault("Content-Security-Policy", pages.CSP)
        # Native form POSTs need their same-origin Origin header for CSRF validation.
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(AuthenticationRequired)
    async def no_session(_request: Request, _error: AuthenticationRequired) -> Response:
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
        token = await to_thread(auth.login, fields["username"], fields["password"], fields["code"],
                                previous_token=session_token(request))
        if token is None:
            return pre_login_response(failed=True)
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(PRE_LOGIN_COOKIE, **COOKIE_POLICY)
        response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_LIFETIME, **COOKIE_POLICY)
        return response

    @app.get("/setup")
    def setup() -> Response:
        return pre_login_response(setup=True)

    @app.post("/setup")
    async def bind(request: Request) -> Response:
        fields = await read_form(request, origin, SETUP_FORM)
        require_pre_login_csrf(request, fields["csrf"])
        bound = await to_thread(auth.bind_account, fields["username"], fields["setup_code"],
                                fields["password"], fields["seed"], fields["code"])
        if not bound:
            return pre_login_response(setup=True, failed=True)
        response = pages.setup_done_page()
        response.delete_cookie(PRE_LOGIN_COOKIE, **COOKIE_POLICY)
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

    @app.post("/admin/accounts")
    async def manage_account(request: Request) -> Response:
        fields = await read_form(request, origin, ACCOUNT_FORM)
        try:
            action = AccountAction(fields["action"])
        except ValueError:
            raise HTTPException(400, "操作有误。") from None
        token = session_token(request)
        try:
            setup_code = await to_thread(auth.manage_account, token, fields["csrf"], action,
                                         fields["username"], fields["role"])
        except InvalidAccount:
            return pages.accounts_page(*await to_thread(auth.inspect_accounts, token), rejected=True)
        return pages.accounts_page(*await to_thread(auth.inspect_accounts, token), setup_code=setup_code, saved=True)

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

    @app.get("/queue")
    def queue_view(request: Request) -> Response:
        with auth.store.locked():
            session = queue_session(request)
            signal_type = request.query_params.get("type", "")
            status = request.query_params.get("status", "")
            if (signal_type and signal_type not in queue_pages.TYPE_LABELS) or (status and status not in queue_pages.STATUS_LABELS):
                raise HTTPException(400, "筛选条件有误。")
            reference = request.query_params.get("signal", "")
            selected = selected_item(reference) if reference else None
            items = tuple(item for item in work_queue.snapshot()
                          if (not signal_type or item.signal.signal_type == signal_type)
                          and (not status or item.status == status))
            alerts = work_queue.alerts()
            auth.store.append_audit(AuditEvent(auth.clock(), AuditAction.VIEW, session.username,
                                              selected.case_id if selected else None,
                                              signal_reference=selected.reference if selected else None))
        return queue_pages.queue_page(session, items, selected, signal_type=signal_type, status=status, alerts=alerts)

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

    return app
