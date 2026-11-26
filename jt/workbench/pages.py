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
    AuditAction.ROLE_CHANGED: "分配角色",
    AuditAction.TOTP_BOUND: "绑定验证器",
    AuditAction.TOTP_REBIND_AUTHORIZED: "授权重绑",
    AuditAction.VIEW: "查看",
    AuditAction.ANNOTATE: "标注",
    AuditAction.REVEAL: "揭示",
    AuditAction.DECIDE: "人工决策",
}
RESULT_LABELS = {AuditResult.SUCCESS: "成功", AuditResult.DENIED: "拒绝"}


def csrf_field(token: str) -> str:
    return f'<input type="hidden" name="csrf" value="{escape(token, quote=True)}">'


def page(
    title: str, content: str, *, session: Session | None = None, login: bool = False, status: int = 200,
) -> HTMLResponse:
    nav = ''
    if session is not None:
        admin_nav = ''
        if session.role == Role.ADMIN:
            admin_nav = '<a href="/admin/accounts">账号管理</a><a href="/admin/audit">审计日志</a>'
        nav = (
            f'<nav aria-label="工作台导航"><a href="/">首页</a>{admin_nav}</nav>'
            f'<form method="post" action="/logout">{csrf_field(session.csrf)}'
            '<button type="submit" class="secondary">退出登录</button></form>'
        )
    main_class = ' class="login-layout"' if login else ''
    return HTMLResponse(
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(title)} · JT 工作台</title><style>{STYLE}</style></head>'
        '<body><header><div class="bar"><strong class="wordmark">JT 工作台</strong>'
        f'{nav}</div></header><main{main_class}>{content}</main></body></html>',
        status_code=status,
    )


def login_page(csrf: str, *, failed: bool = False) -> HTMLResponse:
    error = '<p class="error" role="alert">登录未通过，请确认输入或稍后重试。</p>' if failed else ''
    return page("工作人员登录", f'''
        <section class="panel login-panel" aria-labelledby="headline">
          <h1 id="headline">工作人员登录</h1>
          <p class="muted">使用工作台账号和验证器中的动态验证码登录。</p>
          {error}
          <form method="post" action="/login">
            {csrf_field(csrf)}
            <label>账号<input name="username" autocomplete="username" maxlength="32" required autofocus></label>
            <label>密码<input type="password" name="password" autocomplete="current-password" maxlength="128" required></label>
            <label>动态验证码<input name="code" autocomplete="one-time-code" inputmode="numeric" pattern="[0-9]{{6}}" maxlength="6" required></label>
            <button type="submit">登录</button>
          </form>
          <p class="setup-link"><a href="/setup">首次设置或重绑验证器</a></p>
        </section>
    ''', login=True, status=401 if failed else 200)


def home_page(session: Session) -> HTMLResponse:
    return page("首页", f'''
        <section class="panel">
          <h1>工作台首页</h1>
          <p>当前角色 <strong>{ROLE_LABELS[session.role]}</strong></p>
        </section>
    ''', session=session)


def setup_page(csrf: str, *, failed: bool = False) -> HTMLResponse:
    error = '<p class="error" role="alert">设置未通过，请核对信息或联系管理员重新授权。</p>' if failed else ''
    return page("设置账号", f'''
        <section class="panel login-panel" aria-labelledby="headline">
          <h1 id="headline">设置账号</h1>
          <p class="muted">用管理员交给你的设置码，录入你自己的验证器信息。</p>
          {error}
          <form method="post" action="/setup" autocomplete="off">
            {csrf_field(csrf)}
            <label>账号<input name="username" autocomplete="username" maxlength="32" required></label>
            <label>设置码<input type="password" name="setup_code" maxlength="43" required></label>
            <label>密码<input type="password" name="password" minlength="12" maxlength="128" required><small>首次设置请填写新密码，重绑请使用现有密码。</small></label>
            <label>验证器密钥<input type="password" name="seed" maxlength="40" required><small>填入你已添加到验证器的 32 位 Base32 密钥。</small></label>
            <label>当前动态验证码<input name="code" inputmode="numeric" pattern="[0-9]{{6}}" maxlength="6" required></label>
            <button type="submit">保存验证器</button>
          </form>
          <p class="setup-link"><a href="/login">返回登录</a></p>
        </section>
    ''', login=True, status=401 if failed else 200)


