"""Read-only accounting over all original operations, never a ledger or permit."""
from decimal import Decimal

from .plan import require, is_sha


def costs(accounting,pricing):
    """All monetary data is tied to source-produced native rows by the host.

    A known subtotal is not full coverage. Empty queues/foreground completion do
    not close producers. Missing invoices are expected UNKNOWN, not a zero bill.
    """
    require(type(accounting)is dict,'original accounting required')
    require(type(pricing['scale'])is int and pricing['scale']>0,'original integer monetary scale required')
    require(is_sha(pricing['source_sha256']),'actual pricing source required')
    require(all(type(pricing[key])is int and pricing[key]>=0
                for key in ('model_input_per_token','model_output_per_token')),'original integer token rates required')
    rows=accounting['attempts'];require(type(rows)is list,'all original attempt rows required')
    seen=set();held=0;model_tokens=0;priced_tools=0;unknown_models=0;unknown_tools=0;unresolved=0
    for row in rows:
        require(type(row)is dict,'original financial row required')
        identity=(row['ledger_id'],row['attempt_id'])
        require(all(type(value)is str and value for value in identity)and identity not in seen,'distinct native financial attempt required')
        seen.add(identity)
        require(row['kind'] in pricing['limits'],'unknown financial kind cannot be priced as free')
        require(type(row['conservative_units'])is int and row['conservative_units']>=0,'original held/charged amount required')
        require(is_sha(row['actual_wire_input_sha256'])and row['native_binding_verified']is True,'original Meter/wire/fee association required')
        held+=row['conservative_units']
        receipt=row['receipt']
        if row['kind']=='model':
            usage=None if type(receipt)is not dict else receipt.get('usage')
            values=None if type(usage)is not dict else [usage.get(k)for k in ('prompt_tokens','completion_tokens','total_tokens')]
            priceable=(row['state']=='RECEIVED'and values is not None
                and all(type(v)is int and v>=0 for v in values)and 0<values[2]==values[0]+values[1]
                and all(receipt.get(k)==pricing[k]for k in ('model_id','endpoint','region')))
            if priceable:
                estimated=values[0]*pricing['model_input_per_token']+values[1]*pricing['model_output_per_token']
                require(row['conservative_units']>=estimated,'original charge cannot be below verified token cost')
                model_tokens+=estimated
            else:unknown_models+=1
        elif row['state']=='RECEIVED'and row['priceable_tool_units']is not None:
            require(type(row['priceable_tool_units'])is int and row['priceable_tool_units']>=0,'original tool price units required')
            require(row['conservative_units']>=row['priceable_tool_units'],'original tool charge below verified tool price')
            priced_tools+=row['priceable_tool_units']
        else:unknown_tools+=1
        if row['state']!='RECEIVED' or row['kind']=='model'and not priceable:
            unresolved+=1
            hold=pricing['limits'][row['kind']]['hold_per_attempt_units']
            require(type(hold)is int and hold>=0 and row['conservative_units']>=hold,'unresolved original hold must remain')
    complete=(accounting.get('coverage')=='complete'and accounting.get('producer_closure_verified')is True
              and type(accounting.get('closure_ref'))is str and bool(accounting['closure_ref'])
              and accounting.get('missing')==[])
    scale=Decimal(pricing['scale'])
    money=lambda units:format(Decimal(units)/scale,'f')
    return dict(conservative_cny=money(held)if complete else None,
        token_estimate_cny=money(model_tokens+priced_tools)if complete and not unknown_models and not unknown_tools else None,
        actual_paid_cny=None,actual_paid_status='UNKNOWN_NO_INVOICE',
        observed_conservative_cny=money(held),known_model_token_subtotal_cny=money(model_tokens),
        known_tool_estimate_subtotal_cny=money(priced_tools),unknown_model_attempts=unknown_models,
        unknown_tool_prices=unknown_tools,attempt_count=len(rows),full_coverage=complete,
        unresolved_attempt_count=unresolved,
        note='Native original rows, including failures/UNKNOWN/background. Expected missing supplier invoices do not imply free calls or operational UNKNOWN.')
