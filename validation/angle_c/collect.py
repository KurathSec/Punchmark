#!/usr/bin/env python3
"""Angle C collection: buy the frozen 150-row probe from the pinned routes.

Defaults to a DRY RUN that issues zero calls. Real collection needs both
``--execute`` and ``--max-usd <ceiling>``; the ceiling has no default, so
``--execute`` on its own can never authorize a spend the operator did not state.

What it does, in order:
  1. loads the gitignored credentials and prints which account each route bills;
  2. rebuilds the 150 probe prompts from the public dev seed and verifies them
     against the committed corpus (prompt_set_hash, plus per-item prompt_hash
     spot checks). A prompt mismatch aborts before any spend, because a replay
     whose prompts differ measures the prompt change, not the producer;
  3. projects each route's cost from measured prompt sizes and the observed
     output lengths of the committed June archives for the same items, refusing
     a route before its first POST if the running total would breach the ceiling;
  4. with --execute, issues k=8 sequential identical requests per item exactly as
     the original collection did (temperature 0, max_tokens 2048, two messages,
     no seed/n/stop/logprobs), fanning out across items at the same width June
     used for that task (see JUNE_CONCURRENCY), writing each row as it completes
     so an abort never forces a re-buy;
  5. writes native ``<task>__<slug>.jsonl.gz`` archives under a per-provider
     directory, a window/v1 sidecar recording the real collection window and the
     provider-declared precision, and a per-item response log carrying the
     returned model string, finish reasons and usage.

The bench import below is the scoped exception documented in DESIGN.md: the
prompts must be rebuilt by the same code that built them in June. Bytecode
writing is disabled so nothing is written into the read-only checkout.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from punchmark.canonical import canonical_json, sha256_file, write_text_deterministic  # noqa: E402

PROBE = ROOT / "validation" / "angle_a" / "derived" / "probe_manifest.json"
CRED = HERE / "credentials.json"
ARCHIVES = HERE / "archives"
USER_AGENT = "punchmark/0.1 (+https://github.com/KurathSec/Punchmark)"
PROMPT_SET_HASH = "36b8ffef1f3f7c79"
K_DRAWS = 8
TEMPERATURE = 0.0
MAX_TOKENS = 2048
TIMEOUT_S = 120
MAX_ATTEMPTS = 5
RETRY_BASE_S = 2.0
RETRYABLE = frozenset({429, 500, 502, 503, 504})

# Network fan-out width, per task, read off the June run_meta sidecars of the committed
# archives (`net_concurrency`): comprehend was collected at 48 and refactor at 128, on
# every route, in both the dev and test splits. This replay matches those widths rather
# than picking a convenient number.
#
# Width is a fidelity parameter here, not a speed knob. Hosted serving stacks batch
# concurrent requests continuously, so the width changes which requests share a batch,
# which changes floating-point reduction order, which at temperature 0 can flip a token
# at a near-tie. That is the same layer of the stack this instrument reads text for, so
# a replay collected at a different width than the archive it is compared against would
# confound the collection method with the producer. Two consequences the code enforces:
# both providers use the SAME width for a given task, so provider is not confounded with
# batching on the load-bearing pair; and the width used is written into every window
# sidecar next to June's, so the record shows whether they agreed.
JUNE_CONCURRENCY = {"comprehend": 48, "refactor_dev": 128}

# Pinned prices, USD per million tokens, deliberately rounded UP so a projection
# never under-states. A route without an entry here is refused (DESIGN.md).
PRICES = {
    ("deepinfra", "meta-llama/Llama-3.3-70B-Instruct-Turbo"): 0.60,
    ("deepinfra", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"): 0.10,
    ("together", "meta-llama/Llama-3.3-70B-Instruct-Turbo"): 1.20,
}

# The core purchase: the load-bearing same-weights pair plus the different-weights
# control the power gate requires. Pinned 2026-08-05, see ROUTE_AVAILABILITY.md.
ROUTES = [
    {
        "key": "deepinfra-llama70b",
        "provider": "deepinfra",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "precision": "FP8 (provider-declared, -Turbo tier)",
        "role": "load-bearing pair, DeepInfra side; also the time-drift control "
                "against the committed June archive of this slug",
    },
    {
        "key": "together-llama70b",
        "provider": "together",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "precision": "FP8 (provider-declared, -Turbo tier)",
        "role": "load-bearing pair, Together side: same slug, same declared precision",
    },
    {
        "key": "deepinfra-llama8b",
        "provider": "deepinfra",
        "model": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        "precision": "FP8 (provider-declared, -Turbo tier)",
        "role": "different-weights control for the power gate, paired in-window "
                "against the 70B above",
    },
]

# task name in the probe manifest -> (bench prompt builder, committed archive dir)
TASKS = {"comprehend": ("comprehend", "ladder"), "refactor_dev": ("refactor", "g3")}


def load_credentials() -> dict:
    cred = json.loads(CRED.read_text(encoding="utf-8"))["providers"]
    out = {}
    for name, spec in cred.items():
        env = spec.get("api_key_env", "")
        key = os.environ.get(env, "") if env else ""
        if not key:
            key = spec.get("api_key", "") or ""
        if key.startswith("PASTE_YOUR_"):
            key = ""
        out[name] = {
            "key": key,
            "base_url": spec["base_url"],
            "account_hint": spec.get("account_hint") or "(not stated)",
        }
    return out


def build_prompts(source: Path) -> dict[tuple[str, str], tuple[str, str]]:
    """(task, item_key) -> (system, user), rebuilt by the corpus's own code."""
    sys.path.insert(0, str(source))
    cwd = Path.cwd()
    os.chdir(source)
    try:
        import bench.dataset as D
        import bench.models as M
        import bench.prompts as P
        import bench.tasks as T
        from src.nodes.validator import oracle

        actual = P.prompt_set_hash()
        if actual != PROMPT_SET_HASH:
            raise SystemExit(
                f"prompt-set hash mismatch: {actual} != {PROMPT_SET_HASH}. The prompt "
                "templates have changed, so a replay would measure the prompt change "
                "rather than the producer. Refusing before any spend."
            )
        manifest = json.loads(PROBE.read_text(encoding="utf-8"))["items"]
        split = D.load("dev")
        prompts: dict[tuple[str, str], tuple[str, str]] = {}
        for task, keys in manifest.items():
            builder = TASKS[task][0]
            for key in keys:
                sample, variant, profile, language = key.split("|")
                stem = T._stem_for(split, sample, variant)
                src = T._sources(split.ir(stem), profile)[language]
                rvars = list(oracle(split.program(stem)))
                if builder == "comprehend":
                    system, user = P.comprehend(language, src, rvars, 0)
                else:
                    system, user = P.refactor(language, src, rvars, 0)
                prompts[(task, key)] = (system, user)
        return prompts, M.prompt_hash
    finally:
        os.chdir(cwd)


