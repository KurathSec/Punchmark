# Security

## Supported versions

0.x, latest release only. There are no backports.

## punchmark's own surface

- punchmark has no network access at runtime. It opens no sockets and makes no
  requests. It reads the local files you name and writes files where you say.
- Archive content is never executed. Archives, sidecars, model files, baselines
  and rulings stores are data, parsed with the stdlib JSON and TOML readers.
  There is no plugin mechanism, no `exec`, and no import of anything an input
  names.

All of these inputs are data, and data must never behave as code. In scope:
anything that lets a crafted archive, sidecar, model file or baseline cause code
execution, a file
write outside a path you named, or resource consumption a parser should have
bounded.

## Reporting

Report privately via GitHub's private vulnerability reporting on
`KurathSec/Punchmark` (Security tab -> "Report a vulnerability"). Please do not
open a public issue for a vulnerability. Include the output of `punchmark env`:
the package version and the rulings-spec version together determine what
punchmark decided.
