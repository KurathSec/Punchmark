# Architecture

This document is authoritative over every other prose file, and the code is
authoritative over this document. When they disagree, fix whichever is wrong. Do not
paper over the disagreement.

## 1. What punchmark computes

In short: punchmark starts from response archives whose producing route was fixed by
the collector (the archive filename) and whose collection window the caller declares
(the sidecar). It fits a text-only producer identifier over a closed candidate set,
calibrates a false-substitution-alarm rate on same-route within-window resamples, and
measures power on seeded substitutions. It then rules any archive SAME-PRODUCER /
SUBSTITUTED / UNDETERMINED at a declared operating point, emitting an immutable ruling
and a one-line certificate.

The pipeline, in types (`model.py`):

```
archive.py + sidecar.py     ->  ResponseSet          (rows + label + window)
detector.py (DetectorModel) ->  FittedModel          (per-row, per-candidate scores)
calibrate.py                ->  OperatingPoint[]     (cross-fitted null quantiles)
power.py                    ->  PowerPoint[] + curve (seeded splices, rho*)
modelfile.py                ->  model/v1 file        (everything a bare install needs)
score.py                    ->  Ruling               (three-zone verdict)
rulings.py                  ->  append-only store
certify.py                  ->  Certificate          (one line + certificate/v1)
gate.py                     ->  exit 0/1/2           (artifact-only CI policy)
```

The set statistic is `T(S; r0) = mean_i l_i(r0) - max_{r != r0} mean_i l_i(r)`: the mean
per-row evidence for the declared route minus the best alternative. SUBSTITUTED fires
when T falls below the calibrated null quantile at the declared false-alarm rate.
SAME-PRODUCER additionally requires the power table to support the caller's rho_target
(PMK-RUL-001). Everything else is UNDETERMINED with recorded reasons.

## 2. Layering

```
errors < canonical < model < {archive, sidecar, synth | views < features < detector}
                                   < calibrate < power < modelfile < rulings < score
                                   < {certify, corpus} < gate* < cli
```

Rules, enforced by `tests/test_layering.py` (AST) and ruff TID253:

- No module imports the benchmark checkout's packages (`src`, `bench`, `eval`) or the
  numeric stack (`numpy`, `scipy`, `sklearn`, `pandas`), whether at module level or
  lazily. There is no adapter and no sanctioned import site: punchmark reads files.
- Nothing imports `cli`.
- Readers (`archive`, `sidecar`, `synth`) never import the analysis stack. The detector
  never imports a reader: it works on `ResponseSet`s and never sees a path. The
  featurizer receives completion strings only, and whole rows never reach it
  (PMK-FEA-001).
- `gate`* consumes serialized artifacts only. It never reads an archive and never
  refits anything.
- `archive.py` and `sidecar.py` are write-free.

## 3. Artifact formats

Every schema is versioned and serialized through `canonical.py` (PMK-EMIT-001). The
ones with an id prefix carry a content address computed with the id field removed
(PMK-EMIT-002). `window/v1` is caller-written and binds by the archive hash it pins.
`gate-baseline/v1` is a derived projection of a model file and needs no id of its own:

| schema | file | id prefix |
|---|---|---|
| `model/v1` | `<name>.pmk-model.json` | `pmk-m-` |
| `window/v1` | `<archive>.window.json` (caller-written) | -- |
| `ruling/v1` | one line of the append-only JSONL store | `pmk-r-` |
| `certificate/v1` | `certify` output | `pmk-c-` |
| `corpus/v1` | `calibration/*/MANIFEST.json` | `pmk-cor-` |
| `gate-baseline/v1` | `goldens/operating_point.json` | -- |

An unknown schema or a failed self-hash produces a typed refusal. There is no partial
read, and a KeyError must not masquerade as a verdict.

## 4. Rulings discipline

A ruling id pins the contractual four (detector version, candidate set, operating
point, calibration corpus hash) plus the archive hash, window and spec version
(PMK-RUL-004). The store is append-only, and every read re-verifies every line's hash
and the supersedes chain (PMK-RUL-003). Design decisions are spec rulings
(`src/punchmark/spec/rulings/*.toml`, ids `PMK-XXX-NNN`), cited from code and pinned by
tests. To change a ruling, supersede it. Editing an existing ruling is not allowed.

## 5. Determinism

Identical inputs give identical bytes. Floats are rounded and normalized before
serialization, and gzip is written with mtime=0. Every random stream is seeded by
`derive_seed(...)` from labelled parts (PMK-EMIT-003). The clock and `hash()` are never
used as seeds. `tests/test_determinism.py` runs the pipeline in two processes under two
`PYTHONHASHSEED`s and byte-compares the model files.

## 6. Calibration discipline

- The cluster unit is the base sample name. Clusters move whole in every subsample,
  split and splice (PMK-CAL-001).
- The null is cross-fitted 2-fold by cluster (PMK-CAL-005). The shipped model is fitted
  on everything, so its thresholds are slightly conservative, and that conservatism is
  declared.
- Null material is same-route, same-window only (PMK-CAL-003). Cross-window comparisons
  are diagnostics with no verdict semantics.
- Thresholds are conservative empirical quantiles with conservative set-size lookup
  (PMK-CAL-004). Below the calibrated floor the result is UNDETERMINED, because
  thresholds are never extrapolated.
- Seeded substitutions splice score-table rows as whole clusters, matched by item key
  (PMK-POW-001). rho = 0 must reproduce the null (PMK-POW-002). The minimum resolvable
  substituted fraction rho* is an output in its own right (PMK-POW-003), and seeded
  fidelity is a standing bound (PMK-POW-004).

## 7. The three mechanical gates

1. **Operating-point drift** (`tests/test_operating_point_drift.py` +
   `tools/update_calibration.py`): the committed calibration regenerates its committed
   goldens byte-for-byte. Goldens move only with `--write --confirm-spec-bump` after a
   real detector-version or spec-MAJOR change. Downstream, `punchmark gate` enforces the
   same policy on any model file against any baseline (PMK-GTE-003).
2. **Spec coverage** (`tests/test_spec.py`): every active ruling is cited from code,
   tests or docs, and every ruling-shaped id resolves.
3. **Layering** (`tests/test_layering.py`): section 2, mechanically.

CI never touches the upstream benchmark checkout. Every fixture is planted-truth
synthetic (`synth.py`) and small enough to check on paper.
