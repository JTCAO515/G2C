"""Frozen synthetic FACT wire and the actual existing acquisition/parser path."""
import copy
from datetime import date, datetime, timezone
import json
import unittest

from cj_fact.contract_v1 import decode_query, decode_result, dump, encode_query
from cj_fact.local_source import LocalFactProducer, FactCompletionUnknown
from cj_fact.model import DateRange, Query
from cj_fact.policy import FactFailure

NOW = datetime(2026, 10, 30, 10, tzinfo=timezone.utc)


def query(key='weather', *, dates=None, region='synthetic-city', conditions=(('calendar_timezone','Asia/Shanghai'),)):
    return Query(key, region, dates or DateRange(date(2026,10,30),date(2026,10,30)), conditions, NOW)


class FactV1Tests(unittest.TestCase):
    def result(self, key='weather', **kwargs):
        producer=LocalFactProducer(clock=lambda:NOW)
        raw=producer.invoke(encode_query(query(key,**kwargs)),'synthetic-op')
        return decode_result(raw),producer

    def test_actual_positive_source_and_original_literals(self):
        value,producer=self.result()
        self.assertEqual((producer.invocations,producer.transport_calls),(1,1))
        self.assertEqual((value['outcome'],value['status']),('ok','supported'))
        self.assertIn('NOT a real forecast',value['original_value'])
        self.assertIn('CNY 100',value['original_value'])
        self.assertIn('2026-10-30',value['original_value'])
        source=value['sources'][0]
        self.assertEqual(source['value']['text'],value['original_value'])
        self.assertEqual(source['declarations']['conditions'],{'calendar_timezone':'Asia/Shanghai'})
        self.assertTrue(value['summary_zh'] and value['summary_en'])

    def test_original_query_roundtrip(self):
        original=query('entry_notice',conditions=(('calendar_timezone','Asia/Shanghai'),('category','synthetic')))
        self.assertEqual(decode_query(encode_query(original),evaluated_at=NOW),original)

    def test_statuses_and_failures_stay_distinct(self):
        cases={'expired':('ok','expired'),'conflict':('ok','conflicting'),
            'unknown':('ok','unknown'),'missing':('no_results','unknown'),'rate':('rate_limited','unknown'),
            'malformed':('invalid_response','unknown'),'oversize':('invalid_response','unknown'),
            'redirect':('invalid_response','unknown')}
        for scenario,expected in cases.items():
            with self.subTest(scenario=scenario):
                value,producer=self.result('weather.'+scenario)
                self.assertEqual((value['outcome'],value['status']),expected)
                self.assertIsNone(value['original_value'])
                self.assertEqual(producer.invocations,1)
                if value['outcome']!='ok': self.assertEqual(value['sources'],[])
                self.assertNotIn('SYNTHETIC_PRIVATE_FACT_SENTINEL',json.dumps(value))

    def test_no_extrapolation_region_timezone_or_missing_conditions(self):
        for changes,status in [({'dates':DateRange(date(2026,11,10),date(2026,11,11))},'unsupported_or_out_of_range'),
            ({'region':'another-city'},'unsupported_or_out_of_range'),
            ({'conditions':(('calendar_timezone','America/New_York'),)},'unsupported_or_out_of_range'),
            ({'conditions':()},'unknown')]:
            with self.subTest(changes=changes):
                value,_=self.result(**changes)
                self.assertEqual(value['status'],status)
                self.assertIsNone(value['original_value'])
        value,_=self.result('entry_notice')
        self.assertEqual(value['status'],'unknown')
        self.assertIn('condition_not_supplied',value['sources'][0]['reasons'])

    def test_source_instructions_remain_untrusted_data(self):
        value,producer=self.result('weather.injection')
        self.assertEqual(value['status'],'supported')
        self.assertEqual((producer.invocations,producer.transport_calls),(1,1))
        self.assertEqual(set(value['sources'][0]['declarations']),{'regions','dates','conditions','published_at','expires_at'})
        self.assertNotIn('owner',value)
        self.assertNotIn('budget',value)

    def test_unknown_source_never_fabricates_empty_success(self):
        producer=LocalFactProducer(clock=lambda:NOW)
        with self.assertRaises(FactCompletionUnknown):
            producer.invoke(encode_query(query('weather.timeout')),'synthetic-op')
        self.assertEqual((producer.invocations,producer.transport_calls),(1,1))

    def test_query_boundary_rejects_authority_and_untyped_inputs(self):
        valid=json.loads(encode_query(query()))
        cases=[dict(valid,owner='foreign'),dict(valid,url='http://169.254.169.254'),
               dict(valid,budget='unlimited'),dict(valid,version='FACT-query.99'),
               dict(valid,conditions={'allow':True}),dict(valid,dates={'start':'20261030','end':'2026-10-30'}),
               dict(valid,conditions={str(i):'x' for i in range(33)})]
        producer=LocalFactProducer(clock=lambda:NOW)
        for value in cases:
            with self.subTest(value=value),self.assertRaises(FactFailure):
                producer.invoke(dump(value),'synthetic-op')
        for raw in (b'\xff',b'{"a":NaN}',b'{"version":"FACT-query.1","version":"FACT-query.1"}'):
            with self.subTest(raw=raw),self.assertRaises(FactFailure): decode_query(raw,evaluated_at=NOW)
        self.assertEqual(producer.invocations,0)

    def test_derived_verdict_and_provenance_cannot_be_relabelled(self):
        original,_=self.result('weather.expired')
        changed=copy.deepcopy(original);changed['status']='supported';changed['original_value']='fresh'
        with self.assertRaises(FactFailure): decode_result(dump(changed))
        original,_=self.result()
        for mutation in ('digest','literal','declaration','source','version','origin','shape','span-type','fold-type'):
            value=copy.deepcopy(original)
            if mutation=='digest':value['sources'][0]['original_sha256']='0'*64
            elif mutation=='literal':value['sources'][0]['value']['text']='eligible'
            elif mutation=='declaration':value['sources'][0]['declarations']['conditions']={}
            elif mutation=='source':value['sources'][0]['source_url']='http://169.254.169.254/'
            elif mutation=='version':value['version']='FACT-result.99'
            elif mutation=='origin':value['data_origin']='live'
            elif mutation=='shape':value['outcome']={}
            elif mutation=='span-type':value['sources'][0]['value']['start']=float(value['sources'][0]['value']['start'])
            else:value['sources'][0]['declarations']['published_at']['fold']=False
            with self.subTest(mutation=mutation),self.assertRaises(FactFailure):decode_result(dump(value))
