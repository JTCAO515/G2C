import { compareFreshness } from './freshness.mjs';

const $ = id => document.getElementById(id);
const node = (tag, cls, text) => {
  const element = document.createElement(tag);
  if (cls) element.className = cls;
  if (text !== undefined) element.textContent = text;
  return element;
};
const words = {
  zh: {
    sourceLink: '查看 GitHub 事实库 ↗', heroTitle: '把旅途的疑问，交给可靠的事实。',
    heroText: '为来中国的旅行者准备。从城市交通、支付到景点预约，查阅有来源、有核对日期的实用信息。',
    recordCount: '条知识记录', recordNote: '按城市和主题浏览 · 来源可追溯', publishStatus: '最近自动发布状态',
    badgeNote: '若标识失败或不可用，请勿假定数据已同步。', retry: '重新载入', explore: 'Explore · 城市', about: 'About · 说明',
    aboutText: '数据来自公开事实库。具体安排可能临时变化，出发前请查看原始来源。', library: '旅行知识',
    footer: '每条记录附来源、适用范围和日期。失效条目停止展示正文，请重新核对来源。',
    search: '搜索城市、地点或问题…', cityLabel: '选择城市', topicsLabel: '按主题筛选',
    allCities: '全部城市', allTopics: '全部主题', results: (n, c) => `找到 ${n} 条 · ${c}`,
    empty: '没有找到匹配的条目，请试试其他关键词。', checked: '核对', expires: '失效', source: '来源',
    expired: '已到期', unknown: '待确认', due: n => `${n} 天后到期`, valid: '有效期内',
    expiredBody: '该记录已失效，正文与条件不再展示。请重新核对来源。',
    reservation: ['预约要求待确认', '需预约', '无需强制预约'], closureUnknown: '周闭待确认',
    noClosure: '无固定周闭', closure: s => `常规周${s}闭馆`, holiday: '法定节假日例外',
    max: n => `最多提前 ${n} 天预约`, min: n => `至少提前 ${n} 天预约`,
    ruleUnknown: n => `提前天数 ${n}（规则待核）`, nameText: (zh, en, qid) => `英文名称：${en}。Wikidata 编号：${qid}。`,
    loading: '正在加载发布的数据…', loadFailed: '数据载入失败；当前没有可用内容，请稍后重试。',
    version: (sha, dataSha, when) => `发布版本 ${sha} · 数据版本 ${dataSha} · 生成于 ${when}；非实时，请核对发布状态。`, previewVersion: (sha, dataSha, when) => `预览基于 ${sha} · 数据版本 ${dataSha} · 生成于 ${when}。`,
    badgeFailed: '发布状态不可用，请查看发布记录。', checking: '正在核对 main 版本…', fresh: '事实库版本与 main 一致。', stale: 'main 已更新，页面可能滞后；请查看发布状态。', freshnessUnknown: '无法核对 main，同步状态未知。', preview: '本地预览，未发布；同步状态未知。',
  },
  en: {
    sourceLink: 'View the GitHub knowledge base ↗', heroTitle: 'Better journeys start with reliable facts.',
    heroText: 'Practical information for visitors to China, from payments and transport to reservations, with sources and review dates.',
    recordCount: 'knowledge records', recordNote: 'Browse by city and topic · Sources included', publishStatus: 'Latest automatic publication',
    badgeNote: 'If the badge reports failure or is unavailable, do not assume the data is in sync.', retry: 'Reload data', explore: 'Explore · Cities', about: 'About',
    aboutText: 'These records come from a public knowledge base. Arrangements can change; check the original source before you travel.', library: 'Travel knowledge',
    footer: 'Records include sources, scope and dates. Expired text is hidden until it is reviewed.',
    search: 'Search cities, places or questions…', cityLabel: 'Select city', topicsLabel: 'Filter by topic',
    allCities: 'All cities', allTopics: 'All topics', results: (n, c) => `${n} records · ${c}`,
    empty: 'No matching records. Try another search.', checked: 'Checked', expires: 'Expires', source: 'Source',
    expired: 'Expired', unknown: 'Unknown', due: n => `Expires in ${n} days`, valid: 'Within review period',
    expiredBody: 'This record has expired. Its text and conditions are hidden until the sources are reviewed.',
    reservation: ['Reservation requirement unknown', 'Reservation required', 'No mandatory reservation'], closureUnknown: 'Weekly closure unknown',
    noClosure: 'No regular weekly closure', closure: s => `Normally closed ${s}`, holiday: 'Public holiday exception',
    max: n => `Book up to ${n} days ahead`, min: n => `Book at least ${n} days ahead`,
    ruleUnknown: n => `${n} days ahead (rule unconfirmed)`, nameText: (zh, en, qid) => `Chinese name: ${zh}. Wikidata ID: ${qid}.`,
    loading: 'Loading published data…', loadFailed: 'Could not load the data. No content is available; please try again later.',
    version: (sha, dataSha, when) => `Published ${sha} · data ${dataSha} · built ${when}; not live. Check publication status.`, previewVersion: (sha, dataSha, when) => `Preview based on ${sha} · data ${dataSha} · built ${when}.`,
    badgeFailed: 'Publication status is unavailable; check the publication history.', checking: 'Checking the main branch…', fresh: 'Knowledge base version matches main.', stale: 'Main has changed; this page may be out of date. Check publication status.', freshnessUnknown: 'Unable to check main; sync state is unknown.', preview: 'Local preview, not published; sync state is unknown.',
  },
};
const cities = {
  beijing: ['北京', 'Beijing'], chengdu: ['成都', 'Chengdu'], xian: ['西安', 'Xi’an'],
  shanghai: ['上海', 'Shanghai'], hangzhou: ['杭州', 'Hangzhou'], chongqing: ['重庆', 'Chongqing'],
  shenzhen: ['深圳', 'Shenzhen'], 'taizhou-zhejiang': ['浙江台州', 'Taizhou, Zhejiang'],
  'suzhou-anhui': ['安徽宿州', 'Suzhou, Anhui'], mainland: ['中国大陆', 'Mainland China'],
};
const topics = {
  payment: ['支付', 'Payments'], passport_booking: ['预约与购票', 'Booking & tickets'],
  transport: ['交通与高铁', 'Transport & rail'], connectivity: ['上网', 'Internet'],
  internet: ['上网', 'Internet'], emergency: ['紧急电话', 'Emergency'], visa_entry: ['签证与入境', 'Visa & entry'],
  seasonal_holiday: ['节假日', 'Holidays'], names: ['地点名称', 'Place names'],
};
let language = 'zh', city = 'all', topic = 'all', rows = [], data = null, badgeFailed = false, freshness = 'freshnessUnknown', freshnessRun = 0;
const label = pair => pair ? pair[language === 'zh' ? 0 : 1] : '';
const cityName = key => key === 'all' ? words[language].allCities : (label(cities[key]) || key);
const topicName = key => key === 'all' ? words[language].allTopics : (label(topics[key]) || key);
const recordTopic = row => row.format_version === 'visitor-name.1' ? 'names' : row.topic;

