set -eu
R=/srv/g2c-beta
M=""
for spec in "operator.env:/run/secrets/operator.env" "control:/control" "local-pg-socket:/run/g2c-pg" "backups:/backups" "budget:/budget" "probes/836-platform-release-proof-plan.json:/plan.json" "probes/836-release-export.py:/export.py" "836-platform-release-evidence:/evidence"; do
  M="$M --mount type=bind,src=$R/${spec%%:*},dst=${spec#*:},readonly"
done
docker run --pull=never --rm --network none --read-only --tmpfs /tmp --user 10001:10001 --env-file $R/common.env --entrypoint python $M sha256:5fa290ce84d0f19fca881bcc1518d82b155bc07d307952f6b100c9691edf756e -B /export.py | python3 -c "import json,sys;p=json.load(sys.stdin);print(json.dumps({k:p[k] for k in ('ledger','global_pending','global_active','background_states','memory_states')}))"
