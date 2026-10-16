Installed selftest now stages the invoking installation's canonical remote guard
helper into its isolated mock profile before init installs worker hooks. Missing
helpers fail explicitly; configured remote-policy enforcement is unchanged.
An installed regression requires all 40 built-in checks, including fixture paths
with spaces, without changing the invoking profile or global Git configuration.