function beijingToday() {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(new Date());
  const byType = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${byType.year}-${byType.month}-${byType.day}`;
}
function recordState(row) {
  if (!row.expires_on) return [words[language].unknown, 'soon'];
  const days = Math.round((Date.parse(`${row.expires_on}T00:00:00Z`) - Date.parse(`${beijingToday()}T00:00:00Z`)) / 86400000);
  return days <= 0 ? [words[language].expired, 'expired'] : days <= 30 ? [words[language].due(days), 'soon'] : [words[language].valid, ''];
}
function recordTitle(row) {
  const subject = row.subject || row;
  if (language === 'en') return subject.name_en || subject.name_zh || topicName(recordTopic(row));
  return subject.name_zh || subject.name_en || topicName(recordTopic(row));
}
function setLanguage() {
  document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
  for (const element of document.querySelectorAll('[data-i18n]')) element.textContent = words[language][element.dataset.i18n];
  $('language').textContent = language === 'zh' ? 'EN' : '中';
  $('publish-badge').alt = language === 'zh' ? '发布状态不可用时请查看发布记录' : 'If unavailable, check the publication history';
  $('language').setAttribute('aria-label', language === 'zh' ? 'Switch to English' : '切换到中文');
  $('search').placeholder = words[language].search;
  $('search').setAttribute('aria-label', words[language].search);
  $('city-mobile').setAttribute('aria-label', words[language].cityLabel);
  $('topics').setAttribute('aria-label', words[language].topicsLabel);
  if (badgeFailed) $('badge-note').textContent = words[language].badgeFailed;
  $('freshness').textContent = words[language][freshness];
  updateVersion();
}
async function checkFreshness() {
  const run = ++freshnessRun, current = data;
  if (current.preview) { freshness = 'preview'; $('freshness').textContent = words[language][freshness]; return; }
  freshness = 'checking'; $('freshness').textContent = words[language][freshness];
  let result = 'freshnessUnknown';
  try {
    const response = await fetch('https://api.github.com/repos/JTCAO515/G2C/commits?sha=main&path=knowledge%2Fvisitor&per_page=1', {cache: 'no-store', signal: AbortSignal.timeout(8000)});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const commits = await response.json();
    result = compareFreshness(current.source_revision, commits);
  } catch { result = 'freshnessUnknown'; }
  if (run !== freshnessRun || current !== data) return;
  freshness = result; $('freshness').textContent = words[language][freshness];
}
function updateVersion() {
  if (!data) return;
  const when = new Intl.DateTimeFormat(language === 'zh' ? 'zh-CN' : 'en-GB', {dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai'}).format(new Date(data.built_at));
  $('sync').textContent = words[language][data.preview ? 'previewVersion' : 'version'](data.revision.slice(0, 8), data.data_revision.slice(0, 8), `${when} (UTC+8)`);
}
function filters() {
  const available = new Set(rows.flatMap(row => row.cities));
  $('cities').replaceChildren(); $('city-mobile').replaceChildren();
  for (const key of ['all', ...Object.keys(cities).filter(key => available.has(key))]) {
    const button = node('button', `filter${city === key ? ' active' : ''}`, cityName(key));
    button.type = 'button'; button.setAttribute('aria-pressed', String(city === key));
    button.addEventListener('click', () => { city = key; render(); }); $('cities').append(button);
    const option = node('option', '', cityName(key)); option.value = key; option.selected = city === key; $('city-mobile').append(option);
  }
  $('topics').replaceChildren();
  for (const key of ['all', ...new Set(rows.map(recordTopic))]) {
    const button = node('button', `pill${topic === key ? ' active' : ''}`, topicName(key));
    button.type = 'button'; button.setAttribute('aria-pressed', String(topic === key));
    button.addEventListener('click', () => { topic = key; render(); }); $('topics').append(button);
  }
}
function addConditions(card, row) {
  if (!row.conditions || row.topic !== 'passport_booking' || !row.subject) return;
  const t = words[language], condition = row.conditions, tags = node('div', 'conditions');
  const r = condition.reservation_required;
  tags.append(node('span', `tag${r === null ? ' unknown' : ''}`, t.reservation[r === true ? 1 : r === false ? 2 : 0]));
  const days = condition.closed_weekdays;
  if (Array.isArray(days)) {
    const names = language === 'zh' ? ['日', '一', '二', '三', '四', '五', '六'] : ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    tags.append(node('span', 'tag', days.length ? t.closure(days.map(day => names[day % 7]).join(language === 'zh' ? '、' : ', ')) : t.noClosure));
  } else tags.append(node('span', 'tag unknown', t.closureUnknown));
  if (condition.closed_weekdays_public_holiday_exception === true) tags.append(node('span', 'tag', t.holiday));
  if (condition.advance_booking_days !== null && condition.advance_booking_days !== undefined) {
    const n = condition.advance_booking_days, rule = condition.advance_booking_rule;
    tags.append(node('span', 'tag', rule === 'window_max' ? t.max(n) : rule === 'minimum_lead' ? t.min(n) : t.ruleUnknown(n)));
  }
  card.append(tags);
}
function card(row) {
  const t = words[language], element = node('article', 'card'), top = node('div', 'card-top');
  const [status, kind] = recordState(row);
  top.append(node('span', 'category', `${row.cities.map(cityName).join(' / ')} · ${topicName(recordTopic(row))}`), node('span', `status ${kind}`, status));
  element.append(top, node('h3', '', kind === 'expired' ? row.id : recordTitle(row)));
  if (kind === 'expired') element.append(node('p', 'bodytext expired-text', t.expiredBody));
  else {
    if (row.format_version === 'visitor-name.1') element.append(node('p', 'bodytext', t.nameText(row.name_zh, row.name_en, row.wikidata_qid)));
    else element.append(node('p', 'bodytext', language === 'zh' ? row.text_zh : row.text_en));
    addConditions(element, row);
  }
  const meta = node('div', 'meta');
  meta.append(node('span', '', `${t.checked} ${row.checked_on}`), node('span', '', `${t.expires} ${row.expires_on}`));
  element.append(meta);
  const links = node('div', 'links');
  for (const [index, url] of row.source_urls.entries()) {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:') continue;
    const link = node('a', '', `${t.source} ${index + 1} ↗`);
    link.href = parsed.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; links.append(link);
  }
  element.append(links); return element;
}
function render() {
  if (!data) return;
  setLanguage(); filters();
  const q = $('search').value.trim().toLocaleLowerCase();
  const list = rows.filter(row => {
    if ((city !== 'all' && !row.cities.includes(city)) || (topic !== 'all' && recordTopic(row) !== topic)) return false;
    const visible = recordState(row)[1] === 'expired' ? [row.id, row.cities, recordTopic(row)] : row;
    return !q || JSON.stringify(visible).toLocaleLowerCase().includes(q) || row.cities.some(key => (cities[key] || []).some(name => name.toLocaleLowerCase().includes(q)));
  });
  $('hero-count').textContent = rows.length;
  $('result-count').textContent = words[language].results(list.length, cityName(city));
  $('cards').replaceChildren();
  if (!list.length) $('cards').append(node('div', 'empty', words[language].empty));
  else for (const row of list) $('cards').append(card(row));
}
async function load() {
  ++freshnessRun; $('refresh').disabled = true; $('sync').textContent = words[language].loading;
  try {
    const response = await fetch('data.json', {cache: 'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    if (!Array.isArray(result.records) || !result.records.length || !/^[a-f0-9]{40}$/.test(result.revision) || !/^[a-f0-9]{40}$/.test(result.data_revision) || !/^[a-f0-9]{40}$/.test(result.source_revision) || Number.isNaN(Date.parse(result.built_at))) throw new Error('invalid published data');
    data = result; rows = result.records; $('dot').className = 'dot'; render(); void checkFreshness();
  } catch {
    data = null; rows = []; freshness = 'freshnessUnknown'; $('freshness').textContent = words[language][freshness]; $('dot').className = 'dot error'; $('sync').textContent = words[language].loadFailed;
    $('hero-count').textContent = '—'; $('result-count').textContent = '';
    $('cards').replaceChildren(node('div', 'load-error', words[language].loadFailed));
  } finally { $('refresh').disabled = false; }
}
$('publish-badge').addEventListener('error', () => { badgeFailed = true; $('publish-badge').hidden = true; $('badge-note').textContent = words[language].badgeFailed; });
$('language').addEventListener('click', () => { language = language === 'zh' ? 'en' : 'zh'; if (data) render(); else { setLanguage(); $('sync').textContent = words[language].loadFailed; } });
$('search').addEventListener('input', render);
$('city-mobile').addEventListener('change', event => { city = event.target.value; render(); });
$('refresh').addEventListener('click', load);
setLanguage(); load();
