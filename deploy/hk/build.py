"""Build a source-only image with an application-only PG17 schema artifact."""
import argparse
from pathlib import Path
import subprocess
import tempfile

import psycopg
import migrate
import pg_suites
from deploy.build import source_context,ROOT
from . import schema


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform',choices=['linux/amd64','linux/arm64'],required=True)
    args=parser.parse_args()
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('clean_committed_build_source_required')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    with tempfile.TemporaryDirectory(prefix='g2c-hk-build-') as directory:
        root=Path(directory);context=root/'context';context.mkdir()
        source_context(ROOT,context,revision)
        with pg_suites.cluster('hk-schema',port=55883,role='cj_hk_schema',root=root/'pg',socket=root/'s') as config:
            with psycopg.connect(**config,autocommit=True) as connection:migrate.up(connection,migrate.load(),migrate.load()[-1]['version'])
            schema.generate(config,context/'deploy/hk/schema')
        tag='g2c-beta:'+revision
        subprocess.run(['docker','build','--platform='+args.platform,'--label','org.opencontainers.image.revision='+revision,
            '-f',str(context/'deploy/Dockerfile'),'-t',tag,str(context)],check=True)
        operator_tag='g2c-beta-operator:'+revision
        subprocess.run(['docker','build','--platform='+args.platform,'--label','org.opencontainers.image.revision='+revision,
            '--build-arg','CJ_BETA_IMAGE='+tag,'-f',str(context/'deploy/hk/operator.Dockerfile'),'-t',operator_tag,str(context)],check=True)
        print('PASS SOURCE='+revision+' IMAGE='+tag+' PLATFORM='+args.platform)


if __name__=='__main__':main()