def verify_against_committed(
    prompts: dict, prompt_hash, source: Path, n_check: int = 8
) -> int:
    """Spot-check rebuilt prompts against prompt_hash values recorded in June."""
    checked = 0
    for task, (_name, _subdir) in TASKS.items():
        finalize = source / "bench" / "out" / "subagent"
        name = "comprehend" if task == "comprehend" else "refactor"
        candidates = sorted(finalize.glob(f"{name}__*.json"))
        if not candidates:
            continue
        record = json.loads(candidates[0].read_text(encoding="utf-8"))
        by_key = {}
        for item in record.get("items", []):
            key = "|".join((item["sample"], item.get("variant", "base"),
                            item["profile"], item["language"]))
            if item.get("prompt_hash"):
                by_key[key] = item["prompt_hash"]
        for (t, key), (system, user) in prompts.items():
            if t != task or key not in by_key or checked >= n_check:
                continue
            got = prompt_hash(system, user)
            if got != by_key[key]:
                raise SystemExit(
                    f"prompt mismatch for {task} {key}: rebuilt {got} != recorded "
                    f"{by_key[key]}. Refusing before any spend."
                )
            checked += 1
    return checked


def observed_output_chars(source: Path) -> dict[str, float]:
    """Mean completion length per task, measured from the committed June archives
    for these same items. Grounds the cost projection in real data."""
    out = {}
    for task, (_, subdir) in TASKS.items():
        path = next(
            (source / "bench" / "out" / subdir).glob(f"{task}__*.jsonl.gz"), None
        )
        if path is None:
            out[task] = 2000.0
            continue
        total = n = 0
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                for text in rec.get("raw_outputs") or []:
                    total += len(text)
                    n += 1
                if n > 4000:
                    break
        out[task] = (total / n) if n else 2000.0
    return out


