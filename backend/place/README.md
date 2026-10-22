# CJ-012 PLACE adapter candidate

Pure Python >=3.12,<3.15, standard library only. No installation or root lock
change is needed. Public contract and current limitations:
[contracts/place](../../contracts/place/README.md).

From repository root, using an already installed compatible Python:

```sh
PYTHONPATH=backend/place python3.14 -B -m unittest discover -s backend/place/tests -v
PYTHONPATH=backend/place python3.14 -B contracts/place/examples.py
```

All tests are synthetic and offline. No HTTP server/client, account, credentials,
database, socket, persistent cache or provider business request is created.
`execute` is unconditionally closed. Only explicitly injected trusted offline
fixtures may use `cj_place.synthetic.run_synthetic`; it is not authentication,
budget admission, usage settlement, durable recovery or a production exit.
