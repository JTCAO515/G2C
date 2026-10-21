#!/usr/bin/env python3
"""Summarize a processed xctrace time-profile export; never infer FPS from CPU weights."""
import collections,json,pathlib,sys,xml.etree.ElementTree as ET
root=ET.parse(sys.argv[1]).getroot()
ids={node.get('id'):node for node in root.iter() if node.get('id')}
def resolve(node):
    while node is not None and node.get('ref'): node=ids[node.get('ref')]
    return node
leaf=collections.Counter();own=collections.Counter();threads=collections.Counter();unresolved=0;rows=0;times=[];binaries={}
for row in root.iter('row'):
    fields=list(row)
    if len(fields)!=7: raise SystemExit('Unexpected time-profile row shape')
    stamp,thread,process,core,state,weight,stack=map(resolve,fields)
    if 'CJIOSSpike' not in process.get('fmt',''): raise SystemExit('Unexpected sampled process')
    ms=int(weight.text)/1_000_000
    times.append(int(stamp.text)/1_000_000_000);rows+=1
    group='main' if 'Main Thread' in thread.get('fmt','') else 'other'
    threads[group]+=ms
    frames=[resolve(frame) for frame in stack]
    if frames: leaf[frames[0].get('name','?')]+=ms
    sample_own=set()
    for frame in frames:
        binary=resolve(frame.find('binary'))
        if binary is None: continue
        if binary.get('name')=='CJIOSSpike':
            binaries[binary.get('UUID')]=binary.get('path')
            name=frame.get('name','?')
            if name.startswith('0x') or name in ['?','<unknown>']: unresolved+=1
            else: sample_own.add(name)
    for name in sample_own: own[name]+=ms
summary={'sample_rows':rows,'sample_time_range_seconds':[min(times),max(times)],'sample_weight_ms_by_thread':dict(threads),'unresolved_first_party_frame_occurrences':unresolved,'first_party_binaries':binaries,'top_leaf_sample_weight_ms':leaf.most_common(12),'top_first_party_inclusive_sample_weight_ms':own.most_common(12),'caveat':'One simulator Debug trace; statistical CPU sample weights, not FPS, frame latency, wall-time utilization or product acceptance. Trace warning must be considered.'}
if unresolved:
    summary.pop('top_leaf_sample_weight_ms')
    summary.pop('top_first_party_inclusive_sample_weight_ms')
    summary['hotspot_conclusion'] = 'WITHHELD: unresolved first-party frames; symbolication gate not satisfied'
print(json.dumps(summary,indent=2,ensure_ascii=False))
