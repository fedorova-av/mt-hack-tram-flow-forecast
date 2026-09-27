from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import platform
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


SCENARIOS = {
    "health": ["/health"],
    "typical": [
        "/forecast/routes",
        "/forecast?route=7&date_from=2025-11-01&date_to=2025-11-01",
        "/events/applied?route=7&date_from=2025-11-12&date_to=2025-11-20",
        "/geo/route/7",
    ],
    "full_forecast": ["/forecast"],
    "csv_export": [
        "/export/csv?route=7&date_from=2025-11-01&date_to=2025-11-30"
    ],
    "xlsx_export": [
        "/export/xlsx?route=7&date_from=2025-11-01&date_to=2025-11-30"
    ],
}


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def request_once(url: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "tram-load-test/1.0"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
        error = None
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = exc.code
        error = f"HTTPError: {exc}"
    except Exception as exc:  # noqa: BLE001 - load test must count every failure
        body = b""
        status = 0
        error = f"{type(exc).__name__}: {exc}"
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "latency_ms": elapsed_ms,
        "status": status,
        "bytes": len(body),
        "error": error,
    }


class ResourceSampler:
    def __init__(self, pid: int | None) -> None:
        self.pid = pid
        self.samples: list[dict[str, float]] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.pid is None:
            return
        try:
            import psutil

            process = psutil.Process(self.pid)
            process.cpu_percent(interval=None)
        except Exception:  # noqa: BLE001
            return

        def sample() -> None:
            while not self._stop_event.wait(0.05):
                try:
                    self.samples.append(
                        {
                            "rss_mb": process.memory_info().rss / 1024 / 1024,
                            "cpu_percent": process.cpu_percent(interval=None),
                        }
                    )
                except Exception:  # noqa: BLE001
                    break

        self._thread = threading.Thread(target=sample, daemon=True)
        self._thread.start()

    def stop(self) -> dict[str, float | None]:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        if not self.samples:
            return {
                "server_rss_peak_mb": None,
                "server_cpu_mean_percent": None,
                "server_cpu_peak_percent": None,
            }
        return {
            "server_rss_peak_mb": round(max(x["rss_mb"] for x in self.samples), 2),
            "server_cpu_mean_percent": round(
                statistics.fmean(x["cpu_percent"] for x in self.samples), 2
            ),
            "server_cpu_peak_percent": round(
                max(x["cpu_percent"] for x in self.samples), 2
            ),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="HTTP load test for tram backend")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--scenario", choices=SCENARIOS, default="typical")
    parser.add_argument("--requests", type=int, default=2_000)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--server-pid", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.requests <= 0 or args.concurrency <= 0:
        raise ValueError("--requests and --concurrency must be positive")

    base_url = args.base_url.rstrip("/")
    paths = SCENARIOS[args.scenario]
    urls = [base_url + paths[i % len(paths)] for i in range(args.requests)]

    for i in range(args.warmup):
        result = request_once(base_url + paths[i % len(paths)], args.timeout)
        if not 200 <= result["status"] < 300:
            raise RuntimeError(f"Warmup request failed: {result}")

    sampler = ResourceSampler(args.server_pid)
    sampler.start()
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.concurrency
    ) as executor:
        results = list(
            executor.map(lambda url: request_once(url, args.timeout), urls)
        )
    wall_seconds = time.perf_counter() - started
    resources = sampler.stop()

    latencies = [x["latency_ms"] for x in results]
    failures = [x for x in results if not 200 <= x["status"] < 300]
    status_counts = Counter(str(x["status"]) for x in results)
    error_counts = Counter(x["error"] for x in failures if x["error"])

    summary: dict[str, Any] = {
        "scenario": args.scenario,
        "base_url": base_url,
        "paths": paths,
        "requests": len(results),
        "concurrency": args.concurrency,
        "wall_seconds": round(wall_seconds, 4),
        "throughput_rps": round(len(results) / wall_seconds, 2),
        "latency_ms": {
            "min": round(min(latencies), 3),
            "mean": round(statistics.fmean(latencies), 3),
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "p99": round(percentile(latencies, 0.99), 3),
            "max": round(max(latencies), 3),
        },
        "responses": {
            "success": len(results) - len(failures),
            "failed": len(failures),
            "status_counts": dict(status_counts),
            "error_counts": dict(error_counts),
            "total_bytes": sum(x["bytes"] for x in results),
            "mean_bytes": round(statistics.fmean(x["bytes"] for x in results), 1),
        },
        "resources": resources,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "logical_cpu_count": os.cpu_count(),
        },
    }

    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
