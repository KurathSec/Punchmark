# Validation

Three studies, all under `validation/` (repo only, never in the sdist). Every number
traces to a committed artifact under the study's `derived/`, regenerated deterministically
by that study's scripts. Where a claim has been narrowed or withdrawn since it was first
recorded, the narrowing is stated here rather than left in the artifact.

## Angle A: calibration on the reference corpus

Fit and calibrate on the 8 dev-split archives, validate on the 8 held-out test-split
archives, zero API calls. Narrative in `validation/angle_a/FINDING.md`. Model
`pmk-m-c52e6e6014883edb`, corpus `pmk-cor-32596a35e0452817`.

| question | result | artifact |
|---|---|---|
| Held-out whole-set identification | 8/8 canonical (exact one-sided 95% lower bound 0.6877); 0.9863 over clustered 150-row subsamples. **KT1 passes** | `kt1.json` |
| False-alarm promise on calibration content | pooled per-ruling flag rate 0.0 across the fit stratum (0.0002 in one of eight cells, the rest 0.0); 0/32 canonical halves flagged. **KT2 holds** | `kt2.json` |
| False-alarm transfer to re-minted content | 3 of 8 held-out cells at 0.0598, 0.1144 and 0.1208 against a declared 0.01. **See the qualification below: this is a localised failure, not a cell-level rate** | `kt2.json`, `kt2_bootstrap.json` |
| Minimum resolvable substituted fraction | rho\* 0.2 to 0.75 per ordered pair at m=750, FAR 0.01, over the 15 of 24 cells that pass the rho=0 self-check | `power_heldout.json` |
| Completion length per task | comprehend 54 to 99 chars; refactor 790 to 1122. Only 0.020 to 0.119 of comprehend draws exceed the 200-char ablation cut, against 0.968 to 0.991 of refactor draws | `lengths.json` |
| Formatting-artefact kill | **withdrawn as a control.** See below | `kt3.json`, `lengths.json` |
| Prompt-change + two-week transfer probe | 8/8 identification (declared confounded; no verdicts) | `ablation_probe.json` |

### The transfer finding, qualified

The per-cell criterion judges each rate against a binomial band at n=5000. Those 5000
rulings are 2500 complementary split-halves of one archive, so they are nowhere near
5000 independent trials, and the band is correspondingly too tight.

Resampling each archive's 74 clusters directly (`kt2_bootstrap.json`) gives **no cell
whose 95% interval excludes the declared 0.01**, zero of eight. The exceedances reproduce
as point estimates and carry intervals reaching zero.

What survives is narrower and more useful than the original claim. The failure is
**localised**: flagging concentrates in a minority of base samples, so excluding them
makes the cell flag nothing. On held-out content, particular base samples drive
per-ruling rates an order of magnitude above the declared rate, and neither the pooled
figure nor the fit stratum warns that they are there. An operating point carried to new
content of the same task can be blown out by a subset of that content without any
aggregate showing it.

What does not survive is reading 0.1208 as a stable cell-level property, or "3 of 8 cells
fail" as a rate. The count failing *significantly* at this sample size is none of eight.

### The formatting ablation, withdrawn

KT3 refits on an ablated view (fences stripped, whitespace collapsed, lowercased,
truncated to 200 characters) and reports 0.991 against 0.9845 canonical, so the recorded
kill condition does not fire. That fact now carries no weight, for two reasons measured
in `lengths.json`. The 200-character cut is close to a no-op on comprehend and removes
almost everything on refactor, so the pooled figure is roughly half untouched canonical
view. And against a whole-archive score of 8 of 8, a floor of 0.50 could not realistically
have been crossed. The formatting objection stands open, and the complement experiment
(drop the first 200 characters, report per task over prefix length) has not been run.

## Angle B: per-response granularity

Per-row four-way identification on the held-out archives: 0.5868 first-draw and 0.6171
pooled over draws, against a 0.25 chance rate, spanning 0.9559 down to 0.2065 across
cells (`per_row_identification.json`). The low end is the information floor: for one route
pair on comprehend, 841 of 1500 shared items produce a byte-identical first draw
(`census.json`). Whole-set aggregation is doing real work, and the per-row rate measures
how much.

`meq_attempt.json` records a run of a released model-equality-testing package on this
corpus. It behaves correctly. An earlier version of that record said otherwise and was
withdrawn; the defect was in this repository's probe script.

## Angle C: purchased routes, and the closed-set limit

The same committed route string bought from two providers at declared-identical FP8, on a
frozen 75-item probe, plus a different-weights control. Narrative in
`validation/angle_c/FINDING.md`.

| question | result | artifact |
|---|---|---|
| Does the shipped instrument flag the provider swap? | No. All four archives read SAME-PRODUCER | `angle_c_evaluation.json` |
| Why not? | The candidate set holds one entry for the shared slug, so the statistic is tested against other model families and never against the same model served by someone else | `angle_c_evaluation.json` |
| Does a candidate set that names the alternative flag it? | Yes, on the long task: SUBSTITUTED at T = -0.0704 against a threshold of +0.055473, with 500 of 500 subsamples below | `frame_swap.json` |
| Is the limit an artefact of using a margin statistic? | No. A competitor-free one-sample fit also misses the swap on both tasks, while flagging the different-weights control on both | `one_sample.json` |
| Are the two providers separable from text at all? | 0.992 on the long task, 0.511 on the short one, against a 0.5 binary chance rate | `angle_c_evaluation.json` |
| Is that a collection-batch artefact? | No. The same route at the same provider across two windows separates at 0.530 against 0.993 cross-provider | `temporal_control.json` |
| Are the two endpoints distinct infrastructure? | They terminate at different edges. This says nothing about the inference backend | `transport.json` |

The closed-set limit is carried into [what a ruling does not show](honesty.md). It is the
sharpest limit in the project: an auditor cannot flag a producer its candidate set does
not name, and enumerating one requires contemporaneous reference material from a producer
the auditor did not think to suspect.

## On the kill tests

A fired kill test would have been a reportable finding rather than a failure of the tool.
The wiring deviations from the recorded kill-test wording (small-n identification, the
incoherent any-single-pair clause) are declared in `validation/angle_a/FINDING.md`.
