# Route availability, observed 2026-08-05

A dated record of which routes were purchasable when Angle C was being planned. It is
written down because the observation is perishable: a catalogue listing cannot be
recovered later, and one of the four routes this project's committed corpus was
collected from has already gone.

Source: one call each to the providers' free models endpoints
(`validation/angle_c/check_credentials.py`), no tokens billed.

## The committed June 2026 corpus, five weeks later

The reference corpus was collected 2026-06-27/28 through DeepInfra. Checked against
DeepInfra's catalogue on 2026-08-05:

| route as collected in June | still served on 2026-08-05 |
|---|---|
| `deepseek-ai/DeepSeek-V4-Flash` | yes |
| `meta-llama/Llama-3.3-70B-Instruct-Turbo` | yes |
| `meta-llama/Meta-Llama-3.1-8B-Instruct` | **no** |
| `mistralai/Mistral-Small-3.2-24B-Instruct-2506` | yes |

`meta-llama/Meta-Llama-3.1-8B-Instruct` is absent from the catalogue. The only
Llama-3.1-8B route DeepInfra now lists is `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo`,
the FP8 variant, under a different slug.

## Why this is recorded rather than worked around silently

One quarter of the routes behind this project's own measurements became unpurchasable
within five weeks of collection, and nothing announced it. The measurement cannot be
repeated forward against that route: what remains is the archive. That is the situation
this instrument was built for, and it arrived inside the study's own operating window
rather than as a hypothetical.

Two limits on how far this observation can be pushed:

- A catalogue listing is not the same as a served configuration. This records that the
  slug is no longer offered, not what happened to the weights behind it, and not whether
  anything changed for callers before it disappeared.
- One route over five weeks at one provider is an anecdote about a schedule, not a rate.
  Nothing here supports a claim about how often hosted routes disappear in general.

## Consequence for the Angle C plan

The different-weights control the power gate requires (DESIGN.md route 3, a same-family
size pair collected in-window) cannot use the June 8B slug, because it cannot be bought.
It uses `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo` instead, paired against
`meta-llama/Llama-3.3-70B-Instruct-Turbo`. Both are FP8 and both are collected inside the
Angle C window, which is what the control requires: different weights, same window.

This changes nothing about the load-bearing pair, whose slug
(`meta-llama/Llama-3.3-70B-Instruct-Turbo`) is served by both DeepInfra and Together and
was verified present in both catalogues on the same day.

The 8B route is therefore no longer a re-collection of a committed route. Any comparison
between the new 8B-Turbo archive and the June 8B archive would confound the window with a
declared precision change, so the study does not make one.

## Provider access note

Together sits behind Cloudflare, which rejects the default `Python-urllib` User-Agent
with error 1010 and a 403 that reads like an authentication failure. Requests to Together
must send a User-Agent. DeepInfra does not require this.
