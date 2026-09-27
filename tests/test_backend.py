import io
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as session:
        yield session


def test_static_docs_and_forecast(client):
    for path in ["/", "/static/index.html", "/docs", "/redoc", "/openapi.json",
                 "/project-docs/architecture.md",
                 "/project-docs/external_sources_for_final_solution/README.md"]:
        assert client.get(path).status_code == 200, path
    assert client.get("/health").json() == {"status": "healthy"}
    full = client.get("/forecast").json()
    expected = pd.read_csv(ROOT / "ml/outputs/submission.csv", sep=";")
    assert full["count"] == 14640
    pd.testing.assert_frame_equal(pd.DataFrame(full["items"]), expected, check_dtype=False)
    assert len(client.get("/forecast/routes").json()) == 10


def test_filters_exports_and_map(client):
    query = "?route=7&date_from=2025-11-01&date_to=2025-11-01"
    forecast = client.get("/forecast" + query).json()
    assert forecast["count"] == 24
    for kind in ["csv", "xlsx"]:
        response = client.get("/export/" + kind + query)
        assert response.status_code == 200
        data = (pd.read_csv(io.BytesIO(response.content), sep=";") if kind == "csv"
                else pd.read_excel(io.BytesIO(response.content)))
        pd.testing.assert_frame_equal(data, pd.DataFrame(forecast["items"]), check_dtype=False)
    assert client.get("/geo/routes-with-map").json() == [1, 5, 7, 11, 12]
    for route in [1, 5, 7, 11, 12]:
        geometry = client.get(f"/geo/route/{route}").json()
        assert len(geometry["directions"]) == 2
        for direction in geometry["directions"]:
            order = [s["stop_sequence"] for s in direction["stops"]]
            assert order == sorted(order)
    assert client.get("/geo/route/25").status_code == 404
    assert client.get("/forecast?route=999").json() == {"count": 0, "items": []}
    assert client.get("/events/applied?route=7&date_from=2025-11-12&date_to=2025-11-20").json()["count"] > 0


@pytest.mark.parametrize("endpoint", ["/forecast", "/export/csv", "/export/xlsx", "/events/applied"])
@pytest.mark.parametrize("dates", ["date_from=invalid&date_to=2025-11-01",
                                  "date_from=2025-02-30&date_to=2025-11-01",
                                  "date_from=2025-12-01&date_to=2025-11-01"])
def test_invalid_dates(client, endpoint, dates):
    assert client.get(endpoint + "?route=7&" + dates).status_code == 422


@pytest.mark.parametrize("endpoint", ["/forecast", "/export/csv", "/export/xlsx"])
def test_invalid_hour(client, endpoint):
    assert client.get(endpoint + "?hour=24").status_code == 422


def test_startup_from_another_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app.main import app
    with TestClient(app) as session:
        assert session.get("/").status_code == 200
        assert session.get("/forecast?route=7&hour=8").json()["count"] == 61


@pytest.mark.parametrize("row", ["7;2025-11-01;8;nan", "7;2025-11-01;8;-1",
                                "7;2025-11-01;24;1", "7.5;2025-11-01;8;1",
                                "7;2025-02-30;8;1", "7;2025-11-01;8;inf"])
def test_bad_forecast_file(tmp_path, row):
    from app.data_loader import ForecastData
    path = tmp_path / "bad.csv"
    path.write_text("route;date;hour;prediction\n" + row + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ForecastData(path)
