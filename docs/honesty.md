# What a ruling does not show

Every one of these limits is structural. None of them is a caveat that can be
optimized away. The certificate wording enforces the first two (PMK-CRT-002,
PMK-CRT-003). The rest are carried here and in NOTICE.

A ruling does not verify weights. A certificate says the route label was
consistent with the calibrated fingerprint. It does not say that a particular
set of parameters served the request. A public route name does not denote a
fixed configuration, and punchmark does not repair that. Reading SAME-PRODUCER
as "the model did not change" is a misreading, and the certificate wording
makes that misreading hard.

A ruling is closed-set. A producer outside the declared candidate set will be
mapped to its nearest member. SAME-PRODUCER means "best match within candidate
set C at the declared operating point". It is not an identity proof.

A ruling cannot detect a substitution present throughout calibration. If a
different artifact was silently served for the whole collection window, that
artifact IS the fingerprint. The instrument detects change relative to a
labelled window, and it cannot tell whether that window itself reflected the
truth. The same-producer null additionally rests on the provider's implicit
claim that no substitution occurred inside the window. The window restriction
narrows this exposure and does not close it (PMK-CAL-003).

A ruling cannot say what changed. A SUBSTITUTED ruling is a flag attributable
to nothing: ground truth about what changed never arrives. Weights, sampling,
serving stack, and safety filters are indistinguishable from response text
alone.

The power numbers are a best case. Seeded substitutions are spliced from
another candidate's responses over the identical items, inside one window. Real
substitutions arrive with a date offset, hit time-contiguous traffic, and may
involve an off-candidate producer. This fidelity gap cannot be validated from
committed data and stands as a bound wherever power numbers appear
(PMK-POW-004).

A null is only as good as its power. An archive below the calibrated floor, or
one whose minimum resolvable substituted fraction exceeds what you asked about,
gets UNDETERMINED. Absence of an alarm is never evidence by itself
(PMK-RUL-001, PMK-POW-003).

The false-alarm rate is a property of the calibration content, and its behavior
elsewhere was measured instead of assumed. The validation study applied the
shipped, dev-calibrated per-route thresholds to re-minted content under a
declared task alias (`--task-as`). Same-route per-ruling flag rates ran at
6-12x the declared 1% in three of eight held-out (route, task) cells (see
`validation/angle_a/derived/kt2.json`). A certificate's declared false-alarm
rate is therefore trustworthy over the calibration content family. On other
content it weakens to the transfer rates actually measured, and a `scored as`
clause in a certificate is the marker that this caveat applies.

A ruling makes no capability claims. Nothing here states or implies a benchmark
result or a comparison between models. See NOTICE for the claim boundary with
the upstream corpus.
