# Reading a certificate

Every certificate derives from exactly one ruling (PMK-CRT-001): `punchmark
certify` emits one line of text, and with `--json` or `--out` the same content
as a `certificate/v1` document. Here is a real line from the synthetic
quickstart roundtrip:

```
punchmark certificate pmk-c-9f159a6c9f021abb: producer identity of route
synth/route-a (task synthtask, window
2026-01-01T00:00:00+00:00..2026-01-01T01:00:00+00:00) HOLDS at false-alarm rate
0.01; minimum resolvable substituted fraction 0.02 against candidate set
pmk-cs-169b400fc8599df1 (3 routes) over 72 items in 12 clusters. This certifies
the route label as served within the named candidate set; it is not a statement
about model weights.
[detector chargram v1; model pmk-m-3f963322e6324fe5; ruling pmk-r-3c53036ea627aa37]
```

Those ids are deterministic: the quickstart's commands reproduce them exactly, since
every seed is derived rather than sampled. They are not pinned by any test, so a
detector or generator change would move them without failing CI. Read the shape of the
line here rather than the exact hashes.

Field by field:

| field | meaning |
|---|---|
| `pmk-c-...` | The certificate id: a content hash of the certificate body. Identical inputs reproduce identical ids. |
| `route ...` | The route label being certified: the label as served. The weights behind it are outside the claim (PMK-CRT-002). |
| `task ..., window ...` | The claim's unit: one (route, window) per ruling. The window comes verbatim from the caller-written sidecar. A ruling scored under a declared task alias additionally prints `scored as <model task>` (PMK-RUL-005). That marker means the calibrated false-alarm rate was measured on different content than this archive's. |
| `HOLDS at false-alarm rate 0.01` | The verdict clause at the operating point *you* declared with `--far`. The other clauses are `DOES NOT HOLD ... statistic fell below the calibrated threshold ...` and `IS UNDETERMINED (reasons)`. |
| `minimum resolvable substituted fraction 0.02` | rho\*: the smallest substituted fraction the archive's k and item count could have resolved for the worst candidate pair. Only a `HOLDS` line carries it. |
| `against candidate set pmk-cs-... (3 routes)` | The closed set the verdict is relative to, by content id and size. |
| `over 72 items in 12 clusters` | What the verdict rests on. The cluster count is the one that bounds the effective sample size, since items inside a cluster share program content, so a row count on its own would overstate the evidence (PMK-CAL-001). |
| the scope sentence | Fixed wording, carried by every certificate (PMK-CRT-002): *"This certifies the route label as served within the named candidate set; it is not a statement about model weights."* |
| `[detector ...; model ...; ruling ...]` | Provenance: detector id and version, fitted-model id, and the ruling id this certificate derives from. This is enough to re-derive the line from the rulings store. |

## The tri-state exit code

`punchmark certify` exits **0** on `HOLDS`, **1** on `DOES NOT HOLD`, **2** on
`UNDETERMINED` or unevaluable input. Both non-zero codes are red. An
undetermined certificate can never read as success, and any pipeline that
special-cases exit 2 back to green has defeated the instrument. `UNDETERMINED`
carries its reasons in the line: too few items or clusters, a stub share over
the cap, no operating point calibrated at the requested false-alarm rate, or a
power limit.

## What SAME-PRODUCER means exactly

`SAME-PRODUCER` means: **a substitution of fraction >= rho_target by any
candidate in the set would have been flagged with the calibrated power, and
none was** (PMK-RUL-001). It is a statement about what the archive could have
detected and did not detect. It does not positively identify what served the
route. When some candidate pair is unresolvable at your `--rho-target`, a
passing statistic is forced to `UNDETERMINED`: absence of an alarm is not
evidence there.

## The closed-set caveat

Every verdict is relative to the candidate set declared at fit time
(PMK-CRT-003). A producer outside that set was never considered. If you score a
route that is not in the set, punchmark refuses instead of answering. If the
true producer is not among your candidates, no punchmark verdict, including
`SAME-PRODUCER`, says anything about it. Declare the candidates you actually
mean, and read every certificate with its set.
