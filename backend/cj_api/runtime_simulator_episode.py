"""Join C's unchanged renderer to native actor and next ordinary DUT input.

The composition supplies the pinned C renderer/error types. It never sends the
profile, actor system, choice or sidecar to the product MESSAGE producer.
"""
from hashlib import sha256
import json
import os

from cj_strict_json import compact
from runtime_adapter.contract import Unavailable

from .runtime_actor_host import ActorChoiceInvalid
from .runtime_private import private_directory, read_private


class EpisodeLinks:
    def __init__(self, directory, owner, specification, *, guard):
        self.directory, self.owner, self.specification = directory, owner, specification
        self.guard = guard

    def record(self, original, choice, rendered_text, next_message_id):
        self.guard(read_only=True, purpose='query')
        argument = original.argument
        if argument.binding.scope != self.owner.scope or argument.specification != self.specification:
            raise Unavailable('SIMULATOR_EPISODE_ACTOR_BINDING_CHANGED')
        parent = json.loads(argument.source)
        link = dict(version='LIO-simulator-rendered.1', actor_id=argument.binding.message_id,
            actor_input_sha256=sha256(argument.original()).hexdigest(),
            choice_sha256=sha256(compact(choice, sort_keys=True)).hexdigest(),
            rendered_text_sha256=sha256(rendered_text.encode()).hexdigest(),
            observer_ref=parent['observer_ref'])
        value = compact(dict(version='LIO-simulator-link.1', binding_sha256=self.owner.key,
            profile_id=argument.profile_id, attempt=argument.attempt, round=argument.round,
            dut_source=parent, actor_run_id=argument.binding.run_id,
            actor_specification_sha256=self.specification.key, link=link,
            next_message_id=next_message_id), sort_keys=True)
        name = 'episode-link-'+sha256(argument.binding.message_id.encode()).hexdigest()+'.json'
        with private_directory(self.directory, Unavailable('SIMULATOR_EPISODE_LINK_DIRECTORY')) as directory:
            try:
                fd = os.open(name, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600, dir_fd=directory)
            except FileExistsError:
                if read_private(name, 16384, directory_fd=directory) != value:
                    raise Unavailable('SIMULATOR_EPISODE_LINK_CHANGED')
            else:
                with os.fdopen(fd, 'wb') as output:
                    output.write(value);output.flush();os.fsync(output.fileno())
                os.fsync(directory)
        self.guard(read_only=True, purpose='query')
        return link


class SimulatorActorBridge:
    def __init__(self, actor, dut, links, renderer, input_error, host_unavailable):
        self.actor, self.dut, self.links, self.renderer = actor, dut, links, renderer
        self.input_error, self.host_unavailable = input_error, host_unavailable

    def choose(self, messages):
        try:
            choice = self.actor.choose(messages)
        except ActorChoiceInvalid as error:
            # A received paid response remains in actor.originals even though
            # C's choose() call did not return and its received flag is false.
            raise self.input_error('original actor choice rejected') from error
        except Unavailable as error:
            raise self.host_unavailable('original actor unavailable; query only') from error
        original = self.actor.originals[-1]
        argument = original.argument
        observation = self.dut.last_observation
        source = json.loads(argument.source)
        if (self.dut.latest != source['message_id'] or observation is None
                or observation['observation_ref'] != source['observer_ref']):
            raise self.host_unavailable('original DUT observation changed')
        questions = observation['questions'] if observation['questions_complete'] else None
        # Reuse C's exact renderer. C's runner repeats its existing validation;
        # this projection binds the same ordinary text before the next write.
        rendered = self.renderer(self.actor.specification.profile(self.actor.profile_id),
                                 choice, questions, argument.round)
        index = len(self.dut.originals)
        if index >= len(self.dut.specification.message_ids):
            raise self.host_unavailable('original DUT plan exhausted')
        try:
            link = self.links.record(original, choice, rendered['text'],
                                     self.dut.specification.message_ids[index])
            self.dut.release(rendered['text'], link)
        except Unavailable as error:
            raise self.host_unavailable('original episode link unavailable') from error
        return choice


class SimulatorDutBridge:
    def __init__(self, dut, host_unavailable):
        self.dut, self.host_unavailable = dut, host_unavailable

    def reply(self, text, locale, *, first):
        try:
            return self.dut.reply(text, locale, first=first)
        except Unavailable as error:
            raise self.host_unavailable('original DUT unavailable; query only') from error
