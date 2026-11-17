"""Trusted native simulator composition; no public product route or new exit.

Only B's owned manifest supplies identities, directories and resource pins.
The original C runner/renderer stay in their frozen package. DUT input receives
only the renderer's ordinary text; actor profile/system never become a DUT pin.
"""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
import os
import sqlite3
import psycopg
from threading import RLock, Event, Thread
from time import monotonic, sleep
import uuid

from cj_agent.provider import M4_NATIVE_TURN_BUFFERED
from cj_message.auth_boundary import Boundary
from cj_strict_json import compact
from cj_usage.authorization_budget import CNY_SCALE, canonical
from runtime_adapter.contract import Unavailable, Invalid, decode, require, error_code
from cj_usage.metered_exit import BudgetUnknown
from eval.lio_simulated_user.core import (
    PERSONAS, SIMULATOR_SYSTEM, InputError, actor_output_schema, load_profiles,
    plan as cohort_plan, render_choice)
from eval.lio_simulated_user.runner import HostUnavailable, run_episode

from .local_account_admission_v2 import account_checker_for, retired_in_transaction
from .local_app import ISSUER, scope_for
from .local_worker_context import checker_factory_for
from .runtime_actor import ActorSpecification, actor_registration
from .runtime_actor_host import NativeActorHost, ActorChoiceInvalid
from .runtime_actor_originals import ActorOriginals
from .runtime_actor_source import ActorDutSource
from .runtime_authority import RuntimeAuthority
from .runtime_model import configured_model
from .runtime_originals import RuntimeOriginals
from .runtime_private import read_private, private_directory, PrivateFileError
from .runtime_simulator_baseline import BaselineDutSpecification
from .runtime_simulator_dut import DutSpecification, NativeSimulatorDut
from .runtime_simulator_episode import EpisodeLinks, run_native_episode
from .runtime_simulator_requests import SimulatorRunRequests
from .runtime_simulator_cost import original_charges, recheck_charge_metadata
from .runtime_worker_bindings import pinned_directory
from .tool_evidence import ToolEvidence


VERSION = 'G2C-native-simulator-host.1'


