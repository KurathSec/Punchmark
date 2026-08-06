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
