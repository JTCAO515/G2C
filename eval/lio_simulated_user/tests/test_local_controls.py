import socket
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from eval.lio_simulated_user.core import load_profiles, simulator_messages, render_choice
from eval.lio_simulated_user.local_controls import ScriptedActor, no_tcp


class LocalControls(unittest.TestCase):
    def test_scripted_control_obeys_all_persona_exit_points(self):
        data, _ = load_profiles()
        for profile in data['profiles']:
            for number in range(1, profile['behavior']['direct_after'] + 1):
                history = [dict(speaker=speaker, text='control')
                           for _ in range(number) for speaker in ('user', 'assistant')]
                choice = ScriptedActor().choose(simulator_messages(profile, history, 1))
                turn = render_choice(profile, choice, [dict(factor='interests')], number)
                self.assertTrue(turn['text'])
                self.assertEqual(choice['action'] == 'direct', number == profile['behavior']['direct_after'])

    def test_local_guard_blocks_both_tcp_connection_methods(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock, no_tcp():
            with self.assertRaises(AssertionError):sock.connect(('127.0.0.1', 9))
            with self.assertRaises(AssertionError):sock.connect_ex(('127.0.0.1', 9))

    def test_nonlocal_environment_rejected_before_output_or_native_setup(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'must-not-exist'
            result = subprocess.run([sys.executable, '-B', '-m',
                'eval.lio_simulated_user.local_controls', '--output', str(output)],
                env=dict(os.environ, CJ_ENV='production'), capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
