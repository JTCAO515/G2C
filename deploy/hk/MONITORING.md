# Hong Kong public readiness observations

This complements Docker readiness and retained worker metadata. It does not
prove a MESSAGE, model, planning, memory, or App flow, and never rolls back or
deploys the application. A failed observation requires the existing B incident
procedure; it cannot erase an original product FAIL or UNKNOWN.

The workflow is **inactive until JT authorizes activation** and B sets the
existing repository variable `HK_READINESS_MONITOR_ENABLED=true`. It runs only
while this repository is public, preserving the approved free-runner scope.
No repository
setting, cloud role, agent, billing product, credential, contact, or notification
preference is created by this PR. Permissions are read-only and checkout does
not retain credentials. Approval and actual notification receipt remain separate
from code/CI verification.

When activated on main, a standard GitHub-hosted runner checks only the fixed
public HTTPS `/health/live` and `/health/ready` routes, at most once each per
run. TLS and hostname verification remain enabled; redirects are rejected.
Only route, HTTP status, duration and safe failure categories appear in output.
Response content, exception text, authentication and business data are absent.
There are no retries, signed requests, model/tool calls, account changes or
budget operations. The first failure stops the remaining requests.

The configured workflow schedule determines the ten-minute observation cadence.
A job may run at any hour before authorization expires under the
[JT timing decision](https://github.com/JTCAO515/G2C/issues/495#issuecomment-7042305501).
It checks expiry at actual start and immediately before each GET. Crossing
expiry preserves completed metadata and skips the remaining GET. The hard
expiry is 2027-01-01 00:00 Beijing. If M4 ends sooner, B disables the variable
immediately. GitHub may delay or drop scheduled jobs, so the cadence provides
no availability SLA.

GitHub Actions failure notifications depend on the recipient's existing GitHub
notification settings. After JT approves the target and activation, one manual
`notification_drill=true` run deliberately fails **without contacting Hong Kong**.
Keep its deliberate-failure record separate from service outages, and record an
actual recipient receipt before declaring delivery verified. Missing receipt is
UNKNOWN, not PASS. This PR does not send that drill or change account settings.

Rollback: set the variable to `false` to stop new observations. This changes no
application source/image, config, account, budget or ledger. Existing workflow
records and earlier incident results remain intact.

References: [standard public runners](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job),
[schedule limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule),
[workflow notifications](https://docs.github.com/en/actions/concepts/workflows-and-actions/notifications-for-workflow-runs).
