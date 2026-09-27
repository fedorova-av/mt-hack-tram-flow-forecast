# Backend и дашборд прогноза загрузки трамваев

FastAPI-сервис отдаёт финальный прогноз v3, календарные и транспортные пояснения, геоданные остановок и web-дашборд. В репозитории уже находится проверенный `data/submission.csv` на 14 640 строк.

## Быстрый запуск

Требуется Python 3.10 или новее.

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

После запуска:

- дашборд: http://127.0.0.1:8000/
- интерактивная документация API: http://127.0.0.1:8000/docs
- health-check: http://127.0.0.1:8000/health

## Основные эндпоинты

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/` | Web-дашборд |
| GET | `/health` | Проверка готовности сервиса |
| GET | `/forecast` | Прогноз с фильтрами `route`, `date_from`, `date_to`, `hour` |
| GET | `/forecast/routes` | Маршруты, суммарный прогноз и доступность карты |
| GET | `/events/applied` | События, уже учтённые моделью, со ссылками на источники |
| GET | `/geo/routes-with-map` | Маршруты с географией |
| GET | `/geo/route/{route}` | Остановки обоих направлений в правильном порядке |
| GET | `/export/csv` | Экспорт отфильтрованного прогноза в CSV |
| GET | `/export/xlsx` | Экспорт в Excel |

Пример:

```text
GET /forecast?route=7&date_from=2025-11-01&date_to=2025-11-30
```

## Производительность

Локальный нагрузочный тест от 28.09.2026: 9 650 HTTP-запросов, 0 ошибок. Смешанный API — 646 RPS и `p95 = 97 мс`; полная выдача 14 640 строк — `p95 = 93 мс`; максимальный RSS — 172 MB.

Полная методика, ограничения и список дополнительных возможностей: [`docs/performance_and_features.md`](docs/performance_and_features.md). Короткий текст для формы: [`FORM_RESPONSE.md`](FORM_RESPONSE.md).

Повторить проверку:

```bash
pip install -r requirements-loadtest.txt
python tests/smoke_test.py --base-url http://127.0.0.1:8000
python tests/load_test.py --scenario typical --requests 4000 --concurrency 50
```

## Структура

```text
tram_backend_ready/
├── app/
│   ├── main.py
│   ├── data_loader.py
│   ├── events_loader.py
│   ├── geo_loader.py
│   ├── schemas.py
│   ├── routers/
│   └── static/index.html
├── data/
│   ├── submission.csv
│   ├── calendar_and_events.json
│   └── route_stops_map.csv
├── docs/
│   ├── external_sources.md
│   ├── performance_and_features.md
│   └── performance/*.json
├── tests/
│   ├── smoke_test.py
│   └── load_test.py
├── FORM_RESPONSE.md
├── requirements.txt
└── requirements-loadtest.txt
```

## Данные и ограничения

- Прогноз: 10 маршрутов, период 01.11.2025–31.12.2025, гранулярность `route × date × hour`.
- `data/submission.csv` совпадает с выбранным v3: SHA-256 `91db17acbbc18bb8ac845a2c90ddd946a1d6fff74cf4123a51ac6b31f45cc8f8`.
- География есть только для маршрутов 1, 5, 7, 11 и 12 — таков объём исходного справочника.
- Прогноз относится ко всему маршруту, а не к отдельной остановке.
- Сценарии «что если» выполняются в интерфейсе и визуально отделены от базового ML-прогноза.
- Сервис хранит небольшой набор данных в памяти и не требует базы данных.
- Для публичного production-развёртывания следует ограничить CORS, добавить аутентификацию при необходимости и настроить reverse proxy/TLS.
