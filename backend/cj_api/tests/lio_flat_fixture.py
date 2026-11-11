"""Build new supplier fixtures from explicitly declared test facts, never live data."""
from copy import deepcopy


def flat_fixture(value):
    value=deepcopy(value)
    result={key:value[key] for key in ('intent','reply','needs_tools','city','current_source_index','duration_days','field_sources')}
    result.update(version='LIO-planning-intake.5',start_date=None,party_size=None,unknown_fields=[],uncertain_fields={},
        fixed_items=[],extra_fields={},extra_unknown_fields=[],extra_uncertain_fields={},unresolved=[],long_term_requests=[])
    def scalar(obs,path,unknown,uncertain):
        if obs['state']=='unknown':unknown.append(path)
        elif obs['state']=='uncertain':uncertain[path]=obs['note']
        return obs['value'] if obs['state']=='known' else None
    if value['extraction'] is None:return result
    fields=value['extraction']['fields']
    result['start_date']=scalar(value['start_date'],'start_date',result['unknown_fields'],result['uncertain_fields'])
    result['party_size']=scalar(fields.get('party_size',{'state':'missing'}),'party_size',result['unknown_fields'],result['uncertain_fields'])
    result['unresolved']=value['extraction']['unresolved'];result['long_term_requests']=value['extraction']['long_term_requests']
    for item in fields.get('fixed_items',[]):
        fixed={key:item[key] for key in ('kind','label','detail_refs','applies_to')}
        fixed.update(source_index=item['source_ref']['source_index'],quote=item['source_ref']['quote'],unknown_fields=[],uncertain_fields={})
        for key in ('locked','booking_status'):
            fixed[key]=scalar(item[key],key,fixed['unknown_fields'],fixed['uncertain_fields'])
        for edge in ('start','end'):
            for part in ('date','time','timezone','place'):
                key=edge+'_'+part;fixed[key]=scalar(item[edge][part],key,fixed['unknown_fields'],fixed['uncertain_fields'])
        result['fixed_items'].append(fixed)
    for key,item in fields.items():
        if key in ('party_size','fixed_items'):continue
        if key in ('arrival','departure','overseas_departure'):
            result['extra_fields'][key]={part:scalar(item.get(part,{'state':'missing'}),key+'.'+part,result['extra_unknown_fields'],result['extra_uncertain_fields']) for part in ('date','time','timezone','place')}
        elif key in ('companions','temporary_conditions'):result['extra_fields'][key]=item
        else:result['extra_fields'][key]=scalar(item,key,result['extra_unknown_fields'],result['extra_uncertain_fields'])
    return result
