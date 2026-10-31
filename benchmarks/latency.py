"""Measure sequential API latency against a running server (one client, one request at a time).

Throughput under concurrency is measured with ApacheBench in load_test.sh: a Python
client saturates before the server does.

    python benchmarks/latency.py --url http://localhost:8000 --label docker

Writes benchmarks/results/latency_<label>.json and prints a Markdown table.
"""
import argparse
import json
import os
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HEALTHY = {"Type": "M", "Air temperature": 298.1, "Process temperature": 308.6,
           "Rotational speed": 1551, "Torque": 42.8, "Tool wear": 10}


def pct(values, p):
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def summary(name, lat_ms, wall_s, n_rows=1, concurrency=1):
    return {
        "scenario": name, "requests": len(lat_ms), "concurrency": concurrency,
        "p50_ms": round(pct(lat_ms, 50), 2), "p95_ms": round(pct(lat_ms, 95), 2), "p99_ms": round(pct(lat_ms, 99), 2),
        "mean_ms": round(statistics.mean(lat_ms), 2),
        "throughput_rps": round(len(lat_ms) / wall_s, 1),
        "rows_per_s": round(len(lat_ms) * n_rows / wall_s, 0),
    }


def sequential(client, name, path, body, n, n_rows=1):
    for _ in range(10):  # warm-up
        client.post(path, json=body)
    lat = []
    t0 = time.perf_counter()
    for _ in range(n):
        s = time.perf_counter()
        r = client.post(path, json=body)
        lat.append((time.perf_counter() - s) * 1000)
        r.raise_for_status()
    return summary(name, lat, time.perf_counter() - t0, n_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--label", default="local")
    ap.add_argument("--n", type=int, default=500)
    args = ap.parse_args()

    batch = [HEALTHY] * 1000
    with httpx.Client(base_url=args.url, timeout=60) as c:
        version = c.get("/api/health").json().get("model_version")
        c.delete("/api/drift")
        results = [
            sequential(c, "single /api/predict (no SHAP)", "/api/predict?explain=false", HEALTHY, args.n),
            sequential(c, "single /api/predict (with SHAP)", "/api/predict", HEALTHY, args.n // 2),
            sequential(c, "batch 1,000 rows /api/predict/batch", "/api/predict/batch", batch, 20, n_rows=1000),
        ]

    report = {"label": args.label, "url": args.url, "model_version": version,
              "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "client": {"platform": platform.platform(), "cpus": os.cpu_count(), "python": platform.python_version()},
              "results": results}
    out = Path(__file__).parent / "results" / f"latency_{args.label}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    print(f"\nTarget: {args.url} ({args.label}) | model v{version} | {platform.platform()}, {os.cpu_count()} CPUs\n")
    print("| Scenario | Requests | Concurrency | p50 (ms) | p95 (ms) | p99 (ms) | Throughput (req/s) | Rows/s |")
    print("|---|---|---|---|---|---|---|---|")
    for r in results:
        print(f"| {r['scenario']} | {r['requests']} | {r['concurrency']} | {r['p50_ms']} | {r['p95_ms']} | "
              f"{r['p99_ms']} | {r['throughput_rps']} | {int(r['rows_per_s']):,} |")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
