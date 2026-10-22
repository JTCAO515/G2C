"""Pure display projection of public immutable Draft/Change, never proposal export."""
import base64,json
from fastapi.responses import JSONResponse
from .generated import ManualPreviewResponse
from .trip_projection import trip_projection,content_projection

def encode_response(session,request_id,trip_domain):
    draft=session.draft
    if session.status!='LOCAL' or session.can_save is not False or draft.protection_status!='UNKNOWN':
        raise ValueError('Only unsaved local preview with unknown protection is supported')
    document,after=content_projection(draft.content,trip_domain)
    changes=[{'path':list(c.path),'before_utf8_base64':base64.b64encode(c.before).decode(),
              'after_utf8_base64':base64.b64encode(c.after).decode()} for c in draft.diff]
    value={'preview_status':session.status,'original':trip_projection(draft.original,trip_domain).model_dump(mode='json'),
        'content_utf8_base64':after,'document':document.model_dump(mode='json'),'selected_ids':list(draft.selected_ids),
        'title_selected':draft.title_selected,'protection_status':draft.protection_status,'can_save':session.can_save,'diff':changes}
    return JSONResponse(ManualPreviewResponse.model_validate_json(json.dumps({'request_id':request_id,'preview':value}),strict=True).model_dump(mode='json')).body
