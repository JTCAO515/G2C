"""The #936 choose(messages) seam, with native source/RUN custody beside it.

This does not judge G2/G3 or render traveler wording. C validates the returned
choice with its unchanged render_choice before sending the next DUT message.
"""
from hashlib import sha256
import json
import os
from time import monotonic

from cj_run.core import Binding
from cj_message.auth_boundary import AccessBlocked, IdentityChanged
from cj_strict_json import compact
from runtime_adapter.contract import Unavailable, digest, label

from .runtime_actor import ActorInput, ActorSpecification
from .runtime_actor_run import ActorClaim, NativeActorRun, RetainedActorRun
from .runtime_private import private_directory, read_private


class ActorChoiceInvalid(ValueError):
    """A received, paid original response failed the fixed actor schema."""


class NativeActorHost:
    def __init__(self, database, tools, source, specification, authority, directory, *,
                 profile_id, attempt, dut_message, deadline, clock=monotonic):
        if authority.line != 'C':
            raise ValueError('simulator calls use the approved C allocation')
        self.database, self.tools, self.source = database, tools, source
        self.specification, self.authority, self.directory = specification, authority, directory
        self.profile_id, self.attempt = profile_id, attempt
        self.dut_message, self.deadline, self.clock = dut_message, deadline, clock
        self.owner = authority.binding()
        self.originals = []

    def _guard(self, *, read_only, purpose='query'):
        self.authority.require(binding=self.owner, pins_sha256=self.specification.key,
            purpose=purpose, deadline=self.clock()+30 if read_only else self.deadline, read_only=read_only)

    def _episode(self, parent):
        """One native DUT conversation belongs to one fixed evaluation slot."""
        value = compact(dict(version='LIO-simulator-episode.1', profile_id=self.profile_id,
            attempt=self.attempt, scope_sha256=parent['scope_sha256'],
            conversation_id=parent['conversation_id'], generation=parent['generation']), sort_keys=True)
        name = 'actor-episode-'+sha256(compact([self.owner.scope, self.owner.ledger_id,
            self.owner.producer_id, parent['conversation_id'], parent['generation']])).hexdigest()+'.json'
        self._guard(read_only=False, purpose='claim')
        with private_directory(self.directory, Unavailable('ACTOR_EPISODE_DIRECTORY_AUTHORITY')) as directory:
            try:
                descriptor = os.open(name, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600, dir_fd=directory)
            except FileExistsError:
                if read_private(name, 4096, directory_fd=directory) != value:
                    raise Unavailable('ACTOR_DUT_EPISODE_ALREADY_BOUND')
            else:
                with os.fdopen(descriptor, 'wb') as output:
                    output.write(value);output.flush();os.fsync(output.fileno())
                os.fsync(directory)
        self._guard(read_only=True, purpose='query')

    def recover(self, actor_id):
        """Recover only the same durable source/status/fees, never a capability."""
        self._guard(read_only=True, purpose='query')
        label(actor_id)
        if not actor_id.startswith('actor-'):
            raise Unavailable('ACTOR_ORIGINAL_ID_REQUIRED')
        name = digest([self.owner.scope, self.owner.ledger_id, self.owner.producer_id, actor_id])+'.json'
        with private_directory(self.directory, Unavailable('ACTOR_ORIGINAL_DIRECTORY_AUTHORITY')) as directory:
            raw = read_private(name, 131072, directory_fd=directory)
        from .runtime_actor import _json
        record = _json(raw)
        card = compact(record['specification']['runtime_card'])
        specification = ActorSpecification(self.specification.dataset, self.specification.system,
                                           self.specification.schema, card)
        def no_dispatch():
            raise Unavailable('RECOVERED_ACTOR_IS_QUERY_ONLY')
        argument = ActorInput(Binding(**record['binding']), record['profile_id'], record['attempt'],
            record['round'], compact(record['messages']), compact(record['dut_source']), specification, no_dispatch)
        if (argument.binding.scope != self.owner.scope or argument.binding.message_id != actor_id
                or argument.original() != raw):
            raise Unavailable('ACTOR_ORIGINAL_CLAIM_CHANGED')
        repository = self.database.run_repository(self.owner.scope)
        claim = ActorClaim(self.directory, self.owner, argument, guard=self._guard, repository=repository)
        retained = RetainedActorRun(argument, claim, repository, self._guard)
        retained.inspect()
        if not any(item.argument.binding.message_id == actor_id for item in self.originals):
            self.originals.append(retained)
        return retained

    def choose(self, messages):
        self._guard(read_only=False, purpose='actor')
        raw, history = self.specification.messages(messages, self.profile_id, self.attempt)
        # The trusted DUT host exposes its actual last MID, not an ID inferred
        # from conversation text. Source.use verifies the complete native history.
        message_id = self.dut_message()
        def run(source, check):
            parent = json.loads(source)
            if parent['scope_sha256'] != sha256(self.owner.scope.encode()).hexdigest():
                raise Unavailable('ACTOR_DUT_OWNER_CHANGED')
            self._episode(parent)
            key = sha256(compact([self.owner.scope, self.profile_id, self.attempt,
                len(history)//2, parent['conversation_id'], parent['generation'], parent['run_id']])).hexdigest()
            binding = Binding(self.owner.scope, 'actor-chat-'+key, 'actor-generation-'+key,
                              'actor-'+key, 'actor-run-'+key, 1)
            def original_check():
                self._guard(read_only=True, purpose='query')
                check()
            argument = ActorInput(binding, self.profile_id, self.attempt, len(history)//2,
                raw, source, self.specification, original_check)
            profile = self.database.run_context.current
            repository = self.database.run_repository(binding.scope, usage_profile=profile)
            claim = ActorClaim(self.directory, self.owner, argument, guard=self._guard, repository=repository)
            original = NativeActorRun(self.database, self.tools, argument, claim,
                                     guard=self._guard, profile=profile)
            # Retain the original before claim/dispatch: even a claim or provider
            # ACK failure must leave the same IDs available to finally/accounting.
            retained = [item for item in self.originals if item.argument.binding == binding]
            if retained:
                if retained[0].argument.original() != argument.original():
                    raise Unavailable('ACTOR_ORIGINAL_INPUT_CHANGED')
            else:
                self.originals.append(original)
            prepared = claim.claim(argument.original())
            if not prepared.fresh:
                raise Unavailable('ACTOR_ORIGINAL_ALREADY_CLAIMED_QUERY_ONLY')
            state = original.dispatch(prepared.capability)
            if state.status != 'completed':
                raise Unavailable('ACTOR_ORIGINAL_'+state.status.upper())
            try:
                return self.specification.decode_choice(state.text.encode())
            except ValueError as error:
                raise ActorChoiceInvalid('paid original actor choice failed fixed schema') from error
        # Boundary's canonical AUTH/source lifetime is outside all actor native
        # transactions, including original claim, model send and publication.
        token = self.authority.token_supplier()
        try:
            return self.source.use(token, message_id, history, run)
        except (AccessBlocked, IdentityChanged):
            raise Unavailable('ACTOR_ORIGINAL_AUTH_UNAVAILABLE') from None
