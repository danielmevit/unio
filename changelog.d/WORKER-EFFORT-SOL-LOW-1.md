# Worker effort capability/refusal slice

- Package a read-only `worker-effort WORKER [low|medium|high|xhigh] [--json]`
  CLI, help, completion and guide. Refuse requests truthfully without provider
  calls or changes to existing Source/configuration.
- Keep requested input, acknowledgement, configured effort, pending next turn
  and effective Unknown separate. No managed backend or effort switch is shipped.
- Add installed offline bundle and command smoke/refusal checks. Managed
  app-server RPC, native slot binding and channel lifecycle acceptance remain open.
