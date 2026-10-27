"""Real DashScope acceptance for the P2 provider path: 4 requests (zh/en answer + draft).

  CJ_MODEL_API_BASE_URL=... CJ_MODEL_ID=qwen3.8-flash uv run --locked python -B scripts/provider_smoke.py

The key comes from CJ_MODEL_API_KEY or the macOS Keychain item `g2c-dashscope` and is
never printed. Output: per case status, character counts, a short answer preview and
whether the draft passes TRIP validation. Costs a few thousand tokens at most.
"""
import os
import subprocess
import sys
import time

from cj_agent.draft import DRAFT_SYSTEM, DraftRejected, document_from_model
from cj_agent.provider import DashScopeConfig, DashScopeProvider, ProviderFailed, ProviderUnknown
from cj_trip.domain import Proposal


def key_from_keychain():
    result = subprocess.run(['security', 'find-generic-password', '-s', 'g2c-dashscope', '-w'],
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ''


def main():
    environ = dict(os.environ)
    if not environ.get('CJ_MODEL_API_KEY') and sys.platform == 'darwin':
        environ['CJ_MODEL_API_KEY'] = key_from_keychain()
    provider = DashScopeProvider(DashScopeConfig.from_environment(environ))
    failures = 0
    for label, text in (('zh', '我第一次去北京，想玩三天，有什么建议？'),
                        ('en', 'First time in Beijing, three days. What do you suggest?')):
        for kind, system in (('answer', None), ('draft', DRAFT_SYSTEM)):
            started = time.monotonic()
            chunks = []
            try:
                for chunk in provider.stream([{'role': 'user', 'content': text}], system=system):
                    chunks.append(chunk)
                status = 'PASS'
            except (ProviderFailed, ProviderUnknown) as error:
                status = f'FAIL {type(error).__name__}: {error}'
            reply = ''.join(chunks)
            detail = f'chunks={len(chunks)} chars={len(reply)} seconds={time.monotonic() - started:.1f}'
            if kind == 'draft' and status == 'PASS':
                try:
                    content = document_from_model(reply)
                    Proposal('p-smoke', 'trip-smoke', 0, 'run-smoke', int(time.time()) + 60, content)
                    detail += f' draft=VALID bytes={len(content)}'
                except (DraftRejected, ValueError) as error:
                    status, detail = 'FAIL draft', detail + f' draft=INVALID ({error})'
            preview = reply.replace('\n', ' ')[:80]
            print(f'{status} {label} {kind} {detail} :: {preview}', flush=True)
            failures += not status.startswith('PASS')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