class NativeSimulatorHost:
    def __init__(self, path, runtime, services, tools, *, clock=monotonic,
                 wall_clock=lambda: datetime.now(timezone.utc)):
        self.path = Path(path)
        self.raw = read_private(self.path, 131072)
        data = decode(self.raw)
        fields = {'version', 'window_id', 'mode', 'runtime_card', 'actor_model',
                  'evidence_manifest', 'results_directory', 'starts_at', 'ends_at',
                  'episode_seconds', 'identities'}
        require(type(data) is dict and set(data) == fields and data['version'] == VERSION,
                'SIMULATOR_HOST_MANIFEST')
        require(type(data['window_id']) is str and
                re.fullmatch('[A-Za-z0-9_-]{1,96}', data['window_id']) is not None,
                'SIMULATOR_HOST_WINDOW')
        require(data['mode'] in ('legacy2', 'native4'), 'SIMULATOR_HOST_PROTOCOL')
        require(type(data['episode_seconds']) is int and 0 < data['episode_seconds'] <= 1800,
                'SIMULATOR_HOST_EPISODE_BOUND')
        require(all(type(data[k]) is str for k in ('starts_at', 'ends_at')),
                'SIMULATOR_HOST_TIME_FORMAT')
        start, end = (datetime.fromisoformat(data[k]) for k in ('starts_at', 'ends_at'))
        require(start.tzinfo is not None and end.tzinfo is not None and
                0 < (end - start).total_seconds() <= 7200, 'SIMULATOR_HOST_TIME_BOUND')
        self.start, self.end = start, end
        self.data, self.runtime, self.services, self.tools = data, runtime, services, tools
        self.clock, self.wall_clock = clock, wall_clock
        self.database = runtime.database()
        require(type(data['evidence_manifest']) is str and Path(data['evidence_manifest']).is_absolute(),
                'SIMULATOR_HOST_EVIDENCE_PATH')
        self.directory = pinned_directory(data['results_directory'])
        self.directory_identity = (data['results_directory']['device'], data['results_directory']['inode'])
        self.lock = RLock()
        self.execution_lock = RLock()
        self.worker_ready = Event()
        self.worker_failed = Event()
        self.cohort_thread = None
        self.sessions, self.episodes, self.by_message = {}, {}, {}
        self.active = None
        self.stopped = False
        self.next_slot = 0
        card = data['runtime_card']
        require(type(card) is dict and set(card) == {'code_sha', 'image_digest', 'model'} and
                card['model'] == configured_model(services.model, M4_NATIVE_TURN_BUFFERED),
                'SIMULATOR_HOST_ACTUAL_MODEL_CHANGED')
        self.actor_spec = ActorSpecification(PERSONAS.read_bytes(), SIMULATOR_SYSTEM,
            compact(actor_output_schema(), sort_keys=True), compact(dict(
                code_sha=card['code_sha'], image_digest=card['image_digest'], model=data['actor_model'])))
        # Registration construction validates the real actor endpoint/model and
        # effective parameters without invoking or reserving a provider.
        actor_registration(tools, self.actor_spec)
        dataset, digest = load_profiles()
        self.cohort = cohort_plan(dataset, digest)
        require(type(data['identities']) is list and len(data['identities']) == 2,
                'SIMULATOR_HOST_TWO_ORIGINAL_IDENTITIES')
        for entry in data['identities']:
            require(type(entry) is dict and set(entry) == {
                'locale', 'subject', 'token_file', 'canonical_directory'} and
                entry['locale'] in ('zh', 'en') and entry['locale'] not in self.sessions and
                type(entry['subject']) is str and entry['subject'] in runtime.demo_subjects and
                type(entry['token_file']) is str,
                'SIMULATOR_HOST_EXISTING_DEMO_IDENTITY')
            token_path = Path(entry['token_file'])
            require(token_path.is_absolute(), 'SIMULATOR_HOST_TOKEN_PATH')
            def token(path=token_path):
                raw = read_private(path, 4096).decode('ascii').strip()
                require(raw and all(0x21 <= ord(c) <= 0x7e for c in raw),
                        'SIMULATOR_HOST_ORIGINAL_TOKEN')
                return raw
            checker = account_checker_for(runtime.auth, self.database,
                                          selected_subjects=runtime.demo_subjects)
            builder = checker_factory_for(runtime.auth, selected_subjects=runtime.demo_subjects)
            def transactional(transaction, scope, factory=builder):
                return factory(retired_in_transaction(transaction.cur, scope))
            boundary = Boundary(checker, lambda principal: self.database.message_repository(
                scope_for(principal.issuer, principal.subject)), lambda: str(uuid.uuid4()),
                checker_in_transaction=transactional)
            owner = scope_for(ISSUER, entry['subject'])
            require(owner not in {s['scope'] for s in self.sessions.values()},
                    'SIMULATOR_HOST_DISTINCT_OWNERS')
            self.sessions[entry['locale']] = dict(scope=owner, token=token, checker=checker,
                boundary=boundary, directory=pinned_directory(entry['canonical_directory']))
        require(set(self.sessions) == {'zh', 'en'}, 'SIMULATOR_HOST_BILINGUAL_IDENTITIES')
        self.scopes = frozenset(s['scope'] for s in self.sessions.values())
        self.evidence = ToolEvidence.load(data['evidence_manifest'], runtime.demo_subjects,
                                         runtime_selection=self.selects,
                                         clock=lambda: self.wall_clock().timestamp())
        require(self.evidence.runtime_scopes == self.scopes and
                self.evidence.source_commit == card['code_sha'] and
                self.evidence.expires_at == end.timestamp() and
                self.evidence.model_enabled and self.evidence.tools_enabled,
                'SIMULATOR_HOST_EVIDENCE_BINDING')
        tools.tool_evidence = self.evidence
        self.cohort_failure = None

    def save(self, name, value):
        raw = compact(value, sort_keys=True)
        with private_directory(self.directory, Unavailable('SIMULATOR_RESULTS_DIRECTORY_CHANGED')) as directory:
            info = os.fstat(directory)
            require((info.st_dev, info.st_ino) == self.directory_identity,
                    'SIMULATOR_RESULTS_DIRECTORY_REPLACED')
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            with os.fdopen(fd, 'wb') as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            os.fsync(directory)

    def run_cohort(self):
        """One explicitly started original cohort; never resume an unknown run."""
        if not self.worker_ready.wait(30):
            self.stopped = True
            raise Unavailable('SIMULATOR_NATIVE_WORKER_NOT_READY')
        with self.lock:
            require(self.active is None and not self.stopped, 'SIMULATOR_COHORT_QUERY_ONLY')
            try:
                self.save('cohort.intent.json', dict(version=VERSION,
                    window_id=self.data['window_id'], source=self.data['runtime_card'],
                    dataset_sha256=self.cohort['dataset_sha256'], slots=self.cohort['slots']))
            except FileExistsError:
                self.stopped = True
                raise Unavailable('SIMULATOR_COHORT_ALREADY_ATTEMPTED_QUERY_ONLY') from None
            traces = []
            try:
                for slot in self.cohort['slots']:
                    episode = SimulatorEpisode(self, slot['profile_id'], slot['attempt'])
                    self.current(episode.specification, episode)
                    self.active = episode
                    key = (slot['profile_id'], slot['attempt'])
                    self.episodes[key] = episode
                    for mid in episode.specification.message_ids:
                        self.by_message[(episode.session['scope'], mid)] = episode
                    stage = episode.specification.stage
                    self.save(stage + '.intent.json', dict(version=VERSION,
                        profile_id=slot['profile_id'], attempt=slot['attempt'],
                        binding_sha256=episode.dut.owner.key,
                        dut_specification_sha256=episode.specification.key,
                        actor_specification_sha256=self.actor_spec.key))
                    candidate = self.data['mode'] + '-' + sha256(compact(
                        self.data['runtime_card'], sort_keys=True)).hexdigest()
                    trace = run_native_episode(episode.dut, episode.actor, episode.links,
                        episode.original_cost, candidate=candidate, evidence_layer='L2',
                        run_episode=run_episode, renderer=render_choice,
                        input_error=InputError, host_unavailable=HostUnavailable)
                    self.save(stage + '.trace.json', trace)
                    self.save(stage + '.cost.json', episode.last_cost_report)
                    traces.append(trace)
                    self.next_slot += 1
                    self.active = None
                    measurement_end = (trace['failure_owner'] is None and trace['end_reason'] in (
                        'evaluation_bound_before_observed_exploration_end', 'observed_exploration_end'))
                    if (not measurement_end or episode.last_cost_report['coverage'] != 'COMPLETE'):
                        self.stopped = True
                        break
                self.save('cohort.result.json', dict(version=VERSION,
                    status='STOP_NEW' if self.stopped else 'COHORT_EXECUTED_NOT_QUALITY_APPROVED',
                    completed_slot_count=len(traces), declared_slot_count=60,
                    unrun_slot_count=60-len(traces), source=self.data['runtime_card'],
                    actual_supplier_paid='UNKNOWN_NO_INVOICE'))
                return traces
            finally:
                self.stopped = True
                if self.active is not None:
                    self.active.closed = True
                    self.active.dut.stopped = True

    def current(self, specification, episode):
        if (self.stopped or episode.closed or read_private(self.path, 131072) != self.raw
                or (self.directory / 'STOP_NEW.json').exists()
                or (self.directory / 'STOP_NEW.json').is_symlink()
                or not self.start <= self.wall_clock() < self.end):
            raise Unavailable('SIMULATOR_HOST_NO_NEW_WORK')
        return specification.raw

    def begin(self):
        require(self.cohort_thread is None, 'SIMULATOR_COHORT_ALREADY_STARTED')
        self.cohort_thread = Thread(target=self._cohort_entry, name='g2c-native-simulator', daemon=True)
        self.cohort_thread.start()

    def worker_unavailable(self):
        self.stopped = True
        self.worker_failed.set()

    def _cohort_entry(self):
        try:
            self.run_cohort()
        except (Unavailable, Invalid, OSError, PrivateFileError, BudgetUnknown,
                sqlite3.OperationalError, psycopg.OperationalError):
            # Never print provider text, private manifest fields or credentials.
            # The original durable intent remains query-only after any failure.
            self.stopped = True
            self.cohort_failure = 'SIMULATOR_COHORT_STOPPED_QUERY_ONLY'

    def registrations(self, binding):
        episode = self.by_message.get((binding.scope, binding.message_id))
        if episode is not None:
            return episode.requests.registrations(binding)
        if binding.scope in self.scopes or binding.message_id.startswith('c936-'):
            return {}
        return self.tools.registrations

    def reflection(self, binding):
        episode = self.by_message.get((binding.scope, binding.message_id))
        if episode is not None:
            return episode.requests.reflection(binding)
        if binding.scope in self.scopes or binding.message_id.startswith('c936-'):
            from cj_usage.metered_exit import BudgetUnknown
            raise BudgetUnknown('original simulator message not selected')
        return None

    def exit_observer(self, binding):
        return None

    def selects(self, binding):
        episode = self.by_message.get((binding.scope, binding.message_id))
        if episode is not None:
            return episode.requests.selects(binding)
        if self.active is not None:
            for original in self.active.actor.originals:
                if original.argument.binding == binding:
                    self.active.actor._guard(read_only=True)
                    original.claim.read(binding.message_id)
                    return True
        return False

    def completed(self, outcomes):
        """Called only after the real entrypoint's synchronous run_once return.

        This records a producer boundary, not a financial or quality verdict.
        The normal registered exit and native acknowledged state remain required.
        """
        self.worker_ready.set()
        for outcome in outcomes:
            episode = next((value for (scope, mid), value in self.by_message.items()
                            if mid == outcome.message_id and scope == value.session['scope']), None)
            if episode is None:
                continue
            with self.database.connect(episode.session['scope']) as db:
                db.execute('SET TRANSACTION READ ONLY')
                row = db.execute('SELECT r.status,r.event_sequence,d.acknowledged '
                    'FROM cj_run_record r JOIN cj_message_delivery d '
                    'ON (r.scope,r.run_id,r.message_id)=(d.scope,d.run_id,d.message_id) '
                    'WHERE r.scope=%s AND r.run_id=%s AND r.message_id=%s',
                    (episode.session['scope'], outcome.run_id, outcome.message_id)).fetchone()
            require(row is not None and row[0] == outcome.status and row[2] is True,
                    'SIMULATOR_NATIVE_RETURN_NOT_ACKNOWLEDGED')
            witness = dict(version='G2C-native-simulator-producer-return.1',
                producer='hk.entrypoint.run_worker.run_once.returned',
                source_commit=self.data['runtime_card']['code_sha'],
                message_id=outcome.message_id, run_id=outcome.run_id,
                status=row[0], event_sequence=row[1], acknowledged=True,
                observed_at=self.wall_clock().isoformat(), cost_coverage='NOT_ASSERTED')
            key = (outcome.message_id, outcome.run_id)
            old = episode.returns.get(key)
            if old is not None:
                require({k: v for k, v in old.items() if k != 'observed_at'} ==
                        {k: v for k, v in witness.items() if k != 'observed_at'},
                        'SIMULATOR_NATIVE_RETURN_CHANGED')
            else:
                episode.returns[key] = witness

    def wait_original(self, receipt, deadline):
        episode = self.by_message.get((self.active.session['scope'], receipt.message_id))
        require(episode is self.active, 'SIMULATOR_WAIT_ORIGINAL_NOT_SELECTED')
        while self.clock() < deadline:
            if self.worker_failed.is_set():
                raise Unavailable('SIMULATOR_NATIVE_WORKER_UNAVAILABLE_QUERY_ONLY')
            episode.dut.authority.require(binding=episode.dut.owner,
                pins_sha256=episode.dut.specification.key, purpose='query',
                deadline=deadline, read_only=True)
            witness = episode.returns.get((receipt.message_id, receipt.run_id))
            if witness is not None:
                if witness['status'] != 'completed':
                    raise Unavailable('SIMULATOR_NATIVE_ORIGINAL_NOT_COMPLETED')
                return
            sleep(min(.1, max(0, deadline - self.clock())))
        raise Unavailable('SIMULATOR_NATIVE_ORIGINAL_WAIT_UNKNOWN')


