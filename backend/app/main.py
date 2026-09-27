"""
main.py — точка входа приложения. Именно этот файл ты запускаешь,
чтобы стартовал сервер.

Что здесь происходит:
1. Создаём FastAPI-приложение.
2. При старте (событие "startup") один раз загружаем данные из CSV в память.
3. Подключаем роутеры (наборы эндпоинтов из routers/).
4. Настраиваем CORS — это нужно, чтобы фронтенд (который будет работать на
   другом порту/адресе) вообще МОГ обращаться к этому API из браузера.
   Без этого браузер заблокирует запросы фронта к бэку с ошибкой CORS —
   это стандартный защитный механизм браузеров, а не баг.

Как запустить (из папки tram-backend, с активированным окружением):
    uvicorn app.main:app --reload --port 8000

После запуска открой в браузере:
    http://127.0.0.1:8000/docs
Там будет автоматическая интерактивная документация API (это подарок от
FastAPI/Swagger) — можно прямо там потыкать эндпоинты и увидеть ответы,
не дожидаясь фронта.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path

from app.data_loader import ForecastData
from app.geo_loader import GeoData
from app.events_loader import EventsRegistry
from app.routers import forecast, geo, export, events

# Пути к файлам данных. FORECAST_CSV_PATH указывает на финальный прогноз
# v3 от ML-инженеров (T1-factor 0.90)
BACKEND_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BACKEND_DIR / "app" / "static"
DOCS_DIR = BACKEND_DIR.parent / "docs"
FORECAST_CSV_PATH = BACKEND_DIR / "data" / "submission.csv"
GEO_CSV_PATH = BACKEND_DIR / "data" / "route_stops_map.csv"
EVENTS_JSON_PATH = BACKEND_DIR / "data" / "calendar_and_events.json"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Код, который выполняется ОДИН РАЗ при старте сервера (до слеша yield)
    и один раз при остановке (после yield). Это и есть то самое место,
    где мы грузим CSV в память один раз, а не на каждый запрос.
    """
    print("Загружаю данные прогноза...")
    forecast_data = ForecastData(FORECAST_CSV_PATH)
    forecast.set_forecast_data(forecast_data)
    export.set_forecast_data(forecast_data)
    print(f"Загружено {len(forecast_data.df)} строк прогноза")

    print("Загружаю геоданные...")
    geo_data = GeoData(GEO_CSV_PATH)
    geo.set_geo_data(geo_data)
    routes_with_map = geo_data.get_routes_with_map()
    forecast.set_routes_with_map(routes_with_map)
    print(f"Маршруты с картой: {routes_with_map}")

    print("Загружаю реестр событий и календарных правил...")
    events_registry = EventsRegistry(EVENTS_JSON_PATH)
    events.set_events_registry(events_registry)

    yield  # приложение работает здесь

    print("Остановка сервера")


app = FastAPI(
    title="Прогноз пассажиропотока трамваев",
    description="API для дашборда прогнозирования нагрузки на трамвайные маршруты Москвы",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — разрешаем запросы с любого адреса. Для хакатона это нормально
# и безопасно (внутренний демо-сервис, не публичный продукт с реальными
# пользователями). Если бы это был настоящий production-сервис с
# конфиденциальными данными, тут стоило бы явно перечислить конкретные
# разрешённые домены фронта, а не звёздочку.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры — каждый со своим префиксом пути (задан в самом роутере)
app.include_router(forecast.router)
app.include_router(geo.router)
app.include_router(export.router)
app.include_router(events.router)

# Отдаём файлы дашборда (index.html, если появятся картинки/css — тоже сюда).
# StaticFiles обслуживает файлы из папки app/static/ по пути /static/...
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Отдаём документы из папки docs/ (архитектура, источники, лимиты модели
# и т.д.) — так ссылки на них с дашборда открываются прямо в браузере,
# без похода в файлы репозитория. html=False, потому что это обычные
# .md-файлы, не HTML-страницы для рендеринга браузером.
app.mount("/project-docs", StaticFiles(directory=DOCS_DIR), name="project-docs")


@app.get("/")
def root():
    """
    Главная страница — сразу открывает дашборд, а не JSON-заглушку.
    Если файл дашборда почему-то не найден, вернёт понятную ошибку,
    а не сломает весь сервер.
    """
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    """
    Эндпоинт для проверки "жив ли сервис" — стандартная практика,
    полезно для Docker/мониторинга и просто для быстрой проверки руками.
    """
    return {"status": "healthy"}
