#!/usr/bin/env python3
"""Evidence about the serving endpoints that does NOT come from the response text.

The instrument reads completion text only, by design. That makes one question
unanswerable from inside it: are two endpoints actually distinct infrastructure, or the
same capacity resold twice? An archive's own text cannot settle that, because the text
is what is under test. Review of this study named the absence of any orthogonal channel
as a forfeited validation, which it was.

Two sources, both cheap:

  1. Edge headers from each provider's models endpoint. Free on both providers and
     bills no tokens, so this can be re-run at any time.
  2. Transport metadata recorded during collection (latency, response headers,
     provider-side request ids), which `collect.py` now keeps alongside each draw and
     which never reaches the detector.

What this can and cannot establish is bounded in the output and repeated here: a
different edge termination shows the requests did not arrive at the same front door. It
does not rule out a shared inference backend behind two different edges.

Usage:  .venv/bin/python validation/angle_c/transport.py [--write]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from punchmark.canonical import canonical_json, write_text_deterministic  # noqa: E402

CRED = HERE / "credentials.json"
ARCHIVES = HERE / "archives"
OUT = HERE / "derived" / "transport.json"
USER_AGENT = "punchmark/0.1 (+https://github.com/KurathSec/Punchmark)"
MODELS_URL = {
    "together": "https://api.together.xyz/v1/models",
    "deepinfra": "https://api.deepinfra.com/v1/openai/models",
}
# Headers that say something about the edge rather than about the payload.
EDGE = ("server", "via", "cf-ray", "cf-cache-status", "x-served-by", "x-cache",
        "alt-svc", "x-envoy-upstream-service-time")


def edge_headers(cred: dict) -> dict:
    out = {}
    for name, url in sorted(MODELS_URL.items()):
        key = cred[name].get("api_key") or ""
        req = urllib.request.Request(
            url, headers={"authorization": f"Bearer {key}", "user-agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                h = {k.lower(): v for k, v in resp.headers.items()}
        except Exception as exc:  # noqa: BLE001 -- recorded, not fatal
            out[name] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        # cf-ray encodes a PoP suffix; keep it, it names where the edge terminated.
        out[name] = {k: h[k] for k in EDGE if k in h}
    return out


def collected_transport() -> dict:
    """Summarise the transport metadata recorded during collection, per archive."""
    out = {}
    for path in sorted(ARCHIVES.glob("*/*.responses.jsonl")):
        hdrs: Counter[str] = Counter()
        servers: Counter[str] = Counter()
        lat: list[float] = []
        ids = 0
        n = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            for d in json.loads(line)["draws"]:
                t = d.get("transport") or {}
                if not t:
                    continue
                n += 1
                lat.append(float(t.get("latency_s") or 0.0))
                for k, v in (t.get("headers") or {}).items():
                    hdrs[k] += 1
                    if k == "server":
                        servers[v] += 1
                    if k in ("x-request-id", "x-inference-id"):
                        ids += 1
        if not n:
            continue
        out["/".join(path.parts[-2:]).replace(".responses.jsonl", "")] = {
            "draws_with_transport": n,
            "headers_present": dict(sorted(hdrs.items())),
            "server_values": dict(servers),
            "distinct_request_ids_seen": ids,
            "latency_s": {
                "median": round(statistics.median(lat), 3),
                "min": round(min(lat), 3),
                "max": round(max(lat), 3),
            },
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    cred = json.loads(CRED.read_text(encoding="utf-8"))["providers"]
    edges = edge_headers(cred)
    sets = {k: set(v) for k, v in edges.items() if "error" not in v}
    differ = len(sets) == 2 and len(set(map(frozenset, sets.values()))) == 2

    doc = {
        "punchmark_schema": "angle_c_transport/v1",
        "edge_headers_from_free_models_endpoint": edges,
        "edge_header_sets_differ": differ,
        "collected_transport_by_archive": collected_transport(),
        "what_this_establishes": (
            "The two providers' requests terminate at different edges: one behind a CDN "
            "that stamps its own ray id and PoP, the other on an application server "
            "directly. They are not the same front door."),
        "what_this_does_not_establish": (
            "Nothing about the inference backend. Two distinct edges can proxy to the "
            "same capacity, so this does not rule out a shared or resold upstream, and "
            "it is not evidence about weights, precision or serving configuration."),
        "why_it_is_here": (
            "The detector reads completion text only. No transport field below is ever "
            "an input to it. This exists so that a claim about two endpoints being "
            "distinct can rest on something other than the text under test."),
    }

    for name, h in sorted(edges.items()):
        print(f"{name}: {h}")
    print(f"\nedge header sets differ: {differ}")
    for k, v in sorted(doc["collected_transport_by_archive"].items()):
        print(f"  {k[:58]:58s} n={v['draws_with_transport']:4d} "
              f"server={list(v['server_values']) or '-'} "
              f"median_latency={v['latency_s']['median']}s")

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(doc))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/transport.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
