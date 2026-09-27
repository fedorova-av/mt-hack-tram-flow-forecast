"""
routers/forecast.py — эндпоинты, связанные с прогнозом пассажиропотока.

Что такое "роутер" и "эндпоинт" (коротко):
- Эндпоинт — это один конкретный адрес API, на который можно обратиться,
  например GET /forecast. У каждого эндпоинта есть путь (URL) и метод
  (GET — получить данные, POST — отправить данные и т.д.). Мы везде
  используем GET, потому что только ОТДАЁМ данные, ничего не принимаем.
- Роутер — это способ сгруппировать несколько связанных эндпоинтов в один
  файл, чтобы main.py не разрастался в один гигантский файл со всем API.
  Потом мы "подключаем" роутер в main.py одной строкой.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from app.schemas import ForecastResponse, RouteSummary
from app.data_loader import ForecastData

# APIRouter — это "мини-приложение", в которое мы добавляем эндпоинты.
router = APIRouter(prefix="/forecast", tags=["forecast"])

# Сюда main.py положит загруженные данные при старте сервера.
# Это простой способ "прокинуть" общие данные во все роуты без сложных
# конструкций — для хакатона более чем достаточно.
forecast_data: ForecastData | None = None


def set_forecast_data(data: ForecastData):
    global forecast_data
    forecast_data = data


# Список маршрутов, для которых есть география — тоже прокидываем из main.py,
# по той же схеме, что и forecast_data выше.
routes_with_map_list: list[int] = []


def set_routes_with_map(routes: list[int]):
    global routes_with_map_list
    routes_with_map_list = routes


@router.get("", response_model=ForecastResponse)
def get_forecast(
    # Query(...) — это способ описать параметр из строки запроса
    # (то, что после ? в URL, например /forecast?route=7).
    # default=None означает "необязательный параметр".
    # description — то, что увидит фронтендер в автодокументации на /docs.
    route: int | None = Query(
        default=None, description="Номер маршрута, например 7"
    ),
    date_from: str | None = Query(
        default=None, description="Дата начала периода, формат YYYY-MM-DD"
    ),
    date_to: str | None = Query(
        default=None, description="Дата конца периода, формат YYYY-MM-DD"
    ),
    hour: int | None = Query(
        default=None, ge=0, le=23, description="Конкретный час (0-23)"
    ),
):
    """
    Основной эндпоинт: отдаёт прогноз с фильтрацией.

    Примеры вызова (можно вставить прямо в браузер после запуска сервера):
    - /forecast — весь прогноз целиком (14 640 строк, для теста)
    - /forecast?route=7 — только маршрут 7, все даты и часы
    - /forecast?route=7&date_from=2025-11-01&date_to=2025-11-07
      — маршрут 7 за первую неделю ноября (это и есть "горизонт: день",
      просто в виде диапазона из одного или нескольких дней)
    - /forecast?route=7&date_from=2025-11-01&date_to=2025-11-30
      — маршрут 7 за весь месяц (горизонт "месяц")
    - /forecast?route=7&hour=8 — маршрут 7, только 8 утра, за весь период
    """
    if forecast_data is None:
        raise HTTPException(status_code=500, detail="Данные прогноза не загружены")

    filtered = forecast_data.filter(
        route=route, date_from=date_from, date_to=date_to, hour=hour
    )

    # Данные полностью проверяются и типизируются один раз при старте сервиса.
    # Для ответа используем векторизованную сериализацию pandas, а не iterrows
    # + 14 640 отдельных Pydantic-объектов. Формат JSON остаётся тем же, но
    # полная выдача становится на порядок быстрее и создаёт меньше объектов.
    items_json = filtered.to_json(orient="records", force_ascii=False)
    payload = f'{{"count":{len(filtered)},"items":{items_json}}}'
    return Response(content=payload, media_type="application/json")


@router.get("/routes", response_model=list[RouteSummary])
def get_routes():
    """
    Список всех маршрутов со сводкой — удобно, чтобы фронт построил
    выпадающий список/меню маршрутов и сразу знал, для каких из них
    доступна карта (has_map).
    """
    if forecast_data is None:
        raise HTTPException(status_code=500, detail="Данные прогноза не загружены")

    totals = forecast_data.total_by_route()

    return [
        RouteSummary(
            route=route,
            has_map=route in routes_with_map_list,
            total_prediction=float(totals.get(route, 0)),
        )
        for route in forecast_data.get_available_routes()
    ]
