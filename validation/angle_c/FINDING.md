# Angle C: the same slug, served by two providers

What was bought, and what it measures. Every number here comes from
`derived/angle_c_evaluation.json` and `derived/collection_summary.json`, both regenerated
by `evaluate.py` and `summarize.py` from the archives, and neither hand-edited.

## The question

Angle A calibrated a producer identifier on sixteen archives from one provider. It could
not answer the question a practitioner actually faces, because every route in it came
from the same endpoint: if a hosted route keeps its name and its declared precision but
is served by a different provider, does the identifier notice?

Angle C buys that case. `meta-llama/Llama-3.3-70B-Instruct-Turbo` is served by both
DeepInfra and Together at provider-declared FP8, under the exact slug the committed June
corpus was collected from. Both sides were re-collected inside one hour on 2026-08-06,
on the same 75-item probe, at one declared fan-out width. A different-weights control
pair (the 8B at the same provider) was collected in the same window to say whether the
comparison had any power at all.

## The result in one line

The shipped instrument does not flag the provider change. A separate detector, built for
the purpose and told that the two providers are different labels, can partly separate
them on one of the two tasks and not on the other.

## C1: verification under the shipped model

The shipped model is unchanged, and its four-route candidate set holds one entry for this
slug. Both provider archives declare that slug, so the shipped model is being asked
exactly the practitioner's question: does this archive read as the route it claims to be?

| archive | task | T | threshold | verdict at rho_target 1.0 |
|---|---|---|---|---|
| DeepInfra | comprehend | +0.2370 | -0.0152 | SAME-PRODUCER |
| DeepInfra | refactor_dev | +0.2711 | -0.0565 | SAME-PRODUCER |
| Together | comprehend | +0.2159 | -0.0152 | SAME-PRODUCER |
| Together | refactor_dev | +0.2088 | -0.0565 | SAME-PRODUCER |

Every T is positive and far above threshold, so no archive is anywhere near a
SUBSTITUTED verdict. The Together archive reads as the declared route about as strongly
as the DeepInfra one does.

That sentence is worth very little on its own, and the instrument says so itself. Rerun
at a stronger `rho_target` and all four verdicts change:

