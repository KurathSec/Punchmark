# Changelog

All notable changes to punchmark. The format follows Keep a Changelog; versions follow
SemVer. The rulings-spec version moves independently (see
`src/punchmark/spec/rulings/index.toml`).

## Unreleased

### Added
- Scaffold: native archive reader (filename-is-oracle, two row schemas, error-stub
  tolerance), window sidecars, versioned text views and hashed char-n-gram features,
  the detector seam with the trivial reference detector, cross-fitted null calibration,
  seeded-substitution power analysis with the minimum-resolvable-separation output,
  fitted-model files, append-only rulings, certificates, the artifact-only CI gate,
  the planted-truth synthetic harness, 31 spec rulings, and the three mechanical gates.
- CLI: `fit`, `score`, `certify`, `gate`, `corpus`, `synth`, `census`, `spec`, `env`,
  `cite`.
