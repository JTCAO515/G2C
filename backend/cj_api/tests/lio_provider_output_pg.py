"""Actual registered oversized POI outputs settle unavailable; fixture HTTP only."""
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]
from cj_api.local_lio_provider_sources import RegisteredProviderSources,PROVIDER_OUTPUT_LIMIT
from lio_provider_sources_pg import FixtureWriter,main as providers_main


def main():
    original_value=FixtureWriter.response_value
    original_observe=RegisteredProviderSources.observe_poi2
    rejected=[]
    def response(writer):
        if writer.available:return original_value(writer)
        return dict(status='1',infocode='10000',count='2',pois=[dict(id='B'+str(n)+'x'*198,
            name='\\'*500,cityname='北京市',adcode='110101',location='116.4,39.9',address='"'*1024,
            business=dict(opentime_today='"'*1024,opentime_week='"'*1024))for n in range(2)])
    def observe(source,operation,*args):
        raw,metadata=original_observe(source,operation,*args)
        if metadata.get('unavailable_reason')=='normalized_output_limit':
            assert len(raw.decode())<=PROVIDER_OUTPUT_LIMIT
            assert metadata['result_status']=='unavailable'
            rejected.append(operation.command.attempt_id)
        return raw,metadata
    with patch.object(FixtureWriter,'response_value',response),patch.object(RegisteredProviderSources,'observe_poi2',observe):
        providers_main()
    assert len(rejected)==6 and len(set(rejected))==6
    print('PASS ZH3/EN3 six complete oversized projections -> unavailable/zero eligible records; twelve original registered RECEIVED receipts, no retry or Trip; fixture HTTP only',flush=True)


if __name__=='__main__':main()
