# Angle C design (v2, post-review): adversarial purchased routes

Status: DESIGN ONLY. No API call has been issued. This version incorporates a 22-finding
adversarial review of v1. Collection is gated on (1) the open decisions at the end being
settled by the maintainer and (2) an explicit spend authorization with a stated ceiling.
Nothing here authorizes spending.

## The question Angle C answers

Angle A's four committed routes are four families at four scales, so separating them is
easy in a way real substitution is not. Angle C buys a small adversarial route set to ask
one question the committed corpus cannot:

**Does the fingerprint identify the producing weights, or the serving stack?**

The review established that this question is only answerable if three confounds are
removed by construction: the collection window, the serving precision, and the
identification protocol. v1 controlled none of them. v2 does.

## Pre-registration (write before --execute; the decision rule is fixed before data)

The verdict is decided by a rule fixed in advance, so a fired direction cannot be chosen
after seeing the numbers.

- **Statistics** (all mirroring Angle A's forms, computed by a reused Angle-A-style
  driver): for each ordered route pair at set size m and false-alarm rate FAR, the
  T-statistic, the clustered-subsample identification rate with its cluster-bootstrap CI
  lower bound, and the minimum resolvable separation rho*.
- **The load-bearing comparison**: the same-weights-two-providers pair (both collected
  in-window; see collection) vs a within-window different-weights control pair.
- **Decision rule**: the detector is reported as a **serving-stack identifier** if the
  same-weights pair separates (identification CI lower bound above chance AND a
  SUBSTITUTED-direction T) at an effect within a pre-named band of the different-weights
  control pair's effect. It is reported as a **weights identifier** if the same-weights
  pair does not separate while the control does. Any other outcome is reported as
  **inconclusive**, with the numbers.
- **Power gate**: the same-weights null is verdict-bearing only if the within-window
  different-weights control pair resolves (its rho* at the same m and FAR is below a
  stated bound). If the control does not resolve at this m, the whole contrast is
  **underpowered** and reported as a power limit, not a verdict. This defends against an
  n=1-pair null being read as evidence.
- **Precision-conditioning**: the serving-stack verdict is available only if both sides of
  the same-weights pair have provider-declared precision/quantization recorded and equal
  (see fidelity). If precision parity cannot be established, the verdict is demoted to
  "consistent with either a serving-stack signature or an undisclosed precision
  difference", and the quantized-vs-full pair (below) is the measured yardstick for how
  large a pure precision difference looks.

## Candidate routes (adversarial, window-matched)

Exact slugs and providers are pinned at purchase and recorded with access dates
(purchasability decay is the recorded project risk). Every route below is collected
INSIDE the Angle C window; none reuses a June-committed archive as a live comparison arm.

1. **Same weights, two providers (load-bearing).** One open-weight model id served by two
   different hosted providers, BOTH purchased in-window: `deepinfra-new` and
   `providerB-new`. Provider B must publicly disclose serving precision and must not
   dynamically route; its disclosed precision must match DeepInfra's for the pair to carry
   the "same weights" label.
2. **Time-drift control (decomposes window from provider).** Re-purchase the same slug on
   DeepInfra in-window (`deepinfra-new`) and score it against the June-committed DeepInfra
   archive of that slug. This is same-weights, same-provider, cross-window: it measures
   what five weeks of drift alone looks like, so the load-bearing pair's separation can be
   read against it.
3. **Same family, two sizes.** One more same-family size pair beyond the committed
   Llama-3.1-8B / Llama-3.3-70B, if available.
4. **Quantized vs full (precision yardstick).** The same slug at two quantization levels
   from one provider that exposes the choice. This is the measured effect size of a pure
   precision difference, used to condition the load-bearing verdict.
5. **A near-twin (a genuinely hard pair).** Two instruct tunes of one base.

Open-weight routes only; closed commercial routes never enter any corpus (PMK-COR-002).

## Two-model evaluation protocol (the shipped goldens are never touched)

The review established that "identification against an expanded candidate set at the
shipped operating point" is mechanically impossible and internally contradictory. v2
splits evaluation into two explicitly separate models:

- **Shipped model (verification only).** `calibration/spaghetti/goldens/default.pmk-model.json`,
  unchanged. Used ONLY for routes whose slug is in its 4-route candidate set: the
  same-weights pair's DeepInfra side, and the time-drift control. Produces T-statistics
  and SAME-PRODUCER/SUBSTITUTED verdicts at the shipped FAR via `--task-as`. Its
  candidate_set_id and operating points are never changed; the drift gate stays green.
- **Angle-C side model (identification only).** A SEPARATE detector with its own
  `model_id` and `candidate_set_id`, fit on the committed dev archives PLUS the purchased
  archives, stored under `validation/angle_c/` and NEVER under `calibration/`. It is used
  for whole-set identification against the expanded route set. Fitting uses a declared
  cluster-respecting split of each purchased archive (fit half, score the disjoint half;
  seeds pre-declared), and per-route fit sizes are matched so a 150-row route is not
  scored against a 1500-row profile. This model is described in the writeup as a separate,
  non-shipped detector, never as "the shipped operating point".

Identification (threshold-free argmax) and verification (a statistic vs a FAR) are
reported as distinct quantities and never conflated.

## Collection protocol (replay fidelity + response-side evidence)

