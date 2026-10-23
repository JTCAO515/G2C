"""OFFLINE only: synthetic key and MockTransport; no provider/socket permitted."""
import asyncio,json,logging,os,socket,sqlite3,tempfile
from pathlib import Path
from unittest.mock import patch
import httpx
from dbos import DBOS
import provider_acceptance as target
from test_provider_acceptance import config

logging.disable(logging.CRITICAL)
def no_network(*args,**kwargs):raise AssertionError('OFFLINE_NETWORK_FORBIDDEN')
socket.socket.connect=no_network;socket.create_connection=no_network
P=Path(__file__).parent

async def main():
 record={'scope':'OFFLINE_SECURITY_PROBES_ONLY','real_provider':'UNRUN'}
 with tempfile.TemporaryDirectory(prefix='security-',dir=P) as temp:
  root=Path(temp);keylog=root/'fixture-keylog.txt'
  with patch.dict(os.environ,{'SSLKEYLOGFILE':str(keylog)}):
   transport=httpx.AsyncHTTPTransport(retries=0,trust_env=False)
   record['ambient_TLS_keylog_enabled']=transport._pool._ssl_context.keylog_filename==str(keylog)
   record['keylog_file_created_without_network']=keylog.exists()
   await transport.aclose()
  c=config();key='fixture-runtime-secret-only-6a8'
  escaped=''.join('\\u%04x'%ord(ch) for ch in key)
  text='{"echo":"'+escaped+'"'  # truncated JSON, complete recoverable escaped key
  record['uninspectable_escaped_echo_detected']=target.contains_secret(text,key)
  journal=target.Journal(root/'journal',c);target.CONTEXT=(c,journal,key)
  DBOS(config={'name':'cj002-security-offline','application_version':'fixture-v1','system_database_url':'sqlite:///'+str(root/'dbos.sqlite'),'enable_otlp':False,'log_level':'CRITICAL','use_listen_notify':False})
  DBOS.launch()
  async def handler(request):
   chunks=[{'id':'fixture-response','object':'chat.completion.chunk','created':1,'model':c['model_id'],'choices':[{'index':0,'delta':{'content':text},'finish_reason':None}]},
           {'id':'fixture-response','object':'chat.completion.chunk','created':1,'model':c['model_id'],'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}]
   payload=''.join('data: '+json.dumps(x)+'\n\n' for x in chunks)+'data: [DONE]\n\n'
   return httpx.Response(200,content=payload,headers={'content-type':'text/event-stream'})
  try:
   with patch.object(target.httpx,'AsyncHTTPTransport',lambda **kw:httpx.MockTransport(handler)):
    out=await target.provider_step('security-fixture',0,[target.UserMsg(name='fixture',content='hello').model_dump()],False)
   record['provider_step_outcome']=out['receipt']['outcome']
   record['response_with_encoded_secret_returned']='response' in out and any(getattr(b,'text',None)==text for b in out['response'].content)
  finally:DBOS.destroy()
  persisted=False
  with sqlite3.connect(root/'dbos.sqlite') as db:
   tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
   for table in tables:
    assert table.replace('_','').isalnum()
    for row in db.execute('SELECT * FROM "'+table+'"'):
     for value in row:
      if isinstance(value,str) and escaped in value.replace('\\\\','\\'):persisted=True
  record['encoded_secret_found_in_own_DBOS_persistence']=persisted
 (P/'offline-security-result.json').write_text(json.dumps(record,indent=2)+'\n')
 print(json.dumps(record))
 return 1 if record['ambient_TLS_keylog_enabled'] or record.get('response_with_encoded_secret_returned') else 0

if __name__=='__main__':raise SystemExit(asyncio.run(main()))
