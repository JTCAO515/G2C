"""Escaped, server-rendered pages with a self-contained stylesheet."""

import base64
import hashlib
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from fastapi.responses import HTMLResponse

from .auth import AccountStatus
from .store import AuditAction, AuditEvent, AuditResult, Role, Session


STYLE = Path(__file__).with_name("workbench.css").read_text(encoding="utf-8")
STYLE_HASH = base64.b64encode(hashlib.sha256(STYLE.encode()).digest()).decode()
CSP = (
    f"default-src 'none'; style-src 'sha256-{STYLE_HASH}'; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)
ROLE_LABELS = {Role.OPERATOR: "值班处理员", Role.REVIEWER: "复核员", Role.ADMIN: "管理员"}
ACTION_LABELS = {
    AuditAction.LOGIN: "登录",
    AuditAction.LOGIN_FAILED: "登录失败",
    AuditAction.LOGOUT: "退出",
    AuditAction.ACCOUNT_CREATED: "创建账号",
    AuditAction.ACCOUNT_DISABLED: "停用账号",
    AuditAction.ACCOUNT_UNLOCKED: "解除锁定",
    AuditAction.ACCOUNT_ENABLED: "启用账号",
    AuditAction.ACCOUNT_DELETED: "删除账号",
    AuditAction.PASSWORD_RESET: "重设密码",
    AuditAction.ROLE_CHANGED: "分配角色",
    AuditAction.TOTP_BOUND: "绑定验证器（历史）",
    AuditAction.TOTP_REBIND_AUTHORIZED: "授权重绑（历史）",
    AuditAction.VIEW: "查看",
    AuditAction.ANNOTATE: "标注",
    AuditAction.EXPORT: "导出评测",
    AuditAction.REVEAL: "揭示",
    AuditAction.DECIDE: "人工决策",
}
RESULT_LABELS = {AuditResult.SUCCESS: "成功", AuditResult.DENIED: "拒绝"}
CASE_ACTION_LABELS = {"claim": "认领", "advance": "推进", "confirm": "确认草稿", "reject": "驳回草稿"}
CASE_DENIAL_LABELS = {
    "stale_revision": "案件已更新，请按当前步骤重新操作。",
    "case_closed": "案件已经关闭。",
    "draft_required": "当前步骤还没有待确认草稿。",
    "draft_pending": "请先处理当前草稿。",
    "customer_consent_required": "当前步骤仍需独立的客户同意。",
}


DEMO_BADGE = '<span class="demo-badge">演示数据</span>'

def csrf_field(token: str) -> str:
    return f'<input type="hidden" name="csrf" value="{escape(token, quote=True)}">'


def page(
    title: str, content: str, *, session: Session | None = None, login: bool = False, status: int = 200,
    script: str = "",
) -> HTMLResponse:
    nav = ''
    if session is not None:
        sections = '<a href="/queue">待办队列</a>'
        if session.role == Role.OPERATOR:
            sections += '<a href="/cases">案件</a><a href="/operations">运营台</a>'
        if session.role == Role.ADMIN:
            sections = '<a href="/admin/accounts">用户管理</a><a href="/admin/audit">审计日志</a>'
        nav = (
            f'<nav aria-label="工作台导航"><a href="/">首页</a>{sections}</nav>'
            f'<form method="post" action="/logout">{csrf_field(session.csrf)}'
            '<button type="submit" class="secondary">退出登录</button></form>'
        )
    main_class = ' class="login-layout"' if login else ''
    script_tag = f"<script>{script}</script>" if script else ""
    return HTMLResponse(
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(title)} · JT 工作台</title><style>{STYLE}</style></head>'
        '<body><header><div class="bar"><strong class="wordmark">JT 工作台</strong>'
        f'{nav}</div></header><main{main_class}>{content}</main>{script_tag}</body></html>',
        status_code=status,
    )


