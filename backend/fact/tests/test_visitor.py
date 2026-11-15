"""Visitor summaries are bounded local content, not synthetic/official excerpts."""
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest

from cj_fact.policy import FactFailure
from cj_fact.visitor import Query,decode_query,lookup

ROOT=Path(__file__).resolve().parents[3]
NOW=datetime(2026,11,12,4,tzinfo=timezone.utc)


def entry():
    return dict(id='visitor.fixture.payment',topic='payment',cities=['chengdu'],
        text_zh='合成测试正文，不代表真实支付指引。',text_en='Synthetic test text, not payment guidance.',
        source_urls=['https://english.www.gov.cn/synthetic-fixture'],checked_on='2026-11-11',expires_on='2026-11-13')


class VisitorFacts(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.directory=Path(self.folder.name)

    def write(self,values,name='entries.json'):
        path=self.directory/name;path.write_text(json.dumps(values,ensure_ascii=False));return path

    def read(self,city='chengdu',now=NOW):
        return json.loads(lookup(self.directory,Query('payment',city),evaluated_at=now,request_ref='original-run-tool-ref'))

    def test_first_batch_matches_topic_and_explicit_city_without_translation(self):
        for city in ('成都','510100','Chengdu'):
            raw=lookup(ROOT/'knowledge/visitor/entries',Query('payment',city),evaluated_at=NOW,request_ref='original-ref')
            result=json.loads(raw)
            self.assertEqual(result['version'],'FACT-result.2')
            self.assertEqual(result['status'],'matched')
            self.assertEqual(result['data_origin'],'maintainer_summary')
            self.assertEqual(result['request_ref'],'original-ref')
            self.assertEqual([v['id'] for v in result['entries']],['visitor.mainland.payment-options'])
            expected=json.loads((ROOT/'knowledge/visitor/entries/mainland-basics.json').read_text())[0]
            self.assertEqual(result['entries'][0],expected)
            self.assertNotIn('original_bytes',result);self.assertNotIn('original_value',result)

    def test_unknown_city_is_no_match_with_no_default(self):
        self.write([entry()])
        result=self.read('广州')
        self.assertEqual((result['status'],result['entries']),('no_match',[]))
        self.assertEqual(result['query']['city'],'广州')

    def test_expiry_at_china_midnight_omits_only_expired_entries(self):
        old=entry();old['expires_on']='2026-11-12'
        self.write([old])
        self.assertEqual(self.read(now=datetime(2026,11,11,15,59,59,tzinfo=timezone.utc))['status'],'matched')
        self.assertEqual(self.read(now=datetime(2026,11,11,16,tzinfo=timezone.utc))['entries'],[])
        fresh=entry();fresh['id']='visitor.fixture.fresh'
        self.write([old,fresh])
        self.assertEqual([v['id'] for v in self.read()['entries']],['visitor.fixture.fresh'])

    def test_invalid_entry_fails_whole_catalogue_even_when_not_matched(self):
        for mutation in ('extra','future','range','host','homepage','unknown-city','duplicate-city','blank','invalid-date'):
            bad=entry();bad['id']='visitor.fixture.bad';bad['topic']='internet'
            if mutation=='extra':bad['owner']='caller'
            elif mutation=='future':bad['checked_on']='2026-11-13'
            elif mutation=='range':bad['expires_on']='2026-11-10'
            elif mutation=='host':bad['source_urls']=['https://unapproved.example/guide']
            elif mutation=='homepage':bad['source_urls']=['https://english.www.gov.cn/']
            elif mutation=='unknown-city':bad['cities']=['guangzhou']
            elif mutation=='duplicate-city':bad['cities']=['chengdu','chengdu']
            elif mutation=='blank':bad['text_en']=' '
            else:bad['checked_on']='2026-2-30'
            with self.subTest(mutation=mutation):
                self.write([entry(),bad])
                with self.assertRaises(FactFailure):self.read()

    def test_duplicate_ids_bad_json_and_missing_resource_fail(self):
        with self.assertRaises(FactFailure):self.read()
        self.write([entry()]);self.write([entry()],'other.json')
        with self.assertRaises(FactFailure):self.read()
        (self.directory/'other.json').unlink()
        for raw in (b'{"id":1,"id":2}',b'[NaN]',b'\xff',b'[]'):
            (self.directory/'entries.json').write_bytes(raw)
            with self.subTest(raw=raw),self.assertRaises(FactFailure):self.read()

    def test_only_direct_formal_json_files_are_used_and_sources_are_immutable(self):
        original=entry();self.write([original])
        examples=self.directory/'examples';examples.mkdir()
        (examples/'format.json').write_text('invalid example must never be loaded')
        before=(self.directory/'entries.json').read_bytes()
        first=self.read();second=self.read()
        self.assertEqual(first,second);self.assertEqual(first['entries'],[original])
        self.assertEqual((self.directory/'entries.json').read_bytes(),before)

    def test_v2_query_rejects_old_envelopes_and_authority_fields(self):
        value=dict(version='FACT-query.2',topic='payment',city='成都')
        self.assertEqual(decode_query(json.dumps(value).encode()),Query('payment','成都'))
        for bad in (dict(value,version='FACT-query.1'),dict(value,owner='foreign'),dict(value,topic='visa'),
                    dict(value,city=None),dict(value,city=''),dict(value,evaluated_at='2020-01-01')):
            with self.subTest(value=bad),self.assertRaises(FactFailure):decode_query(json.dumps(bad).encode())
        with self.assertRaises(FactFailure):decode_query(b'{"version":"FACT-query.2","topic":"payment","topic":"internet","city":"chengdu"}')

    def test_additive_wire_examples_and_actual_producer_result(self):
        from jsonschema import Draft202012Validator,FormatChecker
        schema=json.loads((ROOT/'contracts/fact/visitor-schema.2.json').read_text())
        validator=Draft202012Validator(schema,format_checker=FormatChecker())
        for case in json.loads((ROOT/'contracts/fact/visitor-examples.2.json').read_text())['cases']:
            with self.subTest(case=case['id']):self.assertEqual(validator.is_valid(case['value']),case['valid'])
        self.write([entry()]);validator.validate(self.read())

    def test_clock_is_a_required_aware_server_instant(self):
        self.write([entry()])
        with self.assertRaises(ValueError):self.read(now=datetime(2026,11,12))


if __name__=='__main__':unittest.main(verbosity=2)
