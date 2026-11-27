#!/bin/bash
# usage: s-step60-gate.sh <starts_at> <ends_at> <ledger_count> <ledger_sha256>   (writes/replaces gate.json; uploads program once)
set -euo pipefail
SSH=(ssh -i "$HOME/.ssh/g2c-beta.pem" -o BatchMode=yes root@47.83.147.176)
D=$HOME/.local/share/g2c/b-server-smoke-20261118
P=$D/step-release-program.py
H=$(shasum -a 256 "$P" | cut -d' ' -f1)
[ "$H" = 5d609001aa97c597bfac87b01a1bb9dd06c8138b1cec92853cf118f37f212a5e ]
DIR=/srv/g2c-beta/probes/step60-release-20261128
timeout 30 "${SSH[@]}" "test -d $DIR || mkdir -m 0700 $DIR; test -e $DIR/step-release-program.py || cat > $DIR/step-release-program.py; chmod 0600 $DIR/step-release-program.py; sha256sum $DIR/step-release-program.py | cut -d' ' -f1" < "$P" | grep -qx "$H"
timeout 60 "${SSH[@]}" "python3 - '$1' '$2' '$3' '$4' '$H' '$DIR'" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
start,end,count,ledger,script,directory=sys.argv[1:]
R=Path('/srv/g2c-beta')
files=('common.env','api.env','worker.env','operator.env','deploy/hk/compose.yaml','deploy/hk/compose.local-pg.yaml')
gate=dict(source='dfc8a8d8ccef1bb6c893a9b95ed5ede01ee13439',previous_source='e0bea8430d1223b23919d82ae276af03b878b575',
  previous_operator_source='e0bea8430d1223b23919d82ae276af03b878b575',script_sha256=script,starts_at=start,ends_at=end,
  independent_review_approved=True,
  configuration_sha256={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in files},
  selector_sha256=hashlib.sha256((R/'compose.env').read_bytes()).hexdigest(),
  image_id='sha256:c3ef5417769356c95dc6ed27e1f55d31d6281f5a54f9c5550ef0108478ee4538',
  operator_image_id='sha256:e605714d7caf23cd5498068aaae52cf56a9c235c751be7139fe00e85fc8fdbaf',
  previous_image_id='sha256:5fa290ce84d0f19fca881bcc1518d82b155bc07d307952f6b100c9691edf756e',
  previous_operator_image_id='sha256:9c2fa38d7aaf140a26196e996d53690c0baf98cb8b0e94c15c0eb3b6f0963d47',
  ledger=dict(count=int(count),sha256=ledger),
  audit=dict(reviews='program 9f443ae6 + SOURCE fill 5d609001: Review: APPROVE c449d041/9883619f/5d609001/dad58c6c (Opus red line)',
    hk_verify='release-20261119-dfc8a8d8-hk-identity.json: config_equal, layers_equal; operator layers equal (e605714d)',
    range_check='coord/s-release-range-check.py e0bea843..dfc8a8d8 []', source_ci='run 45983277153 attempt 1 success'))
p=Path(directory)/'gate.json'; tmp=p.with_suffix('.tmp')
fd=os.open(str(tmp),os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as f:json.dump(gate,f,sort_keys=True);f.flush();os.fsync(f.fileno())
tmp.replace(p)
print(json.dumps(dict(gate_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),starts_at=start,ends_at=end,ledger=gate['ledger'])))
PY
