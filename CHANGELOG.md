# Changelog

All notable changes to punchmark. The format follows Keep a Changelog. Versions follow
SemVer. The rulings-spec version moves independently (see
`src/punchmark/spec/rulings/index.toml`).

## Unreleased

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
- The Angle A validation study (`validation/angle_a/`): held-out identification,
  the false-alarm promise and its measured non-transfer to re-minted content,
  the formatting-ablation kill test, held-out power, the frozen 150-row probe.
- 41 spec rulings, 40 active (PMK-CAL-002 superseded by PMK-CAL-005). Rulings-spec
  at 2.1.0.
- CLI: `fit`, `score`, `certify`, `gate`, `corpus`, `synth`, `census`, `spec`, `env`,
  `cite`, plus `--task-as` declared cross-split scoring and the `--sidecars` directory
  override.
