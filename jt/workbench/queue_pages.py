"""Chinese desktop queue and its deliberately narrow view of signal evidence."""

import base64
import hashlib
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import urlencode

from fastapi.responses import HTMLResponse

from . import pages
from .queue import BEIJING, QueueItem, display_text
from .store import Role, Session


TYPE_LABELS = {
    "safety": "人身安全",
    "illness": "身体不适",
    "document_loss": "证件丢失",
    "payment_issue": "支付异常",
    "itinerary_disruption": "行程中断",
    "change_request": "变更请求",
    "ai_failure_loop": "助手反复失败",
    "complaint": "投诉反馈",
}
STATUS_LABELS = {"pending": "待复核", "reviewed": "已复核"}
ALERT_SCRIPT = Path(__file__).with_name("alerts.js").read_text(encoding="utf-8")
ALERT_HASH = base64.b64encode(hashlib.sha256(ALERT_SCRIPT.encode()).digest()).decode()
QUEUE_CSP = f"{pages.CSP}; script-src 'sha256-{ALERT_HASH}'; connect-src 'self'"


def local_time(value: datetime) -> str:
    return value.astimezone(BEIJING).strftime("%m-%d %H:%M")


def visible_text(value: str) -> str:
    return escape(display_text(value))


def signal_url(item: QueueItem, signal_type: str, status: str) -> str:
    query = {"signal": item.reference}
    if signal_type:
        query["type"] = signal_type
    if status:
        query["status"] = status
    return escape(f"/queue?{urlencode(query)}", quote=True)


def severity_label(value: str) -> str:
    return f'<span class="severity severity-{value.lower()}">{value}</span>'


def queue_rows(items: tuple[QueueItem, ...], selected: QueueItem | None, signal_type: str, status: str) -> str:
    rows = []
    for item in items:
        signal = item.signal
        selected_link = ' aria-current="page"' if selected and item.reference == selected.reference else ''
        case = f'<code>{escape(item.case_id)}</code>' if item.case_id else '未建单'
        rows.append(f'''
            <a class="queue-item" href="{signal_url(item, signal_type, status)}"{selected_link}>
              <span class="queue-item-head">{severity_label(signal.severity)}<strong>{TYPE_LABELS[signal.signal_type]}</strong><span class="queue-item-status">{STATUS_LABELS[item.status]}</span></span>
              <span class="queue-item-meta"><span>截止 {local_time(item.due_at)}</span><span>{case}</span></span>
            </a>
        ''')
    return ''.join(rows) or '<p class="queue-empty">当前筛选下没有信号。</p>'


def review_form(session: Session, item: QueueItem) -> str:
    severity_options = pages.select_options({f"P{i}": f"P{i}" for i in range(5)})
    return f'''
        <form class="review-form" method="post" action="/queue/review" aria-label="复核标注">
          {pages.csrf_field(session.csrf)}
          <input type="hidden" name="signal" value="{item.reference}">
          <div class="review-fields">
            <label>真实级别<select name="actual_severity"><option value="">请选择</option>{severity_options}</select></label>
            <label>误报<select name="false_positive"><option value="0">否</option><option value="1">是</option></select></label>
            <label>漏报<select name="missed"><option value="0">否</option><option value="1">是</option></select></label>
          </div>
          <label>备注<textarea name="note" rows="3" maxlength="500"></textarea></label>
          <p class="muted review-help">误报时留空真实级别，其余情况请选择真实级别。</p>
          <button type="submit">保存标注</button>
        </form>
    '''


