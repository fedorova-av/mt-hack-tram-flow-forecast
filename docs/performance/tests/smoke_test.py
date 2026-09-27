from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.error
import urllib.request


def fetch(base_url: str, path: str) -> tuple[int, bytes, str]:
    request = urllib.request.Request(base_url.rstrip("/") + path)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "")


def get_json(base_url: str, path: str) -> dict | list:
    status, body, _ = fetch(base_url, path)
    assert status == 200, (path, status, body[:300])
    return json.loads(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for tram backend")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base_url = args.base_url
    checks = 0

    status, body, content_type = fetch(base_url, "/")
    assert status == 200 and "text/html" in content_type
    assert "ИИ-прогноз загрузки трамвайных маршрутов" in body.decode("utf-8")
    checks += 1

    assert get_json(base_url, "/health") == {"status": "healthy"}
    checks += 1

    routes = get_json(base_url, "/forecast/routes")
    assert len(routes) == 10
    assert [x["route"] for x in routes] == [1, 5, 7, 11, 12, 17, 25, 26, 28, 50]
    checks += 1

    one_day = get_json(
        base_url,
        "/forecast?route=7&date_from=2025-11-01&date_to=2025-11-01",
    )
    assert one_day["count"] == 24
    checks += 1

    full = get_json(base_url, "/forecast")
    assert full["count"] == 14_640
    assert round(sum(x["prediction"] for x in full["items"])) == 12_550_152
    checks += 1

    assert get_json(base_url, "/geo/routes-with-map") == [1, 5, 7, 11, 12]
    geometry = get_json(base_url, "/geo/route/7")
    assert geometry["route"] == 7 and len(geometry["directions"]) == 2
    checks += 1

    status, _, _ = fetch(base_url, "/geo/route/25")
    assert status == 404
    checks += 1

    events = get_json(
        base_url,
        "/events/applied?route=7&date_from=2025-11-12&date_to=2025-11-20",
    )
    assert events["count"] > 0
    checks += 1

    status, csv_body, content_type = fetch(
        base_url,
        "/export/csv?route=7&date_from=2025-11-01&date_to=2025-11-01",
    )
    assert status == 200 and "text/csv" in content_type
    rows = list(csv.DictReader(io.StringIO(csv_body.decode("utf-8")), delimiter=";"))
    assert len(rows) == 24

    status, xlsx_body, content_type = fetch(
        base_url,
        "/export/xlsx?route=7&date_from=2025-11-01&date_to=2025-11-01",
    )
    assert status == 200 and "spreadsheetml" in content_type
    assert xlsx_body.startswith(b"PK")
    checks += 1

    print(f"OK: {checks} smoke-test groups passed")


if __name__ == "__main__":
    main()