def login_page(csrf: str, *, failed: bool = False) -> HTMLResponse:
    error = '<p class="error" role="alert">登录未通过，请确认输入或稍后重试。</p>' if failed else ''
    return page("工作人员登录", f'''
        <section class="panel login-panel" aria-labelledby="headline">
          <h1 id="headline">工作人员登录</h1>
          <p class="muted">使用工作台账号和密码登录。</p>
          {error}
          <form method="post" action="/login">
            {csrf_field(csrf)}
            <label>账号<input name="username" autocomplete="username" maxlength="32" required autofocus></label>
            <label>密码<input type="password" name="password" autocomplete="current-password" maxlength="128" required></label>
            <button type="submit">登录</button>
          </form>
        </section>
    ''', login=True, status=401 if failed else 200)


def home_page(session: Session) -> HTMLResponse:
    return page("首页", f'''
        <section class="panel">
          <h1>工作台首页</h1>
          <p>当前角色 <strong>{ROLE_LABELS[session.role]}</strong></p>
        </section>
    ''', session=session)


def select_options(labels, selected: str = "") -> str:
    return ''.join(f'<option value="{value}"{" selected" if value == selected else ""}>{label}</option>'
                   for value, label in labels.items())


def password_fields(label: str = "密码") -> str:
    return (f'<label>{label}<input type="password" name="password" autocomplete="new-password" minlength="12" '
            'maxlength="128" required><small>至少 12 位。</small></label>'
            '<label>再次输入密码<input type="password" name="confirm" autocomplete="new-password" minlength="12" '
            'maxlength="128" required></label>')


def account_controls(session: Session, account: AccountStatus) -> str:
    username = escape(account.username)
    own = session.username == account.username
    if not account.enabled and not account.has_password:
        return '—'
    reset = f'''
          <form method="post" action="/admin/accounts/password" autocomplete="off">
            {csrf_field(session.csrf)}
            <input type="hidden" name="username" value="{username}">
            {password_fields("新密码")}
            <div class="buttons"><button type="submit">重设密码</button></div>
          </form>''' if account.enabled else ''
    manage = ''
    if not own:
        role = select_options(ROLE_LABELS, account.role)
        if account.enabled:
            unlock = '<button name="action" value="unlock">解除锁定</button>' if account.locked else ''
            buttons = (f'<label>角色<select name="role">{role}</select></label><div class="buttons">'
                       f'<button name="action" value="change_role">保存角色</button>{unlock}'
                       '<button class="danger" name="action" value="disable">停用账号</button></div>')
        else:
            buttons = ('<input type="hidden" name="role" value="reviewer"><div class="buttons">'
                       '<button name="action" value="enable">启用账号</button>'
                       '<button class="danger" name="action" value="delete">删除账号（清除密码，不可恢复）</button></div>')
        manage = f'''
          <form method="post" action="/admin/accounts">
            {csrf_field(session.csrf)}
            <input type="hidden" name="username" value="{username}">
            {buttons}
          </form>'''
    return f'''
        <button class="secondary" popovertarget="staff-{username}">管理</button>
        <section class="panel dialog" id="staff-{username}" popover aria-label="管理 {username}">
          <h2>管理 <code>{username}</code></h2>{manage}{reset}
        </section>
    '''


def account_status(account: AccountStatus) -> str:
    if not account.enabled:
        return '已停用' if account.has_password else '已删除'
    return '已锁定' if account.locked else '正常' if account.has_password else '待设密码'


