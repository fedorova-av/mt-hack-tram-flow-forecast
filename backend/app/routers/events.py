"""
routers/events.py — один эндпоинт: что из календарных правил и
транспортных событий уже учтено моделью для заданных маршрута и периода.

Это ИНФОРМАЦИОННЫЙ эндпоинт — он не пересчитывает прогноз, а объясняет,
что уже сидит внутри уже готового prediction. Пользователь ничего здесь
не редактирует.
"""

from fastapi import APIRouter, HTTPException, Query
from app.events_loader import EventsRegistry

router = APIRouter(prefix="/events", tags=["events"])

events_registry: EventsRegistry | None = None


def set_events_registry(registry: EventsRegistry):
    global events_registry
    events_registry = registry


@router.get("/applied")
def get_applied_events(
    route: int = Query(..., description="Номер маршрута, например 7"),
    date_from: str = Query(..., description="Дата начала периода, YYYY-MM-DD"),
    date_to: str = Query(..., description="Дата конца периода, YYYY-MM-DD"),
):
    """
    Примеры:
    - /events/applied?route=7&date_from=2025-11-13&date_to=2025-11-13
      — покажет пояснение про запуск Т1
    - /events/applied?route=1&date_from=2025-11-02&date_to=2025-11-02
      — обычный маршрут и день без особых правил, вернёт пустой список
    """
    if events_registry is None:
        raise HTTPException(status_code=500, detail="Реестр событий не загружен")

    items = events_registry.applied_for(route, date_from, date_to)
    return {"count": len(items), "items": items}
