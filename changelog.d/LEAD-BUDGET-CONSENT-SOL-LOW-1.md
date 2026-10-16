Native Source and independent review admission now require an explicit one-use
owner grant before spending the registered lead's declared account group.
`unio lead-budget grant/show/revoke` uses private bounded local history,
15-minute expiry, exact task/configuration/policy bindings and atomic consumption
under the existing policy lock. Review collections retain the owner task binding.
Consent never raises concurrency caps or invents quota; unsafe state fails closed.
