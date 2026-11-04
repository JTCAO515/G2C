"""M4 device input/output boundaries. Raw native bundles are never publishable."""
import re
import subprocess
from pathlib import Path


def verified_public_certificate(pem: bytes, supplied_der: bytes) -> bytes:
    # OpenSSL accepts extra PEM objects/trailing bytes; the packaging boundary
    # deliberately accepts exactly one certificate and its canonical DER only.
    if re.fullmatch(rb'\s*-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----\s*', pem) is None:
        raise ValueError('A certificate-only PEM is required')
    result = subprocess.run(['openssl', 'x509', '-inform', 'PEM', '-outform', 'DER'],
                            input=pem, capture_output=True)
    if result.returncode or not result.stdout or result.stdout != supplied_der:
        raise ValueError('Public certificate DER must exactly match the parsed server certificate')
    return result.stdout


def redact(text, secrets):
    hits = 0
    for secret in secrets:
        if secret:
            hits += text.count(secret)
            text = text.replace(secret, '<redacted-credential>')
    text, private_blocks = re.subn(
        r'-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----.*?-----END (?:[A-Z ]*PRIVATE KEY)-----',
        '<redacted-private-key>', text, flags=re.S)
    return text, hits + private_blocks


def export_native_logs(raw_result, output, secrets, run_log, kinds=('build','action','console')):
    """Export only redacted text; opaque raw bundles remain private/quarantined.

    Called before checking xcodebuild's exit code so failed/cancelled runs receive
    the same boundary checks as successful runs. A hit never becomes a PASS.
    """
    raw_result, output = Path(raw_result), Path(output)
    texts = {'xcodebuild': run_log}
    missing = []
    if raw_result.exists():
        for kind in kinds:
            result = subprocess.run(['xcrun', 'xcresulttool', 'get', 'log', '--path', str(raw_result),
                                     '--type', kind, '--compact'], capture_output=True, text=True, timeout=30)
            if result.returncode:
                missing.append(kind)
            else:
                texts[kind] = result.stdout
    else:
        missing = list(kinds)
    hits = 0
    for kind, text in texts.items():
        cleaned, count = redact(text, secrets)
        hits += count
        (output / ('native-' + kind + '.log')).write_text(cleaned)
    return dict(secret_hits=hits, missing_logs=missing, raw_bundle_shareable=False,
                raw_bundle_location='private quarantine outside evidence exports',
                status='FAIL' if hits or missing else 'PASS: redacted allowlisted text only')
