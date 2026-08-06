# Superseded: refactor_dev collected at fan-out width 75

Three complete `refactor_dev` archives, 75 rows each, k=8, collected 2026-08-06 at
network fan-out width 75. They were replaced rather than used, and are kept because the
reason they were replaced is a measurement in its own right.

## What is here

| archive | provider | 429s during collection |
|---|---|---|
| `refactor_dev__meta-llama-Llama-3.3-70B-Instruct-Turbo` | deepinfra | 0 |
| `refactor_dev__meta-llama-Meta-Llama-3.1-8B-Instruct-Turbo` | deepinfra | 0 |
| `refactor_dev__meta-llama-Llama-3.3-70B-Instruct-Turbo` | together | **185** |

Each carries its original `window/v1` sidecar, so the recorded width and rejection count
travel with the data.

## Why they were replaced

The collection matches June's per-task fan-out width, for the reasons set out in
`../DESIGN.md`. June collected `refactor` at 128; the probe is 75 items, so the pool
capped at 75, and all three routes were requested at that width.

DeepInfra served 1,200 calls across two routes at width 75 without shedding a single
request. Together shed 185 of the 785 POSTs needed to complete its 600 calls, 23.6%.

That breaks the specific symmetry the width matching exists to protect. The load-bearing
comparison is the same slug at two providers, so the two sides have to be collected under
the same conditions. Requesting the same width achieved that for *offered* load and not
for *accepted* load: at any moment, fewer of the Together requests were actually in the
server's batch than the DeepInfra ones. Provider and shed-rate were confounded on this
task, and the confound is on the side of the comparison the study is about.

`comprehend` was unaffected: width 48 on both providers, zero rejections on either.

## What replaced them

All three `refactor_dev` archives were re-collected at width 48, the width Together had
already demonstrated it sustains without shedding. This also makes the whole Angle C
collection uniform at width 48 across every route and both tasks, so there is one width
to declare rather than one per task.

The trade is explicit: the replacement matches the other side of the pair, and it no
longer matches June's 128 for this task. Between the two, matching the pair wins. The
pair is the comparison being made; the June width matters only for the secondary
DeepInfra drift arm, which already could not reach 128 because the probe has 75 items.

## What this does not claim

That the width-75 archives are wrong, or that shedding changed the text. Nothing here
compares these archives against their replacements, and no such comparison appears in the
study. They were replaced because a condition that differed between the two providers
should not have been left in the collection, not because a difference in the data was
observed.

A limit that survives the fix and is declared rather than solved: matching width controls
only this study's own offered load. Both providers serve other customers whose traffic
shares the same server batches and is invisible from outside, so server-side batch
composition was never controllable at any width.
