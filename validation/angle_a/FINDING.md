# Angle A finding

Fit and calibrate on the 8 committed dev-split archives; validate on the 8 held-out
test-split archives. Zero API calls, $0, one machine. Model `pmk-m-731a3beb2b8c52b8`,
corpus `pmk-cor-32596a35e0452817`, spec 1.1.0. Every number below is read from a
committed artifact in `derived/`, regenerated deterministically by `run.py`; none is
hand-edited.

## The one-paragraph result

A text-only producer fingerprint exists in ordinary benchmark completions, it is a
content signal rather than a formatting artefact, and it survives a re-minted item set,
a prompt-condition change and a two-week window gap. Whole-set identification of the
held-out archives is 8/8 canonically and 0.986 over clustered 150-row subsamples
(CI lower bound 0.965). The recorded kill tests do not fire. What does NOT survive is
the transfer of the calibrated false-alarm rate to content the thresholds were not
calibrated on: the within-window same-route flag rate, promised at 1%, holds at 0.01%
on calibration content and rises to a pooled 8% (up to 27% for one route) on the
re-minted held-out content. The identification half of the instrument generalizes; the
operating point is a property of the calibration content family, and the certificate's
`scored as` clause is the marker that this caveat applies.

## KT1 -- held-out whole-set identification (`derived/kt1.json`)

- Canonical whole-archive: **8/8** (exact one-sided 95% lower bound 0.688 at n=8;
  reported as a count, never as an accuracy with decimals).
- Clustered 150-row subsamples, 2,000 per archive: pooled **0.9863**,
  cluster-bootstrap 5% lower bound **0.965**. Weakest cells:
  `refactor_test` Llama-3.3-70B 0.9295, `comprehend_test` Llama-3.1-8B 0.9725; the
  other six are >= 0.9945.
- Tier B/C only (the 24 structurally unseen families; suggestive, not significant at
  this cluster count): >= 0.944 in seven of eight cells; **0.46 for DeepSeek
  `refactor_test`** -- family-level generalization is genuinely weak for that cell and
  must not be claimed from the pooled number.
- Wiring (declared deviation): the recorded "accuracy >= 0.95 at 1% FAR" cannot be
  resolved by 8 whole archives (8/8 bounds only 0.69), so the contractual form is the
  clustered-subsample population plus canonical 8/8 as a necessary condition.
- **KT1 threshold: canonical 8/8 AND pooled >= 0.95 AND CI lower >= 0.90 -> PASS.**

## KT2 -- the false-alarm promise (`derived/kt2.json`)

Two strata, deliberately separate.

- **Recorded form (fit stratum -- same-route pairs inside one window of the
  calibration content):** pooled flag rate **0.0001** against the declared 0.01
  (bootstrap upper bound 0.0002); canonical seed-pinned split-half pairs flagged:
  **0 of 32**. The recorded kill condition -- rewired, see below -- **does not fire**.
- **Transfer finding (held-out stratum -- dev-calibrated thresholds applied to
  re-minted content under the declared `--task-as` alias):** pooled flag rate
  **0.0803**, bootstrap 5% lower bound **0.0166 > 0.01**: the declared false-alarm
  rate **does not transfer** to re-minted content. It concentrates in three cells --
  Llama-3.1-8B `comprehend_test` 0.272, Llama-3.1-8B `refactor_test` 0.239,
  Llama-3.3-70B `refactor_test` 0.130; the other thirteen archives are <= 0.0012 --
  and the same three cells fail the rho=0 self-check in `derived/power_heldout.json`,
  which is the same fact seen twice. Consequence, carried into `docs/honesty.md`: a
  certificate's declared FAR is trustworthy over the calibration content family; on
  other content it weakens to the rates measured here.
- Wiring (declared deviation): the recorded "ANY single flagged same-route pair breaks
  the operating point" is statistically incoherent under resampling -- at a true 1%
  rate, >=1 flag among 32 canonical pairs occurs with probability ~0.27 -- so the kill
  fires iff the fit stratum's bootstrap lower bound exceeds the declared FAR; canonical
  flags are investigated and declared, never auto-kill.
