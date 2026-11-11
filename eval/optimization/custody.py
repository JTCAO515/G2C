"""Seal a controlled final set with a JT-entered passphrase and emit metadata only."""
import argparse
import errno
from hashlib import sha256
import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import sys
from threading import Thread
import time

from evaluation.cj028.evaluate import fields, nonempty, read_json, require
from .score import LANGUAGES, STATE_RULES, dataset

AGE_VERSION = 'v1.3.2'
FINAL_VERSION = 'G2C-controlled-dialogue-cases.1'
PURPOSE = 'final_acceptance_only'


def age_binary():
    executable = '/opt/homebrew/bin/age' if sys.platform == 'darwin' else 'age'
    result = subprocess.run([executable, '--version'], capture_output=True, check=True)
    require(result.stdout.decode().strip() == AGE_VERSION, 'age version differs from the custody pin')
    return executable


def age_io(arguments, data, passphrase):
    """Use pipes for payloads and a private controlling terminal for age prompts."""
    executable = age_binary()
    input_read, input_write = os.pipe()
    output_read, output_write = os.pipe()
    child, terminal = pty.fork()
    if child == 0:
        os.dup2(input_read, 0)
        os.dup2(output_write, 1)
        for descriptor in (input_read, input_write, output_read, output_write):
            os.close(descriptor)
        os.execv(executable, [executable, *arguments])
    os.close(input_read)
    os.close(output_write)
    output = []

    def send_input():
        with os.fdopen(input_write, 'wb') as stream:
            stream.write(data)

    def read_output():
        with os.fdopen(output_read, 'rb') as stream:
            output.append(stream.read())

    sender = Thread(target=send_input)
    reader = Thread(target=read_output)
    sender.start()
    reader.start()
    prompts = bytearray()
    answered = set()
    deadline = time.monotonic() + 60
    try:
        while True:
            if time.monotonic() >= deadline:
                os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)
                raise RuntimeError('age custody operation timed out')
            if select.select([terminal], [], [], 0.1)[0]:
                try:
                    chunk = os.read(terminal, 4096)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    chunk = b''
                prompts.extend(chunk)
                for prompt in (b'Enter passphrase', b'Confirm passphrase'):
                    if prompt in prompts and prompt not in answered:
                        os.write(terminal, passphrase + b'\n')
                        answered.add(prompt)
            finished, status = os.waitpid(child, os.WNOHANG)
            if finished:
                break
        sender.join()
        reader.join()
        if os.waitstatus_to_exitcode(status) != 0:
            raise RuntimeError('age custody operation failed')
        return output[0]
    finally:
        os.close(terminal)


def jt_passphrase():
    def prompt(message):
        script = ('text returned of (display dialog ' + json.dumps(message, ensure_ascii=False) +
                  ' default answer "" with hidden answer buttons {"取消", "继续"} '
                  'default button "继续" cancel button "取消" with title "G2C 最终题加密")')
        result = subprocess.run(['osascript', '-e', script], capture_output=True)
        require(result.returncode == 0, 'JT cancelled the local custody prompt')
        return result.stdout.rstrip(b'\r\n')

    first = prompt('请设置最终题专用口令（至少 16 个字符），并自行保存到密码管理器。口令只用于本次加密，不会输出或保存到开发文件。')
    require(len(first.decode('utf-8')) >= 16 and b'\n' not in first, 'a passphrase of at least 16 characters is required')
    second = prompt('请再次输入刚才的最终题专用口令。后续独立比较时，请只交给获准的 R 会话。')
    require(first == second, 'the two local passphrase entries differ')
    return first


