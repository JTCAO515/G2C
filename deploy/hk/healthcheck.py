"""Readiness may include an actual Hong Kong → Singapore TLS checkout."""
from urllib.request import urlopen

with urlopen('http://127.0.0.1:8765/health/ready',timeout=10) as response:
    if response.status!=200:raise SystemExit(1)
