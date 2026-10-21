#!/usr/bin/env python3
"""Create an explicitly derived profile using only an exact-UUID dSYM and trace load address."""
import hashlib,json,pathlib,subprocess,sys,xml.etree.ElementTree as ET
source,dwarf,destination,mapping=map(pathlib.Path,sys.argv[1:5])
binary=pathlib.Path(sys.argv[5]) if len(sys.argv)==6 else None
tree=ET.parse(source);root=tree.getroot();ids={n.get('id'):n for n in root.iter() if n.get('id')}
def deref(n):
    while n is not None and n.get('ref'): n=ids[n.get('ref')]
    return n
frames=[];owners={}
for frame in root.iter('frame'):
    if frame.get('ref') or not frame.get('name','').startswith('0x'): continue
    owner=deref(frame.find('binary'))
    if owner is not None and owner.get('name')=='CJIOSSpike':
        frames.append(frame);owners[(owner.get('UUID'),owner.get('arch'),owner.get('load-addr'))]=owner
if len(owners)!=1: raise SystemExit('Need one unambiguous first-party image UUID/architecture/load address')
(uuid,arch,load),owner=next(iter(owners.items()))
uuid_text=subprocess.check_output(['xcrun','dwarfdump','--uuid',str(dwarf)],text=True)
if f'UUID: {uuid} ({arch})' not in uuid_text: raise SystemExit('dSYM UUID/architecture mismatch')
addresses=sorted({f.get('addr') for f in frames},key=lambda value:int(value,16))
result=subprocess.run(['xcrun','atos','-arch',arch,'-o',str(dwarf),'-l',load,*addresses],text=True,capture_output=True,check=True)
lines=result.stdout.splitlines()
if len(lines)!=len(addresses) or result.stderr.strip(): raise SystemExit('Ambiguous atos output count or stderr; refusing derived names')
resolved={};lookups=[]
for address,line in zip(addresses,lines):
    marker=' (in CJIOSSpike)'
    valid=marker in line and not line.startswith(('0x','???')) and '(null)' not in line
    if valid: resolved[address]=line.split(marker,1)[0]
    lookups.append({'address':address,'atos_output':line,'accepted':valid,'method':'atos-dwarf'})
binary_record=None
if binary is not None:
    binary_uuid=subprocess.check_output(['xcrun','dwarfdump','--uuid',str(binary)],text=True)
    if f'UUID: {uuid} ({arch})' not in binary_uuid: raise SystemExit('Binary UUID/architecture mismatch')
    remaining=[item for item in lookups if not item['accepted']]
    if remaining:
        second=subprocess.run(['xcrun','atos','-arch',arch,'-o',str(binary),'-l',load,*[item['address'] for item in remaining]],text=True,capture_output=True,check=True)
        names=second.stdout.splitlines()
        if len(names)!=len(remaining) or second.stderr.strip(): raise SystemExit('Ambiguous binary atos output; refusing derived names')
        for item,line in zip(remaining,names):
            item['binary_atos_output']=line
            valid=' (in CJIOSSpike)' in line and not line.startswith(('0x','???')) and '(null)' not in line
            if valid:
                item.update(accepted=True,method='atos-exact-binary')
                resolved[item['address']]=line.split(' (in CJIOSSpike)',1)[0]
    binary_record={'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'dwarfdump':binary_uuid.strip()}
for frame in frames:
    if frame.get('addr') in resolved: frame.set('name',resolved[frame.get('addr')])
tree.write(destination,encoding='utf-8',xml_declaration=True)
record={'derivation':'Names only for unresolved CJIOSSpike frames; original export and trace untouched','source_export_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'dwarf_sha256':hashlib.sha256(dwarf.read_bytes()).hexdigest(),'uuid':uuid,'architecture':arch,'load_address_from_trace':load,'dwarfdump':uuid_text.strip(),'unique_addresses':len(addresses),'resolved_addresses':len(resolved),'lookups':lookups,'derived_export_sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}
record['exact_binary']=binary_record
mapping.write_text(json.dumps(record,indent=2)+'\n')
print(f'UUID {uuid}: {len(resolved)}/{len(addresses)} addresses resolved; original unchanged')
