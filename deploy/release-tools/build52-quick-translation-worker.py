"""One same-source Build 52 translation probe. Provider/media/credentials stay private."""

def main():
    if not __debug__:
        raise ValueError('non_optimized_worker_required')
    import json,sys,time
    from hashlib import sha256
    from http.client import HTTPException
    from datetime import datetime,timezone
    from urllib.error import HTTPError,URLError
    from urllib.request import Request,build_opener
    from uuid import UUID
    from deploy.hk.configuration import TRANSLATION_INTERNAL_SUBJECTS, authorization, load_secret_environment
    from deploy.hk.plugin_roster import configured_plugin_subjects
    from cj_api.local_app import ISSUER,scope_for
    from cj_usage.sublimits import scope_hash
    import os
    from deploy.hk.server_smoke import NoRedirect, ORIGIN
    from deploy.hk.translation_relay import translation_state
    from cj_api.translation import ROUTE,VERSION,TranslationInput
    from cj_usage.authorization_budget import AuthorizationBudget,HK_JOURNAL_ROOT,CNY_SCALE,LIMITS,journal_state
    from cj_usage.translation_budget import SERVICE, translation_price, SUBLIMIT
    raw=sys.stdin.buffer.read(5*1024*1024+1)
    assert len(raw)<=5*1024*1024
    p=json.loads(raw)
    assert p['case']=='text.zh'
    load_secret_environment('worker')
    assert translation_state() is True
    roster=configured_plugin_subjects(os.environ[TRANSLATION_INTERNAL_SUBJECTS])
    assert p['subject'] in roster
    expected_owner=scope_hash(scope_for(ISSUER,p['subject']))
    authorization()
    budget=AuthorizationBudget(HK_JOURNAL_ROOT,authorization_guard=authorization,demo=True)
    doc=p['document']
    parsed=TranslationInput.read(json.dumps(doc,ensure_ascii=False).encode())
    assert p['case']==parsed.kind+'.'+parsed.source_lang
    key=UUID(doc['request_id']).hex
    def ledger():
     with budget.connect() as db:
      db.execute('BEGIN')
      budget.require_producer(db)
      rows=db.execute('SELECT id,state,receipt FROM attempt WHERE id GLOB ? ORDER BY id',(SERVICE+':*',)).fetchall()
      selected=[]
      for identifier,state,raw in rows:
       if ':'+key+':' in identifier:
        assert identifier.startswith(SERVICE+':'+expected_owner+':'+key+':')
        selected.append((state,raw))
      charge=lambda state,raw: translation_price(json.loads(raw)) if state=='RECEIVED' else None
      known=[charge(*entry) for entry in selected]
      total=sum(cost if (cost:=charge(state,raw)) is not None else LIMITS['model'][1]*CNY_SCALE for _,state,raw in rows)
      return selected,known,total,journal_state(db)
    before,_,prior,before_anchor=ledger()
    assert not before
    req=Request(ORIGIN+ROUTE, data=json.dumps(doc,ensure_ascii=False).encode(), method='POST',
               headers={'Authorization':'Bearer '+p['credential'],'Content-Type':'application/json'})
    status=None
    payload=None
    response_complete=False
    timeout=False
    end=datetime.fromisoformat(p['ends_at'])
    remaining=(end-datetime.now(timezone.utc)).total_seconds()
    if remaining<55:
        raise ValueError('approved_probe_window_too_short')
    def read_body(response, limit):
        try:
            data = response.read(limit+1)
            length = response.headers.get('Content-Length')
            if len(data)>limit or (length is not None and (not length.isascii() or not length.isdecimal()
                                                          or int(length) != len(data))):
                return None, False
            return json.loads(data), True
        except TimeoutError:
            raise
        except (HTTPException,OSError,ValueError):
            return None, False

    start=time.monotonic()
    try:
        with build_opener(NoRedirect()).open(req,timeout=55) as response:
            status=response.status
            payload,response_complete=read_body(response,262144)
    except HTTPError as error:
        status=error.code
        with error:
            try:
                payload,response_complete=read_body(error,2048)
            except TimeoutError:
                timeout=True
    except (HTTPException,OSError,ValueError) as error:
        timeout=isinstance(error,TimeoutError) or isinstance(getattr(error,"reason",None),TimeoutError)

    elapsed_ms=round((time.monotonic()-start)*1000,1)
    after,costs,total,after_anchor=ledger()
    delta=sum(cost if cost is not None else LIMITS['model'][1]*CNY_SCALE for cost in costs)
    items=payload.get('items') if status==200 and isinstance(payload,dict) else None
    answer = isinstance(items,list) and any(isinstance(row,dict)
              and isinstance(row.get('translated_text'),str) and row['translated_text'].strip() for row in items)
    service_failure = bool(timeout or (status is not None and status>=500)
                           or (status==200 and response_complete and not answer))
    correct=(answer and response_complete and payload.get('version')==VERSION
             and payload.get('kind')=='text' and len(after)==1 and all(c is not None for c in costs))
    outcome='PASS' if correct else 'FAIL' if service_failure else 'UNKNOWN'
    print(json.dumps(dict(case=p['case'],status=outcome,http=status,service_failure=service_failure,elapsed_ms=elapsed_ms,fees=dict(conservative_cny_1e7=delta,
         known_cny_1e7=sum(x for x in costs if x is not None),
         paid='UNKNOWN' if after or outcome=='UNKNOWN' else 0,
         observed_only=outcome=='UNKNOWN'),
     request_sha256=sha256(key.encode()).hexdigest(),
     before_anchor=before_anchor,after_anchor=after_anchor,attempt_states=[state for state,_ in after],
         translated=bool(correct and after),new_attempts=len(after),within_translation_ceiling=total<=SUBLIMIT,
         exact_translation_subledger=total-prior==delta)))


if __name__=='__main__':
    try:
        main()
    except Exception:
        import json
        print(json.dumps(dict(status='UNKNOWN',reason='probe_receipt_requires_original_readback')),flush=True)
        raise SystemExit(2) from None
