"""Public-price estimate for complete Beijing receipts, never an invoice.

No implicit-cache/free-credit/discount assumption, no reservation release, and
no effect on B's actual spending/authorization guard.
"""
from decimal import Decimal

SOURCE='https://help.aliyun.com/zh/model-studio/qwen3-8-flash'
AS_OF='2026-11-05'
INPUT=Decimal('0.8')
OUTPUT=Decimal('2.7')


def token_estimate(attempts):
    known=0;unknown=0;input_tokens=0;output_tokens=0
    for row in attempts:
        if row['kind']!='model':continue
        receipt=row.get('receipt')
        usage=None if receipt is None else receipt.get('usage')
        if (row['state']!='RECEIVED' or not isinstance(usage,dict)
                or receipt.get('model_id')!='qwen3.8-flash'
                or receipt.get('region')!='cn-beijing'):
            unknown+=1;continue
        values=[usage.get(k) for k in ('prompt_tokens','completion_tokens','total_tokens')]
        if any(type(v)is not int or v<0 for v in values) or values[2]!=values[0]+values[1]:
            unknown+=1;continue
        known+=1;input_tokens+=values[0];output_tokens+=values[1]
    subtotal=(Decimal(input_tokens)*INPUT+Decimal(output_tokens)*OUTPUT)/Decimal(1000000)
    return dict(currency='CNY',basis='estimated_public_price_not_billed',source=SOURCE,source_as_of=AS_OF,
        model='qwen3.8-flash',region='cn-beijing',input_per_million=str(INPUT),output_per_million=str(OUTPUT),
        complete_model_receipts=known,unknown_model_attempts=unknown,prompt_tokens=input_tokens,completion_tokens=output_tokens,
        known_receipt_subtotal_cny=str(subtotal),entire_model_estimate_cny=str(subtotal) if known and not unknown else None,
        actual_billed_cny='UNKNOWN',tool_monetary_cost='UNKNOWN',
        exclusions='Incomplete windows, tools, cache discounts, credits and invoice adjustments are not inferred; UNKNOWN holds stay reserved')
