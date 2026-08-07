# Changelog

All notable changes to punchmark. The format follows Keep a Changelog. Versions follow
SemVer. The rulings-spec version moves independently (see
`src/punchmark/spec/rulings/index.toml`).

## 0.1.0

### Added
- Scaffold: native archive reader (filename-is-oracle, two row schemas, error-stub
  tolerance), window sidecars, versioned text views and hashed char-n-gram features,
  the detector seam with the trivial reference detector, cross-fitted null calibration,
  seeded-substitution power analysis with the minimum-resolvable-separation output,
  fitted-model files, append-only rulings, certificates, the artifact-only CI gate,
  the planted-truth synthetic harness, and the three mechanical gates.
- The calibrated `chargram` detector (per-route Jeffreys multinomial over hashed
  3-5-grams, CANON@1 primary view) as the default; per-(task, route, far, m)
  operating points; the reference corpus manifest (manifest + local rebuild, no
  completion text re-published), committed collection-window sidecars, and the
  shipped default model (`--model default`).
- The Angle A validation study (`validation/angle_a/`): held-out identification
  (8/8 canonical, 0.9863 over clustered 150-row subsamples), the false-alarm promise
  on calibration content, held-out power, the frozen 150-row probe, and per-task
  completion lengths.
- The Angle B study (`validation/angle_b/`): per-response identification at 0.5868
  first-draw against a 0.25 chance rate, and a recorded run of a released
  model-equality-testing package on this corpus.
- The Angle C study (`validation/angle_c/`): the same committed route string purchased
  from two providers at declared-identical FP8, a same-provider two-window control, a
  transport-layer record kept outside the detector, the verdict frame re-run with the
  alternative enumerated, and a competitor-free one-sample test.
- 41 spec rulings, 40 active (PMK-CAL-002 superseded by PMK-CAL-005). Rulings-spec
  at 2.1.0.
- CLI: `fit`, `score`, `certify`, `gate`, `corpus`, `synth`, `census`, `spec`, `env`,
  `cite`, plus `--task-as` declared cross-split scoring and the `--sidecars` directory
  override.

### Notes on claims

- The false-alarm transfer result is reported as a **localised** failure. Per-ruling
  rates of 0.0598, 0.1144 and 0.1208 appear against a declared 0.01 on held-out content,
  but a cluster bootstrap over each archive's 74 base samples leaves no cell whose 95%
  interval excludes the declared rate. The flagging concentrates in a minority of base
  samples. See `docs/validation.md`.
- The formatting-ablation kill test is **withdrawn as a control**: the 200-character cut
  is close to a no-op on one task and removes almost everything on the other, so the
  pooled figure cannot support a claim about formatting.
- A verdict is silent about any producer the candidate set does not name. This is the
  sharpest limit in the project and it is stated in `docs/honesty.md`.
