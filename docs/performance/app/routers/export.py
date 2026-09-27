"""
routers/export.py — выгрузка прогноза в CSV и XLSX.
Это отдельное требование в задании хакатона (критерий 4: "Экспорт данных").
"""

import io
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from app.data_loader import ForecastData

router = APIRouter(prefix="/export", tags=["export"])

forecast_data: ForecastData | None = None


def set_forecast_data(data: ForecastData):
    global forecast_data
    forecast_data = data


@router.get("/csv")
def export_csv(
    route: int | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    hour: int | None = Query(default=None),
):
    """
    Выгружает отфильтрованный прогноз в CSV-файл — можно открыть в браузере
    (скачается автоматически) или вызвать напрямую из фронта по клику
    на кнопку "Скачать CSV".

    StreamingResponse — способ отдать файл как ответ HTTP-запроса, не
    сохраняя его временный файл на диск: собираем содержимое в памяти
    и сразу отдаём.
    """
    if forecast_data is None:
        raise HTTPException(status_code=500, detail="Данные прогноза не загружены")

    filtered = forecast_data.filter(
        route=route, date_from=date_from, date_to=date_to, hour=hour
    )

    buffer = io.StringIO()
    filtered.to_csv(buffer, sep=";", index=False, encoding="utf-8")
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=forecast_export.csv"},
    )


@router.get("/xlsx")
def export_xlsx(
    route: int | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    hour: int | None = Query(default=None),
):
    """То же самое, но в формате Excel (.xlsx) — вторая опция из требований."""
    if forecast_data is None:
        raise HTTPException(status_code=500, detail="Данные прогноза не загружены")

    filtered = forecast_data.filter(
        route=route, date_from=date_from, date_to=date_to, hour=hour
    )

    buffer = io.BytesIO()
    # engine="openpyxl" — та самая библиотека, что мы ставили при настройке
    filtered.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=forecast_export.xlsx"},
    )
