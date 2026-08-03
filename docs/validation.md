# Validation

The validation study for the reference corpus lives in `validation/angle_a/` (repo only,
not in the sdist): fit and calibrate on the 8 public dev-split archives, validate on the
8 held-out test-split archives, zero API calls. Full narrative:
`validation/angle_a/FINDING.md`; every number traces to a committed artifact under
`validation/angle_a/derived/`, regenerated deterministically by `run.py`.

Headline (model `pmk-m-731a3beb2b8c52b8`, corpus `pmk-cor-32596a35e0452817`):

| question | result | artifact |
|---|---|---|
| Held-out whole-set identification | 8/8 canonical; 0.9863 over clustered 150-row subsamples (CI lower 0.965) -- **KT1 passes** | `kt1.json` |
| False-alarm promise on calibration content | flag rate 0.0001 vs declared 0.01; 0/32 canonical pairs flagged -- **KT2 holds** | `kt2.json` |
| False-alarm transfer to re-minted content | pooled 0.0803, lower bound 0.0166 -- **does not transfer**; concentrated in 3 of 16 cells (up to 0.27) | `kt2.json` |
| Formatting-artefact kill (ablated text) | ablated-view identification 0.991 -- the fingerprint is content, **KT3 does not fire** | `kt3.json` |
| Minimum resolvable substituted fraction | rho* 0.1-0.75 per ordered pair at m=750, FAR 0.01; full swaps always resolve | `power_heldout.json` |
| Prompt-change + two-week transfer probe | 8/8 identification (declared confounded; no verdicts) | `ablation_probe.json` |

The transfer row is the study's load-bearing caveat and is carried into
[what a ruling does not show](honesty.md): a certificate's declared false-alarm rate is a
property of the calibration content family, and the `scored as` clause marks rulings
where it is not validated.

A fired kill test would have been a reportable finding, not a failure of the tool; the
wiring deviations from the recorded kill-test wording (small-n identification, the
incoherent any-single-pair clause) are declared in FINDING.md.
