"""National synthetic v2. Local-only independent seeds; no acceptance-question copying."""
import argparse
from collections import Counter
from pathlib import Path

from cj_api.real_services import NATIONAL_TOOLS, TOOLS

from .convert import HERE, ROOT, VERSION, canonical, digest, sha, validate
from .samples import message, row
from .teacher import Case, FakeTeacher, FakeTools, ProducerProfile, execution, run_fake

DATA_VERSION = 'G2C-national-synthetic.2'
PROMPT_VERSION = 'F-national-public-scripts.2'
PROFILE = ProducerProfile('F789-national-fake.2', PROMPT_VERSION, 'G2C-teacher-handoff.2', DATA_VERSION,
                          ('tooling/datasets/national.py', 'tooling/datasets/national-seeds.v2.jsonl',
                           'tooling/datasets/national-guide.v2.md', 'tooling/datasets/test_national.py'))

# Distinct travel contexts, not POI facts, bookings or copies of C's planning/edit/undo test.
CITIES = (
    ('shanghai', '上海', 'Shanghai', '展览和有休息点的步行', 'exhibitions and walks with rest stops', '少步行', 'less walking'),
    ('chengdu', '成都', 'Chengdu', '茶馆和清淡饮食', 'teahouses and mild food', '少辣', 'mild food'),
    ('xian', '西安', "Xi'an", '历史主题和室内休息', 'history and indoor breaks', '慢节奏', 'a gentle pace'),
    ('hangzhou', '杭州', 'Hangzhou', '绿地和安静休息', 'green spaces and quiet breaks', '安静', 'quiet breaks'),
    ('guangzhou', '广州', 'Guangzhou', '饮食主题和雨天室内选择', 'food themes and indoor options for rain', '无海鲜', 'no seafood'),
    ('guilin', '桂林', 'Guilin', '山水主题和短步行', 'scenery themes and short walks', '短步行', 'short walks'),
    ('chongqing', '重庆', 'Chongqing', '城市景观和体力分配', 'city views and pacing physical effort', '多休息', 'frequent breaks'),
    ('shenzhen', '深圳', 'Shenzhen', '公共空间和室内休息', 'public spaces and indoor breaks', '室内休息', 'indoor breaks'),
)
BEHAVIORS = ('direct_answer', 'clarification', 'correction', 'cancellation', 'tool_failure')