class CapturedActorHost(NativeActorHost):
    def __init__(self, episode, *args, **kwargs):
        self.episode = episode
        super().__init__(*args, **kwargs)

    def choose(self, messages):
        # The actor and ordinary worker share the accepted provider/exit. Keep
        # their physical calls serial without creating another model account.
        with self.episode.host.execution_lock:
            try:
                choice = super().choose(messages)
            except ActorChoiceInvalid:
                self.episode.capture_actor_charge()
                raise
            self.episode.capture_actor_charge()
            return choice


class SimulatorEpisode:
    """One original frozen slot over the real worker and independent actor."""
    def __init__(self, host, profile_id, attempt):
        self.host = host
        self.profile = host.actor_spec.profile(profile_id)
        self.session = host.sessions[self.profile['locale']]
        self.closed = False
        self.returns = {}
        self.actor_charge_proofs = {}
        self.last_cost_report = None
        self.deadline = host.clock() + min(host.data['episode_seconds'],
            max(0, (host.end - host.wall_clock()).total_seconds()))
        stage = 'c936-slot-' + sha256(compact(
            [host.data['window_id'], profile_id, attempt])).hexdigest()
        mids = tuple('c936-' + sha256(compact([self.session['scope'], stage, i])).hexdigest()
                     for i in range(self.profile['behavior']['direct_after'] + 1))
        specification = BaselineDutSpecification if host.data['mode'] == 'legacy2' else DutSpecification
        self.specification = specification(stage, self.profile['opening'], self.profile['locale'],
                                            mids, compact(host.data['runtime_card']))
        def authority(pins):
            return RuntimeAuthority(self.session['checker'], self.session['token'],
                host.services.model.authorization, pins, lambda: host.current(pins, self),
                line='C', wall_clock=host.wall_clock, clock=host.clock)
        self.dut = NativeSimulatorDut(host.database, self.session['boundary'],
            authority(self.specification), self.specification, self.session['token'],
            self.session['directory'], host.wait_original, self,
            deadline=self.deadline, clock=host.clock)
        require(self.dut.owner.scope == self.session['scope'], 'SIMULATOR_HOST_ACTUAL_OWNER_CHANGED')
        self.source = ActorDutSource(self.session['boundary'], host.database)
        self.actor = CapturedActorHost(self, host.database, host.tools, self.source, host.actor_spec,
            authority(host.actor_spec), self.session['directory'], profile_id=profile_id,
            attempt=attempt, dut_message=lambda: self.dut.latest, deadline=self.deadline,
            clock=host.clock)
        require(self.actor.owner == self.dut.owner, 'SIMULATOR_HOST_ACTOR_DUT_OWNER_CHANGED')
        self.requests = SimulatorRunRequests(self.dut, host.tools)
        self.links = EpisodeLinks(self.session['directory'], self.actor.owner, host.actor_spec,
                                  guard=self.actor._guard)
        self.originals = RuntimeOriginals(self.session['boundary'], host.database,
            host.services.model.authorization, host.evidence.directory,
            query_original=lambda context, mid: context.query_lio_message(mid))
        self.actor_originals = ActorOriginals(self.actor, host.evidence.directory)
        self.before_journal = self.journal()
        self.before_background = self.background()

    def capture_actor_charge(self):
        # This happens before C's bridge releases the next ordinary DUT input.
        # Do not later reconstruct that past current-M frame to read raw bytes.
        original = self.actor.originals[-1]
        mid = original.argument.binding.message_id
        try:
            proof = original_charges(self.actor_originals, self.session['token'](), mid, 'actor')
        except (OSError, Invalid, BudgetUnknown, sqlite3.OperationalError) as error:
            raise Unavailable('SIMULATOR_ACTOR_ORIGINAL_CAPTURE_UNAVAILABLE') from error
        old = self.actor_charge_proofs.get(mid)
        require(old is None or old == proof, 'SIMULATOR_ACTOR_ORIGINAL_CAPTURE_CHANGED')
        self.actor_charge_proofs[mid] = proof

    def journal(self):
        budget = self.host.services.model.authorization
        with budget.connect() as db:
            db.execute('BEGIN')
            budget.require_producer(db)
            rows = db.execute('SELECT id,kind,input_sha,state,receipt FROM attempt ORDER BY id').fetchall()
        return dict(rows=rows, anchor=dict(count=len(rows), sha256=sha256(canonical(rows)).hexdigest()))

    def background(self):
        # This concrete worker mode supplies no independent background executor.
        # Changes in that native graph invalidate this qualification; they are
        # never silently treated as a zero-cost tail.
        with self.host.database.connect(self.session['scope']) as db:
            db.execute('SET TRANSACTION READ ONLY')
            return db.execute('SELECT job_id,attempt_id,run_id,state,prepared_input_sha256 '
                'FROM cj_run_background_job WHERE scope=%s ORDER BY job_id,attempt_id',
                (self.session['scope'],)).fetchall()

    def original_cost(self):
        """Close this real host before joining every original native charge."""
        self.closed = True
        self.dut.stopped = True
        try:
            token = self.session['token']()
            reports = []
            memory_tails = []
            for item in self.dut.originals:
                mid = item['step_id']
                report = original_charges(self.originals, token, mid, 'dut')
                witness = self.returns.get((mid, report['run_id']))
                require(witness is not None and witness['status'] == report['status'],
                        'SIMULATOR_DUT_PRODUCER_RETURN_MISSING')
                tail = decode(self.originals.cost_tail(token, mid))
                require(tail['delivery_acknowledged'] is True and
                        all(x['state'] in ('completed', 'cancelled')
                            for x in tail['associated_history_jobs']),
                        'SIMULATOR_MEMORY_PRODUCER_NOT_CLOSED')
                memory_tails.append(tail)
                reports.append(report)
            # NativeActorHost.choose runs synchronously inside C's unchanged
            # bridge. C invokes original_cost only after those calls have left
            # its loop; there is no independent actor worker or queued sender.
            for original in self.actor.originals:
                require(original.inspect() is not None, 'SIMULATOR_ACTOR_ORIGINAL_MISSING')
                mid = original.argument.binding.message_id
                proof = self.actor_charge_proofs.get(mid)
                require(proof is not None, 'SIMULATOR_ACTOR_RETURN_CAPTURE_MISSING')
                recheck_charge_metadata(self.actor_originals, token, proof)
                reports.append(proof)
            require(self.background() == self.before_background,
                    'SIMULATOR_UNQUALIFIED_BACKGROUND_PRODUCER')
            after = self.journal()
            old = {row[0]: row for row in self.before_journal['rows']}
            new = {row[0]: row for row in after['rows']}
            entries = [row for report in reports for row in report['operations']]
            ids = [row['attempt_id'] for row in entries]
            require(len(ids) == len(set(ids)), 'SIMULATOR_DUPLICATE_EPISODE_ATTEMPT')
            financial = {row['attempt_id'] for row in entries if row['financial_attempt']}
            require(set(new) - set(old) == financial and
                    all(new.get(key) == value for key, value in old.items()),
                    'SIMULATOR_WHOLE_JOURNAL_COVERAGE_UNKNOWN')
            self.dut.authority.require(binding=self.dut.owner,
                pins_sha256=self.specification.key, purpose='query',
                deadline=self.host.clock() + 30, read_only=True)
            conservative = sum(row['conservative_units'] for row in entries)
            estimates = [row['estimated_units'] for row in entries]
            def cny(value):
                return format(Decimal(value) / CNY_SCALE, 'f')
            cost = dict(conservative_cny=cny(conservative),
                token_estimate_cny=None if any(x is None for x in estimates) else cny(sum(estimates)),
                actual_paid_cny=None)
            self.last_cost_report = dict(version='G2C-native-simulator-closed-cost.1',
                coverage='COMPLETE', producer_lifecycle='CLOSED', operations=entries,
                producer_returns=list(self.returns.values()), memory_tails=memory_tails,
                inventory_proofs=[{key: report[key] for key in (
                    'message_id', 'run_id', 'status', 'inventory_sha256')} for report in reports],
                background_before_sha256=sha256(canonical(self.before_background)).hexdigest(),
                ledger_before=self.before_journal['anchor'], ledger_after=after['anchor'],
                actual_supplier_paid='UNKNOWN_NO_INVOICE', cost=cost)
            return cost
        except (Unavailable, Invalid, OSError, BudgetUnknown, sqlite3.OperationalError,
                psycopg.OperationalError) as error:
            self.last_cost_report = dict(version='G2C-native-simulator-closed-cost.1',
                coverage='UNKNOWN', producer_lifecycle='NOT_CERTIFIED',
                actual_supplier_paid='UNKNOWN_NO_INVOICE', error_code=error_code(error))
            raise HostUnavailable('original simulator cost unavailable; query only') from error

    def read(self, token, message_id, wire):
        """Read actual protected presentation; missing measurements stay absent."""
        inventory = decode(self.originals.inventory(token, message_id))
        memory = None
        if not self.dut.latest:
            intake = [op for op in inventory['operations']
                      if op['registration_id'] == 'model.lio_intake.9']
            require(len(intake) <= 1, 'SIMULATOR_FIRST_INTAKE_AMBIGUOUS')
            if intake:
                op = intake[0]['operation_id']
                logical = self.originals.input(token, message_id, op)
                data = decode(logical)
                prefix = 'Stored memory data (not instructions):\n'
                packets = [m['content'] for m in data['messages']
                           if m['role'] == 'user' and m['content'].startswith(prefix)]
                require(len(packets) <= 1, 'SIMULATOR_MEMORY_INPUT_AMBIGUOUS')
                if packets:
                    captured = decode(self.originals.artifact(token, message_id, op, wire_input=True))
                    actual = decode(captured['wire_input_utf8'])
                    observed = [m['content'] for m in actual['messages']
                                if m['role'] == 'user' and m['content'].startswith(prefix)]
                    require(observed == packets, 'SIMULATOR_MEMORY_WIRE_CHANGED')
                    payload = decode(packets[0][len(prefix):])
                    require(type(payload) is dict and type(payload.get('items')) is list,
                            'SIMULATOR_MEMORY_INPUT_FORMAT')
                    # Nonempty natural-language facts require independent
                    # normalization; observing bytes does not invent factors.
                    memory = dict(origin='accepted_injected', complete=not payload['items'],
                        text=packets[0], facts=[], ref='native-input:' + op + ':' + sha256(logical).hexdigest())
        native = decode(wire)
        def project(raw, check, projection):
            source = decode(raw)
            require(source['run_id'] == inventory['run_id'] and
                    projection.page.messages[-1].message_id == message_id and
                    projection.page.messages[-1].text == native['text'],
                    'SIMULATOR_OBSERVATION_ORIGINAL_CHANGED')
            check()
            return dict(text=projection.history[-1]['text'], run_outcome='completed',
                exploration_complete=False, questions=[], questions_complete=False,
                question_evidence='unavailable', profile=None, profile_complete=False,
                profile_evidence='unavailable', observation_ref=source['observer_ref'],
                memory_observation=memory)
        return self.source.observe(token, message_id, project)