def final_metadata(payload):
    document = read_json(payload)
    fields(document, {'version', 'purpose', 'tasks'}, 'controlled set')
    require(document['version'] == FINAL_VERSION and document['purpose'] == PURPOSE, 'invalid controlled purpose/version')
    public, _ = dataset()
    public_families = {task['trip_family'] for task in public['tasks']}
    public_inputs = {tuple(variant['turns']) for task in public['tasks'] for variant in task['variants'].values()}
    tasks = document['tasks']
    require(type(tasks) is list and bool(tasks), 'controlled tasks are required')
    ids = set()
    kinds = set()
    for task in tasks:
        fields(task, {'id', 'split', 'trip_family', 'kind', 'setup', 'variants'}, 'controlled task')
        require(nonempty(task['id']) and task['id'] not in ids, 'duplicate or missing controlled task identity')
        require(task['split'] == 'final' and nonempty(task['trip_family']) and task['trip_family'] not in public_families,
                'controlled travel family is exposed in the public set')
        require(task['kind'] in STATE_RULES and nonempty(task['setup']), 'invalid controlled task setup/kind')
        require(set(task['variants']) == set(LANGUAGES), 'controlled task needs both languages')
        for variant in task['variants'].values():
            require(type(variant) is dict and variant.keys() <= {'turns', 'behavior', 'state'}, 'invalid controlled variant')
            turns = variant.get('turns')
            require(type(turns) is list and bool(turns) and all(nonempty(turn) for turn in turns), 'invalid controlled turns')
            require(tuple(turns) not in public_inputs, 'controlled input repeats a public task')
            require(type(variant.get('behavior')) is dict and bool(variant['behavior']), 'controlled behavior rubric missing')
        ids.add(task['id'])
        kinds.add(task['kind'])
    require(kinds == set(STATE_RULES), 'controlled set lacks a required behavior or hard-state class')
    return dict(plaintext_sha256=sha256(payload).hexdigest(), purpose=PURPOSE,
                denominators=dict(tasks=len(tasks), trip_families=len({task['trip_family'] for task in tasks}),
                                  **{language: len(tasks) for language in LANGUAGES},
                                  by_kind={kind: sum(task['kind'] == kind for task in tasks) for kind in sorted(kinds)}))


def seal(payload, output):
    metadata = final_metadata(payload)
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    probe = subprocess.run(['git', '-C', str(output.parent), 'rev-parse', '--is-inside-work-tree'], capture_output=True)
    require(probe.returncode != 0, 'controlled ciphertext must be outside every Git worktree')
    require(not output.exists(), 'controlled output already exists')
    passphrase = jt_passphrase()
    ciphertext = age_io(['--encrypt', '--passphrase'], payload, passphrase)
    restored = age_io(['--decrypt'], ciphertext, passphrase)
    require(restored == payload, 'custody round-trip differs from the authored set')
    del passphrase, restored
    with output.open('xb') as stream:
        os.chmod(output, 0o600)
        stream.write(ciphertext)
        stream.flush()
        os.fsync(stream.fileno())
    metadata['ciphertext_sha256'] = sha256(ciphertext).hexdigest()
    return metadata


def deny_probe(ciphertext, session):
    executable = age_binary()
    raw = ciphertext.expanduser().resolve().read_bytes()
    result = subprocess.run([executable, '--decrypt'], input=raw, capture_output=True,
                            start_new_session=True, timeout=15)
    return dict(session=session, ciphertext_sha256=sha256(raw).hexdigest(), age_version=AGE_VERSION,
                exit_code=result.returncode, decrypted_bytes=len(result.stdout),
                stderr_sha256=sha256(result.stderr).hexdigest(),
                status='PASS' if result.returncode != 0 and not result.stdout else 'FAIL')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    writer = commands.add_parser('seal')
    writer.add_argument('--output', type=Path, required=True)
    probe = commands.add_parser('deny-probe')
    probe.add_argument('--ciphertext', type=Path, required=True)
    probe.add_argument('--session', choices=('D', 'E', 'B'), required=True)
    args = parser.parse_args()
    try:
        result = seal(sys.stdin.buffer.read(), args.output) if args.command == 'seal' else deny_probe(args.ciphertext, args.session)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(2, f'Custody operation failed ({type(error).__name__}).\n')
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2))
    return 0 if result.get('status', 'PASS') == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