def _turns(city, behavior, language, rewrite):
    _, zh, en, topic_zh, topic_en, keep_zh, keep_en = city
    if language == 'zh':
        if behavior == 'direct_answer':
            question = f'在{zh}讨论{topic_zh}，我应该提前考虑哪些个人准备？不用查地点。'
            if rewrite:
                question = f'关于{zh}的{topic_zh}，先聊出门准备，不查任何地点可以吗？'
            return [('user', question), ('assistant', f'可以先考虑体力、舒适鞋服和休息需求；具体地点、天气、营业与预约情况尚未核实。这里仅讨论{zh}的个人准备。')]
        if behavior == 'clarification':
            question = f'我打算2027年3月14日在{zh}开始旅行，偏好{topic_zh}，按我的停留时长讨论分配；还没说玩几天。'
            if rewrite:
                question = f'{zh}旅行的开始日期是2027年3月14日，想侧重{topic_zh}；请先问还缺的停留时长。'
            return [('user', question), ('assistant', '你预计停留几天？'),
                    ('user', '四天。酒店名称和位置仍未知，不要替我预订。'),
                    ('assistant', f'保留{zh}、2027年3月14日开始和四天；酒店未知，不预订。可以先讨论每天的主题，开放与预约情况仍待核实。')]
        if behavior == 'correction':
            question = f'先聊{zh}两天的{topic_zh}，保留{keep_zh}，日期不知道。'
            change = f'改成四天，{zh}和{keep_zh}都不变，日期仍不知道。'
            if rewrite:
                question = f'在{zh}想讨论{topic_zh}，暂定两天，要求{keep_zh}，还没有出发日期。'
                change = f'只有时长要改：四天。城市、{keep_zh}和未知日期保持原样。'
            return [('user', question), ('assistant', '先按给定城市、两天和原偏好讨论，不推定日期或保存。'),
                    ('user', change), ('assistant', f'更新为{zh}四天，保留{keep_zh}和未知日期；这里只是讨论，没有保存或预订。')]
        if behavior == 'cancellation':
            question = f'我想查{zh}一个地点，先等等我给名称。'
            if rewrite:
                question = f'{zh}有个地点想查询，我还没有提供名称。'
            return [('user', question), ('assistant', '请提供名称；目前没有发起查询。'),
                    ('user', '取消这个查询，不再提供名称，也不要查。'),
                    ('assistant', f'已停止这项{zh}查询，没有发起地点工具，也没有保存或预订。')]
    else:
        if behavior == 'direct_answer':
            question = f'Before discussing {topic_en} in {en}, what personal preparation should I consider? Do not look up places.'
            if rewrite:
                question = f'Can we discuss preparation for {topic_en} in {en} without any place lookup?'
            return [('user', question), ('assistant', f'Consider your energy, comfortable clothing and shoes, and rest needs for {en}. Specific places, weather, opening times and bookings have not been verified.')]
        if behavior == 'clarification':
            question = f'I plan to start in {en} on March 14, 2027, focusing on {topic_en}. Discuss how to allocate my stay; I have not given its length.'
            if rewrite:
                question = f'March 14, 2027 is my start date in {en}, with an interest in {topic_en}. Ask only for the missing length of stay.'
            return [('user', question), ('assistant', 'How many days will you stay?'),
                    ('user', 'Four days. My hotel name and location are still unknown. Do not book anything.'),
                    ('assistant', f'Keeping {en}, a March 14, 2027 start, and four days. The hotel is unknown and nothing is booked. We can discuss daily themes; availability is unverified.')]
        if behavior == 'correction':
            question = f'Discuss two days of {topic_en} in {en}, keeping {keep_en}. I do not know my dates.'
            change = f'Make it four days. Keep {en}, {keep_en}, and the unknown dates.'
            if rewrite:
                question = f'For {en}, I want {topic_en} over two days with {keep_en}; dates are unknown.'
                change = f'Change only the duration to four days. Keep the city, {keep_en}, and unknown dates.'
            return [('user', question), ('assistant', 'We can discuss the stated city, two days and your preference without inventing dates or saving.'),
                    ('user', change), ('assistant', f'Updated to four days in {en}, keeping {keep_en} and unknown dates. This is discussion; nothing has been saved or booked.')]
        if behavior == 'cancellation':
            question = f'I may ask you to look up a place in {en}; wait for its name.'
            if rewrite:
                question = f'There is a place in {en} I might want checked, but I have not supplied its name.'
            return [('user', question), ('assistant', 'Please supply the name. No lookup has started.'),
                    ('user', 'Cancel this lookup. Do not search.'),
                    ('assistant', f'The {en} lookup is stopped. No place tool was dispatched and nothing was saved or booked.')]
    raise ValueError('behavior_has_no_discussion_script')


def _tool_row(city, language, variant, cancelled=False):
    slug, zh, en, *_ = city
    behavior = 'cancellation' if cancelled else 'tool_failure'
    task = f'f-national-v2/{slug}/{behavior}' + ('/run-cancel' if cancelled else '')
    sample = task + '/' + language + '/' + str(variant)
    name = zh if language == 'zh' else en
    provider_id = 'SYNTH_NATIONAL_V2_' + slug.upper()
    text = (f'这是{name}的合成地点测试，用户明确提供假编号{provider_id}，请只读查询详情。' if language == 'zh' else
            f'This is a synthetic place test in {name}. I explicitly provide fake ID {provider_id}; read its details only.')
    if variant:
        text = (f'仅作{name}合成测试：我给出的假地点ID是{provider_id}；查询其详情，不作写入。' if language == 'zh' else
                f'For a synthetic {name} test only, look up the details of fake place ID {provider_id} supplied by me; do not write anything.')
    result = row(task, language, behavior, [], 'cancelled' if cancelled else 'failed')
    result.update(sample_id=sample, trip_family=f'f-national-v2/{slug}/{behavior}', rewrite_family=task)
    result['run'].update(attempt_id='synthetic-attempt/' + sample, run_id='synthetic-run/' + sample)
    call = dict(id='cn_v2_' + slug + '_' + language + '_' + str(variant), type='function',
                function=dict(name='place_detail', arguments=canonical(dict(provider_id=provider_id))))
    result['messages'] = [message('user', text), dict(role='assistant', content=None, tool_calls=[call])]
    item = execution(result, call, 0, 0)
    item['status'] = item['evidence']['status'] = 'not_started' if cancelled else 'failed'
    item['error_code'] = None if cancelled else 'ProviderFailed'
    result['executions'] = [item]
    return result


