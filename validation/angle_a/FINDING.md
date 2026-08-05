# Angle A finding

Fit and calibrate on the 8 committed dev-split archives. Validate on the 8 held-out
test-split archives. Zero API calls, $0, one machine. Model `pmk-m-c52e6e6014883edb`,
corpus `pmk-cor-32596a35e0452817`, spec 2.0.0. Every number below is read from a
committed artifact in `derived/`, regenerated deterministically by `run.py`. None is
hand-edited.

## The one-paragraph result

A text-only producer fingerprint exists in ordinary benchmark completions. The signal
is carried by content, and formatting artefacts do not account for it. It survives a
re-minted item set, a prompt-condition change and a two-week window gap. Whole-set
identification of the held-out archives is 8/8 canonically and 0.986 over clustered
150-row subsamples (CI lower bound 0.965). The recorded kill tests do not fire. What
does NOT survive is the transfer of the calibrated false-alarm rate to content the
thresholds were not calibrated on. The per-ruling within-window flag rate, promised
at 1%, is 0.0% on calibration content and runs at 6-12% in three of the eight
held-out (route, task) cells. The identification half of the instrument generalizes.
The operating point is a property of the calibration content family, and the
certificate's `scored as` clause marks where this caveat applies.

## KT1: held-out whole-set identification (`derived/kt1.json`)

- Canonical whole-archive: **8/8** (exact one-sided 95% lower bound 0.688 at n=8;
  reported as a count, never as an accuracy with decimal places).
- Clustered 150-row subsamples, 2,000 per archive: pooled **0.9863**,
  cluster-bootstrap 5% lower bound **0.965**. Weakest cells:
  `refactor_test` Llama-3.3-70B 0.9295, `comprehend_test` Llama-3.1-8B 0.9725. The
  other six are >= 0.9945.
- Tier B/C only (the 24 structurally unseen families): >= 0.944 in seven of eight
  cells, but **0.46 for DeepSeek `refactor_test`**. At this cluster count these
  numbers are suggestive and do not reach significance. Family-level generalization
  is genuinely weak for that cell and must not be claimed from the pooled number.
- Wiring (declared deviation): the recorded "accuracy >= 0.95 at 1% FAR" cannot be
  resolved by 8 whole archives (8/8 bounds only 0.69). The contractual form is
  therefore the clustered-subsample population, with canonical 8/8 as a necessary
  condition.
- **KT1 threshold: canonical 8/8 AND pooled >= 0.95 AND CI lower >= 0.90 -> PASS.**

## KT2: the false-alarm promise (`derived/kt2.json`)

The measurement unit is one RULING. Each cluster-respecting split-half of an archive
yields two rulings at the declared 1% operating point, and rates are per ruling
(2 x 2,500 splits = 5,000 rulings per archive). An earlier draft of this study
counted the two-ruling union event against the per-ruling promise, overstating rates
~2x. The unit is now declared wherever a rate is compared to the far.

The two strata are kept separate. Each archive's rate is judged against the declared
far plus binomial noise at its own n (`cell_tolerance` = 0.0144), because a
concentrated failure must not hide under a pooled mean.

- **Recorded form (fit stratum: same-route rulings inside one window of the
  calibration content):** per-ruling flag rate **0.0000** in seven of the eight fit
  cells, and **0.0002** in comprehend DeepSeek-V4-Flash (one flagged ruling in 5,000,
  about 70x under the 0.0144 cell tolerance); pooled fit-stratum rate **0.0**.
  Canonical seed-pinned pairs flagged: **0 of 16** fit-stratum halves (and 0 of 16
  held-out halves). No fit cell exceeds tolerance. The kill **does not fire**.
- **Transfer finding (held-out stratum: dev-calibrated thresholds applied to
  re-minted content under the declared `--task-as` alias):** pooled per-ruling rate
  **0.037**, with **3 of 8 cells exceeding tolerance**: Llama-3.1-8B
  `comprehend_test` **0.121**, Llama-3.1-8B `refactor_test` **0.114**, Llama-3.3-70B
  `refactor_test` **0.060**. The other five cells are <= 0.0006. Each exceeding cell
  is 6-12x the promise over 5,000 rulings, far outside binomial noise even after
  selecting 3 of 16 cells. (The pooled archive-level bootstrap lower bound, 0.0076,
  does not clear the far on its own. At n=8 archives a pooled mean is the wrong lens
  for a concentrated effect, and that is why the criterion is per cell.) The same
  three cells fail the rho=0 self-check in `derived/power_heldout.json`, so the same
  fact shows up twice. Consequence, carried into `docs/honesty.md`: a certificate's
  declared FAR is trustworthy over the calibration content family, and on other
  content it weakens to the rates measured here.