def detail_panel(session: Session, item: QueueItem | None, case_access: str | None = None) -> str:
    if item is None:
        return '<h2>信号详情</h2><p class="muted">从队列选择一条信号。</p>'
    signal = item.signal
    fragments = ''.join(f'<blockquote>{visible_text(fragment)}</blockquote>' for fragment in signal.redacted_fragments)
    rule_hits = ''.join(f'<li><code>{visible_text(hit)}</code></li>' for hit in signal.rule_hits)
    models = []
    for observation in signal.model_outputs:
        output = observation.output
        label = (f'{output.severity} · {TYPE_LABELS[output.signal_type]}'
                 if output.signal_type else '未建议信号')
        models.append(f'<li><code>{visible_text(observation.model_version)}</code><span>{label}</span><strong>{output.confidence:.1%}</strong></li>')
    case = f'<code>{escape(item.case_id)}</code>' if item.case_id else '未建单'
    if case_access == "owned":
        case += f' · <a href="/cases/{escape(item.case_id)}">查看案件</a>'
    elif case_access == "unclaimed":
        case += (f'<form method="post" action="/cases/{escape(item.case_id)}/claim">'
                 f'{pages.csrf_field(session.csrf)}<button type="submit">认领并查看案件</button></form>')
    review_section = ''
    if session.role == Role.REVIEWER:
        history = ''.join(f'''
          <li><strong>{review.actual_severity or '误报'}</strong> · {escape(review.actor)} · {local_time(review.recorded_at)}
            {' · 漏报' if review.missed else ''}<p>{visible_text(review.note)}</p>
          </li>''' for review in reversed(item.reviews))
        saved_reviews = f'<h3>标注历史</h3><ul class="review-history">{history}</ul>' if history else ''
        review_section = f'<section class="queue-detail-section"><h3>复核标注</h3>{review_form(session, item)}{saved_reviews}</section>'
    return f'''
        <h2>信号详情</h2>
        <div class="detail-title">{severity_label(signal.severity)}<strong>{TYPE_LABELS[signal.signal_type]}</strong></div>
        <dl class="detail-facts">
          <div><dt>发现时间</dt><dd>{local_time(signal.detected_at)}</dd></div>
          <div><dt>响应截止</dt><dd>{local_time(item.due_at)}</dd></div>
          <div><dt>案件</dt><dd>{case}</dd></div>
        </dl>
        <section class="queue-detail-section"><h3>脱敏片段</h3>{fragments or '<p class="muted">暂无片段</p>'}</section>
        <section class="queue-detail-section detail-evidence">
          <div><h3>规则命中</h3>{f'<ul class="rule-hits">{rule_hits}</ul>' if rule_hits else '<p class="muted">无</p>'}</div>
          <div><h3>模型输出</h3>{f'<ul class="model-evidence">{"".join(models)}</ul>' if models else '<p class="muted">无模型输出</p>'}</div>
        </section>
        <dl class="detail-facts versions">
          <div><dt>信号版本</dt><dd><code>{signal.schema_version}</code></dd></div>
          <div><dt>规则版本</dt><dd><code>{visible_text(signal.rules_version)}</code></dd></div>
          <div><dt>脱敏版本</dt><dd><code>{visible_text(signal.redaction_version)}</code></dd></div>
        </dl>
        {review_section}
    '''


def queue_page(
    session: Session, items: tuple[QueueItem, ...], selected: QueueItem | None,
    *, signal_type: str, status: str, alerts: tuple[int, int], invalid_review: bool = False, case_access: str | None = None,
) -> HTMLResponse:
    count, revision = alerts
    urgent = ' urgent' if count else ''
    export = '<a class="export-link" href="/queue/export">导出评测样本</a>' if session.role == Role.REVIEWER else ''
    error = '<p class="error" role="alert">请核对真实级别、误报、漏报和备注。备注最多 500 字。</p>' if invalid_review else ''
    response = pages.page("待办队列", f'''
        <div class="page-heading"><h1>待办队列</h1><div>{pages.DEMO_BADGE} {export}</div></div>
        <section class="queue-alert{urgent}" data-queue-alert data-revision="{revision}" aria-live="polite">
          <div><strong>P0 待复核 <span data-alert-count>{count}</span></strong>
            <span class="alert-status" data-alert-status></span><span class="alert-status" data-alert-transport></span>
          </div>
          <button type="button" class="secondary">开启提醒</button>
        </section>
        {error}
        <div class="queue-layout">
          <aside class="panel queue-filters" aria-label="筛选信号">
            <h2>筛选</h2>
            <form method="get" action="/queue">
              <label>信号类型<select name="type"><option value="">全部类型</option>{pages.select_options(TYPE_LABELS, signal_type)}</select></label>
              <label>复核状态<select name="status"><option value="">全部状态</option>{pages.select_options(STATUS_LABELS, status)}</select></label>
              <button type="submit">应用筛选</button>
              <a class="clear-filter" href="/queue">清除</a>
            </form>
          </aside>
          <section class="panel queue-list" aria-label="信号列表">
            <div class="queue-list-heading"><h2>信号</h2><span class="muted">{len(items)} 项 · 北京时间</span></div>
            {queue_rows(items, selected, signal_type, status)}
          </section>
          <section class="panel queue-detail" aria-label="信号详情">{detail_panel(session, selected, case_access)}</section>
        </div>
    ''', session=session, script=ALERT_SCRIPT, status=400 if invalid_review else 200)
    response.headers["Content-Security-Policy"] = QUEUE_CSP
    return response
