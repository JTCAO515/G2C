"""Operator client for the existing signed Lio API and original worker.

Control is the scoped HK operator channel. It never sends model/tool requests;
only original MESSAGE dispatch through the existing API can cause execution.
"""
from hashlib import sha256
import json
from pathlib import Path
import time

from cj_usage.authorization_budget import canonical
from .runtime_candidate import Candidate,BASELINE
from .runtime_window import ENTRY,owned_json,directory,save_new

VERSION='G2C-runtime-adapter.1'
TASK='G2C-runtime-task.1'


class AdapterUnknown(Exception):
 pass


class RuntimeAdapter:
 def __init__(self,*,api,control,window,identities,journal,clock=time.monotonic):
  self.api,self.control,self.window=api,control,window
  self.identities,self.journal,self.clock=identities,directory(journal),clock

 def _path(self,attempt):return self.journal/(sha256(attempt.encode()).hexdigest()+'.json')

 def _write(self,record):
  path=self._path(record['attempt_id']);temporary=path.with_name(path.stem+'.next.json')
  save_new(self.journal,temporary.name,record)
  temporary.replace(path)

 def _headers(self,language):
  identity=self.identities[language]
  token=identity['access_token']
  return {'Authorization':'Bearer '+token,'Content-Type':'application/json'}

 def _read(self,attempt):
  return owned_json(self._path(attempt))

 def _check_task(self,task):
  if (type(task) is not dict or task.get('version')!=TASK or task.get('language') not in ('zh','en')
      or type(task.get('id')) is not str or type(task.get('steps')) is not list or not task['steps']):
   raise ValueError('frozen complete task steps and one language required')
  for step in task['steps']:
   if type(step) is not dict or step.get('kind') not in ('message','lio_undo_current_trip'):
    raise ValueError('unsupported setup or task step; do not substitute a writer')
   if step['kind']=='message' and (type(step.get('text')) is not str or not step['text'].strip()
                                 or len(step['text'].encode())>12000):
    raise ValueError('bounded complete user turn required')

 def call(self,task,candidate,*,attempt_id,timeout):
  self._check_task(task);candidate=Candidate.parse(candidate)
  if type(attempt_id) is not str or not attempt_id or len(attempt_id.encode())>512:
   raise ValueError('fixed logical attempt required')
  if type(timeout) not in (int,float) or not 0<timeout<=3600:raise ValueError('bounded task timeout required')
  task_sha=sha256(canonical(task)).hexdigest();path=self._path(attempt_id)
  if path.exists():
   old=self._read(attempt_id)
   if old['task_sha256']!=task_sha or old['candidate_sha256']!=candidate.digest:
    raise ValueError('original logical attempt cannot change task or candidate')
   return self.query(attempt_id) # Never resume a half-dispatched task implicitly.
  mode=task.get('mode','task')
  if mode not in ('task','teacher','reflection'):raise ValueError('explicit runtime mode required')
  if mode=='teacher' and candidate.fragments!=BASELINE:raise ValueError('teacher keeps original C0')
  record=dict(version=VERSION,attempt_id=attempt_id,task=task,task_sha256=task_sha,
              candidate_sha256=candidate.digest,candidate=dict(candidate.fragments),steps=[],state='INTENT',
              window_id=self.window['window_id'],pins=self.window['pins'])
  save_new(self.journal,path.name,record)
  deadline=self.clock()+timeout;conversation=None
  try:
   for index,step in enumerate(task['steps']):
    if self.clock()>=deadline:raise AdapterUnknown('task observation deadline reached')
    language=task['language'];headers=self._headers(language)
    identity=self.identities[language]
    mid=self.window['billing_prefix']+sha256((attempt_id+'\0'+str(index)).encode()).hexdigest()[:40]
    if step['kind']=='message':
     body=dict(version='LIO-message.2',message_id=mid,text=step['text'],locale=language)
     if conversation is None:body['new_conversation']=True
     else:body['conversation_id']=conversation
     raw=canonical(body)
     entry=dict(version=ENTRY,window_id=self.window['window_id'],purpose=self.window['purpose'].split('-')[0],
                attempt_id=attempt_id,message_id=mid,subject=identity['subject'],language=language,mode=mode,
                task_id=task['id'],task_sha256=task_sha,input_sha256=sha256(raw).hexdigest(),
                candidate=dict(candidate.fragments),components=task.get('components',[]))
     original=dict(kind='message',message_id=mid,input_sha256=entry['input_sha256'],request=body,phase='PREPARED')
     record['steps'].append(original);self._write(record)
     self.control.submit(entry)
     original['phase']='DISPATCH_INTENT';self._write(record)
     response=self.api.post('/v2/lio/messages',content=raw,headers=headers)
     if response.status_code!=200:raise AdapterUnknown('original signed send not acknowledged')
     receipt=response.json()
     if receipt.get('message_id')!=mid or not receipt.get('conversation_id') or not receipt.get('run_id'):
      raise AdapterUnknown('original signed receipt binding unavailable')
     original.update(receipt=receipt,phase='ACKNOWLEDGED');self._write(record)
     conversation=receipt['conversation_id']
     while True:
      observation=self.control.query(attempt_id)
      found=next((m for m in observation['messages'] if m['message_id']==mid),None)
      if found is not None and found.get('status') in ('completed','failed','unknown','cancelled','context_invalid'):
       original['status']=found['status'];self._write(record)
       if found['status']!='completed':raise AdapterUnknown('original RUN did not complete')
       break
      if self.clock()>=deadline:raise AdapterUnknown('original RUN still unsettled')
      time.sleep(min(.25,max(0,deadline-self.clock())))
    else:
     if conversation is None:raise ValueError('undo needs the same existing conversation')
     current=self.api.get('/v2/lio/trip',params={'conversation_id':conversation},headers=headers)
     if current.status_code!=200 or not current.json().get('undo_target'):
      raise ValueError('current original Lio undo target unavailable')
     action='runtime-undo-'+sha256((attempt_id+'\0'+str(index)).encode()).hexdigest()[:32]
     body=dict(version='LIO-trip-undo.2',action_id=action,target=current.json()['undo_target'],conversation_id=conversation)
     original=dict(kind='lio_undo_current_trip',request=body,phase='DISPATCH_INTENT')
     record['steps'].append(original);self._write(record)
     response=self.api.post('/v2/lio/trip/undo',content=canonical(body),headers=headers)
     if response.status_code!=200 or not response.json().get('committed'):
      raise AdapterUnknown('original undo not acknowledged; query this action only')
     original.update(receipt=response.json(),phase='ACKNOWLEDGED');self._write(record)
   record['state']='RECORDED';self._write(record)
  except AdapterUnknown:
   record['state']='UNKNOWN';self._write(record)
  return self.query(attempt_id)

 def query(self,attempt_id):
  record=self._read(attempt_id)
  observation=self.control.query(attempt_id)
  actions=[]
  for step in record['steps']:
   if step['kind']=='lio_undo_current_trip':
    body=step['request']
    reply=self.api.get('/v2/lio/trip/undo',params={k:body[k] for k in ('action_id','target','conversation_id')},
                       headers=self._headers(record['task']['language']))
    actions.append(dict(request=body,http_status=reply.status_code,receipt=reply.json() if reply.status_code==200 else None))
  return dict(version=VERSION,attempt_id=attempt_id,state=record['state'],task_sha256=record['task_sha256'],
              candidate_sha256=record['candidate_sha256'],pins=record['pins'],steps=record['steps'],
              original_observation=observation,original_actions=actions,
              semantic_assessment='UNRUN; independent D/C annotation required')

 def propose(self,candidate,feedback,components,*,attempt_id,timeout):
  candidate=Candidate.parse(candidate)
  if (type(feedback) is not dict or feedback.get('split')!='development'
      or type(components) is not list or not components or len(components)!=len(set(components))
      or not set(components)<=BASELINE.keys()):
   raise ValueError('only public development feedback and approved components permitted')
  text=canonical(dict(version='G2C-runtime-reflection.1',split='development',feedback=feedback,
                      candidate=dict(candidate.fragments),components=components)).decode()
  task=dict(version=TASK,id='public-development-reflection',language='en',mode='reflection',components=components,
            steps=[dict(kind='message',text=text)])
  observed=self.call(task,dict(candidate.fragments),attempt_id=attempt_id,timeout=timeout)
  if observed['state']!='RECORDED':raise AdapterUnknown('original reflection incomplete; query its attempt')
  messages=observed['original_observation']['messages']
  if len(messages)!=1 or messages[0].get('status')!='completed':raise AdapterUnknown('reflection source unavailable')
  value=json.loads(messages[0]['text'])
  if type(value) is not dict or value.keys()!=set(components):raise ValueError('unapproved reflection result')
  Candidate.parse({**candidate.fragments,**value})
  return value
