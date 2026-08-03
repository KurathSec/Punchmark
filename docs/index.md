# punchmark

**No practitioner can currently re-certify an already-published benchmark number
backwards from the responses it was computed on.** A hosted route name persists
while whatever serves it moves. Every runnable producer-identity tool needs
fresh probes, issued live to an endpoint that has since changed. punchmark is the
retrospective half: point it at the response archive you already hold and get a
producer-identity verdict for the number you already published.

## The four outputs

1. **A fitted whole-set producer identifier** over a named candidate set, with
   its miss-rate-versus-false-alarm curve printed at fit time.
2. **A per-(route, window) ruling** of `SAME-PRODUCER`, `SUBSTITUTED` or
   `UNDETERMINED`, at an operating point you declared yourself. `UNDETERMINED`
   is a verdict in its own right: it is what a passing statistic means when
   your archive could not have resolved the substitution you asked about.
3. **A one-line certificate** attachable to the published score; see
   [Certificates](certificates.md) for how to read one field by field.
4. **The minimum substituted fraction your k and item count could have
   resolved** (rho\*). A null result therefore reads as a power limit. It is
   not reassurance.

## What a verdict does not mean

A ruling certifies the **route label as served** within a **closed candidate
set**. It is never a statement about model weights: a public route name does not
denote a fixed configuration, and punchmark does not repair that. `SAME-PRODUCER`
means "a substitution of the declared fraction by any candidate in the set
would have been flagged with the calibrated power, and none was". It means
nothing more than that. A producer outside the declared set was never
considered, and nothing here states or implies a finding about the capabilities
of any model. See
[Honesty](honesty.md) for the full list of things a ruling does not show.

Start with the [Quickstart](quickstart.md). The input format is specified in
[Archives](archives.md), and every decision the results depend on is a numbered,
immutable [spec ruling](spec/rulings.md) (`punchmark spec list`).
