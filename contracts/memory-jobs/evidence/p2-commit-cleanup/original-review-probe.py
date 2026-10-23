from pathlib import Path
import sys,json
r=Path(__file__).parent;s=r/'snapshot';sys.path[:0]=[str(s/'backend/memory_jobs'),str(s/'backend/message'),str(s/'backend/memory_jobs/tests')]
from test_jobs import Jobs
from cj_memory_jobs.queue import LocalStore,InternalQueue
from cj_memory_jobs.codec import CommitUnknown
f=Jobs();f.setUp()
try:
 f.enqueue();f.begin();native=f.store.db
 class DoubleFault:
  def __getattr__(self,name):return getattr(native,name)
  def commit(self):native.commit();raise OSError('synthetic lost commit ACK')
  def close(self):native.close();raise RuntimeError('synthetic cleanup failure')
 f.store.db=DoubleFault();caught=None
 try:f.complete()
 except BaseException as e:caught=type(e).__name__
 f.store=LocalStore(f.path);f.queue=InternalQueue(f.store,f.host);state=f.query().state
 assert caught=='RuntimeError' and state=='completed'
 print(json.dumps({'durable_completion_after_commit_fault':state,'reported_exception':caught,'expected_uncertainty_exception':'CommitUnknown','reproduced_cleanup_masks_commit_unknown':True}))
finally:f.tearDown()
