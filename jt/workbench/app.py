"""FastAPI routes for the local, HTTPS-only workbench."""

import hmac
from asyncio import to_thread
from datetime import UTC, date, datetime
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from . import pages
from .auth import SESSION_LIFETIME, AccessDenied, AccountAction, Auth, AuthenticationRequired, InvalidAccount
from .security import TOKEN, USERNAME, new_token
from .store import AuditAction, AuditResult


SESSION_COOKIE = "__Host-jt-session"
PRE_LOGIN_COOKIE = "__Host-jt-login"
FORM_LIMIT = 8192
LOGIN_FORM = ("username", "password", "code", "csrf")
SETUP_FORM = ("username", "setup_code", "password", "seed", "code", "csrf")
ACCOUNT_FORM = ("username", "role", "action", "csrf")
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
    if len(pairs) != len(names) or set(fields) != set(names):
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


def create_app(auth: Auth, *, port: int) -> FastAPI:
    host = f"127.0.0.1:{port}"
    origin = f"https://{host}"
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def apply_security(request: Request, call_next) -> Response:
        if request.url.scheme != "https" or request.headers.get("host") != host:
            response = Response(status_code=400)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = pages.CSP
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

    return app
