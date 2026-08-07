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

A verdict is silent about any producer the candidate set does not name. This is the
sharpest limit here and it is structural rather than statistical. Holding one route out
of the four-route set, that route's own archives are absorbed onto some remaining
candidate 8 times out of 8, with no signal that the true producer is missing
(`validation/angle_a/derived/kt2.json`). Buying the same route string from a second
provider reproduces it on live data: the shipped instrument does not flag the swap,
because the set holds one entry for the shared slug
(`validation/angle_c/derived/angle_c_evaluation.json`).

Naming the alternative fixes it, and the same detector and calibration then return
SUBSTITUTED (`frame_swap.json`). Naming it also means calibrating it, from material
contemporaneous with an archive whose producer you did not suspect, which is the
retrospective problem returning one level up. This is not an artefact of the statistic
being a margin: a competitor-free one-sample fit also misses the swap while flagging a
different-weights control (`one_sample.json`). Read every verdict as relative to its
enumerated set, and treat a set that omits a plausible producer as an unevaluated
question rather than a passed one.

The false-alarm rate is a property of the calibration content, and its behavior
elsewhere was measured instead of assumed. The validation study applied the
shipped, dev-calibrated per-route thresholds to re-minted content under a
declared task alias (`--task-as`). Same-route per-ruling flag rates reached 0.0598,
0.1144 and 0.1208 against the declared 0.01 in three of eight held-out (route, task)
cells (`validation/angle_a/derived/kt2.json`).

That failure is real and it is localised rather than uniform. A cluster bootstrap over
each archive's 74 base samples leaves no cell whose 95% interval excludes the declared
rate (`kt2_bootstrap.json`), which means the flagging concentrates in a minority of items:
exclude them and the cell flags nothing. So the operative warning is not that a stated
rate becomes some larger stated rate. It is that particular content can blow an operating
point out by an order of magnitude while every aggregate looks clean. A certificate's
declared false-alarm rate is trustworthy over the calibration content family, a `scored
as` clause marks where that is not validated, and neither a pooled figure nor a clean fit
stratum is evidence that a blow-out is absent.

A ruling makes no capability claims. Nothing here states or implies a benchmark
result or a comparison between models. See NOTICE for the claim boundary with
the upstream corpus.
