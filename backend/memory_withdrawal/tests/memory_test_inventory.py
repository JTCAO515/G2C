"""Provided C4/B3/metadata inventory for actual private-PG Memory tests."""
from cj_cleanup.core import encode
from cj_memory_withdrawal.erasure_service import ORDER


def write_inventory(path,version):
    stores=[dict(id='memory-derived',cleanup_protocol='CLEANUP@1.1'),
        dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')]),
        dict(id='business',objects=[dict(id=target.split('/')[1],cleanup_protocol='CLEANUP@1.1')
            for target in ORDER if target.startswith('business/')])]
    path.write_bytes(encode(dict(version=version,stores=stores)))
