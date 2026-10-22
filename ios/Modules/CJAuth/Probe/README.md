# Dedicated simulator-only synthetic SessionStore probe

Build from repository root: `ios/Modules/CJAuth/Probe/build.sh`.
Only install/run in a newly allocated CJ007-owned simulator. Never run it on a physical
or pre-existing user device. The probe compiles the same CJSession source, not a mock adapter.

Explicit phases (separate app launches):
1. `--phase prepare`: add a unique synthetic item, derive its actual default app group
   from returned attributes, save synthetic session through explicit-group adapter.
2. `--phase restore-clear`: restore after process restart, check network-unknown leaves
   bytes intact, overwrite credential with a non-secret tombstone.
3. `--phase blocked-clean`: confirm tombstone after another restart, delete ONLY the
   uniquely created test item and confirm absent.

Successful ownership metadata (environment UUID/slot/group only, no secret) and boolean
phase reports live in this probe's Documents. A prepare collision or existing metadata
fails without overwriting. Failed stages may delete only an item this probe created.
No wildcard, shared-group search, entitlement generation or real account is implemented.
The UI/log reports contain no session data. All supplied data is explicitly synthetic.

Current run on CJ007-Session-20261021: prepare SecItemAdd failed with
errSecMissingEntitlement (-34018), before any successful creation; later phases UNRUN.
Do not add entitlement or borrow another app identity to work around this without a new
host capability lease. See ../SESSION-STORE.md for precise executed evidence and limitations.

消息密钥 probe 已准备但未执行；见 Proposals/KEYCHAIN-APPROVAL.md。build.sh 不自动
应用 entitlement 提案；本轮未重建/重签/重启现有 probe，旧 -34018 保留。
