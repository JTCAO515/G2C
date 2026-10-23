# CJ-012 PLACE adapter candidate

Pure Python >=3.12,<3.15, standard library only. No installation or root lock
change is needed. Public contract and current limitations:
[contracts/place](../../contracts/place/README.md).

From repository root, using an already installed compatible Python:

```sh
PYTHONPATH=backend/place python3.14 -B -m unittest discover -s backend/place/tests -v
PYTHONPATH=backend/place python3.14 -B contracts/place/examples.py
```

The default discovered parser/time tests and examples are synthetic and offline.
They create no HTTP server/client, account, credentials, database, socket,
persistent cache or provider business request.
`execute` is unconditionally closed. Only explicitly injected trusted offline
fixtures may use `cj_place.synthetic.run_synthetic`; it is not authentication,
budget admission, usage settlement, durable recovery or a production exit.

The explicit [HTTPS transport checks](tests/https_transport_checks.py) create a
task-private loopback TLS service with a disposable self-signed fixture and
synthetic sentinel. They are outside default test discovery. Run only when local
loopback TLS checks are authorized:

```sh
PYTHONPATH=backend/place python3.14 -B backend/place/tests/https_transport_checks.py
```

The unregistered low-level [transport candidate](cj_place/https_transport.py)
uses the provider's fixed origin/profile; its
[contract and limits](../../contracts/place/HTTPS-TRANSPORT.md) do not grant real
dispatch or provider permission. No real provider/account/credential was used.
