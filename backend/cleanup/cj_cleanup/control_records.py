"""CLEANUP-CONTROL-RECORDS@1: registered client reconciliation, not a receipt."""
from .core import Invalid,digest,encode

VERSION='CLEANUP-CONTROL-RECORDS@1'
STORE='cleanup-control'
SLOTS={
    'selected':'M3.Cleanup.Selected',
    'manifest':'M3.Cleanup.Manifest.<verified-account-uuid>',
    'execution':'M3.Cleanup.Execution.<verified-account-uuid>',
    'device':'M3.Cleanup.Device.<verified-account-uuid>',
    'account':'M3.Cleanup.Account.<verified-account-uuid>',
}
SERVICE='G2C.CJAuth.session.<verified-backend-uuid>'


def catalog(store):
    """Validate the exact provided slots. No ordinary SDK/other-account grant."""
    rows=store.get('objects')
    if type(rows) is not list or len(rows)!=len(SLOTS):raise Invalid('complete client control catalog required')
    seen=set();entries=[]
    for row in rows:
        if type(row) is not dict:raise Invalid('client control record required')
        key=row.get('id')
        if (key not in SLOTS or key in seen or row.get('cleanup_protocol')!=VERSION
            or row.get('owner_line')!='A' or row.get('retention_category')!='cleanup_reconciliation'
            or row.get('service_template')!=SERVICE or row.get('slot_template')!=SLOTS[key]
            or row.get('finalization_protocol')!=VERSION
            or row.get('objects')!=['Keychain:'+SERVICE+'/'+SLOTS[key]]):
            raise Invalid('explicit original client reconciliation slot required')
        seen.add(key);entries.append((STORE+'/'+key,digest(encode(row))))
    return tuple(sorted(entries))
