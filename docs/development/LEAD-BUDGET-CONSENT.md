# Shared lead budget consent

Native admission refuses spending the registered lead's declared account group
without explicit owner consent, independently of the concurrency tier.

```
unio lead-budget grant <agent> <worker> <task> <run|review>
unio lead-budget show
unio lead-budget revoke <grant-id>
```

Grants expire after 15 minutes. Each permits exactly one successful admission,
bound to the agent route configuration, worker, owner task name and SHA-256
contents, kind, declared account group, registered lead and lead group. Review
collections bind the owner task rather than their generated attempt label.
Changing any binding requires a new grant. Generic aliases still require
explicit `unio account` grouping; unknown mappings are not detected by reading
credentials. Unmanaged and cross-workspace sessions remain uncounted.

The separate schema-1 `coord/lead-budget.json` store preserves used and revoked
records, with bounded typed data and private permissions. Invalid or unsafe
state refuses without repair or deletion. Issuance, revocation and consumption
use the existing policy lock. Consumption occurs only after capacity and local
admission preparation succeed, before the broker replies. Concurrent attempts
cannot reuse a grant. Uncertain startup, cancellation or provider failure never
restores a consumed grant. History is bounded to 128 records; a full store
refuses new issuance rather than discarding evidence.

Consent authorizes spending the lead group: it creates no quota, capacity lease
or raised cap. Low remains capped including the lead. No tier or lead mutation
is automatic. Owner-issued means a local trusted_host instruction boundary,
not authentication against other code running as the same user. Requested and
effective model, effort and remaining allowance stay distinct; unverified
values remain Unknown. No model or lab is inferred from aliases.

Older schema-1 policy consumers remain compatible. Older executable runners do
not enforce this additive guard; use the updated native runner for protection.
