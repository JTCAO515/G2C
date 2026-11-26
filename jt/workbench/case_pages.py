"""Chinese case list and detail using JT1 playbook execution records."""

from html import escape

from fastapi.responses import HTMLResponse

from jt.common import CaseExecution

from . import pages
from .queue_pages import severity_label
from .store import Session


PLAYBOOK_LABELS = {
    "p0_assistance": "紧急协助",
    "document_loss": "护照丢失",
    "flight_change": "航班变动",
    "ai_failure": "助手反复失败",
}
STEP_LABELS = {
    "prepare_emergency_guidance": "准备演练指引",
    "verify_assistance": "人工核实协助",
    "draft_assistance_summary": "拟定协助摘要",
    "prepare_replacement_checklist": "准备补办清单",
    "verify_document_situation": "人工核实证件情况",
    "draft_document_guidance": "拟定证件补办指引",
    "summarize_flight_change": "整理航班变动",
    "draft_itinerary_change": "拟定行程变更草稿",
    "simulate_paid_rebooking": "模拟付费改订",
    "summarize_repeated_failure": "整理反复失败情况",
    "verify_unresolved_request": "人工核实未解决请求",
    "draft_recovery_summary": "拟定恢复摘要",
}
MODE_LABELS = {"ai_auto": "自动演练", "ai_draft_human_confirm": "人工确认草稿", "human_only": "人工步骤"}
CASE_STATUS_LABELS = {"open": "待处理", "in_progress": "处理中", "closed": "已关闭"}


def case_list(session: Session, records: tuple[tuple[CaseExecution, bool], ...]) -> HTMLResponse:
    rows = []
    for record, owned in records:
        case = record.case
        heading = escape(PLAYBOOK_LABELS.get(case.playbook_id, case.playbook_id))
        link = f'<a href="/cases/{case.case_id}">查看案件</a>'
        if not owned:
            link = (f'<form method="post" action="/cases/{case.case_id}/claim">'
                    f'{pages.csrf_field(session.csrf)}<button type="submit">认领</button></form>')
        rows.append(f'<tr><td>{severity_label(case.severity)}</td><td>{heading}</td><td><code>{case.case_id}</code></td>'
                    f'<td>{CASE_STATUS_LABELS[case.status]}</td><td>{link}</td></tr>')
    content = ''.join(rows) or '<tr><td colspan="5">暂无可用演练案件。</td></tr>'
    return pages.page("演练案件", f'''
        <div class="page-heading"><h1>演练案件</h1></div>
        <section class="panel table-panel" aria-label="演练案件">
          <table>
            <thead><tr><th scope="col">级别</th><th scope="col">处理流程</th><th scope="col">案件编号</th>
              <th scope="col">状态</th><th scope="col">操作</th></tr></thead>
            <tbody>{content}</tbody>
          </table>
        </section>
    ''', session=session)


def case_detail(session: Session, execution: CaseExecution, *, reason: str | None = None) -> HTMLResponse:
    case = execution.case
    title = escape(PLAYBOOK_LABELS.get(case.playbook_id, case.playbook_id))
    items = []
    for position, step in enumerate(case.steps):
        label = escape(STEP_LABELS.get(step.step_id, step.step_id))
        completed = position < execution.step_index
        active = position == execution.step_index
        attrs = ' aria-current="step"' if active else ''
        state = '已完成' if completed else '当前步骤' if active else '未开始'
        items.append(f'<li{attrs}><strong>{label}</strong><span>{MODE_LABELS[step.mode]} · {state}</span></li>')
    notice = ''
    if reason is not None:
        notice = f'<p class="error" role="alert">{pages.CASE_DENIAL_LABELS.get(reason, "当前操作无法执行。")}</p>'

    action_panel = '<p>此演练案件已结束。</p>'
    step = execution.active_step
    if step is not None:
        label = escape(STEP_LABELS.get(step.step_id, step.step_id))
        consent = ''
        gated = step.requires_customer_confirmation and not execution.customer_consent_recorded
        if step.requires_customer_confirmation:
            consent = ('本步骤仍需客户同意。员工确认草稿不能代替客户同意。'
                       if gated else '本步骤已收到独立客户同意。')
            consent = f'<p class="case-consent">{consent}</p>'
        unavailable = ' disabled' if gated else ''
        if execution.draft is not None:
            draft = f'<blockquote>{escape(execution.draft)}</blockquote>'
            buttons = (f'<button name="action" value="confirm"{unavailable}>确认草稿</button>'
                       '<button class="secondary" name="action" value="reject">驳回草稿</button>')
        elif step.mode == "ai_draft_human_confirm":
            draft = '<p class="muted">生成后，草稿将在此处供人工复核。</p>'
            buttons = '<button name="action" value="advance">生成合成草稿</button>'
        else:
            draft = ''
            buttons = f'<button name="action" value="advance"{unavailable}>完成并推进</button>'
        action_panel = f'''
            <h2>{label}</h2>
            <p class="muted">{MODE_LABELS[step.mode]}</p>
            {draft}{consent}
            <form method="post" action="/cases/{case.case_id}/action">
              {pages.csrf_field(session.csrf)}
              <input type="hidden" name="revision" value="{execution.revision}">
              <div class="buttons">{buttons}</div>
            </form>
        '''
    return pages.page("案件详情", f'''
        <a href="/cases" class="case-back">返回演练案件</a>
        <div class="page-heading case-heading">
          <div><h1>{title}</h1><p class="muted">案件编号 <code>{case.case_id}</code></p></div>
          <div>{severity_label(case.severity)} <span>{CASE_STATUS_LABELS[case.status]}</span></div>
        </div>
        {notice}
        <div class="case-layout">
          <section class="panel" aria-label="处理流程">
            <h2>处理流程</h2>
            <p class="muted">版本 <code>{escape(case.playbook_version)}</code></p>
            <ol class="case-steps">{''.join(items)}</ol>
          </section>
          <section class="panel" aria-label="当前动作">{action_panel}</section>
        </div>
    ''', session=session, status=409 if reason else 200)