def project_route(route: dict, prompts: dict, out_chars: dict) -> dict:
    price = PRICES.get((route["provider"], route["model"]))
    if price is None:
        raise SystemExit(
            f"no pinned price for {route['provider']} {route['model']}; refusing "
            "(a route without a price cannot be projected against the ceiling)"
        )
    in_tok = out_tok = 0
    for (task, _key), (system, user) in prompts.items():
        # ~3.5 chars per token is conservative for code-heavy prompts
        in_tok += (len(system) + len(user)) / 3.5 * K_DRAWS
        out_tok += min(out_chars[task] / 3.5, MAX_TOKENS) * K_DRAWS
    total_tok = in_tok + out_tok
    return {
        "calls": len(prompts) * K_DRAWS,
        "est_input_tokens": int(in_tok),
        "est_output_tokens": int(out_tok),
        "usd_per_mtok": price,
        "est_usd": round(total_tok / 1_000_000 * price, 2),
    }


class CollectError(RuntimeError):
    """A route-fatal collection error.

    Raised inside a worker thread, where SystemExit would only kill that thread and
    leave the pool spending. The route loop catches it, stops the remaining workers
    before they buy anything, and re-raises once the in-flight calls have drained.
    """


def post(url: str, key: str, payload: dict, counter: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(MAX_ATTEMPTS):
        req = urllib.request.Request(
            url, data=body,
            headers={"content-type": "application/json",
                     "authorization": f"Bearer {key}", "user-agent": USER_AGENT},
        )
        try:
            with counter["lock"]:
                counter["posts"] += 1
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 429s are counted, not just retried: a run that only reached its width by
            # backing off did not really collect at that width, and the sidecar has to
            # be able to say so.
            if exc.code == 429:
                with counter["lock"]:
                    counter["http_429"] += 1
            if exc.code not in RETRYABLE or attempt == MAX_ATTEMPTS - 1:
                raise CollectError(
                    f"API HTTP {exc.code}: {exc.read().decode()[:300]}"
                ) from exc
            time.sleep(min(RETRY_BASE_S * 2**attempt, 60.0))
        except Exception:
            if attempt == MAX_ATTEMPTS - 1:
                raise
            time.sleep(min(RETRY_BASE_S * 2**attempt, 60.0))
    raise CollectError("unreachable")


def fetch_item(ctx: dict, key: str) -> None:
    """Buy one item's k draws and append its row. One of these per worker thread.

    Module-level and explicitly parameterized rather than a closure over the task
    loop, so the loop variables cannot be captured late (ruff B023).
    """
    state, counter = ctx["state"], ctx["counter"]
    # An earlier worker has already failed the route: return before spending.
    if state["abort"] is not None:
        return
    route, prov, task = ctx["route"], ctx["prov"], ctx["task"]
    system, user = ctx["prompts"][(task, key)]
    sample, variant, profile, language = key.split("|")
    draws: list[str] = []
    meta: list[dict] = []
    for _ in range(K_DRAWS):
        body = post(prov["base_url"], prov["key"], {
            "model": route["model"], "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }, counter)
        choice = (body.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        text = msg.get("content") or ""
        meta.append({
            "returned_model": body.get("model"),
            "finish_reason": choice.get("finish_reason"),
            "from_reasoning_channel": bool(msg.get("reasoning_content")) and not text,
            "usage": body.get("usage", {}),
        })
        u = body.get("usage") or {}
        with ctx["usage_lock"]:
            ctx["usage_total"]["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
            ctx["usage_total"]["completion_tokens"] += int(u.get("completion_tokens") or 0)
        draws.append(text)
    if not [d for d in draws if d.strip()]:
        raise CollectError(
            f"{route['key']} {task} {key}: all {K_DRAWS} draws empty; aborting "
            "this route before spending further"
        )
    row = {"sample": sample, "variant": variant, "profile": profile,
           "language": language, "intrinsic": {"n_ops": 0}, "tier": "A",
           "raw_outputs": draws}
    with ctx["write_lock"]:
        for path, rec in ((ctx["rows_path"], row),
                          (ctx["log_path"], {"item": key, "task": task, "draws": meta})):
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        state["n_done"] += 1
        n = state["n_done"]
    if n % 10 == 0:
        print(f"    {route['key']} {task}: {n}/{ctx['n_pending']} new items, "
              f"{counter['posts']} calls so far", flush=True)


def collect_route(route: dict, prompts: dict, cred: dict, counter: dict,
                  width_override: int | None = None) -> dict:
    prov = cred[route["provider"]]
    slug = route["model"].replace("/", "-")
    outdir = ARCHIVES / route["provider"]
    outdir.mkdir(parents=True, exist_ok=True)
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0}
    written = {}

    # Only the tasks still present in `prompts`; main() filters it for --tasks so a
    # partial re-collection never touches the archives it was not asked to.
    for task in [t for t in TASKS if any(pt == t for pt, _ in prompts)]:
        # Per task, because June used a different width per task and the window is
        # per task; a route-level start would misdate the second archive.
        width = width_override or JUNE_CONCURRENCY[task]
        started = datetime.now(UTC).isoformat()
        n429_at_start = counter["http_429"]
        rows_path = outdir / f"{task}__{slug}.rows.jsonl"
        log_path = outdir / f"{task}__{slug}.responses.jsonl"
        done = set()
        if rows_path.exists():
            for line in rows_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    done.add("|".join((rec["sample"], rec["variant"],
                                       rec["profile"], rec["language"])))
        pending = sorted(k for (t, k) in prompts if t == task and k not in done)
        # A pool cannot be wider than the work in it. The probe is 75 items per task,
        # so refactor_dev tops out at 75 against June's 128; and a resume with few
        # items left is narrower still. The realized width is what gets recorded.
        pool_width = min(width, len(pending)) if pending else 0
        state = {"abort": None, "n_done": 0}
        ctx = {
            "task": task, "route": route, "prov": prov, "prompts": prompts,
            "counter": counter, "usage_total": usage_total, "state": state,
            "usage_lock": threading.Lock(), "write_lock": threading.Lock(),
            "rows_path": rows_path, "log_path": log_path, "n_pending": len(pending),
        }
        if pending:
            print(f"    {route['key']} {task}: {len(pending)} items to buy "
                  f"({len(done)} already on disk), fan-out {pool_width} "
                  f"(requested {width}, June: {JUNE_CONCURRENCY[task]})", flush=True)
            with ThreadPoolExecutor(max_workers=pool_width) as ex:
                futures = [ex.submit(fetch_item, ctx, key) for key in pending]
                for fut in as_completed(futures):
                    try:
                        fut.result()
                    except Exception as exc:  # noqa: BLE001 -- recorded, re-raised below
                        # First failure wins and stops the queued workers; the ones
                        # already in flight finish and their rows are kept.
                        if state["abort"] is None:
                            state["abort"] = exc
            if state["abort"] is not None:
                raise state["abort"]

        rows = [json.loads(line) for line in
                rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows.sort(key=lambda r: (r["sample"], r["variant"], r["profile"], r["language"]))
        archive = outdir / f"{task}__{slug}.jsonl.gz"
        with gzip.GzipFile(filename="", fileobj=open(archive, "wb"), mode="wb", mtime=0) as gz:
            gz.write(("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n").encode())
        written[task] = archive
        sidecar = outdir / f"{archive.name}.window.json"
        # Regenerating the archive is idempotent (sorted rows, mtime 0), but the sidecar
        # is not: it records when this run collected and how wide it ran. A run that
        # bought nothing has neither, so rewriting one here would replace a true record
        # with a window of near-zero length and a width of 0.
        if not pending and sidecar.exists():
            print(f"    {archive.relative_to(ROOT)} already complete "
                  f"({len(rows)} rows); sidecar left as recorded")
            continue
        ended = datetime.now(UTC).isoformat()
        write_text_deterministic(sidecar, canonical_json({
            "punchmark_schema": "window/v1",
            "archive": archive.name,
            "archive_sha256": sha256_file(archive),
            "route": route["model"],
            "task": task,
            "window": {"start_utc": started, "end_utc": ended},
            "collector": {
                "provider": route["provider"],
                "declared_precision": route["precision"],
                "endpoint": prov["base_url"],
                "role": route["role"],
                "k": K_DRAWS, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
                # Fan-out width across items, and the width the June archive of this
                # task was collected at. Recorded because concurrency changes server
                # batch composition, which is a serving-side difference this
                # instrument can read; see JUNE_CONCURRENCY.
                "net_concurrency": pool_width,
                "net_concurrency_requested": width,
                "june_net_concurrency": JUNE_CONCURRENCY[task],
                "net_concurrency_note": (
                    "realized pool width this run; capped by the number of items bought "
                    "in it, so it is below the requested width whenever the task has "
                    "fewer pending items than workers"),
                # A resumed task was collected in more than one pass, so its width and
                # window describe only the last one. Recorded so that can be seen.
                "rows_pre_existing": len(done),
                "rows_bought_this_run": len(pending),
                "http_429": counter["http_429"] - n429_at_start,
                "probe": "validation/angle_a/derived/probe_manifest.json",
            },
            "declared_by": "validation/angle_c/collect.py",
        }))
        print(f"    wrote {archive.relative_to(ROOT)} ({len(rows)} rows)")
    return {"written": {k: str(v) for k, v in written.items()}, "usage": usage_total}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default="/home/kureist/Spaghetti-Architect")
    ap.add_argument("--execute", action="store_true",
                    help="actually issue paid calls; requires --max-usd")
    ap.add_argument("--max-usd", type=float, default=None,
                    help="hard spend ceiling in USD; no default, must be stated")
    ap.add_argument("--routes", default="", help="comma-separated route keys (default all)")
    ap.add_argument("--tasks", default="",
                    help="comma-separated task names (default all). Restricts both the "
                         "projection and the collection, so a re-collection of one task "
                         "cannot disturb the other task's archive or sidecar.")
    ap.add_argument("--concurrency", type=int, default=None,
                    help="override the network fan-out width for EVERY route and task "
                         f"(default: June's per-task widths, {JUNE_CONCURRENCY}). It is "
                         "deliberately not per-provider: the load-bearing pair must be "
                         "collected at one width or provider is confounded with batching.")
    args = ap.parse_args()
    if args.concurrency is not None and args.concurrency < 1:
        print("--concurrency must be >= 1", file=sys.stderr)
        return 2
    want_tasks = [t.strip() for t in args.tasks.split(",") if t.strip()] or list(TASKS)
    unknown = [t for t in want_tasks if t not in TASKS]
    if unknown:
        print(f"unknown task(s) {unknown}; known: {list(TASKS)}", file=sys.stderr)
        return 2
    source = Path(args.source)

    if args.execute and args.max_usd is None:
        print("--execute requires --max-usd <ceiling>; refusing", file=sys.stderr)
        return 2

    selected = [r for r in ROUTES
                if not args.routes or r["key"] in args.routes.split(",")]
    cred = load_credentials()
    print("=" * 72)
    print("ANGLE C COLLECTION" + ("" if args.execute else "  (DRY RUN, zero calls)"))
    print("=" * 72)

    print("\nbilling:")
    for r in selected:
        p = cred.get(r["provider"], {})
        if not p.get("key"):
            print(f"  {r['key']}: NO KEY for {r['provider']}; refusing")
            return 2
        print(f"  {r['key']:22s} {r['provider']:10s} bills {p['account_hint']}"
              f"  key {p['key'][:4]}...{p['key'][-4:]}")

    print("\nfidelity gate:")
    prompts, prompt_hash = build_prompts(source)
    print(f"  prompt_set_hash {PROMPT_SET_HASH} matches")
    n = verify_against_committed(prompts, prompt_hash, source)
    print(f"  {n} per-item prompt_hash spot checks match the June records")
    print(f"  {len(prompts)} probe prompts rebuilt "
          f"({sum(1 for t,_ in prompts if t=='comprehend')} comprehend, "
          f"{sum(1 for t,_ in prompts if t=='refactor_dev')} refactor_dev)")

    # Verify against the full committed set first, then narrow. Filtering earlier would
    # weaken the fidelity gate to whichever task happened to be selected.
    if want_tasks != list(TASKS):
        prompts = {(t, k): v for (t, k), v in prompts.items() if t in want_tasks}
        print(f"  restricted to {want_tasks}: {len(prompts)} prompts will be collected")

    print("\nfan-out width (matched to June per task, same for every provider):")
    for task in want_tasks:
        width = args.concurrency or JUNE_CONCURRENCY[task]
        n_items = sum(1 for t, _ in prompts if t == task)
        realized = min(width, n_items)
        if width != JUNE_CONCURRENCY[task]:
            note = f"OVERRIDDEN, June used {JUNE_CONCURRENCY[task]}"
        elif realized < width:
            note = f"June used {width}, capped to {realized} by the {n_items}-item probe"
        else:
            note = "matches June"
        print(f"  {task:14s} {realized:4d}  ({note})")

    out_chars = observed_output_chars(source)
    print("\nprojection (output length measured from the June archives):")
    total = 0.0
    plan = []
    for r in selected:
        proj = project_route(r, prompts, out_chars)
        plan.append((r, proj))
        total += proj["est_usd"]
        print(f"  {r['key']:22s} {proj['calls']:5d} calls  "
              f"~{(proj['est_input_tokens']+proj['est_output_tokens'])/1e6:.2f}M tok  "
              f"@ ${proj['usd_per_mtok']:.2f}/Mtok  ->  ~${proj['est_usd']:.2f}")
    print(f"  {'TOTAL':22s} {sum(p['calls'] for _, p in plan):5d} calls"
          f"{'':28s}  ->  ~${total:.2f}")
    if args.max_usd is not None:
        print(f"  ceiling ${args.max_usd:.2f}  ->  "
              f"{'WITHIN' if total <= args.max_usd else 'EXCEEDS, would refuse'}")

    if not args.execute:
        print("\nDry run only. No calls were issued and nothing was billed.")
        print("To collect:  --execute --max-usd <ceiling>")
        return 0

    if total > args.max_usd:
        print(f"\nprojected ${total:.2f} exceeds ceiling ${args.max_usd:.2f}; refusing")
        return 1

    counter = {"posts": 0, "http_429": 0, "lock": threading.Lock()}
    spent = 0.0
    print("\ncollecting:")
    for r, proj in plan:
        if spent + proj["est_usd"] > args.max_usd:
            print(f"  stopping before {r['key']}: would breach the ceiling")
            break
        print(f"  {r['key']} ({r['model']} via {r['provider']})")
        result = collect_route(r, prompts, cred, counter, args.concurrency)
        u = result["usage"]
        actual = (u["prompt_tokens"] + u["completion_tokens"]) / 1e6 * proj["usd_per_mtok"]
        spent += actual if actual else proj["est_usd"]
        print(f"    usage {u['prompt_tokens']}+{u['completion_tokens']} tok, "
              f"~${actual:.2f}; running total ~${spent:.2f} of ${args.max_usd:.2f}")
    print(f"\ndone: {counter['posts']} calls, ~${spent:.2f} spent "
          f"(ceiling ${args.max_usd:.2f}), {counter['http_429']} rate-limited retries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