def setup_done_page() -> HTMLResponse:
    return page("设置完成", '''
        <section class="panel login-panel">
          <h1>设置完成</h1>
          <p>请使用验证器中的下一组验证码登录。</p>
          <p><a href="/login">前往登录</a></p>
        </section>
    ''', login=True)


def select_options(labels, selected: str = "") -> str:
    return ''.join(f'<option value="{value}"{" selected" if value == selected else ""}>{label}</option>'
                   for value, label in labels.items())


def account_controls(session: Session, account: AccountStatus) -> str:
    if session.username == account.username or not account.enabled:
        return '—'
    username = escape(account.username)
    role = select_options(ROLE_LABELS, account.role)
    unlock = '<button name="action" value="unlock">解除锁定</button>' if account.locked else ''
    return f'''
        <button class="secondary" popovertarget="staff-{username}">管理</button>
        <section class="panel dialog" id="staff-{username}" popover aria-label="管理 {username}">
          <h2>管理 <code>{username}</code></h2>
          <form method="post" action="/admin/accounts">
            {csrf_field(session.csrf)}
            <input type="hidden" name="username" value="{username}">
            <label>角色<select name="role">{role}</select></label>
            <div class="buttons">
              <button name="action" value="change_role">保存角色</button>
              {unlock}
              <button name="action" value="rebind">授权重绑</button>
              <button class="danger" name="action" value="disable">停用账号</button>
            </div>
          </form>
        </section>
    '''


def accounts_page(
    session: Session, accounts: tuple[AccountStatus, ...], *,
    setup_code: str | None = None, saved: bool = False, rejected: bool = False,
) -> HTMLResponse:
    notice = ''
    if setup_code is not None:
        notice = (f'<section class="notice" role="status"><p>请将一次性设置码仅交给该员工。15 分钟内有效，离开此页后无法再次查看。</p>'
                  f'<p><code>{escape(setup_code)}</code></p></section>')
    elif saved:
        notice = '<p class="notice" role="status">账号状态已更新。</p>'
    elif rejected:
        notice = '<p class="error" role="alert">无法更新账号，请核对账号、角色或当前状态。</p>'
    rows = []
    for account in accounts:
        status = ('已停用' if not account.enabled else '已锁定' if account.locked
                  else '待绑定' if account.setup_pending else '正常')
        rows.append(f'<tr><td><code>{escape(account.username)}</code></td><td>{ROLE_LABELS[account.role]}</td>'
                    f'<td>{status}</td><td>{account_controls(session, account)}</td></tr>')
    return page("账号管理", f'''
        <div class="page-heading">
          <h1>账号管理</h1>
          <button popovertarget="new-staff">创建账号</button>
        </div>
        {notice}
        <section class="panel dialog" id="new-staff" popover aria-label="创建工作人员账号">
          <h2>创建工作人员账号</h2>
          <form method="post" action="/admin/accounts" autocomplete="off">
            {csrf_field(session.csrf)}
            <label>账号<input name="username" pattern="[a-z][a-z0-9_\\-]{{2,31}}" maxlength="32" required><small>3 至 32 位，小写字母开头，可用小写字母、数字、下划线和连字符。</small></label>
            <label>角色<select name="role" required>{select_options(ROLE_LABELS)}</select></label>
            <button name="action" value="create">生成设置码</button>
          </form>
        </section>
        <section class="panel table-panel" aria-label="工作人员账号">
          <table>
            <thead><tr><th scope="col">账号</th><th scope="col">角色</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </section>
    ''', session=session, status=400 if rejected else 201 if setup_code is not None else 200)


def audit_page(session: Session, events: tuple[AuditEvent, ...], filters: dict[str, str]) -> HTMLResponse:
    rows = []
    for event in sorted(reversed(events), key=lambda item: item.timestamp, reverse=True):
        timestamp = datetime.fromtimestamp(event.timestamp, UTC).strftime("%Y-%m-%d %H:%M:%S")
        actor = escape(event.actor) if event.actor is not None else '—'
        case_id = escape(event.case_id) if event.case_id is not None else '—'
        target = escape(event.staff_target) if event.staff_target is not None else '—'
        rows.append(f'<tr><td><time>{timestamp}</time></td><td>{ACTION_LABELS[event.action]}</td><td>{actor}</td>'
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