- **Prompts**: the frozen 150-row probe subset from `validation/angle_a/derived/probe_manifest.json`
  (75 comprehend + 75 refactor, dev-only), rebuilt via `bench.dataset.load("dev")` (public
  seed 20260619, annotated condition, paraphrase variant 0).
- **Send-side fidelity gate (runs inside --execute, per route, before spending on it)**:
  `bench.models.prompt_hash(system, user)` must reproduce the stored `prompt_hash` for the
  probe items, and `bench.prompts.prompt_set_hash()` must equal `36b8ffef1f3f7c79`. Abort
  the route on mismatch.
- **Request shape**: one POST per draw, k=8 sequential identical requests per item,
  temperature 0, max_tokens 2048, two messages (system + user), no seed/n/stop/logprobs.
  Provider endpoint and key per route.
- **Response-side evidence (new; the strict archive row cannot hold it)**: a per-item
  collection log JSONL beside each archive records item_key, prompt_hash, the
  provider-returned model string, finish_reason per draw, usage tokens, and whether text
  came from `content` vs a `reasoning_content` channel. Per-route summaries record the
  snapshot-id set, truncation rate, and empty-completion rate.
- **Per-draw validation**: each completion must be non-empty and non-whitespace. Empty or
  reasoning-only completions are counted; a route is aborted before further spend if the
  empty/short rate exceeds a declared bound. A failed draw is retried to reach k=8; if it
  cannot, the row is recorded with its true short k (never padded), and the ragged count
  is logged.
- **Output**: native `<task>__<slug>.jsonl.gz` archives, per-provider output directories so
  the same slug at two providers never collides, plus a `window/v1` sidecar per archive
  carrying the real collection window AND a `collector` block recording provider,
  provider-declared precision/quantization, model revision, and endpoint. Route labels for
  the side model are provider-disambiguated.

## Spend controls (hard; enforced in the script, not the plan)

- **Dry-run default.** Default mode builds prompts, runs the send-side fidelity gate,
  prints the per-route plan and projected cost, and issues ZERO calls. Real collection
  requires `--execute` AND `--max-usd <ceiling>` with no default ceiling (so `--execute`
  alone can never authorize a spend the operator did not state).
- **Pinned price table required.** Every purchased route must have a pinned price entry
  (USD per Mtok, or per-1k with estimated tokens/call) or `--execute` refuses that route,
  mirroring the upstream harness's "no price for model" refusal. A response missing its
  usage block is treated as the pinned estimate, never as $0.
- **Per-route pre-flight.** Before the first POST of a route, project its cost
  (1,200 calls x pinned price x estimated tokens) and refuse the route if
  running-total + projection would exceed `--max-usd`.
- **Live counter.** A running count of issued POSTs (retries included) aborts if it would
  exceed a declared call ceiling.
- **Per-item resumability.** Each item's row is written as it completes (temp-file +
  rename); resume skips (item, draw) pairs already present, so an abort at item 149 never
  forces a full-route re-buy. An existing 150-row archive for a route is treated as done.
- **Billing visibility.** On `--execute` the script prints which key source, account
  hint, provider, and endpoint each route will bill, and requires confirmation, so the
  operator sees what is charged before any call.

## Storage and disclosure (PMK-COR-002 not re-opened)

- Raw purchased archives go to a gitignored, local-only directory
  (`validation/angle_c/archives/`, added to `.gitignore`, same treatment as `/paper/`).
  No completion text is committed.
- Committed to the repo: a sha256-per-file manifest of the purchased archives (mirroring
  the calibration manifest), the pinned route/provider/price/precision table, the derived
  numbers under `validation/angle_c/derived/`, and the finding. The side model's file is
  committed (it is parameters, not completions) under `validation/angle_c/`, never under
  `calibration/`.

## Scoped constraint exceptions (documented)

- The collection script under `validation/angle_c/` imports `bench.*` to rebuild prompts.
  This is a scoped, documented exception to the "never import the upstream checkout"
  rule, which remains enforced in `src/punchmark` by TID253. The script runs with
  bytecode writing disabled so it never writes `.pyc` into the read-only checkout, and the
  read-only invariant is checked with `git -C /home/kureist/Spaghetti-Architect status
  --porcelain` before and after.

## What Angle C does NOT do

It does not recalibrate or move the shipped operating point or the drift-gate goldens. It
does not add closed commercial routes to any corpus. It does not commit purchased
completion text. It does not claim a substitution incidence rate for hosted evaluation
generally. Its verdict is conditional on the pre-registered decision rule, the power gate,
and precision attestation, and a single unresolved pair yields "underpowered", not a
verdict.

## Open decisions for the maintainer (required before --execute)

These are genuinely external or budgetary and cannot be settled from the repo:

1. **Provider B for the same-weights pair.** Which second host serves an open-weight slug
   that DeepInfra also serves, discloses its serving precision, and does not dynamically
   route? The whole load-bearing contrast depends on this existing; if no
   precision-disclosing match is purchasable, Angle C narrows to the family-size and
   quantized-vs-full pairs and the serving-stack question stays open (a reportable null).
2. **Credentials and billing.** Which key and account should each provider bill? The
   DeepInfra key currently in `bench/config.json` is plaintext and its account should be
   confirmed (and rotated if it was ever exposed); other providers need their own keys.
3. **The spend ceiling** (`--max-usd`) and the call ceiling.
4. **The exact route/slug list** at purchase time, with precisions, pinned prices, and
   access dates recorded in the route table.
