"""Provider-catalog resolution, including same-name ambiguity; HTTP fixtures only."""
import json
from cj_api.lio_city import resolve

def node(name, adcode, level, children=()):
    return dict(name=name, adcode=adcode, level=level, districts=list(children))

def data():
    provinces = [('上海市', '310000', [('上海市', '310100', [])]), ('四川省', '510000', [('成都市', '510100', [])]), ('陕西省', '610000', [('西安市', '610100', [])]), ('广西壮族自治区', '450000', [('桂林市', '450300', [])]), ('广东省', '440000', [('广州市', '440100', [])]), ('浙江省', '330000', [('杭州市', '330100', []), ('金华市', '330700', [node('义乌市', '330782', 'district')])]), ('江苏省', '320000', [('苏州市', '320500', [])]), ('安徽省', '340000', [('宿州市', '341300', [])]), ('辽宁省', '210000', [('朝阳市', '211300', [])]), ('北京市', '110000', [('北京市', '110100', [node('朝阳区', '110105', 'district')])])]
    records = [node(p, code, 'province', [node(c, a, 'city', districts) for (c, a, districts) in cities]) for (p, code, cities) in provinces]
    return json.dumps(dict(status='1', infocode='10000', districts=[node('中华人民共和国', '100000', 'country', records)]), ensure_ascii=False).encode()
import unittest

class NationalLioCity(unittest.TestCase):

    def test_six_cities_both_languages_from_provider_catalog(self):
        for (zh, en, adcode) in [('上海', 'Shanghai', '310000'), ('成都', 'Chengdu', '510100'), ('西安', "Xi'an", '610100'), ('桂林', 'Guilin', '450300'), ('广州', 'Guangzhou', '440100'), ('杭州', 'Hangzhou', '330100')]:
            with self.subTest(zh=zh, en=en, adcode=adcode):
                for query in (zh, en):
                    result = resolve(data(), query)
                    assert result['status'] == 'resolved'
                    assert result['candidates'][0]['adcode'] == adcode
                    assert result['candidates'][0]['timezone'] == 'Asia/Shanghai'

    def test_same_name_and_pinyin_ambiguity_never_take_first(self):
        assert resolve(data(), '朝阳')['status'] == 'ambiguous'
        assert resolve(data(), 'Suzhou')['status'] == 'ambiguous'
        confirmed = resolve(data(), '朝阳', province='辽宁')
        assert confirmed['status'] == 'resolved' and confirmed['candidates'][0]['adcode'] == '211300'
        assert resolve(data(), '朝阳区', province='北京')['candidates'][0]['adcode'] == '110105'

    def test_unproven_translation_and_province_ask_before_publishing(self):
        assert resolve(data(), 'Canton', normalized_name='广州市')['status'] == 'confirmation_required'
        assert resolve(data(), '四川')['status'] == 'needs_city'
        assert resolve(data(), 'Szechuan',normalized_name='四川省')['status']=='needs_city'
        assert resolve(data(), 'not-a-city')['status'] == 'not_found'
        assert resolve(data(), "Xi'an",province='Shaanxi')['status']=='confirmation_required'
        assert resolve(data(), "Xi'an",province='Shaanxi')['candidates'][0]['name']=='西安市'

    def test_catalog_wire_has_no_url_logger_and_preserves_one_guarded_request(self):
        import asyncio
        import io
        import logging
        from unittest.mock import patch
        from cj_api.lio_city import fetch_catalog
        from cj_usage.metered_exit import BudgetUnknown
        key='fixture-secret-only-no-real-key';body=data();writes=[];aborts=[];connections=[]
        class Writer:
            def __init__(self):self.transport=self
            def write(self,value):writes.append(value)
            async def drain(self):pass
            def abort(self):aborts.append(True)
        async def connect(*args,**kwargs):
            connections.append((args,kwargs))
            reader=asyncio.StreamReader()
            reader.feed_data(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
            reader.feed_eof()
            return reader,Writer()
        log=io.StringIO();handler=logging.StreamHandler(log)
        loggers=[logging.getLogger('httpx'),logging.getLogger('httpcore')]
        levels=[logger.level for logger in loggers]
        try:
            for logger in loggers:logger.addHandler(handler);logger.setLevel(logging.DEBUG)
            with patch('cj_api.lio_city.asyncio.open_connection',side_effect=connect):
                assert fetch_catalog(key,lambda:True)==body
            assert len(writes)==len(connections)==1 and len(aborts)==1
            assert b'/v3/config/district?' in writes[0] and b'subdistrict=3' in writes[0]
            assert key not in log.getvalue()
            writes.clear();connections.clear();aborts.clear();checks=iter((True,False))
            with patch('cj_api.lio_city.asyncio.open_connection',side_effect=connect), self.assertRaises(BudgetUnknown):
                fetch_catalog(key,lambda:next(checks))
            assert not writes and len(connections)==1 and len(aborts)==1
            assert key not in log.getvalue()
        finally:
            for logger,level in zip(loggers,levels):logger.removeHandler(handler);logger.setLevel(level)

    def test_short_header_and_body_keep_unknown_and_abort_without_retry(self):
        import asyncio
        from unittest.mock import patch
        from cj_api.lio_city import fetch_catalog
        from cj_usage.metered_exit import BudgetUnknown
        for raw in (b'HTTP/1.1 200',b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 10\r\n\r\n{}'):
            with self.subTest(response=raw):
                writes=[];aborts=[];connections=[]
                class Writer:
                    def __init__(self):self.transport=self
                    def write(self,value):writes.append(value)
                    async def drain(self):pass
                    def abort(self):aborts.append(True)
                async def connect(*args,**kwargs):
                    connections.append(True);reader=asyncio.StreamReader();reader.feed_data(raw);reader.feed_eof()
                    return reader,Writer()
                with patch('cj_api.lio_city.asyncio.open_connection',side_effect=connect),self.assertRaises(BudgetUnknown):
                    fetch_catalog('fixture-not-a-real-key',lambda:True)
                assert len(writes)==len(connections)==len(aborts)==1


    def test_pinyin_apostrophe_keeps_xi_an_distinct_from_xian_county(self):
        value=json.loads(data())
        value['districts'][0]['districts'].append(node('河北省','130000','province',
            [node('沧州市','130900','city',[node('献县','130929','district')])]))
        raw=json.dumps(value,ensure_ascii=False).encode()
        for query in ("Xi'an",'Xi’an'):
            with self.subTest(query=query):
                result=resolve(raw,query)
                self.assertEqual(result['status'],'resolved')
                self.assertEqual([c['adcode'] for c in result['candidates']],['610100'])
        self.assertEqual(resolve(raw,'Xian')['status'],'ambiguous')
        self.assertEqual(resolve(raw,"'Xian'")['status'],'ambiguous')
        self.assertEqual(resolve(raw,"'西安'")['candidates'][0]['adcode'],'610100')
        self.assertEqual(resolve(raw,'献县')['candidates'][0]['adcode'],'130929')