def seeds():
    result = []
    for city in CITIES:
        slug = city[0]
        for behavior in BEHAVIORS:
            task = f'f-national-v2/{slug}/{behavior}'
            for language in ('zh', 'en'):
                for variant in (0, 1):
                    if behavior == 'tool_failure':
                        item = _tool_row(city, language, variant)
                    else:
                        item = row(task, language, behavior,
                                   [message(role, text) for role, text in _turns(city, behavior, language, variant)])
                        item.update(sample_id=task + '/' + language + '/' + str(variant), trip_family=task, rewrite_family=task)
                    item['source'] = dict(kind='synthetic_fixture' if behavior == 'tool_failure' else 'synthetic_manual',
                                          source_id=DATA_VERSION + '/' + item['sample_id'], revision=DATA_VERSION)
                    item['versions'].update(model=None, prompt=PROMPT_VERSION, adapter=None)
                    validate(item)
                    result.append(item)
        for language in ('zh', 'en'):
            item = _tool_row(city, language, 0, cancelled=True)
            item['source'] = dict(kind='synthetic_fixture', source_id=DATA_VERSION + '/' + item['sample_id'], revision=DATA_VERSION)
            item['versions'].update(prompt=PROMPT_VERSION)
            validate(item)
            result.append(item)
    return result


def catalog(rows):
    return dict(version='F-national-seed-catalog.2', data_version=DATA_VERSION, record_schema=VERSION,
                purpose='public_synthetic_fixture_not_real_teacher_input',
                cities=[dict(id=c[0], zh=c[1], en=c[2]) for c in CITIES],
                samples={r['sample_id']: dict(city=r['trip_family'].split('/')[1], task_id=r['task_id'],
                    trip_family=r['trip_family'], rewrite_family=r['rewrite_family'], language=r['language'],
                    behavior=r['scenario'], fixture_sha256=digest(r)) for r in rows})


def run_national(output, batch):
    rows = seeds()
    # No params/identity remapping: the one shared detail shape is byte-identical in B's profiles.
    legacy = next(t for t in TOOLS if t['function']['name'] == 'place_detail')
    national = next(t for t in NATIONAL_TOOLS if t['function']['name'] == 'place_detail')
    if canonical(legacy) != canonical(national):
        raise ValueError('shared_detail_profile_changed')
    inputs = dict(version='F-national-task-inputs.2', data_version=DATA_VERSION,
                  eligibility='not_authorized_real_task_set',
                  tasks={r['sample_id']: dict(city=r['trip_family'].split('/')[1], language=r['language'],
                      trip_family=r['trip_family'], user_turns=[m['content'] for m in r['messages'] if m['role'] == 'user']) for r in rows})
    count = Counter(r['trip_family'].split('/')[1] + '/' + r['language'] + '/' + r['scenario'] for r in rows)
    coverage = dict(version='F-national-coverage.2', data_version=DATA_VERSION, seed_rows=len(rows),
                    families=len({r['trip_family'] for r in rows}), city_language_behavior=dict(count),
                    tool_scope='shared-place_detail-failure-or-not-started-only',
                    shared_tool_sha256=digest(legacy), successful_national_tool_results='UNRUN',
                    real_requests=0, quality_status='UNRUN', release_status='UNRUN', training_status='UNRUN')
    reference = dict(version='F-national-coverage-reference.2',
                     path='eval/lio_national_cases.v1.json',
                     sha256=sha((ROOT / 'eval/lio_national_cases.v1.json').read_bytes()),
                     usage='public_coverage_reference_only_not_seed_or_teacher_prompt', copied_questions_or_answers=False)
    return run_fake(output, batch, [Case(r['sample_id'], r) for r in rows], FakeTeacher(), FakeTools(), profile=PROFILE,
                    extra_artifacts={'national-catalog.v2.json': catalog(rows), 'national-inputs.v2.json': inputs,
                                     'national-coverage.v2.json': coverage, 'national-reference.v2.json': reference})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-seeds', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--batch-id', default='f789-national-v2')
    args = parser.parse_args(argv)
    if args.write_seeds:
        (HERE / 'national-seeds.v2.jsonl').write_text(''.join(canonical(r) + '\n' for r in seeds()))
        return 0
    if args.output is None:
        parser.error('--output required for Fake handoff')
    report = run_national(args.output, args.batch_id)
    print(canonical(report))
    return 0 if report['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