| rho_target | verdict, all four archives |
|---|---|
| 1.0 (punchmark's default) | SAME-PRODUCER |
| 0.5 | UNDETERMINED, power limit |
| 0.2 | UNDETERMINED, power limit |

At 75 items the reported `rho_min` is 1.0, so SAME-PRODUCER here carries its weakest
possible meaning: a substitution of every single item by another candidate in the set
would have been caught, and nothing smaller. Asked for anything stronger the instrument
refuses rather than reassures, and names the candidates it lacks power against. This is
the designed behaviour rather than a surprise, and it is the reason the headline is not
"punchmark confirms the route was unchanged".

### Correction: the non-detection is first of all about the candidate set

An earlier version of this finding gave `rho_min = 1.0` as **the** reason the provider
change went unflagged. That mis-attributes to a shortage of power what is first of all a
property of the alternative space, and the correction matters more than the original
claim did.

The shipped candidate set holds one entry for the committed slug. Both provider archives
declare that slug, so T compares each archive against the **other three model families**
and against nothing else. A same-model swap between providers is not among the
alternatives the statistic is tested against. The test can report that an archive is
better explained by DeepSeek, the 8B or Mistral; it has no term for "the same model,
served by someone else".

So `rho_min = 1.0` is a real and separate fact, and it means the resolvable fraction
*against those three model-family alternatives*, measured by splicing their rows in. No
provider swap was ever spliced, so it is not a power statement about the swap that
actually occurred.

The same limit appears from the other direction in Angle A's leave-one-route-out
diagnostic, where every excluded route maps cleanly onto some remaining candidate. An
auditor cannot flag an alternative it does not enumerate, and an operating point says
nothing about producers outside the set it was calibrated over. That belongs beside
`rho_min` in any honest report, and the instrument does not yet print it.

## C2: identification under a separate side model

Verification asks whether an archive clears a calibrated threshold. Identification asks
which of several labels fits best. They are different questions and are never merged
here. The side model is fit and stored under `validation/angle_c/`, never under
`calibration/`, with provider-disambiguated labels so that "which provider" is a question
with a checkable answer. It is not the shipped operating point and is not offered as one.

| archive | task | whole-set | subsample rate (m=25) |
|---|---|---|---|
| DeepInfra 70B | comprehend | correct | 0.880 |
| DeepInfra 70B | refactor_dev | correct | 1.000 |
| DeepInfra 8B | comprehend | correct | 1.000 |
| DeepInfra 8B | refactor_dev | correct | 1.000 |
| Together 70B | comprehend | **wrong** | **0.109** |
| Together 70B | refactor_dev | correct | 0.984 |

Pooled 0.8288, cluster-bootstrap 5% lower bound 0.7833, against a chance rate of 0.3333.
The pooled number is above chance, but it is carried by the four easy archives and should
not be read as the provider result.

The provider result is the last two rows, and they disagree with each other. On
`refactor_dev` the Together archive is identified correctly 98.4% of the time. On
`comprehend` it is identified correctly 10.9% of the time, which is below chance.

**Why below chance, and why that is not a defect.** Guessing between indistinguishable
candidates lands at chance rather than under it, so a below-chance rate needs an account.
The full confusion matrix (`c2_confusion` in the artifact, computed from the same draws
as the rate above, so its diagonal is that rate) gives one. The misidentifications are
not spread over the two wrong labels: 0.858 of the draws go to the archive's **same-slug
twin** at DeepInfra and 0.033 to the different-weights control. The discriminator
separates the easy class almost perfectly and collapses the two near-identical ones,
which places one twin below chance by construction in a three-way problem. It is signal
with a predictable structure rather than an inverted label.

**A negative control.** Permuting the row-to-route assignment within a task and refitting
drops pooled subsample identification from 0.8288 to 0.3362 against a chance rate of
0.3333 (`c2_permutation_control`). Labels are permuted per row rather than per archive:
relabelling whole archives would leave each archive's text intact under its new name and
the detector would learn that instead. Per task the permuted rates are 0.2343 and 0.438,
which bracket chance and show that three archives per task is too few to read either one
on its own.

The out-of-fold pairwise margins say the same thing in the units the detector works in:

| task | same slug, DeepInfra vs Together | different weights, 70B vs 8B |
|---|---|---|
| comprehend | +0.0128 and -0.0143 | +0.1475 and +0.8137 |
| refactor_dev | +0.0817 and +0.0608 | +0.2309 and +0.3235 |

The provider separation is roughly an order of magnitude smaller than the weights
separation on comprehend, and around a third of it on refactor.

## C3: power, and the pre-registered gate

rho\* is the smallest substituted fraction resolvable at FAR 0.01 with power 0.8.

| pair | comprehend | refactor_dev |
|---|---|---|
| load-bearing (DeepInfra vs Together, same slug) | does not resolve | 0.5 |
| control (70B vs 8B, different weights) | 0.2 | 0.3 |

"Does not resolve" means the pair failed to reach the power target at every fraction on
the grid, up to and including a total substitution. It is strictly weaker than a large
rho\*, and is reported rather than dropped.

The control pair resolves on both tasks, so the different-weights comparison has power
here and the same-weights null is not vacuous. The load-bearing pair is harder than the
control on both tasks, which is the ordering one would expect if provider is a smaller
perturbation than weights.

### The same-provider control (`derived/temporal_control.json`)

Adversarial review raised the competing explanation the original design could not answer:
the two provider archives were also two separate collections, so anything varying between
collection batches (queue state, batch composition, which replica answered) was
confounded with the provider.

The control is the same route at the same provider in two windows, run through identical
machinery. It exists at both providers, and the two versions deliberately bound different
things: the DeepInfra windows sit about 3.5 hours apart on one day (2026-08-06), so that
pair bounds a collection-batch effect; the Together windows sit 14 days apart
(2026-08-06 and 2026-08-20), so that pair bounds drift over two weeks. Same frozen
probe, same declared width, k and temperature throughout. All contrasts are binary, so
chance is 0.5:

| task | two providers, one window | DeepInfra, two windows (~3.5 h) | Together, two windows (14 days) |
|---|---|---|---|
| comprehend | 0.515 | 0.519 | 0.508 |
| refactor_dev | **0.993** | **0.530** | **0.632** |

On `refactor_dev` the cross-provider contrast reaches 0.993 while the same-provider
contrasts reach 0.530 across hours and 0.632 across two weeks, gaps of 0.463 and 0.361.
What the discriminator reads on the long task is therefore neither a property of the
collection batch nor of two weeks of serving drift at one provider. The 0.632 is itself
worth reading: fourteen days move the discriminator measurably off chance (per side
0.707 and 0.557), so some drift is visible in the text, and it is still nowhere near
the provider gap. On `comprehend` all three sit at chance, consistent with there being
nothing to read at 59 to 75 characters either way.

This could have gone the other way, and it is reported because it could have: had the
same-provider windows separated comparably, the long-task result would have been a
statement about collection conditions and Angle C's one positive finding would not have
stood.

Two limits. One replicate pair per provider on one route bounds a batch effect at one
and two weeks of drift at the other; neither observation generalises beyond this route.
And stability across windows does not establish that what distinguishes the two
providers is the model rather than the serving stack.

### Evidence from outside the text channel (`derived/transport.json`)

The detector reads completion text only, which leaves one question unanswerable from
inside it: are the two endpoints distinct infrastructure, or the same capacity sold twice?
The archive's own text cannot settle that, because the text is what is under test. Review
named the absence of any orthogonal channel as a forfeited check, which it was.

`collect.py` now records transport metadata alongside every draw, and none of it is ever
an input to the detector. The two providers terminate at different edges: Together
responds from behind a CDN that stamps a ray id and a point-of-presence code, DeepInfra
from an application server directly with no CDN headers. Their header sets are disjoint in
the CDN fields, and this is readable for free from each provider's models endpoint, so it
bills no tokens and can be re-checked at any time. Per-draw collection also recorded a
distinct provider-side request id on all 600 draws of each re-collected archive.

What this establishes is narrow: the requests did not arrive at the same front door. It
says nothing about the inference backend, since two distinct edges can proxy to the same
capacity, so it does not rule out a shared or resold upstream and is not evidence about
weights or precision.

### A number that was wrong, and how it was caught

The first version of this evaluation put the archive's full size, m = 75, in the
calibration grid, and reported rho\* = 0.05 for the load-bearing pair on `refactor_dev`.
That would have been a striking claim: a provider swap detectable at a 5% substituted
fraction, better than a change of model size.

It was an artifact. A null draw is a cluster-respecting subsample of at least m rows, so
at m equal to the archive size every draw is the whole archive, and the 5000-draw null
collapsed to one repeated value (`n_distinct = 1`, `sd = 0.00000`). rho\* measured
against a point mass is not a power statement. The null-spread diagnostic in
`evaluate.py` is what surfaced it, and m is now capped strictly below the archive size,
with any null that still collapses flagged as degenerate. At m = 50 every null has 5000
distinct draws and the numbers in the table above are the corrected ones.

This is recorded because the wrong number was the more interesting one, and nothing in
the output would have looked out of place if the spread had not been printed.

The corrected 0.5 now carries the uncertainty this project demands of every null
(`derived/rho_star_uncertainty.json`). A score-conditional cluster bootstrap (B=500
joint resamples of the pair's 40 shared clusters, the m=50 null and the rho=0
self-check rebuilt per resample, both splice directions re-run, pair-worst rho\* each
time) puts 0.88 of the resample mass on 0.5 with a 95% grid interval of [0.3, 0.75]
and a 0.4% self-check failure share: stable at the grid's own resolution, one step of
play either way. Score-conditional is forced rather than chosen: a per-resample
detector refit would place duplicated cluster content in both cross-fitting folds,
which is the leakage the fold map exists to prevent, so the refit variance is declared
uncaptured instead of smuggled in through a broken resampling scheme.

## The decision rule, applied as pre-registered

DESIGN.md fixed the rule before collection. Applying it:

- **Serving-stack identifier** requires the same-weights pair to separate, defined as an
  identification CI lower bound above chance **and** a SUBSTITUTED-direction T. The second
  condition fails outright: every T in C1 is positive, and no archive is ruled
  SUBSTITUTED at any rho_target. Not met. Note what the correction above implies here:
  under the shipped candidate set that condition could not have been met by a provider
  swap at any sample size, because the swap is not in the alternative space. The
  pre-registered rule did not notice this, and neither did we until it was pointed out.
- **Weights identifier** requires the same-weights pair not to separate while the control
  does. This holds on `comprehend`, where the load-bearing pair never resolves and is
  identified below chance while the control resolves at 0.2. It does not hold on
  `refactor_dev`, where the pair resolves at 0.5 and is identified correctly 98.4% of the
  time. Met on one task, contradicted on the other.
- Therefore the pre-registered outcome is **inconclusive, reported with the numbers**.

The two tasks disagreeing is the substantive finding rather than a failure to get one.
The plausible reason is how much text each task produces: comprehend completions average
59 to 75 characters across the three archives, refactor 861 to 893, more than a factor of
ten. A serving-stack signature has to be carried by the text, and a one-line JSON object
carries very little of anything. This is an explanation consistent with the numbers
rather than a tested claim, since Angle C did not vary text volume deliberately.

### A gap in the pre-registration, declared

The power gate says the control pair must resolve "below a stated bound", and no number
was ever stated. The control resolves at 0.2 and 0.3, so the gate passes under any bound
at or above 0.3 and fails under a stricter one. Rather than pick a threshold now that
would decide the outcome after seeing the data, the values are reported and the gap is
recorded as a defect in the pre-registration.

## Limits

- **75 items.** Every conclusion sits on one 75-item probe per route per task, with
  temperature-0 degeneracy reducing effective evidence further. On the two 70B comprehend
  archives, the ones the load-bearing comparison rests on, 57 and 62 of 75 rows have all
  eight draws byte-identical, so those rows carry one draw of evidence rather than eight.
  The 8B archive degenerates far less (3 of 75), which is part of why it is the easier
  case. The power tables are the honest statement of what this supports.
- **The side model is fit and evaluated on the same six archives**, with two-fold
  cross-fitting inside them. It shows that a discriminator can be built when it is told
  the providers apart; it does not show that such a discriminator transfers to archives it
  was not fit on. Angle A already found that this detector's false-alarm rate does not
  transfer across strata, and nothing here contradicts that.
- **Provider is confounded with collection time.** The two sides of each task were
  collected minutes apart rather than simultaneously, which is unavoidable with one
  client.
- **Batch composition was never controlled.** Both providers serve other customers whose
  traffic shares the same server batches and cannot be seen from outside. Matching fan-out
  width equalises this study's own offered load and nothing more.
- **Collection was not perfectly symmetric.** Together shed 4 requests to rate limiting on
  `refactor_dev` against DeepInfra's 0, and one Together draw of 3600 hit the 2048-token
  cap. Both are small and both are recorded rather than smoothed.
- **Declared FP8 on both sides controls the precision class, not the quantization
  scheme.** A difference in scaling granularity or kernel would sit inside what this
  design calls "same precision".

## What this does not claim

- Nothing here is a statement about model capability, quality, or any benchmark score.
  No capability number appears in this study and none can be derived from it.
- Nothing here says either provider served anything other than what it advertised. Every
  archive returned the exact slug requested, and a verdict in this framework is about the
  route label as served and says nothing about weights (PMK-CRT-002).
- The failure to separate the providers is not evidence that the two are the same. It is
  a measured limit on this detector at this item count, which is why the verdicts become
  UNDETERMINED rather than SAME-PRODUCER as soon as a meaningful rho_target is asked for.
- One slug, one pair of providers, one hour, one 75-item probe. Nothing here supports a
  general rate at which hosted routes differ between providers.

## Additions after adversarial review

### The frame with the alternative enumerated (`derived/frame_swap.json`)

The correction above diagnoses the non-detection as a property of the candidate set. That
diagnosis is testable, and leaving it untested left the project's central architectural
claim (the detector is a replaceable slot, the frame supplies the guarantee) asserted
rather than demonstrated.

Re-running the frame with a candidate set that *can* express the alternative, then posing
the substitution question in the frame's own terms: take the Together archive, declare it
to be the DeepInfra route, judge against DeepInfra's own calibrated null at FAR 0.01.

| task | Together declared as DeepInfra | DeepInfra declared honestly |
|---|---|---|
| comprehend | T=+0.0057, not flagged | T=+0.0057, not flagged |
| refactor_dev | **T=-0.0704, SUBSTITUTED** (500/500 subsamples below threshold) | T=+0.0829, not flagged (0.008 below) |

So the frame is not the limitation, and the earlier null was not evidence that a
cross-provider swap is undetectable from archived text. Same detector, same statistic,
same calibration, one more candidate. This does not rescue the shipped instrument for the
practitioner's case: enumerating the second provider needed reference material from that
provider in the same window, which a retrospective auditor does not have.

### Robustness (`derived/robustness.json`)

**Permutation distribution, 200 draws.** The observed pooled identification rate exceeds
every draw of the permutation null on both tasks, so the one-sided p-value is at its floor
of 1/201. The null is wide: mean 0.3148 with a 95th percentile of 0.4733 on comprehend,
mean 0.3263 with 0.5167 on refactor_dev. That width matters for reading the single draw
reported earlier: a permuted rate of 0.438 looks high against a chance rate of 0.3333, and
is an ordinary draw from a null reaching 0.5767.

**Leave-4-out for the shed requests.** Four Together refactor POSTs were shed to rate
limiting; the per-item record cannot identify which, since the counter is per archive. Over
200 random four-item removals the long-task identification rate ranges 0.75 to 1.0, median
0.965. The direction is robust, the magnitude is not: which four items go is worth up to a
quarter of the headline figure. On comprehend the same procedure gives 0.0 to 0.23, the
instability expected of a rate already below chance.

### Is the closed-set limit the regime, or the statistic? (`derived/one_sample.json`)

Review objected that the closed-set claim is definitional rather than measured: the set
statistic is a margin, l(r0) minus the best competitor in C, and a margin cannot respond
to an alternative outside C. No experiment is needed to know that.

The objection names the test that settles it. Drop the competitor set and use a one-sample
fit statistic, the mean length-normalised log-likelihood under the declared route alone,
calibrated against that route's own split-half null. Such a test responds to any departure
from r0 whether or not the substitute is enumerated.

It does not flag the swap, on either task.

| task | threshold | 8B control | honest DeepInfra | **Together (the swap)** | DeepInfra window 2 |
|---|---|---|---|---|---|
| comprehend | -8.9895 | -9.1894 **SUBSTITUTED** | -8.4663 pass | **-8.4390 not flagged** | -8.4897 pass |
| refactor_dev | -9.6831 | -9.6838 **SUBSTITUTED** | -9.3094 pass | **-9.4311 not flagged** | -9.3086 pass |

The test is not simply insensitive: it flags the different-weights control on both tasks,
clears the honestly declared archive on both, and clears a second collection of the same
route at the same provider in a later window. It has power against a real substitution and
misses this one. So the limit is not an artefact of choosing a margin.

The two tasks fail for different reasons and the distinction matters. On comprehend there
is nothing to detect: the swapped archive fits the declared route *better* than that
route's own archive does out of fold, -8.4390 against -8.4663, which is the byte-identity
floor reappearing. On refactor_dev the direction is right and the power is not there, a
0.12 shortfall against a threshold 0.37 away at 75 items. Enumerating the alternative
recovers what the one-sample test cannot, because a margin against a correctly named
competitor is sharper than a fit against a null.

### How large an archive would the one-sample test need? (`derived/power_vs_m.json`)

Review asked for the power-versus-m curve behind that 0.12 shortfall: if the test would
flag the swap at larger archives, "enumeration is required" weakens to "enumeration is
required at these archive sizes". Two curves answer it, kept separate because they answer
different questions. The measured curve, over cluster-respecting subsamples at m = 20 to
68 rows, shows the swap's flag rate rising only near the full archive (0.694 at m=68 on
refactor_dev), and that rise is finite-population shrinkage, not fresh-archive power: at
m=68 a draw holds most of the archive, so null and alternative both collapse onto their
archive means. The different-weights 8B control reaches power 1.0 by m=53 on both tasks
and the second-window control stays at the false-alarm floor throughout, so the curve
machinery has power where power exists.

