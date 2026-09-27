"""
schemas.py — здесь описано, как ИМЕННО выглядит JSON, который отдаёт наш API.

Что такое Pydantic-схема (коротко):
Это класс-описание структуры данных. Мы говорим FastAPI: "ответ на этот
запрос будет вот с такими полями и вот такими типами". FastAPI сам
проверяет данные на соответствие схеме и сам генерирует документацию
(она появится на /docs, когда запустим сервер).

Если бы мы просто возвращали словарь Python (dict), фронтендер не знал бы
заранее, какие поля точно будут в ответе. Схема — это контракт между
backend и frontend.
"""

from pydantic import BaseModel
from typing import Optional


class ForecastPoint(BaseModel):
    """Один прогноз: конкретный маршрут, дата, час и число пассажиров."""
    route: int
    date: str          # формат YYYY-MM-DD, как строка (проще для фронта и JSON)
    hour: int           # 0-23
    prediction: float   # прогноз числа посадок


class ForecastResponse(BaseModel):
    """Ответ на запрос списка прогнозов — с учётом фильтров."""
    count: int                     # сколько строк вернулось
    items: list[ForecastPoint]     # сами данные


class RouteSummary(BaseModel):
    """Короткая сводка по одному маршруту — для списка маршрутов на фронте."""
    route: int
    has_map: bool          # есть ли география для этого маршрута (для карты)
    total_prediction: float  # суммарный прогноз за весь период (для общей картины)


class StopPoint(BaseModel):
    """Одна остановка на маршруте — для отрисовки на карте."""
    stop_id: int
    stop_name: str
    stop_sequence: int
    lat: float
    lon: float


class RouteDirection(BaseModel):
    """Одно направление маршрута (туда ИЛИ обратно) — со списком остановок по порядку."""
    trip_id: int
    direction_id: int
    stops: list[StopPoint]


class RouteGeometry(BaseModel):
    """Полная геометрия маршрута — оба направления."""
    route: int
    directions: list[RouteDirection]


class ErrorResponse(BaseModel):
    """Единый формат ошибок, чтобы фронт всегда знал, чего ожидать при сбое."""
    detail: str
