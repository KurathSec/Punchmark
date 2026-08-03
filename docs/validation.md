# Validation

The validation study for the reference corpus lives in `validation/` (repo only, not in
the sdist) and has not run yet: this page gains its numbers when `validation/angle_a/`
lands, and every number on it will trace to a committed derived artifact there.

What the study will report, and against which pre-registered thresholds:

- **KT1 -- held-out identification.** Clustered-subsample whole-set identification on
  the held-out archives at the declared 1% false-substitution-alarm rate, with a
  clustered-bootstrap confidence interval; the canonical whole-archive identifications
  reported alongside with an exact small-n bound, never as a bare accuracy.
- **KT2 -- the false-alarm promise.** Measured within-window same-route flag rate
  against the declared 1%, tested one-sided with cluster respect; canonical seed-pinned
  split-half pair rulings reported individually.
- **KT3 -- the formatting ablation.** Identification under the raw, canonical and
  ablated text views, plus a format-channel/content-channel stratification, so a
  template-artefact detector cannot pass as a producer identifier.
- **Power.** The miss-rate-versus-false-alarm curve and the minimum resolvable
  substituted fraction rho* per ordered candidate pair, with each pair's
  indistinguishable-item rate printed as its information floor.

A fired kill test is a reportable finding, not a failure of the tool.
