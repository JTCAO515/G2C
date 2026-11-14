"""Durable call/propose orchestration over B's existing authority and exits.

No SDK, login, provider request, finance store, budget creation or retry loop.
"""
from pathlib import Path
from time import monotonic

from .contract import (VERSION, Invalid, Unavailable, candidate as checked_candidate, decode, digest, encode,
                       error_code, label, raw_digest, require, seconds)
from .evidence import check_snapshot
from .journal import IntentStore


class RuntimeAdapter:
    def __init__(self, backend, binding, pins, directory, *, dataset_path=None, clock=monotonic):
        if backend is None:
            raise Unavailable('B_REGISTERED_BACKEND_NOT_BOUND')
        self.backend, self.binding, self.pins, self.clock = backend, binding, pins, clock
        path = dataset_path or Path(__file__).resolve().parents[2] / 'eval/optimization/cases.v2.json'
        raw = Path(path).read_bytes()
        require(raw_digest(raw) == pins.value['task_sha256'], 'TASK_DATA_PIN_MISMATCH')
        data = decode(raw)
        require(data['version'] == pins.value['task_version'], 'TASK_VERSION')
        self.tasks = {task['id']: task for task in data['tasks']}
        self.store = IntentStore(directory)

    def _guard(self, purpose, deadline, *, read_only):
        if self.backend.binding() != self.binding:
            raise Unavailable('ORIGINAL_AUTH_CONTEXT_CHANGED')
        self.backend.require(binding=self.binding, pins_sha256=self.pins.key, purpose=purpose,
                             deadline=deadline, read_only=read_only)
        if self.backend.binding() != self.binding:
            raise Unavailable('ORIGINAL_AUTH_CONTEXT_CHANGED')
        if self.clock() >= deadline:
            raise Unavailable('DEADLINE_REACHED')
        if not read_only:
            if self.backend.pins() != self.pins.raw:
                raise Unavailable('RUNTIME_PIN_CHANGED')

    def _result(self, status, attempt, reason=None, **values):
        return dict(version=VERSION, status=status, attempt_id=attempt, reason=reason,
                    binding_sha256=self.binding.key, pins_sha256=self.pins.key,
                    quality_status='UNKNOWN', **values)

    def _read_step(self, request, deadline):
        self._guard('query', deadline, read_only=True)
        first = self.backend.inspect(request['attempt_id'], request['step_id'], deadline=deadline)
        if first is None:
            raise Unavailable('ORIGINAL_NOT_FOUND_DO_NOT_RESEND')

        def original(ref):
            self._guard('query', deadline, read_only=True)
            value = self.backend.original(ref, deadline=deadline)
            self._guard('query', deadline, read_only=True)
            return value

        result = check_snapshot(first, request=request, binding=self.binding, pins=self.pins, original=original)
        self._guard('query', deadline, read_only=True)
        if self.backend.inspect(request['attempt_id'], request['step_id'], deadline=deadline) != first:
            raise Unavailable('ORIGINAL_SNAPSHOT_CHANGED')
        self._guard('query', deadline, read_only=True)
        return result

    def query(self, attempt_id):
        label(attempt_id)
        record = self.store.read(attempt_id)
        if record is None:
            return self._result('UNKNOWN', attempt_id, 'ORIGINAL_INTENT_NOT_FOUND_DO_NOT_RESEND')
        require(record['binding_sha256'] == self.binding.key and record['pins_sha256'] == self.pins.key,
                'ORIGINAL_INTENT_BINDING_CHANGED')
        steps = []
        deadline = self.clock() + 30
        for request in record['steps']:
            try:
                step = self._read_step(request, deadline)
            except (Unavailable, Invalid, OSError, TimeoutError) as error:
                # A broken/missing original cannot hide the other started RUNs.
                code = error_code(error)
                step = dict(status='UNKNOWN', step_id=request['step_id'], reason=code)
            steps.append(step)
        try:
            # Prior successful reads are private too. Recheck before publishing
            # any payload; revoked/changed authority or an expired read may not
            # return the earlier results merely with an UNKNOWN label.
            self._guard('query', deadline, read_only=True)
        except (Unavailable, OSError, TimeoutError) as error:
            code = error_code(error)
            return self._result('UNKNOWN', attempt_id, code)
        original_ids = [op['attempt_id'] for step in steps if 'snapshot' in step
                        for op in step['snapshot']['operations']]
        if len(original_ids) != len(set(original_ids)):
            return self._result('UNKNOWN', attempt_id, 'DUPLICATE_ORIGINAL_ATTEMPT_IN_TASK', steps=steps)
        statuses = {step['status'] for step in steps}
        for status in ('UNKNOWN', 'CANCELLED', 'FAIL', 'UNRUN'):
            if status in statuses:
                return self._result(status, attempt_id, 'ORIGINAL_NOT_COMPLETED', steps=steps)
        if len(record['steps']) < len(record['plan']):
            return self._result('UNKNOWN', attempt_id, 'TASK_INTERRUPTED_NO_AUTOMATIC_CONTINUATION', steps=steps)
        result = steps[-1]['result'] if steps else None
        if record['purpose'] == 'propose':
            components = record['request']['components']
            if not (type(result) is dict and set(result) == set(components) and
                    all(type(v) is str and v.strip() and len(v.encode()) <= 8192 for v in result.values())):
                return self._result('FAIL', attempt_id, 'REFLECTION_RESULT_COMPONENTS', steps=steps)
        return self._result('PASS', attempt_id, steps=steps, result=result)

    def _execute(self, purpose, payload, plan, attempt, timeout):
        label(attempt)
        deadline = self.clock() + seconds(timeout, 90 if purpose == 'propose' else 180)
        with self.store.locked():
            existing = self.store.read(attempt)
            if existing is not None:
                require(existing['request_sha256'] == digest(payload) and existing['purpose'] == purpose,
                        'ORIGINAL_ATTEMPT_INPUT_CHANGED')
                return self.query(attempt)  # never dispatch an existing intent, including UNRUN
            # One unresolved attempt stops new operations in this binding. Query
            # may reconcile originals; it never clears holds or edits old records.
            for other in self.store.all():
                require(other['binding_sha256'] == self.binding.key and other['pins_sha256'] == self.pins.key,
                        'INTENT_DIRECTORY_BINDING_CHANGED')
                if self.query(other['attempt_id'])['status'] in ('UNKNOWN', 'UNRUN'):
                    return self._result('UNRUN', attempt, 'UNRESOLVED_OR_STOPPED_ORIGINAL',
                                        blocked_by=other['attempt_id'])
            try:
                self._guard(purpose, deadline, read_only=False)
                if purpose == 'call':
                    source = self.tasks[payload['task_id']]
                    variant = source['variants'][payload['language']]
                    execution_only = {key: source[key] for key in ('id', 'split', 'trip_family', 'setup')}
                    execution_only['variant'] = {key: variant[key] for key in ('steps', 'turns') if key in variant}
                    self.backend.prepare_task(decode(encode(execution_only)), payload['language'])
                self._guard(purpose, deadline, read_only=False)
            except Unavailable as error:
                return self._result('UNRUN', attempt, str(error))
            record = dict(attempt_id=attempt, purpose=purpose, request=payload,
                          request_sha256=digest(payload), plan=plan, steps=[],
                          binding_sha256=self.binding.key, pins_sha256=self.pins.key)
            self.store.write(record)
            for index, action in enumerate(plan):
                step_purpose = 'cancel_original' if action['kind'] == 'cancel_original_run' else purpose
                try:
                    self._guard(step_purpose, deadline, read_only=False)
                except Unavailable as error:
                    return self._result('UNKNOWN', attempt, str(error))
                request = dict(version=VERSION, attempt_id=attempt,
                    # Stable original client ID even if local mapping, candidate,
                    # pins or auth session were lost/changed. B atomically binds
                    # the request digest; altered bytes cannot mint another ID.
                    step_id='runtime-' + digest([self.binding.scope, attempt, index]),
                    binding_sha256=self.binding.key, pins_sha256=self.pins.key,
                    kind=action['kind'], payload=action['payload'],
                    candidate=payload['candidate'], prior_step_ids=[step['step_id'] for step in record['steps']])
                record['steps'].append(request)
                self.store.write(record)  # fsync before entering any mutating B seam
                try:
                    prepared = self.backend.claim(encode(request), deadline=deadline)
                    if not prepared.fresh:
                        return self._result('UNKNOWN', attempt, 'B_ORIGINAL_ALREADY_EXISTS_QUERY_ONLY')
                    self._guard(step_purpose, deadline, read_only=False)
                    self.backend.dispatch(encode(request), capability=prepared.capability, deadline=deadline)
                    result = self._read_step(request, deadline)
                except (Unavailable, Invalid, TimeoutError, OSError):
                    return self._result('UNKNOWN', attempt, 'DISPATCH_OR_ACK_UNCERTAIN_QUERY_ORIGINAL')
                cancelling_original = (action['kind'] == 'start_controlled_generation' and
                    result['source_status'] == 'RUNNING' and index+1 < len(plan) and
                    plan[index+1]['kind'] == 'cancel_original_run')
                if result['status'] != 'PASS' and not cancelling_original:
                    return self._result(result['status'], attempt, 'ORIGINAL_NOT_COMPLETED', steps=[result])
                if self.clock() >= deadline:
                    return self._result('UNKNOWN', attempt, 'DEADLINE_REACHED_QUERY_ORIGINAL')
            return self.query(attempt)

    def call(self, task, candidate, attempt_id, timeout):
        require(type(task) is dict and set(task) == {'id', 'language'}, 'TASK_REFERENCE_FIELDS')
        require(type(task['id']) is str and task['id'] in self.tasks and
                type(task['language']) is str and task['language'] in ('zh', 'en'), 'PUBLIC_TASK_REFERENCE')
        t = self.tasks[task['id']]
        fragments = checked_candidate(candidate)
        variant = t['variants'][task['language']]
        # Setup is an original action too, not permission to run admin SQL or
        # count the expected state in cases.2 as an observed outcome.
        plan = [dict(kind='task_setup', payload=dict(task_id=t['id'], language=task['language'],
                     dataset_sha256=self.pins.value['task_sha256'], setup=t['setup']))]
        if 'steps' in variant:
            for step in variant['steps']:
                plan.append(dict(kind=step['kind'], payload=dict(step)))
        else:
            for index, text in enumerate(variant['turns']):
                kind = 'message'
                if t['id'] == 'dev-cancel':
                    kind = 'start_controlled_generation' if index == 0 else 'cancel_original_run'
                elif t['id'] == 'val-deleted-recall' and index == len(variant['turns']) - 1:
                    kind = 'new_conversation_message'
                plan.append(dict(kind=kind, payload=dict(text=text)))
        payload = dict(task_id=t['id'], language=task['language'], split=t['split'], candidate=fragments,
                       task_version=self.pins.value['task_version'], task_sha256=self.pins.value['task_sha256'])
        return self._execute('call', payload, plan, attempt_id, timeout)

    def propose(self, candidate, feedback, components, attempt_id, timeout):
        fragments = checked_candidate(candidate)
        require(type(components) is list and components and all(type(key) is str for key in components)
                and len(set(components)) == len(components)
                and set(components) <= set(fragments), 'REFLECTION_COMPONENTS')
        components = list(components)
        require(type(feedback) is dict and set(feedback) == {'split', 'dataset_sha256', 'rows'} and
                feedback['split'] == 'development' and feedback['dataset_sha256'] == self.pins.value['task_sha256']
                and type(feedback['rows']) is list and feedback['rows'], 'DEVELOPMENT_FEEDBACK_ONLY')
        for row in feedback['rows']:
            require(type(row) is dict and set(row) == {'task_id', 'language', 'feedback', 'evidence'} and
                    row['task_id'] in self.tasks and self.tasks[row['task_id']]['split'] == 'development' and
                    row['language'] in ('zh', 'en') and type(row['feedback']) is str and
                    type(row['evidence']) is list and row['evidence'], 'DEVELOPMENT_FEEDBACK_ROW')
        require(len(encode(feedback)) <= 16384, 'FEEDBACK_BOUND')
        payload = dict(candidate=fragments, feedback=decode(encode(feedback)), components=components)
        plan = [dict(kind='reflection', payload=payload)]
        return self._execute('propose', payload, plan, attempt_id, timeout)