- Wiring (declared deviation): the recorded "ANY single flagged same-route pair
  breaks the operating point" is statistically incoherent under resampling, since at
  a true 1% rate, >=1 flag among 32 canonical halves occurs with probability ~0.27.
  The kill therefore fires on per-cell tolerance exceedance, or on a pooled
  fit-stratum lower bound over the far. Canonical flags are investigated and
  declared. They do not trigger an automatic kill.
- Leave-one-route-out (diagnostic only: the route unit n=4 sits exactly at the LOO
  floor, so there are no confidence intervals): 3-way identification is 6/6 for every
  held-out route. Every excluded route maps closed-set onto some remaining candidate,
  the open-set hazard that PMK-CRT-003 exists for.
- Null-integrity check (file-order halves of the 3h58m `refactor_test` window): no
  half flagged. This is a check on the oracle-circularity exposure and does not
  amount to a verdict. The S2 scorer's note stands verbatim: the same-producer
  positive pairs rest on the provider's own claim that no substitution occurred
  inside the window. The window restriction narrows this exposure and does not close
  it.

## KT3: formatting ablation (`derived/kt3.json`)

Pooled 150-row subsample identification on held-out archives, detector refitted per
view: RAW\@1 **0.9895**, CANON\@1 **0.9845**, ABL\@1 **0.991**. The recorded form
(raw > 0.95 AND ablated < 0.50) **does not fire**. The ablated channel (fences
stripped, lowercased, whitespace collapsed, truncated to 200 characters) identifies
essentially as well as raw text. The fingerprint is carried by content and does not
reduce to a prompt-template artefact. The instrument's premise of consuming other
people's archives survives its sharpest recorded objection.

## Power and the minimum resolvable separation (`derived/power_heldout.json`, model file)

At the shipped thresholds (m=750, FAR 0.01), held-out seeded substitutions resolve at
rho* between **0.1 and 0.75** depending on the ordered pair. Every pair resolves a
full swap. The shipped power table now covers every calibrated far, so a ruling at
any declared operating point has a table to consult. The rho=0 self-check is enforced
inside `power_analysis` itself. The dev calibration passes it. The three held-out
transfer cells fail their held-out version and are flagged per entry in the artifact.
At the 150-row probe size the hardest pairs are marginal by design, and output (d)
reports it: a 150-row probe inherits that limit and says so. Seeded-substitution
fidelity to real vendor changes cannot be validated and stands as a bound
(PMK-POW-004).

## Transfer probe: the ablation arm (`derived/ablation_probe.json`)

The upstream ablation-arm archives (same four routes, k=1, a DIFFERENT prompt
condition, collected ~two weeks after the calibration corpus, serving drift
uncontrolled) identify **8/8** under the shipped model. They are declared confounded:
identification only, no verdict vocabulary, excluded from all calibration. Even so,
as a joint stress of prompt change plus window gap, they are stronger transfer
evidence than KT3's synthetic ablation alone.

## The frozen probe (`derived/probe_manifest.json`)

150 rows (75 per task), selected from dev archives only (enforced by refusal), by
worst-ordered-pair margin utility under coverage caps, seed-pinned. Its expected
power is the m=150 column of the shipped power table: marginal for the hardest pairs,
and declared as such.

## Canonical rulings (`derived/rulings.jsonl`, `derived/certificates.txt`)

All 8 held-out archives rule **SAME-PRODUCER** at FAR 0.01 with `scored as` recorded.
Ruling ids pin detector v1, candidate set `pmk-cs-2f6b636d317d3ffe`, the operating
point and the corpus hash. Read with the KT2 transfer caveat: for `scored as` rulings
the nominal FAR is not validated on that content, and for the three exceeding cells
it is measured to be 6-12x looser.

## What this does not show

Everything in `docs/honesty.md`, and specifically here: four routes served through
one provider endpoint cannot separate a weights signature from a serving-stack
signature (the pre-committed purchased extension is the only design that can). The
committed window cannot rule out a substitution present throughout collection. None
of these numbers is a substitution incidence rate for hosted evaluation generally.
The curve is a curve for this asset.

## Corrections to the source dossier, carried

The 23 anomalous rows are zero-draw API error stubs (`{sample, profile, language}`
only), not "rows with fewer than 8 draws". The ladder archives carry no `tier` key.
The collection windows are 2026-06-27/28 (per-run records), not "2026-06-19..24" as
one scoring record states. "k=8" overstates information content: most rows collapse
to 1-2 distinct draws at temperature 0 (`derived/census.json`), and one row is one
evidence unit throughout.