def accounts_page(
    session: Session, accounts: tuple[AccountStatus, ...], *, saved: bool = False, rejected: bool = False,
) -> HTMLResponse:
    notice = ''
    if saved:
        notice = '<p class="notice" role="status">账号状态已更新。</p>'
    elif rejected:
        notice = '<p class="error" role="alert">无法更新账号，请核对账号、角色、当前状态，密码至少 12 位且两次输入一致。</p>'
    rows = [f'<tr><td><code>{escape(account.username)}</code></td><td>{ROLE_LABELS[account.role]}</td>'
            f'<td>{account_status(account)}</td><td>{account_controls(session, account)}</td></tr>'
            for account in accounts]
    return page("用户管理", f'''
        <div class="page-heading">
          <h1>用户管理</h1>
          <button popovertarget="new-staff">添加账号</button>
        </div>
        {notice}
        <section class="panel dialog" id="new-staff" popover aria-label="添加工作人员账号">
          <h2>添加工作人员账号</h2>
          <form method="post" action="/admin/accounts/create" autocomplete="off">
            {csrf_field(session.csrf)}
            <label>账号<input name="username" pattern="[a-z][a-z0-9_\\-]{{2,31}}" maxlength="32" required><small>3 至 32 位，小写字母开头，可用小写字母、数字、下划线和连字符。</small></label>
            <label>角色<select name="role" required>{select_options(ROLE_LABELS)}</select></label>
            {password_fields()}
            <button type="submit">添加账号</button>
          </form>
        </section>
        <section class="panel table-panel" aria-label="工作人员账号">
          <table>
            <thead><tr><th scope="col">账号</th><th scope="col">角色</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </section>
    ''', session=session, status=400 if rejected else 200)


def audit_page(session: Session, events: tuple[AuditEvent, ...], filters: dict[str, str]) -> HTMLResponse:
    rows = []
    for event in sorted(reversed(events), key=lambda item: item.timestamp, reverse=True):
        timestamp = datetime.fromtimestamp(event.timestamp, UTC).strftime("%Y-%m-%d %H:%M:%S")
        actor = escape(event.actor) if event.actor is not None else '—'
        case_id = escape(event.case_id) if event.case_id is not None else '—'
        target = escape(event.staff_target) if event.staff_target is not None else '—'
        action = ACTION_LABELS[event.action]
        detail = event.case_detail
        if detail is not None:
            step = f' · <code>{escape(detail.step_id)}</code>' if detail.step_id else ''
            revision = f' · 版本 {detail.revision}' if detail.revision is not None else ''
            reason = f'<br>{CASE_DENIAL_LABELS.get(detail.reason, "操作被拒绝。")}' if detail.reason else ''
            action = f'案件 {CASE_ACTION_LABELS[detail.action]}{step}{revision}{reason}'
        operations = event.operations_detail
        if operations is not None:
            action = f'演示操作 <code>{escape(operations.action)} · {escape(operations.reference)}</code>'
        rows.append(f'<tr><td><time>{timestamp}</time></td><td>{action}</td><td>{actor}</td>'
                    f'<td>{target}</td><td>{case_id}</td><td>{RESULT_LABELS[event.result]}</td></tr>')
    return page("审计日志", f'''
        <h1>审计日志</h1>
        <form class="audit-filters" method="get" action="/admin/audit" aria-label="筛选审计日志">
          <label>从（UTC）<input type="date" name="start" value="{escape(filters['start'])}"></label>
          <label>至（UTC）<input type="date" name="end" value="{escape(filters['end'])}"></label>
          <label>工作人员<input name="actor" maxlength="32" value="{escape(filters['actor'])}"></label>
          <label>操作<select name="action"><option value="">全部</option>{select_options(ACTION_LABELS, filters['action'])}</select></label>
          <label>结果<select name="result"><option value="">全部</option>{select_options(RESULT_LABELS, filters['result'])}</select></label>
          <button type="submit">筛选</button><a href="/admin/audit">清除</a>
        </form>
        <section class="panel table-panel" aria-label="审计日志记录">
          <table>
            <thead><tr><th scope="col">时间（UTC）</th><th scope="col">操作</th><th scope="col">工作人员</th><th scope="col">目标账号</th><th scope="col">案件编号</th><th scope="col">结果</th></tr></thead>
            <tbody>{''.join(rows) or '<tr><td colspan="6">没有符合条件的记录。</td></tr>'}</tbody>
          </table>
        </section>
    ''', session=session)


def denied_page(*, logged_in: bool = False) -> HTMLResponse:
    if logged_in:
        return page("访问被拒绝", '<h1>访问被拒绝</h1><p>此操作未获授权。</p>', status=403)
    return page("请先登录", '<h1>请先登录</h1><p><a href="/login">前往工作人员登录</a></p>', status=401)
