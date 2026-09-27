"""
routers/geo.py — эндпоинты для карты: отдаёт координаты остановок маршрута.
"""

from fastapi import APIRouter, HTTPException
from app.schemas import RouteGeometry
from app.geo_loader import GeoData

router = APIRouter(prefix="/geo", tags=["geo"])

geo_data: GeoData | None = None


def set_geo_data(data: GeoData):
    global geo_data
    geo_data = data


@router.get("/routes-with-map", response_model=list[int])
def get_routes_with_map():
    """Список маршрутов, для которых вообще есть география (сейчас: 1,5,7,11,12)."""
    if geo_data is None:
        raise HTTPException(status_code=500, detail="Геоданные не загружены")
    return geo_data.get_routes_with_map()


@router.get("/route/{route}", response_model=RouteGeometry)
def get_route_geometry(route: int):
    """
    Геометрия одного маршрута для отрисовки на карте.

    Пример: /geo/route/7 вернёт оба направления маршрута 7 со списком
    остановок в правильном порядке.

    Если у маршрута нет географии (например, route=25) — вернёт понятную
    ошибку 404, а не пустой/сломанный ответ. Фронт должен обрабатывать
    этот случай — например, показывать "карта недоступна для этого маршрута"
    вместо попытки нарисовать пустую карту.
    """
    if geo_data is None:
        raise HTTPException(status_code=500, detail="Геоданные не загружены")

    directions = geo_data.get_route_geometry(route)

    if directions is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Для маршрута {route} нет географических данных. "
                f"Доступные маршруты с картой: {geo_data.get_routes_with_map()}"
            ),
        )

    return RouteGeometry(route=route, directions=directions)
