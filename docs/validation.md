# Validation

The validation study for the reference corpus lives in `validation/angle_a/`
(repo only, not in the sdist): fit and calibrate on the 8 public dev-split
archives, validate on the 8 held-out test-split archives, zero API calls. The
full narrative is `validation/angle_a/FINDING.md`. Every number traces to a
committed artifact under `validation/angle_a/derived/`, regenerated
deterministically by `run.py`.

Headline (model `pmk-m-c52e6e6014883edb`, corpus `pmk-cor-32596a35e0452817`):

| question | result | artifact |
|---|---|---|
| Held-out whole-set identification | 8/8 canonical; 0.9863 over clustered 150-row subsamples (CI lower 0.965). **KT1 passes** | `kt1.json` |
| False-alarm promise on calibration content | per-ruling flag rate 0.0000 in every fit cell; 0/32 canonical halves flagged. **KT2 holds** | `kt2.json` |
| False-alarm transfer to re-minted content | 3 of 8 held-out cells at 0.06-0.12 vs the declared 0.01 (tolerance 0.0144). **Does not transfer** for those cells | `kt2.json` |
| Formatting-artefact kill (ablated text) | ablated-view identification 0.991, so the fingerprint is content. **KT3 does not fire** | `kt3.json` |
| Minimum resolvable substituted fraction | rho* 0.1-0.75 per ordered pair at m=750, FAR 0.01; full swaps always resolve; rho=0 self-check enforced | `power_heldout.json` |
| Prompt-change + two-week transfer probe | 8/8 identification (declared confounded; no verdicts) | `ablation_probe.json` |

The transfer row is the study's central caveat, and it is carried into
[what a ruling does not show](honesty.md). A certificate's declared false-alarm
rate is a property of the calibration content family, and the `scored as`
clause marks rulings where it is not validated.

A fired kill test would have been a reportable finding. It would not have meant
the tool failed. The wiring deviations from the recorded kill-test wording
(small-n identification, the incoherent any-single-pair clause) are declared in
FINDING.md.
