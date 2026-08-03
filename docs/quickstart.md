# Quickstart

## Install

```sh
pip install punchmark
```

Python >= 3.12, zero runtime dependencies. No network access at runtime: every
verb reads local files you name and writes where you say.

## The synthetic roundtrip

Everything below runs on planted-truth archives generated locally. No model is
called and nothing is downloaded.

```sh
# 1. three invented routes: one archive + window sidecar per route
punchmark synth --out demo --routes 3

# 2. fit and calibrate a detector over the labelled archives
punchmark fit demo/synthtask__synth-route-a.jsonl.gz \
              demo/synthtask__synth-route-b.jsonl.gz \
              demo/synthtask__synth-route-c.jsonl.gz \
    --candidates synth/route-a,synth/route-b,synth/route-c \
    --out model.pmk-model.json

# 3. rule one archive at a declared operating point; the ruling is appended to
#    punchmark-rulings.jsonl and its id printed
punchmark score demo/synthtask__synth-route-a.jsonl.gz \
    --model model.pmk-model.json --far 0.01

# 4. the one-line certificate for that ruling
#    (exit 0 HOLDS / 1 DOES NOT HOLD / 2 UNDETERMINED)
punchmark certify --ruling pmk-r-<id printed by score>

# 5. the CI gate: freeze the operating point once, then fail any silent move
punchmark gate model.pmk-model.json --baseline baseline.json --write-baseline
punchmark gate model.pmk-model.json --baseline baseline.json
```

`fit` prints the calibrated operating points, the miss-rate-versus-false-alarm
curve, and rho\*, the minimum substituted fraction each ordered candidate pair
could have resolved at this k and item count.

## Bring your own archives

punchmark reads gzipped-JSONL response archives plus one sidecar per archive.
Two facts are never inferred from content: the producer label and the
collection window.

The producer label is the filename. Archives are named
`<task>__<route-slug>.jsonl.gz`, where the slug is the route name with `/`
replaced by `-` (route `vendor/model-x` -> `mytask__vendor-model-x.jsonl.gz`).
You fixed it at collection time, and nothing in the rows can change it. The row
schemas are specified in [Archives](archives.md), and
`punchmark census archive.jsonl.gz` describes what an archive holds (rows,
stubs, clusters, modal k, sha256).

The collection window is a sidecar you write, at
`<archive-filename>.window.json`, schema `window/v1`:

```json
{
  "punchmark_schema": "window/v1",
  "archive": "mytask__vendor-model-x.jsonl.gz",
  "archive_sha256": "<sha256 of the gzipped bytes, as punchmark census prints>",
  "route": "vendor/model-x",
  "task": "mytask",
  "window": {
    "start_utc": "2026-05-01T00:00:00+00:00",
    "end_utc": "2026-05-08T00:00:00+00:00"
  },
  "collector": {},
  "declared_by": "caller"
}
```

Timestamps must carry an explicit timezone. The sidecar's route must slug-match
the filename, and its `archive_sha256` must match the bytes on disk. Window
metadata therefore cannot be quietly re-pointed at different data. Running
`fit`, `score` or `certify` without a sidecar refuses, and the refusal prints
the exact JSON to write, pre-filled with the archive's real hash.
