"""Bounded capture of ordinary App originals; never an alternate send path.

The operator precreates the 0600 policy, lock and empty claim file in an owned
0700 directory. Each frozen input slot is consumed by one genuine worker RUN.
App-generated message IDs are retained, not replaced with evaluation IDs.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import time
from psycopg import Error as DatabaseError

from cj_strict_json import reject_duplicates
from cj_usage.authorization_budget import canonical, HK_PRODUCER
from cj_usage.sublimits import scope_hash
from cj_usage.metered_exit import BudgetUnknown
from .local_app import ISSUER, scope_for
from .runtime_private import read_private, private_directory
from .tool_evidence import ToolEvidence


VERSION = 'G2C-App-smoke-capture.1'
CLAIMS = 'G2C-App-smoke-claims.1'
_SHA = re.compile('[0-9a-f]{64}')


def _json(raw):
    return json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate smoke field'))


class AppSmokeCapture:
    def __init__(self, policy_path, subjects, registrations, database, budget, *, clock=time.time):
        self.policy_path = Path(policy_path)
        self.raw = read_private(self.policy_path, 65536)
        self.policy = p = _json(self.raw)
        keys = {'version', 'window_id', 'source_commit', 'app_source', 'plan_sha256', 'starts_at', 'ends_at',
                'directory', 'directory_device', 'directory_inode', 'evidence_manifest', 'evidence_sha256',
                'artifact_device','artifact_inode','slots', 'ledger_id', 'producer_id'}
        if (type(p) is not dict or set(p) != keys or p['version'] != VERSION
                or type(p['window_id']) is not str or re.fullmatch('[A-Za-z0-9_-]{1,100}', p['window_id']) is None
                or any(type(p[k]) is not str or re.fullmatch('[0-9a-f]{40}', p[k]) is None
                       for k in ('source_commit', 'app_source'))
                or any(type(p[k]) is not int or p[k] < 0 for k in ('directory_device', 'directory_inode','artifact_device','artifact_inode'))
                or type(p['evidence_sha256']) is not str or _SHA.fullmatch(p['evidence_sha256']) is None
                or type(p['plan_sha256']) is not str or _SHA.fullmatch(p['plan_sha256']) is None
                or any(type(p[k]) is not str or not Path(p[k]).is_absolute()
                       for k in ('directory', 'evidence_manifest'))
                or type(p['slots']) is not list or not 1 <= len(p['slots']) <= 12):
            raise ValueError('explicit bounded App smoke policy required')
        start, end = (datetime.fromisoformat(p[k]) for k in ('starts_at', 'ends_at'))
        if start.tzinfo is None or end.tzinfo is None or not 0 < (end-start).total_seconds() <= 5400:
            raise ValueError('bounded App smoke time required')
        self.start, self.end, self.clock = start.timestamp(), end.timestamp(), clock
        self.slots = []
        owners, names = set(), set()
        for slot in p['slots']:
            if (type(slot) is not dict or set(slot) != {'slot_id', 'nonce', 'subject', 'locale', 'protocol', 'text_sha256', 'setup', 'conversation_mode', 'prior_slot_id'}
                    or type(slot['slot_id']) is not str or re.fullmatch('[A-Za-z0-9_.-]{1,80}', slot['slot_id']) is None
                    or type(slot['nonce']) is not str or re.fullmatch('[0-9a-f]{32}',slot['nonce']) is None
                    or slot['slot_id'] in names or type(slot['subject']) is not str or slot['subject'] not in subjects
                    or slot['locale'] not in ('zh', 'en') or slot['protocol'] not in ('LIO-message.1', 'LIO-message.2')
                    or type(slot['text_sha256']) is not str or _SHA.fullmatch(slot['text_sha256']) is None
                    or type(slot['setup']) is not bool or slot['conversation_mode'] not in ('new', 'default', 'continuation')
                    or (slot['conversation_mode']=='continuation' and (type(slot['prior_slot_id']) is not str or
                        not any(x['slot_id']==slot['prior_slot_id'] and x['subject']==slot['subject'] for x in self.slots)))
                    or (slot['conversation_mode']!='continuation' and slot['prior_slot_id'] is not None)
                    or (slot['protocol']=='LIO-message.1') != (slot['conversation_mode']=='default')):
                raise ValueError('fixed ordinary Home smoke slot required')
            names.add(slot['slot_id']); owners.add(slot['subject'])
            self.slots.append(dict(slot, scope=scope_for(ISSUER, slot['subject'])))
        if (len(owners) != 2 or sum(not x['setup'] for x in self.slots) != 8
                or sum(x['setup'] for x in self.slots) > 4
                or {x['locale'] for x in self.slots}!={'zh','en'}
                or any(sum(x['subject']==owner and not x['setup'] for x in self.slots)!=4
                       or sum(x['subject']==owner and x['setup'] for x in self.slots)>2
                       or len({x['locale'] for x in self.slots if x['subject']==owner})!=1 for owner in owners)):
            raise ValueError('two owners, eight App messages and at most four setup messages required')
        self.scopes = frozenset(x['scope'] for x in self.slots)
        if (budget.ledger_id, budget.producer) != (p['ledger_id'], p['producer_id']) or budget.producer != HK_PRODUCER:
            raise ValueError('original Hong Kong smoke budget required')
        with budget.connect() as journal:
            journal.execute('BEGIN'); budget.require_producer(journal)
            for scope in self.scopes:
                row=journal.execute('SELECT line FROM scope_sublimit WHERE scope_hash=?',(scope_hash(scope),)).fetchone()
                if row!=('C',):
                    raise ValueError('only original C allocation may enter App smoke capture')
        self.directory = Path(p['directory'])
        self.digest = sha256(self.raw).hexdigest()
        self.database, self.original_registrations = database, registrations
        self.evidence = ToolEvidence.load(p['evidence_manifest'], subjects, clock=clock,
                                         runtime_selection=self.selects)
        if (self.evidence.runtime_scopes != self.scopes or self.evidence.source_commit != p['source_commit']
                or self.evidence.expires_at != self.end or not self.evidence.model_enabled
                or not self.evidence.tools_enabled):
            raise ValueError('same-source App smoke evidence required')
        self._guard()
        with self._locked(False) as directory:
            retained=self._claims(directory)
        self.known={(x['binding']['message_id'],x['binding']['run_id']) for x in retained['claims']}

    def _guard(self):
        if not self.start <= self.clock() < self.end:
            raise BudgetUnknown('App smoke window is not active')
        if read_private(self.policy_path, 65536) != self.raw:
            raise BudgetUnknown('App smoke policy changed')
        if sha256(read_private(self.policy['evidence_manifest'],131072)).hexdigest()!=self.policy['evidence_sha256']:
            raise BudgetUnknown('App smoke evidence policy changed')
        with private_directory(self.evidence.directory,BudgetUnknown('App smoke artifact directory authority changed')) as directory:
            info=os.fstat(directory)
            if (info.st_dev,info.st_ino)!=(self.policy['artifact_device'],self.policy['artifact_inode']):
                raise BudgetUnknown('App smoke artifact directory replaced')

    def _locked(self, write):
        from contextlib import contextmanager
        @contextmanager
        def locked():
            with private_directory(self.directory, BudgetUnknown('App smoke directory authority changed')) as directory:
                info = os.fstat(directory)
                if (info.st_dev, info.st_ino) != (self.policy['directory_device'], self.policy['directory_inode']):
                    raise BudgetUnknown('App smoke directory replaced')
                fd = os.open('claims.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                        raise BudgetUnknown('App smoke lock authority changed')
                    fcntl.flock(fd, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                    yield directory
                finally:
                    os.close(fd)
        return locked()

    def _claims(self, directory):
        value = _json(read_private('claims.json', 65536, directory_fd=directory))
        if (type(value) is not dict or set(value) != {'version', 'policy_sha256', 'claims'}
                or value['version'] != CLAIMS or value['policy_sha256'] != self.digest
                or type(value['claims']) is not list or len(value['claims']) > len(self.slots)):
            raise BudgetUnknown('original App smoke claims required')
        used = set()
        identities = set()
        for row in value['claims']:
            if (type(row) is not dict or set(row) != {'slot_id', 'binding', 'input_sha256', 'canonical_sha256', 'producer_return'}
                    or type(row['slot_id']) is not str or row['slot_id'] in used or type(row['binding']) is not dict
                    or set(row['binding']) != {'scope', 'conversation_id', 'generation', 'message_id', 'run_id', 'message_sequence'}
                    or any(type(row[k]) is not str or _SHA.fullmatch(row[k]) is None for k in ('input_sha256', 'canonical_sha256'))):
                raise BudgetUnknown('invalid retained App smoke claim')
            from cj_run.core import Binding
            Binding(**row['binding'])
            witness=row['producer_return']
            if witness is not None:
                fields={'version','producer','source_commit','status','event_sequence','acknowledged','observed_at','cost_coverage'}
                if (type(witness) is not dict or set(witness)!=fields
                        or witness['version']!='G2C-App-smoke-producer-return.1'
                        or witness['producer']!='hk.entrypoint.run_worker.run_once.returned'
                        or witness['source_commit']!=self.policy['source_commit']
                        or witness['status'] not in ('completed','failed','cancelled','context_invalid','unknown')
                        or type(witness['event_sequence']) is not int or witness['event_sequence']<1
                        or witness['acknowledged'] is not True or witness['cost_coverage']!='NOT_ASSERTED'
                        or type(witness['observed_at']) is not str
                        or datetime.fromisoformat(witness['observed_at']).tzinfo is None):
                    raise BudgetUnknown('invalid retained App smoke producer return')
            slot = next((x for x in self.slots if x['slot_id'] == row['slot_id']), None)
            identity = (row['binding']['scope'], row['binding']['message_id'])
            if slot is None or row['binding']['scope'] != slot['scope'] or identity in identities:
                raise BudgetUnknown('retained App smoke owner changed')
            used.add(row['slot_id']); identities.add(identity)
        return value

    def _save(self, directory, value):
        # A leftover pending file is an uncertain prior write, never permission
        # to erase/reset the counter or blindly retry publication.
        fd=os.open('claims.pending',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        with os.fdopen(fd,'wb') as output:
            output.write(canonical(value));output.flush();os.fsync(output.fileno())
        os.replace('claims.pending','claims.json',src_dir_fd=directory,dst_dir_fd=directory)
        os.fsync(directory)

    def _original(self, binding):
        with self.database.connect(binding.scope) as db:
            db.execute('SET TRANSACTION READ ONLY')
            row = db.execute('SELECT demo_dialogue_protocol,lio_wire_protocol,lio_wire_input,demo_dialogue_locale,'
                'demo_dialogue_input_sha256,raw_input,input_sha256 '
                'FROM cj_message_receipt WHERE scope=%s AND message_id=%s AND run_id=%s '
                'AND conversation_id=%s AND generation=%s AND sequence=%s',
                (binding.scope, binding.message_id, binding.run_id, binding.conversation_id,
                 binding.generation, binding.message_sequence)).fetchone()
        if row is None or row[0] != 'LIO-message.1' or row[1:3] != (None, None):
            raise BudgetUnknown('ordinary legacy Lio original required; native3/4 is separate')
        raw = bytes(row[5]); value = _json(raw)
        if (sha256(raw).hexdigest() != row[6] or type(value) is not dict or type(value.get('text')) is not str
                or row[3] not in ('zh', 'en') or type(row[4]) is not str or _SHA.fullmatch(row[4]) is None):
            raise BudgetUnknown('ordinary App original changed')
        # v1/v2 persist the exact outer digest, not its bytes/version. Do not
        # reconstruct or attest outer bytes here. C joins A's real INTENT bytes
        # against this digest before deciding the actual Home protocol passed.
        return row[3], sha256(value['text'].encode()).hexdigest(), row[4], row[6]

    def registrations(self, binding):
        if binding.scope not in self.scopes:
            return self.original_registrations
        try:
            return self._registrations(binding)
        except FileExistsError:
            raise BudgetUnknown('App smoke uncertain prior claim write; reconcile only') from None
        except DatabaseError:
            raise BudgetUnknown('App smoke original database unavailable') from None
        except (OSError,ValueError):
            raise BudgetUnknown('App smoke retained authority unavailable') from None

    def _registrations(self,binding):
        self._guard()
        locale, text, wire, canonical_sha = self._original(binding)
        original = asdict(binding)
        with self._locked(True) as directory:
            value = self._claims(directory)
            prior = next((x for x in value['claims'] if (x['binding']['scope'], x['binding']['message_id']) ==
                          (binding.scope, binding.message_id)), None)
            if prior is not None:
                if prior['binding'] != original or (prior['input_sha256'],prior['canonical_sha256']) != (wire,canonical_sha):
                    raise BudgetUnknown('App smoke original binding changed')
            else:
                used = {x['slot_id'] for x in value['claims']}
                slot = next((x for x in self.slots if x['scope'] == binding.scope and x['slot_id'] not in used), None)
                if slot is None or (locale, text) != (slot['locale'], slot['text_sha256']):
                    raise BudgetUnknown('App smoke input outside next fixed slot')
                from cj_message.demo_dialogue import _identity, lio_conversation
                if slot['conversation_mode']=='new':
                    if binding.message_sequence!=1 or binding.conversation_id!='lio-dialogue-'+_identity(binding.scope,'lio-new:'+binding.message_id):
                        raise BudgetUnknown('App smoke new conversation required')
                elif slot['conversation_mode']=='default':
                    if binding.conversation_id!=lio_conversation(binding.scope):
                        raise BudgetUnknown('App smoke default conversation changed')
                else:
                    previous=next((x for x in value['claims'] if x['slot_id']==slot['prior_slot_id']),None)
                    if previous is None or (binding.conversation_id,binding.generation,binding.message_sequence)!=(
                            previous['binding']['conversation_id'],previous['binding']['generation'],previous['binding']['message_sequence']+1):
                        raise BudgetUnknown('App smoke seed continuation changed')
                value['claims'].append(dict(slot_id=slot['slot_id'], binding=original, input_sha256=wire,
                                          canonical_sha256=canonical_sha,producer_return=None))
                self._save(directory,value)
        self._guard()
        self.known.add((binding.message_id,binding.run_id))
        return self.original_registrations

    def selects(self, binding):
        if binding.scope not in self.scopes:
            return False
        self._guard()
        with self._locked(False) as directory:
            value = self._claims(directory)
            return any(row['binding'] == asdict(binding) for row in value['claims'])

    def claims_snapshot(self):
        """Typed control metadata only; callers still need native read AUTH.

        Returning this snapshot does not grant raw-original access, attest an
        App binary, or certify the financial lifecycle. The qualified reader
        must join each retained binding to its native receipt and current AUTH.
        """
        self._guard()
        with self._locked(False) as directory:
            result=canonical(self._claims(directory))
        self._guard()
        return result

    def reflection(self, binding):
        return None

    def exit_observer(self, binding):
        return None

    def completed(self, outcomes):
        """Witness the actual synchronous worker return, not a queue-idle guess.

        This composition passes no background_jobs to run_once. A witness does
        not settle any operation or certify complete cost: the reader must also
        reconcile every original Meter/fee and associated Memory/background job.
        """
        if not any((x.message_id,x.run_id) in self.known for x in outcomes):return
        self._guard()
        with self._locked(True) as directory:
            value=self._claims(directory);changed=False
            for row in value['claims']:
                b=row['binding']
                outcome=next((x for x in outcomes if (x.message_id,x.run_id)==(b['message_id'],b['run_id'])),None)
                if outcome is None or row['producer_return'] is not None:continue
                with self.database.connect(b['scope']) as db:
                    db.execute('SET TRANSACTION READ ONLY')
                    status=db.execute('SELECT r.status,r.event_sequence,d.acknowledged FROM cj_run_record r '
                        'JOIN cj_message_delivery d ON (r.scope,r.run_id,r.message_id)=(d.scope,d.run_id,d.message_id) '
                        'WHERE r.scope=%s AND r.run_id=%s AND r.message_id=%s',
                        (b['scope'],b['run_id'],b['message_id'])).fetchone()
                if status is None or status[0]!=outcome.status or status[0] not in (
                        'completed','failed','cancelled','context_invalid','unknown') or status[2] is not True:
                    raise BudgetUnknown('App smoke original worker return not acknowledged')
                row['producer_return']=dict(version='G2C-App-smoke-producer-return.1',
                    producer='hk.entrypoint.run_worker.run_once.returned',source_commit=self.policy['source_commit'],
                    status=status[0],event_sequence=status[1],acknowledged=status[2],
                    observed_at=datetime.fromtimestamp(self.clock(),timezone.utc).isoformat(),
                    cost_coverage='NOT_ASSERTED')
                changed=True
            if changed:self._save(directory,value)
