from pathlib import Path
import sys,json
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo
r=Path(__file__).parent;s=r/'snapshot';sys.path[:0]=[str(s/'backend'/x) for x in ['auth','draft','trip','needs','memory','feasibility']]+[str(s/'backend/draft/tests')]
from test_review import needs,memory,proposal
from cj_draft.review import request,review,SourceLink
snap,revisions=needs();ctx=memory();tz=ZoneInfo('America/New_York');a=datetime(2026,11,1,1,30,tzinfo=tz,fold=0);b=a.replace(fold=1)
original=replace(ctx.items[0],recorded_at=a);other=replace(original,recorded_at=b);ctx=replace(ctx,items=(original,));p=proposal();req=request(p,snap,revisions,ctx,subject='self',context_id='trip-1')
assert a.timestamp()!=b.timestamp() and original==other
result=review(req,snap,revisions,ctx,subject='self',context_id='trip-1',links=(SourceLink('item-1','original-needs',revisions[0]),SourceLink('item-1','original-memory',other)),cancelled=False,as_of=100)
assert result.links[1].source is other and result.links[1].source.recorded_at.timestamp()!=original.recorded_at.timestamp()
print(json.dumps({'reproduced_nonoriginal_fold_source_accepted':True,'original_recorded_at':a.isoformat(),'accepted_recorded_at':b.isoformat(),'different_instants':True,'can_publish':result.can_publish}))
