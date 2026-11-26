"""Staff operations HTML. This module does not import the demo data source."""

from html import escape

from . import pages
from .operations import Lead, ServiceRequest
from .store import Session


STATES = {
    "user_confirmed": "客户已确认", "submitted": "已提交", "accepted": "已接单", "quoted": "已报价",
    "arranged": "双方已确认", "in_progress": "已到场 · 进行中", "completed": "已完成",
    "user_cancelled": "已取消", "unavailable": "无法提供", "outcome_unknown": "结果未知",
}
ACTIONS = {
    "accepted": "接单", "quoted": "报价", "arranged": "登记双方确认", "in_progress": "登记到场",
    "completed": "登记完成", "user_cancelled": "登记取消", "unavailable": "标记无法提供",
    "outcome_unknown": "标记结果未知",
}
LEADS = {"pending": "待联系", "contacted": "已联系", "converted": "已转为服务", "closed": "已关闭"}
LEAD_ACTIONS = {"contacted": "标记已联系", "converted": "转为服务", "closed": "关闭"}


def heading(title: str, active: str) -> str:
    return f'''
      <div class="page-heading"><h1>{title}</h1>{pages.DEMO_BADGE}</div>
      <nav class="operations-nav" aria-label="运营台导航">
        <a href="/operations" {'aria-current="page"' if active == 'requests' else ''}>服务请求</a>
        <a href="/operations/leads" {'aria-current="page"' if active == 'leads' else ''}>官网线索</a>
      </nav>
    '''


def request_list(session: Session, requests: tuple[ServiceRequest, ...]):
    rows = []
    for item in requests:
        details = item.details
        status_class = " warning" if item.state == "outcome_unknown" else ""
        rows.append(f'<tr><td><a href="/operations/requests/{escape(item.request_id)}"><code>{escape(item.request_id)}</code></a></td>'
                    f'<td>{escape(details.customer_name)}</td><td>广州中英商务陪同</td>'
                    f'<td>{escape(details.service_date)}</td><td><span class="operation-status{status_class}">'
                    f'{STATES[item.state]}</span></td></tr>')
    return pages.page("服务请求", heading("服务请求", "requests") + f'''
      <section class="panel table-panel" aria-label="服务请求">
        <table><thead><tr><th>请求编号</th><th>客户称呼</th><th>服务类型</th><th>服务日期</th><th>状态</th></tr></thead>
        <tbody>{''.join(rows)}</tbody></table>
      </section>
    ''', session=session)


def request_detail(session: Session, item: ServiceRequest):
    d = item.details
    times = {"half_day_am": "上午半天", "half_day_pm": "下午半天", "full_day": "全天"}
    fields = ''.join(f'<div><dt>{label}</dt><dd>{escape(value)}</dd></div>' for label, value in (
        ("请求编号", item.request_id), ("服务类型", "广州中英商务陪同"),
        ("状态", STATES[item.state]), ("服务日期", d.service_date), ("时段", times[d.time_window]),
        ("客户称呼", d.customer_name), ("联系号码", d.contact_phone), ("会面地点", d.venue),
        ("会面目的", d.meeting_purpose),
    ))
    quote = ''
    if item.quote is not None:
        units, minor = divmod(item.quote.amount_minor, 100)
        quote = f'<p>报价 ¥{units:,}.{minor:02d} · App 外付款</p>'
    service = item.human_service
    arrival = ''
    if service.escort_display_name and service.arrival:
        arrival = (f'<p>陪同称呼：{escape(service.escort_display_name)} · '
                   f'预计到场：{escape(service.arrival.local_time)} · {escape(service.arrival.place)}</p>')
    public_history = ''.join(
        f'<li>{STATES[row.to]} · <time>{row.at:%m-%d %H:%M} UTC</time></li>' for row in item.history)
    staff_history = ''.join(f'<li><strong>{STATES[row.to]}</strong><p>{escape(row.evidence)}</p>'
                            f'<code>{escape(row.evidence_kind)} · {escape(row.evidence_ref)}</code></li>'
                            for row in reversed(item.history))
    if item.actions:
        options = pages.select_options({state: ACTIONS[state] for state in item.actions})
        quote_input = ('<label>新增报价（人民币分，仅报价时填写）<input name="amount" inputmode="numeric" maxlength="9"></label>'
                       if "quoted" in item.actions else '<input type="hidden" name="amount" value="">')
        action = f'''
          <form method="post" action="/operations/requests/{escape(item.request_id)}">
            {pages.csrf_field(session.csrf)}
            <input type="hidden" name="seq" value="{len(item.history)}">
            <label>操作<select name="target">{options}</select></label>
            {quote_input}
            <label>演示凭据<textarea name="evidence" required maxlength="300" rows="3"></textarea></label>
            <button type="submit">保存演示操作</button>
          </form>
        '''
    else:
        action = '<p class="muted">此请求已结束。</p>'
    return pages.page("服务请求详情", heading("服务请求详情", "requests") + f'''
      <div class="operations-detail">
        <section class="panel" aria-label="对客字段"><h2>对客字段</h2>
          <dl class="operation-fields">{fields}</dl>{quote}{arrival}
          <h3>对客状态历史</h3><ol class="operation-history">{public_history}</ol>
        </section>
        <section class="panel" aria-label="员工专用字段"><h2>员工专用</h2>
          {action}<h3>凭据记录</h3><ol class="operation-history">{staff_history}</ol>
        </section>
      </div>
    ''', session=session)


def lead_list(session: Session, leads: tuple[Lead, ...]):
    rows = []
    for lead in leads:
        buttons = ''.join(f'<button class="secondary" name="target" value="{target}">{LEAD_ACTIONS[target]}</button>'
                          for target in lead.actions)
        action = (f'<form class="buttons" method="post" action="/operations/leads/{escape(lead.client_request_id)}">'
                  f'{pages.csrf_field(session.csrf)}{buttons}</form>') if buttons else '—'
        rows.append(f'<tr><td><code>{escape(lead.client_request_id)}</code></td><td>{escape(lead.details.customer_name)}</td>'
                    f'<td>{escape(lead.details.contact_phone)}</td><td>{LEADS[lead.state]}</td><td>{action}</td></tr>')
    return pages.page("官网线索", heading("官网线索", "leads") + f'''
      <section class="panel table-panel" aria-label="官网线索待联系">
        <table><thead><tr><th>线索编号</th><th>称呼</th><th>演示号码</th><th>跟进状态</th><th>操作</th></tr></thead>
        <tbody>{''.join(rows)}</tbody></table>
      </section>
    ''', session=session)