The fresh-archive answer is a model-based extrapolation (Gaussian cluster means with the
finite-population correction; the sd model fits the seven measured nulls within 1.6%,
and a bad fit would have voided it). On refactor_dev the paired per-cluster shift is
+0.1217 with a 95% CI of [0.052, 0.206] excluding zero, and the crossover lands at
roughly **713 rows for 50% power and 1264 rows for 80%** (CIs 248 to 3864 and 440 to
6846), against the 75 purchased. The naive no-FPC figure a bare sqrt-m scaling gives is
353 rows, understated by about half, and is printed in the artifact as a warning label.
On comprehend the question is a sign, not a crossover: the shift is -0.0273 with CI
[-0.089, +0.004] straddling zero, so whether *any* archive size could flag the swap on
the short task is UNDETERMINED at 41 clusters, and "never" is deliberately not asserted.

So the enumeration claim, refined rather than weakened: at the purchased size the
competitor-free test misses the swap on both tasks; under a stated model it would need
roughly ten times the archive to reach standard power on the long task, with a wide
interval; and on the short task even the sign of the detectable difference is
unresolved. Enumerating the alternative recovers at m=75 what the one-sample test might
reach at m ~ 1000.

### What the separation is made of (`derived/first_draw_side_model.json`, `derived/short_probe.json`)

Two review questions about the side model's 0.992/0.511, answered from held data
through the identical pipeline, candidate frame and subsample seed stream.

Does the long-task separation ride on the draw-multiplicity channel? How often a
temperature-0 endpoint repeats itself across k draws is a serving property, and pooling
draws lets it into the counts. Truncating every row to its first draw removes that
channel entirely, and the binary pair contrast moves from 0.9925 to **0.9745** on
`refactor_dev` while `comprehend` moves from 0.5114 to 0.503. The long-task signal
lives in the response text itself, not in repetition behaviour across draws.

Is "at chance on the short task" a property of the channel, or of 3-to-5-grams? Two
deliberately stronger feature families, character 6-to-8-grams and word 1-to-2-grams,
run through the same crossfit and seeds (with the shipped family reproduced first by
the same local implementation as a reconciliation gate). On `comprehend` they reach
0.5356 and 0.5 against a 0.5 chance rate; on `refactor_dev` the same families reach
0.996 and 1.0, so the probes are not weak, the short-task text is. The at-chance
reading is a property of ~59-character completions under every family tried, not an
artefact of the shipped detector's gram orders, and the claim keeps its stated scope
("to this detector") without needing it.
