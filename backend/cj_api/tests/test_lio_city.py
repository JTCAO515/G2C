"""Provider-catalog resolution, including same-name ambiguity; HTTP fixtures only."""
import json
import pytest
from cj_api.lio_city import resolve


def node(name,adcode,level,children=()):return dict(name=name,adcode=adcode,level=level,districts=list(children))


def data():
    provinces=[('上海市','310000',[('上海市','310100',[])]),
       ('四川省','510000',[('成都市','510100',[])]),
       ('陕西省','610000',[('西安市','610100',[])]),
       ('广西壮族自治区','450000',[('桂林市','450300',[])]),
       ('广东省','440000',[('广州市','440100',[])]),
       ('浙江省','330000',[('杭州市','330100',[]),('金华市','330700',[node('义乌市','330782','district')])]),
       ('江苏省','320000',[('苏州市','320500',[])]),
       ('安徽省','340000',[('宿州市','341300',[])]),
       ('辽宁省','210000',[('朝阳市','211300',[])]),
       ('北京市','110000',[('北京市','110100',[node('朝阳区','110105','district')])])]
    records=[node(p,code,'province',[node(c,a,'city',districts) for c,a,districts in cities]) for p,code,cities in provinces]
    return json.dumps(dict(status='1',infocode='10000',districts=[node('中华人民共和国','100000','country',records)]),ensure_ascii=False).encode()


@pytest.mark.parametrize('zh,en,adcode',[('上海','Shanghai','310000'),('成都','Chengdu','510100'),
    ('西安',"Xi'an",'610100'),('桂林','Guilin','450300'),('广州','Guangzhou','440100'),('杭州','Hangzhou','330100')])
def test_six_cities_both_languages_from_provider_catalog(zh,en,adcode):
    for query in (zh,en):
        result=resolve(data(),query)
        assert result['status']=='resolved'
        assert result['candidates'][0]['adcode']==adcode
        assert result['candidates'][0]['timezone']=='Asia/Shanghai'


def test_same_name_and_pinyin_ambiguity_never_take_first():
    assert resolve(data(),'朝阳')['status']=='ambiguous'
    assert resolve(data(),'Suzhou')['status']=='ambiguous'
    confirmed=resolve(data(),'朝阳',province='辽宁')
    assert confirmed['status']=='resolved' and confirmed['candidates'][0]['adcode']=='211300'
    assert resolve(data(),'朝阳区',province='北京')['candidates'][0]['adcode']=='110105'


def test_unproven_translation_and_province_ask_before_publishing():
    assert resolve(data(),'Canton',normalized_name='广州市')['status']=='confirmation_required'
    assert resolve(data(),'四川')['status']=='needs_city'
    assert resolve(data(),'not-a-city')['status']=='not_found'
