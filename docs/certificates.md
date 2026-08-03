# Reading a certificate

Every certificate derives from exactly one ruling (PMK-CRT-001): `punchmark
certify` emits one line of text, and with `--json` or `--out` the same content
as a `certificate/v1` document. Here is a real line from the synthetic
quickstart roundtrip:

```
punchmark certificate pmk-c-898ad0d5041b740a: producer identity of route
synth/route-a (task synthtask, window
2026-01-01T00:00:00+00:00..2026-01-01T01:00:00+00:00) HOLDS at false-alarm rate
0.01; minimum resolvable substituted fraction 0.2 against candidate set
pmk-cs-169b400fc8599df1 (3 routes). This certifies the route label as served
within the named candidate set; it is not a statement about model weights.
[detector trivial v1; model pmk-m-f43f9b523d55e64b; ruling pmk-r-63efb346736a81d9]
```

Field by field:

| field | meaning |
|---|---|
| `pmk-c-...` | The certificate id: a content hash of the certificate body. Identical inputs reproduce identical ids. |
| `route ...` | The route label being certified -- the label, as served, never the weights behind it (PMK-CRT-002). |
| `task ..., window ...` | The claim's unit: one (route, window) per ruling. The window comes verbatim from the caller-written sidecar; an unwindowed ruling prints `window UNDECLARED`. |
| `HOLDS at false-alarm rate 0.01` | The verdict clause at the operating point *you* declared with `--far`. The other clauses are `DOES NOT HOLD ... statistic fell below the calibrated threshold ...` and `IS UNDETERMINED (reasons)`. |
| `minimum resolvable substituted fraction 0.2` | rho\*: the smallest substituted fraction the archive's k and item count could have resolved for the worst candidate pair. Only a `HOLDS` line carries it. |
| `against candidate set pmk-cs-... (3 routes)` | The closed set the verdict is relative to, by content id and size. |
| the scope sentence | Fixed wording, carried by every certificate (PMK-CRT-002): *"This certifies the route label as served within the named candidate set; it is not a statement about model weights."* |
| `[detector ...; model ...; ruling ...]` | Provenance: detector id and version, fitted-model id, and the ruling id this certificate derives from -- enough to re-derive the line from the rulings store. |

## The tri-state exit code

`punchmark certify` exits **0** on `HOLDS`, **1** on `DOES NOT HOLD`, **2** on
`UNDETERMINED` or unevaluable input. Both non-zero codes are red: an
undetermined certificate can never read as success, and any pipeline that
special-cases exit 2 back to green has defeated the instrument. `UNDETERMINED`
carries its reasons in the line -- too few items or clusters, a stub share over
the cap, no operating point calibrated at the requested false-alarm rate, or a
power limit.

## What SAME-PRODUCER means exactly

`SAME-PRODUCER` means: **a substitution of fraction >= rho_target by any
candidate in the set would have been flagged with the calibrated power; none
was** (PMK-RUL-001). It is a statement about what the archive could have
detected and did not -- never a positive identification of what served the
route. When some candidate pair is unresolvable at your `--rho-target`, a
passing statistic is forced to `UNDETERMINED`: absence of an alarm is not
evidence there.

## The closed-set caveat

Every verdict is relative to the candidate set declared at fit time
(PMK-CRT-003). A producer outside that set was never considered; scoring a route
that is not in the set is refused rather than answered. If the true producer is
not among your candidates, no punchmark verdict -- including `SAME-PRODUCER` --
says anything about it. Declare the candidates you actually mean, and read every
certificate with its set.
