# Security policy

Please report vulnerabilities privately through GitHub's "Report a vulnerability" button on this
repository, not in public issues.

EZE OS is experimental and offered without warranty or liability (see README and LICENSE).
Vendor credentials are read only from environment variables or explicit arguments and are never
stored by EZE OS. The OpenQASM parser evaluates parameter expressions with a restricted grammar,
never with Python `eval`.
