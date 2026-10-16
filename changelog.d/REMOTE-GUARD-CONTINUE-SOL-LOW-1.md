Fix remote guard ambiguity across all resolved push destinations, avoid credential
persistence with opaque destination hashes, validate private policy files and CLI
arguments strictly, and preserve/refuse unsafe owner hook installation. Both hook
installation routes now use the canonical helper. Preserve the original HIGH
quota failure and unaccepted Gemini proposal separately from this LOW correction.
