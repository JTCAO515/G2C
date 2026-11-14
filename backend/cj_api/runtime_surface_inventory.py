"""Private exhaustive per-MESSAGE input/output collection for disclosure scans.

This is not an E metadata response. Bytes may contain a detected leak and must
remain with the trusted observer; only a separately qualified digest view may
be published. Missing evidence is explicit, never an observed empty surface.
"""
import base64
from hashlib import sha256

from runtime_adapter.contract import decode,encode,Unavailable


VERSION='G2C-runtime-surface-inventory.1'


class NativeSurfaceInventory:
    def __init__(self,originals,token_supplier,*,guard):
        self.originals,self.token_supplier,self.guard=originals,token_supplier,guard

    @staticmethod
    def _surface(raw):
        return dict(sha256=sha256(raw).hexdigest(),bytes_base64=base64.b64encode(raw).decode('ascii'))

    def collect(self,message_id):
        self.guard()
        token=self.token_supplier();before=self.originals.inventory(token,message_id)
        inventory=decode(before)
        visible=self.originals.visible_original(token,message_id)
        view=decode(visible);entries=[];missing=[]
        surfaces=[dict(source_kind='message_input',source_id=message_id,**view['input'])]
        surfaces.extend(dict(source_kind='run_event',source_id=str(event['sequence']),
            event_kind=event['kind'],**event['value'])for event in view['events'])
        if inventory['status']not in('completed','failed','cancelled'):
            missing.append(dict(field='terminal_run'))
        if view['tail']['delivery_acknowledged']is not True:
            missing.append(dict(field='delivery_acknowledgement'))
        for job in view['tail']['associated_history_jobs']:
            missing.append(dict(field='associated_history_surfaces',job_id=job['job_id'],attempt_id=job['attempt_id']))
        for operation in inventory['operations']:
            op=operation['operation_id'];kind=operation['kind']
            # Native AUTH/erasure failures withhold the complete collection.
            # Only absent capture files are nullable incomplete evidence.
            logical=self.originals.input(token,message_id,op)
            surfaces.append(dict(source_kind='logical_input',source_id=op,**self._surface(logical)))
            row=dict(operation_id=op,attempt_id=operation['attempt_id'],
                registration_id=operation['registration_id'],kind=kind,
                logical_input=self._surface(logical),output=None,wire_input=None)
            try:artifact=decode(self.originals.artifact(token,message_id,op))
            except FileNotFoundError:missing.append(dict(operation_id=op,field='output'))
            else:
                row['output']=self._surface(artifact['result_utf8'].encode('utf-8'))
                surfaces.append(dict(source_kind='provider_output',source_id=op,**row['output']))
            if kind in ('model','memory'):
                try:wire=decode(self.originals.artifact(token,message_id,op,wire_input=True))
                except FileNotFoundError:missing.append(dict(operation_id=op,field='wire_input'))
                else:
                    row['wire_input']=self._surface(wire['wire_input_utf8'].encode('utf-8'))
                    surfaces.append(dict(source_kind='model_wire_input',source_id=op,**row['wire_input']))
            entries.append(row)
        if self.originals.inventory(token,message_id)!=before:
            raise Unavailable('ORIGINAL_SURFACE_INVENTORY_CHANGED')
        if self.originals.visible_original(token,message_id)!=visible:
            raise Unavailable('ORIGINAL_VISIBLE_SURFACES_CHANGED')
        self.guard()
        return encode(dict(version=VERSION,message_id=message_id,run_id=inventory['run_id'],
            native_inventory_sha256=sha256(before).hexdigest(),
            visible_original=self._surface(visible),operations=entries,surfaces=surfaces,missing=missing,
            evidence_status='UNKNOWN'if missing else'COMPLETE',
            coverage_scope='NATIVE_MESSAGE_RUN_AND_OBSERVED_ASSOCIATED_HISTORY',
            privacy_scope='TRUSTED_OBSERVER_ONLY_NO_PUBLICATION'))
