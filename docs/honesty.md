# What a ruling does not show

Every one of these limits is structural, not a caveat to be optimized away. The
certificate wording enforces the first two (PMK-CRT-002, PMK-CRT-003); the rest are
carried here and in NOTICE.

**It does not verify weights.** A certificate says the route label was consistent with
the calibrated fingerprint, not that a particular set of parameters served the request.
A public route name does not denote a fixed configuration, and punchmark does not repair
that. Reading SAME-PRODUCER as "the model did not change" is reading it wrong, and the
certificate wording makes that hard.

**It is closed-set.** A producer outside the declared candidate set will be mapped to
its nearest member. SAME-PRODUCER is "best match within candidate set C at the declared
operating point", never an identity proof.

**It cannot detect a substitution present throughout calibration.** If a different
artifact was silently served for the whole collection window, that artifact IS the
fingerprint. The instrument detects change relative to a labelled window, not truth.
The same-producer null additionally rests on the provider's implicit claim that no
substitution occurred inside the window; the window restriction narrows this exposure
and does not close it (PMK-CAL-003).

**It cannot say what changed.** A SUBSTITUTED ruling is a flag attributable to nothing:
ground truth about what changed never arrives. Weights, sampling, serving stack, and
safety filters are indistinguishable from response text alone.

**Its power numbers are a best case.** Seeded substitutions are spliced from another
candidate's responses over the identical items, inside one window. Real substitutions
arrive with a date offset, hit time-contiguous traffic, and may involve an off-candidate
producer. This fidelity gap cannot be validated from committed data and stands as a
bound wherever power numbers appear (PMK-POW-004).

**A null is only as good as its power.** An archive below the calibrated floor, or one
whose minimum resolvable substituted fraction exceeds what you asked about, gets
UNDETERMINED -- absence of an alarm is never evidence by itself (PMK-RUL-001,
PMK-POW-003).

**It makes no capability claims.** Nothing here states or implies a benchmark result or
a comparison between models; see NOTICE for the claim boundary with the upstream corpus.
