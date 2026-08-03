# The native archive shape

punchmark reads exactly one input format: gzipped JSONL named
`<task>__<route-slug>.jsonl.gz`, one row per item. Anything else is a typed
refusal naming the file and line, never a KeyError downstream.

## The filename is the producer label

The route slug in the filename was fixed by the experimenter at collection time
and is independent of any text the detector sees; nothing in punchmark ever
derives identity from row content (PMK-ARC-001). The slug is the route name with
`/` replaced by `-`. A slug alone cannot say which dash was a `/`, so resolution
runs only in one direction: the candidate set you declare at `fit` time maps its
own routes to slugs, and the filename must match one of them.

## Rows

Two row schemas plus one tolerated stub:

| shape | keys | handling |
|---|---|---|
| full row | `sample, variant, profile, language, intrinsic, tier, raw_outputs` | featurized |
| row without `tier` | the same minus `tier` | featurized; the native corpus ships both shapes (PMK-ARC-003) |
| API error stub | exactly `sample, profile, language` | counted and surfaced, never featurized (PMK-ARC-002) |
| anything else | -- | typed refusal naming the line |

A full row:

```json
{"sample": "s017", "variant": "v2", "profile": "default", "language": "python",
 "intrinsic": {"loc": 41, "depth": 3}, "tier": "hard",
 "raw_outputs": ["...draw 1...", "...draw 2...", "...draw 3...", "...draw 4..."]}
```

- `raw_outputs` is a non-empty list of strings: the k response draws, text only.
- `intrinsic` is a string-to-integer object.
- Item identity is `(sample, variant, profile, language)` and must be unique;
  a duplicate is a refusal.
- A stub records that collection failed for an item: it occupies the item slot,
  carries zero draws, and is reported by `census` and every ruling
  (`stubs=...`). A ruling goes `UNDETERMINED` when the stub share exceeds
  `--stub-cap`.
- Ragged draw counts (a row whose k differs from the archive's modal k) are
  tolerated and counted -- they are a serving event -- never silently padded or
  dropped.

## The window sidecar

Each archive is accompanied by `<archive-filename>.window.json`, schema
`window/v1`; the exact shape is shown in the [Quickstart](quickstart.md). Three
binding rules, each a spec ruling:

1. **The window is declared, never inferred** (PMK-SDC-001). punchmark never
   reads time out of content, filenames or mtimes. Without a sidecar there is no
   (route, window) unit, so `fit`, `score` and `certify` refuse -- and the
   refusal prints the exact JSON to write.
2. **The sidecar must agree with the filename** (PMK-SDC-002). Its `route` must
   slug-match the archive filename and its `task` must equal the filename task.
   The filename is the oracle: a sidecar may resolve a slug to a route name, but
   never contradict it.
3. **The sidecar binds to the bytes** (PMK-SDC-003). It pins the sha256 of the
   archive it describes and is refused against any other bytes, so window
   metadata cannot be quietly re-pointed at different data.

## What is deliberately not read

No logprobs, no HTTP headers, no timing. The row type has no fields for them, so
the text-only input restriction is enforced by construction rather than by
policy (PMK-ARC-004). This is what makes the tool retrospective: it asks nothing
of an archive that an ordinary evaluation run would not already have saved.
