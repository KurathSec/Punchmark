# punchmark

<!-- Release links. Remove this block, marker to marker, when this repository is
     submitted as anonymous supplementary material. The Data provenance section
     below carries a second identifying link and needs the same treatment. -->
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21833314.svg)](https://doi.org/10.5281/zenodo.21833314)
[![PyPI](https://img.shields.io/pypi/v/punchmark)](https://pypi.org/project/punchmark/)
[![docs](https://img.shields.io/badge/docs-online-blue)](https://kurathsec.github.io/Punchmark/)
<!-- End release links. -->

**No practitioner can currently re-certify an already-published benchmark number backwards
from the responses it was computed on.** A hosted route name persists while whatever serves
it moves. Every runnable producer-identity tool needs fresh probes issued live to an
endpoint that has since changed. punchmark is the retrospective half: point it at the
response archive you already have and get a producer-identity verdict for the number you
already published.

```
pip install punchmark
punchmark fit    dev/*.jsonl.gz --candidates routeA,routeB --out model.pmk-model.json
punchmark score  archive.jsonl.gz --model model.pmk-model.json --far 0.01
punchmark certify --ruling pmk-r-...
```

Four outputs:

1. **A fitted whole-set producer identifier** with its printed
   miss-rate-versus-false-alarm curve over a named candidate set.
2. **A per-(route, window) ruling**: `SAME-PRODUCER`, `SUBSTITUTED` or `UNDETERMINED`,
   issued at an operating point you declared yourself (as opposed to one you inherited).
   `UNDETERMINED` is a verdict in its own right: it is what a passing statistic means
   when your archive could not have resolved the substitution you asked about.
3. **A one-line certificate** attachable to the published score:
   *"producer identity of route R over window W HOLDS at false-alarm rate 0.01 against
   candidate set C."*
4. **The minimum substituted fraction your k and item count could have resolved**, so a
   null result reads as a power limit and not as reassurance.

## What a verdict means, and what it does not

A ruling certifies the **route label as served** within a **closed candidate set**. It is
never a statement about model weights: a public route name does not denote a fixed
configuration, and punchmark does not repair that. A `SAME-PRODUCER` ruling means exactly
"a substitution of the declared fraction by any candidate in the set would have been
flagged with the calibrated power, and none was", and nothing more. See `docs/honesty.md`
for the full list of things a ruling does not show.

## How it works

- **Inputs**: gzipped-JSONL response archives, one row per item with k draws of response
  **text only**: no logprobs, no headers, no timing. The route name comes from the
  archive filename (fixed by you at collection time); the collection window comes from a
  sidecar you write. Neither is ever inferred from content.
- **Oracle**: by construction. Cross-route labels score identification. Same-route
  subsets inside one window calibrate the false-alarm rate. Seeded substitutions (spliced
  from another route's rows over the identical item set) measure power.
- **Discipline**: every threshold is an empirical null quantile, cross-fitted so
  calibration optimism cannot silently overshoot the declared false-alarm rate. Every
  committed artifact is byte-stable and content-addressed. Rulings are append-only: a
  ruling can be superseded but is never edited. The CI gate fails any calibration move
  that arrives without a declared version bump.

## Status

0.1.0, the first release. The calibrated chargram detector, the reference
corpus manifest, the shipped default model and the held-out validation study
(`validation/angle_a/FINDING.md`) are all committed; the numbers in `docs/validation.md`
trace to committed derived artifacts. Nothing in this repository states or implies a
finding about the capabilities of any model.

## Data provenance

The reference calibration corpus is defined over the committed response archives of the
public [Spaghetti Architect](https://github.com/KurathSec/Spaghetti-Architect) benchmark,
pinned by commit and per-file hash in `calibration/spaghetti/MANIFEST.json`. No
completion text is re-published here; the command
`punchmark corpus rebuild --corpus calibration/spaghetti --source <checkout>`
verifies a local checkout byte-for-byte. Results in this repository are statements
about producer identity of those archives as re-analysed here. They are not claims
about, or corrections to, any capability table published from that benchmark
elsewhere.

## License

MIT.