- Leave-one-route-out (diagnostic only; route unit n=4 sits exactly at the LOO floor,
  no confidence intervals): 3-way identification 6/6 for every held-out route; every
  excluded route maps closed-set onto some remaining candidate, which is the open-set
  hazard PMK-CRT-003 exists for.
- Null-integrity check (file-order halves of the 3h58m `refactor_test` window): no
  half flagged; a check on the oracle-circularity exposure, not a verdict. The S2
  scorer's note stands verbatim: the same-producer positive pairs rest on the
  provider's own claim that no substitution occurred inside the window; the window
  restriction narrows this exposure and does not close it.

## KT3 -- formatting ablation (`derived/kt3.json`)

Pooled 150-row subsample identification on held-out archives, detector refitted per
view: RAW\@1 **0.9895**, CANON\@1 **0.9845**, ABL\@1 **0.991**. The recorded form
(raw > 0.95 AND ablated < 0.50) **does not fire**; the ablated channel -- fences
stripped, lowercased, whitespace collapsed, truncated to 200 characters -- identifies
essentially as well as raw text. The fingerprint is a content signal, not a prompt-
template artefact, and the instrument's premise of consuming other people's archives
survives its sharpest recorded objection.

## Power and the minimum resolvable separation (`derived/power_heldout.json`, model file)

At the shipped thresholds (m=750, FAR 0.01), held-out seeded substitutions resolve at
rho* between **0.1 and 0.75** depending on the ordered pair; every pair resolves a full
swap. At the 150-row probe size the hardest pairs are marginal by design (worst-pair
miss 0.27-0.48 on the dev calibration), which is output (d) doing its job: a 150-row
probe inherits that limit and says so. The three cells with failed rho=0 self-checks
are the KT2 transfer cells; their power numbers are optimistic and flagged in the
artifact. Seeded-substitution fidelity to real vendor changes cannot be validated and
stands as a bound (PMK-POW-004).

## Transfer probe -- the ablation arm (`derived/ablation_probe.json`)

The upstream ablation-arm archives (same four routes, k=1, a DIFFERENT prompt
condition, collected ~two weeks after the calibration corpus, serving drift
uncontrolled) identify **8/8** under the shipped model. Declared confounded --
identification only, no verdict vocabulary, excluded from all calibration -- but as a
joint stress of prompt change plus window gap it is stronger transfer evidence than
KT3's synthetic ablation alone.

## The frozen probe (`derived/probe_manifest.json`)

150 rows (75 per task), selected from dev archives only (enforced by refusal), by
worst-ordered-pair margin utility under coverage caps, seed-pinned. Its expected power
is the m=150 column of the shipped power table -- marginal for the hardest pairs,
declared.

## Canonical rulings (`derived/rulings.jsonl`, `derived/certificates.txt`)

All 8 held-out archives rule **SAME-PRODUCER** at FAR 0.01 with `scored as` recorded;
ruling ids pin detector v1, candidate set `pmk-cs-2f6b636d317d3ffe`, the operating
point and the corpus hash. Read with the KT2 transfer caveat: for `scored as` rulings
the nominal FAR is not validated on that content.

## What this does not show

Everything in `docs/honesty.md`, and specifically here: four routes served through one
provider endpoint cannot separate a weights signature from a serving-stack signature
(the pre-committed purchased extension is the only design that can); the committed
window cannot rule out a substitution present throughout collection; and none of these
numbers is a substitution incidence rate for hosted evaluation generally -- the curve
is a curve for this asset.

## Corrections to the source dossier, carried

The 23 anomalous rows are zero-draw API error stubs (`{sample, profile, language}`
only), not "rows with fewer than 8 draws"; the ladder archives carry no `tier` key;
the collection windows are 2026-06-27/28 (per-run records), not "2026-06-19..24" as
one scoring record states; "k=8" overstates information content -- most rows collapse
to 1-2 distinct draws at temperature 0 (`derived/census.json`), and one row is one
evidence unit throughout.
